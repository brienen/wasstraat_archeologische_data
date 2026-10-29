"""Extractie van afbeeldingen en rapporten (collectie Filenames, taken Extract_Data_From_Fotos_*).

Elk bestand in de collectie ``Filenames`` (database ``config.DB_FILES``) heeft
na de import-taken precies één van deze statussen (issue 70):

- **verwerkt**: ``processed: True`` en ``verwerkt_op`` (tijdstip, UTC);
- **overgeslagen**: ``processed: True``, ``verwerkt_op`` en ``overgeslagen`` met
  de reden (``OVERGESLAGEN_JPG_AANWEZIG`` of ``OVERGESLAGEN_GEEN_AFBEELDING``);
- **mislukt**: ``processed: False`` met ``fout`` (foutmelding) en ``fout_op``
  (tijdstip, UTC); de volgende import-taak (herhaling, ``Redo_Images`` of de
  volgende incrementele run) probeert het bestand opnieuw;
- **onverwerkt**: ``processed: False`` zonder ``fout``: nog niet aan de beurt
  geweest. Na de import-taken hoort dit niet voor te komen.

Een vol volume, een quotum of een alleen-lezen of niet-schrijfbare uitvoermap is
een ``OnherstelbareFout``: de import-taak stopt direct (binnen Airflow zonder
herhalingen) in plaats van alle volgende bestanden stil te laten mislukken. De
taak ``Controleer_Afbeeldingen`` telt daarna de statussen, logt de eerste
foutmeldingen en faalt als het aantal mislukte en onverwerkte bestanden boven
de drempel komt (``AIRFLOW_MAX_MISLUKTE_AFBEELDINGEN`` en
``AIRFLOW_MAX_MISLUKTE_AFBEELDINGEN_PCT``).
"""
import errno
import logging
import os
import random
import re

import gridfs
import pandas as pd
import pymongo
from pymongo import InsertOne

import shared.config as config
import shared.image_util as image_util
import wasstraat.paden_overslaan as paden_overslaan
import wasstraat.verwerkingsrun as verwerkingsrun

try:
    from airflow.exceptions import AirflowFailException as _FaalZonderHerhaling
except ImportError:  # buiten Airflow, bijvoorbeeld in de unit tests
    _FaalZonderHerhaling = Exception

logger = logging.getLogger("airflow.task")

# Statussen van een bestand in Filenames (afgeleid uit processed, overgeslagen en fout)
STATUS_VERWERKT = 'verwerkt'
STATUS_OVERGESLAGEN = 'overgeslagen'
STATUS_MISLUKT = 'mislukt'
STATUS_ONVERWERKT = 'onverwerkt'

# Redenen in het veld 'overgeslagen'
OVERGESLAGEN_JPG_AANWEZIG = 'jpg-versie aanwezig'
OVERGESLAGEN_GEEN_AFBEELDING = 'sfeerfoto of niet-ondersteund bestandstype'

# Filters per status
FILTER_VERWERKT = {'processed': True, 'overgeslagen': {'$exists': False}}
FILTER_OVERGESLAGEN = {'processed': True, 'overgeslagen': {'$exists': True}}
FILTER_MISLUKT = {'processed': False, 'fout': {'$exists': True}}
FILTER_ONVERWERKT = {'processed': False, 'fout': {'$exists': False}}

# Drempel voor Controleer_Afbeeldingen: de taak faalt als het aantal mislukte plus
# onverwerkte bestanden groter is dan max(aantal, percentage van het totaal)
OMGEVING_MAX_MISLUKT = 'AIRFLOW_MAX_MISLUKTE_AFBEELDINGEN'
OMGEVING_MAX_MISLUKT_PCT = 'AIRFLOW_MAX_MISLUKTE_AFBEELDINGEN_PCT'
STANDAARD_MAX_MISLUKT = 10
STANDAARD_MAX_MISLUKT_PCT = 1.0

MAX_VOORBEELDEN = 10        # aantal foutmeldingen in het log en het run-document
MAX_LENGTE_FOUT = 2000      # foutmeldingen in Filenames worden hierop afgekapt

