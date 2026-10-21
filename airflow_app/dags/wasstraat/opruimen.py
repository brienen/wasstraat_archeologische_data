"""Opruimen van oude records voor gewijzigde en verwijderde bronbestanden (incrementeel laden, stap 2).

Werkwijze per categorie (zie docs/componenten/incrementeel-laden.md):

1. Verzamel de ``_id``'s van de staging-documenten van de bestanden
   (staging-collecties op ``mdbfile``, ``Plaatjes`` op ``fullFileName``).
2. Lees de bijbehorende ``Single_Store``-documenten (zelfde ``_id``, of via
   ``brondata.mdbfile``/``fullFileName`` voor soorten waarvan de harmonisatie
   een nieuw ``_id`` maakt) en bewaar hun soort, key en projectcd (voor
   Artefact ook key_subnr en artefactsoort) in het run-document.
3. Verwijder daarna de documenten uit ``Single_Store``, uit
   ``Single_Store_Clean`` (op dezelfde ``_id``'s) en uit de staging. Voor
   afbeeldingen ook uit ``Plaatjes`` en ``Filenames``, de GridFS-bestanden en
   de kopieën in ``AIRFLOW_OUTPUT_MEDIA``.
"""
import os

import pymongo
import gridfs
from bson import ObjectId

import shared.config as config
import wasstraat.verwerkingsrun as verwerkingsrun
import wasstraat.bronbestanden as bronbestanden
import logging

logger = logging.getLogger("airflow.task")

BATCH_GROOTTE = 5000

# Velden in Plaatjes die naar de opgeslagen afbeeldingen verwijzen. De huidige
# image_util slaat paden relatief aan AIRFLOW_OUTPUT_MEDIA op in imageID,
# imageMiddleID en imageThumbID; een oudere versie sloeg GridFS-ObjectIds op in
# imageUUID, imageMiddleUUID en imageThumbUUID.
IMAGE_ID_VELDEN = ['imageID', 'imageMiddleID', 'imageThumbID', 'imageUUID', 'imageMiddleUUID', 'imageThumbUUID']

SLEUTEL_VELDEN = {'soort': 1, 'key': 1, 'projectcd': 1, 'key_subnr': 1, 'artefactsoort': 1}


# ============================================================
# Bronnen en filters
# ============================================================

def getStagingBronnen(categorie):
    """Retourneer waar de staging-documenten van een categorie staan en hoe ze aan een bestand hangen.

    Args:
        categorie: invoercategorie, bijv. 'projecten' of 'afbeeldingen'

    Returns:
        Lijst met dicts {'collectie', 'veld', 'single_store_veld'}. ``veld`` is het
        veld in de staging-collectie met het pad (None: de hele collectie komt uit
        dat ene bestand); ``single_store_veld`` is het veld in Single_Store met het pad.
    """
    for cat, _, coll in bronbestanden.getMdbCategorieen():
        if cat == categorie:
            return [{'collectie': coll, 'veld': 'mdbfile', 'single_store_veld': 'brondata.mdbfile'}]
    if categorie == bronbestanden.CAT_EXTRA_PROJECTEN:
        return [{'collectie': config.COLL_STAGING_PROJECTENLIJST, 'veld': 'mdbfile', 'single_store_veld': 'brondata.mdbfile'}]
    if categorie == bronbestanden.CAT_REFERENTIETABELLEN:
        return [{'collectie': config.COLL_STAGING_REFERENTIETABELLEN, 'veld': None, 'single_store_veld': None}]
    if categorie == bronbestanden.CAT_AFBEELDINGEN:
        return [{'collectie': config.COLL_PLAATJES, 'veld': 'fullFileName', 'single_store_veld': 'fullFileName'}]
    return []


def inBatches(waarden, grootte=BATCH_GROOTTE):
    """Splits een lijst in batches (voor $in-filters die anders te groot worden)."""
    waarden = list(waarden)
    for i in range(0, len(waarden), grootte):
        yield waarden[i:i + grootte]


def maakPadFilter(veld, paden):
    """Filter op documenten waarvan ``veld`` een van de paden bevat; zonder veld: alle documenten."""
    return {veld: {'$in': list(paden)}} if veld else {}


def maakIdFilter(ids):
    """Filter op documenten met een van de opgegeven _id's."""
    return {'_id': {'$in': list(ids)}}


