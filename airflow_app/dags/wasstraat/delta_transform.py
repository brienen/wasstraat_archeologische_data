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
  anders de primary_key uit de bron (ABR) of uit PostgreSQL (op _id, op een
  unieke bestandsidentiteit, op een unieke key of, sinds issue 81, op de
  hulpsleutel uit de bronrij: getBronsleutel) en pas als laatste een nieuw
  nummer boven het bestaande maximum. Sinds issue 71 doet de volledige cyclus
  dat ook (setStabielePrimaryKeys); daar is het _id altijd nieuw.

Alle documenten die een incrementele run in Single_Store_Clean (opnieuw)
schrijft, hebben ``delta_run`` gelijk aan het run-id van die run.

Fase 3 (upsert-load, loadToDatabase_functions.loadIncrementeel) gebruikt
``leesPgSleutels``, ``bepaalVerdwenenPrimaryKeys`` en ``getLaadKey`` (de key
in PostgreSQL, voor artefacten ``getArtefactKey``) uit deze module.
"""
import ast
import copy
import datetime
import hashlib
import json
import math
from collections import Counter, defaultdict

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
# Velden (en kolommen van Def_Bestand) waarmee een bestand wordt herkend, los van zijn key: de map en de
# bestandsnaam. Foto's hebben vaak dezelfde key (sfeer- en opgravingsfoto met hetzelfde nummer, issue 71).
BESTAND_IDENTITEIT = ('directory', 'fileName')

# Hulpsleutel uit de bronrij (issue 81), zie getBronsleutel.
# Velden die de extractie (importMDB.sh) aan elke bronrij toevoegt; ze horen niet bij de inhoud van de rij.
BRONRIJ_TECHNISCHE_VELDEN = frozenset(['_id', 'loadtime', 'bron', 'mdbfile', 'table', 'projectcd'])
# Kolommen die als autonummer van de Access-tabel gelden, in volgorde van voorkeur
BRONRIJ_ID_KOLOMMEN = ('ID', 'Id', 'id')
# Map waarin de Airflow-container de invoer ziet; het pad in de bronsleutel is relatief daaraan
INVOERMAP = '/input/'
# Voorvoegsel van de hulpsleutel in de kolom key van PostgreSQL (rijen zonder natuurlijke key)
PREFIX_BRONSLEUTEL = 'bron:'
# Scheidingsteken tussen de bronrijen van een samengevoegd document
SCHEIDING_BRONRIJEN = ';'
# Langere bronsleutels (samengevoegde documenten met veel bronrijen) worden ingekort tot een hash
MAX_LENGTE_BRONSLEUTEL = 400
# Soorten met een eigen identiteit buiten de key: bestanden (map en bestandsnaam) en de ABR-thesaurus
# (primary_key uit de bron). Die krijgen geen hulpsleutel.
SOORTEN_ZONDER_BRONSLEUTEL = frozenset(list(const.BESTANDSOORTEN) + ['Bestand', 'ABR'])


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


# ============================================================
# Hulpsleutel uit de bronrij (issue 81)
# ============================================================

def _alsTekst(waarde):
    """Geef een getal of tekst als tekst; een geheel getal als float (10.0) zonder decimalen ('10')."""
    if isinstance(waarde, float) and waarde.is_integer():
        return str(int(waarde))
    return str(waarde)


def _jsonWaarde(waarde):
    """Tekst voor waarden die json niet kent (ObjectId, datetime), voor de hash van een bronrij."""
    return str(waarde)


def getBronrijId(element):
    """Retourneer de identiteit van één bronrij: bestand, tabel en autonummer (of een hash van de inhoud).

    Een element van ``brondata`` is de oorspronkelijke rij uit een Access-tabel
    met de velden die importMDB.sh toevoegt (``mdbfile``, ``table``,
    ``projectcd``, ``bron``, ``loadtime``) en het ``_id`` van het
    staging-document. De identiteit is
    ``<pad>:<tabel>:<autonummer>``, met het pad relatief aan de invoermap
    (``projecten/DB034_Koningsveld IV/C Database/opgravingDB34.mdb``) en het
    autonummer uit de eerste kolom van BRONRIJ_ID_KOLOMMEN met een geheel
    getal. Heeft de tabel geen autonummer, dan is het
    ``<pad>:<tabel>:#<hash>`` met een sha1 over de inhoud van de rij (alle
    velden behalve BRONRIJ_TECHNISCHE_VELDEN). Een ongewijzigde rij geeft zo bij
    elke extractie dezelfde identiteit; het ``_id`` en ``loadtime`` zijn wel
    elke keer nieuw.

    Args:
        element: dict met de velden van de bronrij

    Returns:
        Tekst, of None als het element geen bronrij uit een bestand is (geen
        mdbfile of table, bijv. een gegenereerd document)
    """
    if not isinstance(element, dict):
        return None
    pad, tabel = element.get('mdbfile'), element.get('table')
    if isLeeg(pad) or isLeeg(tabel):
        return None
    pad = str(pad)
    if pad.startswith(INVOERMAP):
        pad = pad[len(INVOERMAP):]
    for kolom in BRONRIJ_ID_KOLOMMEN:
        waarde = element.get(kolom)
        if isinstance(waarde, bool) or not isinstance(waarde, (int, float)):
            continue
        if isinstance(waarde, float) and not waarde.is_integer():
            continue
        return f"{pad}:{tabel}:{int(waarde)}"
    inhoud = {k: v for k, v in element.items() if k not in BRONRIJ_TECHNISCHE_VELDEN}
    tekst = json.dumps(inhoud, sort_keys=True, ensure_ascii=False, default=_jsonWaarde)
    return f"{pad}:{tabel}:#{hashlib.sha1(tekst.encode('utf-8')).hexdigest()[:16]}"


def getBronsleutel(brondata):
    """Retourneer de hulpsleutel van een document: de identiteit van zijn bronrij(en).

    Voor rijen zonder (unieke) natuurlijke key (issue 81): artefacten zonder
    subnr, monsters, plaatsingen, vindplaatsen, en rijen waarvan de key vaker
    voorkomt (standplaatsen, sporen, dozen). Een verplaatst document heeft één
    bronrij (getBronrijId); een samengevoegd document (merge in Transform 5)
    heeft er meer, en dan is de hulpsleutel de gesorteerde lijst van alle
    bronrijen, gescheiden door SCHEIDING_BRONRIJEN (langer dan
    MAX_LENGTE_BRONSLEUTEL: het aantal en een hash). Komt er een bronrij bij of
    verdwijnt er een, dan verandert de hulpsleutel van het samengevoegde
    document; het houdt zijn primary_key dan alleen via een unieke key.

    De functie werkt op ``brondata`` uit MongoDB (lijst, of dict bij
    gegenereerde documenten) en op de kolom brondata uit PostgreSQL na
    leesBrondataTekst, met dezelfde uitkomst.

    Args:
        brondata: lijst met bronrijen, één bronrij (dict) of None

    Returns:
        Tekst, of None als het document geen bronrij uit een bestand heeft
    """
    if brondata is None:
        return None
    elementen = brondata if isinstance(brondata, (list, tuple)) else [brondata]
    ids = sorted({rij_id for rij_id in (getBronrijId(e) for e in elementen) if rij_id})
    if not ids:
        return None
    sleutel = SCHEIDING_BRONRIJEN.join(ids)
    if len(sleutel) > MAX_LENGTE_BRONSLEUTEL:
        sleutel = f"{len(ids)} bronrijen #{hashlib.sha1(sleutel.encode('utf-8')).hexdigest()[:16]}"
    return sleutel


def _getArtefactVoorvoegsel(doc):
    """Leesbaar begin van de hulpsleutel van een artefact: P<projectcd>[P<putnr>][V<vondstnr>].

    Zoals key_subnr zonder het subnummer, en zonder de projectbrede vlag
    vondstkey_met_putnr: het putnummer staat erin als het bekend is.
    """
    delen = ['P', '' if isLeeg(doc.get('projectcd')) else _alsTekst(doc['projectcd'])]
    if not isLeeg(doc.get('putnr')):
        delen += ['P', _alsTekst(doc['putnr'])]
    if not isLeeg(doc.get('vondstnr')):
        delen += ['V', _alsTekst(doc['vondstnr'])]
    return ''.join(delen)


def getLaadKey(soort, doc):
    """Retourneer de key waarmee een document in PostgreSQL staat (kolom key) en wordt teruggevonden.

    1. De natuurlijke key uit Transform 3; bij artefacten getArtefactKey
       (key, of anders key_subnr|artefactsoort).
    2. Zonder natuurlijke key de hulpsleutel uit de bronrij (issue 81):
       artefacten ``P<project>[P<put>][V<vondst>]|<artefactsoort>|bron:<bronsleutel>``,
       andere soorten ``bron:<bronsleutel>``. Bestanden en de ABR krijgen geen
       hulpsleutel (SOORTEN_ZONDER_BRONSLEUTEL).

    De load zet deze waarde in de kolom key (vulLaadKey) en
    setStabielePrimaryKeys vergelijkt erop, zodat beide hetzelfde zien. Een
    natuurlijke key die vaker voorkomt blijft staan; die rijen worden op hun
    bronsleutel teruggevonden (bepaalStabieleIds).

    Args:
        soort: soort van het document
        doc: document uit Single_Store_Clean (met key, en voor de hulpsleutel brondata)

    Returns:
        De key, of None
    """
    if soort == 'Artefact':
        key = getArtefactKey(doc)
    else:
        key = None if isLeeg(doc.get('key')) else doc['key']
    if key is not None or soort in SOORTEN_ZONDER_BRONSLEUTEL:
        return key
    bronsleutel = getBronsleutel(doc.get('brondata'))
    if bronsleutel is None:
        return None
    if soort == 'Artefact':
        artefactsoort = '' if isLeeg(doc.get('artefactsoort')) else doc['artefactsoort']
        return (f"{_getArtefactVoorvoegsel(doc)}{SCHEIDING_ARTEFACT_KEY}{artefactsoort}"
                f"{SCHEIDING_ARTEFACT_KEY}{PREFIX_BRONSLEUTEL}{bronsleutel}")
    return f"{PREFIX_BRONSLEUTEL}{bronsleutel}"


# Aanroepen die in de tekst van brondata (str() van de lijst uit MongoDB) kunnen staan, met hun waarde
_BRONDATA_AANROEPEN = {
    'ObjectId': lambda waarde: str(waarde),
    'Int64': lambda waarde: int(waarde),
    'datetime.datetime': lambda *args: datetime.datetime(*args),
    'datetime': lambda *args: datetime.datetime(*args),
    'datetime.date': lambda *args: datetime.date(*args),
}
_BRONDATA_NAMEN = {'nan': float('nan'), 'inf': float('inf'), 'None': None, 'True': True, 'False': False}


def _naamVan(knoop):
    """Volledige naam van een (attribuut)naam in de syntaxboom, bijv. 'datetime.datetime'."""
    if isinstance(knoop, ast.Name):
        return knoop.id
    if isinstance(knoop, ast.Attribute):
        return f"{_naamVan(knoop.value)}.{knoop.attr}"
    raise ValueError('Onbekende aanroep in brondata')


def _evalueerBrondata(knoop):
    """Evalueer een knoop uit de syntaxboom van brondata; alleen literals en de bekende aanroepen."""
    if isinstance(knoop, ast.Constant):
        return knoop.value
    if isinstance(knoop, (ast.List, ast.Tuple)):
        return [_evalueerBrondata(e) for e in knoop.elts]
    if isinstance(knoop, ast.Dict):
        if any(k is None for k in knoop.keys):
            raise ValueError('Uitpakken in brondata wordt niet ondersteund')
        return {_evalueerBrondata(k): _evalueerBrondata(v) for k, v in zip(knoop.keys, knoop.values)}
    if isinstance(knoop, ast.UnaryOp) and isinstance(knoop.op, (ast.USub, ast.UAdd)):
        waarde = _evalueerBrondata(knoop.operand)
        if isinstance(waarde, bool) or not isinstance(waarde, (int, float)):
            raise ValueError('Teken voor een waarde die geen getal is')
        return -waarde if isinstance(knoop.op, ast.USub) else waarde
    if isinstance(knoop, ast.Name) and knoop.id in _BRONDATA_NAMEN:
        return _BRONDATA_NAMEN[knoop.id]
    if isinstance(knoop, ast.Call) and not knoop.keywords:
        functie = _BRONDATA_AANROEPEN.get(_naamVan(knoop.func))
        if functie is None:
            raise ValueError('Onbekende aanroep in brondata')
        return functie(*[_evalueerBrondata(a) for a in knoop.args])
    raise ValueError(f'Onverwachte waarde in brondata: {type(knoop).__name__}')


def leesBrondataTekst(tekst):
    """Lees de kolom brondata uit PostgreSQL terug als lijst met bronrijen.

    De load schrijft brondata als ``str()`` van de lijst uit MongoDB
    (transformRow), met ObjectId, Int64, datetime en nan. Deze functie leest
    die tekst veilig terug (geen eval: alleen literals en die aanroepen), zodat
    getBronsleutel voor een rij in PostgreSQL dezelfde hulpsleutel geeft als
    voor het document in MongoDB. Zo vindt Transform 4 ook rijen terug die zijn
    geladen vóór issue 81.

    Args:
        tekst: inhoud van de kolom brondata, of None

    Returns:
        Lijst (of dict) met de bronrij(en), of None als de tekst leeg of onleesbaar is
    """
    if tekst is None or not isinstance(tekst, str) or not tekst.strip():
        return None
    try:
        waarde = _evalueerBrondata(ast.parse(tekst.strip(), mode='eval').body)
    except (SyntaxError, ValueError, TypeError, RecursionError, OverflowError, MemoryError):
        return None
    return waarde if isinstance(waarde, (list, dict)) else None


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
    """Lees de bestaande toewijzing (_id, key, bestandsidentiteit) → primary_key uit een PostgreSQL-tabel.

    Args:
        tabel: tabelnaam, bijv. 'Def_Vondst'
        cursor: optionele psycopg2-cursor. De upsert-load (fase 3) geeft zijn
            eigen cursor mee: die houdt locks op de tabellen vast, zodat een
            tweede verbinding zou blijven wachten. Zonder cursor wordt een
            eigen verbinding geopend en gesloten.

    Returns:
        Lijst met dicts {'primary_key', '_id', 'key'} plus de kolommen van
        BESTAND_IDENTITEIT als de tabel die heeft (Def_Bestand); kolommen die
        ontbreken worden weggelaten. None als de tabel (of de kolom
        primary_key) niet bestaat
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
    velden = ['primary_key'] + [k for k in ('_id', 'key') + BESTAND_IDENTITEIT if k in kolommen]
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


