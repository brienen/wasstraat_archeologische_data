"""
Unit tests voor de delta-varianten van de transformaties (incrementeel laden, fase 2, issue 61).

Test wasstraat/delta_transform.py en de optionele parameters van de bestaande
transformatiefuncties:

- opbouw van de delta-pipelines (positie van de extra $match en van
  $addFields delta_run, geen mutatie van de pipelines uit meta.py en de harmonizer)
- het filter op de staging-collecties per categorie
- de bepaling van de geraakte sleutels (inclusief verwijderde_keys en het
  Artefact-geval met key_subnr) en de geraakte projecten
- het verwijderen van verdwenen sleutels en gegenereerde documenten in
  Single_Store_Clean
- de stabiele toewijzing van ID's met een nagebootste PostgreSQL-mapping,
  voor artefacten op de samengestelde sleutel key_subnr|artefactsoort (fase 3)

Gebruikt de nagebootste MongoDB uit tests/unit/nep_mongo.py, met een kleine
uitbreiding in dit bestand ($regex, replace_one, update_many en bulk_write met
UpdateOne/ReplaceOne).

De klasse TestVondstkeyVlag test dat de projectbrede vlag vondstkey_met_putnr
bij een incrementele run voor de geraakte projecten opnieuw wordt bepaald en
dat Transform 3 en 5 de soorten waarvan de sleutels van die vlag afhangen voor
de hele geraakte projecten opnieuw verwerken.
"""
import copy
import re
import sys
import types

import pytest
from bson import ObjectId
from pymongo import UpdateOne, ReplaceOne, InsertOne

# Mock shared.image_util (wordt via bronbestanden/opruimen geïmporteerd door image_import.py)
if "shared.image_util" not in sys.modules:
    sys.modules["shared.image_util"] = types.ModuleType("shared.image_util")

import shared.config as config
import wasstraat.verwerkingsrun as verwerkingsrun
import wasstraat.delta_transform as delta_transform
import wasstraat.harmonize_functions as harmonize_functions
import wasstraat.references_functions as references_functions
import wasstraat.merge_functions as merge_functions
import wasstraat.meta as meta
from tests.unit import nep_mongo
from tests.unit.nep_mongo import NepClient, NepCollectie, NepDatabase, NepResultaat


RUN_ID = '20261021T120000'
SY003_MDB = '/input/projecten/SY003/C Database/opgravingSY003.mdb'
SY001_MDB = '/input/projecten/SY001/C Database/opgravingSY001.mdb'
FOTO_SY003 = '/input/projecten/SY003/L Fotos/SY003_F001.jpg'
FOTO_SY001 = '/input/projecten/SY001/L Fotos/SY001_F001.jpg'


# ============================================================
# Uitbreiding van de nagebootste MongoDB
# ============================================================

_origineleMatcht = nep_mongo.matcht


def matchtMetRegex(doc, filt):
    """matcht uit nep_mongo, aangevuld met $regex op tekstvelden."""
    rest = {}
    for veld, voorwaarde in (filt or {}).items():
        if isinstance(voorwaarde, dict) and '$regex' in voorwaarde:
            waarde = nep_mongo.haalOp(doc, veld)
            if not isinstance(waarde, str) or not re.search(voorwaarde['$regex'], waarde):
                return False
        else:
            rest[veld] = voorwaarde
    return _origineleMatcht(doc, rest)


class UitgebreideCollectie(NepCollectie):
    """NepCollectie met replace_one, update_many ($set en $unset) en bulk_write voor updates."""

    def replace_one(self, filt, doc, upsert=False):
        for i, d in enumerate(self.docs):
            if nep_mongo.matcht(d, filt):
                nieuw = copy.deepcopy(doc)
                nieuw['_id'] = d['_id']
                self.docs[i] = nieuw
                return NepResultaat(matched_count=1)
        if upsert:
            nieuw = copy.deepcopy(doc)
            nieuw.setdefault('_id', filt.get('_id'))
            self.docs.append(nieuw)
        return NepResultaat(matched_count=0)

    def update_many(self, filt, update):
        aantal = 0
        for d in self.docs:
            if nep_mongo.matcht(d, filt):
                for pad, waarde in update.get('$set', {}).items():
                    nep_mongo._zetWaarde(d, pad, copy.deepcopy(waarde))
                for pad in update.get('$unset', {}):
                    d.pop(pad, None)
                aantal += 1
        return NepResultaat(matched_count=aantal, modified_count=aantal)

    def bulk_write(self, operaties):
        for op in operaties:
            if isinstance(op, UpdateOne):
                self.update_one(op._filter, op._doc)
            elif isinstance(op, ReplaceOne):
                self.replace_one(op._filter, op._doc, upsert=op._upsert)
            elif isinstance(op, InsertOne):
                self.insert_one(op._doc)
        return NepResultaat()


class UitgebreideDatabase(NepDatabase):
    def __getitem__(self, naam):
        return self.collecties.setdefault(naam, UitgebreideCollectie(naam))


class UitgebreideClient(NepClient):
    def __getitem__(self, naam):
        return self.databases.setdefault(naam, UitgebreideDatabase(naam))


class OpnameCollectie:
    """Collectie die alleen vastlegt welke pipelines en filters worden gebruikt."""

    def __init__(self, resultaat=None):
        self.pipelines = []
        self.filters = []
        self.resultaat = resultaat or []
        self.database = types.SimpleNamespace(client=types.SimpleNamespace(close=lambda: None))

    def aggregate(self, pipeline, **kwargs):
        self.pipelines.append(copy.deepcopy(pipeline))
        return iter(self.resultaat)

    def find(self, filt=None, *args, **kwargs):
        self.filters.append(copy.deepcopy(filt))
        return iter([])

    def distinct(self, veld, filt=None):
        """Voorrang bij de harmonisatie (issue 89): zonder documenten selecteert geen pipeline een tabel."""
        return []


@pytest.fixture
def client(monkeypatch):
    """Vervang de MongoClients door een (uitgebreide) in-memory nabootsing."""
    nep = UitgebreideClient()
    monkeypatch.setattr(nep_mongo, 'matcht', matchtMetRegex)
    monkeypatch.setattr(verwerkingsrun, '_getClient', lambda: nep)
    monkeypatch.setattr(delta_transform, '_getClient', lambda: nep)
    return nep


def startRunMet(**velden):
    """Start een incrementele run en zet velden in het run-document."""
    verwerkingsrun.startRun('incrementeel')
    if velden:
        verwerkingsrun.werkRunBij(velden)
    return verwerkingsrun.huidigeRun()


def analyse(client):
    return client[config.DB_ANALYSE][config.COLL_ANALYSE]


def clean(client):
    return client[config.DB_ANALYSE][config.COLL_ANALYSE_CLEAN]


# ============================================================
# Klasse 1: opbouw van de delta-pipelines
# ============================================================

HARMONIZE_PIPELINE = [
    {'$match': {'table': 'VONDST'}},
    {'$replaceRoot': {'newRoot': {'_id': '$_id', 'brondata': '$$ROOT'}}},
    {'$addFields': {'projectcd': '$brondata.projectcd', 'soort': 'Vondst'}},
    {'$merge': {'into': {'db': 'x', 'coll': 'y'}, 'on': '_id', 'whenMatched': 'replace', 'whenNotMatched': 'insert'}},
]


