"""
Unit tests voor de artefactsoort uit de ABR-materiaalcode (issue 86, wasstraat/artefactsoort_materiaal.py).

De RAAP-tabel ARTEFACT wordt sinds issue 86 geladen. Hij wordt door de
algemene soort Artefact geharmoniseerd en heeft daardoor geen artefactsoort,
wel een materiaalcode (kolom MATERIAAL: ODL, OPH, MFE, GLS, KER, PYP ...).
Transform 2 leidt de artefactsoort af uit de kolommen ABR-materiaal en
ABR-submateriaal van het blad Objecten (omgekeerde opzoeking langs de
ABR-thesaurus). Getest wordt:

- de artefactsoorten uit de Delftse harmonisatie-Excel;
- de afleiding per code met een ABR-thesaurus die de Delftse materialen
  nabootst (zelfde URI's, zelfde ouder-kindrelaties): eenduidige codes, de
  gelijke stand bij Metaal en Munt, een onderverdeeld materiaal (Keramiek,
  Organisch), een code één niveau boven de soort (OPH boven OPHT) en codes
  zonder soort;
- zetArtefactsoortUitMateriaalcode op een nagebootste Single_Store: alleen
  artefacten zonder artefactsoort, de incrementele filter, de telling en de
  waarschuwing voor codes zonder soort.
"""
import os
import sys
import types

import pandas as pd
import pytest
from bson import ObjectId

# Mock shared.image_util (wordt via bronbestanden/opruimen geïmporteerd door image_import.py)
if "shared.image_util" not in sys.modules:
    sys.modules["shared.image_util"] = types.ModuleType("shared.image_util")

import shared.const as const
import wasstraat.artefactsoort_materiaal as am
import wasstraat.foutbeleid as foutbeleid
import wasstraat.harmonizer as harmonizer
from tests.unit import nep_mongo
from tests.unit.test_delta_transform import UitgebreideCollectie, matchtMetRegex


ROOT = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
DELFT_EXCEL = os.path.join(ROOT, 'data', 'delft', 'wasstraat_config', 'Wasstraat_Config_HarmonizeV3.xlsx')
ABR = 'https://data.cultureelerfgoed.nl/term/id/abr/'

# ABR-materialen zoals in de Delftse thesaurus (abr_versie_01122018.xlsx): (primary_key, ouder, code, begrip, uri)
MATERIALEN = [
    (1, None, None, 'Materialen', const.ABR_URI_MATERIALEN),
    (10, 1, 'GLS', 'Glas', const.ABR_URI_GLAS),
    (20, 1, 'KER', 'Keramiek', const.ABR_URI_KARAMIEK),
    (21, 20, 'KBW', 'Bouwaardewerk', const.ABR_URI_BOUWAARDEWERK),
    (22, 20, 'KHL', 'Huttenleem', ABR + 'a37c175c-0000-0000-0000-000000000000'),
    (23, 22, 'KKP', 'Pijpaarde', ABR + '0555d2ff-0000-0000-0000-000000000000'),
    (24, 20, None, 'Aardewerk', ABR + '9084ba17-eefe-44db-8eab-d7b746668d9b'),
    (30, 1, 'MXX', 'Metaal', const.ABR_URI_METAAL),
    (31, 30, 'MFE', 'Ijzer', ABR + '2f766fbd-0000-0000-0000-000000000000'),
    (32, 31, 'MGI', 'Gietijzer', ABR + '960bedce-0000-0000-0000-000000000000'),
    (33, 30, 'MCU', 'Koper', ABR + '46771516-0000-0000-0000-000000000000'),
    (40, 1, 'OXX', 'Organisch', const.ABR_URI_ORGANISCH),
    (41, 40, 'ODL', 'Leer', const.ABR_URI_LEER),
    (42, 40, 'ODX', 'Dierlijk', ABR + '43a39d52-0000-0000-0000-000000000000'),
    (43, 42, 'ODB', 'Dierlijk Bot', const.ABR_URI_DIERLIJK_BOT),
    (44, 40, 'OPX', 'Plantaardig', ABR + 'c85037d7-0000-0000-0000-000000000000'),
    (45, 44, 'OPH', 'Hout/Houtskool', ABR + '5fcd583e-0000-0000-0000-000000000000'),
    (46, 45, 'OPHT', 'Hout', const.ABR_URI_HOUT),
    (47, 45, 'OPHK', 'Houtskool', ABR + '422583f5-0000-0000-0000-000000000000'),
    (48, 40, 'OTE', 'Textiel', const.ABR_URI_TEXTIEL),
    (50, 1, 'SXX', 'Steen', const.ABR_URI_STEEN),
    (51, 50, 'STX', 'Natuursteen', ABR + 'e063fc0a-0000-0000-0000-000000000000'),
    (52, 51, 'SGR', 'Graniet', ABR + '74ac3c69-0000-0000-0000-000000000000'),
    (60, 1, 'GEM', 'Gemengd', ABR + '6047ce7c-0000-0000-0000-000000000000'),
    # Dezelfde code buiten Materialen (artefacttypen): telt niet mee
    (90, None, None, 'Artefacten', const.ABR_URI_ARTEFACTEN),
    (91, 90, 'GLS', 'Glazen voorwerp', ABR + 'ffffffff-0000-0000-0000-000000000000'),
]