def getBestandIdentiteit(doc):
    """Retourneer de identiteit van een bestand (map/bestandsnaam), of None als een van beide ontbreekt.

    Werkt op een document uit Single_Store_Clean en op een rij uit
    leesPgSleutels (kolommen directory en fileName van Def_Bestand).

    Args:
        doc: document of rij met de velden uit BESTAND_IDENTITEIT

    Returns:
        Tekst '<directory>/<fileName>' of None
    """
    directory, naam = (doc.get(veld) for veld in BESTAND_IDENTITEIT)
    if isLeeg(directory) or isLeeg(naam):
        return None
    return f"{str(directory).rstrip('/')}/{naam}"


def getBronPrimaryKey(doc):
    """Retourneer het veld primary_key uit de brondata als geheel getal, of None.

    Alleen de ABR-thesaurus levert een eigen primary_key (de harmonisatie neemt
    de kolom over); parentID en de webapplicatie verwijzen naar die nummers.

    Args:
        doc: document uit Single_Store_Clean

    Returns:
        Geheel getal of None (ontbrekend, leeg of geen geheel getal)
    """
    waarde = doc.get('primary_key')
    if waarde is None or isinstance(waarde, bool):
        return None
    try:
        getal = float(waarde)
    except (TypeError, ValueError):
        return None
    if math.isnan(getal) or getal != int(getal):
        return None
    return int(getal)