# Fouten waarbij doorgaan met het volgende bestand geen zin heeft
ONHERSTELBARE_ERRNOS = {
    errno.ENOSPC: 'het volume is vol',
    errno.EROFS: 'het volume is alleen-lezen',
}
if hasattr(errno, 'EDQUOT'):
    ONHERSTELBARE_ERRNOS[errno.EDQUOT] = 'het schijfquotum is bereikt'


class OnherstelbareFout(_FaalZonderHerhaling):
    """Fout waarbij de taak direct moet stoppen.

    Bijvoorbeeld een vol mediavolume, geen schrijfrechten op de uitvoermap of te
    veel mislukte bestanden. Binnen Airflow is dit een AirflowFailException: de
    taak faalt meteen, zonder de herhalingen (retries) die bij een tijdelijke
    storing wel zinvol zijn.
    """


def _laadImageFilterPatronen():
    """Laad rapportcode-prefixen uit correcties.yml en combineer met generieke patronen."""
    generieke_patronen = ["velddocument", "fotos", "tekening"]
    try:
        import yaml
        pad = getattr(config, 'AIRFLOW_CORRECTIES_CONFIG', None)
        if pad and os.path.isfile(pad):
            with open(pad, 'r') as f:
                correcties = yaml.safe_load(f) or {}
            if isinstance(correcties, dict):
                for entry in correcties.get('rapportcode_prefixen', []):
                    if isinstance(entry, dict) and 'prefix' in entry:
                        generieke_patronen.append(str(entry['prefix']))
                    else:
                        logger.warning(f"Ongeldige rapportcode_prefix entry: {entry} — overslaan.")
    except Exception as e:
        logger.error(f"Fout bij laden image-filterpatronen uit correcties.yml: {e}")
    return generieke_patronen

_image_filter_patronen = None


def _zoekBestandenInMap(dir):
    """Alle bestanden onder een map met een extensie uit IMAGE_EXTENSIONS."""
    return [os.path.join(dp, f) for dp, dn, filenames in os.walk(dir) for f in filenames if os.path.splitext(f)[1].lower() in config.IMAGE_EXTENSIONS]


def _selecteerOpNaam(lst):
    """Houd de bestanden over waarvan het pad een van de filterpatronen bevat (_laadImageFilterPatronen)."""
    global _image_filter_patronen
    if _image_filter_patronen is None:
        _image_filter_patronen = _laadImageFilterPatronen()
    patronen = _image_filter_patronen
    # Generieke patronen worden case-insensitive gematcht, rapportcode-prefixen case-sensitive
    def matchesFilter(file):
        fl = file.lower()
        for p in patronen:
            if p[0].isupper():
                # Rapportcode-prefixen: case-sensitive match
                if p in file:
                    return True
            else:
                # Generieke patronen: case-insensitive match
                if p in fl:
                    return True
        return False
    return [file for file in lst if matchesFilter(file)]


def getImageNamesFromDir(dir, overgeslagen=None):
    """Retourneer de afbeeldingen en rapporten onder een map waarvan het pad een filterpatroon bevat.

    Bestanden die onder een patroon uit paden_overslaan in correcties.yml
    vallen, worden weggelaten (issue 84), met een logregel per bestand.

    Args:
        dir: invoermap (de patronen van paden_overslaan zijn hier relatief aan)
        overgeslagen: optionele lijst die met de overgeslagen paden wordt aangevuld

    Returns:
        Lijst met unieke volledige paden
    """
    lst = list(set(_selecteerOpNaam(_zoekBestandenInMap(dir))))
    return paden_overslaan.filterPaden(lst, dir, overgeslagen=overgeslagen, omschrijving='afbeeldingen en rapporten')


