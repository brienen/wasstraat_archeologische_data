"""Verwerkingsrapport per run (issue 62).

Aan het eind van elke run van de volledige cyclus, de incrementele cyclus en
``DAG_Load_Only`` draait de taak ``Verwerkingsrapport`` (trigger rule
``all_done``, dus ook na een fout). Die bouwt een rapport uit:

- het run-document (``Verwerkingsruns``): status, delta, tellingen per stap en
  de meldingen van het foutbeleid (issue 54);
- de registratie van bronbestanden (``Def_Bronbestand``, rijen van deze run),
  de vingerafdrukken van de run (``Verwerkingsrun_Bestanden``) en de status van
  de afbeeldingen (``Filenames``);
- de staging- en analysecollecties: ``_processing_errors`` (Transform 2),
  locatiefouten, onherkende bestandsnamen en samengevoegde documenten in
  ``Single_Store_Clean``;
- PostgreSQL: aantallen per ``Def_``-tabel, artefacten per soort en rijen
  zonder key;
- de Airflow-metadata: status en doorlooptijd van elke taak van de DagRun.

Het rapport wordt als JSON (machineleesbaar) en als Markdown (leesbaar)
geschreven naar ``AIRFLOW_OUTPUT_RAPPORTEN`` (standaard ``/output/rapporten``;
niet schrijfbaar: ``AIRFLOW_LOGDIR/rapporten``), met een bestandsnaam met
run-id, soort en tijdstip, bijvoorbeeld
``verwerkingsrapport_20261029T101500_volledig_20261029T102312.json``. Een
samenvatting komt in het log van de taak en, met de paden, in het run-document
(veld ``rapport``), zodat de webapplicatie het later kan tonen.

Een sectie die niet opgebouwd kan worden (bijv. PostgreSQL onbereikbaar) komt
in het rapport als niet beschikbaar, met de fout onder ``fouten_in_rapport``;
het rapport zelf wordt dan toch geschreven.
"""
import json
import os
import re
from datetime import datetime

import pymongo

import shared.config as config
import wasstraat.foutbeleid as foutbeleid
import wasstraat.verwerkingsrun as verwerkingsrun
import wasstraat.loadToDatabase_functions as loadToDatabase
import logging

logger = logging.getLogger("airflow.task")

RAPPORT_VERSIE = 1
SECTIES = ['run', 'samenvatting', 'foutbeleid', 'bronbestanden', 'objecttotalen', 'kwaliteitsmeldingen', 'pipeline']

# Begrenzingen: het JSON-rapport noemt hoogstens zoveel bestanden, de Markdown minder
MAX_BESTANDEN = 2000
MAX_BESTANDEN_MARKDOWN = 200
MAX_VOORBEELDEN = 10
MAX_PROCESSING_ERRORS = 100000

CAT_AFBEELDINGEN = 'afbeeldingen'
COLL_PROCESSING_ERRORS = '_processing_errors'
COLL_RUN_BESTANDEN = verwerkingsrun.COLL_RUN_BESTANDEN

# Status van een bronbestand in het rapport
BESTAND_VERWERKT = 'verwerkt'
BESTAND_OVERGESLAGEN = 'overgeslagen'
BESTAND_MISLUKT = 'mislukt'
BESTAND_VERWIJDERD = 'verwijderd'
BESTAND_ONGEWIJZIGD = 'ongewijzigd'
BESTAND_ONVERWERKT = 'onverwerkt'
BESTANDSTATUSSEN = [BESTAND_VERWERKT, BESTAND_OVERGESLAGEN, BESTAND_MISLUKT, BESTAND_ONVERWERKT,
                    BESTAND_VERWIJDERD, BESTAND_ONGEWIJZIGD]

UITKOMST_GESLAAGD = 'geslaagd'
UITKOMST_WAARSCHUWINGEN = 'geslaagd met waarschuwingen'
UITKOMST_MISLUKT = 'mislukt'


# ============================================================
# Verbindingen (te vervangen in unit tests)
# ============================================================

def _getClient():
    """Maak een MongoClient op basis van de configuratie."""
    return pymongo.MongoClient(str(config.MONGO_URI))


def _getPgConnection():
    """Maak een verbinding met PostgreSQL (zoals de laadstap)."""
    return loadToDatabase.getPgConnection()


# ============================================================
# Hulpfuncties
# ============================================================

def _naief(tijdstip):
    """Naïef UTC-tijdstip (of None)."""
    return verwerkingsrun._naiefUtc(tijdstip) if isinstance(tijdstip, datetime) else tijdstip


def _duurSeconden(start, eind):
    """Duur in seconden tussen twee tijdstippen (of None)."""
    start, eind = _naief(start), _naief(eind)
    if isinstance(start, datetime) and isinstance(eind, datetime):
        return round((eind - start).total_seconds(), 1)
    return None


def _jsonWaarde(waarde):
    """Zet waarden die json niet kent om: tijdstippen naar ISO 8601 (UTC), overige naar tekst."""
    if isinstance(waarde, datetime):
        return _naief(waarde).isoformat(timespec='seconds')
    return str(waarde)


def leesVersie():
    """Lees de versie van de Wasstraat, als die in de container beschikbaar is.

    Eerst de omgevingsvariabele WASSTRAAT_VERSION (deploy/docker-compose.yml
    geeft die mee), anders de regel VERSION= uit het bestand in
    WASSTRAAT_VERSIEBESTAND (standaard /opt/airflow/version.env, een kopie van
    config/version.env als die gemount is).

    Returns:
        De versie (tekst), of None als hij niet bekend is
    """
    versie = os.getenv('WASSTRAAT_VERSION')
    if versie and versie.strip():
        return versie.strip()
    pad = os.getenv('WASSTRAAT_VERSIEBESTAND') or '/opt/airflow/version.env'
    try:
        with open(pad, encoding='utf-8') as f:
            for regel in f:
                if regel.strip().startswith('VERSION='):
                    return regel.split('=', 1)[1].strip() or None
    except OSError:
        pass
    return None


def _statusTekst(status):
    """Status van een taakinstantie als tekst (TaskInstanceState is een str-enum)."""
    if status is None:
        return None
    return getattr(status, 'value', status)


# ============================================================
# Verzamelen: Airflow-metadata
# ============================================================

def leesTaken(dag_run, uitsluiten=()):
    """Lees status en doorlooptijd van alle taken van de DagRun.

    Args:
        dag_run: Airflow DagRun (uit de context)
        uitsluiten: task_id's die niet meetellen (het rapport zelf en de eindtaak)

    De scheduler legt per taak start en einde vast. ``airflow dags test``
    (de integratietests) legt alleen het einde vast; daar lopen de taken na
    elkaar, dus wordt de start geschat als het einde van de taak die daarvóór
    eindigde (start_geschat True).

    Returns:
        Lijst met per taak taak, stap, status, start, eind, duur_seconden,
        start_geschat, pogingen en cruciaal, gesorteerd op start
    """
    taken = []
    for ti in dag_run.get_task_instances():
        if ti.task_id in uitsluiten:
            continue
        taken.append({
            'taak': ti.task_id,
            'stap': foutbeleid.bepaalStap(ti.task_id),
            'status': _statusTekst(ti.state),
            'start': _naief(ti.start_date),
            'eind': _naief(ti.end_date),
            'duur_seconden': round(ti.duration, 1) if ti.duration is not None else None,
            'start_geschat': False,
            'pogingen': ti.try_number,
            'cruciaal': foutbeleid.isCrucialeTaak(ti.task_id),
        })
    vorig_eind = None
    for taak in sorted((t for t in taken if t['eind'] is not None), key=lambda t: t['eind']):
        if taak['start'] is None:
            taak['start'] = vorig_eind or taak['eind']
            taak['duur_seconden'] = _duurSeconden(taak['start'], taak['eind'])
            taak['start_geschat'] = True
        vorig_eind = taak['eind']
    return sorted(taken, key=lambda t: (t['start'] is None, t['start'] or datetime.min, t['taak']))