@pytest.mark.unit
class TestDeltaPipelines:
    """Test de positie van de extra fasen en dat de bronpipelines niet veranderen."""

    def test_harmonize_match_vooraan_en_delta_run_voor_merge(self):
        origineel = copy.deepcopy(HARMONIZE_PIPELINE)
        pipeline = delta_transform.maakDeltaHarmonizePipeline(HARMONIZE_PIPELINE, {'mdbfile': {'$in': [SY003_MDB]}}, RUN_ID)
        assert pipeline[0] == {'$match': {'mdbfile': {'$in': [SY003_MDB]}}}
        assert pipeline[1:4] == origineel[:3]
        assert pipeline[-2] == {'$addFields': {'delta_run': RUN_ID}}
        assert '$merge' in pipeline[-1]
        assert len(pipeline) == len(origineel) + 2
        assert HARMONIZE_PIPELINE == origineel

    def test_harmonize_zonder_padfilter_voor_abr(self):
        pipeline = delta_transform.maakDeltaHarmonizePipeline(HARMONIZE_PIPELINE, {}, RUN_ID)
        assert pipeline[0] == HARMONIZE_PIPELINE[0]
        assert pipeline[-2] == {'$addFields': {'delta_run': RUN_ID}}

    def test_harmonize_artefactsoort_fase_blijft_voor_delta_run(self):
        """getHarmonizeAggr voegt bij artefactsoorten een $addFields vlak voor de $merge toe."""
        bron = HARMONIZE_PIPELINE[:-1] + [{'$addFields': {'artefactsoort': 'Glas', 'soort': 'Artefact'}}, HARMONIZE_PIPELINE[-1]]
        pipeline = delta_transform.maakDeltaHarmonizePipeline(bron, {'mdbfile': {'$in': [SY003_MDB]}}, RUN_ID)
        assert pipeline[-3] == {'$addFields': {'artefactsoort': 'Glas', 'soort': 'Artefact'}}
        assert pipeline[-2] == {'$addFields': {'delta_run': RUN_ID}}

    def test_harmonize_pipeline_zonder_merge(self):
        assert delta_transform.maakDeltaHarmonizePipeline([], {'mdbfile': {'$in': [SY003_MDB]}}, RUN_ID) is None

    def test_eerste_match_aanvullen(self):
        pipeline = [{'$match': {'soort': 'Vondst'}}, {'$addFields': {'key': 'x'}}]
        nieuw = delta_transform.voegToeAanEersteMatch(pipeline, {'delta_run': RUN_ID})
        assert nieuw[0] == {'$match': {'soort': 'Vondst', 'delta_run': RUN_ID}}
        assert pipeline[0] == {'$match': {'soort': 'Vondst'}}

    def test_eerste_match_botsing_wordt_and(self):
        nieuw = delta_transform.voegToeAanEersteMatch([{'$match': {'key': 'a'}}], {'key': {'$in': ['b']}})
        assert nieuw[0] == {'$match': {'$and': [{'key': 'a'}, {'key': {'$in': ['b']}}]}}

    def test_lege_pipeline_krijgt_match(self):
        """Fotokoppel heeft een lege sleutelpipeline; de delta beperkt die tot de delta-documenten."""
        assert delta_transform.voegToeAanEersteMatch([], {'delta_run': RUN_ID}) == [{'$match': {'delta_run': RUN_ID}}]

    def test_merge_pipeline_artefact(self):
        bron = merge_functions.getMergeAggregate('Artefact', key='key_subnr')
        origineel = copy.deepcopy(bron)
        pipeline = delta_transform.maakDeltaMergePipeline(bron, 'key_subnr', ['PSY003P1V1A1'], RUN_ID)
        assert pipeline[0] == {'$match': {'soort': 'Artefact', 'key_subnr': {'$in': ['PSY003P1V1A1']}}}
        assert pipeline[-2] == {'$addFields': {'delta_run': RUN_ID}}
        assert '$merge' in pipeline[-1]
        assert pipeline[1:-2] == origineel[1:-1]
        assert bron == origineel

    def test_generate_missing_pipeline_match_vooraan(self):
        bron = meta.getGenerateMissingPipelines('Put')[0]
        pipeline = delta_transform.maakProjectMatchPipeline(bron, ['SY003'])
        assert pipeline[0] == {'$match': {'projectcd': {'$in': ['SY003']}}}
        assert pipeline[1:] == bron
        assert meta.getGenerateMissingPipelines('Put')[0] == bron


@pytest.mark.unit
class TestDeltaAanroepen:
    """Test dat de bestaande functies met incrementeel=True de juiste pipeline gebruiken."""

    def test_harmonize_incrementeel(self, client, monkeypatch):
        projectenlijst = '/input/projectenlijst/projectenlijst.mdb'
        startRunMet(gewijzigd={'projectenlijst': [projectenlijst]}, ongewijzigd={'projecten': [SY001_MDB]})
        opname = OpnameCollectie()
        monkeypatch.setattr(harmonize_functions.pymongo, 'MongoClient', lambda *a, **k: _OpnameClient(opname))
        bron = meta.getHarmonizePipelines('Project')
        origineel = copy.deepcopy(bron)

        harmonize_functions.harmonize(config.COLL_STAGING_PROJECTENLIJST, bron, incrementeel=True)

        pipeline = opname.pipelines[0]
        assert pipeline[0] == {'$match': {'mdbfile': {'$in': [projectenlijst]}}}
        assert pipeline[1:-2] == origineel[0][:-1]
        assert pipeline[-2] == {'$addFields': {'delta_run': verwerkingsrun.huidigeRun()['run_id']}}
        assert pipeline[-1] == origineel[0][-1]
        assert meta.getHarmonizePipelines('Project') == origineel

    def test_harmonize_incrementeel_artefactsoort_uit_excel(self, client, monkeypatch):
        """De pipeline van de harmonizer (met de artefactsoort-fase) krijgt delta_run vlak voor de $merge."""
        startRunMet(nieuw={'projecten': [SY003_MDB]})
        opname = OpnameCollectie()
        monkeypatch.setattr(harmonize_functions.pymongo, 'MongoClient', lambda *a, **k: _OpnameClient(opname))

        harmonize_functions.harmonize(config.COLL_STAGING_OUD, 'Glas', incrementeel=True)
        harmonize_functions.harmonize(config.COLL_STAGING_OUD, 'Glas', incrementeel=True)

        for pipeline in opname.pipelines:
            assert pipeline[0] == {'$match': {'mdbfile': {'$in': [SY003_MDB]}}}
            assert pipeline[-3] == {'$addFields': {'artefactsoort': 'Glas', 'soort': 'Artefact'}}
            assert pipeline[-2] == {'$addFields': {'delta_run': verwerkingsrun.huidigeRun()['run_id']}}
            assert '$merge' in pipeline[-1]
            assert sum(1 for fase in pipeline if 'delta_run' in fase.get('$addFields', {})) == 1

    def test_harmonize_incrementeel_zonder_delta_doet_niets(self, client, monkeypatch):
        startRunMet(ongewijzigd={'projecten': [SY001_MDB]})
        opname = OpnameCollectie()
        monkeypatch.setattr(harmonize_functions.pymongo, 'MongoClient', lambda *a, **k: _OpnameClient(opname))
        harmonize_functions.harmonize(config.COLL_STAGING_OUD, meta.getHarmonizePipelines('Project'), incrementeel=True)
        assert opname.pipelines == []

    def test_harmonize_volledig_ongewijzigd(self, client, monkeypatch):
        opname = OpnameCollectie()
        monkeypatch.setattr(harmonize_functions.pymongo, 'MongoClient', lambda *a, **k: _OpnameClient(opname))
        bron = meta.getHarmonizePipelines('Project')
        harmonize_functions.harmonize(config.COLL_STAGING_PROJECTENLIJST, bron)
        assert opname.pipelines == [bron[0]]

    def test_set_reference_keys_incrementeel(self, client, monkeypatch):
        startRunMet()
        opname = OpnameCollectie()
        monkeypatch.setattr(references_functions, 'getAnalyseCollection', lambda: opname)
        bron = meta.getReferenceKeysPipeline('Vondst')
        origineel = copy.deepcopy(bron)
        references_functions.setReferenceKeys(bron, 'Vondst', incrementeel=True)
        assert opname.pipelines[0][0] == {'$match': {'soort': 'Vondst', 'delta_run': verwerkingsrun.huidigeRun()['run_id']}}
        assert opname.pipelines[0][1:] == origineel[1:]
        assert meta.getReferenceKeysPipeline('Vondst') == origineel

    def test_move_incrementeel(self, client, monkeypatch):
        startRunMet()
        opname = OpnameCollectie()
        monkeypatch.setattr(merge_functions, 'getAnalyseCollection', lambda: opname)
        merge_functions.moveSoort('Spoor', incrementeel=True)
        assert opname.pipelines[0][0] == {'$match': {'soort': 'Spoor', 'delta_run': verwerkingsrun.huidigeRun()['run_id']}}
        merge_functions.moveSoort('Spoor')
        assert opname.pipelines[1][0] == {'$match': {'soort': 'Spoor'}}


class _OpnameClient:
    """MongoClient-nabootsing die elke collectie door dezelfde OpnameCollectie vervangt."""

    def __init__(self, opname):
        self.opname = opname

    def __getitem__(self, naam):
        return _OpnameDatabase(self.opname)

    def close(self):
        pass


class _OpnameDatabase:
    def __init__(self, opname):
        self.opname = opname

    def __getitem__(self, naam):
        return self.opname


# ============================================================
# Klasse 2: filter op de staging-collecties
# ============================================================

@pytest.mark.unit
class TestStagingDeltaFilter:
    """Test welke staging-documenten Transform 1 bij een incrementele run harmoniseert."""

    def test_projecten(self):
        run = {'nieuw': {'projecten': [SY003_MDB]}, 'gewijzigd': {'projecten': [SY001_MDB]}, 'verwijderd': {'projecten': ['/x.mdb']}}
        assert delta_transform.getStagingDeltaFilter(config.COLL_STAGING_OUD, run) == {'mdbfile': {'$in': sorted([SY003_MDB, SY001_MDB])}}

    def test_projectenlijst_met_extra_projecten(self):
        run = {'gewijzigd': {'projectenlijst': ['/input/projectenlijst/p.mdb'], 'extra_projecten': [config.FILE_EXTRA_PROJECTS]}}
        assert delta_transform.getStagingDeltaFilter(config.COLL_STAGING_PROJECTENLIJST, run) == {
            'mdbfile': {'$in': sorted(['/input/projectenlijst/p.mdb', config.FILE_EXTRA_PROJECTS])}}

    def test_abr_hele_collectie_of_niets(self):
        assert delta_transform.getStagingDeltaFilter(
            config.COLL_STAGING_REFERENTIETABELLEN, {'gewijzigd': {'referentietabellen': [config.FILE_ABREXCEL]}}) == {}
        assert delta_transform.getStagingDeltaFilter(
            config.COLL_STAGING_REFERENTIETABELLEN, {'ongewijzigd': {'referentietabellen': [config.FILE_ABREXCEL]}}) is None

    def test_geen_delta_of_alleen_verwijderd(self):
        assert delta_transform.getStagingDeltaFilter(config.COLL_STAGING_OUD, {'ongewijzigd': {'projecten': [SY001_MDB]}}) is None
        assert delta_transform.getStagingDeltaFilter(config.COLL_STAGING_OUD, {'verwijderd': {'projecten': [SY003_MDB]}}) is None
        assert delta_transform.getStagingDeltaFilter(config.COLL_STAGING_MONSTER, {'nieuw': {'projecten': [SY003_MDB]}}) is None