def abrDocs():
    """De materialen als ABR-documenten in Single_Store (de ABR-tabel levert floats voor de sleutels)."""
    return [{'_id': ObjectId(), 'soort': 'ABR', 'primary_key': float(pk),
             'parentID': float('nan') if ouder is None else float(ouder),
             'code': code if code else float('nan'), 'concept': begrip, 'uri': uri}
            for pk, ouder, code, begrip, uri in MATERIALEN]


@pytest.fixture
def delftExcel(monkeypatch):
    monkeypatch.setattr(harmonizer, 'AIRFLOW_WASSTRAAT_CONFIG', DELFT_EXCEL)


@pytest.fixture
def soorten(delftExcel):
    return am.leesArtefactsoorten()


@pytest.fixture
def thesaurus():
    return am.maakThesaurus(abrDocs())


# ============================================================
# Gegevens
# ============================================================

@pytest.mark.unit
class TestGegevens:

    def test_artefactsoorten_uit_de_delftse_excel(self, soorten):
        """Alle objecten die van Artefact overerven, behalve Onbekend (geen ABR-materiaal)."""
        assert [s['soort'] for s in soorten] == ['Hout', 'Leer', 'Kleipijp', 'Steen', 'Glas', 'Metaal', 'Munt',
                                                 'Aardewerk', 'Menselijk_Bot', 'Bouwaardewerk', 'Dierlijk_Bot',
                                                 'Schelp', 'Textiel']
        per_soort = {s['soort']: s for s in soorten}
        assert per_soort['Hout'] == {'soort': 'Hout', 'materiaal': const.ABR_URI_ORGANISCH,
                                     'submateriaal': const.ABR_URI_HOUT}
        assert per_soort['Metaal']['submateriaal'] is None and per_soort['Munt']['submateriaal'] is None
        assert per_soort['Kleipijp'] == {'soort': 'Kleipijp', 'materiaal': const.ABR_URI_KARAMIEK, 'submateriaal': None}

    def test_objecten_als_dataframe(self):
        objecten = pd.DataFrame([
            {'Object': 'Ignore', 'Overerven': None, 'ABR-materiaal': None, 'ABR-submateriaal': None},
            {'Object': 'Vondst', 'Overerven': None, 'ABR-materiaal': const.ABR_URI_GLAS, 'ABR-submateriaal': None},
            {'Object': ' Glas ', 'Overerven': 'Artefact', 'ABR-materiaal': const.ABR_URI_GLAS, 'ABR-submateriaal': float('nan')},
            {'Object': 'Onbekend', 'Overerven': 'Artefact', 'ABR-materiaal': None, 'ABR-submateriaal': None},
        ])
        assert am.leesArtefactsoorten(objecten) == [{'soort': 'Glas', 'materiaal': const.ABR_URI_GLAS,
                                                     'submateriaal': None}]

    def test_thesaurus_alleen_materialen(self, thesaurus):
        assert thesaurus['per_code']['GLS'] == [10]
        assert 'MATERIALEN' not in thesaurus['per_code']
        assert sorted(thesaurus['kinderen'][45]) == [46, 47]


# ============================================================
# Afleiding per code
# ============================================================