def bepaalStappen(taken):
    """Vat de taken samen per stap van de pipeline (extractie, transform1 ... load, index).

    Args:
        taken: lijst uit leesTaken

    Returns:
        Lijst per stap met start, eind, duur_seconden (van eerste start tot
        laatste eind), som_taakduur_seconden, taken, geslaagd, mislukt,
        niet_uitgevoerd en overgeslagen, gesorteerd op start
    """
    per_stap = {}
    for taak in taken:
        stap = per_stap.setdefault(taak['stap'], {
            'stap': taak['stap'], 'start': None, 'eind': None, 'taken': 0, 'geslaagd': 0, 'mislukt': 0,
            'niet_uitgevoerd': 0, 'overgeslagen': 0, 'som_taakduur_seconden': 0.0})
        stap['taken'] += 1
        status = taak['status']
        if status == 'success':
            stap['geslaagd'] += 1
        elif status == 'failed':
            stap['mislukt'] += 1
        elif status == 'skipped':
            stap['overgeslagen'] += 1
        else:
            stap['niet_uitgevoerd'] += 1
        if taak['start'] and (stap['start'] is None or taak['start'] < stap['start']):
            stap['start'] = taak['start']
        if taak['eind'] and (stap['eind'] is None or taak['eind'] > stap['eind']):
            stap['eind'] = taak['eind']
        stap['som_taakduur_seconden'] = round(stap['som_taakduur_seconden'] + (taak['duur_seconden'] or 0), 1)
    for stap in per_stap.values():
        stap['duur_seconden'] = _duurSeconden(stap['start'], stap['eind'])
    return sorted(per_stap.values(), key=lambda s: (s['start'] is None, s['start'] or datetime.min, s['stap']))


# ============================================================
# Verzamelen: bronbestanden
# ============================================================

def leesRegistratieVanRun(run_id):
    """Lees de rijen van Def_Bronbestand die deze run heeft geregistreerd (leeg als de tabel ontbreekt).

    Returns:
        Lijst met dicts pad, categorie, grootte, status en aantal_records
    """
    conn = _getPgConnection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT to_regclass('public.\"Def_Bronbestand\"') IS NOT NULL")
        rij = cursor.fetchone()
        if not rij or not rij[0]:
            return []
        cursor.execute('SELECT pad, categorie, grootte, status, aantal_records FROM "Def_Bronbestand" '
                       'WHERE run_id = %s ORDER BY categorie, pad', (run_id,))
        return [{'pad': r[0], 'categorie': r[1], 'grootte': r[2], 'status': r[3], 'aantal_records': r[4]}
                for r in cursor.fetchall()]
    finally:
        conn.close()


def leesRunBestanden(run_id):
    """Lees de vingerafdrukken van de bestanden van een (incrementele) run uit Verwerkingsrun_Bestanden."""
    client = _getClient()
    try:
        col = client[str(config.DB_STAGING)][COLL_RUN_BESTANDEN]
        return list(col.find({'run_id': run_id}, {'_id': 0, 'pad': 1, 'categorie': 1, 'status': 1, 'grootte': 1}))
    finally:
        client.close()


def _filterAfbeeldingenVanRun(run):
    """Filter op Filenames voor de afbeeldingen van een run (zoals Controleer_Afbeeldingen telt)."""
    if run and run.get('soort') == verwerkingsrun.SOORT_INCREMENTEEL and run.get('gestart_op'):
        return {'$or': [{'processed': False}, {'verwerkt_op': {'$gte': run['gestart_op']}}]}
    return {}


def leesAfbeeldingProblemen(run):
    """Lees de afbeeldingen en rapporten die mislukt, onverwerkt of overgeslagen zijn.

    Returns:
        Lijst met dicts filename, processed, overgeslagen, fout (hoogstens MAX_BESTANDEN)
    """
    client = _getClient()
    try:
        col = client[str(config.DB_FILES)][config.COLL_FILENAMES]
        problemen = {'$or': [{'processed': False}, {'overgeslagen': {'$exists': True}}]}
        bereik = _filterAfbeeldingenVanRun(run)
        filt = {'$and': [bereik, problemen]} if bereik else problemen
        return list(col.find(filt, {'_id': 0, 'filename': 1, 'processed': 1, 'overgeslagen': 1, 'fout': 1})
                    .limit(MAX_BESTANDEN))
    finally:
        client.close()


def bouwBronbestanden(run, registratie, run_bestanden, afbeeldingen):
    """Bouw de sectie bronbestanden: per bestand status en reden, en totalen per categorie.

    Bronnen, in volgorde van voorrang:

    1. de registratie van deze run (Def_Bronbestand: verwerkt of verwijderd,
       met het aantal records) en, bij een incrementele run, de delta
       (Verwerkingsrun_Bestanden: nieuw, gewijzigd, ongewijzigd, verwijderd);
    2. de controle van de Access-databases (tellingen.extractie): onleesbaar
       (mislukt), leeg en overgeslagen tabellen;
    3. de status van de afbeeldingen in Filenames: mislukt, onverwerkt of
       overgeslagen met reden;
    4. de paden die paden_overslaan (correcties.yml) overslaat
       (paden_overgeslagen in het run-document).

    De lijst noemt alle bestanden behalve ongewijzigde bestanden en verwerkte
    afbeeldingen zonder bijzonderheden, hoogstens MAX_BESTANDEN; de totalen
    tellen alles.

    Args:
        run: run-document (of None)
        registratie: rijen uit leesRegistratieVanRun
        run_bestanden: records uit leesRunBestanden
        afbeeldingen: documenten uit leesAfbeeldingProblemen

    Returns:
        Dict met registratie_uitgevoerd, totalen, delta, bestanden, weggelaten en paden_overgeslagen
    """
    run = run or {}
    bestanden = {}

    def bestand(pad, categorie=None):
        b = bestanden.setdefault(pad, {'bestand': pad, 'categorie': categorie, 'grootte': None, 'status': None,
                                       'wijziging': None, 'records': None, 'reden': None})
        if categorie and not b['categorie']:
            b['categorie'] = categorie
        return b

    for r in run_bestanden or []:
        b = bestand(r['pad'], r.get('categorie'))
        b['wijziging'] = r.get('status')
        b['grootte'] = r.get('grootte')
        if r.get('status') == verwerkingsrun.STATUS_ONGEWIJZIGD:
            b['status'] = BESTAND_ONGEWIJZIGD
    for r in registratie or []:
        b = bestand(r['pad'], r.get('categorie'))
        b['grootte'] = r.get('grootte') if r.get('grootte') is not None else b['grootte']
        b['records'] = r.get('aantal_records')
        b['status'] = BESTAND_VERWIJDERD if r.get('status') == BESTAND_VERWIJDERD else (
            BESTAND_MISLUKT if r.get('status') == BESTAND_MISLUKT else BESTAND_VERWERKT)

    extractie = (run.get('tellingen') or {}).get('extractie') or {}
    for o in extractie.get('onleesbare_databases') or []:
        b = bestand(o['bestand'], o.get('categorie'))
        b['status'] = BESTAND_MISLUKT
        b['reden'] = 'onleesbaar (mdb-tables kan het bestand niet lezen; mogelijk corrupt)'
    for leeg in extractie.get('lege_databases') or []:
        b = bestand(leeg['bestand'], leeg.get('categorie'))
        b['status'] = b['status'] or BESTAND_VERWERKT
        b['records'] = 0
        b['reden'] = 'geen records (leeg, of alle tabellen leeg of overgeslagen)'
    for t in extractie.get('overgeslagen_tabellen') or []:
        b = bestand(t['bestand'], t.get('categorie'))
        b.setdefault('tabellen_overgeslagen', []).append({'tabel': t.get('tabel'), 'reden': t.get('reden')})
        b['status'] = b['status'] or BESTAND_VERWERKT
        if not b['reden']:
            b['reden'] = 'tabel(len) overgeslagen bij de export'

    for a in afbeeldingen or []:
        b = bestand(a['filename'], CAT_AFBEELDINGEN)
        if a.get('processed') is False:
            b['status'] = BESTAND_MISLUKT if a.get('fout') else BESTAND_ONVERWERKT
            b['reden'] = a.get('fout') or 'niet verwerkt (geen foutmelding)'
        elif a.get('overgeslagen'):
            b['status'] = BESTAND_OVERGESLAGEN
            b['reden'] = a['overgeslagen']

    paden_overgeslagen = run.get('paden_overgeslagen') or {}
    for categorie, paden in paden_overgeslagen.items():
        for pad in paden or []:
            b = bestand(pad, categorie)
            b['status'] = BESTAND_OVERGESLAGEN
            b['reden'] = 'paden_overslaan (correcties.yml)'

    # Zonder registratie (de run stopte ervoor) zijn nieuwe en gewijzigde bestanden niet (volledig) verwerkt
    standaard = BESTAND_VERWERKT if registratie else BESTAND_ONVERWERKT
    totalen = {}
    for b in bestanden.values():
        status = b['status'] or (BESTAND_VERWIJDERD if b['wijziging'] == verwerkingsrun.STATUS_VERWIJDERD else standaard)
        b['status'] = status
        per_status = totalen.setdefault(b['categorie'] or 'onbekend', {s: 0 for s in BESTANDSTATUSSEN})
        per_status[status] = per_status.get(status, 0) + 1

    def tonen(b):
        if b['status'] == BESTAND_ONGEWIJZIGD:
            return False
        if b['categorie'] == CAT_AFBEELDINGEN and b['status'] in (BESTAND_VERWERKT, BESTAND_ONVERWERKT) and not b['reden']:
            # Alleen bij een incrementele run: de nieuwe en gewijzigde afbeeldingen
            return b['wijziging'] in (verwerkingsrun.STATUS_NIEUW, verwerkingsrun.STATUS_GEWIJZIGD)
        return True

    volgorde = {BESTAND_MISLUKT: 0, BESTAND_ONVERWERKT: 1, BESTAND_OVERGESLAGEN: 2, BESTAND_VERWIJDERD: 3,
                BESTAND_VERWERKT: 4}
    lijst = sorted((b for b in bestanden.values() if tonen(b)),
                   key=lambda b: (volgorde.get(b['status'], 9), b['categorie'] or '', b['bestand']))
    return {
        'registratie_uitgevoerd': bool(registratie),
        'delta': (run.get('tellingen') or {}).get('delta'),
        'totalen': dict(sorted(totalen.items())),
        'bestanden': lijst[:MAX_BESTANDEN],
        'weggelaten': max(len(lijst) - MAX_BESTANDEN, 0),
        'paden_overgeslagen': (run.get('tellingen') or {}).get('paden_overgeslagen') or {},
    }