def _koppelOpUniekeWaarde(zonder_id, toewijzing, in_gebruik, waarde_van, pg_rijen, alleen=None):
    """Ken documenten zonder toewijzing de primary_key toe van de enige rij in PostgreSQL met dezelfde waarde.

    Een waarde die meer dan één keer in de tabel voorkomt wordt niet gebruikt;
    een primary_key die al in gebruik is wordt niet nog eens uitgedeeld.

    Args:
        zonder_id: documenten zonder ID
        toewijzing: dict index -> primary_key (wordt aangevuld)
        in_gebruik: set met uitgedeelde primary_keys (wordt aangevuld)
        waarde_van: functie die van een document en van een rij de waarde geeft (of None)
        pg_rijen: rijen uit leesPgSleutels
        alleen: optionele functie die van een document zegt of het in deze stap mag koppelen

    Returns:
        Aantal toegekende primary_keys
    """
    per_waarde = {}
    aantal = Counter()
    for rij in pg_rijen or []:
        waarde = waarde_van(rij)
        if rij.get('primary_key') is None or waarde is None:
            continue
        aantal[waarde] += 1
        per_waarde[waarde] = int(rij['primary_key'])
    gekoppeld = 0
    for i, doc in enumerate(zonder_id):
        if i in toewijzing or (alleen is not None and not alleen(doc)):
            continue
        waarde = waarde_van(doc)
        if waarde is None or aantal.get(waarde) != 1:
            continue
        pk = per_waarde[waarde]
        if pk not in in_gebruik:
            toewijzing[i] = pk
            in_gebruik.add(pk)
            gekoppeld += 1
    return gekoppeld


