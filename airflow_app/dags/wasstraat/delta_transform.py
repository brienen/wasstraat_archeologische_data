"""Hulpfuncties voor de delta-varianten van de transformaties (incrementeel laden, fase 2, issue 61).

Zie docs/componenten/incrementeel-laden.md voor het ontwerp. De bestaande
transformatiefuncties (harmonize, enhanceAllAttributes, setReferenceKeys,
moveSoort, mergeSoort, mergeMissing, setPrimaryKeys enz.) hebben een optionele
parameter ``incrementeel`` (``stabiel`` bij setPrimaryKeys); zonder die
parameter werken ze precies zoals in de volledige cyclus. Met de parameter
lezen ze het run-document van de actieve verwerkingsrun en gebruiken ze de
functies uit deze module om zich te beperken tot de delta:

- Transform 1 harmoniseert alleen staging-documenten uit nieuwe en gewijzigde
  bronbestanden en zet op elk geschreven Single_Store-document het veld
  ``delta_run`` met het run-id.
- Transform 2 en 3 werken alleen op documenten met ``delta_run``; projectbrede
  stappen alleen op de geraakte projecten.
- Transform 5 verplaatst de delta-documenten, voegt de geraakte sleutels
  opnieuw samen (sleutels van delta-documenten plus ``verwijderde_keys``),
  verwijdert samengevoegde documenten waarvan de sleutel is verdwenen en
  genereert ontbrekende entiteiten opnieuw voor de geraakte projecten.
- Transform 4 kent stabiele sleutels toe: een document houdt zijn ID, krijgt
  anders de primary_key uit PostgreSQL (op _id, of op een unieke key) en pas
  als laatste een nieuw nummer boven het bestaande maximum.

Alle documenten die een incrementele run in Single_Store_Clean (opnieuw)
schrijft, hebben ``delta_run`` gelijk aan het run-id van die run.

Fase 3 (upsert-load, loadToDatabase_functions.loadIncrementeel) gebruikt
``leesPgSleutels``, ``bepaalVerdwenenPrimaryKeys`` en ``getArtefactKey`` uit
deze module.
"""
import copy
import math
from collections import Counter

import pymongo
from pymongo import UpdateOne

import shared.config as config
import shared.const as const
import wasstraat.verwerkingsrun as verwerkingsrun
import logging

logger = logging.getLogger("airflow.task")

VELD_DELTA_RUN = 'delta_run'
# Veld dat de merge-pipeline (merge_functions.AGGREGATE_MERGE) aan elk samengevoegd document toevoegt
VELD_SAMENGEVOEGD = 'brondata_count'
PREFIX_GEGENEREERD = 'generated_'
BATCH_GROOTTE = 5000
# Scheidingsteken in de samengestelde sleutel van een artefact zonder key (key_subnr|artefactsoort)
SCHEIDING_ARTEFACT_KEY = '|'
# Projectbrede vlag (setAndVondstUniqueInProject): vondstnummers komen in meer dan één put voor
VELD_VONDSTKEY_VLAG = 'vondstkey_met_putnr'
# Soorten waarvan een sleutel in meta.py (key of key_vondst via aggr_key_vondst) van die vlag afhangt
SOORTEN_MET_VONDSTKEY_VLAG = ['Spoor', 'Vulling', 'Artefact', 'Monster', 'Vondst']


# ============================================================
# Algemeen
# ============================================================

def _getClient():
    """Maak een MongoClient op basis van de configuratie (vervangbaar in tests)."""
    return pymongo.MongoClient(str(config.MONGO_URI))


def inBatches(waarden, grootte=BATCH_GROOTTE):
    """Splits een lijst in batches (voor $in-filters en bulk-operaties die anders te groot worden)."""
    waarden = list(waarden)
    for i in range(0, len(waarden), grootte):
        yield waarden[i:i + grootte]


def zoekOpPaden(col, veld, paden, projectie=None):
    """Zoek documenten waarvan ``veld`` een van de paden bevat, in batches.

    Args:
        col: MongoDB-collectie
        veld: veld met het pad (bijv. 'fullFileName')
        paden: lijst met paden
        projectie: optionele projectie

    Returns:
        Generator met documenten
    """
    for batch in inBatches(paden):
        for doc in col.find({veld: {'$in': batch}}, projectie):
            yield doc