# ============================================================
# Verzamelen: objecttotalen
# ============================================================

def leesTabelaantallen(tabellen):
    """Tel de rijen per Def_-tabel in PostgreSQL en de artefacten per artefactsoort.

    Returns:
        Tuple (dict tabel -> aantal of None als de tabel ontbreekt, dict artefactsoort -> aantal)
    """
    conn = _getPgConnection()
    try:
        cursor = conn.cursor()
        aantallen = {}
        for tabel in tabellen:
            cursor.execute("SELECT to_regclass(%s) IS NOT NULL", (f'public."{tabel}"',))
            rij = cursor.fetchone()
            if not rij or not rij[0]:
                aantallen[tabel] = None
                continue
            cursor.execute(f'SELECT COUNT(*) FROM "{tabel}"')
            aantallen[tabel] = int(cursor.fetchone()[0])
        artefactsoorten = {}
        if aantallen.get('Def_Artefact') is not None:
            cursor.execute('SELECT COALESCE(artefactsoort::text, \'(leeg)\'), COUNT(*) FROM "Def_Artefact" '
                           'GROUP BY 1 ORDER BY 1')
            artefactsoorten = {r[0]: int(r[1]) for r in cursor.fetchall()}
        return aantallen, artefactsoorten
    finally:
        conn.close()


def leesSamengevoegd(run):
    """Tel per soort de samengevoegde documenten (brondata_count > 1) in Single_Store_Clean.

    Bij een incrementele run alleen de documenten die deze run (opnieuw) schreef.

    Returns:
        Dict soort -> aantal
    """
    filt = {'brondata_count': {'$gt': 1}}
    if run and run.get('soort') == verwerkingsrun.SOORT_INCREMENTEEL:
        filt['delta_run'] = run['run_id']
    client = _getClient()
    try:
        col = client[str(config.DB_ANALYSE)][config.COLL_ANALYSE_CLEAN]
        return {r['_id']: r['aantal'] for r in col.aggregate([
            {'$match': filt}, {'$group': {'_id': '$soort', 'aantal': {'$sum': 1}}}]) if r['_id']}
    finally:
        client.close()


def bouwObjecttotalen(run, aantallen, artefactsoorten, samengevoegd):
    """Bouw de sectie objecttotalen: per tabel totaal, aangemaakt, bijgewerkt, samengevoegd en verwijderd.

    Incrementeel komen aangemaakt, bijgewerkt en verwijderd uit de upsert
    (tellingen.load: ingevoegd, bijgewerkt, verwijderd); bij de volledige
    cyclus en DAG_Load_Only uit de vergelijking van de oude en de nieuwe
    tabel (ingevoegd en verwijderd; bijgewerkt is daar niet bekend, want
    alles wordt opnieuw geschreven). Samengevoegd is het aantal documenten
    dat uit meer dan één bronrecord is samengevoegd. Totaal is het aantal
    rijen in PostgreSQL na de run.

    Args:
        run: run-document (of None)
        aantallen: dict tabel -> aantal rijen (leesTabelaantallen)
        artefactsoorten: dict artefactsoort -> aantal
        samengevoegd: dict soort -> aantal samengevoegde documenten

    Returns:
        Dict met load_uitgevoerd, tabellen, totaal en artefactsoorten
    """
    tellingen = ((run or {}).get('tellingen') or {})
    load = tellingen.get('load') or {}
    primary_keys = (tellingen.get('transform') or {}).get('primary_keys') or {}
    tabellen = {}
    for tabel, totaal in aantallen.items():
        soort = tabel[4:] if tabel.startswith('Def_') else tabel
        t = load.get(tabel) or {}
        tabellen[tabel] = {
            'totaal': totaal,
            'aangemaakt': t.get('ingevoegd'),
            'bijgewerkt': t.get('bijgewerkt'),
            'samengevoegd': samengevoegd.get(soort, 0),
            'verwijderd': t.get('verwijderd'),
            'nieuwe_sleutels': (primary_keys.get(soort) or {}).get('nieuw'),
        }
    velden = ['totaal', 'aangemaakt', 'bijgewerkt', 'samengevoegd', 'verwijderd']
    totaal = {}
    for veld in velden:
        waarden = [t[veld] for t in tabellen.values() if t[veld] is not None]
        totaal[veld] = sum(waarden) if waarden else None
    return {'load_uitgevoerd': bool(load), 'tabellen': tabellen, 'totaal': totaal,
            'artefactsoorten': artefactsoorten}


# ============================================================
# Verzamelen: kwaliteitsmeldingen
# ============================================================

def leesVerwerkingsfouten(run):
    """Groepeer de records uit _processing_errors van deze run per fase, soort en fouttype.

    Returns:
        Lijst met fase, soort, fouttype, aantal en voorbeelden, aflopend op aantal
    """
    filt = {}
    if run and run.get('gestart_op'):
        filt['timestamp'] = {'$gte': run['gestart_op']}
    client = _getClient()
    try:
        col = client[str(config.DB_ANALYSE)][COLL_PROCESSING_ERRORS]
        groepen = {}
        for doc in col.find(filt, {'fase': 1, 'soort': 1, 'error_type': 1, 'error_msg': 1, 'original_id': 1,
                                   'projectcd': 1}).limit(MAX_PROCESSING_ERRORS):
            sleutel = (doc.get('fase'), doc.get('soort'), doc.get('error_type'))
            groep = groepen.setdefault(sleutel, {'fase': sleutel[0], 'soort': sleutel[1], 'fouttype': sleutel[2],
                                                 'aantal': 0, 'voorbeelden': []})
            groep['aantal'] += 1
            if len(groep['voorbeelden']) < 3:
                groep['voorbeelden'].append({'original_id': str(doc.get('original_id')),
                                             'projectcd': doc.get('projectcd'),
                                             'melding': str(doc.get('error_msg'))[:300]})
        return sorted(groepen.values(), key=lambda g: (-g['aantal'], str(g['fase']), str(g['soort'])))
    finally:
        client.close()


