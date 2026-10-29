"""Voorrang bij de harmonisatie (Transform 1, issue 89): elke staging-tabel door precies één pipeline.

De taken ``Harmonize_<soort>`` van Transform 1 draaien parallel. Elke
pipeline selecteert de documenten van zijn staging-collectie op de naam van de
Access-tabel (veld ``table``; patronen uit de harmonisatie-Excel, blad
``Objecten``, kolom ``Tabellen``, of een vaste ``$match`` in meta.py) en
schrijft ze met ``$merge`` op ``_id`` (``whenMatched: replace``) naar
Single_Store. Selecteren twee pipelines dezelfde tabel, dan overschrijft de
pipeline die het laatst klaar is het werk van de andere, en welke dat is
verschilt per run. In Delft gebeurde dat met ``AW1DeterminatiesJohan``
(Aardewerk via ``AW1.*``, Artefact via ``Determinaties``).

Deze module maakt de keuze deterministisch. Elke taak bepaalt zelf, met
``distinct('table', <leidende $match-fasen>)`` op de staging-collectie, welke
tabellen de pipelines op dezelfde collectie selecteren (bepaalClaims), kiest
per tabel die meer dan één pipeline selecteert één soort (bepaalBesluiten) en
sluit in zijn eigen pipeline de tabellen uit die een andere soort krijgt
(pasUitsluitingToe: ``{$match: {table: {$nin: [...]}}}`` vooraan). Alle
taken gebruiken dezelfde staging, dezelfde configuratie en dezelfde regel en
komen dus tot hetzelfde besluit, onafhankelijk van de volgorde waarin ze
draaien.

Voorrang per tabel:

1. expliciet in ``correcties.yml``, sectie ``harmonisatie_voorrang``:
   tabelnaam → soort, of een lege waarde: door geen enkele pipeline (voor
   codetabellen). Een expliciete keuze geeft geen waarschuwing;
2. anders de vaste regel (getVoorrangVolgorde): een specifieke artefactsoort
   (``meta.lst_artefactsoort``) gaat vóór de algemene ``Artefact``; verder de
   volgorde van ``meta.wasstraat_model``.

Alleen pipelines die het ``_id`` van het staging-document naar Single_Store
schrijven kunnen elkaar overschrijven (getSelectieFilter). Standplaatsen,
plaatsingen en dozen maken uit dezelfde rij van de magazijnlijst elk een eigen
document met een nieuw ``_id``; die tellen niet mee.

Een tabel die meer dan één pipeline selecteert zonder instelling geeft een
waarschuwing in het run-document (``foutbeleid.SOORT_TABEL_DUBBEL_GESELECTEERD``),
met de tabel, de kandidaten en de gekozen soort. Alle besluiten (ook de
expliciete) staan in ``tellingen.transform.harmonisatie_voorrang.<soort>`` en
in het verwerkingsrapport (kwaliteitsmeldingen). Elk besluit wordt door één
taak gemeld: die van de gekozen soort, of bij een tabel die geen soort krijgt
die van de eerste kandidaat.
"""
import copy
from collections import defaultdict

import wasstraat.foutbeleid as foutbeleid
import wasstraat.harmonizer as harmonizer
import wasstraat.meta as meta
import logging

logger = logging.getLogger("airflow.task")

# Sectie in correcties.yml
SECTIE_VOORRANG = 'harmonisatie_voorrang'
# Soorten uit meta.py zonder eigen Harmonize-taak (foto's komen uit ParseFotobestanden)
SOORTEN_ZONDER_HARMONISATIETAAK = ['Foto']
# Waar een besluit vandaan komt
BRON_INSTELLING = 'correcties.yml'
BRON_REGEL = 'voorrangsregel'
# Pad onder tellingen in het run-document
TELLING_VOORRANG = 'transform.harmonisatie_voorrang'


# ============================================================
# Soorten en pipelines
# ============================================================

def getHarmonizeSoorten():
    """Retourneer de soorten met een taak Harmonize_<soort>, in de volgorde van meta.wasstraat_model.

    Returns:
        Lijst met soorten (zonder SOORTEN_ZONDER_HARMONISATIETAAK)
    """
    return [soort for soort in meta.getKeys(meta.HARMONIZE_PIPELINES) if soort not in SOORTEN_ZONDER_HARMONISATIETAAK]