def getSleutelveld(soort):
    """Retourneer het veld waarop een soort wordt samengevoegd (Artefact: key_subnr, anders key)."""
    return 'key_subnr' if soort == 'Artefact' else 'key'


def isLeeg(waarde):
    """Bepaal of een waarde ontbreekt: None, NaN of lege tekst."""
    if waarde is None:
        return True
    if isinstance(waarde, float) and math.isnan(waarde):
        return True
    return isinstance(waarde, str) and waarde.strip() == ''


def getArtefactKey(doc):
    """Retourneer de key waarmee een artefact in PostgreSQL wordt teruggevonden.

    Artefacten worden samengevoegd op ``key_subnr`` en ``artefactsoort``
    (merge_functions.mergeSoort) en hebben meestal geen ``key`` (die is alleen
    gevuld als ``artefactnr`` bekend is). Zonder key is de sleutel daarom de
    samengestelde sleutel ``key_subnr|artefactsoort``. De load vult daarmee de
    kolom ``key`` van Def_Artefact (volledige en incrementele cyclus), zodat
    setStabielePrimaryKeys een opnieuw ingelezen artefact op die sleutel
    terugvindt.

    Args:
        doc: artefact-document (met key, key_subnr en artefactsoort)

    Returns:
        De key, de samengestelde sleutel, of None als ook key_subnr leeg is
    """
    if not isLeeg(doc.get('key')):
        return doc['key']
    key_subnr = doc.get('key_subnr')
    if isLeeg(key_subnr):
        return None
    artefactsoort = doc.get('artefactsoort')
    return f"{key_subnr}{SCHEIDING_ARTEFACT_KEY}{'' if isLeeg(artefactsoort) else artefactsoort}"


def getCleanSoortFilter(soort):
    """Retourneer het filter op Single_Store_Clean voor de samengevoegde documenten van een soort.

    Tekening en Rapport (en Foto) staan in Single_Store_Clean als soort 'Bestand'
    met het veld bestandsoort_XX.
    """
    if soort in const.BESTANDSOORTEN:
        return {'soort': 'Bestand', 'bestandsoort_XX': soort}
    return {'soort': soort}


# ============================================================
# Pipelines
# ============================================================

def voegToeAanEersteMatch(pipeline, extra):
    """Voeg voorwaarden toe aan de eerste $match van een pipeline, zonder de pipeline zelf te wijzigen.

    Begint de pipeline niet met een $match, dan komt er een nieuwe $match vooraan.
    Botst een voorwaarde met een bestaande, dan worden beide met $and gecombineerd.

    Args:
        pipeline: lijst met aggregatiefasen (wordt niet gewijzigd)
        extra: dict met extra voorwaarden

    Returns:
        Nieuwe pipeline (diepe kopie)
    """
    nieuw = copy.deepcopy(pipeline)
    if nieuw and '$match' in nieuw[0]:
        bestaand = nieuw[0]['$match']
        if any(sleutel in bestaand for sleutel in extra):
            nieuw[0]['$match'] = {'$and': [bestaand, copy.deepcopy(extra)]}
        else:
            nieuw[0]['$match'] = dict(bestaand, **copy.deepcopy(extra))
    else:
        nieuw.insert(0, {'$match': copy.deepcopy(extra)})
    return nieuw


def voegMatchVooraanToe(pipeline, extra):
    """Zet een extra $match vooraan in een pipeline, zonder de pipeline zelf te wijzigen.

    Returns:
        Nieuwe pipeline (diepe kopie)
    """
    nieuw = copy.deepcopy(pipeline)
    nieuw.insert(0, {'$match': copy.deepcopy(extra)})
    return nieuw


def getMergeIndex(pipeline):
    """Retourneer de index van de (laatste) $merge-fase, of None als de pipeline niets schrijft."""
    for i in range(len(pipeline) - 1, -1, -1):
        if '$merge' in pipeline[i]:
            return i
    return None


def voegDeltaRunToeVoorMerge(pipeline, run_id):
    """Zet ``{$addFields: {delta_run: run_id}}`` vlak vóór de $merge, zonder de pipeline zelf te wijzigen.

    Returns:
        Nieuwe pipeline (diepe kopie), of None als de pipeline geen $merge heeft
    """
    idx = getMergeIndex(pipeline)
    if idx is None:
        return None
    nieuw = copy.deepcopy(pipeline)
    nieuw.insert(idx, {'$addFields': {VELD_DELTA_RUN: run_id}})
    return nieuw


