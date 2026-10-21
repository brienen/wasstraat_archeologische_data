"""
Unit tests voor wasstraat/opruimen.py en de delta-varianten van de extractie
(incrementeel laden, issue 61).

Test de filters en de volledige werking van verwijderOudeRecords met een
nagebootste MongoDB (tests/unit/nep_mongo.py), een nep-GridFS en een
tijdelijke map voor AIRFLOW_OUTPUT_MEDIA. Daarnaast de delta-varianten van
image_import (Filenames), extract_referentietabellen en extract_extra_projects.
"""
import os
import sys
import types
import pytest
import pandas as pd
from bson import ObjectId

# Mock shared.image_util (wordt geïmporteerd door image_import.py, vereist PIL/pdf2image/magic)
if "shared.image_util" not in sys.modules:
    sys.modules["shared.image_util"] = types.ModuleType("shared.image_util")

import shared.config as config
import wasstraat.verwerkingsrun as verwerkingsrun
import wasstraat.opruimen as opruimen
import wasstraat.image_import as image_import
import wasstraat.extract_referentietabellen as extract_referentietabellen
import wasstraat.extract_extra_projects as extract_extra_projects
from tests.unit.nep_mongo import NepClient, NepGridFS


SY003_MDB = '/input/projecten/SY003/C Database/opgravingSY002.mdb'
SY001_MDB = '/input/projecten/SY001/C Database/opgravingSY001.mdb'
MAG_MDB = '/input/magazijnlijst/MAGAZIJN.mdb'
FOTO_SY003 = '/input/projecten/SY003/L Fotos/SY002_F001.jpg'
FOTO_SY001 = '/input/projecten/SY001/L Fotos/SY001_F001.jpg'
FOTO_OUD = '/input/projecten/SY003/L Fotos/oud.jpg'
GRIDFS_ID = ObjectId()


@pytest.fixture
def nep_client(monkeypatch):
    """Vervang de MongoClients door een in-memory nabootsing."""
    client = NepClient()
    monkeypatch.setattr(verwerkingsrun, '_getClient', lambda: client)
    monkeypatch.setattr(opruimen, '_getClient', lambda: client)
    return client


@pytest.fixture
def media(tmp_path, monkeypatch):
    """Tijdelijke AIRFLOW_OUTPUT_MEDIA."""
    monkeypatch.setattr(config, 'AIRFLOW_OUTPUT_MEDIA', str(tmp_path / 'archeomedia'))
    return tmp_path / 'archeomedia'


def maakMediabestand(media, file_id):
    pad = media / file_id.lstrip('/')
    pad.parent.mkdir(parents=True, exist_ok=True)
    pad.write_bytes(b'jpg')
    return pad


def mediaIds(dir, naam):
    return {'imageID': f'{dir}/{naam}.jpg', 'imageMiddleID': f'{dir}/{naam}-med.jpg', 'imageThumbID': f'{dir}/{naam}-sml.jpg'}


def startRunMet(client, **lijsten):
    """Start een run en zet de deltalijsten in het run-document."""
    verwerkingsrun.startRun('incrementeel')
    velden = {status: lijsten.get(status, {}) for status in verwerkingsrun.STATUSSEN_BESTAND}
    velden['registratie_leeg'] = lijsten.get('registratie_leeg', False)
    verwerkingsrun.werkRunBij(velden)


# ============================================================
# Klasse 1: bronnen en filters
# ============================================================