def getVoorrangVolgorde(soorten=None):
    """Retourneer de soorten in volgorde van voorrang (de vaste regel).

    Een specifieke artefactsoort (meta.lst_artefactsoort) gaat vóór de
    algemene soort ``Artefact``: de artefactsoorten die in meta.wasstraat_model
    na ``Artefact`` staan, schuiven ervoor, in hun onderlinge volgorde. Verder
    geldt de volgorde van meta.wasstraat_model.

    Args:
        soorten: soorten om te ordenen; standaard getHarmonizeSoorten()

    Returns:
        Lijst met soorten, de soort met de hoogste voorrang eerst
    """
    soorten = list(getHarmonizeSoorten() if soorten is None else soorten)
    specifiek = [soort for soort in soorten if soort in meta.lst_artefactsoort]
    volgorde = []
    for soort in soorten:
        if soort == 'Artefact':
            volgorde += [s for s in specifiek if s not in volgorde]
        if soort not in volgorde:
            volgorde.append(soort)
    return volgorde


def getStagingCollectie(soort):
    """Retourneer de staging-collectie van een soort, of None als de soort er geen heeft."""
    return meta.wasstraat_model.get(soort, {}).get(meta.STAGING_COLLECTION)


def getPipeline(soort, harmonizerDf=None):
    """Retourneer de harmonisatie-pipeline van een soort (uit de harmonisatie-Excel of meta.py).

    Args:
        soort: soort uit meta.wasstraat_model
        harmonizerDf: optioneel de al gelezen Excel (harmonizer.getHarmonizer)

    Returns:
        Lijst met aggregatiefasen (leeg als de soort geen pipeline heeft)
    """
    pipelines = meta.getHarmonizePipelines(soort)
    if isinstance(pipelines, str):
        return harmonizer.getHarmonizeAggr(pipelines, df=harmonizerDf)
    return pipelines[0] if pipelines else []


def bepaalSoort(strOrAggr):
    """Bepaal de soort bij het argument strOrAggr van harmonize_functions.harmonize.

    Een tekst is de naam van het object in de harmonisatie-Excel en daarmee de
    soort. Bij een lijst met een vaste pipeline uit meta.py is het de soort
    met precies die pipeline.

    Args:
        strOrAggr: naam van het object of een lijst met één pipeline

    Returns:
        De soort, of None als die niet te bepalen is
    """
    if isinstance(strOrAggr, str):
        return strOrAggr
    for soort in getHarmonizeSoorten():
        if meta.getHarmonizePipelines(soort) == strOrAggr:
            return soort
    return None


def getSelectieFilter(pipeline):
    """Retourneer het filter waarmee een pipeline staging-documenten selecteert, als hij hun _id schrijft.

    Het filter is de combinatie van de ``$match``-fasen aan het begin van de
    pipeline. Alleen een pipeline die met ``$merge`` op ``_id`` naar
    Single_Store schrijft en het ``_id`` van het staging-document behoudt, kan
    het werk van een andere pipeline overschrijven. Een ``$replaceRoot`` (of
    ``$replaceWith``) zonder ``_id`` in het nieuwe document geeft elk document
    een nieuw ``_id`` (standplaatsen, plaatsingen en dozen uit dezelfde rij van
    de magazijnlijst); zo'n pipeline doet niet mee.

    Args:
        pipeline: lijst met aggregatiefasen

    Returns:
        Het filter (dict; {} als de pipeline niet met een $match begint), of
        None als de pipeline niets schrijft of nieuwe _id's maakt
    """
    if not pipeline:
        return None
    merges = [fase['$merge'] for fase in pipeline if isinstance(fase, dict) and '$merge' in fase]
    if not merges:
        return None
    op = merges[-1].get('on', '_id') if isinstance(merges[-1], dict) else '_id'
    if op not in ('_id', ['_id']):
        return None
    for fase in pipeline:
        nieuw = None
        if '$replaceRoot' in fase:
            nieuw = (fase['$replaceRoot'] or {}).get('newRoot')
        elif '$replaceWith' in fase:
            nieuw = fase['$replaceWith']
        else:
            continue
        if isinstance(nieuw, dict) and nieuw.get('_id') != '$_id':
            return None
    matches = []
    for fase in pipeline:
        if '$match' not in fase:
            break
        matches.append(fase['$match'])
    if not matches:
        return {}
    return copy.deepcopy(matches[0]) if len(matches) == 1 else {'$and': copy.deepcopy(matches)}


