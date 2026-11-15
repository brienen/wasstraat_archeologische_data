"""Registratie van bronbestanden en bepaling van de delta (incrementeel laden, issue 61).

Elk invoerbestand (Access-database, spreadsheet, afbeelding, rapport) wordt
geregistreerd in de tabel ``Def_Bronbestand`` in PostgreSQL met een
vingerafdruk (grootte + mtime als snelle controle, sha256 als inhoudelijke
controle). Een incrementele run vergelijkt de bestanden op schijf met de
registratie en bepaalt per bestand de status ``nieuw``, ``gewijzigd``,
``ongewijzigd`` of ``verwijderd``.

Publieke taken:

- ``bepaalDelta()``: taak Bepaal_Delta van de incrementele cyclus
- ``registreerBronbestanden()``: taak Registreer_Run van de incrementele cyclus
- ``registreerVolledigeCyclus()``: taak Registreer_Bronbestanden van de volledige cyclus

De tabel ``Def_Bronbestand`` valt buiten de atomic swap van ``loadAll()`` en
wordt door ``shared.database.getAllTables()`` overgeslagen, zodat er geen
Elasticsearch-index voor wordt gemaakt.
"""
import os
import hashlib

import bson
import pymongo
import psycopg2.extras

import shared.config as config
import wasstraat.verwerkingsrun as verwerkingsrun
import wasstraat.image_import as image_import
import wasstraat.paden_overslaan as paden_overslaan
from wasstraat.loadToDatabase_functions import getPgConnection
import logging

logger = logging.getLogger("airflow.task")

TABEL_BRONBESTAND = 'Def_Bronbestand'

# Invoercategorieën
CAT_PROJECTEN = 'projecten'
CAT_PROJECTENLIJST = 'projectenlijst'
CAT_MAGAZIJNLIJST = 'magazijnlijst'
CAT_FOTOLIJST = 'fotolijst'
CAT_MONSTERDATABASE = 'monsterdatabase'
CAT_RAPPORTEN = 'rapporten'
CAT_REFERENTIETABELLEN = 'referentietabellen'
CAT_EXTRA_PROJECTEN = 'extra_projecten'
CAT_BESTANDENLIJST = 'bestandenlijst'
CAT_AFBEELDINGEN = 'afbeeldingen'

# Statussen in de registratie
REG_VERWERKT = 'verwerkt'
REG_MISLUKT = 'mislukt'
REG_VERWIJDERD = 'verwijderd'

MDB_EXTENSIES = ('.mdb', '.accdb')
HASH_BLOKGROOTTE = 1024 * 1024
BATCH_GROOTTE = 10000
# Bovengrens voor de padlijsten in het run-document (MongoDB staat max. 16 MB per document toe)
MAX_LIJSTEN_BYTES = 12 * 1024 * 1024
# Maximaal aantal overgeslagen paden (paden_overslaan, issue 84) per categorie in het run-document;
# de tellingen zijn altijd volledig
MAX_OVERGESLAGEN_PADEN = 1000

SQL_MAAK_TABEL = f'''
    CREATE TABLE IF NOT EXISTS "{TABEL_BRONBESTAND}" (
        pad TEXT PRIMARY KEY,
        categorie TEXT NOT NULL,
        grootte BIGINT,
        mtime DOUBLE PRECISION,
        sha256 CHAR(64),
        status TEXT NOT NULL CHECK (status IN ('{REG_VERWERKT}', '{REG_MISLUKT}', '{REG_VERWIJDERD}')),
        verwerkt_op TIMESTAMP,
        run_id TEXT,
        aantal_records INTEGER NOT NULL DEFAULT 0
    )
'''

SQL_UPSERT = f'''
    INSERT INTO "{TABEL_BRONBESTAND}"
        (pad, categorie, grootte, mtime, sha256, status, verwerkt_op, run_id, aantal_records)
    VALUES %s
    ON CONFLICT (pad) DO UPDATE SET
        categorie = EXCLUDED.categorie,
        grootte = EXCLUDED.grootte,
        mtime = EXCLUDED.mtime,
        sha256 = EXCLUDED.sha256,
        status = EXCLUDED.status,
        verwerkt_op = EXCLUDED.verwerkt_op,
        run_id = EXCLUDED.run_id,
        aantal_records = EXCLUDED.aantal_records
'''