@pytest.mark.unit
class TestFilters:
    """Test de opbouw van de bronnen en filters."""

    def test_staging_bronnen_per_categorie(self):
        assert opruimen.getStagingBronnen('projecten') == [
            {'collectie': config.COLL_STAGING_OUD, 'veld': 'mdbfile', 'single_store_veld': 'brondata.mdbfile'}]
        assert opruimen.getStagingBronnen('monsterdatabase')[0]['collectie'] == config.COLL_STAGING_MONSTER
        assert opruimen.getStagingBronnen('rapporten')[0]['collectie'] == config.COLL_STAGING_RAPPORTEN
        assert opruimen.getStagingBronnen('extra_projecten') == [
            {'collectie': config.COLL_STAGING_PROJECTENLIJST, 'veld': 'mdbfile', 'single_store_veld': 'brondata.mdbfile'}]
        assert opruimen.getStagingBronnen('afbeeldingen') == [
            {'collectie': config.COLL_PLAATJES, 'veld': 'fullFileName', 'single_store_veld': 'fullFileName'}]
        # Het ABR-bestand is de enige bron van de referentietabellen-collectie
        assert opruimen.getStagingBronnen('referentietabellen') == [
            {'collectie': config.COLL_STAGING_REFERENTIETABELLEN, 'veld': None, 'single_store_veld': None}]
        assert opruimen.getStagingBronnen('bestandenlijst') == []

    def test_pad_en_id_filters(self):
        assert opruimen.maakPadFilter('mdbfile', [SY003_MDB]) == {'mdbfile': {'$in': [SY003_MDB]}}
        assert opruimen.maakPadFilter(None, [SY003_MDB]) == {}
        assert opruimen.maakIdFilter(['a', 'b']) == {'_id': {'$in': ['a', 'b']}}

    def test_batches(self):
        assert list(opruimen.inBatches(range(5), grootte=2)) == [[0, 1], [2, 3], [4]]

    def test_te_opruimen_paden_gewijzigd_verwijderd_en_nieuw(self):
        run = {'nieuw': {'projecten': [SY003_MDB]}, 'gewijzigd': {'magazijnlijst': [MAG_MDB]},
               'verwijderd': {'afbeeldingen': [FOTO_SY003]}, 'ongewijzigd': {'projecten': [SY001_MDB]},
               'registratie_leeg': False}
        assert opruimen.bepaalTeOpruimenPaden(run) == {
            'afbeeldingen': [FOTO_SY003], 'magazijnlijst': [MAG_MDB], 'projecten': [SY003_MDB]}

    def test_nieuw_niet_opruimen_bij_lege_registratie(self):
        run = {'nieuw': {'projecten': [SY003_MDB]}, 'registratie_leeg': True}
        assert opruimen.bepaalTeOpruimenPaden(run) == {}

    def test_verzamel_sleutels_met_artefact(self):
        docs = [
            {'_id': 1, 'soort': 'Vondst', 'key': 'PSY003V1', 'projectcd': 'SY003'},
            {'_id': 2, 'soort': 'Artefact', 'key': 'PSY003V1A1', 'projectcd': 'SY003', 'key_subnr': 'PSY003V1A1S1', 'artefactsoort': 'Glas'},
            {'_id': 3, 'soort': 'Vondst', 'key': 'PSY003V1', 'projectcd': 'SY003'},  # dubbel
            {'_id': 4, 'soort': 'Put', 'projectcd': 'SY004'},  # nog zonder key
        ]
        keys, projecten = opruimen.verzamelSleutels(docs)
        assert keys == {
            'Vondst': [{'key': 'PSY003V1', 'projectcd': 'SY003'}],
            'Artefact': [{'key': 'PSY003V1A1', 'projectcd': 'SY003', 'key_subnr': 'PSY003V1A1S1', 'artefactsoort': 'Glas'}],
        }
        assert projecten == {'SY003', 'SY004'}

    def test_artefact_zonder_key_met_key_subnr_telt_mee(self):
        """In Single_Store hebben artefacten vaak key: null; ze worden samengevoegd op key_subnr."""
        docs = [
            {'_id': 1, 'soort': 'Artefact', 'key': None, 'key_subnr': 'PSY003P1V1A1', 'artefactsoort': 'Aardewerk', 'projectcd': 'SY003'},
            {'_id': 2, 'soort': 'Fotobeschrijving', 'projectcd': 'SY003'},
        ]
        keys, projecten = opruimen.verzamelSleutels(docs)
        assert keys == {'Artefact': [{'key': None, 'projectcd': 'SY003', 'key_subnr': 'PSY003P1V1A1', 'artefactsoort': 'Aardewerk'}]}
        assert projecten == {'SY003'}

    def test_media_pad_afleiden(self, media):
        assert opruimen.bepaalMediaPad('/SY003/L Fotos/a.jpg') == os.path.join(os.path.realpath(str(media)), 'SY003', 'L Fotos', 'a.jpg')
        assert opruimen.bepaalMediaPad('/../../etc/passwd') is None
        assert opruimen.bepaalMediaPad('') is None
        assert opruimen.bepaalMediaPad(None) is None

    def test_gridfs_id_herkennen(self):
        assert opruimen.isGridfsId(str(GRIDFS_ID))
        assert opruimen.isGridfsId(GRIDFS_ID)
        assert not opruimen.isGridfsId('/SY003/L Fotos/a.jpg')