def _koppelOpGroep(zonder_id, toewijzing, in_gebruik, waarde_van_doc, pg_waarden):
    """Koppel documenten aan vrije rijen in PostgreSQL met dezelfde waarde, ook als die waarde vaker voorkomt.

    Per waarde worden de documenten (gesorteerd op _id) en de vrije
    primary_keys (oplopend) paarsgewijs gekoppeld; wat overblijft koppelt niet.
    Bedoeld voor de bronsleutel (issue 81): documenten met dezelfde bronsleutel
    en dezelfde key komen uit identieke bronrijen (bijv. een Access-tabel zonder
    autonummer met twee gelijke rijen) en zijn onderling uitwisselbaar. Een
    groep met documenten met verschillende keys (één bronrij die bij twee
    artefactsoorten hoort) wordt overgeslagen, behalve als er precies één
    document en één rij is.

    Args:
        zonder_id: documenten zonder ID
        toewijzing: dict index -> primary_key (wordt aangevuld)
        in_gebruik: set met uitgedeelde primary_keys (wordt aangevuld)
        waarde_van_doc: functie die van een document de waarde geeft (of None)
        pg_waarden: lijst met (primary_key, waarde) van de rijen in PostgreSQL

    Returns:
        Aantal toegekende primary_keys
    """
    pks_per_waarde = defaultdict(list)
    for pk, waarde in pg_waarden:
        if waarde is not None and pk not in in_gebruik:
            pks_per_waarde[waarde].append(pk)
    docs_per_waarde = defaultdict(list)
    for i, doc in enumerate(zonder_id):
        if i in toewijzing:
            continue
        waarde = waarde_van_doc(doc)
        if waarde is not None and waarde in pks_per_waarde:
            docs_per_waarde[waarde].append(i)
    gekoppeld = 0
    for waarde, indexen in docs_per_waarde.items():
        pks = sorted(pks_per_waarde[waarde])
        if len({zonder_id[i].get('key') for i in indexen}) > 1 and not (len(indexen) == 1 and len(pks) == 1):
            continue
        for i, pk in zip(sorted(indexen, key=lambda i: str(zonder_id[i]['_id'])), pks):
            toewijzing[i] = pk
            in_gebruik.add(pk)
            gekoppeld += 1
    return gekoppeld


