"""
Unit tests voor de voorrang bij de harmonisatie (issue 89, wasstraat/harmonisatie_voorrang.py).

De taken Harmonize_<soort> draaien parallel en schrijven met $merge op _id
naar Single_Store. Selecteren twee pipelines dezelfde staging-tabel, dan won
de pipeline die het laatst klaar was (AW1DeterminatiesJohan: Aardewerk of
Artefact, per run anders). Getest wordt:

- de vaste voorrangsregel (specifieke artefactsoort vóór Artefact, verder de
  volgorde van meta.wasstraat_model) en welke pipelines meedoen (alleen
  pipelines die het _id van het staging-document schrijven);
- de overlapdetectie met de Delftse harmonisatie-Excel en de tabelnamen uit
  de Delftse staging (tests/unit/fixtures/delft_staging_tabellen.json), met een
  nagebootste distinct-aanroep: alleen AW1DeterminatiesJohan is dubbel;
  METAAL OPPERVLAK staat in de projectenlijst, waar alleen Project en
  Vindplaats draaien;
- de besluiten met en zonder instelling in correcties.yml (ook ongeldige
  instellingen), de uitsluiting in de pipeline (ook in de incrementele
  cyclus) en de waarschuwing in het run-document (één keer, door de taak van
  de gekozen soort);
- harmonize_functions.harmonize: dezelfde uitkomst in Single_Store, in welke
  volgorde de taken ook draaien.

De sectie harmonisatie_voorrang van correcties.yml (inlezen en foutgevallen)
staat in tests/unit/test_correcties_yml.py.
"""
import copy
import json
import os
import sys
import types
from unittest.mock import MagicMock

import pytest
from bson import ObjectId

# Mock shared.image_util (wordt via bronbestanden/opruimen geïmporteerd door image_import.py)
if "shared.image_util" not in sys.modules:
    sys.modules["shared.image_util"] = types.ModuleType("shared.image_util")

import shared.config as config
import wasstraat.delta_transform as delta_transform
import wasstraat.foutbeleid as foutbeleid
import wasstraat.harmonisatie_voorrang as voorrang
import wasstraat.harmonize_functions as harmonize_functions
import wasstraat.harmonizer as harmonizer
import wasstraat.meta as meta
import wasstraat.verwerkingsrun as verwerkingsrun
from tests.unit import nep_mongo
from tests.unit.nep_mongo import NepCollectie
from tests.unit.test_delta_transform import UitgebreideClient, matchtMetRegex, startRunMet, SY003_MDB


ROOT = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
DELFT_CONFIG = os.path.join(ROOT, 'data', 'delft', 'wasstraat_config')
DELFT_EXCEL = os.path.join(DELFT_CONFIG, 'Wasstraat_Config_HarmonizeV3.xlsx')
DELFT_CORRECTIES = os.path.join(DELFT_CONFIG, 'correcties.yml')
TABELLEN = json.load(open(os.path.join(os.path.dirname(__file__), 'fixtures', 'delft_staging_tabellen.json'),
                          encoding='utf-8'))['tabellen']
OUD = 'Staging_Projecten_Oud'


@pytest.fixture
def delftExcel(monkeypatch):
    """De Delftse harmonisatie-Excel (in de repo gelijk aan die van de testomgeving)."""
    monkeypatch.setattr(harmonizer, 'AIRFLOW_WASSTRAAT_CONFIG', DELFT_EXCEL)


@pytest.fixture
def correcties(monkeypatch):
    """Lege cache van correcties.yml voor en na de test; geef een functie om een bestand te kiezen."""
    harmonize_functions._correcties_cache = None

    def kies(pad):
        harmonize_functions._correcties_cache = None
        monkeypatch.setattr(harmonize_functions.config, 'AIRFLOW_CORRECTIES_CONFIG', pad)
        return harmonize_functions.laadCorrecties()

    yield kies
    harmonize_functions._correcties_cache = None


@pytest.fixture
def client(monkeypatch):
    """Nagebootste MongoDB voor het run-document."""
    nep = UitgebreideClient()
    monkeypatch.setattr(nep_mongo, 'matcht', matchtMetRegex)
    monkeypatch.setattr(verwerkingsrun, '_getClient', lambda: nep)
    monkeypatch.setattr(delta_transform, '_getClient', lambda: nep)
    return nep