SQL_WERK_VINGERAFDRUK_BIJ = f'''
    UPDATE "{TABEL_BRONBESTAND}" AS b
    SET grootte = v.grootte, mtime = v.mtime, sha256 = v.sha256
    FROM (VALUES %s) AS v(pad, grootte, mtime, sha256)
    WHERE b.pad = v.pad
'''


# ============================================================
# Categorieën en paden
# ============================================================

def getMdbCategorieen():
    """Retourneer de MDB-categorieën met hun invoermap en staging-collectie.

    Dit zijn de zes mappen die importMDB.sh in de Extract-groep verwerkt.

    Returns:
        Lijst met tuples (categorie, invoermap, staging-collectie)
    """
    return [
        (CAT_PROJECTEN, config.AIRFLOW_INPUT_PROJECTEN, config.COLL_STAGING_OUD),
        (CAT_PROJECTENLIJST, config.AIRFLOW_INPUT_PROJECTENLIJST, config.COLL_STAGING_PROJECTENLIJST),
        (CAT_MAGAZIJNLIJST, config.AIRFLOW_INPUT_MAGAZIJNLIJST, config.COLL_STAGING_MAGAZIJNLIJST),
        (CAT_FOTOLIJST, config.AIRFLOW_INPUT_FOTOLIJST, config.COLL_STAGING_FOTOLIJST),
        (CAT_MONSTERDATABASE, config.AIRFLOW_INPUT_MONSTER, config.COLL_STAGING_MONSTER),
        (CAT_RAPPORTEN, config.AIRFLOW_INPUT_RAPPORTEN, config.COLL_STAGING_RAPPORTEN),
    ]


def getMdbCategorieNamen():
    """Retourneer de namen van de MDB-categorieën."""
    return [categorie for categorie, _, _ in getMdbCategorieen()]


def getLosseBestanden():
    """Retourneer de losse invoerbestanden met hun categorie.

    Returns:
        Lijst met tuples (categorie, pad)
    """
    return [
        (CAT_REFERENTIETABELLEN, config.FILE_ABREXCEL),
        (CAT_EXTRA_PROJECTEN, config.FILE_EXTRA_PROJECTS),
        (CAT_BESTANDENLIJST, config.FILE_IMPORT_FILES_EXCEL),
    ]


def getLijstbestandPad(categorie):
    """Retourneer het pad van het lijstbestand voor importMDB.sh van een MDB-categorie.

    Args:
        categorie: bijv. 'projecten'

    Returns:
        Pad in AIRFLOW_TEMPDIR, bijv. /opt/airflow/tmp/delta_projecten.txt
    """
    return os.path.join(str(config.AIRFLOW_TEMPDIR), f'delta_{categorie}.txt')


# ============================================================
# Scannen en vingerafdrukken
# ============================================================

def zoekMdbBestanden(invoermap, overgeslagen=None):
    """Zoek alle MDB/ACCDB-bestanden met exact dezelfde selectie als importMDB.sh.

    importMDB.sh gebruikt ``"$1"/**/*.mdb "$1"/**/*.accdb`` met globstar: recursief,
    hoofdlettergevoelige extensie, zonder verborgen bestanden en mappen en zonder
    symbolisch gelinkte mappen te volgen. Daarna laten beide de bestanden weg
    die onder een patroon uit paden_overslaan in correcties.yml vallen (issue
    84, wasstraat/paden_overslaan.py), met een logregel per bestand.

    Args:
        invoermap: map om te doorzoeken
        overgeslagen: optionele lijst die met de overgeslagen paden wordt aangevuld

    Returns:
        Gesorteerde lijst met volledige paden
    """
    if not invoermap or not os.path.isdir(invoermap):
        return []
    resultaat = []
    for dirpath, dirnames, filenames in os.walk(invoermap):
        dirnames[:] = [d for d in dirnames if not d.startswith('.')]
        for f in filenames:
            if not f.startswith('.') and f.endswith(MDB_EXTENSIES):
                resultaat.append(os.path.join(dirpath, f))
    return paden_overslaan.filterPaden(sorted(resultaat), invoermap, overgeslagen=overgeslagen,
                                       omschrijving='Access-databases')