def getImageNamesFromExcelAndDir(dir, overgeslagen=None):
    """Retourneer de bestanden uit de bestandenlijst (FILE_IMPORT_FILES_EXCEL) die getImageNamesFromDir niet al vindt.

    Bestanden die onder een patroon uit paden_overslaan vallen, worden
    weggelaten (issue 84). De vergelijking met getImageNamesFromDir gebeurt op
    de selectie vóór paden_overslaan, zodat een overgeslagen bestand niet via de
    bestandenlijst alsnog wordt verwerkt.

    Args:
        dir: invoermap (de patronen van paden_overslaan zijn hier relatief aan)
        overgeslagen: optionele lijst die met de overgeslagen paden wordt aangevuld

    Returns:
        Lijst met volledige paden
    """
    # get list from excel
    df = pd.read_excel(config.FILE_IMPORT_FILES_EXCEL)
    df = df[df['wel/niet'] == 1]
    df['fulldir'] = df['Dir'] + '/' + df['Bestand']
    excel_lst = df['fulldir'].tolist()

    # get files from dir
    dir_lst = _zoekBestandenInMap(dir)

    lst = list(set(excel_lst).intersection(set(dir_lst)).difference(set(_selecteerOpNaam(dir_lst))))
    return paden_overslaan.filterPaden(lst, dir, overgeslagen=overgeslagen, omschrijving='bestanden uit de bestandenlijst')


def markeerVerwerkt(col, doc_id, overgeslagen=None):
    """Leg in Filenames vast dat een bestand verwerkt of bewust overgeslagen is.

    Args:
        col: de collectie Filenames
        doc_id: _id van het document
        overgeslagen: reden van overslaan (bijv. OVERGESLAGEN_JPG_AANWEZIG); None als het bestand verwerkt is
    """
    velden = {'processed': True, 'verwerkt_op': verwerkingsrun.nu()}
    weg = {'fout': '', 'fout_op': ''}
    if overgeslagen:
        velden['overgeslagen'] = overgeslagen
    else:
        weg['overgeslagen'] = ''
    col.update_one({'_id': doc_id}, {'$set': velden, '$unset': weg})


def markeerMislukt(col, doc_id, melding):
    """Leg in Filenames vast dat een bestand mislukt is (processed blijft False).

    Args:
        col: de collectie Filenames
        doc_id: _id van het document
        melding: foutmelding (afgekapt op MAX_LENGTE_FOUT tekens)
    """
    col.update_one({'_id': doc_id}, {
        '$set': {'processed': False, 'fout': str(melding)[:MAX_LENGTE_FOUT], 'fout_op': verwerkingsrun.nu()},
        '$unset': {'overgeslagen': '', 'verwerkt_op': ''}})


def vindOnherstelbareOorzaak(err):
    """Zoek in de keten van oorzaken van een fout naar een fout waarbij doorgaan geen zin heeft.

    image_util verpakt fouten in een nieuwe Exception ('raise ... from err'),
    daarom wordt de hele keten (__cause__ en __context__) doorzocht. Onherstelbaar
    zijn een OSError met errno ENOSPC (volume vol), EDQUOT (quotum) of EROFS
    (alleen-lezen), en een PermissionError op een pad in de uitvoermap
    (AIRFLOW_OUTPUT_MEDIA). Een PermissionError op een bronbestand geldt als een
    gewone fout van dat ene bestand.

    Args:
        err: de opgevangen exception

    Returns:
        De onherstelbare OSError uit de keten, of None
    """
    uitvoermap = os.path.normpath(str(config.AIRFLOW_OUTPUT_MEDIA))
    gezien = set()
    while err is not None and id(err) not in gezien:
        gezien.add(id(err))
        if isinstance(err, OSError):
            if err.errno in ONHERSTELBARE_ERRNOS:
                return err
            if isinstance(err, PermissionError) and err.filename is not None:
                pad = os.path.normpath(str(err.filename))
                if pad == uitvoermap or pad.startswith(uitvoermap + os.sep):
                    return err
        err = err.__cause__ if err.__cause__ is not None else err.__context__
    return None