def stagingDelft():
    """Per staging-collectie een nagebootste collectie met één document per tabel uit de Delftse staging."""
    collecties = {}
    for collectie, tabel, _ in TABELLEN:
        collecties.setdefault(collectie, NepCollectie(collectie)).docs.append({'_id': ObjectId(), 'table': tabel})
    return collecties


def alleBesluiten(instellingen=None):
    besluiten = {}
    for naam, col in stagingDelft().items():
        besluiten.update(voorrang.bepaalBesluiten(voorrang.bepaalClaims(col, naam), instellingen, naam))
    return besluiten


# ============================================================
# Klasse 1: voorrangsregel en deelnemende pipelines
# ============================================================

@pytest.mark.unit
class TestVoorrangVolgorde:

    def test_artefactsoorten_voor_artefact(self):
        volgorde = voorrang.getVoorrangVolgorde()
        for soort in meta.lst_artefactsoort:
            assert volgorde.index(soort) < volgorde.index('Artefact'), soort

    def test_verder_de_volgorde_van_meta(self):
        volgorde = voorrang.getVoorrangVolgorde()
        assert volgorde[:6] == ['Put', 'Vlak', 'Spoor', 'Vulling', 'Stelling', 'Aardewerk']
        assert volgorde.index('Vlak') < volgorde.index('Metaal') < volgorde.index('Artefact') < volgorde.index('Monster')
        overig = [s for s in volgorde if s not in meta.lst_artefactsoort and s != 'Artefact']
        assert overig == [s for s in voorrang.getHarmonizeSoorten() if s in overig]

    def test_zelfde_soorten_als_de_taken(self):
        assert sorted(voorrang.getVoorrangVolgorde()) == sorted(voorrang.getHarmonizeSoorten())
        assert 'Foto' not in voorrang.getHarmonizeSoorten()
        assert set(voorrang.getHarmonizeSoorten()) == set(meta.getKeys(meta.HARMONIZE_PIPELINES)) - {'Foto'}

    def test_volgorde_van_een_deelverzameling(self):
        assert voorrang.getVoorrangVolgorde(['Vondst', 'Artefact', 'Glas', 'Put']) == ['Vondst', 'Glas', 'Artefact', 'Put']


@pytest.mark.unit
class TestSelectieFilter:

    def test_excel_pipeline_beide_match_fasen(self, delftExcel):
        pipeline = voorrang.getPipeline('Aardewerk')
        filt = voorrang.getSelectieFilter(pipeline)
        assert filt == {'$and': [pipeline[0]['$match'], pipeline[1]['$match']]}

    def test_vaste_pipeline_project(self):
        assert voorrang.getSelectieFilter(voorrang.getPipeline('Project')) == {'table': 'OPGRAVINGEN'}

    @pytest.mark.parametrize('soort', ['Standplaats', 'Plaatsing', 'Doos'])
    def test_pipelines_met_nieuwe_id_doen_niet_mee(self, soort):
        """Uit één rij van de magazijnlijst maken ze elk een eigen document met een nieuw _id."""
        assert voorrang.getSelectieFilter(voorrang.getPipeline(soort)) is None

    def test_lege_pipeline_doet_niet_mee(self):
        assert voorrang.getPipeline('Bestand') == []
        assert voorrang.getSelectieFilter([]) is None

    def test_zonder_merge_of_merge_op_ander_veld(self):
        assert voorrang.getSelectieFilter([{'$match': {'table': 'A'}}, {'$addFields': {'x': 1}}]) is None
        assert voorrang.getSelectieFilter([{'$match': {'table': 'A'}}, {'$merge': {'into': 'x', 'on': 'key'}}]) is None
        assert voorrang.getSelectieFilter([{'$replaceWith': {'brondata': '$$ROOT'}}, {'$merge': {'into': 'x'}}]) is None

    def test_zonder_match_alle_documenten(self):
        assert voorrang.getSelectieFilter([{'$addFields': {'x': 1}}, {'$merge': {'into': 'x', 'on': '_id'}}]) == {}

    def test_soort_uit_het_argument_van_harmonize(self):
        assert voorrang.bepaalSoort('Glas') == 'Glas'
        assert voorrang.bepaalSoort(meta.getHarmonizePipelines('Project')) == 'Project'
        assert voorrang.bepaalSoort([[{'$match': {'table': 'onbekend'}}]]) is None


# ============================================================
# Klasse 2: overlap in de Delftse staging
# ============================================================