def leesAnalyseKwaliteit(run):
    """Lees locatiefouten en onherkende bestandsnamen uit Single_Store_Clean.

    Locatiefouten zijn documenten met een veld error (archutils.logError:
    coördinaten buiten Nederland of onleesbaar); onherkende bestandsnamen zijn
    bestanden die parseFotobestanden niet als foto, tekening of rapport
    herkende (soort Bestand, fototype N). Bij een incrementele run alleen de
    documenten van deze run.

    Returns:
        Dict met locatiefouten (lijst soort, type, aantal, voorbeelden) en
        onherkende_bestandsnamen (aantal, voorbeelden)
    """
    basis = {}
    if run and run.get('soort') == verwerkingsrun.SOORT_INCREMENTEEL:
        basis['delta_run'] = run['run_id']
    client = _getClient()
    try:
        col = client[str(config.DB_ANALYSE)][config.COLL_ANALYSE_CLEAN]
        groepen = {}
        for doc in col.find(dict(basis, error={'$exists': True}), {'soort': 1, 'error': 1, 'projectcd': 1}):
            fout = ((doc.get('error') or {}).get('Error') or {})
            sleutel = (doc.get('soort'), fout.get('Type'))
            groep = groepen.setdefault(sleutel, {'soort': sleutel[0], 'type': sleutel[1], 'aantal': 0,
                                                 'voorbeelden': []})
            groep['aantal'] += 1
            if len(groep['voorbeelden']) < 3:
                groep['voorbeelden'].append({'projectcd': doc.get('projectcd'), 'melding': fout.get('Message')})
        onherkend_filter = dict(basis, soort='Bestand', fototype='N')
        onherkend = {
            'aantal': col.count_documents(onherkend_filter),
            'voorbeelden': [d.get('fullFileName') or d.get('fileName')
                            for d in col.find(onherkend_filter, {'fullFileName': 1, 'fileName': 1}).limit(MAX_VOORBEELDEN)],
        }
        return {'locatiefouten': sorted(groepen.values(), key=lambda g: (-g['aantal'], str(g['soort']))),
                'onherkende_bestandsnamen': onherkend}
    finally:
        client.close()


def leesRijenZonderKey(tabellen):
    """Tel per Def_-tabel met een kolom key de rijen zonder key in PostgreSQL.

    Returns:
        Dict tabel -> aantal (alleen tabellen met een kolom key en minstens één zo'n rij)
    """
    conn = _getPgConnection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT table_name FROM information_schema.columns WHERE table_schema = 'public' "
                       "AND column_name = 'key'")
        met_key = {r[0] for r in cursor.fetchall()}
        resultaat = {}
        for tabel in tabellen:
            if tabel not in met_key:
                continue
            cursor.execute(f'SELECT COUNT(*) FROM "{tabel}" WHERE key IS NULL OR key = \'\'')
            aantal = int(cursor.fetchone()[0])
            if aantal:
                resultaat[tabel] = aantal
        return resultaat
    finally:
        conn.close()


def bouwKwaliteit(run, verwerkingsfouten, analyse, rijen_zonder_key):
    """Bouw de sectie kwaliteitsmeldingen uit de verzamelde gegevens en de tellingen in het run-document.

    Args:
        run: run-document (of None)
        verwerkingsfouten: lijst uit leesVerwerkingsfouten
        analyse: dict uit leesAnalyseKwaliteit (of None)
        rijen_zonder_key: dict uit leesRijenZonderKey (of None als er geen load was)

    Returns:
        Dict met per onderwerp de gegevens (leeg/None als er niets te melden is)
    """
    tellingen = ((run or {}).get('tellingen') or {})
    load = tellingen.get('load') or {}
    transform = tellingen.get('transform') or {}
    primary_keys = transform.get('primary_keys') or {}
    hernummerd = {t: v.get('hernummerd') for t, v in load.items()
                  if isinstance(v, dict) and v.get('hernummerd')}
    nieuw_verdwenen = {s: {'nieuw': v.get('nieuw', 0), 'verdwenen': v.get('verdwenen', 0)}
                       for s, v in primary_keys.items() if isinstance(v, dict) and (v.get('nieuw') or v.get('verdwenen'))}
    meldingen = (run or {}).get('meldingen') or []
    afgeleid_mislukt = [m['melding'] for m in meldingen if m.get('soort') == foutbeleid.SOORT_AFGELEIDE_VELDEN]
    extractie = tellingen.get('extractie')
    # Transform 1 (issue 89): tabellen die meer dan één harmonisatie-pipeline selecteert, per melder
    voorrang = sorted((besluit for besluiten in (transform.get('harmonisatie_voorrang') or {}).values()
                       if isinstance(besluiten, list) for besluit in besluiten if isinstance(besluit, dict)),
                      key=lambda b: (str(b.get('collectie')), str(b.get('tabel'))))
    return {
        'verwerkingsfouten': {'totaal': sum(g['aantal'] for g in verwerkingsfouten or []),
                              'groepen': verwerkingsfouten or [],
                              'drempel': tellingen.get('verwerkingsfouten')},
        'afbeeldingen': tellingen.get('afbeeldingen'),
        'databases': {k: extractie.get(k) for k in ('databases', 'onleesbaar', 'leeg', 'tabellen_overgeslagen',
                                                    'onleesbare_databases', 'lege_databases', 'overgeslagen_tabellen',
                                                    'overige_meldingen', 'drempel')} if extractie else None,
        'paden_overgeslagen': tellingen.get('paden_overgeslagen'),
        'harmonisatie_voorrang': voorrang,
        'locatiefouten': (analyse or {}).get('locatiefouten') or [],
        'onherkende_bestandsnamen': (analyse or {}).get('onherkende_bestandsnamen'),
        'rijen_zonder_key': rijen_zonder_key,
        'fk': {'niet_hersteld': load.get('fk_niet_hersteld'), 'niet_hersteld_namen': load.get('fk_niet_hersteld_namen'),
               'niet_gevalideerd': load.get('fk_niet_gevalideerd')} if load else None,
        'gebruikersdata': tellingen.get('gebruikersdata'),
        'sleutels': {'hernummerd': hernummerd, 'nieuw_en_verdwenen': nieuw_verdwenen},
        'afgeleide_velden': {'mislukt': bool(afgeleid_mislukt), 'melding': afgeleid_mislukt[0] if afgeleid_mislukt else None,
                             'tellingen': tellingen.get('afgeleide_velden')},
    }


# ============================================================
# Foutbeleid en samenvatting
# ============================================================