@pytest.mark.unit
class TestBepaalArtefactsoort:

    @pytest.mark.parametrize('code, soort', [
        ('ODL', 'Leer'),            # ABR-submateriaal van Leer
        ('GLS', 'Glas'),            # ABR-materiaal van alleen Glas
        ('SGR', 'Steen'),           # onder Natuursteen onder Steen
        ('MFE', 'Metaal'),          # onder Metaal: Metaal en Munt, de naam van het begrip beslist
        ('MGI', 'Metaal'),
        ('MCU', 'Metaal'),
        ('MXX', 'Metaal'),
        ('OPH', 'Hout'),            # één niveau boven OPHT (Hout)
        ('OPHT', 'Hout'),
        ('ODB', 'Dierlijk_Bot'),
        ('ODX', 'Dierlijk_Bot'),    # één niveau boven ODB
        ('KBW', 'Bouwaardewerk'),
        ('OTE', 'Textiel'),
        (' odl ', 'Leer'),          # hoofdletterongevoelig, zonder spaties
    ])
    def test_eenduidig(self, soorten, thesaurus, code, soort):
        assert am.bepaalArtefactsoort(code, soorten, thesaurus) == (soort, None)

    @pytest.mark.parametrize('code', ['KER', 'KHL', 'KKP', 'OXX', 'OPX', 'OPHK'])
    def test_niet_eenduidig(self, soorten, thesaurus, code):
        """Keramiek (Aardewerk, Bouwaardewerk, Kleipijp) en Organisch zijn onderverdeeld."""
        assert am.bepaalArtefactsoort(code, soorten, thesaurus) == (None, am.REDEN_NIET_EENDUIDIG)

    @pytest.mark.parametrize('code, reden', [
        ('PYP', am.REDEN_CODE_ONBEKEND),   # RAAP-code voor pijpen, geen ABR-materiaal
        ('', am.REDEN_CODE_ONBEKEND),
        (None, am.REDEN_CODE_ONBEKEND),
        ('GEM', am.REDEN_GEEN_SOORT),       # Gemengd: geen artefactsoort
    ])
    def test_zonder_soort(self, soorten, thesaurus, code, reden):
        assert am.bepaalArtefactsoort(code, soorten, thesaurus) == (None, reden)

    def test_gelijke_stand_zonder_passende_naam(self, thesaurus):
        """Twee soorten met hetzelfde ABR-materiaal en geen van beide met de naam van het begrip."""
        soorten = [{'soort': 'Munt', 'materiaal': const.ABR_URI_METAAL, 'submateriaal': None},
                   {'soort': 'Penning', 'materiaal': const.ABR_URI_METAAL, 'submateriaal': None}]
        assert am.bepaalArtefactsoort('MFE', soorten, thesaurus) == (None, am.REDEN_NIET_EENDUIDIG)

    def test_ouder_buiten_de_thesaurus(self, soorten):
        """Een parentID die niet bestaat, stopt de zoektocht omhoog zonder fout."""
        docs = abrDocs() + [{'_id': ObjectId(), 'soort': 'ABR', 'primary_key': 99.0, 'parentID': 12345.0,
                             'code': 'XYZ', 'concept': 'Los', 'uri': ABR + 'los'}]
        thesaurus = am.maakThesaurus(docs)
        assert 'XYZ' not in thesaurus['per_code']  # niet onder Materialen
        thesaurus['per_code']['XYZ'] = [99]
        assert am.bepaalArtefactsoort('XYZ', soorten, thesaurus) == (None, am.REDEN_GEEN_SOORT)

    def test_lege_thesaurus(self, soorten):
        assert am.bepaalArtefactsoort('ODL', soorten, am.maakThesaurus([])) == (None, am.REDEN_CODE_ONBEKEND)

    @pytest.mark.parametrize('waarde, leeg', [(None, True), (float('nan'), True), ('', True), (' - ', True),
                                              ('Onbekend', True), ('Hout', False)])
    def test_lege_artefactsoort(self, waarde, leeg):
        assert am.isLegeArtefactsoort(waarde) == leeg


# ============================================================
# Transform 2: zetArtefactsoortUitMateriaalcode
# ============================================================

def artefact(code, artefactsoort=None, tabel='ARTEFACT', **extra):
    doc = {'_id': ObjectId(), 'soort': 'Artefact', 'projectcd': 'DC112', 'materiaalcode': code,
           'brondata': {'table': tabel}}
    if artefactsoort is not None:
        doc['artefactsoort'] = artefactsoort
    doc.update(extra)
    return doc


@pytest.fixture
def meldingen(monkeypatch):
    """Vang de meldingen en tellingen voor het run-document op."""
    opgevangen = {'meld': [], 'telling': []}
    monkeypatch.setattr(foutbeleid, 'meld', lambda *args, **kwargs: opgevangen['meld'].append((args, kwargs)))
    monkeypatch.setattr(foutbeleid, 'schrijfTelling', lambda pad, waarde: opgevangen['telling'].append((pad, waarde)))
    monkeypatch.setattr(nep_mongo, 'matcht', matchtMetRegex)
    return opgevangen