@pytest.mark.unit
class TestOverlapDelft:

    def test_alleen_aw1_determinaties_dubbel(self, delftExcel):
        besluiten = alleBesluiten()
        assert besluiten == {'AW1DeterminatiesJohan': {
            'tabel': 'AW1DeterminatiesJohan', 'collectie': OUD, 'kandidaten': ['Aardewerk', 'Artefact'],
            'gekozen': 'Aardewerk', 'bron': voorrang.BRON_REGEL}}
        assert voorrang.isWaarschuwing(besluiten['AW1DeterminatiesJohan'])

    def test_metaal_oppervlak_door_geen_pipeline_geselecteerd(self, delftExcel):
        """De codetabel staat in de projectenlijst; Vlak en Metaal draaien op Staging_Projecten_Oud."""
        staging = stagingDelft()
        claims = {naam: voorrang.bepaalClaims(col, naam) for naam, col in staging.items()}
        assert not any('METAAL OPPERVLAK' in tabellen for c in claims.values() for tabellen in c.values())
        assert claims['Staging_Projecten_Projectenlijst'] == {'Project': {'OPGRAVINGEN'}, 'Vindplaats': {'VINDPLAATSEN'}}
        assert voorrang.getStagingCollectie('Vlak') == voorrang.getStagingCollectie('Metaal') == OUD

    def test_delftse_correcties_nemen_de_waarschuwing_weg(self, delftExcel, correcties):
        instellingen = voorrang.leesVoorrangInstellingen(correcties(DELFT_CORRECTIES))
        assert instellingen == {'AW1DeterminatiesJohan': 'Aardewerk', 'AARDEWERK 1&2 VOORWERP': None,
                                'AARDEWERK 1 BAKSEL': None}
        besluiten = alleBesluiten(instellingen)
        besluit = besluiten['AW1DeterminatiesJohan']
        assert besluit['gekozen'] == 'Aardewerk' and besluit['bron'] == voorrang.BRON_INSTELLING
        assert not voorrang.isWaarschuwing(besluit)
        # Issue 75: de codetabellen van het aardewerk door geen enkele soort, zonder waarschuwing
        for tabel in ('AARDEWERK 1&2 VOORWERP', 'AARDEWERK 1 BAKSEL'):
            assert besluiten[tabel] == {'tabel': tabel, 'collectie': OUD, 'kandidaten': ['Aardewerk'],
                                        'gekozen': None, 'bron': voorrang.BRON_INSTELLING}
            assert not voorrang.isWaarschuwing(besluiten[tabel])
        assert voorrang.getUitTeSluitenTabellen('Aardewerk', besluiten) == ['AARDEWERK 1 BAKSEL',
                                                                             'AARDEWERK 1&2 VOORWERP']
        assert voorrang.getUitTeSluitenTabellen('Artefact', besluiten) == ['AW1DeterminatiesJohan']

    def test_distinct_per_soort_met_het_filter_van_de_pipeline(self, delftExcel):
        """Eén distinct('table', filter) per pipeline op de collectie, met de $match-fasen van die pipeline."""
        col = MagicMock()
        col.distinct.side_effect = lambda veld, filt: ['AW1DeterminatiesJohan', 'CATALOGUS AW1'] \
            if filt == voorrang.getSelectieFilter(voorrang.getPipeline('Aardewerk')) else \
            (['AW1DeterminatiesJohan', 'Determinaties'] if filt == voorrang.getSelectieFilter(voorrang.getPipeline('Artefact')) else [])
        claims = voorrang.bepaalClaims(col, OUD)
        soorten_oud = [s for s in voorrang.getHarmonizeSoorten() if voorrang.getStagingCollectie(s) == OUD]
        assert col.distinct.call_count == len(soorten_oud) == 22
        assert all(c.args[0] == 'table' for c in col.distinct.call_args_list)
        assert claims['Aardewerk'] == {'AW1DeterminatiesJohan', 'CATALOGUS AW1'}
        assert voorrang.getUitTeSluitenTabellen('Artefact', voorrang.bepaalBesluiten(claims, {}, OUD)) == ['AW1DeterminatiesJohan']
        assert voorrang.getUitTeSluitenTabellen('Aardewerk', voorrang.bepaalBesluiten(claims, {}, OUD)) == []

    def test_onbouwbare_pipeline_wordt_overgeslagen(self, monkeypatch, caplog):
        """Een soort die in de Excel ontbreekt laat zijn eigen taak falen, niet die van de andere soorten."""
        echt = voorrang.getPipeline

        def pipeline(soort, *args):
            if soort == 'Glas':
                raise Exception('Glas does not exist in Excel.')
            return echt(soort, *args)
        monkeypatch.setattr(voorrang, 'getPipeline', pipeline)
        claims = voorrang.bepaalClaims(stagingDelft()[OUD], OUD)
        assert 'Glas' not in claims and 'Aardewerk' in claims
        assert 'Glas does not exist' in caplog.text