def bepaalFoutbeleid(run, taken):
    """Bepaal de uitkomst van het foutbeleid: welke fout de run stopte en welke waarschuwingen er waren.

    Bronnen: de meldingen in het run-document (foutbeleid.meld en de
    on_failure_callback) en de status van de taken in Airflow. Een mislukte
    taak zonder melding (bijv. als het run-document niet bereikbaar was) komt
    er met een algemene melding bij.

    Args:
        run: run-document (of None)
        taken: lijst uit leesTaken

    Returns:
        Dict met uitkomst, gestopt_door, fouten, waarschuwingen, mislukte_taken en drempels
    """
    meldingen = list((run or {}).get('meldingen') or [])
    mislukte_taken = [t for t in taken if t['status'] == 'failed']
    for taak in mislukte_taken:
        if not any(m.get('taak') == taak['taak'] for m in meldingen):
            meldingen.append({
                'niveau': foutbeleid.NIVEAU_FOUT if taak['cruciaal'] else foutbeleid.NIVEAU_WAARSCHUWING,
                'stap': taak['stap'], 'taak': taak['taak'], 'soort': foutbeleid.SOORT_TAAK_MISLUKT,
                'melding': 'Taak mislukt; de foutmelding staat in het log van de taak.', 'aantal': None,
                'details': None, 'tijdstip': taak['eind']})
    fouten = [m for m in meldingen if m.get('niveau') == foutbeleid.NIVEAU_FOUT]
    waarschuwingen = [m for m in meldingen if m.get('niveau') == foutbeleid.NIVEAU_WAARSCHUWING]

    gestopt_door = None
    cruciaal = sorted((t for t in mislukte_taken if t['cruciaal']),
                      key=lambda t: (t['eind'] is None, t['eind'] or datetime.min))
    if cruciaal:
        eerste = cruciaal[0]
        melding = next((m['melding'] for m in fouten if m.get('taak') == eerste['taak']), None)
        gestopt_door = {'taak': eerste['taak'], 'stap': eerste['stap'], 'melding': melding}
    elif run and run.get('status') == verwerkingsrun.STATUS_MISLUKT:
        gestopt_door = {'taak': None, 'stap': None, 'melding': run.get('melding')}

    if gestopt_door is not None or (run is None and mislukte_taken):
        uitkomst = UITKOMST_MISLUKT
    elif waarschuwingen:
        uitkomst = UITKOMST_WAARSCHUWINGEN
    else:
        uitkomst = UITKOMST_GESLAAGD

    tellingen = ((run or {}).get('tellingen') or {})
    afbeeldingen = tellingen.get('afbeeldingen') or {}
    drempels = {
        'afbeeldingen': {'max_aantal': afbeeldingen.get('max_aantal'), 'max_pct': afbeeldingen.get('max_pct'),
                         'drempel': afbeeldingen.get('drempel')},
        'databases': {'max_aantal': config.AIRFLOW_MAX_MISLUKTE_DATABASES,
                      'max_pct': config.AIRFLOW_MAX_MISLUKTE_DATABASES_PCT,
                      'drempel': (tellingen.get('extractie') or {}).get('drempel')},
        'verwerkingsfouten': {'max_aantal': config.AIRFLOW_MAX_VERWERKINGSFOUTEN,
                              'max_pct': config.AIRFLOW_MAX_VERWERKINGSFOUTEN_PCT},
    }
    return {
        'uitkomst': uitkomst,
        'gestopt_door': gestopt_door,
        'fouten': fouten,
        'waarschuwingen': waarschuwingen,
        'mislukte_taken': [{'taak': t['taak'], 'stap': t['stap'], 'cruciaal': t['cruciaal']} for t in mislukte_taken],
        'niet_uitgevoerd': len([t for t in taken if t['status'] == 'upstream_failed']),
        'drempels': drempels,
    }


def bouwMeta(run, dag_run, taken, gemaakt_op):
    """Bouw de sectie run: gegevens van de run, de Airflow-run, het profiel en de versie."""
    run = run or {}
    gestart = run.get('gestart_op') or (verwerkingsrun.startVanAirflowRun(dag_run) if dag_run is not None else None)
    beeindigd = run.get('beeindigd_op') or max((t['eind'] for t in taken if t['eind']), default=None) or gemaakt_op
    meta = {
        'run_id': run.get('run_id'),
        'soort': run.get('soort'),
        'status': run.get('status'),
        'melding': run.get('melding'),
        'dag_id': run.get('dag_id') or getattr(dag_run, 'dag_id', None),
        'airflow_run_id': run.get('airflow_run_id') or getattr(dag_run, 'run_id', None),
        'gestart_op': gestart,
        'beeindigd_op': beeindigd,
        'duur_seconden': _duurSeconden(gestart, beeindigd),
        'profiel': getattr(config, 'WASSTRAAT_GEMEENTE', None) or 'delft',
    }
    versie = leesVersie()
    if versie:
        meta['versie'] = versie
    return meta


def bouwPipeline(dag_run, taken):
    """Bouw de sectie pipeline: start, eind en duur van de Airflow-run, per stap en per taak."""
    start = min((t['start'] for t in taken if t['start']), default=None) or _naief(getattr(dag_run, 'start_date', None))
    eind = max((t['eind'] for t in taken if t['eind']), default=None)
    return {'start': start, 'eind': eind, 'duur_seconden': _duurSeconden(start, eind),
            'stappen': bepaalStappen(taken), 'taken': taken}


def maakSamenvatting(rapport):
    """Compacte samenvatting voor het log en het run-document."""
    fb = rapport.get('foutbeleid') or {}
    bron = rapport.get('bronbestanden') or {}
    obj = rapport.get('objecttotalen') or {}
    kw = rapport.get('kwaliteitsmeldingen') or {}
    per_status = {}
    for telling in (bron.get('totalen') or {}).values():
        for status, aantal in telling.items():
            per_status[status] = per_status.get(status, 0) + aantal
    afbeeldingen = kw.get('afbeeldingen') or {}
    databases = kw.get('databases') or {}
    return {
        'uitkomst': fb.get('uitkomst'),
        'status': (rapport.get('run') or {}).get('status'),
        'duur_seconden': (rapport.get('run') or {}).get('duur_seconden'),
        'fouten': len(fb.get('fouten') or []),
        'waarschuwingen': len(fb.get('waarschuwingen') or []),
        'gestopt_door': (fb.get('gestopt_door') or {}).get('taak') if fb.get('gestopt_door') else None,
        'bronbestanden': {s: n for s, n in per_status.items() if n},
        'objecten': obj.get('totaal'),
        'verwerkingsfouten': (kw.get('verwerkingsfouten') or {}).get('totaal'),
        'afbeeldingen_mislukt': (afbeeldingen.get('mislukt') or 0) + (afbeeldingen.get('onverwerkt') or 0) if afbeeldingen else None,
        'databases_onleesbaar': databases.get('onleesbaar'),
        'secties_niet_beschikbaar': [f['sectie'] for f in rapport.get('fouten_in_rapport') or []],
    }


# ============================================================
# Opbouw van het hele rapport
# ============================================================

def verzamelRapport(run, taken, dag_run=None, gemaakt_op=None):
    """Verzamel alle gegevens en bouw het rapport; een sectie die faalt wordt als niet beschikbaar gemeld.

    Args:
        run: run-document (of None als de run niet gestart is)
        taken: lijst uit leesTaken
        dag_run: Airflow DagRun (optioneel)
        gemaakt_op: tijdstip van het rapport (standaard nu)

    Returns:
        Het rapport (dict) met de secties uit SECTIES en fouten_in_rapport
    """
    gemaakt_op = gemaakt_op or verwerkingsrun.nu()
    fouten = []

    def probeer(sectie, functie, standaard=None):
        try:
            return functie()
        except Exception as err:
            logger.warning(f"Verwerkingsrapport: sectie {sectie} niet volledig: {err}")
            fouten.append({'sectie': sectie, 'fout': f"{type(err).__name__}: {err}"[:500]})
            return standaard

    soort = (run or {}).get('soort')
    load_uitgevoerd = 'load' in (((run or {}).get('tellingen')) or {})
    tabellen = [t for t in loadToDatabase.LOAD_TABELLEN]

    met_bronbestanden = soort in (verwerkingsrun.SOORT_VOLLEDIG, verwerkingsrun.SOORT_INCREMENTEEL)
    registratie = probeer('bronbestanden', lambda: leesRegistratieVanRun(run['run_id']), []) if met_bronbestanden else []
    run_bestanden = probeer('bronbestanden', lambda: leesRunBestanden(run['run_id']), []) \
        if run and soort == verwerkingsrun.SOORT_INCREMENTEEL else []
    afbeeldingen = probeer('bronbestanden', lambda: leesAfbeeldingProblemen(run), []) \
        if soort in (verwerkingsrun.SOORT_VOLLEDIG, verwerkingsrun.SOORT_INCREMENTEEL) else []
    bronbestanden = probeer('bronbestanden', lambda: bouwBronbestanden(run, registratie, run_bestanden, afbeeldingen),
                            {'registratie_uitgevoerd': False, 'totalen': {}, 'bestanden': [], 'weggelaten': 0})
    bronbestanden['van_toepassing'] = met_bronbestanden

    aantallen, artefactsoorten = probeer('objecttotalen', lambda: leesTabelaantallen(tabellen), ({}, {}))
    samengevoegd = probeer('objecttotalen', lambda: leesSamengevoegd(run), {}) if soort != verwerkingsrun.SOORT_LADEN else {}
    objecttotalen = probeer('objecttotalen', lambda: bouwObjecttotalen(run, aantallen, artefactsoorten, samengevoegd),
                            {'load_uitgevoerd': load_uitgevoerd, 'tabellen': {}, 'totaal': {}})

    verwerkingsfouten = probeer('kwaliteitsmeldingen', lambda: leesVerwerkingsfouten(run), []) \
        if soort != verwerkingsrun.SOORT_LADEN else []
    analyse = probeer('kwaliteitsmeldingen', lambda: leesAnalyseKwaliteit(run), None) \
        if soort != verwerkingsrun.SOORT_LADEN else None
    zonder_key = probeer('kwaliteitsmeldingen', lambda: leesRijenZonderKey(tabellen), None) if load_uitgevoerd else None
    kwaliteit = probeer('kwaliteitsmeldingen', lambda: bouwKwaliteit(run, verwerkingsfouten, analyse, zonder_key), {})

    rapport = {
        'rapport_versie': RAPPORT_VERSIE,
        'gemaakt_op': gemaakt_op,
        'run': probeer('run', lambda: bouwMeta(run, dag_run, taken, gemaakt_op), {}),
        'foutbeleid': probeer('foutbeleid', lambda: bepaalFoutbeleid(run, taken), {}),
        'bronbestanden': bronbestanden,
        'objecttotalen': objecttotalen,
        'kwaliteitsmeldingen': kwaliteit,
        'pipeline': probeer('pipeline', lambda: bouwPipeline(dag_run, taken), {}),
    }
    rapport['fouten_in_rapport'] = fouten
    rapport['samenvatting'] = maakSamenvatting(rapport)
    return rapport