def maakDeltaHarmonizePipeline(pipeline, padfilter, run_id):
    """Bouw de delta-variant van een harmonisatie-pipeline.

    Vooraan komt een extra $match op het padveld van de staging-collectie (bij
    een leeg filter, zoals voor de ABR-referentietabellen, niet); vlak vóór de
    $merge komt ``$addFields {delta_run}``. De gecachete of in meta.py
    vastgelegde pipeline wordt niet gewijzigd.

    Args:
        pipeline: harmonisatie-pipeline
        padfilter: filter op de staging-collectie (uit getStagingDeltaFilter)
        run_id: id van de verwerkingsrun

    Returns:
        Nieuwe pipeline, of None als de pipeline niets schrijft (geen $merge)
    """
    nieuw = voegDeltaRunToeVoorMerge(pipeline, run_id)
    if nieuw is None:
        return None
    if padfilter:
        nieuw.insert(0, {'$match': copy.deepcopy(padfilter)})
    return nieuw


def maakDeltaMergePipeline(pipeline, sleutelveld, sleutels, run_id):
    """Bouw de delta-variant van een merge-pipeline (Transform 5).

    De eerste $match (op soort) krijgt een voorwaarde op de geraakte sleutels;
    vlak vóór de $merge komt ``$addFields {delta_run}``, zodat herschreven
    documenten herkenbaar zijn.

    Args:
        pipeline: merge-pipeline (uit merge_functions.getMergeAggregate)
        sleutelveld: 'key' of 'key_subnr'
        sleutels: lijst met geraakte sleutels
        run_id: id van de verwerkingsrun

    Returns:
        Nieuwe pipeline
    """
    nieuw = voegToeAanEersteMatch(pipeline, {sleutelveld: {'$in': list(sleutels)}})
    return voegDeltaRunToeVoorMerge(nieuw, run_id)


def maakProjectMatchPipeline(pipeline, projecten):
    """Zet een $match op de geraakte projecten vooraan in een pipeline (generate missing)."""
    return voegMatchVooraanToe(pipeline, {'projectcd': {'$in': list(projecten)}})


# ============================================================
# Transform 1: delta op de staging-collecties
# ============================================================

def getCategorieenMetStaging():
    """Retourneer alle invoercategorieën die documenten in een staging-collectie opleveren."""
    import wasstraat.bronbestanden as bronbestanden
    return bronbestanden.getMdbCategorieNamen() + [
        bronbestanden.CAT_EXTRA_PROJECTEN, bronbestanden.CAT_REFERENTIETABELLEN, bronbestanden.CAT_AFBEELDINGEN]


def getStagingDeltaFilter(collectie, run):
    """Bepaal het filter op een staging-collectie voor de nieuwe en gewijzigde bronbestanden van de run.

    De projectenlijst-collectie krijgt ook de paden van de extra projecten. De
    referentietabellen-collectie heeft geen padveld: de hele collectie komt uit
    het ABR-bestand.

    Args:
        collectie: naam van de staging-collectie
        run: run-document

    Returns:
        None als er voor deze collectie niets te doen is; {} als de hele
        collectie opnieuw geharmoniseerd moet worden (ABR-bestand in de delta);
        anders bijv. ``{'mdbfile': {'$in': [...]}}``
    """
    import wasstraat.opruimen as opruimen

    paden_per_veld = {}
    hele_collectie = False
    for categorie in getCategorieenMetStaging():
        for bron in opruimen.getStagingBronnen(categorie):
            if bron['collectie'] != collectie:
                continue
            paden = verwerkingsrun.getDeltaPaden(categorie, run=run)
            if not paden:
                continue
            if bron['veld'] is None:
                hele_collectie = True
            else:
                paden_per_veld.setdefault(bron['veld'], set()).update(paden)

    if hele_collectie:
        return {}
    if not paden_per_veld:
        return None
    filters = [{veld: {'$in': sorted(paden)}} for veld, paden in sorted(paden_per_veld.items())]
    return filters[0] if len(filters) == 1 else {'$or': filters}