# ============================================================
# Klasse 3: geraakte sleutels en projecten
# ============================================================

@pytest.mark.unit
class TestGeraakteSleutels:
    """Test de bepaling van de sleutels en projecten die opnieuw verwerkt worden."""

    def test_sleutels_van_delta_documenten_en_verwijderde_keys(self, client):
        analyse(client).insert_many([
            {'_id': 1, 'soort': 'Vondst', 'key': 'PSY003P1V1', 'projectcd': 'SY003', 'delta_run': RUN_ID},
            {'_id': 2, 'soort': 'Vondst', 'key': 'PSY003P1V2', 'projectcd': 'SY003', 'delta_run': RUN_ID},
            {'_id': 3, 'soort': 'Vondst', 'key': 'PSY001P1V1', 'projectcd': 'SY001'},  # geen delta
            {'_id': 4, 'soort': 'Vondst', 'key': 'PSY002P1V1', 'projectcd': 'SY002', 'delta_run': 'eerdere_run'},
            {'_id': 5, 'soort': 'Spoor', 'key': 'PSY003P1S1', 'projectcd': 'SY003', 'delta_run': RUN_ID},
            {'_id': 6, 'soort': 'Vondst', 'key': None, 'projectcd': 'SY003', 'delta_run': RUN_ID},  # zonder sleutel
        ])
        run = {'run_id': RUN_ID, 'verwijderde_keys': {
            'Vondst': [{'key': 'PSY003P1V2', 'projectcd': 'SY003'}, {'key': 'PSY003P4V12', 'projectcd': 'SY003'}],
            'Spoor': [{'key': 'PSY003P9S9', 'projectcd': 'SY003'}]}}
        assert delta_transform.bepaalGeraakteSleutels('Vondst', analyse(client), run) == ['PSY003P1V1', 'PSY003P1V2', 'PSY003P4V12']

    def test_artefact_op_key_subnr(self, client):
        """Artefacten hebben in Single_Store vaak key: null en worden samengevoegd op key_subnr."""
        analyse(client).insert_many([
            {'_id': 1, 'soort': 'Artefact', 'key': None, 'key_subnr': 'PSY003P1V1A1', 'artefactsoort': 'Glas', 'delta_run': RUN_ID},
            {'_id': 2, 'soort': 'Artefact', 'key': 'PSY003P1V1A7', 'key_subnr': None, 'delta_run': RUN_ID},
        ])
        run = {'run_id': RUN_ID, 'verwijderde_keys': {'Artefact': [
            {'key': None, 'projectcd': 'SY003', 'key_subnr': 'PSY003P2V4A1', 'artefactsoort': 'Aardewerk'}]}}
        assert delta_transform.bepaalGeraakteSleutels('Artefact', analyse(client), run) == ['PSY003P1V1A1', 'PSY003P2V4A1']

    def test_geraakte_projecten_uit_run_en_delta(self, client):
        analyse(client).insert_many([
            {'_id': 1, 'soort': 'Foto', 'projectcd': 'SY002', 'delta_run': RUN_ID},
            {'_id': 2, 'soort': 'Vondst', 'projectcd': 'SY003', 'delta_run': RUN_ID},
            {'_id': 3, 'soort': 'Vondst', 'projectcd': 'SY001'},
            {'_id': 4, 'soort': 'Monster', 'delta_run': RUN_ID},  # zonder projectcode
        ])
        run = {'run_id': RUN_ID, 'geraakte_projecten': ['SY004']}
        assert delta_transform.getGeraakteProjecten(run) == ['SY002', 'SY003', 'SY004']

    def test_werk_geraakte_projecten_bij_in_run_document(self, client):
        run = startRunMet(geraakte_projecten=['SY004'])
        analyse(client).insert_many([
            {'_id': 1, 'soort': 'Vondst', 'projectcd': 'SY003', 'delta_run': run['run_id']},
            {'_id': 2, 'soort': 'Vondst', 'projectcd': 'SY001', 'delta_run': 'eerdere_run'},
        ])
        assert delta_transform.werkGeraakteProjectenBij() == ['SY003', 'SY004']
        run = verwerkingsrun.huidigeRun()
        assert run['geraakte_projecten'] == ['SY003', 'SY004']
        assert run['tellingen']['transform']['delta_documenten'] == 1

    def test_foto_filter(self, client):
        analyse(client).insert_many([
            {'_id': 1, 'soort': 'Foto', 'projectcd': 'SY003', 'delta_run': RUN_ID},
            {'_id': 2, 'soort': 'Fotokoppel', 'bestandsnaam': 'SY001_F001.jpg', 'delta_run': RUN_ID},
        ])
        filt = delta_transform.getFotoDeltaFilter(analyse(client), {'run_id': RUN_ID, 'geraakte_projecten': ['SY002']})
        assert filt == {'soort': 'Foto', '$or': [
            {'delta_run': RUN_ID}, {'projectcd': {'$in': ['SY002', 'SY003']}}, {'fileName': {'$in': ['SY001_F001.jpg']}}]}

    def test_foto_filter_zonder_geraakte_fotos(self, client):
        assert delta_transform.getFotoDeltaFilter(analyse(client), {'run_id': RUN_ID, 'geraakte_projecten': []}) is None


# ============================================================
# Klasse 4: opruimen in Single_Store_Clean
# ============================================================

@pytest.mark.unit
class TestVerwijderenInClean:
    """Test het verwijderen van verdwenen sleutels en gegenereerde documenten."""

    def test_verdwenen_sleutels_vondst(self, client):
        clean(client).insert_many([
            {'_id': 'a', 'soort': 'Vondst', 'key': 'PSY003P1V1', 'brondata_count': 1, 'delta_run': RUN_ID},   # opnieuw samengevoegd
            {'_id': 'b', 'soort': 'Vondst', 'key': 'PSY003P1V1', 'brondata_count': 2, 'delta_run': 'oud'},   # oud _id van dezelfde key
            {'_id': 'c', 'soort': 'Vondst', 'key': 'PSY003P4V12', 'brondata_count': 1},                     # sleutel verdwenen
            {'_id': 'd', 'soort': 'Vondst', 'key': 'PSY001P1V1', 'brondata_count': 1},                      # niet geraakt
            {'_id': 'e', 'soort': 'Vondst', 'key': 'PSY003P4V12', 'brondata': {'table': 'generated_vondst'}},  # gegenereerd
        ])
        aantal = delta_transform.verwijderVerdwenenSleutels('Vondst', clean(client), ['PSY003P1V1', 'PSY003P4V12'], RUN_ID)
        assert aantal == 2
        assert sorted(d['_id'] for d in clean(client).find({})) == ['a', 'd', 'e']

    def test_verdwenen_sleutels_artefact_en_move_documenten(self, client):
        clean(client).insert_many([
            {'_id': 'm1', 'soort': 'Artefact', 'key_subnr': 'PSY003P1V1A1', 'artefactsoort': 'Glas', 'brondata_count': 1, 'delta_run': RUN_ID},
            {'_id': 'm2', 'soort': 'Artefact', 'key_subnr': 'PSY003P1V1A1', 'artefactsoort': 'Aardewerk', 'brondata_count': 1},  # artefactsoort verdwenen
            {'_id': 'mv', 'soort': 'Artefact', 'key_subnr': 'PSY003P1V1A1', 'artefactsoort': 'Munt'},  # verplaatst, blijft
        ])
        assert delta_transform.verwijderVerdwenenSleutels('Artefact', clean(client), ['PSY003P1V1A1'], RUN_ID) == 1
        assert sorted(d['_id'] for d in clean(client).find({})) == ['m1', 'mv']

    def test_verdwenen_sleutels_tekening_als_bestand(self, client):
        clean(client).insert_many([
            {'_id': 't1', 'soort': 'Bestand', 'bestandsoort_XX': 'Tekening', 'key': 'PSY003T001', 'brondata_count': 1},
            {'_id': 'f1', 'soort': 'Bestand', 'bestandsoort_XX': 'Foto', 'key': 'PSY003T001'},
        ])
        assert delta_transform.verwijderVerdwenenSleutels('Tekening', clean(client), ['PSY003T001'], RUN_ID) == 1
        assert [d['_id'] for d in clean(client).find({})] == ['f1']

    def test_gegenereerde_documenten_van_geraakte_projecten(self, client):
        clean(client).insert_many([
            {'_id': 1, 'soort': 'Put', 'projectcd': 'SY003', 'key': 'PSY003P1', 'brondata': {'table': 'generated_put', 'projectcd': 'SY003'}},
            {'_id': 2, 'soort': 'Put', 'projectcd': 'SY001', 'key': 'PSY001P1', 'brondata': {'table': 'generated_put', 'projectcd': 'SY001'}},
            {'_id': 3, 'soort': 'Put', 'projectcd': 'SY003', 'key': 'PSY003P2', 'brondata': [{'table': 'PUT'}]},
            {'_id': 4, 'soort': 'Vlak', 'projectcd': 'SY003', 'key': 'PSY003P1V1', 'brondata': {'table': 'generated_vlak'}},
        ])
        assert delta_transform.verwijderGegenereerdeDocumenten('Put', clean(client), ['SY003']) == 1
        assert sorted(d['_id'] for d in clean(client).find({})) == [2, 3, 4]