# ============================================================
# Klasse 2: verwijderOudeRecords
# ============================================================

@pytest.fixture
def gevulde_mongo(nep_client, media, monkeypatch):
    """Vul staging, Single_Store, Clean, Plaatjes, Filenames, GridFS en media voor SY001 en SY003."""
    staging = nep_client[config.DB_STAGING]
    analyse = nep_client[config.DB_ANALYSE]
    files = nep_client[config.DB_FILES]

    staging[config.COLL_STAGING_OUD].insert_many([
        {'_id': 'st_sy003_vondst', 'mdbfile': SY003_MDB, 'table': 'VONDST'},
        {'_id': 'st_sy003_artefact', 'mdbfile': SY003_MDB, 'table': 'ARTEFACT'},
        {'_id': 'st_sy001_vondst', 'mdbfile': SY001_MDB, 'table': 'VONDST'},
    ])
    staging[config.COLL_STAGING_MAGAZIJNLIJST].insert_one({'_id': 'st_mag', 'mdbfile': MAG_MDB, 'table': 'magazijnlijst'})
    ids_sy003 = mediaIds('/SY003/L Fotos', 'SY002_F001')
    ids_sy001 = mediaIds('/SY001/L Fotos', 'SY001_F001')
    staging[config.COLL_PLAATJES].insert_many([
        dict({'_id': 'pl_sy003', 'fullFileName': FOTO_SY003, 'projectcd': 'SY003'}, **ids_sy003),
        dict({'_id': 'pl_sy001', 'fullFileName': FOTO_SY001, 'projectcd': 'SY001'}, **ids_sy001),
        {'_id': 'pl_oud', 'fullFileName': FOTO_OUD, 'imageUUID': str(GRIDFS_ID)},
    ])

    analyse[config.COLL_ANALYSE].insert_many([
        {'_id': 'st_sy003_vondst', 'soort': 'Vondst', 'key': 'PSY003V1', 'projectcd': 'SY003', 'brondata': {'mdbfile': SY003_MDB}},
        {'_id': 'st_sy003_artefact', 'soort': 'Artefact', 'key': 'PSY003V1A1', 'key_subnr': 'PSY003V1A1S1',
         'artefactsoort': 'Glas', 'projectcd': 'SY003', 'brondata': {'mdbfile': SY003_MDB}},
        {'_id': 'st_sy001_vondst', 'soort': 'Vondst', 'key': 'PSY001V1', 'projectcd': 'SY001', 'brondata': {'mdbfile': SY001_MDB}},
        # Standplaats: de harmonisatie maakt een nieuw _id; alleen via brondata.mdbfile te vinden
        {'_id': ObjectId(), 'soort': 'Standplaats', 'key': 'S1V2', 'projectcd': 'SY001', 'brondata': {'mdbfile': MAG_MDB}},
        {'_id': 'pl_sy003', 'soort': 'Foto', 'key': 'FSY003F1', 'projectcd': 'SY003', 'fullFileName': FOTO_SY003},
    ])
    analyse[config.COLL_ANALYSE_CLEAN].insert_many([
        {'_id': 'st_sy003_vondst', 'soort': 'Vondst', 'key': 'PSY003V1'},
        {'_id': 'st_sy001_vondst', 'soort': 'Vondst', 'key': 'PSY001V1'},
        {'_id': {'key_subnr': 'PSY003V1A1S1', 'artefactsoort': 'Glas'}, 'soort': 'Artefact'},  # Merge-soort: fase 2
    ])
    files[config.COLL_FILENAMES].insert_many([
        {'iter': 0, 'filename': FOTO_SY003, 'processed': True},
        {'iter': 1, 'filename': FOTO_SY001, 'processed': True},
        {'iter': 2, 'filename': FOTO_OUD, 'processed': True},
    ])
    gridfs_store = NepGridFS([GRIDFS_ID])
    monkeypatch.setattr(opruimen, '_getGridFS', lambda filesdb: gridfs_store)

    mediabestanden = {naam: [maakMediabestand(media, v) for v in ids.values()]
                      for naam, ids in [('sy003', ids_sy003), ('sy001', ids_sy001)]}
    return types.SimpleNamespace(client=nep_client, staging=staging, analyse=analyse, files=files,
                                 gridfs=gridfs_store, media=mediabestanden)