def zorgVoorDeltaIndex(analyseCol):
    """Maak een (sparse) index op delta_run in Single_Store, zodat de delta-filters niet de hele collectie scannen."""
    analyseCol.create_index([(VELD_DELTA_RUN, pymongo.ASCENDING)], name='idx_delta_run', sparse=True)


def getDeltaProjecten(analyseCol, run_id):
    """Retourneer de projectcodes van de Single_Store-documenten die in deze run (opnieuw) zijn geharmoniseerd.

    Returns:
        Set met projectcodes (als tekst)
    """
    projecten = set()
    pipeline = [{'$match': {VELD_DELTA_RUN: run_id}}, {'$group': {'_id': '$projectcd', 'aantal': {'$sum': 1}}}]
    for rij in analyseCol.aggregate(pipeline):
        if rij.get('_id') is not None:
            projecten.add(str(rij['_id']))
    return projecten


def getGeraakteProjecten(run=None, analyseCol=None):
    """Retourneer de geraakte projecten: die uit het run-document plus die van de delta-documenten.

    Args:
        run: run-document; standaard de actieve run
        analyseCol: Single_Store-collectie; standaard een nieuwe verbinding

    Returns:
        Gesorteerde lijst met projectcodes
    """
    run = run if run else verwerkingsrun.huidigeRun()
    projecten = set(run.get('geraakte_projecten') or [])
    if analyseCol is not None:
        return sorted(projecten | getDeltaProjecten(analyseCol, run['run_id']))
    client = _getClient()
    try:
        col = client[str(config.DB_ANALYSE)][config.COLL_ANALYSE]
        return sorted(projecten | getDeltaProjecten(col, run['run_id']))
    finally:
        client.close()


def getVondstkeyProjecten(soort, run):
    """Retourneer de geraakte projecten waarvan alle documenten van een soort opnieuw verwerkt worden.

    De vlag vondstkey_met_putnr geldt per project en wordt bij een incrementele
    run voor de geraakte projecten opnieuw bepaald. Verandert hij, dan
    veranderen ook de sleutels (key van Vondst, key_vondst van Spoor, Vulling,
    Artefact en Monster) van documenten uit bronbestanden die niet in de delta
    zitten. Daarom berekenen Transform 3 en 5 die soorten voor de hele geraakte
    projecten opnieuw, niet alleen voor de delta-documenten.

    Args:
        soort: soort
        run: run-document

    Returns:
        Gesorteerde lijst met projectcodes; leeg als de sleutels van de soort
        niet van de vlag afhangen of als er geen geraakte projecten zijn
    """
    if soort not in SOORTEN_MET_VONDSTKEY_VLAG:
        return []
    return getGeraakteProjecten(run)


def getDeltaOfProjectFilter(soort, run, projecten=None):
    """Bepaal welke Single_Store-documenten van een soort Transform 3 (sleutels) en 5 (verplaatsen) opnieuw verwerken.

    Dat zijn de documenten met delta_run van deze run en, voor de soorten
    waarvan de sleutels van de vlag vondstkey_met_putnr afhangen, ook alle
    documenten van de geraakte projecten (zie getVondstkeyProjecten).

    Args:
        soort: soort
        run: run-document
        projecten: uitkomst van getVondstkeyProjecten, als die al bepaald is

    Returns:
        Filter, bijv. ``{'delta_run': run_id}`` of
        ``{'$or': [{'delta_run': run_id}, {'projectcd': {'$in': [...]}}]}``
    """
    run_id = run['run_id']
    if projecten is None:
        projecten = getVondstkeyProjecten(soort, run)
    if not projecten:
        return {VELD_DELTA_RUN: run_id}
    return {'$or': [{VELD_DELTA_RUN: run_id}, {'projectcd': {'$in': projecten}}]}