# ============================================================
# Klasse 5: stabiele sleutels
# ============================================================

OID_A, OID_B, OID_C, OID_D = ObjectId(), ObjectId(), ObjectId(), ObjectId()


@pytest.mark.unit
class TestStabieleSleutels:
    """Test de toewijzing van ID's met een nagebootste PostgreSQL-mapping."""

    def test_id_behouden_op_id_op_key_en_nieuw(self):
        docs = [
            {'_id': OID_A, 'key': 'PSY001P1V1', 'ID': 0},       # (a) heeft al een ID
            {'_id': OID_B, 'key': 'PSY002P1V1'},                # (b) op _id
            {'_id': OID_C, 'key': 'PSY003P1V1'},                # (b) op unieke key
            {'_id': OID_D, 'key': 'PSY003P1V9'},                # (c) nieuw
        ]
        pg = [
            {'primary_key': 0, '_id': str(OID_A), 'key': 'PSY001P1V1'},
            {'primary_key': 4, '_id': str(OID_B), 'key': 'PSY002P1V1'},
            {'primary_key': 7, '_id': 'oud_id', 'key': 'PSY003P1V1'},
            {'primary_key': 9, '_id': 'weg', 'key': 'PSY003P4V12'},
        ]
        toewijzing, tellingen = delta_transform.bepaalStabieleIds(docs, pg)
        assert dict(toewijzing) == {OID_B: 4, OID_C: 7, OID_D: 10}
        assert tellingen == {'behouden': 1, 'uit_bron': 0, 'op_id': 1, 'op_bestand': 0, 'op_vervangende_key': 0, 'op_key': 1, 'op_bronsleutel': 0, 'op_bronsleutel_andere_key': 0, 'op_bronsleutel_overgang': 0, 'nieuw': 1, 'nieuw_bronrij_bekend': 0}

    def test_dubbele_key_in_tabel_wordt_niet_gebruikt(self):
        """Move-soorten zoals Standplaats hebben dubbele keys; die zijn geen betrouwbare sleutel."""
        docs = [{'_id': OID_A, 'key': 'S1V2'}]
        pg = [{'primary_key': 3, '_id': 'x', 'key': 'S1V2'}, {'primary_key': 5, '_id': 'y', 'key': 'S1V2'}]
        toewijzing, tellingen = delta_transform.bepaalStabieleIds(docs, pg)
        assert toewijzing == [(OID_A, 6)]
        assert tellingen['op_key'] == 0 and tellingen['nieuw'] == 1

    def test_nieuw_nummer_boven_maximum_van_clean_en_postgres(self):
        docs = [{'_id': OID_A, 'key': 'a', 'ID': 20}, {'_id': OID_B, 'key': 'b'}]
        toewijzing, _ = delta_transform.bepaalStabieleIds(docs, [{'primary_key': 12, '_id': 'z', 'key': 'z'}])
        assert toewijzing == [(OID_B, 21)]
        toewijzing, _ = delta_transform.bepaalStabieleIds([{'_id': OID_B, 'key': 'b'}], [{'primary_key': 12, '_id': 'z', 'key': 'z'}])
        assert toewijzing == [(OID_B, 13)]

    def test_primary_key_in_gebruik_wordt_niet_nog_eens_uitgedeeld(self):
        """Een nieuw document met dezelfde key als een bestaand document krijgt niet diens primary_key."""
        docs = [
            {'_id': OID_A, 'key': 'PSY002S99'},   # bestaand document, vervangen: terug op _id
            {'_id': OID_B, 'key': 'PSY002S99'},   # kopie met dezelfde key
            {'_id': OID_C, 'key': 'PSY002S1', 'ID': 5},
            {'_id': OID_D, 'key': 'PSY002S1'},    # key wijst naar een ID dat in gebruik is
        ]
        pg = [{'primary_key': 3, '_id': str(OID_A), 'key': 'PSY002S99'}, {'primary_key': 5, '_id': str(OID_C), 'key': 'PSY002S1'}]
        toewijzing, tellingen = delta_transform.bepaalStabieleIds(docs, pg)
        # Nieuwe nummers in volgorde van key: PSY002S1 vóór PSY002S99
        assert dict(toewijzing) == {OID_A: 3, OID_D: 6, OID_B: 7}
        assert tellingen == {'behouden': 1, 'uit_bron': 0, 'op_id': 1, 'op_bestand': 0, 'op_vervangende_key': 0, 'op_key': 0, 'op_bronsleutel': 0, 'op_bronsleutel_andere_key': 0, 'op_bronsleutel_overgang': 0, 'nieuw': 2, 'nieuw_bronrij_bekend': 0}

    def test_soort_zonder_tabel(self):
        docs = [{'_id': OID_A, 'ID': 2}, {'_id': OID_B}, {'_id': OID_C, 'ID': float('nan')}]
        toewijzing, tellingen = delta_transform.bepaalStabieleIds(docs, None)
        assert sorted(i for _, i in toewijzing) == [3, 4]
        assert tellingen['behouden'] == 1

    def test_eerste_nummer_zonder_bestaande_sleutels(self):
        toewijzing, _ = delta_transform.bepaalStabieleIds([{'_id': OID_B, 'key': 'b'}, {'_id': OID_A, 'key': 'a'}], [])
        assert toewijzing == [(OID_B, 1), (OID_A, 0)]

    def test_verdwenen_primary_keys(self):
        pg = [{'primary_key': 1}, {'primary_key': 2}, {'primary_key': 3}]
        assert delta_transform.bepaalVerdwenenPrimaryKeys(pg, [1, 3, 4]) == [2]
        assert delta_transform.bepaalVerdwenenPrimaryKeys(None, [1]) == []

    def test_tabel_per_soort(self):
        assert delta_transform.getTabelVoorSoort('Vondst') == 'Def_Vondst'
        assert delta_transform.getTabelVoorSoort('Foto') == 'Def_Bestand'
        assert delta_transform.getTabelVoorSoort('Tekening') == 'Def_Bestand'
        assert delta_transform.getTabelVoorSoort('Bestand') == 'Def_Bestand'
        assert delta_transform.getTabelVoorSoort('Fotobeschrijving') is None
        assert delta_transform.getTabelVoorSoort('Fotokoppel') is None

    def test_set_stabiele_primary_keys_schrijft_alleen_id(self, client, monkeypatch):
        col = clean(client)
        col.insert_many([
            {'_id': OID_A, 'soort': 'Vondst', 'key': 'PSY001P1V1', 'ID': 0, 'projectID': 0},
            {'_id': OID_B, 'soort': 'Vondst', 'key': 'PSY002P1V1', 'projectcd': 'SY002'},
            {'_id': OID_C, 'soort': 'Vondst', 'key': 'PSY003P1V1'},
        ])
        monkeypatch.setattr(delta_transform, 'leesPgSleutels', lambda tabel: [
            {'primary_key': 0, '_id': str(OID_A), 'key': 'PSY001P1V1'},
            {'primary_key': 1, '_id': 'oud', 'key': 'PSY002P1V1'},
            {'primary_key': 2, '_id': 'weg', 'key': 'PSY002P9V9'}])
        startRunMet()
        assert delta_transform.setStabielePrimaryKeys('Vondst', col) is True
        docs = {d['_id']: d for d in col.find({})}
        assert docs[OID_A] == {'_id': OID_A, 'soort': 'Vondst', 'key': 'PSY001P1V1', 'ID': 0, 'projectID': 0}
        assert docs[OID_B] == {'_id': OID_B, 'soort': 'Vondst', 'key': 'PSY002P1V1', 'projectcd': 'SY002', 'ID': 1}
        assert docs[OID_C]['ID'] == 3
        telling = verwerkingsrun.huidigeRun()['tellingen']['transform']['primary_keys']['Vondst']
        assert telling == {'behouden': 1, 'uit_bron': 0, 'op_id': 0, 'op_bestand': 0, 'op_vervangende_key': 0, 'op_key': 1, 'op_bronsleutel': 0, 'op_bronsleutel_andere_key': 0, 'op_bronsleutel_overgang': 0, 'nieuw': 1, 'nieuw_bronrij_bekend': 0,
                           'verdwenen': 1, 'tabel': 'Def_Vondst'}

    def test_lege_database_volgt_oude_gedrag(self, client, monkeypatch):
        col = clean(client)
        col.insert_many([{'_id': OID_A, 'soort': 'Vondst', 'key': 'a'}])
        monkeypatch.setattr(delta_transform, 'leesPgSleutels', lambda tabel: None)
        assert delta_transform.setStabielePrimaryKeys('Vondst', col) is False
        assert 'ID' not in col.find_one({'_id': OID_A})

    def test_ontbrekende_tabel_met_bestaande_ids_nummert_door(self, client, monkeypatch):
        col = clean(client)
        col.insert_many([{'_id': OID_A, 'soort': 'Vondst', 'key': 'a', 'ID': 4}, {'_id': OID_B, 'soort': 'Vondst', 'key': 'b'}])
        monkeypatch.setattr(delta_transform, 'leesPgSleutels', lambda tabel: None)
        assert delta_transform.setStabielePrimaryKeys('Vondst', col) is True
        assert col.find_one({'_id': OID_B})['ID'] == 5