def ids(col):
    return sorted(str(d['_id']) for d in col.find({}))


@pytest.mark.unit
class TestVerwijderOudeRecords:
    """Test de volledige opruimstap met nagebootste databases."""

    def test_verwijderd_project_en_afbeeldingen(self, gevulde_mongo):
        m = gevulde_mongo
        startRunMet(m.client, verwijderd={'projecten': [SY003_MDB], 'afbeeldingen': [FOTO_SY003, FOTO_OUD]},
                    ongewijzigd={'projecten': [SY001_MDB], 'afbeeldingen': [FOTO_SY001]})

        tellingen = opruimen.verwijderOudeRecords()

        assert ids(m.staging[config.COLL_STAGING_OUD]) == ['st_sy001_vondst']
        assert ids(m.staging[config.COLL_PLAATJES]) == ['pl_sy001']
        assert sorted(d['_id'] for d in m.analyse[config.COLL_ANALYSE].find({'projectcd': 'SY003'})) == []
        assert m.analyse[config.COLL_ANALYSE].count_documents({'_id': 'st_sy001_vondst'}) == 1
        # Clean: Move-document weg, Merge-document (afgeleid _id) blijft voor fase 2
        assert m.analyse[config.COLL_ANALYSE_CLEAN].count_documents({'_id': 'st_sy003_vondst'}) == 0
        assert m.analyse[config.COLL_ANALYSE_CLEAN].count_documents({'soort': 'Artefact'}) == 1
        assert m.analyse[config.COLL_ANALYSE_CLEAN].count_documents({'_id': 'st_sy001_vondst'}) == 1
        # Filenames, media en GridFS
        assert [d['filename'] for d in m.files[config.COLL_FILENAMES].find({})] == [FOTO_SY001]
        assert not any(p.exists() for p in m.media['sy003'])
        assert all(p.exists() for p in m.media['sy001'])
        assert m.gridfs.verwijderd == [GRIDFS_ID]

        assert tellingen['projecten'] == {config.COLL_STAGING_OUD: 2, 'single_store': 2, 'single_store_clean': 1}
        assert tellingen['afbeeldingen'][config.COLL_PLAATJES] == 2
        assert tellingen['afbeeldingen']['media'] == 3
        assert tellingen['afbeeldingen']['gridfs'] == 1
        assert tellingen['afbeeldingen']['filenames'] == 2

    def test_sleutels_en_projecten_in_run_document(self, gevulde_mongo):
        startRunMet(gevulde_mongo.client, verwijderd={'projecten': [SY003_MDB], 'afbeeldingen': [FOTO_SY003]})
        opruimen.verwijderOudeRecords()
        run = verwerkingsrun.huidigeRun()
        assert run['verwijderde_keys']['Vondst'] == [{'key': 'PSY003V1', 'projectcd': 'SY003'}]
        assert run['verwijderde_keys']['Artefact'] == [
            {'key': 'PSY003V1A1', 'projectcd': 'SY003', 'key_subnr': 'PSY003V1A1S1', 'artefactsoort': 'Glas'}]
        assert run['verwijderde_keys']['Foto'] == [{'key': 'FSY003F1', 'projectcd': 'SY003'}]
        assert run['geraakte_projecten'] == ['SY003']
        assert 'projecten' in run['tellingen']['opruimen']

    def test_gewijzigde_magazijnlijst_vindt_single_store_via_brondata(self, gevulde_mongo):
        m = gevulde_mongo
        startRunMet(m.client, gewijzigd={'magazijnlijst': [MAG_MDB]})
        opruimen.verwijderOudeRecords()
        assert m.staging[config.COLL_STAGING_MAGAZIJNLIJST].count_documents({}) == 0
        assert m.analyse[config.COLL_ANALYSE].count_documents({'soort': 'Standplaats'}) == 0
        assert verwerkingsrun.huidigeRun()['verwijderde_keys'] == {'Standplaats': [{'key': 'S1V2', 'projectcd': 'SY001'}]}

    def test_restanten_van_nieuw_bestand_worden_opgeruimd(self, gevulde_mongo):
        """Na een mislukte run kan een nieuw bestand al deels in de staging staan."""
        startRunMet(gevulde_mongo.client, nieuw={'projecten': [SY003_MDB]})
        opruimen.verwijderOudeRecords()
        assert gevulde_mongo.staging[config.COLL_STAGING_OUD].count_documents({'mdbfile': SY003_MDB}) == 0

    def test_mediabestand_dat_nog_gebruikt_wordt_blijft_staan(self, gevulde_mongo):
        m = gevulde_mongo
        # Een tweede Plaatjes-document verwijst naar dezelfde mediakopie
        m.staging[config.COLL_PLAATJES].insert_one(dict({'_id': 'pl_kopie', 'fullFileName': '/input/x/kopie.jpg'},
                                                        **mediaIds('/SY003/L Fotos', 'SY002_F001')))
        startRunMet(m.client, verwijderd={'afbeeldingen': [FOTO_SY003]})
        opruimen.verwijderOudeRecords()
        assert all(p.exists() for p in m.media['sy003'])

    def test_niets_op_te_ruimen(self, gevulde_mongo):
        m = gevulde_mongo
        startRunMet(m.client, ongewijzigd={'projecten': [SY001_MDB, SY003_MDB]})
        assert opruimen.verwijderOudeRecords() == {}
        assert m.staging[config.COLL_STAGING_OUD].count_documents({}) == 3
        assert verwerkingsrun.huidigeRun()['tellingen']['opruimen'] == {}

    def test_sleutels_bewaard_voordat_er_iets_verwijderd_wordt(self, gevulde_mongo, monkeypatch):
        startRunMet(gevulde_mongo.client, verwijderd={'projecten': [SY003_MDB]})

        def kapot(client, plan):
            raise RuntimeError("verbinding verbroken")
        monkeypatch.setattr(opruimen, 'verwijderVolgensPlan', kapot)
        with pytest.raises(RuntimeError):
            opruimen.verwijderOudeRecords()
        assert verwerkingsrun.huidigeRun()['geraakte_projecten'] == ['SY003']
        assert gevulde_mongo.staging[config.COLL_STAGING_OUD].count_documents({'mdbfile': SY003_MDB}) == 2

    def test_gewijzigd_abr_bestand_ruimt_hele_referentiecollectie_op(self, nep_client, media):
        nep_client[config.DB_STAGING][config.COLL_STAGING_REFERENTIETABELLEN].insert_many([{'_id': 'abr1'}, {'_id': 'abr2'}])
        nep_client[config.DB_ANALYSE][config.COLL_ANALYSE].insert_one({'_id': 'abr1', 'soort': 'ABR', 'key': 'Ahttps://x'})
        startRunMet(nep_client, gewijzigd={'referentietabellen': [config.FILE_ABREXCEL]})
        opruimen.verwijderOudeRecords()
        assert nep_client[config.DB_STAGING][config.COLL_STAGING_REFERENTIETABELLEN].count_documents({}) == 0
        assert verwerkingsrun.huidigeRun()['verwijderde_keys'] == {'ABR': [{'key': 'Ahttps://x', 'projectcd': None}]}


