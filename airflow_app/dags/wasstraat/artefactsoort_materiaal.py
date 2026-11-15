"""Artefactsoort uit de ABR-materiaalcode (Transform 2, issue 86).

De harmonisatie geeft een artefact zijn artefactsoort via de tabel waaruit
het komt (blad ``Objecten`` van de harmonisatie-Excel: de tabel ``METAAL``
levert Metaal). Een tabel die door de algemene soort ``Artefact`` wordt
geharmoniseerd, levert geen artefactsoort. Heeft zo'n rij wel een
materiaalcode (kolom ``MAT`` of ``MATERIAAL``, veld ``materiaalcode``), dan
leidt deze module de artefactsoort daaruit af. In Delft gaat het om de
RAAP-tabel ``ARTEFACT`` (132 rijen in DC008, DC024 en DC112, materiaalcodes
als ``ODL``, ``OPH`` en ``MFE``), die sinds issue 86 wordt geladen.

De afleiding is een omgekeerde opzoeking in de kolommen ``ABR-materiaal`` en
``ABR-submateriaal`` van het blad Objecten (de URI's die de harmonisatie ook
in ``abr_materiaal`` en ``abr_submateriaal`` zet), langs de ABR-thesaurus
(documenten van soort ``ABR`` in Single_Store, met ``code``, ``uri`` en
``parentID``):

1. zoek het ABR-begrip met de materiaalcode onder Materialen
   (``const.ABR_URI_MATERIALEN``; hoofdletterongevoelig);
2. loop van het begrip omhoog naar Materialen. Bij het eerste begrip dat
   ABR-submateriaal (of, als geen soort het als submateriaal heeft,
   ABR-materiaal) van een artefactsoort is:

   - precies één soort: die soort (``ODL`` Leer, ``GLS`` Glas, ``SXX`` en
     alles daaronder Steen);
   - meer soorten waarvan geen enkele een submateriaal heeft: de soort met
     dezelfde naam als het begrip (``MXX`` Metaal en daaronder ``MFE``,
     ``MCU``, ``MPB``: Metaal, niet Munt, want een materiaalcode zegt niets
     over de vorm van het voorwerp);
   - anders is de code niet eenduidig (``KER`` Keramiek: Aardewerk,
     Bouwaardewerk of Kleipijp; ``OXX`` Organisch); hogerop wordt het alleen
     algemener;
3. geen soort gevonden: kijk één niveau lager. Wijzen de begrippen direct
   onder de code naar precies één soort, dan is het die soort (``OPH``
   Hout/Houtskool, met daaronder ``OPHT`` Hout: Hout).

Een code zonder passende soort (geen ABR-materiaalcode, zoals ``PYP``, of
niet eenduidig) laat de artefactsoort leeg: het artefact wordt geladen als
``Onbekend``, zoals elk artefact zonder artefactsoort. Die rijen worden per
code geteld en gemeld als waarschuwing (``foutbeleid.SOORT_ARTEFACTSOORT_NIET_AFGELEID``).
De tellingen staan in het run-document onder
``tellingen.transform.artefactsoort_uit_materiaalcode``.
"""
import re

import pandas as pd

import shared.const as const
import wasstraat.foutbeleid as foutbeleid
import wasstraat.harmonizer as harmonizer
import logging

logger = logging.getLogger("airflow.task")

# Pad onder tellingen in het run-document
TELLING = 'transform.artefactsoort_uit_materiaalcode'
# Redenen waarom een code geen artefactsoort oplevert
REDEN_CODE_ONBEKEND = 'geen ABR-materiaalcode'
REDEN_NIET_EENDUIDIG = 'niet eenduidig'
REDEN_GEEN_SOORT = 'geen artefactsoort bij dit materiaal'
# Waarden van artefactsoort die als leeg gelden (zoals merge_functions.AGGR_PHASE_ARTEFACTSOORT)
LEGE_ARTEFACTSOORTEN = ('', '-', 'onbekend')
LEGE_ARTEFACTSOORT_REGEX = re.compile(r'^\s*(-|onbekend)?\s*$', re.IGNORECASE)
# Maximaal aantal voorbeelden in de melding
MAX_VOORBEELDEN = 10