@pytest.mark.unit
class TestArtefactSleutel:
    """Test de samengestelde sleutel van artefacten (key_subnr|artefactsoort, fase 3)."""

    @pytest.mark.parametrize('doc, verwacht', [
        ({'key': 'PSY001P1V1A5', 'key_subnr': 'PSY001P1V1A1', 'artefactsoort': 'Glas'}, 'PSY001P1V1A5'),
        ({'key_subnr': 'PSY001P1V1A1', 'artefactsoort': 'Glas'}, 'PSY001P1V1A1|Glas'),
        ({'key': None, 'key_subnr': 'PSY001P1V1A1', 'artefactsoort': 'Aardewerk'}, 'PSY001P1V1A1|Aardewerk'),
        ({'key': float('nan'), 'key_subnr': 'PSY001P1V1A1', 'artefactsoort': 'Aardewerk'}, 'PSY001P1V1A1|Aardewerk'),
        ({'key': '', 'key_subnr': 'PSY001P1V1A1'}, 'PSY001P1V1A1|'),
        ({'key_subnr': 'PSY001P1V1A1', 'artefactsoort': float('nan')}, 'PSY001P1V1A1|'),
        ({'artefactsoort': 'Glas'}, None),
        ({'key_subnr': float('nan'), 'artefactsoort': 'Glas'}, None),
    ])
    def test_artefact_key(self, doc, verwacht):
        assert delta_transform.getArtefactKey(doc) == verwacht

    def test_opnieuw_ingelezen_artefact_op_samengestelde_sleutel(self, client, monkeypatch):
        """Een artefact met een nieuw _id (gewijzigde database) krijgt zijn primary_key terug op key_subnr|artefactsoort."""
        col = clean(client)
        col.insert_many([
            {'_id': OID_A, 'soort': 'Artefact', 'key_subnr': 'PSY002P1V1A1', 'artefactsoort': 'Aardewerk', 'ID': 3},
            {'_id': OID_B, 'soort': 'Artefact', 'key_subnr': 'PSY003P1V1A1', 'artefactsoort': 'Aardewerk'},
            {'_id': OID_C, 'soort': 'Artefact', 'key_subnr': 'PSY003P1V1A1', 'artefactsoort': 'Glas'},
            {'_id': OID_D, 'soort': 'Artefact', 'key_subnr': 'PSY003P1V1A2', 'artefactsoort': 'Glas'},
        ])
        monkeypatch.setattr(delta_transform, 'leesPgSleutels', lambda tabel: [
            {'primary_key': 3, '_id': str(OID_A), 'key': 'PSY002P1V1A1|Aardewerk'},
            {'primary_key': 7, '_id': 'oud_1', 'key': 'PSY003P1V1A1|Aardewerk'},
            {'primary_key': 8, '_id': 'oud_2', 'key': 'PSY003P1V1A1|Glas'},
            {'primary_key': 9, '_id': 'weg', 'key': 'PSY003P1V1A9|Glas'},
        ])
        startRunMet()
        assert delta_transform.setStabielePrimaryKeys('Artefact', col) is True
        ids = {d['_id']: d['ID'] for d in col.find({})}
        assert ids == {OID_A: 3, OID_B: 7, OID_C: 8, OID_D: 10}
        # Alleen het veld ID is geschreven, niet de (samengestelde) key
        assert all('key' not in d for d in col.find({}))
        telling = verwerkingsrun.huidigeRun()['tellingen']['transform']['primary_keys']['Artefact']
        assert telling == {'behouden': 1, 'uit_bron': 0, 'op_id': 0, 'op_bestand': 0, 'op_vervangende_key': 0, 'op_key': 2, 'op_bronsleutel': 0, 'op_bronsleutel_andere_key': 0, 'op_bronsleutel_overgang': 0, 'nieuw': 1, 'nieuw_bronrij_bekend': 0,
                           'verdwenen': 1, 'tabel': 'Def_Artefact'}

    def test_dubbele_samengestelde_sleutel_wordt_niet_gebruikt(self, client, monkeypatch):
        col = clean(client)
        col.insert_many([{'_id': OID_A, 'soort': 'Artefact', 'key_subnr': 'PSY003P1V1A1', 'artefactsoort': 'Munt'}])
        monkeypatch.setattr(delta_transform, 'leesPgSleutels', lambda tabel: [
            {'primary_key': 1, '_id': 'x', 'key': 'PSY003P1V1A1|Munt'},
            {'primary_key': 2, '_id': 'y', 'key': 'PSY003P1V1A1|Munt'}])
        assert delta_transform.setStabielePrimaryKeys('Artefact', col) is True
        assert col.find_one({'_id': OID_A})['ID'] == 3

    def test_lees_pg_sleutels_met_cursor(self):
        """leesPgSleutels gebruikt een meegegeven cursor in plaats van een eigen verbinding."""
        class NepCursor:
            def __init__(self):
                self.sql = []
                self.resultaat = []

            def execute(self, sql, params=None):
                self.sql.append(sql)
                if 'information_schema.columns' in sql:
                    self.resultaat = [('primary_key',), ('_id',), ('key',), ('naam',)]
                else:
                    self.resultaat = [(1, 'a', 'PSY001'), (2, 'b', None)]

            def fetchall(self):
                return self.resultaat

        cursor = NepCursor()
        rijen = delta_transform.leesPgSleutels('Def_Vondst', cursor=cursor)
        assert rijen == [{'primary_key': 1, '_id': 'a', 'key': 'PSY001'}, {'primary_key': 2, '_id': 'b', 'key': None}]
        assert cursor.sql[-1] == 'SELECT "primary_key", "_id", "key" FROM "Def_Vondst"'


# ============================================================
# Klasse 5b: stabiele sleutels in de volledige cyclus (issue 71)
# ============================================================

class _NepOperator:
    """Nabootsing van een Airflow-operator: legt task_id en op_kwargs vast en ondersteunt >>."""

    def __init__(self, task_id, python_callable=None, op_kwargs=None, **kwargs):
        self.task_id = task_id
        self.python_callable = python_callable
        self.op_kwargs = op_kwargs or {}
        _NepOperator.aangemaakt.append(self)

    def __rshift__(self, ander):
        return ander


class _NepTaskGroup:
    def __init__(self, group_id):
        self.group_id = group_id

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def laadTransform4Taakgroep(monkeypatch):
    """Importeer tasks_transform4_references met een nagebootst Airflow (niet geïnstalleerd in de testomgeving)."""
    _NepOperator.aangemaakt = []
    modules = {
        'airflow': types.ModuleType('airflow'),
        'airflow.utils': types.ModuleType('airflow.utils'),
        'airflow.utils.task_group': types.SimpleNamespace(TaskGroup=_NepTaskGroup),
        'airflow.operators': types.ModuleType('airflow.operators'),
        'airflow.operators.bash': types.SimpleNamespace(BashOperator=_NepOperator),
        'airflow.operators.dummy': types.SimpleNamespace(DummyOperator=_NepOperator),
        'airflow.operators.python': types.SimpleNamespace(PythonOperator=_NepOperator),
    }
    for naam, module in modules.items():
        monkeypatch.setitem(sys.modules, naam, module)
    monkeypatch.delitem(sys.modules, 'tasks_transform4_references', raising=False)
    import tasks_transform4_references
    return tasks_transform4_references