def bepaalStabieleIds(docs, pg_rijen=None, lees_bronsleutels=None):
    """Bepaal stabiele ID's voor de documenten van een soort zonder ID.

    Volgorde per document zonder ID:

    1. de primary_key uit de bron (veld ``primary_key``, alleen bij de
       ABR-thesaurus; getBronPrimaryKey), zoals de oude nummering van de
       volledige cyclus;
    2. de primary_key van de rij in PostgreSQL met dezelfde ``_id`` (tekst van
       het ``_id``). Verplaatste documenten houden het ``_id`` van hun
       staging-document; een samengevoegd document krijgt het ``_id`` van het
       laatste brondocument in zijn groep, dat gelijk blijft zolang de groep
       niet verandert. In de volledige cyclus is het ``_id`` altijd nieuw;
    3. bij bestanden de primary_key van de rij met dezelfde map en
       bestandsnaam (getBestandIdentiteit), als die combinatie precies één
       keer in de tabel voorkomt: foto's hebben vaak dezelfde key;
    4. de primary_key van de rij met dezelfde ``key``, als die key precies één
       keer in de tabel voorkomt. Een document met een bronsleutel waarvan de
       key ook onder de documenten vaker voorkomt, slaat deze stap over: welke
       rij bij welk document hoort, beslist dan de bronsleutel (stap 5);
    5. (issue 81) de primary_key van een vrije rij met dezelfde ``bronsleutel``
       én dezelfde ``key`` (getBronsleutel; voor de rijen in PostgreSQL
       afgeleid uit de kolom brondata met ``lees_bronsleutels``). Zo houden
       rijen met een key die vaker voorkomt (standplaatsen, sporen, dozen,
       artefacten die zowel verplaatst als samengevoegd zijn) hun nummer.
       Komt de combinatie vaker voor (identieke bronrijen), dan worden
       documenten en rijen paarsgewijs gekoppeld (_koppelOpGroep);
    6. (issue 81, overgang) de primary_key van een vrije rij zonder key met
       dezelfde ``bronsleutel``: rijen die zijn geladen vóór de hulpsleutel en
       nog geen key hebben (artefacten zonder subnr, monsters, plaatsingen,
       vindplaatsen) houden zo bij de eerste cyclus hun nummer;
    7. de primary_key van de rij met dezelfde, in de tabel unieke ``key`` voor
       de documenten die stap 4 oversloeg en die stap 5 niet kon koppelen (de
       regel van vóór issue 81: het eerste document krijgt het nummer);
    8. anders een nieuw nummer, oplopend vanaf het maximum van de primary_keys
       in PostgreSQL en de ID's in Single_Store_Clean, plus één.

    Een primary_key die al bij een ander document hoort (een document dat zijn
    ID heeft behouden, of eerder in deze toewijzing) wordt niet nog eens
    uitgedeeld. Documenten met een ID houden dat ID. Twee documenten met
    dezelfde (in PostgreSQL unieke) key zonder bronsleutel: het eerste krijgt
    de bestaande primary_key, het tweede een nieuw nummer.

    Args:
        docs: documenten van de soort uit Single_Store_Clean (met _id, key en eventueel ID,
            primary_key, directory, fileName en bronsleutel)
        pg_rijen: rijen uit leesPgSleutels, of None als de soort geen tabel heeft. Een rij
            mag zelf al een 'bronsleutel' hebben (dan wordt lees_bronsleutels niet gebruikt)
        lees_bronsleutels: optionele functie die voor een lijst primary_keys een dict
            primary_key -> bronsleutel teruggeeft (leesPgBronsleutels); alleen aangeroepen
            voor de rijen die na stap 4 nog vrij zijn, en alleen als er documenten met een
            bronsleutel over zijn

    Returns:
        Tuple (lijst met (_id, ID) voor de documenten zonder ID, dict met tellingen
        'behouden', 'uit_bron', 'op_id', 'op_bestand', 'op_key', 'op_bronsleutel',
        'op_bronsleutel_overgang' en 'nieuw')
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
    for rij in pg_rijen or []:
        if rij.get('primary_key') is None:
            continue
        pk = int(rij['primary_key'])
        maximum = max(maximum, pk)
        if rij.get('_id') is not None:
            per_id[str(rij['_id'])] = pk

    tellingen = {'behouden': len(docs) - len(zonder_id), 'uit_bron': 0, 'op_id': 0, 'op_bestand': 0,
                 'op_key': 0, 'op_bronsleutel': 0, 'op_bronsleutel_overgang': 0, 'nieuw': 0}
    toewijzing = {}

    # 1. Uit de bron (ABR)
    for i, doc in enumerate(zonder_id):
        pk = getBronPrimaryKey(doc)
        if pk is not None and pk not in in_gebruik:
            toewijzing[i] = pk
            in_gebruik.add(pk)
            maximum = max(maximum, pk)
            tellingen['uit_bron'] += 1

    # 2. Op _id
    for i, doc in enumerate(zonder_id):
        if i in toewijzing:
            continue
        pk = per_id.get(str(doc['_id']))
        if pk is not None and pk not in in_gebruik:
            toewijzing[i] = pk
            in_gebruik.add(pk)
            tellingen['op_id'] += 1

    # 3. Op een unieke bestandsidentiteit, 4. op een unieke key (behalve documenten met een bronsleutel
    #    waarvan de key onder de documenten vaker voorkomt: die gaan via stap 5)
    tellingen['op_bestand'] = _koppelOpUniekeWaarde(zonder_id, toewijzing, in_gebruik, getBestandIdentiteit, pg_rijen)
    keys_in_docs = Counter(doc.get('key') for doc in docs if doc.get('key') is not None)
    tellingen['op_key'] = _koppelOpUniekeWaarde(
        zonder_id, toewijzing, in_gebruik, lambda d: d.get('key'), pg_rijen,
        alleen=lambda d: d.get('bronsleutel') is None or keys_in_docs[d.get('key')] <= 1)

    # 5. en 6. Op de bronsleutel (issue 81), alleen voor de rijen die nog vrij zijn
    resterend = [i for i in range(len(zonder_id)) if i not in toewijzing and zonder_id[i].get('bronsleutel')]
    vrij = [rij for rij in pg_rijen or [] if rij.get('primary_key') is not None
            and int(rij['primary_key']) not in in_gebruik]
    if resterend and vrij:
        if all('bronsleutel' in rij for rij in vrij) or lees_bronsleutels is None:
            gelezen = {}
        else:
            gelezen = lees_bronsleutels([int(rij['primary_key']) for rij in vrij if 'bronsleutel' not in rij])
        met_key, zonder_key = [], []
        for rij in vrij:
            pk = int(rij['primary_key'])
            bronsleutel = rij['bronsleutel'] if 'bronsleutel' in rij else gelezen.get(pk)
            if bronsleutel is None:
                continue
            if isLeeg(rij.get('key')):
                zonder_key.append((pk, bronsleutel))
            else:
                met_key.append((pk, (bronsleutel, rij['key'])))
        tellingen['op_bronsleutel'] = _koppelOpGroep(
            zonder_id, toewijzing, in_gebruik,
            lambda d: (d['bronsleutel'], d.get('key')) if d.get('bronsleutel') else None, met_key)
        tellingen['op_bronsleutel_overgang'] = _koppelOpGroep(
            zonder_id, toewijzing, in_gebruik, lambda d: d.get('bronsleutel'), zonder_key)

    # 7. De rest op een unieke key, zoals vóór issue 81
    tellingen['op_key'] += _koppelOpUniekeWaarde(zonder_id, toewijzing, in_gebruik, lambda d: d.get('key'), pg_rijen)

    # 8. Nieuwe nummers, in een vaste volgorde
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


def leesPgBronsleutels(tabel, primary_keys, cursor=None):
    """Lees de bronsleutels van rijen in PostgreSQL, afgeleid uit de kolom brondata (issue 81).

    De hulpsleutel staat niet in een eigen kolom: hij volgt uit de bronrijen in
    de kolom brondata (leesBrondataTekst en getBronsleutel), net zoals uit het
    veld brondata in MongoDB. Daardoor werkt het terugvinden ook voor rijen die
    zijn geladen vóór issue 81. Transform 4 leest alleen de rijen die na de
    koppeling op _id, bestand en unieke key nog vrij zijn.

    Args:
        tabel: tabelnaam, bijv. 'Def_Artefact'
        primary_keys: de primary_keys waarvan de bronsleutel nodig is
        cursor: optionele psycopg2-cursor; zonder cursor een eigen verbinding

    Returns:
        Dict primary_key -> bronsleutel (alleen rijen met een bronsleutel); leeg als
        de tabel geen kolom brondata heeft
    """
    primary_keys = sorted({int(pk) for pk in primary_keys})
    if not primary_keys:
        return {}
    if cursor is None:
        from wasstraat.loadToDatabase_functions import getPgConnection

        conn = getPgConnection()
        try:
            return leesPgBronsleutels(tabel, primary_keys, conn.cursor())
        finally:
            conn.close()

    cursor.execute("""
        SELECT column_name FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = %s AND column_name = 'brondata'
    """, (tabel,))
    if not cursor.fetchall():
        return {}
    bronsleutels = {}
    onleesbaar = 0
    for batch in inBatches(primary_keys, BATCH_GROOTTE):
        cursor.execute(f'SELECT primary_key, brondata FROM "{tabel}" WHERE primary_key = ANY(%s)', (list(batch),))
        for pk, brondata in cursor.fetchall():
            bronrijen = leesBrondataTekst(brondata)
            if bronrijen is None and brondata:
                onleesbaar += 1
            bronsleutel = getBronsleutel(bronrijen)
            if bronsleutel is not None:
                bronsleutels[int(pk)] = bronsleutel
    if onleesbaar:
        logger.warning(f"{onleesbaar} rijen in {tabel} met een kolom brondata die niet te lezen is; die rijen "
                       f"worden niet op hun bronsleutel teruggevonden.")
    return bronsleutels


def setStabielePrimaryKeys(soort, collection):
    """Ken stabiele ID's toe aan de documenten van een soort in Single_Store_Clean (zie bepaalStabieleIds).

    Draait in de incrementele én (sinds issue 71) de volledige cyclus. Alleen
    documenten zonder ID worden bijgewerkt (alleen het veld ID). De documenten
    worden vergeleken op ``getLaadKey``, dezelfde key als de load in de kolom
    key zet: de natuurlijke key (artefacten: key, of anders
    ``key_subnr|artefactsoort``), en zonder natuurlijke key de hulpsleutel uit
    de bronrij (issue 81). Daarnaast krijgt elk document (behalve bestanden en
    de ABR) in het geheugen zijn ``bronsleutel`` (getBronsleutel), waarmee rijen
    met een key die vaker voorkomt worden teruggevonden; de bronsleutels van
    de rijen in PostgreSQL komen uit de kolom brondata (leesPgBronsleutels).
    Bestaat de tabel in PostgreSQL niet en heeft nog geen enkel document een
    ID (eerste run in een lege database), dan retourneert de functie False: de
    aanroeper kent de sleutels dan toe zoals vóór issue 71 (volgnummers vanaf
    0). Een lege tabel geeft ook nummers vanaf 0 (op volgorde van key en _id).

    Args:
        soort: soort uit SET_KEYS_PIPELINES
        collection: Single_Store_Clean-collectie

    Returns:
        True als de sleutels zijn toegekend, False als de aanroeper het oude gedrag moet volgen
    """
    tabel = getTabelVoorSoort(soort)
    met_bronsleutel = tabel is not None and soort not in SOORTEN_ZONDER_BRONSLEUTEL
    projectie = {'_id': 1, 'key': 1, 'ID': 1, 'primary_key': 1}
    projectie.update({veld: 1 for veld in BESTAND_IDENTITEIT})
    if soort == 'Artefact':
        projectie.update({'key_subnr': 1, 'artefactsoort': 1, 'projectcd': 1, 'putnr': 1, 'vondstnr': 1})
    if met_bronsleutel:
        projectie['brondata'] = 1
    docs = list(collection.find({'soort': soort}, projectie))
    for doc in docs:
        # Zelfde key als de load in de kolom key zet (alleen in het geheugen)
        doc['key'] = getLaadKey(soort, doc)
        if met_bronsleutel:
            doc['bronsleutel'] = getBronsleutel(doc.pop('brondata', None))
    if not docs:
        logger.warning(f"Geen documenten van soort {soort} gevonden in Single_Store_Clean — geen sleutels toegekend.")
        return True

    pg_rijen = leesPgSleutels(tabel) if tabel else None
    if tabel and pg_rijen is None and not any(heeftId(doc) for doc in docs):
        logger.info(f"Tabel {tabel} bestaat niet en geen enkel document van soort {soort} heeft een ID — "
                    f"sleutels worden toegekend zoals in de volledige cyclus.")
        return False

    lees_bronsleutels = (lambda pks: leesPgBronsleutels(tabel, pks)) if met_bronsleutel else None
    toewijzingen, tellingen = bepaalStabieleIds(docs, pg_rijen, lees_bronsleutels)
    for batch in inBatches(toewijzingen):
        collection.bulk_write([UpdateOne({'_id': _id}, {'$set': {'ID': nieuw_id}}) for _id, nieuw_id in batch])

    ids = [doc['ID'] for doc in docs if heeftId(doc)] + [nieuw_id for _, nieuw_id in toewijzingen]
    tellingen['verdwenen'] = len(bepaalVerdwenenPrimaryKeys(pg_rijen, ids))
    tellingen['tabel'] = tabel
    logger.info(f"Stabiele sleutels voor {soort} (tabel {tabel}): {tellingen}.")
    werkTellingBij(f'primary_keys.{soort}', tellingen)
    return True