@pytest.mark.unit
class TestZetArtefactsoort:

    def maakCollectie(self, docs):
        col = UitgebreideCollectie('Single_Store')
        col.docs = abrDocs() + docs
        return col

    def test_raap_artefacten(self, delftExcel, meldingen):
        docs = [artefact('ODL'), artefact('ODL'), artefact('OPH'), artefact('MFE'), artefact('GLS'),
                artefact('KER'), artefact('PYP'), artefact('PYP'),
                artefact('ODL', artefactsoort='Textiel', tabel='ARTF_OTE'),   # heeft al een soort
                artefact('MFE', artefactsoort=' onbekend '),                  # telt als leeg
                artefact(None), {'_id': ObjectId(), 'soort': 'Vondst', 'materiaalcode': 'ODL'}]
        col = self.maakCollectie(docs)
        telling = am.zetArtefactsoortUitMateriaalcode(col)
        soort = {d['_id']: d.get('artefactsoort') for d in col.docs}
        assert [soort[d['_id']] for d in docs] == ['Leer', 'Leer', 'Hout', 'Metaal', 'Glas', None, None, None,
                                                   'Textiel', 'Metaal', None, None]
        assert telling['afgeleid'] == {'Leer': 2, 'Hout': 1, 'Metaal': 2, 'Glas': 1}
        assert telling['niet_afgeleid'] == {'KER': 1, 'PYP': 2}
        assert telling['per_code']['KER'] == am.REDEN_NIET_EENDUIDIG
        # Eén waarschuwing met het aantal en de codes, en de telling in het run-document
        assert len(meldingen['meld']) == 1
        args, kwargs = meldingen['meld'][0]
        assert args[:2] == (foutbeleid.NIVEAU_WAARSCHUWING, foutbeleid.SOORT_ARTEFACTSOORT_NIET_AFGELEID)
        assert kwargs['aantal'] == 3 and 'PYP (2, geen ABR-materiaalcode)' in args[2]
        assert meldingen['telling'] == [(am.TELLING, telling)]

    def test_alles_afgeleid_geen_waarschuwing(self, delftExcel, meldingen):
        col = self.maakCollectie([artefact('ODL'), artefact('SGR')])
        telling = am.zetArtefactsoortUitMateriaalcode(col)
        assert telling['afgeleid'] == {'Leer': 1, 'Steen': 1} and telling['niet_afgeleid'] == {}
        assert meldingen['meld'] == []

    def test_niets_te_doen_leest_de_excel_niet(self, monkeypatch, meldingen):
        monkeypatch.setattr(harmonizer, 'AIRFLOW_WASSTRAAT_CONFIG', '/bestaat/niet.xlsx')
        col = self.maakCollectie([artefact('ODL', artefactsoort='Leer')])
        assert am.zetArtefactsoortUitMateriaalcode(col) == {'afgeleid': {}, 'niet_afgeleid': {}, 'per_code': {}}
        assert meldingen['telling'] == []

    def test_incrementeel_alleen_de_delta(self, delftExcel, meldingen):
        oud, nieuw = artefact('ODL'), artefact('ODL', delta_run='run-1')
        col = self.maakCollectie([oud, nieuw])
        am.zetArtefactsoortUitMateriaalcode(col, {'delta_run': 'run-1'})
        soort = {d['_id']: d.get('artefactsoort') for d in col.docs}
        assert soort[nieuw['_id']] == 'Leer' and soort[oud['_id']] is None

    def test_filter(self):
        filt = am.maakFilter({'delta_run': 'x'})
        assert filt['$and'][0] == {'delta_run': 'x'}
        assert filt['$and'][1]['soort'] == 'Artefact'


@pytest.mark.unit
class TestInTransform2:
    """enhanceAllAttributes roept de afleiding aan, na de identificatie van alle documenten."""

    def test_raap_artefact_krijgt_artefactsoort(self, monkeypatch, delftExcel, meldingen):
        import shared.config as config
        import wasstraat.harmonize_functions as harmonize_functions
        import wasstraat.setAttributes_functions as setAttributes_functions
        from tests.unit.test_delta_transform import UitgebreideClient
        client = UitgebreideClient()
        col = client[config.DB_ANALYSE][config.COLL_ANALYSE]
        raap = artefact('OPH', projectcd='DC008', vondstnr='0', artefactnr='1')
        col.docs = abrDocs() + [raap, artefact('PYP')]
        monkeypatch.setattr(harmonize_functions, 'laadCorrecties', lambda: {})
        monkeypatch.setattr(setAttributes_functions.pymongo, 'MongoClient', lambda *a, **k: client)
        setAttributes_functions.enhanceAllAttributes()
        doc = next(d for d in col.docs if d['_id'] == raap['_id'])
        assert doc['artefactsoort'] == 'Hout' and doc['artefactnr'] == 1
        assert [t for pad, t in meldingen['telling'] if pad == am.TELLING] == [
            {'afgeleid': {'Hout': 1}, 'niet_afgeleid': {'PYP': 1}, 'per_code': {'OPH': 'Hout', 'PYP': am.REDEN_CODE_ONBEKEND}}]