def bepaalTeOpruimenPaden(run):
    """Bepaal per categorie welke bestanden opgeruimd moeten worden.

    Gewijzigde en verwijderde bestanden altijd. Nieuwe bestanden ook, tenzij de
    registratie leeg was: zo levert een herhaalde run na een mislukte run
    (waarin een nieuw bestand al deels was ingelezen) geen dubbelingen op.

    Returns:
        Dict categorie -> gesorteerde lijst met paden
    """
    statussen = [verwerkingsrun.STATUS_GEWIJZIGD, verwerkingsrun.STATUS_VERWIJDERD]
    if not run.get('registratie_leeg'):
        statussen.append(verwerkingsrun.STATUS_NIEUW)

    categorieen = set()
    for status in statussen:
        categorieen.update((run.get(status) or {}).keys())
    resultaat = {}
    for categorie in sorted(categorieen):
        paden = verwerkingsrun.getDeltaPaden(categorie, statussen=statussen, run=run)
        if paden:
            resultaat[categorie] = paden
    return resultaat


def maakVerwijderdeKeyEntry(doc):
    """Maak een entry voor verwijderde_keys uit een Single_Store-document."""
    entry = {'key': doc.get('key'), 'projectcd': doc.get('projectcd')}
    if doc.get('soort') == 'Artefact':
        entry['key_subnr'] = doc.get('key_subnr')
        entry['artefactsoort'] = doc.get('artefactsoort')
    return entry


def heeftSleutel(doc):
    """Bepaal of een Single_Store-document een sleutel heeft om later opnieuw samen te voegen.

    Artefacten worden samengevoegd op key_subnr (+ artefactsoort) en hebben in
    Single_Store vaak key: null; voor hen telt key_subnr.
    """
    if doc.get('key') is not None:
        return True
    return doc.get('soort') == 'Artefact' and doc.get('key_subnr') is not None


def verzamelSleutels(docs):
    """Verzamel per soort de sleutels en de geraakte projecten van Single_Store-documenten.

    Documenten zonder sleutel (nog niet door Transform 3 gegaan, of soorten
    zonder key zoals Fotobeschrijving) leveren geen entry op, maar hun
    projectcode telt wel mee.

    Returns:
        Tuple (verwijderde_keys: dict soort -> lijst entries, geraakte_projecten: set)
    """
    per_soort = {}
    projecten = set()
    for doc in docs:
        if doc.get('projectcd') is not None:
            projecten.add(str(doc['projectcd']))
        if not heeftSleutel(doc):
            continue
        soort = doc.get('soort') if doc.get('soort') else 'Onbekend'
        per_soort.setdefault(soort, []).append(maakVerwijderdeKeyEntry(doc))
    return verwerkingsrun.voegVerwijderdeKeysSamen({}, per_soort), projecten


def isGridfsId(waarde):
    """Bepaal of een waarde een GridFS-ObjectId is (oude image_util) en geen mediapad."""
    return isinstance(waarde, ObjectId) or (isinstance(waarde, str) and ObjectId.is_valid(waarde))


def bepaalMediaPad(file_id):
    """Leid het pad van een kopie in AIRFLOW_OUTPUT_MEDIA af uit een imageID-waarde.

    Zelfde afleiding als image_util.putImageInGrid. Paden die buiten
    AIRFLOW_OUTPUT_MEDIA uitkomen worden genegeerd.

    Returns:
        Absoluut pad, of None als er geen pad af te leiden is
    """
    if not isinstance(file_id, str) or not file_id.strip('/\\'):
        return None
    basis = os.path.realpath(str(config.AIRFLOW_OUTPUT_MEDIA))
    pad = os.path.realpath(os.path.join(basis, file_id.lstrip('/\\')))
    if not pad.startswith(basis + os.sep):
        return None
    return pad


def verzamelImageIds(plaatjes_docs):
    """Verzamel alle waarden van de image-id-velden van Plaatjes-documenten."""
    waarden = set()
    for doc in plaatjes_docs:
        for veld in IMAGE_ID_VELDEN:
            waarde = doc.get(veld)
            if waarde:
                waarden.add(str(waarde))
    return waarden


# ============================================================
# Database-toegang (vervangbaar in tests)
# ============================================================