# ============================================================
# Klasse 3: delta-varianten van de extractie
# ============================================================

@pytest.fixture
def nep_mongoclient(nep_client, monkeypatch):
    """Laat pymongo.MongoClient in de extractiemodules de nep-client teruggeven."""
    monkeypatch.setattr(image_import.pymongo, 'MongoClient', lambda *args, **kwargs: nep_client)
    return nep_client


@pytest.mark.unit
class TestFilenamesDelta:
    """Test de incrementele variant van getAndStoreImageFilenames."""

    def test_iter_waarden_gespreid_over_de_collectie(self):
        inserts = image_import.maakFilenameInserts(['a', 'b', 'c', 'd'], aantal_bestaand=96)
        iters = [op._doc['iter'] for op in inserts]
        assert iters == [0, 25, 50, 75]
        assert all(op._doc['processed'] is False for op in inserts)

    def test_alleen_delta_toegevoegd_zonder_drop(self, nep_mongoclient):
        col = nep_mongoclient[config.DB_FILES][config.COLL_FILENAMES]
        col.insert_many([{'iter': 0, 'filename': FOTO_SY001, 'processed': True},
                         {'iter': 1, 'filename': FOTO_SY003, 'processed': True}])
        image_import.voegImageFilenamesToe([FOTO_SY003, FOTO_OUD])
        docs = {d['filename']: d for d in col.find({})}
        assert set(docs) == {FOTO_SY001, FOTO_SY003, FOTO_OUD}
        assert docs[FOTO_SY001]['processed'] is True
        assert docs[FOTO_SY003]['processed'] is False
        assert docs[FOTO_OUD]['processed'] is False
        assert col.count_documents({'filename': FOTO_SY003}) == 1

    def test_lege_delta_laat_collectie_ongemoeid(self, nep_mongoclient):
        col = nep_mongoclient[config.DB_FILES][config.COLL_FILENAMES]
        col.insert_one({'iter': 0, 'filename': FOTO_SY001, 'processed': True})
        image_import.voegImageFilenamesToe([])
        assert col.count_documents({}) == 1

    def test_incrementeel_gebruikt_run_document(self, nep_mongoclient):
        startRunMet(nep_mongoclient, nieuw={'afbeeldingen': [FOTO_SY003]}, ongewijzigd={'afbeeldingen': [FOTO_SY001]})
        image_import.getAndStoreImageFilenames(incrementeel=True)
        col = nep_mongoclient[config.DB_FILES][config.COLL_FILENAMES]
        assert [d['filename'] for d in col.find({})] == [FOTO_SY003]