def werkGeraakteProjectenBij():
    """Taak Werk_Geraakte_Projecten_Bij: voeg de projectcodes van de delta-documenten toe aan het run-document.

    Draait aan het eind van Transform 1 en nogmaals aan het eind van Transform 2
    (die de projectcode van foto's en via het gemeenteprofiel ook andere
    projectcodes kan aanpassen). Maakt ook de index op delta_run aan.

    Returns:
        Gesorteerde lijst met geraakte projecten
    """
    run = verwerkingsrun.huidigeRun()
    run_id = run['run_id']
    client = _getClient()
    try:
        col = client[str(config.DB_ANALYSE)][config.COLL_ANALYSE]
        zorgVoorDeltaIndex(col)
        delta_projecten = getDeltaProjecten(col, run_id)
        aantal = col.count_documents({VELD_DELTA_RUN: run_id})
    finally:
        client.close()

    geraakte = sorted(set(run.get('geraakte_projecten') or []) | delta_projecten)
    verwerkingsrun.werkRunBij({'geraakte_projecten': geraakte, 'tellingen.transform.delta_documenten': aantal}, run_id=run_id)
    logger.info(f"Run {run_id}: {aantal} delta-documenten in Single_Store; geraakte projecten: {geraakte}.")
    return geraakte


# ============================================================
# Transform 5: geraakte sleutels en opruimen in Single_Store_Clean
# ============================================================

def bepaalGeraakteSleutels(soort, analyseCol, run, cleanCol=None):
    """Bepaal de sleutels van een Merge-soort die opnieuw samengevoegd moeten worden.

    Dat zijn de sleutels van de Single_Store-documenten van die soort met
    delta_run van deze run, plus de sleutels uit verwijderde_keys[soort] (van
    documenten die Opruimen_Oude_Records heeft verwijderd). Voor Artefact is
    dat key_subnr (artefacten hebben in Single_Store vaak key: null). Documenten
    zonder sleutel tellen niet mee, net als bij het opruimen.

    Voor de soorten waarvan de sleutels van de vlag vondstkey_met_putnr afhangen
    (zie getVondstkeyProjecten) komen daar de sleutels van alle documenten van
    de geraakte projecten bij: in Single_Store (de nieuwe sleutels) en, als
    cleanCol is meegegeven, de samengevoegde documenten in Single_Store_Clean
    (de oude sleutels, zodat verwijderVerdwenenSleutels een vervallen sleutel
    opruimt).

    Args:
        soort: Merge-soort (bijv. 'Vondst', 'Artefact', 'Tekening')
        analyseCol: Single_Store-collectie
        run: run-document
        cleanCol: Single_Store_Clean-collectie (optioneel)

    Returns:
        Gesorteerde lijst met sleutels
    """
    veld = getSleutelveld(soort)
    sleutels = set()
    projecten = getVondstkeyProjecten(soort, run)
    for doc in analyseCol.find(dict({'soort': soort}, **getDeltaOfProjectFilter(soort, run, projecten)), {veld: 1}):
        if doc.get(veld) is not None:
            sleutels.add(doc[veld])
    if projecten and cleanCol is not None:
        filt = dict(getCleanSoortFilter(soort), **{'projectcd': {'$in': projecten}, VELD_SAMENGEVOEGD: {'$exists': True}})
        for doc in cleanCol.find(filt, {veld: 1}):
            if doc.get(veld) is not None:
                sleutels.add(doc[veld])
    for entry in (run.get('verwijderde_keys') or {}).get(soort, []):
        if entry.get(veld) is not None:
            sleutels.add(entry[veld])
    return sorted(sleutels, key=str)


def verwijderVerdwenenSleutels(soort, cleanCol, sleutels, run_id):
    """Verwijder samengevoegde documenten van een soort met een geraakte sleutel die deze run niet opnieuw heeft geschreven.

    Na de delta-merge heeft elk (opnieuw) samengevoegd document delta_run gelijk
    aan het run-id. Een samengevoegd document met een geraakte sleutel zonder die
    markering is verouderd: er bestaat geen Single_Store-document meer met die
    sleutel, of het document is opnieuw samengevoegd onder een ander ``_id``.
    De merge-pipeline neemt namelijk het ``_id`` over van het laatste
    brondocument in de groep (``$mergeObjects`` op ``$$ROOT``), zodat een
    gewijzigde groep een nieuw document oplevert in plaats van het oude te
    vervangen. Samengevoegde documenten zijn herkenbaar aan ``brondata_count``;
    verplaatste documenten (Artefact is ook Move-soort), gegenereerde documenten
    en foto's hebben dat veld niet en blijven altijd staan.

    Args:
        soort: Merge-soort
        cleanCol: Single_Store_Clean-collectie
        sleutels: geraakte sleutels
        run_id: id van de verwerkingsrun

    Returns:
        Aantal verwijderde documenten
    """
    veld = getSleutelveld(soort)
    te_verwijderen = []
    for batch in inBatches(sleutels):
        filt = dict(getCleanSoortFilter(soort), **{veld: {'$in': batch}, VELD_SAMENGEVOEGD: {'$exists': True}})
        for doc in cleanCol.find(filt, {'_id': 1, VELD_DELTA_RUN: 1}):
            if doc.get(VELD_DELTA_RUN) != run_id:
                te_verwijderen.append(doc['_id'])

    aantal = 0
    for batch in inBatches(te_verwijderen):
        aantal += cleanCol.delete_many({'_id': {'$in': batch}}).deleted_count
    return aantal