# ============================================================
# Markdown
# ============================================================

def _cel(waarde):
    """Tekst voor een cel in een Markdown-tabel (| en regeleinden onschadelijk gemaakt)."""
    if waarde is None or waarde == '':
        return '–'
    if isinstance(waarde, datetime):
        return _tijd(waarde)
    if isinstance(waarde, bool):
        return 'ja' if waarde else 'nee'
    if isinstance(waarde, float):
        return f"{waarde:g}".replace('.', ',')
    return str(waarde).replace('|', '\\|').replace('\r', ' ').replace('\n', ' ')


def _tijd(tijdstip):
    """Tijdstip als tekst in UTC."""
    if not isinstance(tijdstip, datetime):
        return _cel(tijdstip)
    return _naief(tijdstip).strftime('%Y-%m-%d %H:%M:%S') + ' UTC'


def _duur(seconden):
    """Duur leesbaar: 12,3 s, 8 min 12 s of 1 u 05 min."""
    if seconden is None:
        return '–'
    if seconden < 60:
        return f"{seconden:.1f} s".replace('.', ',')
    minuten, sec = divmod(int(round(seconden)), 60)
    if minuten < 60:
        return f"{minuten} min {sec} s"
    uren, minuten = divmod(minuten, 60)
    return f"{uren} u {minuten:02d} min"


def _tabel(koppen, rijen):
    """Markdown-tabel; zonder rijen 'Geen.'."""
    if not rijen:
        return ['Geen.', '']
    regels = ['| ' + ' | '.join(koppen) + ' |', '|' + '|'.join('---' for _ in koppen) + '|']
    regels += ['| ' + ' | '.join(_cel(w) for w in rij) + ' |' for rij in rijen]
    return regels + ['']


def _meldingenTabel(meldingen):
    return _tabel(['Stap', 'Taak', 'Soort', 'Aantal', 'Melding'],
                  [[m.get('stap'), m.get('taak'), m.get('soort'), m.get('aantal'), m.get('melding')] for m in meldingen])