# ============================================================
# Gegevens: artefactsoorten uit de Excel en de ABR-thesaurus
# ============================================================

def _tekst(waarde):
    """Tekst zonder spaties aan begin en eind, of None voor een lege waarde (ook NaN)."""
    if waarde is None or (isinstance(waarde, float) and waarde != waarde):
        return None
    tekst = str(waarde).strip()
    return tekst or None


def leesArtefactsoorten(objecten=None):
    """Lees de artefactsoorten met hun ABR-materiaal en ABR-submateriaal uit het blad Objecten.

    Een artefactsoort is een object dat overerft van ``Artefact`` (kolom
    Overerven). Soorten zonder ABR-materiaal (Onbekend) doen niet mee.

    Args:
        objecten: optioneel het blad Objecten als DataFrame; standaard gelezen uit
            de harmonisatie-Excel (harmonizer.AIRFLOW_WASSTRAAT_CONFIG)

    Returns:
        Lijst met dicts (soort, materiaal, submateriaal) in de volgorde van het blad
    """
    if objecten is None:
        objecten = pd.read_excel(harmonizer.AIRFLOW_WASSTRAAT_CONFIG, sheet_name='Objecten')
    soorten = []
    for _, rij in objecten.iterrows():
        soort = _tekst(rij.get('Object'))
        if soort is None or _tekst(rij.get('Overerven')) != 'Artefact':
            continue
        materiaal, submateriaal = _tekst(rij.get('ABR-materiaal')), _tekst(rij.get('ABR-submateriaal'))
        if materiaal is None and submateriaal is None:
            continue
        soorten.append({'soort': soort, 'materiaal': materiaal, 'submateriaal': submateriaal})
    return soorten


def _sleutel(waarde):
    """primary_key of parentID als geheel getal (de ABR-tabel levert floats), of None."""
    try:
        if waarde is None or (isinstance(waarde, float) and waarde != waarde):
            return None
        return int(waarde)
    except (TypeError, ValueError):
        return None


def maakThesaurus(abr_docs):
    """Bouw de materialen uit de ABR-thesaurus op: per code de begrippen onder Materialen.

    Args:
        abr_docs: documenten van soort ABR (met primary_key, parentID, uri, code en concept)

    Returns:
        Dict met 'begrippen' (primary_key -> document), 'kinderen' (primary_key ->
        lijst met primary_keys) en 'per_code' (code in hoofdletters -> lijst met
        primary_keys van begrippen onder Materialen)
    """
    begrippen, kinderen = {}, {}
    for doc in abr_docs:
        pk = _sleutel(doc.get('primary_key'))
        if pk is not None:
            begrippen[pk] = doc
    for pk, doc in begrippen.items():
        ouder = _sleutel(doc.get('parentID'))
        if ouder is not None and ouder != pk:
            kinderen.setdefault(ouder, []).append(pk)
    per_code = {}
    wortels = [pk for pk, doc in begrippen.items() if doc.get('uri') == const.ABR_URI_MATERIALEN]
    gezien, te_doen = set(), list(wortels)
    while te_doen:
        pk = te_doen.pop()
        if pk in gezien:
            continue
        gezien.add(pk)
        code = _tekst(begrippen[pk].get('code'))
        if code is not None and pk not in wortels:
            per_code.setdefault(code.upper(), []).append(pk)
        te_doen.extend(kinderen.get(pk, []))
    return {'begrippen': begrippen, 'kinderen': kinderen, 'per_code': per_code}


# ============================================================
# Afleiding
# ============================================================

def _naam(tekst):
    """Naam om een soort met een begrip te vergelijken: kleine letters, _ als spatie."""
    return str(tekst or '').replace('_', ' ').strip().lower()