def verwijderGegenereerdeDocumenten(soort, cleanCol, projecten):
    """Verwijder de gegenereerde documenten (brondata.table begint met 'generated_') van een soort in de geraakte projecten.

    Returns:
        Aantal verwijderde documenten
    """
    filt = {'soort': soort, 'projectcd': {'$in': list(projecten)},
            'brondata.table': {'$regex': '^' + PREFIX_GEGENEREERD}}
    return cleanCol.delete_many(filt).deleted_count


def getFotoDeltaFilter(analyseCol, run):
    """Bepaal welke Foto-documenten mergeFotoinfo bij een incrementele run opnieuw samenvoegt.

    Dat zijn foto's met delta_run, foto's in een geraakt project (bijv. omdat
    de fotobeschrijvingen in de projectdatabase zijn gewijzigd) en foto's
    waarvan de bestandsnaam voorkomt in een gewijzigde fotolijst.

    Args:
        analyseCol: Single_Store-collectie
        run: run-document

    Returns:
        Filter op Single_Store, of None als er geen foto's geraakt zijn
    """
    run_id = run['run_id']
    projecten = getGeraakteProjecten(run, analyseCol)
    bestandsnamen = sorted({doc['bestandsnaam'] for doc in analyseCol.find(
        {'soort': 'Fotokoppel', VELD_DELTA_RUN: run_id}, {'bestandsnaam': 1}) if doc.get('bestandsnaam')})
    aantal_delta = analyseCol.count_documents({'soort': 'Foto', VELD_DELTA_RUN: run_id})
    if not projecten and not bestandsnamen and aantal_delta == 0:
        return None

    voorwaarden = [{VELD_DELTA_RUN: run_id}]
    if projecten:
        voorwaarden.append({'projectcd': {'$in': projecten}})
    if bestandsnamen:
        voorwaarden.append({'fileName': {'$in': bestandsnamen}})
    return {'soort': 'Foto', '$or': voorwaarden}


def werkTellingBij(pad, waarde):
    """Schrijf een telling naar het run-document van de actieve run (als die er is)."""
    run = verwerkingsrun.huidigeRun(verplicht=False)
    if run is None:
        return
    verwerkingsrun.werkRunBij({f'tellingen.transform.{pad}': waarde}, run_id=run['run_id'])


# ============================================================
# Transform 4: stabiele sleutels
# ============================================================

def getTabelVoorSoort(soort):
    """Retourneer de PostgreSQL-tabel van een soort, of None als de soort geen tabel heeft.

    Foto, Tekening, Rapport en Bestand staan samen in Def_Bestand. Soorten als
    Fotobeschrijving en Fotokoppel worden niet geladen en hebben geen tabel.
    """
    from wasstraat.loadToDatabase_functions import LOAD_TABELLEN
    if soort in const.BESTANDSOORTEN or soort == 'Bestand':
        return 'Def_Bestand'
    tabel = f'Def_{soort}'
    return tabel if tabel in LOAD_TABELLEN else None