def zoekAfbeeldingen(overgeslagen=None):
    """Zoek alle afbeeldingen en rapporten met dezelfde selectie als de extractie (image_import).

    Args:
        overgeslagen: optionele lijst die met de paden wordt aangevuld die
            volgens paden_overslaan in correcties.yml worden overgeslagen
    """
    return sorted(set(image_import.getImageFilenames(overgeslagen=overgeslagen)))


def leesVingerafdruk(pad):
    """Lees de snelle vingerafdruk van een bestand.

    Returns:
        Tuple (grootte in bytes, mtime als float)
    """
    st = os.stat(pad)
    return st.st_size, st.st_mtime


def berekenSha256(pad):
    """Bereken de sha256-hash van de inhoud van een bestand (in blokken van 1 MB)."""
    h = hashlib.sha256()
    with open(pad, 'rb') as f:
        for blok in iter(lambda: f.read(HASH_BLOKGROOTTE), b''):
            h.update(blok)
    return h.hexdigest()


def scanBronbestanden(overgeslagen=None):
    """Scan alle invoerbestanden per categorie.

    Bestanden die onder een patroon uit paden_overslaan in correcties.yml
    vallen, worden niet gescand (issue 84). Een geregistreerd bestand dat zo
    buiten de selectie valt, geldt daarna als verwijderd.

    Args:
        overgeslagen: optionele dict die per categorie wordt aangevuld met de
            gesorteerde lijst van overgeslagen paden

    Returns:
        Dict pad -> {'categorie', 'grootte', 'mtime'}
    """
    bestanden = {}
    if overgeslagen is None:
        overgeslagen = {}

    def voegToe(pad, categorie):
        if pad in bestanden:
            if bestanden[pad]['categorie'] != categorie:
                logger.warning(f"Bestand {pad} hoort bij zowel {bestanden[pad]['categorie']} als {categorie}; "
                               f"het wordt geregistreerd als {bestanden[pad]['categorie']}.")
            return
        try:
            grootte, mtime = leesVingerafdruk(pad)
        except OSError as err:
            logger.warning(f"Bestand {pad} ({categorie}) is niet leesbaar en wordt overgeslagen: {err}")
            return
        bestanden[pad] = {'categorie': categorie, 'grootte': grootte, 'mtime': mtime}

    for categorie, invoermap, _ in getMdbCategorieen():
        weggelaten = []
        for pad in zoekMdbBestanden(invoermap, overgeslagen=weggelaten):
            voegToe(pad, categorie)
        if weggelaten:
            overgeslagen[categorie] = sorted(weggelaten)
    weggelaten = []
    for pad in zoekAfbeeldingen(overgeslagen=weggelaten):
        voegToe(pad, CAT_AFBEELDINGEN)
    if weggelaten:
        overgeslagen[CAT_AFBEELDINGEN] = sorted(set(weggelaten))
    for categorie, pad in getLosseBestanden():
        if pad and os.path.isfile(pad):
            voegToe(pad, categorie)

    if overgeslagen:
        logger.info(f"{len(bestanden)} bronbestanden gevonden, {sum(len(p) for p in overgeslagen.values())} "
                    f"overgeslagen volgens paden_overslaan: {telOvergeslagen(overgeslagen)}.")
    else:
        logger.info(f"{len(bestanden)} bronbestanden gevonden.")
    return bestanden


def telOvergeslagen(overgeslagen):
    """Tel de overgeslagen paden (paden_overslaan) per categorie, plus een totaal.

    Args:
        overgeslagen: dict categorie -> lijst met paden (uit scanBronbestanden)

    Returns:
        Dict categorie -> aantal, met de extra sleutel 'totaal'
    """
    tellingen = {categorie: len(paden) for categorie, paden in sorted(overgeslagen.items())}
    tellingen['totaal'] = sum(tellingen.values())
    return tellingen


def maakOvergeslagenVelden(overgeslagen):
    """Velden voor het run-document met de paden die paden_overslaan overslaat (issue 84).

    ``paden_overgeslagen`` bevat per categorie de gesorteerde paden (hoogstens
    MAX_OVERGESLAGEN_PADEN per categorie), ``tellingen.paden_overgeslagen`` de
    volledige aantallen per categorie en het totaal.

    Args:
        overgeslagen: dict categorie -> lijst met paden (uit scanBronbestanden)

    Returns:
        Dict met veldnamen voor verwerkingsrun.werkRunBij
    """
    paden = {categorie: sorted(lijst)[:MAX_OVERGESLAGEN_PADEN] for categorie, lijst in sorted(overgeslagen.items())}
    return {'paden_overgeslagen': paden, 'tellingen.paden_overgeslagen': telOvergeslagen(overgeslagen)}