@pytest.mark.unit
class TestReferentiesEnExtraProjectenDelta:
    """Test dat ABR en extra projecten alleen bij een wijziging worden ingelezen."""

    def test_abr_overgeslagen_als_ongewijzigd(self, nep_client, monkeypatch):
        aangeroepen = []
        monkeypatch.setattr(extract_referentietabellen, 'extractABR', lambda: aangeroepen.append(True))
        startRunMet(nep_client, ongewijzigd={'referentietabellen': [config.FILE_ABREXCEL]})
        extract_referentietabellen.extractAllRefs(incrementeel=True)
        assert aangeroepen == []

    def test_abr_ingelezen_als_gewijzigd_of_volledig(self, nep_client, monkeypatch):
        aangeroepen = []
        monkeypatch.setattr(extract_referentietabellen, 'extractABR', lambda: aangeroepen.append(True))
        startRunMet(nep_client, gewijzigd={'referentietabellen': [config.FILE_ABREXCEL]})
        extract_referentietabellen.extractAllRefs(incrementeel=True)
        extract_referentietabellen.extractAllRefs()
        assert aangeroepen == [True, True]

    def test_extra_projecten_krijgen_mdbfile(self, nep_mongoclient, tmp_path, monkeypatch):
        bestand = tmp_path / 'extra.xlsx'
        bestand.write_bytes(b'')
        monkeypatch.setattr(config, 'FILE_EXTRA_PROJECTS', str(bestand))
        monkeypatch.setattr(extract_extra_projects.pd, 'read_excel', lambda pad: pd.DataFrame([{'CODE': 'EX1'}, {'CODE': 'EX2'}]))
        extract_extra_projects.extractExtraProjects()
        col = nep_mongoclient[config.DB_STAGING][config.COLL_STAGING_PROJECTENLIJST]
        assert [d['mdbfile'] for d in col.find({})] == [str(bestand), str(bestand)]

    def test_extra_projecten_overgeslagen_als_ongewijzigd(self, nep_mongoclient, tmp_path, monkeypatch):
        bestand = tmp_path / 'extra.xlsx'
        bestand.write_bytes(b'')
        monkeypatch.setattr(config, 'FILE_EXTRA_PROJECTS', str(bestand))
        monkeypatch.setattr(extract_extra_projects.pd, 'read_excel', lambda pad: pd.DataFrame([{'CODE': 'EX1'}]))
        startRunMet(nep_mongoclient, ongewijzigd={'extra_projecten': [str(bestand)]})
        extract_extra_projects.extractExtraProjects(incrementeel=True)
        assert nep_mongoclient[config.DB_STAGING][config.COLL_STAGING_PROJECTENLIJST].count_documents({}) == 0