# ============================================================
# Klasse 3: besluiten
# ============================================================

CLAIMS = {'Artefact': {'T', 'Determinaties'}, 'Aardewerk': {'T', 'U'}}


@pytest.mark.unit
class TestBesluiten:

    def test_voorrangsregel(self):
        besluiten = voorrang.bepaalBesluiten(CLAIMS, {}, OUD)
        assert list(besluiten) == ['T']
        assert besluiten['T']['kandidaten'] == ['Aardewerk', 'Artefact'] and besluiten['T']['gekozen'] == 'Aardewerk'
        assert voorrang.getUitTeSluitenTabellen('Artefact', besluiten) == ['T']
        assert voorrang.getUitTeSluitenTabellen('Aardewerk', besluiten) == []

    def test_instelling_kiest_een_andere_soort(self):
        besluiten = voorrang.bepaalBesluiten(CLAIMS, {'T': 'Artefact'}, OUD)
        assert besluiten['T']['gekozen'] == 'Artefact' and besluiten['T']['bron'] == voorrang.BRON_INSTELLING
        assert voorrang.getUitTeSluitenTabellen('Aardewerk', besluiten) == ['T']
        assert voorrang.getUitTeSluitenTabellen('Artefact', besluiten) == []

    def test_lege_instelling_door_geen_enkele_soort(self):
        besluiten = voorrang.bepaalBesluiten(CLAIMS, {'T': None, 'U': None}, OUD)
        assert besluiten['T']['gekozen'] is None and besluiten['U']['gekozen'] is None
        assert voorrang.getUitTeSluitenTabellen('Aardewerk', besluiten) == ['T', 'U']
        assert voorrang.getUitTeSluitenTabellen('Artefact', besluiten) == ['T']
        assert voorrang.getMelder(besluiten['T']) == 'Aardewerk'
        assert not voorrang.isWaarschuwing(besluiten['U'])

    @pytest.mark.parametrize('ingesteld', ['Glas', 'Aardewrk'])
    def test_ongeldige_instelling_valt_terug_op_de_regel(self, ingesteld):
        """Een soort die de tabel niet selecteert (of niet bestaat): de regel kiest, met een waarschuwing."""
        besluiten = voorrang.bepaalBesluiten(CLAIMS, {'T': ingesteld, 'U': ingesteld}, OUD)
        for tabel in ('T', 'U'):
            assert besluiten[tabel]['gekozen'] == 'Aardewerk' and besluiten[tabel]['ongeldige_instelling'] == ingesteld
            assert voorrang.isWaarschuwing(besluiten[tabel])
        assert 'genegeerd' in voorrang.maakMeldingTekst(besluiten['T'])

    def test_instelling_voor_onbekende_tabel_doet_niets(self):
        assert voorrang.bepaalBesluiten(CLAIMS, {'X': 'Glas'}, OUD).keys() == {'T'}

    def test_kandidaten_in_volgorde_van_voorrang(self):
        claims = {'Artefact': {'T'}, 'Vlak': {'T'}, 'Metaal': {'T'}}
        assert voorrang.bepaalBesluiten(claims, {}, OUD)['T']['kandidaten'] == ['Vlak', 'Metaal', 'Artefact']