def _getClient():
    """Maak een MongoClient op basis van de configuratie."""
    return pymongo.MongoClient(str(config.MONGO_URI))


def _getGridFS(filesdb):
    """Retourneer de GridFS-store in de files-database."""
    return gridfs.GridFS(filesdb)


def _zoekInBatches(col, veld, waarden, projectie):
    """Zoek documenten met veld in waarden, in batches; retourneert een lijst documenten."""
    docs = []
    for batch in inBatches(waarden):
        docs.extend(col.find({veld: {'$in': batch}}, projectie))
    return docs


def _verwijderInBatches(col, veld, waarden):
    """Verwijder documenten met veld in waarden, in batches; retourneert het aantal."""
    aantal = 0
    for batch in inBatches(waarden):
        aantal += col.delete_many({veld: {'$in': batch}}).deleted_count
    return aantal


def _maakIndexen(client, te_opruimen):
    """Maak indexen op de padvelden zodat opzoeken en tellen niet de hele collectie hoeft te scannen."""
    stagingdb = client[str(config.DB_STAGING)]
    analysecol = client[str(config.DB_ANALYSE)][config.COLL_ANALYSE]
    for categorie in te_opruimen:
        for bron in getStagingBronnen(categorie):
            if bron['veld']:
                stagingdb[bron['collectie']].create_index([(bron['veld'], pymongo.ASCENDING)])
            if bron['single_store_veld']:
                analysecol.create_index([(bron['single_store_veld'], pymongo.ASCENDING)])


# ============================================================
# Taak
# ============================================================

def verzamelTeVerwijderen(client, te_opruimen):
    """Fase 1: verzamel per categorie de staging- en Single_Store-documenten die weg moeten.

    Args:
        client: MongoClient
        te_opruimen: dict categorie -> paden (uit bepaalTeOpruimenPaden)

    Returns:
        Lijst met stappen (dicts) met categorie, collectie, paden, staging_docs en single_store_docs
    """
    stagingdb = client[str(config.DB_STAGING)]
    analysecol = client[str(config.DB_ANALYSE)][config.COLL_ANALYSE]

    plan = []
    for categorie, paden in te_opruimen.items():
        for bron in getStagingBronnen(categorie):
            stap = dict(bron, categorie=categorie, paden=paden)
            col = stagingdb[bron['collectie']]
            projectie = {veld: 1 for veld in ['_id'] + (IMAGE_ID_VELDEN if categorie == bronbestanden.CAT_AFBEELDINGEN else [])}

            if bron['veld']:
                stap['staging_docs'] = _zoekInBatches(col, bron['veld'], paden, projectie)
            else:
                stap['staging_docs'] = list(col.find(maakPadFilter(None, paden), projectie))
            staging_ids = [doc['_id'] for doc in stap['staging_docs']]

            single_store = {}
            for doc in _zoekInBatches(analysecol, '_id', staging_ids, SLEUTEL_VELDEN):
                single_store[doc['_id']] = doc
            if bron['single_store_veld']:
                for doc in _zoekInBatches(analysecol, bron['single_store_veld'], paden, SLEUTEL_VELDEN):
                    single_store[doc['_id']] = doc
            stap['single_store_docs'] = list(single_store.values())

            logger.info(f"{categorie} / {bron['collectie']}: {len(paden)} bestand(en), "
                        f"{len(staging_ids)} staging-documenten, {len(single_store)} Single_Store-documenten.")
            plan.append(stap)
    return plan


def verwijderMedia(client, plaatjes_docs):
    """Verwijder de GridFS-bestanden en mediakopieën van verwijderde Plaatjes-documenten.

    Bestanden waarnaar een overgebleven Plaatjes-document nog verwijst blijven staan.

    Returns:
        Tuple (aantal GridFS-bestanden, aantal mediabestanden) dat is verwijderd
    """
    kandidaten = verzamelImageIds(plaatjes_docs)
    if not kandidaten:
        return 0, 0

    plaatjes = client[str(config.DB_STAGING)][config.COLL_PLAATJES]
    nog_gebruikt = set()
    for veld in IMAGE_ID_VELDEN:
        for doc in _zoekInBatches(plaatjes, veld, sorted(kandidaten), {veld: 1}):
            nog_gebruikt.add(str(doc.get(veld)))

    fs = None
    aantal_gridfs = 0
    aantal_media = 0
    for waarde in sorted(kandidaten - nog_gebruikt):
        if isGridfsId(waarde):
            fs = fs if fs else _getGridFS(client[str(config.DB_FILES)])
            if fs.exists(ObjectId(waarde)):
                fs.delete(ObjectId(waarde))
                aantal_gridfs += 1
        else:
            pad = bepaalMediaPad(waarde)
            if pad and os.path.isfile(pad):
                os.remove(pad)
                aantal_media += 1
    return aantal_gridfs, aantal_media