@pytest.mark.unit
class TestStabieleSleutelsVolledigeCyclus:
    """Transform 4 kent ook in de volledige cyclus stabiele sleutels toe (issue 71).

    In de volledige cyclus is MongoDB geleegd: geen document heeft een ID en elk
    _id is nieuw. De primary_key komt dan uit de bron (ABR), via de map en
    bestandsnaam (bestanden) of via een unieke key uit PostgreSQL.
    """

    def test_taakgroep_geeft_altijd_stabiel(self, monkeypatch):
        module = laadTransform4Taakgroep(monkeypatch)
        module.getSetReferencesTaskGroup()
        sleuteltaken = [t for t in _NepOperator.aangemaakt if t.task_id.startswith('Set_PrimaryKey_')]
        assert sleuteltaken, "Geen Set_PrimaryKey-taken aangemaakt"
        assert {t.task_id for t in sleuteltaken} == {f'Set_PrimaryKey_{s}' for s in meta.getKeys(meta.SET_KEYS_PIPELINES)}
        for taak in sleuteltaken:
            assert taak.python_callable is references_functions.setPrimaryKeys
            assert taak.op_kwargs['stabiel'] is True, taak.task_id

    def test_nieuwe_id_s_terug_op_key_en_nieuwe_nummers_boven_maximum(self):
        """Na een nieuwe extractie: elk document zonder ID en met een nieuw _id."""
        docs = [
            {'_id': OID_A, 'key': 'PSY001P1'},      # unieke key: oude primary_key
            {'_id': OID_B, 'key': 'PSY001P2'},      # unieke key: oude primary_key
            {'_id': OID_C, 'key': 'PSY001P3'},      # nieuwe put
        ]
        pg = [
            {'primary_key': 0, '_id': 'oud_a', 'key': 'PSY001P1'},
            {'primary_key': 5, '_id': 'oud_b', 'key': 'PSY001P2'},
            {'primary_key': 8, '_id': 'oud_c', 'key': 'PSY001P9'},   # verdwenen put
        ]
        toewijzing, tellingen = delta_transform.bepaalStabieleIds(docs, pg)
        assert dict(toewijzing) == {OID_A: 0, OID_B: 5, OID_C: 9}
        assert tellingen == {'behouden': 0, 'uit_bron': 0, 'op_id': 0, 'op_bestand': 0, 'op_vervangende_key': 0, 'op_key': 2, 'op_bronsleutel': 0, 'op_bronsleutel_andere_key': 0, 'op_bronsleutel_overgang': 0, 'nieuw': 1, 'nieuw_bronrij_bekend': 0}

    def test_zelfde_key_twee_documenten(self):
        """Twee documenten met dezelfde (in PostgreSQL unieke) key: het eerste krijgt de oude primary_key."""
        docs = [{'_id': OID_A, 'key': 'PSY001P1'}, {'_id': OID_B, 'key': 'PSY001P1'}]
        toewijzing, tellingen = delta_transform.bepaalStabieleIds(docs, [{'primary_key': 3, '_id': 'x', 'key': 'PSY001P1'}])
        assert dict(toewijzing) == {OID_A: 3, OID_B: 4}
        assert tellingen['op_key'] == 1 and tellingen['nieuw'] == 1

    def test_primary_key_uit_de_bron(self):
        """ABR: de primary_key uit de thesaurus wordt het ID (parentID verwijst ernaar), ook als de key dubbel is."""
        docs = [
            {'_id': OID_A, 'key': 'Ahttp://abr/1', 'primary_key': 31},
            {'_id': OID_B, 'key': 'Ahttp://abr/1', 'primary_key': 32.0},
            {'_id': OID_C, 'key': 'Ahttp://abr/2', 'primary_key': float('nan')},
        ]
        pg = [{'primary_key': 31, '_id': 'x', 'key': 'Ahttp://abr/1'}, {'primary_key': 32, '_id': 'y', 'key': 'Ahttp://abr/1'},
              {'primary_key': 7, '_id': 'z', 'key': 'Ahttp://abr/2'}]
        toewijzing, tellingen = delta_transform.bepaalStabieleIds(docs, pg)
        assert dict(toewijzing) == {OID_A: 31, OID_B: 32, OID_C: 7}
        assert tellingen['uit_bron'] == 2 and tellingen['op_key'] == 1

    def test_primary_key_uit_de_bron_telt_mee_voor_het_maximum(self):
        docs = [{'_id': OID_A, 'key': 'a', 'primary_key': 40}, {'_id': OID_B, 'key': 'b'}]
        toewijzing, _ = delta_transform.bepaalStabieleIds(docs, [{'primary_key': 3, '_id': 'x', 'key': 'z'}])
        assert dict(toewijzing) == {OID_A: 40, OID_B: 41}

    @pytest.mark.parametrize('waarde, verwacht', [
        (5, 5), (5.0, 5), ('7', 7), (None, None), (float('nan'), None), (2.5, None), ('x', None), (True, None)])
    def test_bron_primary_key(self, waarde, verwacht):
        assert delta_transform.getBronPrimaryKey({'primary_key': waarde}) == verwacht

    def test_bestanden_op_map_en_bestandsnaam(self):
        """Foto's met dezelfde key (sfeer- en opgravingsfoto) houden hun primary_key via map en bestandsnaam."""
        map_ = '/input/projecten/SY001/L Fotos'
        docs = [
            {'_id': OID_A, 'key': 'PSY001S1', 'directory': map_, 'fileName': 'SY001_F001.jpg'},
            {'_id': OID_B, 'key': 'PSY001S1', 'directory': map_ + '/', 'fileName': 'SY001_G001.jpg'},
            {'_id': OID_C, 'key': 'PSY001T1'},                       # tekening zonder bestand: op key
        ]
        pg = [
            {'primary_key': 4, '_id': 'x', 'key': 'PSY001S1', 'directory': map_, 'fileName': 'SY001_G001.jpg'},
            {'primary_key': 6, '_id': 'y', 'key': 'PSY001S1', 'directory': map_, 'fileName': 'SY001_F001.jpg'},
            {'primary_key': 9, '_id': 'z', 'key': 'PSY001T1', 'directory': None, 'fileName': None},
        ]
        toewijzing, tellingen = delta_transform.bepaalStabieleIds(docs, pg)
        assert dict(toewijzing) == {OID_A: 6, OID_B: 4, OID_C: 9}
        assert tellingen['op_bestand'] == 2 and tellingen['op_key'] == 1 and tellingen['nieuw'] == 0

    def test_dubbel_bestand_in_tabel_wordt_niet_gebruikt(self):
        map_ = '/input/projecten/SY001/L Fotos'
        docs = [{'_id': OID_A, 'key': 'PSY001S1', 'directory': map_, 'fileName': 'SY001_F001.jpg'}]
        pg = [{'primary_key': 4, '_id': 'x', 'key': 'PSY001S1', 'directory': map_, 'fileName': 'SY001_F001.jpg'},
              {'primary_key': 6, '_id': 'y', 'key': 'PSY001S1', 'directory': map_, 'fileName': 'SY001_F001.jpg'}]
        toewijzing, tellingen = delta_transform.bepaalStabieleIds(docs, pg)
        assert toewijzing == [(OID_A, 7)] and tellingen['nieuw'] == 1

    def test_bestand_identiteit(self):
        assert delta_transform.getBestandIdentiteit({'directory': '/a/b/', 'fileName': 'c.jpg'}) == '/a/b/c.jpg'
        assert delta_transform.getBestandIdentiteit({'directory': '/a/b', 'fileName': 'c.jpg'}) == '/a/b/c.jpg'
        assert delta_transform.getBestandIdentiteit({'directory': '', 'fileName': 'c.jpg'}) is None
        assert delta_transform.getBestandIdentiteit({'fileName': 'c.jpg'}) is None

    def test_lees_pg_sleutels_leest_bestandsidentiteit(self):
        class NepCursor:
            def __init__(self):
                self.sql = []

            def execute(self, sql, params=None):
                self.sql.append(sql)

            def fetchall(self):
                if len(self.sql) == 1:
                    return [('primary_key',), ('_id',), ('key',), ('directory',), ('fileName',), ('fileSize',)]
                return [(1, 'a', 'PSY001S1', '/m', 'f.jpg')]

        cursor = NepCursor()
        rijen = delta_transform.leesPgSleutels('Def_Bestand', cursor=cursor)
        assert cursor.sql[-1] == 'SELECT "primary_key", "_id", "key", "directory", "fileName" FROM "Def_Bestand"'
        assert rijen == [{'primary_key': 1, '_id': 'a', 'key': 'PSY001S1', 'directory': '/m', 'fileName': 'f.jpg'}]

    def _cleanVoorSetPrimaryKeys(self, client, monkeypatch, docs):
        col = clean(client)
        col.insert_many(docs)
        col.database = types.SimpleNamespace(client=types.SimpleNamespace(close=lambda: None))
        monkeypatch.setattr(references_functions, 'getAnalyseCleanCollection', lambda: col)
        return col

    def test_set_primary_keys_volledige_cyclus_houdt_sleutels(self, client, monkeypatch):
        """setPrimaryKeys(stabiel=True) na een volledige extractie: zelfde primary_keys, alleen ID geschreven."""
        col = self._cleanVoorSetPrimaryKeys(client, monkeypatch, [
            {'_id': OID_A, 'soort': 'Vondst', 'key': 'PSY002P1V1', 'projectcd': 'SY002'},
            {'_id': OID_B, 'soort': 'Vondst', 'key': 'PSY001P1V1', 'projectcd': 'SY001'},
            {'_id': OID_C, 'soort': 'Vondst', 'key': 'PSY003P1V1', 'projectcd': 'SY003'},
        ])
        monkeypatch.setattr(delta_transform, 'leesPgSleutels', lambda tabel: [
            {'primary_key': 0, '_id': 'oud_1', 'key': 'PSY001P1V1'},
            {'primary_key': 1, '_id': 'oud_2', 'key': 'PSY002P1V1'}])
        references_functions.setPrimaryKeys('Vondst', col='analyseclean', stabiel=True)
        docs = {d['_id']: d for d in col.find({})}
        assert {k: d['ID'] for k, d in docs.items()} == {OID_A: 1, OID_B: 0, OID_C: 2}
        assert docs[OID_A] == {'_id': OID_A, 'soort': 'Vondst', 'key': 'PSY002P1V1', 'projectcd': 'SY002', 'ID': 1}

    def test_set_primary_keys_eerste_run_in_lege_tabel(self, client, monkeypatch):
        """Een lege tabel (eerste run, tabellen door de webapplicatie aangemaakt): nummers vanaf 0."""
        col = self._cleanVoorSetPrimaryKeys(client, monkeypatch, [
            {'_id': OID_A, 'soort': 'Vondst', 'key': 'b'}, {'_id': OID_B, 'soort': 'Vondst', 'key': 'a'}])
        monkeypatch.setattr(delta_transform, 'leesPgSleutels', lambda tabel: [])
        references_functions.setPrimaryKeys('Vondst', col='analyseclean', stabiel=True)
        assert {d['_id']: d['ID'] for d in col.find({})} == {OID_A: 1, OID_B: 0}

    def test_set_primary_keys_zonder_tabel_nummert_zoals_voorheen(self, client, monkeypatch):
        """Geen tabel en geen ID's: volgnummers vanaf 0 in de volgorde van de collectie (oude gedrag)."""
        col = self._cleanVoorSetPrimaryKeys(client, monkeypatch, [
            {'_id': OID_A, 'soort': 'Vondst', 'key': 'b'}, {'_id': OID_B, 'soort': 'Vondst', 'key': 'a'}])
        monkeypatch.setattr(delta_transform, 'leesPgSleutels', lambda tabel: None)
        references_functions.setPrimaryKeys('Vondst', col='analyseclean', stabiel=True)
        assert {d['_id']: d['ID'] for d in col.find({})} == {OID_A: 0, OID_B: 1}

    def test_set_primary_keys_abr_houdt_bron_primary_key(self, client, monkeypatch):
        col = self._cleanVoorSetPrimaryKeys(client, monkeypatch, [
            {'_id': OID_A, 'soort': 'ABR', 'key': 'Ahttp://abr/1', 'primary_key': 31},
            {'_id': OID_B, 'soort': 'ABR', 'key': 'Ahttp://abr/1', 'primary_key': 0}])
        monkeypatch.setattr(delta_transform, 'leesPgSleutels', lambda tabel: [])
        references_functions.setPrimaryKeys('ABR', col='analyseclean', stabiel=True)
        assert {d['_id']: d['ID'] for d in col.find({})} == {OID_A: 31, OID_B: 0}