def maakMeldingOnherstelbaar(bestand, oorzaak):
    """Bouw een duidelijke foutmelding voor een onherstelbare fout.

    Args:
        bestand: het bestand dat werd verwerkt
        oorzaak: de OSError uit vindOnherstelbareOorzaak

    Returns:
        Tekst met de oorzaak, de uitvoermap en wat de beheerder moet doen
    """
    if oorzaak.errno in ONHERSTELBARE_ERRNOS:
        wat = ONHERSTELBARE_ERRNOS[oorzaak.errno]
    else:
        wat = 'er zijn geen schrijfrechten'
    return (f"Extractie van afbeeldingen gestopt: {wat} bij het opslaan van {bestand} in de uitvoermap "
            f"{config.AIRFLOW_OUTPUT_MEDIA} ({oorzaak}). Alle volgende bestanden zouden ook mislukken. "
            f"Los dit op (ruimte vrijmaken, volume vergroten of rechten herstellen) en draai de extractie "
            f"opnieuw; Redo_Images verwerkt alleen de bestanden die nog niet verwerkt zijn.")


def verwerkBestand(col, fs, plaatjes, file):
    """Verwerk één bestand uit Filenames en leg de status vast.

    Args:
        col: de collectie Filenames
        fs: GridFS van de files-database
        plaatjes: de staging-collectie Plaatjes
        file: het document uit Filenames

    Returns:
        STATUS_VERWERKT, STATUS_OVERGESLAGEN of STATUS_MISLUKT

    Raises:
        OnherstelbareFout: bij een vol volume of een niet-schrijfbare uitvoermap
    """
    filedirname = file['filename']
    logger.info('Afbeelding verwerken en laden: %s' % filedirname)

    # Een tif of pdf waarvan al een jpg-versie bestaat wordt bewust overgeslagen
    filename, file_extension = os.path.splitext(filedirname)
    if 'tif' in file_extension or 'pdf' in file_extension:
        regex = re.compile(re.escape(filename + ".jpg"))
        if col.find_one({'filename': regex}):
            markeerVerwerkt(col, file['_id'], overgeslagen=OVERGESLAGEN_JPG_AANWEZIG)
            return STATUS_OVERGESLAGEN

    try:
        result = image_util.adjustAndSaveFile(filedirname, fs, plaatjes)
    except Exception as err:
        markeerMislukt(col, file['_id'], err)
        oorzaak = vindOnherstelbareOorzaak(err)
        if oorzaak is not None:
            msg = maakMeldingOnherstelbaar(filedirname, oorzaak)
            logger.error(msg)
            raise OnherstelbareFout(msg) from err
        logger.error(f"Onbekende fout bij het laden van image: {filedirname} met melding {err}")
        return STATUS_MISLUKT

    if not result:
        # adjustAndSaveFile slaat sfeerfoto's en niet-ondersteunde bestandstypen bewust over
        logger.warning(f"Bestand {filedirname} niet opgeslagen ({OVERGESLAGEN_GEEN_AFBEELDING}).")
        markeerVerwerkt(col, file['_id'], overgeslagen=OVERGESLAGEN_GEEN_AFBEELDING)
        return STATUS_OVERGESLAGEN

    markeerVerwerkt(col, file['_id'])
    return STATUS_VERWERKT