@pytest.mark.unit
class TestUitsluitingInPipeline:

    def test_niets_uit_te_sluiten(self, delftExcel):
        pipeline = voorrang.getPipeline('Artefact')
        assert voorrang.pasUitsluitingToe(pipeline, []) is pipeline

    def test_match_vooraan_zonder_de_bron_te_wijzigen(self, delftExcel):
        pipeline = voorrang.getPipeline('Artefact')
        origineel = copy.deepcopy(pipeline)
        nieuw = voorrang.pasUitsluitingToe(pipeline, ['T', 'AW1DeterminatiesJohan'])
        assert nieuw[0] == {'$match': {'table': {'$nin': ['AW1DeterminatiesJohan', 'T']}}}
        assert nieuw[1:] == origineel and pipeline == origineel

    def test_incrementeel_delta_match_ervoor(self, delftExcel):
        pipeline = voorrang.pasUitsluitingToe(voorrang.getPipeline('Artefact'), ['AW1DeterminatiesJohan'])
        delta = delta_transform.maakDeltaHarmonizePipeline(pipeline, {'mdbfile': {'$in': ['x.mdb']}}, 'run')
        assert delta[0] == {'$match': {'mdbfile': {'$in': ['x.mdb']}}}
        assert delta[1] == {'$match': {'table': {'$nin': ['AW1DeterminatiesJohan']}}}


# ============================================================
# Klasse 4: melden in het run-document
# ============================================================

def leesRun():
    return verwerkingsrun.huidigeRun()


@pytest.mark.unit
class TestMelden:

    def test_waarschuwing_een_keer_door_de_gekozen_soort(self, client):
        startRunMet()
        besluiten = voorrang.bepaalBesluiten(CLAIMS, {}, OUD)
        assert voorrang.meldBesluiten('Artefact', besluiten) == []
        assert voorrang.meldBesluiten('Aardewerk', besluiten) == [besluiten['T']]
        run = leesRun()
        meldingen = [m for m in run.get('meldingen') or [] if m['soort'] == foutbeleid.SOORT_TABEL_DUBBEL_GESELECTEERD]
        assert len(meldingen) == 1 and meldingen[0]['niveau'] == foutbeleid.NIVEAU_WAARSCHUWING
        assert meldingen[0]['details'] == {'tabel': 'T', 'collectie': OUD, 'kandidaten': ['Aardewerk', 'Artefact'],
                                           'gekozen': 'Aardewerk'}
        assert 'harmonisatie_voorrang' in meldingen[0]['melding']
        assert run['tellingen']['transform']['harmonisatie_voorrang'] == {'Aardewerk': [besluiten['T']]}

    def test_instelling_geeft_geen_waarschuwing_wel_een_telling(self, client):
        startRunMet()
        besluiten = voorrang.bepaalBesluiten(CLAIMS, {'T': 'Aardewerk', 'U': None}, OUD)
        voorrang.meldBesluiten('Aardewerk', besluiten)
        voorrang.meldBesluiten('Artefact', besluiten)
        run = leesRun()
        assert not run.get('meldingen')
        assert [b['tabel'] for b in run['tellingen']['transform']['harmonisatie_voorrang']['Aardewerk']] == ['T', 'U']
        assert 'Artefact' not in run['tellingen']['transform']['harmonisatie_voorrang']

    def test_zonder_run_alleen_het_log(self, client, caplog):
        besluiten = voorrang.bepaalBesluiten(CLAIMS, {}, OUD)
        assert voorrang.meldBesluiten('Aardewerk', besluiten) == [besluiten['T']]
        assert 'voorrangsregel' in caplog.text


# ============================================================
# Klasse 5: harmonize_functions.harmonize
# ============================================================

class SimulatieStaging(NepCollectie):
    """Staging-collectie die de harmonisatie nabootst: $match-fasen, de soort uit $addFields en $merge op _id."""

    def __init__(self, naam, single_store, docs):
        super().__init__(naam)
        self.docs = docs
        self.single_store = single_store
        self.pipelines = []

    def aggregate(self, pipeline):
        self.pipelines.append(copy.deepcopy(pipeline))
        docs = list(self.docs)
        for fase in pipeline:
            if '$match' not in fase:
                break
            docs = [d for d in docs if nep_mongo.matcht(d, fase['$match'])]
        velden = {}
        for fase in pipeline:
            for veld in ('soort', 'artefactsoort'):
                if veld in fase.get('$addFields', {}) and isinstance(fase['$addFields'][veld], str):
                    velden[veld] = fase['$addFields'][veld]
        for d in docs:
            # whenMatched: replace
            self.single_store[d['_id']] = dict(velden, table=d['table'])
        return iter([])


class SimulatieClient:
    def __init__(self, staging):
        self.staging = staging

    def __getitem__(self, naam):
        return {coll.name: coll for coll in self.staging.values()}

    def close(self):
        pass


SIMULATIE_TABELLEN = ('AW1DeterminatiesJohan', 'Determinaties', 'CATALOGUS AW1', 'AARDEWERK 1')