def leesPgSleutels(tabel, cursor=None):
    """Lees de bestaande toewijzing (_id, key) → primary_key uit een PostgreSQL-tabel.

    Args:
        tabel: tabelnaam, bijv. 'Def_Vondst'
        cursor: optionele psycopg2-cursor. De upsert-load (fase 3) geeft zijn
            eigen cursor mee: die houdt locks op de tabellen vast, zodat een
            tweede verbinding zou blijven wachten. Zonder cursor wordt een
            eigen verbinding geopend en gesloten.

    Returns:
        Lijst met dicts {'primary_key', '_id', 'key'} (kolommen die ontbreken
        worden weggelaten), of None als de tabel (of de kolom primary_key) niet bestaat
    """
    if cursor is not None:
        return _leesPgSleutelsMetCursor(cursor, tabel)

    from wasstraat.loadToDatabase_functions import getPgConnection

    conn = getPgConnection()
    try:
        return _leesPgSleutelsMetCursor(conn.cursor(), tabel)
    finally:
        conn.close()


def _leesPgSleutelsMetCursor(cursor, tabel):
    """Lees (primary_key, _id, key) uit een tabel met een bestaande cursor (zie leesPgSleutels)."""
    cursor.execute("""
        SELECT column_name FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = %s
    """, (tabel,))
    kolommen = {rij[0] for rij in cursor.fetchall()}
    if 'primary_key' not in kolommen:
        return None
    velden = ['primary_key'] + [k for k in ('_id', 'key') if k in kolommen]
    kolomlijst = ', '.join(f'"{veld}"' for veld in velden)
    cursor.execute(f'SELECT {kolomlijst} FROM "{tabel}"')
    return [dict(zip(velden, rij)) for rij in cursor.fetchall()]


def heeftId(doc):
    """Bepaal of een document al een (geldig) ID heeft."""
    waarde = doc.get('ID')
    if waarde is None:
        return False
    try:
        return not math.isnan(float(waarde))
    except (TypeError, ValueError):
        return False


def bepaalStabieleIds(docs, pg_rijen=None):
    """Bepaal stabiele ID's voor de documenten van een soort zonder ID.

    Volgorde per document zonder ID:

    1. de primary_key van de rij in PostgreSQL met dezelfde ``_id`` (tekst van
       het ``_id``). Verplaatste documenten houden het ``_id`` van hun
       staging-document; een samengevoegd document krijgt het ``_id`` van het
       laatste brondocument in zijn groep, dat gelijk blijft zolang de groep
       niet verandert;
    2. anders de primary_key van de rij met dezelfde ``key``, maar alleen als
       die key precies één keer in de tabel voorkomt (Move-soorten zoals
       Standplaats hebben dubbele keys);
    3. anders een nieuw nummer, oplopend vanaf het maximum van de primary_keys
       in PostgreSQL en de ID's in Single_Store_Clean, plus één.

    Een primary_key die al bij een ander document hoort (een document dat zijn
    ID heeft behouden, of eerder in deze toewijzing) wordt niet nog eens
    uitgedeeld. Documenten met een ID houden dat ID.

    Args:
        docs: documenten van de soort uit Single_Store_Clean (met _id, key en eventueel ID)
        pg_rijen: rijen uit leesPgSleutels, of None als de soort geen tabel heeft

    Returns:
        Tuple (lijst met (_id, ID) voor de documenten zonder ID, dict met tellingen
        'behouden', 'op_id', 'op_key' en 'nieuw')
    """
    in_gebruik = set()
    maximum = -1
    for doc in docs:
        if heeftId(doc):
            waarde = int(doc['ID'])
            in_gebruik.add(waarde)
            maximum = max(maximum, waarde)
    zonder_id = [doc for doc in docs if not heeftId(doc)]

    per_id = {}
    per_key = {}
    aantal_per_key = Counter()
    for rij in pg_rijen or []:
        if rij.get('primary_key') is None:
            continue
        pk = int(rij['primary_key'])
        maximum = max(maximum, pk)
        if rij.get('_id') is not None:
            per_id[str(rij['_id'])] = pk
        if rij.get('key') is not None:
            aantal_per_key[rij['key']] += 1
            per_key[rij['key']] = pk

    tellingen = {'behouden': len(docs) - len(zonder_id), 'op_id': 0, 'op_key': 0, 'nieuw': 0}
    toewijzing = {}

    # 1. Op _id
    for i, doc in enumerate(zonder_id):
        pk = per_id.get(str(doc['_id']))
        if pk is not None and pk not in in_gebruik:
            toewijzing[i] = pk
            in_gebruik.add(pk)
            tellingen['op_id'] += 1

    # 2. Op een unieke key
    for i, doc in enumerate(zonder_id):
        if i in toewijzing:
            continue
        key = doc.get('key')
        if key is None or aantal_per_key.get(key) != 1:
            continue
        pk = per_key[key]
        if pk not in in_gebruik:
            toewijzing[i] = pk
            in_gebruik.add(pk)
            tellingen['op_key'] += 1

    # 3. Nieuwe nummers, in een vaste volgorde
    volgende = maximum + 1
    resterend = sorted((i for i in range(len(zonder_id)) if i not in toewijzing),
                       key=lambda i: (str(zonder_id[i].get('key')), str(zonder_id[i]['_id'])))
    for i in resterend:
        toewijzing[i] = volgende
        volgende += 1
        tellingen['nieuw'] += 1

    return [(zonder_id[i]['_id'], toewijzing[i]) for i in sorted(toewijzing)], tellingen