def importImages(index, of):
    """Verwerk het blok index (van of blokken) van de nog niet verwerkte bestanden in Filenames.

    De taken Extract_Data_From_Fotos_<index> draaien parallel; elk neemt de
    documenten met processed False en een iter-waarde in het eigen blok (het
    laatste blok neemt de rest). Per bestand wordt de status vastgelegd (zie de
    moduledocumentatie). Een fout bij één bestand stopt de taak niet; een
    onherstelbare fout (vol volume, geen schrijfrechten) wel.

    Args:
        index: nummer van het blok (0 t/m of - 1)
        of: aantal blokken (parallelle taken)

    Returns:
        Dict met het aantal verwerkte, overgeslagen en mislukte bestanden in dit blok

    Raises:
        OnherstelbareFout: bij een vol volume of een niet-schrijfbare uitvoermap
        Exception: bij andere fouten buiten de verwerking van een bestand (bijv. MongoDB)
    """
    myclient = None
    try:
        myclient = pymongo.MongoClient(config.MONGO_URI)
        filesdb = myclient[config.DB_FILES]
        fs = gridfs.GridFS(filesdb)
        stagingdb = myclient[config.DB_STAGING]
        col = filesdb[config.COLL_FILENAMES]

        count = col.count_documents({})
        blocksize = int(count/of)
        import_from = index*blocksize -1
        import_to = (index+1)*blocksize

        logger.info(f"Importing images from index {str(import_from)} " + f" to index {str(import_to)}" if index<of-1 else "")
        aggr = {'iter': {'$gt': import_from, '$lt': import_to}, 'processed': False} if index<of-1 else {'iter': {'$gt': index*blocksize -1}, 'processed': False}

        tellingen = {STATUS_VERWERKT: 0, STATUS_OVERGESLAGEN: 0, STATUS_MISLUKT: 0}
        for file in col.find(aggr):
            status = verwerkBestand(col, fs, stagingdb[config.COLL_PLAATJES], file)
            tellingen[status] += 1

        logger.info(f"Blok {index} van {of}: {tellingen[STATUS_VERWERKT]} verwerkt, "
                    f"{tellingen[STATUS_OVERGESLAGEN]} overgeslagen, {tellingen[STATUS_MISLUKT]} mislukt.")
        if tellingen[STATUS_MISLUKT]:
            logger.warning(f"Blok {index} van {of}: {tellingen[STATUS_MISLUKT]} bestanden mislukt; zie het veld "
                           f"'fout' in {config.COLL_FILENAMES} en de taak Controleer_Afbeeldingen.")
        return tellingen

    except OnherstelbareFout:
        raise

    except Exception as err:
        msg = "Onbekende fout bij het laden van images: " + str(err)
        logger.error(msg)
        raise Exception(msg) from err

    finally:
        if myclient is not None:
            myclient.close()


def leesGetalUitOmgeving(naam, standaard, soort=int):
    """Lees een niet-negatief getal uit een omgevingsvariabele.

    Omgevingsvariabelen zijn altijd tekst. Een lege, ongeldige of negatieve
    waarde levert de standaardwaarde op, met een waarschuwing in het log.

    Args:
        naam: naam van de omgevingsvariabele
        standaard: waarde als de variabele ontbreekt of ongeldig is
        soort: int of float

    Returns:
        Het getal
    """
    waarde = os.getenv(naam)
    if waarde is None or not str(waarde).strip():
        return standaard
    try:
        getal = soort(str(waarde).strip().replace(',', '.'))
    except ValueError:
        logger.warning(f"Ongeldige waarde '{waarde}' voor {naam}; standaardwaarde {standaard} gebruikt.")
        return standaard
    if getal < 0:
        logger.warning(f"Negatieve waarde '{waarde}' voor {naam}; standaardwaarde {standaard} gebruikt.")
        return standaard
    return getal


def bepaalDrempel(totaal, max_aantal, max_pct):
    """Bepaal hoeveel mislukte bestanden nog acceptabel zijn.

    De drempel is het grootste van een vast aantal en een percentage van het
    totaal: bij een kleine verzameling telt het vaste aantal, bij een grote
    (~100.000 foto's) het percentage.

    Args:
        totaal: aantal bestanden waarover geteld is
        max_aantal: vast aantal (AIRFLOW_MAX_MISLUKTE_AFBEELDINGEN)
        max_pct: percentage van het totaal (AIRFLOW_MAX_MISLUKTE_AFBEELDINGEN_PCT)

    Returns:
        Het hoogste toegestane aantal mislukte plus onverwerkte bestanden
    """
    return max(int(max_aantal), int(totaal * max_pct / 100))


def _metBereik(bereik, filt):
    """Combineer een bereikfilter (kan leeg zijn) met een statusfilter."""
    return {'$and': [bereik, filt]} if bereik else dict(filt)