def bepaalStatussen(gescand, geregistreerd, berekenHash=berekenSha256):
    """Bepaal per bestand de status ten opzichte van de registratie.

    De sha256 wordt alleen opnieuw berekend als grootte of mtime afwijkt van de
    registratie (of als het bestand nieuw is). Een bestand met registratiestatus
    'mislukt' geldt als gewijzigd, zodat het opnieuw wordt verwerkt. Een
    bestand met registratiestatus 'verwijderd' dat weer opduikt geldt als nieuw.

    Args:
        gescand: dict pad -> {'categorie', 'grootte', 'mtime'} (uit scanBronbestanden)
        geregistreerd: dict pad -> {'categorie', 'grootte', 'mtime', 'sha256', 'status'}
        berekenHash: functie pad -> sha256 (vervangbaar in tests)

    Returns:
        Tuple (records, aantal_hashes). Elk record is een dict met pad, categorie,
        status, grootte, mtime, sha256 en vingerafdruk_bijgewerkt (True als een
        ongewijzigd bestand een nieuwe grootte/mtime heeft die in de registratie
        moet worden bijgewerkt).
    """
    records = []
    aantal_hashes = 0

    for pad in sorted(gescand):
        info = gescand[pad]
        reg = geregistreerd.get(pad)
        record = {'pad': pad, 'categorie': info['categorie'], 'grootte': info['grootte'], 'mtime': info['mtime'],
                  'sha256': None, 'vingerafdruk_bijgewerkt': False}

        if reg is None or reg.get('status') == REG_VERWIJDERD:
            record['sha256'] = berekenHash(pad)
            aantal_hashes += 1
            record['status'] = verwerkingsrun.STATUS_NIEUW
        else:
            zelfde_vingerafdruk = (reg.get('grootte') == info['grootte'] and reg.get('mtime') == info['mtime']
                                   and bool(reg.get('sha256')))
            if zelfde_vingerafdruk:
                record['sha256'] = reg['sha256']
            else:
                record['sha256'] = berekenHash(pad)
                aantal_hashes += 1

            if reg.get('status') == REG_MISLUKT:
                record['status'] = verwerkingsrun.STATUS_GEWIJZIGD
            elif record['sha256'] == reg.get('sha256'):
                record['status'] = verwerkingsrun.STATUS_ONGEWIJZIGD
                record['vingerafdruk_bijgewerkt'] = not zelfde_vingerafdruk
            else:
                record['status'] = verwerkingsrun.STATUS_GEWIJZIGD
        records.append(record)

    for pad in sorted(geregistreerd):
        reg = geregistreerd[pad]
        if pad not in gescand and reg.get('status') != REG_VERWIJDERD:
            records.append({'pad': pad, 'categorie': reg.get('categorie'), 'status': verwerkingsrun.STATUS_VERWIJDERD,
                            'grootte': reg.get('grootte'), 'mtime': reg.get('mtime'), 'sha256': reg.get('sha256'),
                            'vingerafdruk_bijgewerkt': False})

    return records, aantal_hashes


def maakDeltaLijsten(records):
    """Groepeer de records tot lijsten per status en categorie.

    Returns:
        Dict status -> categorie -> gesorteerde lijst met paden (alle vier statussen aanwezig)
    """
    lijsten = {status: {} for status in verwerkingsrun.STATUSSEN_BESTAND}
    for record in records:
        lijsten[record['status']].setdefault(record['categorie'], []).append(record['pad'])
    for per_categorie in lijsten.values():
        for categorie in per_categorie:
            per_categorie[categorie] = sorted(per_categorie[categorie])
    return lijsten