def _kandidaten(uri, soorten):
    """Soorten met dit begrip als ABR-submateriaal, anders als ABR-materiaal."""
    if not uri:
        return []
    sub = [s for s in soorten if s['submateriaal'] == uri]
    return sub if sub else [s for s in soorten if s['materiaal'] == uri]


def _kies(kandidaten, begrip):
    """Kies uit de soorten bij één begrip: één soort, of bij een gelijke stand de soort met de naam van het begrip.

    Returns:
        De soort, of None als de keuze niet eenduidig is
    """
    namen = list(dict.fromkeys(s['soort'] for s in kandidaten))
    if len(namen) == 1:
        return namen[0]
    if any(s['submateriaal'] for s in kandidaten if s['materiaal'] == begrip.get('uri')):
        # Het materiaal is onderverdeeld (Keramiek, Organisch): de code zegt niet welk deel
        return None
    gelijk = [naam for naam in namen
              if _naam(naam) in (_naam(begrip.get('concept')), _naam(begrip.get('label')))]
    return gelijk[0] if len(gelijk) == 1 else None


def bepaalArtefactsoort(code, soorten, thesaurus):
    """Bepaal de artefactsoort bij een ABR-materiaalcode (zie de moduledocumentatie).

    Args:
        code: materiaalcode, bijv. 'OPH'
        soorten: lijst uit leesArtefactsoorten
        thesaurus: dict uit maakThesaurus

    Returns:
        Tuple (soort of None, reden of None)
    """
    sleutel = _tekst(code)
    pks = thesaurus['per_code'].get(sleutel.upper()) if sleutel else None
    if not pks:
        return None, REDEN_CODE_ONBEKEND
    begrippen, kinderen = thesaurus['begrippen'], thesaurus['kinderen']
    gevonden = set()
    for pk in pks:
        # 2. omhoog, tot en met het eerste begrip met kandidaten
        huidig, bezocht, soort, eenduidig = pk, set(), None, True
        while huidig is not None and huidig not in bezocht:
            bezocht.add(huidig)
            begrip = begrippen.get(huidig)
            if begrip is None:
                # Ouder die niet in de thesaurus staat
                break
            kandidaten = _kandidaten(begrip.get('uri'), soorten)
            if kandidaten:
                soort = _kies(kandidaten, begrip)
                eenduidig = soort is not None
                break
            huidig = _sleutel(begrip.get('parentID'))
        if soort is None:
            # 3. één niveau lager
            onder = {s['soort'] for kind in kinderen.get(pk, [])
                     for s in _kandidaten(begrippen[kind].get('uri'), soorten)}
            if len(onder) == 1:
                soort = onder.pop()
            elif len(onder) > 1:
                eenduidig = False
        if soort is not None:
            gevonden.add(soort)
        elif not eenduidig:
            gevonden.add(None)
    if len(gevonden) == 1 and None not in gevonden:
        return gevonden.pop(), None
    if gevonden:
        return None, REDEN_NIET_EENDUIDIG
    return None, REDEN_GEEN_SOORT


def isLegeArtefactsoort(waarde):
    """True als een artefactsoort ontbreekt of leeg, '-' of 'onbekend' is."""
    return waarde is None or (isinstance(waarde, float) and waarde != waarde) \
        or str(waarde).strip().lower() in LEGE_ARTEFACTSOORTEN


# ============================================================
# Transform 2
# ============================================================

def maakFilter(doc_filter=None):
    """Filter op de artefacten zonder artefactsoort met een materiaalcode.

    Args:
        doc_filter: optioneel extra filter (bijv. delta_run in de incrementele cyclus)
    """
    filt = {'soort': 'Artefact', 'materiaalcode': {'$exists': True, '$nin': [None, '']},
            '$or': [{'artefactsoort': {'$exists': False}}, {'artefactsoort': None},
                    {'artefactsoort': LEGE_ARTEFACTSOORT_REGEX}]}
    if doc_filter:
        filt = {'$and': [doc_filter, filt]}
    return filt