def telAfbeeldingStatussen(col, bereik=None):
    """Tel de bestanden in Filenames per status.

    Args:
        col: de collectie Filenames
        bereik: optioneel filter op de documenten die meetellen (incrementele run)

    Returns:
        Dict met totaal, verwerkt, overgeslagen, overgeslagen_per_reden, mislukt,
        onverwerkt en voorbeelden (de eerste MAX_VOORBEELDEN mislukte of
        onverwerkte bestanden met filename, fout en fout_op)
    """
    tellingen = {
        'totaal': col.count_documents(bereik or {}),
        STATUS_VERWERKT: col.count_documents(_metBereik(bereik, FILTER_VERWERKT)),
        STATUS_OVERGESLAGEN: col.count_documents(_metBereik(bereik, FILTER_OVERGESLAGEN)),
        STATUS_MISLUKT: col.count_documents(_metBereik(bereik, FILTER_MISLUKT)),
        STATUS_ONVERWERKT: col.count_documents(_metBereik(bereik, FILTER_ONVERWERKT)),
    }
    per_reden = col.aggregate([
        {'$match': _metBereik(bereik, FILTER_OVERGESLAGEN)},
        {'$group': {'_id': '$overgeslagen', 'aantal': {'$sum': 1}}},
    ])
    tellingen['overgeslagen_per_reden'] = {str(r['_id']): r['aantal'] for r in per_reden}
    voorbeelden = col.find(_metBereik(bereik, {'processed': False}),
                           {'_id': 0, 'filename': 1, 'fout': 1, 'fout_op': 1}).sort('filename', 1).limit(MAX_VOORBEELDEN)
    tellingen['voorbeelden'] = [{'filename': d.get('filename'), 'fout': d.get('fout'), 'fout_op': d.get('fout_op')}
                                for d in voorbeelden]
    return tellingen