def telDelta(lijsten):
    """Tel het aantal bestanden per categorie en status, plus een totaal.

    Returns:
        Dict categorie -> status -> aantal, met de extra sleutel 'totaal'
    """
    tellingen = {'totaal': {status: 0 for status in verwerkingsrun.STATUSSEN_BESTAND}}
    for status, per_categorie in lijsten.items():
        for categorie, paden in per_categorie.items():
            tellingen.setdefault(categorie, {s: 0 for s in verwerkingsrun.STATUSSEN_BESTAND})
            tellingen[categorie][status] += len(paden)
            tellingen['totaal'][status] += len(paden)
    return tellingen


def schrijfLijstbestanden(lijsten):
    """Schrijf per MDB-categorie het lijstbestand voor importMDB.sh.

    Het lijstbestand bevat de nieuwe en gewijzigde bestanden, één pad per regel.
    Elk lijstbestand wordt altijd geschreven (leeg als er niets te doen is),
    zodat er nooit een verouderde lijst van een vorige run blijft staan.

    Args:
        lijsten: dict status -> categorie -> paden (uit maakDeltaLijsten)

    Returns:
        Dict categorie -> pad van het lijstbestand
    """
    os.makedirs(str(config.AIRFLOW_TEMPDIR), exist_ok=True)
    resultaat = {}
    for categorie in getMdbCategorieNamen():
        paden = sorted(set(lijsten.get(verwerkingsrun.STATUS_NIEUW, {}).get(categorie, []))
                       | set(lijsten.get(verwerkingsrun.STATUS_GEWIJZIGD, {}).get(categorie, [])))
        pad_lijst = getLijstbestandPad(categorie)
        with open(pad_lijst, 'w', encoding='utf-8') as f:
            for pad in paden:
                f.write(pad + '\n')
        logger.info(f"Lijstbestand {pad_lijst} geschreven met {len(paden)} bestand(en).")
        resultaat[categorie] = pad_lijst
    return resultaat


def begrensLijsten(lijsten):
    """Laat de lijst 'ongewijzigd' weg als de padlijsten het run-document te groot maken.

    Returns:
        Tuple (lijsten, weggelaten): weggelaten is True als 'ongewijzigd' is geleegd
    """
    if len(bson.encode({'lijsten': lijsten})) <= MAX_LIJSTEN_BYTES:
        return lijsten, False
    logger.warning("De padlijsten zijn te groot voor het run-document; de lijst 'ongewijzigd' wordt weggelaten "
                   "(de aantallen staan in tellingen.delta, de details in Verwerkingsrun_Bestanden).")
    lijsten = dict(lijsten)
    lijsten[verwerkingsrun.STATUS_ONGEWIJZIGD] = {}
    return lijsten, True


# ============================================================
# Registratie in PostgreSQL
# ============================================================

def maakRegistratieTabel(cursor):
    """Maak de tabel Def_Bronbestand aan als die nog niet bestaat."""
    cursor.execute(SQL_MAAK_TABEL)


def laadRegistratie(cursor):
    """Lees de volledige registratie uit Def_Bronbestand.

    Returns:
        Dict pad -> {'categorie', 'grootte', 'mtime', 'sha256', 'status'}
    """
    cursor.execute(f'SELECT pad, categorie, grootte, mtime, sha256, status FROM "{TABEL_BRONBESTAND}"')
    return {rij[0]: {'categorie': rij[1], 'grootte': rij[2], 'mtime': rij[3], 'sha256': rij[4], 'status': rij[5]}
            for rij in cursor.fetchall()}


def leesRegistratie():
    """Maak zo nodig de registratietabel aan en lees de registratie."""
    conn = getPgConnection()
    try:
        cursor = conn.cursor()
        maakRegistratieTabel(cursor)
        conn.commit()
        return laadRegistratie(cursor)
    finally:
        conn.close()