# ============================================================
# Klasse 6: delta-varianten met de nagebootste MongoDB
# ============================================================

class NepProfiel:
    """Gemeenteprofiel dat elk bestand als foto van SY003 herkent."""

    def extract_projectcode_uit_bestandsnaam(self, fileName, directory):
        return fileName.split('_')[0]

    def identificeer_foto(self, doc, projectcd):
        doc['projectcd'] = projectcd
        doc['soort'] = 'Foto'
        return doc


@pytest.mark.unit
class TestDeltaMetNepMongo:
    """Test de delta-varianten die direct met MongoDB werken."""

    def test_parse_fotobestanden_alleen_delta_met_delta_run(self, client, monkeypatch):
        monkeypatch.setattr(harmonize_functions.pymongo, 'MongoClient', lambda *a, **k: client)
        monkeypatch.setattr(harmonize_functions, 'get_profiel', lambda: NepProfiel())
        client[config.DB_STAGING][config.COLL_PLAATJES].insert_many([
            {'_id': 'p3', 'fileName': 'SY003_F001.jpg', 'fullFileName': FOTO_SY003, 'fileType': '.jpg'},
            {'_id': 'p1', 'fileName': 'SY001_F001.jpg', 'fullFileName': FOTO_SY001, 'fileType': '.jpg'},
        ])
        run = startRunMet(nieuw={'afbeeldingen': [FOTO_SY003]}, ongewijzigd={'afbeeldingen': [FOTO_SY001]})

        harmonize_functions.parseFotobestanden(incrementeel=True)

        docs = list(analyse(client).find({}))
        assert [(d['_id'], d['soort'], d['projectcd'], d['delta_run']) for d in docs] == [('p3', 'Foto', 'SY003', run['run_id'])]

    def test_fix_monster_projectcds_alleen_delta(self, client, monkeypatch):
        monkeypatch.setattr(harmonize_functions.pymongo, 'MongoClient', lambda *a, **k: client)
        run = startRunMet()
        analyse(client).insert_many([
            {'_id': 1, 'soort': 'Monster', 'projectcd': 'SY001'},  # niet in de delta: blijft
            {'_id': 2, 'soort': 'Monster', 'projectcd': 'X', 'delta_run': run['run_id']},  # zonder PROJECT: wordt None
        ])
        harmonize_functions.fixMonsterProjectcds(incrementeel=True)
        assert analyse(client).find_one({'_id': 1})['projectcd'] == 'SY001'
        assert analyse(client).find_one({'_id': 2})['projectcd'] is None

    def test_geen_geraakte_sleutels_slaat_merge_over(self, client, monkeypatch):
        opname = OpnameCollectie()
        opname.find = lambda *a, **k: iter([])
        opname.database = _DatabaseVan(client)
        monkeypatch.setattr(merge_functions, 'getAnalyseCollection', lambda: opname)
        startRunMet()
        merge_functions.mergeSoort('Vondst', incrementeel=True)
        assert opname.pipelines == []
        assert verwerkingsrun.huidigeRun()['tellingen']['transform']['merge']['Vondst'] == {'sleutels': 0, 'verwijderd': 0}

    def test_merge_soort_delta(self, client, monkeypatch):
        run = startRunMet(verwijderde_keys={'Vondst': [{'key': 'PSY003P4V12', 'projectcd': 'SY003'}]})
        analyse(client).insert_one({'_id': 1, 'soort': 'Vondst', 'key': 'PSY003P1V1', 'delta_run': run['run_id']})
        clean(client).insert_many([
            {'_id': 'oud1', 'soort': 'Vondst', 'key': 'PSY003P1V1', 'brondata_count': 1},
            {'_id': 'oud2', 'soort': 'Vondst', 'key': 'PSY003P4V12', 'brondata_count': 1},
        ])
        pipelines = []
        origineel = analyse(client).aggregate

        def aggregate(pipeline, **kwargs):
            if not any('$merge' in fase for fase in pipeline):
                return origineel(pipeline)  # bepaling van de geraakte projecten
            # Bootst de $merge na: het opnieuw samengevoegde document krijgt het _id van het brondocument
            pipelines.append(pipeline)
            clean(client).insert_one({'_id': 1, 'soort': 'Vondst', 'key': 'PSY003P1V1', 'brondata_count': 1, 'delta_run': run['run_id']})
            return iter([])

        col = analyse(client)
        col.aggregate = aggregate
        col.database = _DatabaseVan(client)
        monkeypatch.setattr(merge_functions, 'getAnalyseCollection', lambda: col)

        merge_functions.mergeSoort('Vondst', incrementeel=True)

        assert pipelines[0][0] == {'$match': {'soort': 'Vondst', 'key': {'$in': ['PSY003P1V1', 'PSY003P4V12']}}}
        assert sorted(str(d['_id']) for d in clean(client).find({})) == ['1']
        assert verwerkingsrun.huidigeRun()['tellingen']['transform']['merge']['Vondst'] == {'sleutels': 2, 'verwijderd': 2}

    def test_enhance_all_attributes_filter(self, client, monkeypatch):
        opname = OpnameCollectie()
        monkeypatch.setattr(harmonize_functions, 'laadCorrecties', lambda: {})
        import wasstraat.setAttributes_functions as setAttributes_functions
        monkeypatch.setattr(setAttributes_functions.pymongo, 'MongoClient', lambda *a, **k: _OpnameClient(opname))
        run = startRunMet()
        setAttributes_functions.enhanceAllAttributes(incrementeel=True)
        setAttributes_functions.enhanceAllAttributes()
        assert opname.filters == [{'delta_run': run['run_id']}, {}]


class _DatabaseVan:
    """Database-attribuut van een collectie (collection.database) voor de nep-client."""

    def __init__(self, client):
        self.client = client

    def __getitem__(self, naam):
        return self.client[config.DB_ANALYSE][naam]


# ============================================================
# Klasse 8: de vlag vondstkey_met_putnr bij een incrementele run
# ============================================================