def simuleer(monkeypatch, volgorde, incrementeel=False, soort_doorgeven=True, tabellen=SIMULATIE_TABELLEN,
             staging_docs=None):
    """Draai de Harmonize-taken van Staging_Projecten_Oud in een gegeven volgorde; retourneer Single_Store."""
    single_store = {}
    docs = [{'_id': f'{tabel}:{i}', 'table': tabel, 'mdbfile': SY003_MDB} for tabel in tabellen for i in range(2)]
    if staging_docs is not None:
        staging_docs.extend(docs)
    staging = {OUD: SimulatieStaging(OUD, single_store, docs)}
    monkeypatch.setattr(harmonize_functions.pymongo, 'MongoClient', lambda *a, **k: SimulatieClient(staging))
    for soort in volgorde:
        harmonize_functions.harmonize(OUD, meta.getHarmonizePipelines(soort), incrementeel=incrementeel,
                                      **({'soort': soort} if soort_doorgeven else {}))
    return single_store, staging[OUD].pipelines


@pytest.mark.unit
class TestHarmonizeDeterministisch:

    def test_volgorde_van_de_taken_maakt_niet_uit(self, monkeypatch, delftExcel, correcties, client):
        correcties('/tmp/bestaat_niet_correcties.yml')
        eerst_artefact, _ = simuleer(monkeypatch, ['Artefact', 'Aardewerk'])
        eerst_aardewerk, _ = simuleer(monkeypatch, ['Aardewerk', 'Artefact'])
        assert eerst_artefact == eerst_aardewerk
        soorten = {d['table']: (d['soort'], d.get('artefactsoort')) for d in eerst_artefact.values()}
        assert soorten == {'AW1DeterminatiesJohan': ('Artefact', 'Aardewerk'), 'Determinaties': ('Artefact', None),
                           'CATALOGUS AW1': ('Artefact', 'Aardewerk'), 'AARDEWERK 1': ('Artefact', 'Aardewerk')}

    def test_instelling_artefact_wint(self, monkeypatch, delftExcel, correcties, client, tmp_path):
        bestand = tmp_path / 'correcties.yml'
        bestand.write_text('harmonisatie_voorrang:\n  AW1DeterminatiesJohan: Artefact\n', encoding='utf-8')
        correcties(str(bestand))
        for volgorde in (['Artefact', 'Aardewerk'], ['Aardewerk', 'Artefact']):
            single_store, pipelines = simuleer(monkeypatch, volgorde)
            assert {d['table']: d.get('artefactsoort') for d in single_store.values()}['AW1DeterminatiesJohan'] is None
            aardewerk = pipelines[volgorde.index('Aardewerk')]
            assert aardewerk[0] == {'$match': {'table': {'$nin': ['AW1DeterminatiesJohan']}}}

    def test_soort_afgeleid_zonder_argument(self, monkeypatch, delftExcel, correcties, client):
        """Ook zonder het argument soort (oude aanroep) weet de taak welke soort hij is."""
        correcties('/tmp/bestaat_niet_correcties.yml')
        single_store, pipelines = simuleer(monkeypatch, ['Aardewerk', 'Artefact'], soort_doorgeven=False)
        assert pipelines[1][0] == {'$match': {'table': {'$nin': ['AW1DeterminatiesJohan']}}}
        assert {d['table']: d.get('artefactsoort') for d in single_store.values()}['AW1DeterminatiesJohan'] == 'Aardewerk'

    def test_incrementeel_uitsluiting_na_de_delta_match(self, monkeypatch, delftExcel, correcties, client):
        correcties('/tmp/bestaat_niet_correcties.yml')
        startRunMet(nieuw={'projecten': [SY003_MDB]})
        single_store, pipelines = simuleer(monkeypatch, ['Aardewerk', 'Artefact'], incrementeel=True)
        artefact = pipelines[1]
        assert artefact[0] == {'$match': {'mdbfile': {'$in': [SY003_MDB]}}}
        assert artefact[1] == {'$match': {'table': {'$nin': ['AW1DeterminatiesJohan']}}}
        assert artefact[-2] == {'$addFields': {'delta_run': verwerkingsrun.huidigeRun()['run_id']}}
        assert {d['table']: d.get('artefactsoort') for d in single_store.values()}['AW1DeterminatiesJohan'] == 'Aardewerk'
        # De waarschuwing komt één keer, van de taak van Aardewerk
        meldingen = [m for m in verwerkingsrun.huidigeRun().get('meldingen') or []
                     if m['soort'] == foutbeleid.SOORT_TABEL_DUBBEL_GESELECTEERD]
        assert len(meldingen) == 1 and meldingen[0]['details']['gekozen'] == 'Aardewerk'