def controleerAfbeeldingen(incrementeel=False):
    """Taak Controleer_Afbeeldingen: tel de statussen in Filenames en faal boven de drempel.

    Draait na alle import-taken (Extract_Data_From_Fotos_*) en vóór de
    transformatie. Logt het aantal verwerkte, overgeslagen, mislukte en
    onverwerkte bestanden en de eerste foutmeldingen. Is het aantal mislukte
    plus onverwerkte bestanden groter dan de drempel (bepaalDrempel), dan faalt
    de taak en daarmee de DAG; daaronder volgt een waarschuwing.

    In de volledige cyclus, Extract_only en Redo_Images telt de hele collectie.
    In de incrementele cyclus tellen alleen de bestanden die in deze run zijn
    verwerkt of overgeslagen (verwerkt_op na de start van de run) en alle
    bestanden die nog openstaan (processed False); de tellingen komen in het
    run-document onder tellingen.afbeeldingen, ook als de taak faalt.

    Args:
        incrementeel: True in de incrementele cyclus (run-document bijwerken)

    Raises:
        OnherstelbareFout: als het aantal mislukte plus onverwerkte bestanden boven de drempel ligt
    """
    max_aantal = leesGetalUitOmgeving(OMGEVING_MAX_MISLUKT, STANDAARD_MAX_MISLUKT, int)
    max_pct = leesGetalUitOmgeving(OMGEVING_MAX_MISLUKT_PCT, STANDAARD_MAX_MISLUKT_PCT, float)

    run = verwerkingsrun.huidigeRun() if incrementeel else None
    bereik = {'$or': [{'processed': False}, {'verwerkt_op': {'$gte': run['gestart_op']}}]} if run else None

    myclient = pymongo.MongoClient(config.MONGO_URI)
    try:
        col = myclient[config.DB_FILES][config.COLL_FILENAMES]
        tellingen = telAfbeeldingStatussen(col, bereik)
    finally:
        myclient.close()

    niet_verwerkt = tellingen[STATUS_MISLUKT] + tellingen[STATUS_ONVERWERKT]
    drempel = bepaalDrempel(tellingen['totaal'], max_aantal, max_pct)
    tellingen.update({'drempel': drempel, 'max_aantal': max_aantal, 'max_pct': max_pct,
                      'boven_drempel': niet_verwerkt > drempel})

    if run:
        verwerkingsrun.werkRunBij({'tellingen.afbeeldingen': tellingen}, run_id=run['run_id'])

    logger.info(f"Controle afbeeldingen: {tellingen['totaal']} bestanden, {tellingen[STATUS_VERWERKT]} verwerkt, "
                f"{tellingen[STATUS_OVERGESLAGEN]} overgeslagen {tellingen['overgeslagen_per_reden']}, "
                f"{tellingen[STATUS_MISLUKT]} mislukt, {tellingen[STATUS_ONVERWERKT]} onverwerkt "
                f"(drempel {drempel}: max({max_aantal}, {max_pct}% van {tellingen['totaal']})).")
    if not niet_verwerkt:
        return

    lijst = "\n".join(f"  - {v['filename']}: {v['fout'] if v['fout'] else 'niet verwerkt (geen foutmelding)'}"
                      for v in tellingen['voorbeelden'])
    if niet_verwerkt > MAX_VOORBEELDEN:
        lijst += f"\n  ... en nog {niet_verwerkt - MAX_VOORBEELDEN} (zoek in {config.COLL_FILENAMES} op processed: false)"

    if tellingen['boven_drempel']:
        msg = (f"{niet_verwerkt} van de {tellingen['totaal']} afbeeldingen en rapporten zijn niet verwerkt "
               f"({tellingen[STATUS_MISLUKT]} mislukt, {tellingen[STATUS_ONVERWERKT]} onverwerkt); dat is meer dan "
               f"de drempel van {drempel} ({OMGEVING_MAX_MISLUKT}={max_aantal}, {OMGEVING_MAX_MISLUKT_PCT}={max_pct}). "
               f"Eerste meldingen:\n{lijst}\nHerstel de oorzaak en draai de extractie opnieuw (Redo_Images verwerkt "
               f"alleen de onverwerkte bestanden), of verhoog de drempel als deze bestanden bekend en acceptabel zijn.")
        logger.error(msg)
        raise OnherstelbareFout(msg)

    logger.warning(f"{niet_verwerkt} afbeeldingen en rapporten niet verwerkt ({tellingen[STATUS_MISLUKT]} mislukt, "
                   f"{tellingen[STATUS_ONVERWERKT]} onverwerkt), binnen de drempel van {drempel}:\n{lijst}")




def getImageFilenames(overgeslagen=None):
    """Retourneer alle afbeeldingen en rapporten die de extractie verwerkt.

    Dezelfde selectie wordt gebruikt door de volledige extractie en door de
    registratie van bronbestanden (bronbestanden.py) voor incrementeel laden.
    Bestanden die onder een patroon uit paden_overslaan in correcties.yml
    vallen, horen er niet bij (issue 84).

    Args:
        overgeslagen: optionele lijst die met de overgeslagen paden wordt aangevuld

    Returns:
        Lijst met volledige paden (niet geschud)
    """
    return (getImageNamesFromDir(config.AIRFLOW_INPUT_IMAGES, overgeslagen)
            + getImageNamesFromDir(config.AIRFLOW_INPUT_RAPPORTEN, overgeslagen)
            + getImageNamesFromExcelAndDir(config.AIRFLOW_INPUT_IMAGES, overgeslagen))