def schrijfRegistratie(rijen, bijwerken):
    """Schrijf de registratie weg in PostgreSQL in één transactie.

    Args:
        rijen: tuples (pad, categorie, grootte, mtime, sha256, status, verwerkt_op, run_id, aantal_records) voor de upsert
        bijwerken: tuples (pad, grootte, mtime, sha256) voor ongewijzigde bestanden met een nieuwe grootte/mtime
    """
    conn = getPgConnection()
    try:
        cursor = conn.cursor()
        maakRegistratieTabel(cursor)
        if rijen:
            psycopg2.extras.execute_values(cursor, SQL_UPSERT, rijen, page_size=1000)
        if bijwerken:
            psycopg2.extras.execute_values(cursor, SQL_WERK_VINGERAFDRUK_BIJ, bijwerken,
                                           template='(%s, %s::bigint, %s::double precision, %s)', page_size=1000)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def maakRegistratieRijen(records, aantallen, run_id, tijdstip, alles_verwerkt=False):
    """Zet de records van een run om naar rijen voor Def_Bronbestand.

    Nieuwe en gewijzigde bestanden krijgen status 'verwerkt', verwijderde
    bestanden status 'verwijderd'. Een Access-database die geen enkel
    staging-document opleverde krijgt ook status 'verwerkt' (met
    aantal_records 0) en een waarschuwing in het log, zodat een lege of
    onleesbare database zichtbaar is maar niet bij elke run opnieuw wordt
    verwerkt. De status 'mislukt' wordt hier niet (meer) gezet. Bij een
    ongewijzigd bestand worden alleen grootte en mtime bijgewerkt als die
    veranderd zijn.

    Args:
        records: records uit bepaalStatussen
        aantallen: dict pad -> aantal staging-documenten
        run_id: run die de bestanden verwerkte
        tijdstip: verwerkt_op
        alles_verwerkt: True voor de volledige cyclus: ook ongewijzigde bestanden gelden als verwerkt

    Returns:
        Tuple (rijen voor de upsert, rijen voor het bijwerken van de vingerafdruk)
    """
    mdb_categorieen = getMdbCategorieNamen()
    verwerkt_statussen = [verwerkingsrun.STATUS_NIEUW, verwerkingsrun.STATUS_GEWIJZIGD]
    if alles_verwerkt:
        verwerkt_statussen.append(verwerkingsrun.STATUS_ONGEWIJZIGD)

    rijen = []
    bijwerken = []
    for r in records:
        if r['status'] in verwerkt_statussen:
            aantal = int(aantallen.get(r['pad'], 0))
            if r['categorie'] in mdb_categorieen and aantal == 0:
                logger.warning(f"Access-database {r['pad']} leverde geen staging-documenten op (leeg of onleesbaar); "
                               f"geregistreerd als verwerkt met 0 records.")
            rijen.append((r['pad'], r['categorie'], r['grootte'], r['mtime'], r['sha256'], REG_VERWERKT, tijdstip, run_id, aantal))
        elif r['status'] == verwerkingsrun.STATUS_VERWIJDERD:
            rijen.append((r['pad'], r['categorie'], r['grootte'], r['mtime'], r['sha256'], REG_VERWIJDERD, tijdstip, run_id, 0))
        elif r.get('vingerafdruk_bijgewerkt'):
            bijwerken.append((r['pad'], r['grootte'], r['mtime'], r['sha256']))
    return rijen, bijwerken


def telRegistratie(rijen, bijwerken):
    """Tel de registratierijen per status."""
    tellingen = {REG_VERWERKT: 0, REG_MISLUKT: 0, REG_VERWIJDERD: 0, 'vingerafdruk_bijgewerkt': len(bijwerken)}
    for rij in rijen:
        tellingen[rij[5]] += 1
    return tellingen


# ============================================================
# MongoDB-hulpfuncties
# ============================================================

def _getClient():
    """Maak een MongoClient op basis van de configuratie."""
    return pymongo.MongoClient(str(config.MONGO_URI))


def controleerStagingLeeg(client):
    """Controleer dat staging en Single_Store leeg zijn (voor een run met lege registratie).

    Raises:
        Exception: met een verwijzing naar de volledige cyclus als er al gegevens zijn
    """
    niet_leeg = {}
    stagingdb = client[str(config.DB_STAGING)]
    for naam in stagingdb.list_collection_names():
        if naam in [verwerkingsrun.COLL_VERWERKINGSRUNS, verwerkingsrun.COLL_RUN_BESTANDEN] or naam.startswith('system.'):
            continue
        aantal = stagingdb[naam].estimated_document_count()
        if aantal:
            niet_leeg[naam] = aantal
    aantal = client[str(config.DB_ANALYSE)][config.COLL_ANALYSE].estimated_document_count()
    if aantal:
        niet_leeg[config.COLL_ANALYSE] = aantal

    if niet_leeg:
        msg = (f"De registratie van bronbestanden ({TABEL_BRONBESTAND}) is leeg, maar staging/analyse bevat al "
               f"gegevens: {niet_leeg}. Een incrementele run zou alles dubbel inlezen. Draai eerst de volledige "
               f"cyclus (Extract_Transform_Load_Full_Cycle); die registreert aan het eind alle bronbestanden.")
        logger.error(msg)
        raise Exception(msg)