@pytest.mark.unit
class TestVondstkeyVlag:
    """Test het opnieuw bepalen van de vlag vondstkey_met_putnr en de gevolgen voor Transform 3 en 5."""

    def test_soorten_met_vlag_volgen_meta(self):
        """SOORTEN_MET_VONDSTKEY_VLAG bevat precies de soorten waarvan een sleutelpipeline de vlag gebruikt."""
        met_vlag = [soort for soort in meta.getKeys(meta.SET_KEYS_PIPELINES)
                    if '$' + delta_transform.VELD_VONDSTKEY_VLAG in str(meta.getReferenceKeysPipeline(soort))]
        assert sorted(met_vlag) == sorted(delta_transform.SOORTEN_MET_VONDSTKEY_VLAG)

    def _analyseMetVlag(self, client, monkeypatch, projecten_met_dubbele_vondstnrs):
        """Single_Store met SY002 (geraakt, had de vlag), SY001 (niet geraakt, vlag blijft) en SY003 (geraakt, houdt de vlag)."""
        run = startRunMet(geraakte_projecten=['SY002', 'SY003'])
        run_id = run['run_id']
        col = analyse(client)
        col.insert_many([
            # SY002: de vondsten zijn opnieuw ingelezen (delta) en vondstnr 5 staat nu in één put
            {'_id': 1, 'soort': 'Vondst', 'projectcd': 'SY002', 'putnr': 1, 'vondstnr': 5, 'delta_run': run_id},
            # foto uit de fotolijst, niet opnieuw verwerkt, met de oude vlag
            {'_id': 2, 'soort': 'Foto', 'projectcd': 'SY002', 'putnr': 1, 'vondstnr': 5, 'vondstkey_met_putnr': True},
            {'_id': 3, 'soort': 'Monster', 'projectcd': 'SY002', 'putnr': 1, 'vondstnr': 5, 'vondstkey_met_putnr': True},
            # SY001 is niet geraakt: de vlag blijft staan
            {'_id': 4, 'soort': 'Vondst', 'projectcd': 'SY001', 'putnr': 1, 'vondstnr': 1, 'vondstkey_met_putnr': True},
            # SY003: vondstnr 7 in twee putten, de vlag blijft nodig
            {'_id': 5, 'soort': 'Vondst', 'projectcd': 'SY003', 'putnr': 1, 'vondstnr': 7, 'delta_run': run_id},
            {'_id': 6, 'soort': 'Vondst', 'projectcd': 'SY003', 'putnr': 2, 'vondstnr': 7, 'vondstkey_met_putnr': True},
        ])
        origineel = col.aggregate
        pipelines = []

        def aggregate(pipeline, **kwargs):
            # De groepering op (projectcd, vondstnr) kent nep_mongo niet: geef het resultaat zelf
            if '$addToSet' in str(pipeline):
                pipelines.append(pipeline)
                return iter([{'projectcd': p} for p in projecten_met_dubbele_vondstnrs])
            return origineel(pipeline)

        col.aggregate = aggregate
        col.database = _DatabaseVan(client)
        monkeypatch.setattr(references_functions, 'getAnalyseCollection', lambda: col)
        return col, pipelines

    def test_vlag_wordt_weggehaald_en_alleen_waar_nodig_teruggezet(self, client, monkeypatch):
        col, pipelines = self._analyseMetVlag(client, monkeypatch, ['SY003'])

        references_functions.setAndVondstUniqueInProject(incrementeel=True)

        vlag = {d['_id']: d.get('vondstkey_met_putnr') for d in col.find({})}
        assert vlag == {1: None, 2: None, 3: None, 4: True, 5: True, 6: True}
        # De bepaling van de dubbele vondstnummers kijkt alleen naar de geraakte projecten
        assert pipelines[0][0] == {'$match': {'projectcd': {'$in': ['SY002', 'SY003']}}}

    def test_vlag_weg_ook_als_geen_project_hem_meer_nodig_heeft(self, client, monkeypatch):
        col, _ = self._analyseMetVlag(client, monkeypatch, [])

        references_functions.setAndVondstUniqueInProject(incrementeel=True)

        vlag = {d['_id']: d.get('vondstkey_met_putnr') for d in col.find({})}
        assert vlag == {1: None, 2: None, 3: None, 4: True, 5: None, 6: None}

    def test_volledige_cyclus_haalt_de_vlag_niet_weg(self, client, monkeypatch):
        col, _ = self._analyseMetVlag(client, monkeypatch, ['SY003'])

        references_functions.setAndVondstUniqueInProject()

        vlag = {d['_id']: d.get('vondstkey_met_putnr') for d in col.find({})}
        assert vlag == {1: None, 2: True, 3: True, 4: True, 5: True, 6: True}

    def test_set_reference_keys_neemt_geraakte_projecten_mee(self, client, monkeypatch):
        run = startRunMet(geraakte_projecten=['SY002'])
        opname = OpnameCollectie()
        monkeypatch.setattr(references_functions, 'getAnalyseCollection', lambda: opname)

        references_functions.setReferenceKeys(meta.getReferenceKeysPipeline('Vondst'), 'Vondst', incrementeel=True)
        references_functions.setReferenceKeys(meta.getReferenceKeysPipeline('Monster'), 'Monster', incrementeel=True)
        references_functions.setReferenceKeys(meta.getReferenceKeysPipeline('Foto'), 'Foto', incrementeel=True)

        delta_of_project = {'$or': [{'delta_run': run['run_id']}, {'projectcd': {'$in': ['SY002']}}]}
        assert opname.pipelines[0][0] == {'$match': dict({'soort': 'Vondst'}, **delta_of_project)}
        assert opname.pipelines[1][0] == {'$match': dict({'soort': 'Monster', 'projectcd': {'$exists': True}}, **delta_of_project)}
        # De sleutels van foto's hangen niet van de vlag af: alleen de delta
        assert opname.pipelines[2][0] == {'$match': {'soort': 'Foto', 'delta_run': run['run_id']}}

    def test_move_neemt_geraakte_projecten_mee_met_delta_run(self, client, monkeypatch):
        run = startRunMet(geraakte_projecten=['SY002'])
        opname = OpnameCollectie()
        monkeypatch.setattr(merge_functions, 'getAnalyseCollection', lambda: opname)

        merge_functions.moveSoort('Spoor', incrementeel=True)
        merge_functions.moveSoort('Put', incrementeel=True)
        merge_functions.moveSoort('Spoor')

        spoor, put, volledig = opname.pipelines
        assert spoor[0] == {'$match': {'soort': 'Spoor', '$or': [{'delta_run': run['run_id']}, {'projectcd': {'$in': ['SY002']}}]}}
        assert spoor[-2] == {'$addFields': {'delta_run': run['run_id']}}
        assert '$merge' in spoor[-1]
        assert put[0] == {'$match': {'soort': 'Put', 'delta_run': run['run_id']}}
        assert volledig[0] == {'$match': {'soort': 'Spoor'}}
        assert not any('delta_run' in fase.get('$addFields', {}) for fase in volledig)

    def test_geraakte_sleutels_vondst_met_oude_en_nieuwe_sleutel(self, client):
        """Na het wegvallen van de vlag: de nieuwe sleutel uit Single_Store en de oude uit Single_Store_Clean."""
        analyse(client).insert_many([
            {'_id': 1, 'soort': 'Vondst', 'key': 'PSY002V5', 'projectcd': 'SY002'},           # niet in de delta, nieuwe sleutel
            {'_id': 2, 'soort': 'Vondst', 'key': 'PSY001P1V1', 'projectcd': 'SY001'},         # niet geraakt
            {'_id': 3, 'soort': 'Tekening', 'key': 'PSY002T1', 'projectcd': 'SY002'},         # niet afhankelijk van de vlag
        ])
        clean(client).insert_many([
            {'_id': 'oud', 'soort': 'Vondst', 'key': 'PSY002P1V5', 'projectcd': 'SY002', 'brondata_count': 1},
            {'_id': 'gen', 'soort': 'Vondst', 'key': 'PSY002P2V9', 'projectcd': 'SY002', 'brondata': {'table': 'generated_vondst'}},
            {'_id': 't1', 'soort': 'Bestand', 'bestandsoort_XX': 'Tekening', 'key': 'PSY002T1', 'projectcd': 'SY002', 'brondata_count': 1},
        ])
        run = {'run_id': RUN_ID, 'geraakte_projecten': ['SY002']}

        assert delta_transform.bepaalGeraakteSleutels('Vondst', analyse(client), run, clean(client)) == ['PSY002P1V5', 'PSY002V5']
        assert delta_transform.bepaalGeraakteSleutels('Vondst', analyse(client), run) == ['PSY002V5']
        assert delta_transform.bepaalGeraakteSleutels('Tekening', analyse(client), run, clean(client)) == []

    def test_merge_vondst_ruimt_oude_sleutel_op(self, client, monkeypatch):
        run = startRunMet(geraakte_projecten=['SY002'])
        analyse(client).insert_one({'_id': 1, 'soort': 'Vondst', 'key': 'PSY002V5', 'projectcd': 'SY002'})
        clean(client).insert_one({'_id': 1, 'soort': 'Vondst', 'key': 'PSY002P1V5', 'projectcd': 'SY002', 'brondata_count': 1, 'ID': 12})
        pipelines = []

        origineel = analyse(client).aggregate

        def aggregate(pipeline, **kwargs):
            if not any('$merge' in fase for fase in pipeline):
                return origineel(pipeline)  # bepaling van de geraakte projecten
            # Bootst de $merge na: hetzelfde _id, nu met de nieuwe sleutel en zonder ID
            pipelines.append(pipeline)
            clean(client).delete_many({'_id': 1})
            clean(client).insert_one({'_id': 1, 'soort': 'Vondst', 'key': 'PSY002V5', 'projectcd': 'SY002', 'brondata_count': 1, 'delta_run': run['run_id']})
            return iter([])

        col = analyse(client)
        col.aggregate = aggregate
        col.database = _DatabaseVan(client)
        monkeypatch.setattr(merge_functions, 'getAnalyseCollection', lambda: col)

        merge_functions.mergeSoort('Vondst', incrementeel=True)

        assert pipelines[0][0] == {'$match': {'soort': 'Vondst', 'key': {'$in': ['PSY002P1V5', 'PSY002V5']}}}
        assert [d['key'] for d in clean(client).find({'soort': 'Vondst'})] == ['PSY002V5']