def verwijderVolgensPlan(client, plan):
    """Fase 2: verwijder de verzamelde documenten uit Single_Store, Single_Store_Clean, staging en de bestandsopslag.

    Returns:
        Dict categorie -> tellingen
    """
    stagingdb = client[str(config.DB_STAGING)]
    analysedb = client[str(config.DB_ANALYSE)]
    filesdb = client[str(config.DB_FILES)]

    tellingen = {}
    for stap in plan:
        staging_ids = [doc['_id'] for doc in stap['staging_docs']]
        single_store_ids = [doc['_id'] for doc in stap['single_store_docs']]
        clean_ids = list(dict.fromkeys(single_store_ids + staging_ids))

        telling = tellingen.setdefault(stap['categorie'], {})
        telling[stap['collectie']] = telling.get(stap['collectie'], 0) + _verwijderInBatches(stagingdb[stap['collectie']], '_id', staging_ids)
        telling['single_store'] = telling.get('single_store', 0) + _verwijderInBatches(analysedb[config.COLL_ANALYSE], '_id', single_store_ids)
        telling['single_store_clean'] = telling.get('single_store_clean', 0) + _verwijderInBatches(analysedb[config.COLL_ANALYSE_CLEAN], '_id', clean_ids)

        if stap['categorie'] == bronbestanden.CAT_AFBEELDINGEN:
            telling['filenames'] = _verwijderInBatches(filesdb[config.COLL_FILENAMES], 'filename', stap['paden'])
            telling['gridfs'], telling['media'] = verwijderMedia(client, stap['staging_docs'])

        logger.info(f"Opgeruimd voor {stap['categorie']}: {telling}")
    return tellingen


def verwijderOudeRecords():
    """Taak Opruimen_Oude_Records: ruim de records op van gewijzigde en verwijderde bronbestanden.

    De sleutels en projectcodes van de verwijderde Single_Store-documenten
    worden in het run-document bewaard (verwijderde_keys, geraakte_projecten)
    vóórdat er iets wordt verwijderd, zodat latere stappen de geraakte
    entiteiten opnieuw kunnen samenstellen.

    Returns:
        Dict met de tellingen per categorie
    """
    run = verwerkingsrun.huidigeRun()
    run_id = run['run_id']
    te_opruimen = bepaalTeOpruimenPaden(run)
    if not te_opruimen:
        logger.info(f"Run {run_id}: geen gewijzigde of verwijderde bronbestanden — niets op te ruimen.")
        verwerkingsrun.werkRunBij({'tellingen.opruimen': {}}, run_id=run_id)
        return {}

    myclient = _getClient()
    try:
        _maakIndexen(myclient, te_opruimen)
        plan = verzamelTeVerwijderen(myclient, te_opruimen)

        # Eerst de sleutels bewaren, dan pas verwijderen
        alle_docs = [doc for stap in plan for doc in stap['single_store_docs']]
        verwijderde_keys, projecten = verzamelSleutels(alle_docs)
        verwerkingsrun.werkRunBij({
            'verwijderde_keys': verwerkingsrun.voegVerwijderdeKeysSamen(run.get('verwijderde_keys'), verwijderde_keys),
            'geraakte_projecten': sorted(set(run.get('geraakte_projecten') or []) | projecten),
        }, run_id=run_id)

        tellingen = verwijderVolgensPlan(myclient, plan)
        verwerkingsrun.werkRunBij({'tellingen.opruimen': tellingen}, run_id=run_id)
    finally:
        myclient.close()

    logger.info(f"Run {run_id}: oude records opgeruimd: {tellingen}; geraakte projecten: {sorted(projecten)}.")
    return tellingen