# ============================================================
# Configuratie
# ============================================================

def leesVoorrangInstellingen(correcties):
    """Lees de sectie harmonisatie_voorrang uit correcties.yml.

    Vorm: een dictionary van tabelnaam naar soort. Een lege waarde (niets,
    ``~``, ``null`` of ``""``) betekent: door geen enkele pipeline
    harmoniseren. Een tabelnaam moet precies overeenkomen met de naam van de
    Access-tabel (hoofdlettergevoelig). Ongeldige regels worden met een
    foutmelding in het log overgeslagen; is de sectie geen dictionary, dan
    geldt geen enkele instelling. Of de soort bestaat en de tabel selecteert,
    controleert bepaalBesluiten.

    Args:
        correcties: dict uit harmonize_functions.laadCorrecties() (of None)

    Returns:
        Dict tabelnaam -> soort (tekst) of None
    """
    sectie = (correcties or {}).get(SECTIE_VOORRANG)
    if sectie is None:
        return {}
    if not isinstance(sectie, dict):
        logger.error(f"Sectie {SECTIE_VOORRANG} in correcties.yml is geen dictionary (tabelnaam: soort) maar "
                     f"{type(sectie).__name__} — geen voorrang ingesteld.")
        return {}
    instellingen = {}
    for tabel, soort in sectie.items():
        if not isinstance(tabel, str) or not tabel.strip():
            logger.error(f"Ongeldige tabelnaam in {SECTIE_VOORRANG}: {tabel!r} (zet de naam tussen "
                         f"aanhalingstekens) — regel overgeslagen.")
            continue
        if soort is None or (isinstance(soort, str) and not soort.strip()):
            instellingen[tabel] = None
        elif isinstance(soort, str):
            instellingen[tabel] = soort.strip()
        else:
            logger.error(f"Ongeldige soort in {SECTIE_VOORRANG} voor tabel {tabel!r}: {soort!r} (verwacht de naam "
                         f"van een soort, of een lege waarde) — regel overgeslagen.")
    return instellingen


# ============================================================
# Claims en besluiten
# ============================================================

def bepaalClaims(stagingcollectie, collectienaam, soorten=None):
    """Bepaal per soort welke tabellen van een staging-collectie zijn harmonisatie-pipeline selecteert.

    Alleen soorten met deze staging-collectie en een pipeline die het _id
    van het staging-document schrijft (getSelectieFilter) doen mee. De tabellen
    komen uit ``distinct('table', <filter>)`` op de hele collectie, ook in de
    incrementele cyclus, zodat elke run hetzelfde besluit neemt. Een soort
    waarvan de pipeline niet te bouwen is (bijvoorbeeld een object dat in de
    Excel ontbreekt) wordt met een waarschuwing overgeslagen; zijn eigen taak
    faalt daar al op.

    Args:
        stagingcollectie: pymongo-collectie (alleen distinct wordt gebruikt)
        collectienaam: naam van de staging-collectie
        soorten: soorten om te bekijken; standaard getHarmonizeSoorten()

    Returns:
        Dict soort -> set met tabelnamen
    """
    claims = {}
    soorten = [soort for soort in (getHarmonizeSoorten() if soorten is None else soorten)
               if getStagingCollectie(soort) == collectienaam]
    # De Excel één keer lezen voor alle soorten op deze collectie (uit de cache, als die er is)
    harmonizerDf = None
    if any(isinstance(meta.getHarmonizePipelines(soort), str) for soort in soorten):
        harmonizerDf = harmonizer.getHarmonizer()
    for soort in soorten:
        try:
            filt = getSelectieFilter(getPipeline(soort, harmonizerDf))
        except Exception as err:
            logger.warning(f"Pipeline van {soort} niet te bouwen voor de voorrang bij de harmonisatie: {err}")
            continue
        if filt is None:
            continue
        claims[soort] = {str(tabel) for tabel in stagingcollectie.distinct('table', filt) if tabel is not None}
    return claims