def maakMarkdown(rapport):
    """Zet het rapport om naar Markdown met vaste koppen (ook als een sectie leeg is).

    Koppen: Verwerkingsrapport, Foutbeleid, Bronbestanden, Objecttotalen,
    Kwaliteitsmeldingen en Pipeline, met subkoppen per onderwerp.

    Args:
        rapport: dict uit verzamelRapport

    Returns:
        De Markdown-tekst
    """
    meta = rapport.get('run') or {}
    fb = rapport.get('foutbeleid') or {}
    bron = rapport.get('bronbestanden') or {}
    obj = rapport.get('objecttotalen') or {}
    kw = rapport.get('kwaliteitsmeldingen') or {}
    pipe = rapport.get('pipeline') or {}
    uit = []

    uit += [f"# Verwerkingsrapport {meta.get('run_id') or '(geen run-document)'}", '']
    uitkomst = fb.get('uitkomst') or 'onbekend'
    uit += [f"Uitkomst: **{uitkomst}** ({len(fb.get('fouten') or [])} fout(en), "
            f"{len(fb.get('waarschuwingen') or [])} waarschuwing(en)).", '']
    gegevens = [['Soort run', meta.get('soort')], ['Status', meta.get('status')],
                ['DAG', meta.get('dag_id')], ['Airflow-run', meta.get('airflow_run_id')],
                ['Gestart', _tijd(meta.get('gestart_op'))], ['Beëindigd', _tijd(meta.get('beeindigd_op'))],
                ['Doorlooptijd', _duur(meta.get('duur_seconden'))], ['Profiel', meta.get('profiel')]]
    if meta.get('versie'):
        gegevens.append(['Versie', meta.get('versie')])
    if meta.get('melding'):
        gegevens.append(['Melding', meta.get('melding')])
    gegevens.append(['Rapport gemaakt', _tijd(rapport.get('gemaakt_op'))])
    uit += _tabel(['Gegeven', 'Waarde'], gegevens)
    if rapport.get('fouten_in_rapport'):
        uit += ['Niet alle gegevens konden worden verzameld:', '']
        uit += [f"- {f['sectie']}: {_cel(f['fout'])}" for f in rapport['fouten_in_rapport']] + ['']

    # Foutbeleid
    uit += ['## Foutbeleid', '']
    gestopt = fb.get('gestopt_door')
    if gestopt:
        taak = f"taak `{gestopt['taak']}` (stap {gestopt.get('stap')})" if gestopt.get('taak') else 'een taak'
        uit += [f"De run is gestopt door {taak}: {_cel(gestopt.get('melding'))}", '']
    else:
        uit += ['Geen fout heeft de run gestopt.', '']
    uit += ['### Fouten', ''] + _meldingenTabel(fb.get('fouten') or [])
    uit += ['### Waarschuwingen', ''] + _meldingenTabel(fb.get('waarschuwingen') or [])
    uit += ['### Mislukte taken', '']
    uit += _tabel(['Taak', 'Stap', 'Cruciaal'], [[t['taak'], t['stap'], t['cruciaal']] for t in fb.get('mislukte_taken') or []])

    # Bronbestanden
    uit += ['## Bronbestanden', '']
    if bron.get('van_toepassing') is False:
        uit += ['Deze run verwerkt geen bronbestanden (alleen laden uit Single_Store_Clean).', '']
    elif not bron.get('registratie_uitgevoerd'):
        uit += ['De registratie van de bronbestanden is in deze run niet (volledig) uitgevoerd; de gegevens hieronder '
                'kunnen onvolledig zijn.', '']
    uit += ['### Totalen per categorie', '']
    statussen = [s for s in BESTANDSTATUSSEN if any((t or {}).get(s) for t in (bron.get('totalen') or {}).values())]
    uit += _tabel(['Categorie'] + statussen,
                  [[categorie] + [telling.get(s, 0) for s in statussen] for categorie, telling in (bron.get('totalen') or {}).items()]
                  if statussen else [])
    uit += ['### Bestanden', '']
    bestanden = bron.get('bestanden') or []
    uit += _tabel(['Bestand', 'Categorie', 'Grootte', 'Status', 'Records', 'Reden'],
                  [[b['bestand'], b['categorie'], b.get('grootte'), b['status'], b.get('records'),
                    b.get('reden') if not b.get('tabellen_overgeslagen') else
                    f"{b.get('reden')}: " + ', '.join(f"{t['tabel']} ({t['reden']})" for t in b['tabellen_overgeslagen'])]
                   for b in bestanden[:MAX_BESTANDEN_MARKDOWN]])
    weggelaten = max(len(bestanden) - MAX_BESTANDEN_MARKDOWN, 0) + (bron.get('weggelaten') or 0)
    if weggelaten:
        uit += [f"En nog {weggelaten} bestand(en); zie het JSON-rapport.", '']

    # Objecttotalen
    uit += ['## Objecttotalen', '']
    if not obj.get('load_uitgevoerd'):
        uit += ['Deze run heeft PostgreSQL niet bijgewerkt; de totalen zijn de huidige inhoud.', '']
    rijen = [[tabel, t.get('totaal'), t.get('aangemaakt'), t.get('bijgewerkt'), t.get('samengevoegd'), t.get('verwijderd')]
             for tabel, t in (obj.get('tabellen') or {}).items()]
    totaal = obj.get('totaal') or {}
    if rijen:
        rijen.append(['**Totaal**', totaal.get('totaal'), totaal.get('aangemaakt'), totaal.get('bijgewerkt'),
                      totaal.get('samengevoegd'), totaal.get('verwijderd')])
    uit += _tabel(['Tabel', 'Totaal', 'Aangemaakt', 'Bijgewerkt', 'Samengevoegd', 'Verwijderd'], rijen)
    uit += ['### Artefacten per soort', '']
    uit += _tabel(['Artefactsoort', 'Aantal'], [[s, n] for s, n in (obj.get('artefactsoorten') or {}).items()])

    # Kwaliteitsmeldingen
    uit += ['## Kwaliteitsmeldingen', '']
    vf = kw.get('verwerkingsfouten') or {}
    uit += ['### Verwerkingsfouten (Transform 2)', '']
    uit += _tabel(['Fase', 'Soort', 'Fouttype', 'Aantal', 'Voorbeeld'],
                  [[g['fase'], g['soort'], g['fouttype'], g['aantal'],
                    (g['voorbeelden'][0]['melding'] if g.get('voorbeelden') else None)] for g in vf.get('groepen') or []])
    uit += ['### Afbeeldingen en rapporten', '']
    afb = kw.get('afbeeldingen')
    if afb:
        redenen = ', '.join(f"{n} {r}" for r, n in (afb.get('overgeslagen_per_reden') or {}).items())
        uit += [f"{afb.get('totaal', 0)} bestanden: {afb.get('verwerkt', 0)} verwerkt, {afb.get('overgeslagen', 0)} "
                f"overgeslagen{f' ({redenen})' if redenen else ''}, {afb.get('mislukt', 0)} mislukt, "
                f"{afb.get('onverwerkt', 0)} onverwerkt (drempel {afb.get('drempel')}).", '']
        if afb.get('voorbeelden'):
            uit += _tabel(['Bestand', 'Fout'], [[v.get('filename'), v.get('fout')] for v in afb['voorbeelden']])
    else:
        uit += ['Geen afbeeldingen gecontroleerd in deze run.', '']
    uit += ['### Access-databases', '']
    db = kw.get('databases')
    if db:
        uit += [f"{db.get('databases', 0)} databases verwerkt: {db.get('onleesbaar', 0)} onleesbaar, {db.get('leeg', 0)} "
                f"zonder records, {db.get('tabellen_overgeslagen', 0)} tabel(len) overgeslagen "
                f"(drempel onleesbaar {db.get('drempel')}).", '']
        problemen = ([[o['bestand'], 'onleesbaar'] for o in db.get('onleesbare_databases') or []]
                     + [[l['bestand'], 'geen records'] for l in db.get('lege_databases') or []]
                     + [[t['bestand'], f"tabel {t['tabel']}: {t['reden']}"] for t in db.get('overgeslagen_tabellen') or []])
        if problemen:
            uit += _tabel(['Bestand', 'Probleem'], problemen)
    else:
        uit += ['Geen Access-databases gecontroleerd in deze run.', '']
    uit += ['### Overgeslagen paden (paden_overslaan)', '']
    uit += _tabel(['Categorie', 'Aantal'], [[c, n] for c, n in (kw.get('paden_overgeslagen') or {}).items()])
    uit += ['### Harmonisatie: tabellen bij meer dan één soort', '']
    uit += _tabel(['Tabel', 'Collectie', 'Kandidaten', 'Geharmoniseerd door', 'Keuze'],
                  [[b.get('tabel'), b.get('collectie'), ', '.join(b.get('kandidaten') or []),
                    b.get('gekozen') if b.get('gekozen') is not None else 'geen enkele soort',
                    'correcties.yml' if b.get('bron') == 'correcties.yml' else
                    (f"voorrangsregel; instelling {b['ongeldige_instelling']} genegeerd"
                     if b.get('ongeldige_instelling') is not None else 'voorrangsregel (waarschuwing)')]
                   for b in kw.get('harmonisatie_voorrang') or []])
    uit += ['### Locatiefouten', '']
    uit += _tabel(['Soort', 'Type', 'Aantal', 'Voorbeeld'],
                  [[g['soort'], g['type'], g['aantal'], (g['voorbeelden'][0]['melding'] if g.get('voorbeelden') else None)]
                   for g in kw.get('locatiefouten') or []])
    uit += ['### Onherkende bestandsnamen', '']
    onherkend = kw.get('onherkende_bestandsnamen') or {}
    if onherkend.get('aantal'):
        uit += [f"{onherkend['aantal']} bestand(en) niet herkend als foto, tekening of rapport (soort Bestand), "
                f"bijvoorbeeld: " + ', '.join(_cel(v) for v in onherkend.get('voorbeelden') or []) + '.', '']
    else:
        uit += ['Geen.', '']
    uit += ['### Rijen zonder key', '']
    uit += _tabel(['Tabel', 'Rijen zonder key'], [[t, n] for t, n in (kw.get('rijen_zonder_key') or {}).items()])
    uit += ['### Verwijzingen (FK)', '']
    fk = kw.get('fk') or {}
    fk_rijen = []
    if fk.get('niet_hersteld'):
        fk_rijen.append(['niet hersteld', fk.get('niet_hersteld'), ', '.join(fk.get('niet_hersteld_namen') or [])])
    if fk.get('niet_gevalideerd'):
        fk_rijen.append(['niet gevalideerd', len(fk['niet_gevalideerd']), ', '.join(fk['niet_gevalideerd'])])
    uit += _tabel(['Probleem', 'Aantal', 'Constraints'], fk_rijen)
    uit += ['### Gebruikersdata', '']
    gd_rijen = []
    for tabel, kolommen in (kw.get('gebruikersdata') or {}).items():
        for kolom, telling in (kolommen or {}).items():
            if isinstance(telling, dict) and any(telling.values()):
                gd_rijen.append([tabel, kolom, ', '.join(f"{k} {v}" for k, v in telling.items())])
    uit += _tabel(['Tabel', 'Kolom', 'Tellingen'], gd_rijen)
    uit += ['### Sleutels', '']
    sleutels = kw.get('sleutels') or {}
    sl_rijen = [[t, 'hernummerd (sleutels niet stabiel)', n] for t, n in (sleutels.get('hernummerd') or {}).items()]
    sl_rijen += [[s, 'nieuwe / verdwenen primary_keys', f"{v['nieuw']} / {v['verdwenen']}"]
                 for s, v in (sleutels.get('nieuw_en_verdwenen') or {}).items()]
    uit += _tabel(['Tabel of soort', 'Wat', 'Aantal'], sl_rijen)
    uit += ['### Afgeleide velden', '']
    afgeleid = kw.get('afgeleide_velden') or {}
    if afgeleid.get('mislukt'):
        uit += [f"Niet herberekend: {_cel(afgeleid.get('melding'))}", '']
    else:
        uit += _tabel(['Tabel', 'Rijen met een nieuwe waarde'],
                      [[t, (v or {}).get('rijen')] for t, v in (afgeleid.get('tellingen') or {}).items()])

    # Pipeline
    uit += ['## Pipeline', '']
    uit += [f"Airflow-run van {_tijd(pipe.get('start'))} tot {_tijd(pipe.get('eind'))} ({_duur(pipe.get('duur_seconden'))}).", '']
    uit += ['### Doorlooptijd per stap', '']
    uit += _tabel(['Stap', 'Start', 'Eind', 'Duur', 'Taken', 'Mislukt', 'Niet uitgevoerd'],
                  [[s['stap'], _tijd(s['start']), _tijd(s['eind']), _duur(s['duur_seconden']), s['taken'],
                    s['mislukt'], s['niet_uitgevoerd']] for s in pipe.get('stappen') or []])
    uit += ['### Langste taken', '']
    langste = sorted((t for t in pipe.get('taken') or [] if t.get('duur_seconden') is not None),
                     key=lambda t: -t['duur_seconden'])[:10]
    uit += _tabel(['Taak', 'Duur', 'Status'], [[t['taak'], _duur(t['duur_seconden']), t['status']] for t in langste])
    return '\n'.join(uit).rstrip() + '\n'