def zetArtefactsoortUitMateriaalcode(analyseCol, doc_filter=None, objecten=None):
    """Geef artefacten zonder artefactsoort de artefactsoort van hun ABR-materiaalcode (Transform 2).

    Leest de artefactsoorten uit het blad Objecten en de ABR-thesaurus uit
    Single_Store, bepaalt per materiaalcode de soort (bepaalArtefactsoort) en
    zet die met één update per code. Rijen waarvan de code geen soort oplevert,
    blijven zonder artefactsoort (Onbekend) en worden gemeld als waarschuwing.

    Args:
        analyseCol: Single_Store-collectie
        doc_filter: optioneel extra filter (incrementele cyclus: delta_run)
        objecten: optioneel het blad Objecten (voor tests)

    Returns:
        Dict met 'afgeleid' (soort -> aantal), 'niet_afgeleid' (code -> aantal) en
        'per_code' (code -> soort of reden)
    """
    filt = maakFilter(doc_filter)
    per_code_aantal = {}
    for groep in analyseCol.aggregate([{'$match': filt}, {'$group': {'_id': '$materiaalcode', 'n': {'$sum': 1}}}]):
        per_code_aantal[groep['_id']] = groep['n']
    telling = {'afgeleid': {}, 'niet_afgeleid': {}, 'per_code': {}}
    if not per_code_aantal:
        logger.info("Geen artefacten zonder artefactsoort met een materiaalcode.")
        return telling

    soorten = leesArtefactsoorten(objecten)
    thesaurus = maakThesaurus(analyseCol.find({'soort': 'ABR'}, {'primary_key': 1, 'parentID': 1, 'uri': 1,
                                                                 'code': 1, 'concept': 1, 'label': 1}))
    if not thesaurus['per_code']:
        logger.warning("Geen ABR-thesaurus met materialen in Single_Store: de artefactsoort is niet af te leiden "
                       "uit de materiaalcode.")

    voorbeelden = []
    for code in sorted(per_code_aantal, key=str):
        aantal = per_code_aantal[code]
        soort, reden = bepaalArtefactsoort(code, soorten, thesaurus)
        sleutel = str(code)
        if soort is not None:
            resultaat = analyseCol.update_many({'$and': [filt, {'materiaalcode': code}]},
                                               {'$set': {'artefactsoort': soort}})
            telling['afgeleid'][soort] = telling['afgeleid'].get(soort, 0) + resultaat.modified_count
            telling['per_code'][sleutel] = soort
            logger.info(f"Materiaalcode {code}: {resultaat.modified_count} artefacten krijgen artefactsoort {soort}.")
        else:
            telling['niet_afgeleid'][sleutel] = aantal
            telling['per_code'][sleutel] = reden
            if len(voorbeelden) < MAX_VOORBEELDEN:
                voorbeelden.append({'materiaalcode': sleutel, 'aantal': aantal, 'reden': reden})

    niet_afgeleid = sum(telling['niet_afgeleid'].values())
    if niet_afgeleid:
        codes = ', '.join(f"{v['materiaalcode']} ({v['aantal']}, {v['reden']})" for v in voorbeelden)
        melding = (f"{niet_afgeleid} artefacten zonder artefactsoort hebben een materiaalcode waaruit geen "
                   f"artefactsoort volgt; ze worden geladen als Onbekend. Codes: {codes}. De afleiding gebruikt de "
                   f"kolommen ABR-materiaal en ABR-submateriaal van het blad Objecten van de harmonisatie-Excel.")
        logger.warning(melding)
        foutbeleid.meld(foutbeleid.NIVEAU_WAARSCHUWING, foutbeleid.SOORT_ARTEFACTSOORT_NIET_AFGELEID, melding,
                        aantal=niet_afgeleid, details=voorbeelden)
    foutbeleid.schrijfTelling(TELLING, telling)
    return telling