def bewaarRunBestanden(client, run_id, records):
    """Bewaar de records van een run in de collectie Verwerkingsrun_Bestanden."""
    col = verwerkingsrun.getRunBestandenCollectie(client)
    col.delete_many({'run_id': run_id})
    for i in range(0, len(records), BATCH_GROOTTE):
        col.insert_many([dict(r, run_id=run_id) for r in records[i:i + BATCH_GROOTTE]])


def laadRunBestanden(client, run_id):
    """Lees de records van een run uit de collectie Verwerkingsrun_Bestanden."""
    col = verwerkingsrun.getRunBestandenCollectie(client)
    return list(col.find({'run_id': run_id}, {'_id': 0}))


def telStagingRecords(client, paden=None):
    """Tel het aantal staging-documenten per bronbestand.

    Access-databases en het extra-projectenbestand worden geteld op het veld
    mdbfile; het ABR-bestand is de enige bron van de referentietabellen-collectie.
    Afbeeldingen tellen als 0 (zie ontwerp).

    Args:
        client: MongoClient
        paden: optioneel; beperk de telling tot deze paden

    Returns:
        Dict pad -> aantal
    """
    stagingdb = client[str(config.DB_STAGING)]
    collecties = sorted({coll for _, _, coll in getMdbCategorieen()} | {config.COLL_STAGING_PROJECTENLIJST})
    match = {'mdbfile': {'$in': list(paden)}} if paden is not None else {'mdbfile': {'$exists': True}}

    aantallen = {}
    for coll in collecties:
        for doc in stagingdb[coll].aggregate([{'$match': match}, {'$group': {'_id': '$mdbfile', 'aantal': {'$sum': 1}}}]):
            aantallen[doc['_id']] = aantallen.get(doc['_id'], 0) + doc['aantal']

    if paden is None or config.FILE_ABREXCEL in paden:
        aantallen[config.FILE_ABREXCEL] = stagingdb[config.COLL_STAGING_REFERENTIETABELLEN].count_documents({})
    return aantallen


# ============================================================
# Taken
# ============================================================

def bepaalDelta():
    """Taak Bepaal_Delta: bepaal de status van alle bronbestanden voor de actieve run.

    Schrijft de lijsten per status en categorie in het run-document, de
    vingerafdrukken in Verwerkingsrun_Bestanden en per MDB-categorie een
    lijstbestand in AIRFLOW_TEMPDIR voor importMDB.sh. Is de registratie leeg,
    dan geldt alles als nieuw; de staging moet dan wel leeg zijn.

    Returns:
        Dict met de tellingen per categorie en status
    """
    run = verwerkingsrun.huidigeRun()
    run_id = run['run_id']
    logger.info(f"Bepalen van de delta voor run {run_id}...")

    geregistreerd = leesRegistratie()
    registratie_leeg = len(geregistreerd) == 0

    myclient = _getClient()
    try:
        if registratie_leeg:
            logger.info(f"De registratie ({TABEL_BRONBESTAND}) is leeg: alle bestanden gelden als nieuw.")
            controleerStagingLeeg(myclient)

        overgeslagen = {}
        gescand = scanBronbestanden(overgeslagen)
        records, aantal_hashes = bepaalStatussen(gescand, geregistreerd)
        lijsten = maakDeltaLijsten(records)
        tellingen = telDelta(lijsten)
        schrijfLijstbestanden(lijsten)
        bewaarRunBestanden(myclient, run_id, records)
    finally:
        myclient.close()

    lijsten, ongewijzigd_weggelaten = begrensLijsten(lijsten)
    velden = {status: lijsten[status] for status in verwerkingsrun.STATUSSEN_BESTAND}
    velden.update({
        'registratie_leeg': registratie_leeg,
        'ongewijzigd_weggelaten': ongewijzigd_weggelaten,
        'tellingen.delta': tellingen,
        'tellingen.hash_berekend': aantal_hashes,
    })
    velden.update(maakOvergeslagenVelden(overgeslagen))
    verwerkingsrun.werkRunBij(velden, run_id=run_id)

    logger.info(f"Delta voor run {run_id}: {tellingen['totaal']} (sha256 berekend voor {aantal_hashes} bestanden).")
    for categorie, per_status in sorted(tellingen.items()):
        if categorie != 'totaal':
            logger.info(f"  {categorie}: {per_status}")
    return tellingen