def bepaalBesluiten(claims, instellingen=None, collectienaam=None, volgorde=None):
    """Bepaal per tabel welke soort hem harmoniseert, als er iets te kiezen of in te stellen is.

    Een besluit volgt voor elke tabel die meer dan één soort selecteert en voor
    elke tabel met een instelling in harmonisatie_voorrang:

    - een instelling met een soort die de tabel selecteert, of een lege
      instelling (geen enkele soort), geldt (bron ``correcties.yml``);
    - zonder (bruikbare) instelling kiest de vaste regel de eerste kandidaat
      in de voorrangsvolgorde (bron ``voorrangsregel``). Een instelling met
      een soort die de tabel niet selecteert (of die niet bestaat) wordt
      genegeerd en vermeld onder ``ongeldige_instelling``.

    Een tabel met één kandidaat en zonder instelling krijgt geen besluit.

    Args:
        claims: dict soort -> tabellen (bepaalClaims)
        instellingen: dict tabel -> soort of None (leesVoorrangInstellingen)
        collectienaam: naam van de staging-collectie (alleen voor het besluit)
        volgorde: voorrangsvolgorde van de soorten; standaard getVoorrangVolgorde()

    Returns:
        Dict tabel -> besluit met tabel, collectie, kandidaten (in volgorde van
        voorrang), gekozen (soort of None), bron, en eventueel ongeldige_instelling
    """
    instellingen = instellingen or {}
    volgorde = list(getVoorrangVolgorde() if volgorde is None else volgorde)
    rang = {soort: i for i, soort in enumerate(volgorde)}
    kandidaten_per_tabel = defaultdict(list)
    for soort in sorted(claims, key=lambda s: (rang.get(s, len(rang)), s)):
        for tabel in claims[soort]:
            kandidaten_per_tabel[tabel].append(soort)

    besluiten = {}
    for tabel in sorted(kandidaten_per_tabel):
        kandidaten = kandidaten_per_tabel[tabel]
        besluit = {'tabel': tabel, 'collectie': collectienaam, 'kandidaten': list(kandidaten)}
        if tabel in instellingen:
            ingesteld = instellingen[tabel]
            if ingesteld is None or ingesteld in kandidaten:
                besluiten[tabel] = dict(besluit, gekozen=ingesteld, bron=BRON_INSTELLING)
                continue
            besluit['ongeldige_instelling'] = ingesteld
        elif len(kandidaten) < 2:
            continue
        besluiten[tabel] = dict(besluit, gekozen=kandidaten[0], bron=BRON_REGEL)
    return besluiten


def getUitTeSluitenTabellen(soort, besluiten):
    """Retourneer de tabellen die de pipeline van een soort moet overslaan: die een andere (of geen) soort krijgen."""
    return sorted(tabel for tabel, besluit in besluiten.items()
                  if soort in besluit['kandidaten'] and besluit['gekozen'] != soort)


def getMelder(besluit):
    """Retourneer de soort waarvan de taak een besluit meldt: de gekozen soort, anders de eerste kandidaat."""
    return besluit['gekozen'] if besluit['gekozen'] is not None else besluit['kandidaten'][0]


def isWaarschuwing(besluit):
    """True als een besluit een waarschuwing geeft: gekozen door de vaste regel (geen bruikbare instelling)."""
    return besluit['bron'] == BRON_REGEL


def pasUitsluitingToe(pipeline, uitsluiten):
    """Sluit tabellen uit in een harmonisatie-pipeline, zonder de pipeline zelf te wijzigen.

    Vooraan komt ``{$match: {table: {$nin: [...]}}}``; MongoDB voegt
    opeenvolgende $match-fasen samen. Bij de incrementele cyclus komt de
    delta-$match (delta_transform.maakDeltaHarmonizePipeline) daar nog vóór,
    zodat de uitsluiting ook daar geldt.

    Args:
        pipeline: lijst met aggregatiefasen
        uitsluiten: tabellen om over te slaan

    Returns:
        Nieuwe pipeline (diepe kopie), of de pipeline zelf als er niets uit te sluiten is
    """
    if not uitsluiten:
        return pipeline
    nieuw = copy.deepcopy(pipeline)
    nieuw.insert(0, {'$match': {'table': {'$nin': sorted(uitsluiten)}}})
    return nieuw


# ============================================================
# Melden
# ============================================================