def bepaalVerdwenenPrimaryKeys(pg_rijen, ids):
    """Retourneer de primary_keys uit PostgreSQL die niet meer als ID in Single_Store_Clean voorkomen.

    De upsert-load (fase 3, loadToDatabase_functions.loadIncrementeel)
    verwijdert deze rijen uit de Def_-tabel.

    Args:
        pg_rijen: rijen uit leesPgSleutels (of None)
        ids: ID's van de documenten van de soort in Single_Store_Clean

    Returns:
        Gesorteerde lijst met primary_keys
    """
    aanwezig = {int(i) for i in ids if i is not None}
    return sorted({int(rij['primary_key']) for rij in (pg_rijen or []) if rij.get('primary_key') is not None} - aanwezig)


def setStabielePrimaryKeys(soort, collection):
    """Ken stabiele ID's toe aan de documenten van een soort in Single_Store_Clean (zie bepaalStabieleIds).

    Alleen documenten zonder ID worden bijgewerkt (alleen het veld ID). Voor
    Artefact wordt op ``getArtefactKey`` vergeleken (key, of anders
    ``key_subnr|artefactsoort``), net als de kolom key in Def_Artefact. Bestaat
    de tabel in PostgreSQL niet en heeft nog geen enkel document een ID (eerste
    run in een lege database), dan retourneert de functie False: de aanroeper
    kent de sleutels dan toe zoals de volledige cyclus.

    Args:
        soort: soort uit SET_KEYS_PIPELINES
        collection: Single_Store_Clean-collectie

    Returns:
        True als de sleutels zijn toegekend, False als de aanroeper het oude gedrag moet volgen
    """
    projectie = {'_id': 1, 'key': 1, 'ID': 1}
    if soort == 'Artefact':
        projectie.update({'key_subnr': 1, 'artefactsoort': 1})
    docs = list(collection.find({'soort': soort}, projectie))
    if soort == 'Artefact':
        # Zelfde sleutel als de load in de kolom key van Def_Artefact zet (alleen in het geheugen)
        for doc in docs:
            doc['key'] = getArtefactKey(doc)
    if not docs:
        logger.warning(f"Geen documenten van soort {soort} gevonden in Single_Store_Clean — geen sleutels toegekend.")
        return True

    tabel = getTabelVoorSoort(soort)
    pg_rijen = leesPgSleutels(tabel) if tabel else None
    if tabel and pg_rijen is None and not any(heeftId(doc) for doc in docs):
        logger.info(f"Tabel {tabel} bestaat niet en geen enkel document van soort {soort} heeft een ID — "
                    f"sleutels worden toegekend zoals in de volledige cyclus.")
        return False

    toewijzingen, tellingen = bepaalStabieleIds(docs, pg_rijen)
    for batch in inBatches(toewijzingen):
        collection.bulk_write([UpdateOne({'_id': _id}, {'$set': {'ID': nieuw_id}}) for _id, nieuw_id in batch])

    ids = [doc['ID'] for doc in docs if heeftId(doc)] + [nieuw_id for _, nieuw_id in toewijzingen]
    tellingen['verdwenen'] = len(bepaalVerdwenenPrimaryKeys(pg_rijen, ids))
    tellingen['tabel'] = tabel
    logger.info(f"Stabiele sleutels voor {soort} (tabel {tabel}): {tellingen}.")
    werkTellingBij(f'primary_keys.{soort}', tellingen)
    return True