def maakFilenameInserts(paden, aantal_bestaand):
    """Maak InsertOne-operaties voor nieuwe of gewijzigde afbeeldingen bij een incrementele run.

    De iter-waarden worden gelijkmatig verdeeld over het bereik van de hele
    collectie, zodat de parallelle importImages-taken (die op iter-blokken
    splitsen) de nieuwe bestanden onderling verdelen.

    Args:
        paden: lijst met volledige paden van de toe te voegen bestanden
        aantal_bestaand: aantal documenten dat al in Filenames staat

    Returns:
        Lijst met InsertOne-operaties
    """
    totaal = aantal_bestaand + len(paden)
    return [InsertOne({'iter': (i * totaal) // len(paden), 'filename': v, 'processed': False}) for i, v in enumerate(paden)]


def voegImageFilenamesToe(paden):
    """Voeg bij een incrementele run alleen de opgegeven afbeeldingen toe aan Filenames.

    De collectie wordt niet geleegd. Bestaande entries voor dezelfde
    bestandsnamen worden eerst verwijderd, zodat er geen dubbelingen ontstaan.
    De nieuwe entries krijgen processed: False, waarna importImages ze oppakt,
    samen met de bestanden die in een eerdere run mislukten.

    Openstaande entries (processed: False) van bestanden die niet meer bestaan
    worden verwijderd. Dat gebeurt als een bestand na een mislukte run is
    weggehaald voordat het geregistreerd was: de delta kent het dan niet als
    verwijderd, en zonder opruimen zou elke volgende run het als mislukt tellen.

    Args:
        paden: lijst met volledige paden van nieuwe en gewijzigde afbeeldingen
    """
    paden = list(paden)
    random.shuffle(paden) # Shuffle to make sure not all big files are at the end
    logger.info(f'Incrementeel: {len(paden)} nieuwe of gewijzigde afbeeldingen voor verwerking...')

    myclient = None
    try:
        myclient = pymongo.MongoClient(config.MONGO_URI)
        filesdb = myclient[config.DB_FILES]
        col = filesdb[config.COLL_FILENAMES]

        verdwenen = [d['filename'] for d in col.find({'processed': False}, {'filename': 1})
                     if not os.path.exists(d['filename'])]
        if verdwenen:
            col.delete_many({'filename': {'$in': verdwenen}})
            logger.warning(f"{len(verdwenen)} openstaande Filenames-entries verwijderd van bestanden die niet meer "
                           f"bestaan: {verdwenen[:MAX_VOORBEELDEN]}")

        if not paden:
            logger.info("Geen nieuwe of gewijzigde afbeeldingen — overslaan.")
            return

        verwijderd = col.delete_many({'filename': {'$in': paden}}).deleted_count
        if verwijderd:
            logger.info(f"{verwijderd} bestaande Filenames-entries voor deze bestanden verwijderd.")

        col.bulk_write(maakFilenameInserts(paden, col.count_documents({})))
        col.create_index([ ("iter", 1) ])
        col.create_index([ ("filename", 1) ])

    except Exception as err:
        msg = "Onbekende fout bij het toevoegen van de filenames: " + str(err)
        logger.error(msg)
        raise Exception(msg) from err

    finally:
        if myclient is not None:
            myclient.close()


def getAndStoreImageFilenames(incrementeel=False):
    """Sla de te verwerken afbeeldingen op in de collectie Filenames.

    Args:
        incrementeel: als True alleen de nieuwe en gewijzigde afbeeldingen uit de
            actieve verwerkingsrun toevoegen (zonder de collectie te legen)
    """
    if incrementeel:
        voegImageFilenamesToe(verwerkingsrun.getDeltaPaden('afbeeldingen'))
        return

    lst_filenames = getImageFilenames()
    random.shuffle(lst_filenames) # Shuffle to make sure not all big files are at the end
    logger.info(f'Found {len(lst_filenames)} unique image files for processing...')

    try: 
        myclient = pymongo.MongoClient(config.MONGO_URI)
        filesdb = myclient[config.DB_FILES]
        col = filesdb[config.COLL_FILENAMES]

        #First drop collection to not get doubles
        col.drop()

        inserts=[ InsertOne({'iter': i, 'filename': v, 'processed': False}) for i,v in enumerate(lst_filenames) ]
        if not inserts:
            logger.info("Geen afbeeldingen gevonden om te verwerken — overslaan.")
            return
        result = col.bulk_write(inserts)
        col.create_index([ ("iter", 1) ])
        col.create_index([ ("filename", 1) ])
     
    except Exception as err:
        msg = "Onbekende fout bij het opslaan van de filenames: " + str(err)
        logger.error(msg)    
        raise Exception(msg) from err

    finally:
        myclient.close()