def maakMeldingTekst(besluit):
    """Leesbare tekst voor de waarschuwing bij een besluit van de vaste regel."""
    kandidaten = ', '.join(besluit['kandidaten'])
    if besluit.get('ongeldige_instelling') is not None:
        oorzaak = (f"De instelling {besluit['tabel']}: {besluit['ongeldige_instelling']} in {SECTIE_VOORRANG} "
                   f"(correcties.yml) is genegeerd: die soort selecteert de tabel niet (kandidaten: {kandidaten}).")
    else:
        oorzaak = f"Tabel {besluit['tabel']} wordt geselecteerd door de pipelines van {kandidaten}."
    return (f"{oorzaak} Volgens de voorrangsregel harmoniseert {besluit['gekozen']} hem "
            f"(collectie {besluit.get('collectie')}). Leg de keuze vast in {SECTIE_VOORRANG} in correcties.yml "
            f"(tabel: soort, of een lege waarde voor geen enkele soort) om deze waarschuwing weg te nemen.")


def meldBesluiten(soort, besluiten):
    """Meld de besluiten waarvoor deze soort de melder is (getMelder) in het log en het run-document.

    Schrijft de besluiten naar ``tellingen.transform.harmonisatie_voorrang.<soort>``
    en geeft per besluit van de vaste regel een waarschuwing
    (SOORT_TABEL_DUBBEL_GESELECTEERD). Zonder run (een DAG zonder
    run-document) alleen het log.

    Args:
        soort: soort van de lopende Harmonize-taak
        besluiten: dict tabel -> besluit (bepaalBesluiten)

    Returns:
        Lijst met de gemelde besluiten
    """
    eigen = [besluiten[tabel] for tabel in sorted(besluiten) if getMelder(besluiten[tabel]) == soort]
    for besluit in eigen:
        if isWaarschuwing(besluit):
            tekst = maakMeldingTekst(besluit)
            logger.warning(tekst)
            foutbeleid.meld(foutbeleid.NIVEAU_WAARSCHUWING, foutbeleid.SOORT_TABEL_DUBBEL_GESELECTEERD, tekst,
                            details={k: besluit.get(k) for k in ('tabel', 'collectie', 'kandidaten', 'gekozen',
                                                                 'ongeldige_instelling') if k in besluit})
        else:
            logger.info(f"Tabel {besluit['tabel']} (kandidaten {', '.join(besluit['kandidaten'])}): volgens "
                        f"{SECTIE_VOORRANG} in correcties.yml "
                        f"{'door geen enkele soort' if besluit['gekozen'] is None else 'door ' + besluit['gekozen']} "
                        f"geharmoniseerd.")
    if eigen:
        foutbeleid.schrijfTelling(f'{TELLING_VOORRANG}.{soort}', eigen)
    return eigen


def bepaalVoorrang(soort, collectienaam, stagingcollectie, correcties):
    """Bepaal voor de taak Harmonize_<soort> welke tabellen zijn pipeline moet overslaan, en meld de besluiten.

    Args:
        soort: soort van de taak
        collectienaam: naam van de staging-collectie van de taak
        stagingcollectie: pymongo-collectie (voor distinct)
        correcties: dict uit harmonize_functions.laadCorrecties()

    Returns:
        Dict met 'uitsluiten' (gesorteerde lijst met tabellen) en 'besluiten'
        (de besluiten over tabellen die deze soort selecteert)
    """
    soorten = getHarmonizeSoorten()
    if soort not in soorten:
        logger.info(f"Soort {soort} heeft geen eigen harmonisatietaak; geen voorrang bepaald.")
        return {'uitsluiten': [], 'besluiten': {}}
    claims = bepaalClaims(stagingcollectie, collectienaam, soorten)
    if soort not in claims:
        return {'uitsluiten': [], 'besluiten': {}}
    besluiten = bepaalBesluiten(claims, leesVoorrangInstellingen(correcties), collectienaam,
                                getVoorrangVolgorde(soorten))
    besluiten = {tabel: besluit for tabel, besluit in besluiten.items() if soort in besluit['kandidaten']}
    meldBesluiten(soort, besluiten)
    uitsluiten = getUitTeSluitenTabellen(soort, besluiten)
    if uitsluiten:
        logger.info(f"Harmonize_{soort} slaat {len(uitsluiten)} tabel(len) over die een andere pipeline "
                    f"harmoniseert of die geen soort krijgen: {uitsluiten}")
    return {'uitsluiten': uitsluiten, 'besluiten': besluiten}