@pytest.mark.unit
class TestCodetabelZonderSoort:
    """Issue 75: een tabel met een lege waarde in harmonisatie_voorrang komt niet in Single_Store(_Clean).

    In Delft de codetabellen AARDEWERK 1&2 VOORWERP en AARDEWERK 1 BAKSEL uit
    opgravingDB34.mdb: alleen Aardewerk selecteert ze (via ".*AARDEWERK.*"),
    zodat er geen dubbele selectie is; de lege waarde sluit ze uit. De
    staging-documenten blijven staan als referentiedata.
    """

    TABELLEN = ('AARDEWERK 1', 'AARDEWERK 1&2 VOORWERP', 'AARDEWERK 1 BAKSEL')

    @pytest.fixture
    def instelling(self, correcties, tmp_path):
        bestand = tmp_path / 'correcties.yml'
        bestand.write_text('harmonisatie_voorrang:\n  "AARDEWERK 1&2 VOORWERP":\n  "AARDEWERK 1 BAKSEL":\n',
                           encoding='utf-8')
        return correcties(str(bestand))

    def test_niet_in_single_store_wel_in_de_staging(self, monkeypatch, delftExcel, instelling, client):
        startRunMet()
        staging = []
        single_store, pipelines = simuleer(monkeypatch, ['Artefact', 'Aardewerk'], tabellen=self.TABELLEN,
                                           staging_docs=staging)
        assert sorted({d['table'] for d in single_store.values()}) == ['AARDEWERK 1']
        assert pipelines[1][0] == {'$match': {'table': {'$nin': ['AARDEWERK 1 BAKSEL', 'AARDEWERK 1&2 VOORWERP']}}}
        # De taak van Artefact selecteert de tabellen niet en sluit dus niets uit
        assert pipelines[0][0] != pipelines[1][0]
        # Referentiedata: de staging-documenten blijven ongewijzigd staan
        assert sorted({d['table'] for d in staging}) == sorted(self.TABELLEN) and len(staging) == 6
        # Geen waarschuwing, wel de besluiten in het run-document (gemeld door de taak van Aardewerk)
        run = verwerkingsrun.huidigeRun()
        assert not [m for m in run.get('meldingen') or [] if m['soort'] == foutbeleid.SOORT_TABEL_DUBBEL_GESELECTEERD]
        besluiten = run['tellingen']['transform']['harmonisatie_voorrang']['Aardewerk']
        assert [(b['tabel'], b['gekozen'], b['bron']) for b in besluiten] == [
            ('AARDEWERK 1 BAKSEL', None, voorrang.BRON_INSTELLING), ('AARDEWERK 1&2 VOORWERP', None, voorrang.BRON_INSTELLING)]

    def test_niet_in_single_store_clean(self, monkeypatch, delftExcel, instelling, client):
        """Wat niet in Single_Store staat, kan Transform 5 niet verplaatsen of samenvoegen."""
        from tests.unit.test_merge_artefacten import artefact, simuleerTransform5
        single_store, _ = simuleer(monkeypatch, ['Aardewerk', 'Artefact'], tabellen=self.TABELLEN)
        docs = [artefact(d['table'], bron_id=i) for i, d in enumerate(single_store.values())]
        clean = simuleerTransform5(docs)
        assert len(clean) == 2 and {b['table'] for d in clean for b in d['brondata']} == {'AARDEWERK 1'}

    def test_incrementeel(self, monkeypatch, delftExcel, instelling, client):
        startRunMet(nieuw={'projecten': [SY003_MDB]})
        single_store, pipelines = simuleer(monkeypatch, ['Aardewerk'], incrementeel=True, tabellen=self.TABELLEN)
        assert pipelines[0][0] == {'$match': {'mdbfile': {'$in': [SY003_MDB]}}}
        assert pipelines[0][1] == {'$match': {'table': {'$nin': ['AARDEWERK 1 BAKSEL', 'AARDEWERK 1&2 VOORWERP']}}}
        assert sorted({d['table'] for d in single_store.values()}) == ['AARDEWERK 1']