# ============================================================
# Schrijven
# ============================================================

def bepaalRapportmap():
    """Bepaal de map voor de rapporten: AIRFLOW_OUTPUT_RAPPORTEN, of AIRFLOW_LOGDIR/rapporten als die niet schrijfbaar is.

    Returns:
        Tuple (map, terugval): terugval is True als de reservemap wordt gebruikt

    Raises:
        OSError: als geen van beide mappen schrijfbaar is
    """
    kandidaten = [str(config.AIRFLOW_OUTPUT_RAPPORTEN)]
    if getattr(config, 'AIRFLOW_LOGDIR', None):
        kandidaten.append(os.path.join(str(config.AIRFLOW_LOGDIR), 'rapporten'))
    fouten = []
    for i, map_ in enumerate(kandidaten):
        try:
            os.makedirs(map_, exist_ok=True)
            if os.access(map_, os.W_OK):
                if i:
                    logger.warning(f"Rapportmap {kandidaten[0]} is niet schrijfbaar; het rapport komt in {map_}.")
                return map_, i > 0
            fouten.append(f"{map_}: niet schrijfbaar")
        except OSError as err:
            fouten.append(f"{map_}: {err}")
    raise OSError(f"Geen schrijfbare map voor het verwerkingsrapport: {fouten}")


def maakBestandsnaam(rapport):
    """Bestandsnaam zonder extensie: verwerkingsrapport_<run_id>_<soort>_<tijdstip>."""
    meta = rapport.get('run') or {}
    run_id = meta.get('run_id') or 'zonder-run'
    soort = meta.get('soort') or meta.get('dag_id') or 'onbekend'
    tijdstip = _naief(rapport.get('gemaakt_op') or verwerkingsrun.nu()).strftime('%Y%m%dT%H%M%S')
    naam = f"verwerkingsrapport_{run_id}_{soort}_{tijdstip}"
    return re.sub(r'[^A-Za-z0-9_.-]', '_', naam)


def _schrijfAtomair(pad, tekst):
    """Schrijf een bestand via een tijdelijk bestand in dezelfde map, zodat er nooit een half rapport staat."""
    tijdelijk = pad + '.tmp'
    with open(tijdelijk, 'w', encoding='utf-8') as f:
        f.write(tekst)
    os.replace(tijdelijk, pad)


def schrijfRapport(rapport, markdown, map_):
    """Schrijf het rapport als JSON en Markdown in een map.

    Args:
        rapport: dict uit verzamelRapport
        markdown: tekst uit maakMarkdown
        map_: map uit bepaalRapportmap

    Returns:
        Tuple (pad JSON, pad Markdown)
    """
    basis = os.path.join(map_, maakBestandsnaam(rapport))
    _schrijfAtomair(basis + '.json', json.dumps(rapport, default=_jsonWaarde, ensure_ascii=False, indent=2))
    _schrijfAtomair(basis + '.md', markdown)
    return basis + '.json', basis + '.md'


def logSamenvatting(rapport, json_pad, md_pad):
    """Schrijf een leesbare samenvatting van het rapport in het log van de taak."""
    meta = rapport.get('run') or {}
    s = rapport.get('samenvatting') or {}
    fb = rapport.get('foutbeleid') or {}
    regels = [f"Verwerkingsrapport van run {meta.get('run_id')} ({meta.get('soort')}, {meta.get('dag_id')}): "
              f"{s.get('uitkomst')}, status {meta.get('status')}, doorlooptijd {_duur(meta.get('duur_seconden'))}.",
              f"  Fouten: {s.get('fouten')}, waarschuwingen: {s.get('waarschuwingen')}"
              + (f", gestopt door {s.get('gestopt_door')}" if s.get('gestopt_door') else '') + '.',
              f"  Bronbestanden: {s.get('bronbestanden')}.",
              f"  Objecten: {s.get('objecten')}.",
              f"  Verwerkingsfouten: {s.get('verwerkingsfouten')}, afbeeldingen niet verwerkt: "
              f"{s.get('afbeeldingen_mislukt')}, onleesbare databases: {s.get('databases_onleesbaar')}."]
    for m in (fb.get('fouten') or [])[:5]:
        regels.append(f"  FOUT [{m.get('stap')}] {m.get('taak')}: {str(m.get('melding'))[:300]}")
    for m in (fb.get('waarschuwingen') or [])[:10]:
        regels.append(f"  WAARSCHUWING [{m.get('stap')}] {m.get('taak')}: {str(m.get('melding'))[:300]}")
    regels.append(f"  Rapport: {json_pad} en {md_pad}")
    logger.info('\n'.join(regels))


# ============================================================
# Taak
# ============================================================

def maakVerwerkingsrapport(**context):
    """Taak Verwerkingsrapport: bouw en schrijf het rapport van deze run (trigger rule all_done).

    Zoekt het run-document van deze Airflow-run (ook als de run al is
    beëindigd of mislukt), leest de taken van de DagRun, bouwt het rapport,
    schrijft het als JSON en Markdown, logt een samenvatting en zet de paden
    en de samenvatting in het run-document (veld rapport). Zonder
    run-document (Start_Run mislukte) volgt een rapport met alleen de
    gegevens uit Airflow.

    Args:
        context: Airflow-context (dag_run en task_instance)

    Returns:
        Dict met de paden van het JSON- en het Markdown-rapport
    """
    dag_run = context.get('dag_run')
    ti = context.get('task_instance') or context.get('ti')
    run = None
    if dag_run is not None:
        run = verwerkingsrun.zoekRunVanAirflowRun(dag_run.run_id, sinds=verwerkingsrun.startVanAirflowRun(dag_run))
    else:
        run = verwerkingsrun.huidigeRun(verplicht=False)

    uitsluiten = set()
    if ti is not None:
        uitsluiten.add(ti.task_id)
        taak = getattr(ti, 'task', None)
        if taak is not None:
            uitsluiten.update(t.task_id for t in taak.get_flat_relatives(upstream=False))
    taken = leesTaken(dag_run, uitsluiten) if dag_run is not None else []

    map_, terugval = bepaalRapportmap()
    if terugval and run is not None:
        # De waarschuwing komt in het run-document vóór het rapport wordt opgebouwd, en dus ook in het rapport
        foutbeleid.meld(foutbeleid.NIVEAU_WAARSCHUWING, foutbeleid.SOORT_RAPPORT,
                        f"Rapportmap {config.AIRFLOW_OUTPUT_RAPPORTEN} niet schrijfbaar; rapport geschreven naar {map_}.",
                        run_id=run['run_id'], taak=ti.task_id if ti is not None else None)
        run = verwerkingsrun.zoekRunVanAirflowRun(dag_run.run_id, sinds=verwerkingsrun.startVanAirflowRun(dag_run)) if dag_run is not None else run

    rapport = verzamelRapport(run, taken, dag_run)
    markdown = maakMarkdown(rapport)
    json_pad, md_pad = schrijfRapport(rapport, markdown, map_)
    logSamenvatting(rapport, json_pad, md_pad)

    if run is not None:
        try:
            verwerkingsrun.werkRunBij({'rapport': {
                'json': json_pad, 'markdown': md_pad, 'map_terugval': terugval,
                'gemaakt_op': rapport['gemaakt_op'], 'samenvatting': rapport['samenvatting']}}, run_id=run['run_id'])
        except Exception as err:
            logger.warning(f"Rapport niet in het run-document vastgelegd: {err}")
    return {'json': json_pad, 'markdown': md_pad}