def registreerBronbestanden():
    """Taak Registreer_Run: werk Def_Bronbestand bij na een geslaagde incrementele run.

    Nieuwe en gewijzigde bestanden krijgen status verwerkt (met run_id,
    verwerkt_op en aantal_records), verwijderde bestanden status verwijderd.
    Daarna wordt het run-document op 'afgerond' gezet.

    Returns:
        Dict met de tellingen van de registratie
    """
    run = verwerkingsrun.huidigeRun()
    run_id = run['run_id']
    tijdstip = verwerkingsrun.nu()

    myclient = _getClient()
    try:
        records = laadRunBestanden(myclient, run_id)
        te_tellen = [r['pad'] for r in records if r['status'] in [verwerkingsrun.STATUS_NIEUW, verwerkingsrun.STATUS_GEWIJZIGD]]
        aantallen = telStagingRecords(myclient, paden=te_tellen)
    finally:
        myclient.close()

    rijen, bijwerken = maakRegistratieRijen(records, aantallen, run_id, tijdstip)
    schrijfRegistratie(rijen, bijwerken)
    tellingen = telRegistratie(rijen, bijwerken)

    verwerkingsrun.werkRunBij({'tellingen.registratie': tellingen}, run_id=run_id)
    verwerkingsrun.beeindigRun(verwerkingsrun.STATUS_AFGEROND, run_id=run_id)
    logger.info(f"Registratie van run {run_id} bijgewerkt: {tellingen}.")
    return tellingen


def registreerVolledigeCyclus():
    """Taak Registreer_Bronbestanden: registreer na de volledige cyclus alle bestanden als verwerkt.

    Maakt een run-document van soort 'volledig' aan. Alle gevonden bestanden
    krijgen status verwerkt (een Access-database die niets opleverde met
    aantal_records 0 en een waarschuwing in het log); geregistreerde bestanden die niet meer bestaan krijgen status verwijderd.
    Zonder deze registratie zou de eerste incrementele run na een volledige run
    alles als nieuw zien en de staging dubbel vullen.

    Returns:
        Dict met de tellingen van de registratie
    """
    run_id = verwerkingsrun.startRun(verwerkingsrun.SOORT_VOLLEDIG)
    try:
        geregistreerd = leesRegistratie()
        overgeslagen = {}
        gescand = scanBronbestanden(overgeslagen)
        records, aantal_hashes = bepaalStatussen(gescand, geregistreerd)
        tellingen_delta = telDelta(maakDeltaLijsten(records))

        myclient = _getClient()
        try:
            aantallen = telStagingRecords(myclient)
        finally:
            myclient.close()

        rijen, bijwerken = maakRegistratieRijen(records, aantallen, run_id, verwerkingsrun.nu(), alles_verwerkt=True)
        schrijfRegistratie(rijen, bijwerken)
        tellingen = telRegistratie(rijen, bijwerken)

        velden = {
            'registratie_leeg': len(geregistreerd) == 0,
            'tellingen.delta': tellingen_delta,
            'tellingen.hash_berekend': aantal_hashes,
            'tellingen.registratie': tellingen,
        }
        velden.update(maakOvergeslagenVelden(overgeslagen))
        verwerkingsrun.werkRunBij(velden, run_id=run_id)
        verwerkingsrun.beeindigRun(verwerkingsrun.STATUS_AFGEROND, run_id=run_id)
        logger.info(f"Volledige cyclus: registratie van {len(rijen)} bronbestanden bijgewerkt: {tellingen}.")
        return tellingen

    except Exception as err:
        msg = f"Fout bij het registreren van de bronbestanden na de volledige cyclus: {err}"
        logger.error(msg)
        verwerkingsrun.beeindigRun(verwerkingsrun.STATUS_MISLUKT, run_id=run_id, melding=msg)
        raise Exception(msg) from err
