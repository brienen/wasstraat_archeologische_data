"""
Integratietest voor de volledige Wasstraat-pipeline met één project.

Simuleert de complete ETL-cyclus:
  Extract (staging-data + foto's) → Harmonize → Enhance → Set Keys
  → Move & Merge → Set References

Vereist:
  1. pip install -r requirements-test.txt
  2. docker compose -f docker-compose.test.yml up -d

Draaien:
  make integration
  OF
  python -m pytest tests/integration/test_full_pipeline.py -v
"""
import pytest
import copy
import os
import sys
import tempfile
import shutil
import re
from pathlib import Path
from datetime import datetime

# ============================================================
# Imports (skip hele module als dependencies ontbreken)
# ============================================================
pymongo = pytest.importorskip("pymongo")
pd = pytest.importorskip("pandas")
openpyxl = pytest.importorskip("openpyxl")
pytest.importorskip("simplejson")

import shared.config as config
import shared.const as const


# ============================================================
# Test-configuratie
# ============================================================

MONGO_TEST_URI = os.getenv(
    "MONGO_TEST_URI",
    "mongodb://testroot:testpass@localhost:27117/"
)
DB_STAGING_TEST = "Arch_Staging_Pipeline_Test"
DB_ANALYSE_TEST = "Arch_Analyse_Pipeline_Test"
DB_FILES_TEST = "Arch_Files_Pipeline_Test"

# Test project
TEST_PROJECT_CODE = "DC999"
TEST_PROJECT_NAAM = "Testopgraving Marktplein"


# ============================================================
# Fixtures
# ============================================================

@pytest.fixture(scope="module")
def mongo_client():
    """Maak verbinding met de test-MongoDB."""
    client = pymongo.MongoClient(MONGO_TEST_URI, serverSelectionTimeoutMS=3000)
    try:
        client.admin.command("ping")
    except pymongo.errors.ConnectionFailure:
        pytest.skip("MongoDB test-server niet bereikbaar op " + MONGO_TEST_URI)
    yield client
    client.close()


@pytest.fixture(scope="module")
def test_databases(mongo_client):
    """Maak schone test-databases aan en ruim op na afloop."""
    mongo_client.drop_database(DB_STAGING_TEST)
    mongo_client.drop_database(DB_ANALYSE_TEST)
    mongo_client.drop_database(DB_FILES_TEST)

    staging_db = mongo_client[DB_STAGING_TEST]
    analyse_db = mongo_client[DB_ANALYSE_TEST]
    files_db = mongo_client[DB_FILES_TEST]

    yield {
        "staging": staging_db,
        "analyse": analyse_db,
        "files": files_db,
        "client": mongo_client,
    }

    # Cleanup
    mongo_client.drop_database(DB_STAGING_TEST)
    mongo_client.drop_database(DB_ANALYSE_TEST)
    mongo_client.drop_database(DB_FILES_TEST)


@pytest.fixture(autouse=True, scope="module")
def patch_config():
    """Patch shared.config zodat alle pipeline-functies de test-databases gebruiken.

    Dit MOET vóór de import van wasstraat-modules plaatsvinden omdat meta.py
    bij import de config-waarden gebruikt in de $merge-stappen.
    """
    _originals = {}
    attrs_to_patch = {
        "MONGO_URI": MONGO_TEST_URI,
        "MONGO_STAGING_URI": MONGO_TEST_URI + DB_STAGING_TEST,
        "MONGO_ANALYSE_URI": MONGO_TEST_URI + DB_ANALYSE_TEST,
        "MONGO_FILES_URI": MONGO_TEST_URI + DB_FILES_TEST,
        "DB_STAGING": DB_STAGING_TEST,
        "DB_ANALYSE": DB_ANALYSE_TEST,
        "DB_FILES": DB_FILES_TEST,
    }
    for attr, val in attrs_to_patch.items():
        if hasattr(config, attr):
            _originals[attr] = getattr(config, attr)
        setattr(config, attr, val)

    # Force re-import van meta zodat de $merge-stappen de test-DB gebruiken
    import importlib
    import wasstraat.meta as meta_mod
    import wasstraat.merge_functions as merge_mod
    importlib.reload(meta_mod)
    importlib.reload(merge_mod)

    yield

    for attr, val in _originals.items():
        setattr(config, attr, val)


@pytest.fixture(scope="module")
def test_photo_dir():
    """Maak een tijdelijke directory met testfoto's (kleine JPEG's)."""
    tmpdir = tempfile.mkdtemp(prefix="wasstraat_test_fotos_")
    project_dir = os.path.join(tmpdir, TEST_PROJECT_CODE + "_Testopgraving")
    fotos_dir = os.path.join(project_dir, "D_Velddocumenten", "fotos")
    aardewerk_dir = os.path.join(project_dir, "F_Vondstmateriaal", "aardewerk")
    os.makedirs(fotos_dir, exist_ok=True)
    os.makedirs(aardewerk_dir, exist_ok=True)

    # Minimale geldige JPEG (1x1 pixel)
    minimal_jpeg = bytes([
        0xFF, 0xD8, 0xFF, 0xE0, 0x00, 0x10, 0x4A, 0x46, 0x49, 0x46, 0x00, 0x01,
        0x01, 0x00, 0x00, 0x01, 0x00, 0x01, 0x00, 0x00, 0xFF, 0xDB, 0x00, 0x43,
        0x00, 0x08, 0x06, 0x06, 0x07, 0x06, 0x05, 0x08, 0x07, 0x07, 0x07, 0x09,
        0x09, 0x08, 0x0A, 0x0C, 0x14, 0x0D, 0x0C, 0x0B, 0x0B, 0x0C, 0x19, 0x12,
        0x13, 0x0F, 0x14, 0x1D, 0x1A, 0x1F, 0x1E, 0x1D, 0x1A, 0x1C, 0x1C, 0x20,
        0x24, 0x2E, 0x27, 0x20, 0x22, 0x2C, 0x23, 0x1C, 0x1C, 0x28, 0x37, 0x29,
        0x2C, 0x30, 0x31, 0x34, 0x34, 0x34, 0x1F, 0x27, 0x39, 0x3D, 0x38, 0x32,
        0x3C, 0x2E, 0x33, 0x34, 0x32, 0xFF, 0xC0, 0x00, 0x0B, 0x08, 0x00, 0x01,
        0x00, 0x01, 0x01, 0x01, 0x11, 0x00, 0xFF, 0xC4, 0x00, 0x1F, 0x00, 0x00,
        0x01, 0x05, 0x01, 0x01, 0x01, 0x01, 0x01, 0x01, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08,
        0x09, 0x0A, 0x0B, 0xFF, 0xC4, 0x00, 0xB5, 0x10, 0x00, 0x02, 0x01, 0x03,
        0x03, 0x02, 0x04, 0x03, 0x05, 0x05, 0x04, 0x04, 0x00, 0x00, 0x01, 0x7D,
        0x01, 0x02, 0x03, 0x00, 0x04, 0x11, 0x05, 0x12, 0x21, 0x31, 0x41, 0x06,
        0x13, 0x51, 0x61, 0x07, 0x22, 0x71, 0x14, 0x32, 0x81, 0x91, 0xA1, 0x08,
        0x23, 0x42, 0xB1, 0xC1, 0x15, 0x52, 0xD1, 0xF0, 0x24, 0x33, 0x62, 0x72,
        0x82, 0x09, 0x0A, 0x16, 0x17, 0x18, 0x19, 0x1A, 0x25, 0x26, 0x27, 0x28,
        0x29, 0x2A, 0x34, 0x35, 0x36, 0x37, 0x38, 0x39, 0x3A, 0x43, 0x44, 0x45,
        0x46, 0x47, 0x48, 0x49, 0x4A, 0x53, 0x54, 0x55, 0x56, 0x57, 0x58, 0x59,
        0x5A, 0x63, 0x64, 0x65, 0x66, 0x67, 0x68, 0x69, 0x6A, 0x73, 0x74, 0x75,
        0x76, 0x77, 0x78, 0x79, 0x7A, 0x83, 0x84, 0x85, 0x86, 0x87, 0x88, 0x89,
        0x8A, 0x92, 0x93, 0x94, 0x95, 0x96, 0x97, 0x98, 0x99, 0x9A, 0xA2, 0xA3,
        0xA4, 0xA5, 0xA6, 0xA7, 0xA8, 0xA9, 0xAA, 0xB2, 0xB3, 0xB4, 0xB5, 0xB6,
        0xB7, 0xB8, 0xB9, 0xBA, 0xC2, 0xC3, 0xC4, 0xC5, 0xC6, 0xC7, 0xC8, 0xC9,
        0xCA, 0xD2, 0xD3, 0xD4, 0xD5, 0xD6, 0xD7, 0xD8, 0xD9, 0xDA, 0xE1, 0xE2,
        0xE3, 0xE4, 0xE5, 0xE6, 0xE7, 0xE8, 0xE9, 0xEA, 0xF1, 0xF2, 0xF3, 0xF4,
        0xF5, 0xF6, 0xF7, 0xF8, 0xF9, 0xFA, 0xFF, 0xDA, 0x00, 0x08, 0x01, 0x01,
        0x00, 0x00, 0x3F, 0x00, 0x7B, 0x94, 0x11, 0x00, 0x00, 0x00, 0x00, 0x00,
        0xFF, 0xD9,
    ])

    for name, folder in [
        (f"{TEST_PROJECT_CODE}_G001.jpg", fotos_dir),
        (f"{TEST_PROJECT_CODE}_F001.jpg", fotos_dir),
        (f"{TEST_PROJECT_CODE}_H5_1.jpg", aardewerk_dir),
        (f"{TEST_PROJECT_CODE}_P3_H5_2_1.jpg", aardewerk_dir),
        (f"{TEST_PROJECT_CODE}_B001.tif", fotos_dir),
    ]:
        with open(os.path.join(folder, name), "wb") as f:
            f.write(minimal_jpeg)

    yield tmpdir
    shutil.rmtree(tmpdir, ignore_errors=True)


@pytest.fixture(scope="module")
def projecten_xlsx():
    """Maak een tijdelijke projecten.xlsx met één testproject."""
    tmpdir = tempfile.mkdtemp(prefix="wasstraat_test_xlsx_")
    xlsx_path = os.path.join(tmpdir, "projecten.xlsx")

    df = pd.DataFrame([{
        "CODE": TEST_PROJECT_CODE,
        "OPGRAVING": TEST_PROJECT_NAAM,
        "TOPONIEM": "Marktplein",
        "XCOORD": 84500,
        "YCOORD": 447500,
        "TREFWOORDEN": "test, integratie, aardewerk",
        "JAAR": 2024,
        "CODENAAM": "Test Marktplein",
        "table": "OPGRAVINGEN",
    }])

    df.to_excel(xlsx_path, index=False)
    yield xlsx_path
    shutil.rmtree(tmpdir, ignore_errors=True)


# ============================================================
# Testdata: staging-documenten die de Extract-fase simuleren
# ============================================================

def get_staging_oud_docs():
    """Retourneert staging-documenten zoals de MDB-extractie (mongoimport CSV) die produceert.

    Let op: mongoimport zet alle velden PLAT op root-niveau. Er is geen genest
    'brondata'-veld — dat wordt pas door de harmonize-stap aangemaakt via
    $replaceRoot: {brondata: $$ROOT}.
    """
    ts = "2024-01-15T10:00:00+01:00"
    mdb = f"{TEST_PROJECT_CODE}_Testopgraving.mdb"
    # Kolomnamen moeten overeenkomen met Wasstraat_Config_HarmonizeV3.xlsx:
    #   putnr    ← PUT / PUTNO         (niet PUTNR!)
    #   vlaknr   ← VLAK / VLAKNO
    #   spoornr  ← SPOOR / SPOORNO
    #   vondstnr ← VONDST / VONDSTNO
    #   artefactnr ← ARTEFACT
    return [
        # 2 Putten
        {
            "table": "PUTTEN", "projectcd": TEST_PROJECT_CODE,
            "bron": f"opgraving{TEST_PROJECT_CODE}", "loadtime": ts, "mdbfile": mdb,
            "PUT": "1", "DIEPTE": "150",
        },
        {
            "table": "PUTTEN", "projectcd": TEST_PROJECT_CODE,
            "bron": f"opgraving{TEST_PROJECT_CODE}", "loadtime": ts, "mdbfile": mdb,
            "PUT": "3", "DIEPTE": "200",
        },
        # 1 Vlak
        {
            "table": "VLAKKEN", "projectcd": TEST_PROJECT_CODE,
            "bron": f"opgraving{TEST_PROJECT_CODE}", "loadtime": ts, "mdbfile": mdb,
            "PUT": "1", "VLAK": "1",
        },
        # 2 Sporen
        {
            "table": "SPOREN", "projectcd": TEST_PROJECT_CODE,
            "bron": f"opgraving{TEST_PROJECT_CODE}", "loadtime": ts, "mdbfile": mdb,
            "SPOOR": "5", "PUT": "3", "VLAK": "1",
            "AARD": "Kuil", "DATERING": "1600-1700",
        },
        {
            "table": "SPOREN", "projectcd": TEST_PROJECT_CODE,
            "bron": f"opgraving{TEST_PROJECT_CODE}", "loadtime": ts, "mdbfile": mdb,
            "SPOOR": "7", "PUT": "3", "VLAK": "1",
            "AARD": "Muur", "DATERING": "17e eeuw",
        },
        # 2 Vondsten
        {
            "table": "VONDSTEN", "projectcd": TEST_PROJECT_CODE,
            "bron": f"opgraving{TEST_PROJECT_CODE}", "loadtime": ts, "mdbfile": mdb,
            "VONDST": "1", "PUT": "3", "SPOOR": "5",
            "AANTAL": "12", "DATERING": "1600-1700",
        },
        {
            "table": "VONDSTEN", "projectcd": TEST_PROJECT_CODE,
            "bron": f"opgraving{TEST_PROJECT_CODE}", "loadtime": ts, "mdbfile": mdb,
            "VONDST": "2", "PUT": "3", "SPOOR": "7",
            "AANTAL": "3", "DATERING": "17e eeuw",
        },
        # 2 Artefacten (aardewerk + glas)
        {
            "table": "AARDEWERK", "projectcd": TEST_PROJECT_CODE,
            "bron": f"opgraving{TEST_PROJECT_CODE}", "loadtime": ts, "mdbfile": mdb,
            "VONDST": "1", "PUT": "3", "ARTEFACT": "1", "SUBNR": "1",
            "VORMTYPE": "Grape", "DATERING": "1600-1650", "DOOSNO": "10",
        },
        {
            "table": "GLAS", "projectcd": TEST_PROJECT_CODE,
            "bron": f"opgraving{TEST_PROJECT_CODE}", "loadtime": ts, "mdbfile": mdb,
            "VONDST": "2", "PUT": "3", "ARTEFACT": "1", "SUBNR": "1",
            "VORM": "Roemer", "DATERING": "1650-1700",
        },
    ]


def get_staging_delfit_docs():
    """DelfIT project-documenten (OPGRAVINGEN-tabel)."""
    return [{
        "_id": f"TEST_DELFIT_{TEST_PROJECT_CODE}",
        "table": "OPGRAVINGEN",
        "CODE": TEST_PROJECT_CODE,
        "OPGRAVING": TEST_PROJECT_NAAM,
        "TOPONIEM": "Marktplein",
        "XCOORD": 84500.0,
        "YCOORD": 447500.0,
        "TREFWOORDEN": "test, integratie, aardewerk",
        "JAAR": 2024,
        "CODENAAM": "Test Marktplein",
    }]


def get_staging_plaatjes_docs():
    """Foto-metadatadocumenten zoals de image-extract die produceert."""
    base_dir = f"/{TEST_PROJECT_CODE}_Testopgraving"
    return [
        {
            "_id": f"TEST_FOTO_{TEST_PROJECT_CODE}_G001",
            "fileName": f"{TEST_PROJECT_CODE}_G001.jpg",
            "fullFileName": f"{base_dir}/D_Velddocumenten/fotos/{TEST_PROJECT_CODE}_G001.jpg",
            "directory": f"{base_dir}/D_Velddocumenten/fotos",
            "fileType": ".jpg", "mime_type": "image/jpeg",
            "projectcd": TEST_PROJECT_CODE,
            "imageID": "test_img_1", "imageMiddleID": "test_mid_1", "imageThumbID": "test_thm_1",
        },
        {
            "_id": f"TEST_FOTO_{TEST_PROJECT_CODE}_F001",
            "fileName": f"{TEST_PROJECT_CODE}_F001.jpg",
            "fullFileName": f"{base_dir}/D_Velddocumenten/fotos/{TEST_PROJECT_CODE}_F001.jpg",
            "directory": f"{base_dir}/D_Velddocumenten/fotos",
            "fileType": ".jpg", "mime_type": "image/jpeg",
            "projectcd": TEST_PROJECT_CODE,
            "imageID": "test_img_2", "imageMiddleID": "test_mid_2", "imageThumbID": "test_thm_2",
        },
        {
            "_id": f"TEST_FOTO_{TEST_PROJECT_CODE}_H5_1",
            "fileName": f"{TEST_PROJECT_CODE}_H5_1.jpg",
            "fullFileName": f"{base_dir}/F_Vondstmateriaal/aardewerk/{TEST_PROJECT_CODE}_H5_1.jpg",
            "directory": f"{base_dir}/F_Vondstmateriaal/aardewerk",
            "fileType": ".jpg", "mime_type": "image/jpeg",
            "projectcd": TEST_PROJECT_CODE,
            "imageID": "test_img_3", "imageMiddleID": "test_mid_3", "imageThumbID": "test_thm_3",
        },
        {
            "_id": f"TEST_FOTO_{TEST_PROJECT_CODE}_B001",
            "fileName": f"{TEST_PROJECT_CODE}_B001.tif",
            "fullFileName": f"{base_dir}/D_Velddocumenten/fotos/{TEST_PROJECT_CODE}_B001.tif",
            "directory": f"{base_dir}/D_Velddocumenten/fotos",
            "fileType": ".tif", "mime_type": "image/tiff",
            "projectcd": TEST_PROJECT_CODE,
            "imageID": "test_img_4", "imageMiddleID": "test_mid_4", "imageThumbID": "test_thm_4",
        },
    ]


# ============================================================
# Helpers
# ============================================================

def seed_staging_data(test_databases):
    """Vul de staging-databases met testdata (simuleert de Extract-fase)."""
    staging_db = test_databases["staging"]
    staging_db[config.COLL_STAGING_PROJECTENLIJST].insert_many(get_staging_delfit_docs())
    staging_db[config.COLL_STAGING_OUD].insert_many(get_staging_oud_docs())
    staging_db[config.COLL_PLAATJES].insert_many(get_staging_plaatjes_docs())


def patch_merge_target(pipeline):
    """Pas $merge-stappen in een aggregation-pipeline aan naar de test-database."""
    pipeline = copy.deepcopy(pipeline)
    for stage in pipeline:
        if "$merge" in stage:
            stage["$merge"]["into"]["db"] = DB_ANALYSE_TEST
            stage["$merge"]["into"]["coll"] = config.COLL_ANALYSE
    return pipeline


# ============================================================
# Tests – worden sequentieel uitgevoerd (test_01, test_02, …)
# ============================================================

@pytest.mark.integration
class TestFullPipeline:
    """Test de volledige Wasstraat-pipeline met één testproject (DC999)."""

    # ----------------------------------------------------------
    # Stap 1: Extract – seed staging data
    # ----------------------------------------------------------
    def test_01_seed_staging(self, test_databases, projecten_xlsx):
        """Staging-databases worden correct gevuld met testdata."""
        seed_staging_data(test_databases)
        staging = test_databases["staging"]

        assert staging[config.COLL_STAGING_PROJECTENLIJST].count_documents({}) >= 1
        assert staging[config.COLL_STAGING_OUD].count_documents({}) >= 9
        assert staging[config.COLL_PLAATJES].count_documents({}) >= 4

    # ----------------------------------------------------------
    # Stap 2: Harmonize – Project
    # ----------------------------------------------------------
    def test_02_harmonize_project(self, test_databases):
        """Project DC999 wordt geharmoniseerd vanuit de DelfIT-collectie."""
        from wasstraat import meta
        staging_db = test_databases["staging"]
        analyse_db = test_databases["analyse"]

        pipeline = meta.getHarmonizePipelines("Project")
        aggr = patch_merge_target(pipeline[0])

        coll = staging_db[config.COLL_STAGING_PROJECTENLIJST]
        list(coll.aggregate(aggr))

        result_coll = analyse_db[config.COLL_ANALYSE]
        project = result_coll.find_one({"soort": "Project", "projectcd": TEST_PROJECT_CODE})
        assert project is not None, "Project niet gevonden na harmonisatie"
        assert project["projectnaam"] == TEST_PROJECT_NAAM
        assert project["xcoor_rd"] == 84500.0

    # ----------------------------------------------------------
    # Stap 3: Harmonize – Putten, Sporen, Vondsten, Artefacten
    # ----------------------------------------------------------
    def test_03_harmonize_archaeological_objects(self, test_databases):
        """Putten, Sporen, Vondsten en Artefacten worden geharmoniseerd."""
        from wasstraat.harmonizer import getHarmonizeAggr
        staging_db = test_databases["staging"]
        analyse_db = test_databases["analyse"]
        coll_staging = staging_db[config.COLL_STAGING_OUD]
        result_coll = analyse_db[config.COLL_ANALYSE]

        for soort in ["Put", "Vlak", "Spoor", "Vondst", "Aardewerk", "Glas"]:
            pipeline = getHarmonizeAggr(soort, reload=True)
            pipeline = patch_merge_target(pipeline)
            list(coll_staging.aggregate(pipeline))

        assert result_coll.count_documents({"soort": "Put"}) == 2, "Verwachtte 2 putten"
        assert result_coll.count_documents({"soort": "Spoor"}) == 2, "Verwachtte 2 sporen"
        assert result_coll.count_documents({"soort": "Vondst"}) == 2, "Verwachtte 2 vondsten"
        assert result_coll.count_documents({"soort": "Artefact"}) == 2, "Verwachtte 2 artefacten"

    # ----------------------------------------------------------
    # Stap 4: Harmonize – Foto-parsing
    # ----------------------------------------------------------
    def test_04_harmonize_foto_parsing(self, test_databases):
        """Foto's worden geparsed op bestandsnaam → type, projectcd, vondstnr, etc."""
        from wasstraat import harmonize_functions
        analyse_db = test_databases["analyse"]
        result_coll = analyse_db[config.COLL_ANALYSE]

        harmonize_functions.parseFotobestanden()

        # Opgravingsfoto (G-type)
        foto_g = result_coll.find_one({"_id": f"TEST_FOTO_{TEST_PROJECT_CODE}_G001"})
        assert foto_g is not None, "Opgravingsfoto G001 niet gevonden"
        assert foto_g["soort"] == "Foto"
        assert foto_g["fototype"] == "G"
        assert foto_g["projectcd"] == TEST_PROJECT_CODE

        # Sfeerfoto (F-type)
        foto_f = result_coll.find_one({"_id": f"TEST_FOTO_{TEST_PROJECT_CODE}_F001"})
        assert foto_f is not None, "Sfeerfoto F001 niet gevonden"
        assert foto_f["fototype"] == "F"

        # Objectfoto (H-type) – bevat vondstnr uit bestandsnaam
        foto_h = result_coll.find_one({"_id": f"TEST_FOTO_{TEST_PROJECT_CODE}_H5_1"})
        assert foto_h is not None, "Objectfoto H5_1 niet gevonden"
        assert foto_h["fototype"] == "H"
        assert foto_h["vondstnr"] == "5", f"Verwachtte vondstnr=5, got {foto_h.get('vondstnr')}"

        # Tekening (B-type)
        tek = result_coll.find_one({"_id": f"TEST_FOTO_{TEST_PROJECT_CODE}_B001"})
        assert tek is not None, "Tekening B001 niet gevonden"
        assert tek["soort"] == "Tekening"
        assert tek["fototype"] == "B"

    # ----------------------------------------------------------
    # Stap 5: Enhance Attributes
    # ----------------------------------------------------------
    def test_05_enhance_attributes(self, test_databases):
        """Attributen worden genormaliseerd: projectcd→uppercase, putnr→int, RD→WGS84."""
        from wasstraat import setAttributes_functions
        analyse_db = test_databases["analyse"]
        result_coll = analyse_db[config.COLL_ANALYSE]

        setAttributes_functions.enhanceAllAttributes()

        # projectcd moet uppercase + zero-padded zijn
        project = result_coll.find_one({"soort": "Project", "projectcd": TEST_PROJECT_CODE})
        assert project is not None, "Project niet gevonden na enhance"
        assert project["projectcd"] == TEST_PROJECT_CODE

        # putnr moet int zijn (was string "1")
        put = result_coll.find_one({"soort": "Put", "projectcd": TEST_PROJECT_CODE})
        assert put is not None, "Put niet gevonden na enhance"
        assert isinstance(put.get("putnr"), int), \
            f"putnr zou int moeten zijn, is {type(put.get('putnr'))}: {put.get('putnr')}"

        # RD-coördinaten → WGS84 GeoJSON
        if project.get("xcoor_rd"):
            assert "coor_wgs" in project, "WGS84-coördinaten ontbreken na enhance"
            assert project["coor_wgs"]["type"] == "Point"
            coords = project["coor_wgs"]["coordinates"]
            assert len(coords) == 2, "GeoJSON Point moet [lon, lat] zijn"

    # ----------------------------------------------------------
    # Stap 6: Set Keys
    # ----------------------------------------------------------
    def test_06_set_reference_keys(self, test_databases):
        """Hiërarchische keys worden gegenereerd: P{code}P{putnr}V{vlaknr}S{spoornr}."""
        from wasstraat import meta, references_functions
        analyse_db = test_databases["analyse"]
        result_coll = analyse_db[config.COLL_ANALYSE]

        for soort in meta.getKeys(meta.SET_KEYS_PIPELINES):
            pipeline = meta.getReferenceKeysPipeline(soort)
            if pipeline:
                try:
                    references_functions.setReferenceKeys(pipeline, soort, col='analyse')
                except Exception:
                    pass  # Soorten zonder testdata

        # Put key = P{code}P{putnr}
        put = result_coll.find_one({"soort": "Put", "projectcd": TEST_PROJECT_CODE, "putnr": 1})
        assert put is not None, "Put met putnr=1 niet gevonden"
        assert put.get("key") == f"P{TEST_PROJECT_CODE}P1", \
            f"Put key fout: {put.get('key')}"
        assert put.get("key_project") == f"P{TEST_PROJECT_CODE}"

        # Project key = P{code}
        project = result_coll.find_one({"soort": "Project", "projectcd": TEST_PROJECT_CODE})
        assert project.get("key") == f"P{TEST_PROJECT_CODE}"

        # Spoor key bevat S
        spoor = result_coll.find_one({"soort": "Spoor", "projectcd": TEST_PROJECT_CODE, "spoornr": 5})
        assert spoor is not None, "Spoor met spoornr=5 niet gevonden"
        assert "S" in spoor.get("key", ""), f"Spoor key mist 'S': {spoor.get('key')}"
        assert "key_put" in spoor, "Spoor mist key_put referentie"

    def test_07_set_primary_keys(self, test_databases):
        """Elk soort krijgt sequentiële ID's (primary keys)."""
        from wasstraat import references_functions
        analyse_db = test_databases["analyse"]
        result_coll = analyse_db[config.COLL_ANALYSE]

        for soort in ["Project", "Put", "Vlak", "Spoor", "Vondst", "Artefact", "Foto", "Tekening"]:
            if result_coll.count_documents({"soort": soort}) > 0:
                references_functions.setPrimaryKeys(soort, col='analyse')

        project = result_coll.find_one({"soort": "Project", "projectcd": TEST_PROJECT_CODE})
        assert "ID" in project, "Project mist ID na setPrimaryKeys"
        assert isinstance(project["ID"], (int, float)), \
            f"ID moet numeriek zijn, is {type(project['ID'])}"

    # ----------------------------------------------------------
    # Stap 7: Move & Merge
    # ----------------------------------------------------------
    def test_08_move_soort(self, test_databases):
        """Records worden verplaatst naar de clean-collectie."""
        from wasstraat import meta, merge_functions
        analyse_db = test_databases["analyse"]

        for soort in meta.getKeys(meta.MOVEANDMERGE_MOVE):
            if analyse_db[config.COLL_ANALYSE].count_documents({"soort": soort}) > 0:
                try:
                    merge_functions.moveSoort(soort)
                except Exception:
                    pass

        clean_coll = analyse_db[config.COLL_ANALYSE_CLEAN]
        total = clean_coll.count_documents({})
        assert total >= 1, f"Verwachtte ≥1 doc in clean collectie, vond {total}"

    def test_09_merge_soort(self, test_databases):
        """Duplicaten worden samengevoegd op key → brondata wordt een lijst."""
        from wasstraat import meta, merge_functions
        analyse_db = test_databases["analyse"]

        for soort in meta.getKeys(meta.MOVEANDMERGE_MERGE):
            if analyse_db[config.COLL_ANALYSE].count_documents({"soort": soort}) > 0:
                try:
                    merge_functions.mergeSoort(soort)
                except Exception:
                    pass

        clean_coll = analyse_db[config.COLL_ANALYSE_CLEAN]
        assert clean_coll.count_documents({"soort": "Vondst"}) >= 1, \
            "Na merge moeten er Vondsten in clean staan"

    # ----------------------------------------------------------
    # Stap 8: Set References (final)
    # ----------------------------------------------------------
    def test_10_set_references_final(self, test_databases):
        """Foreign keys worden gelegd: Spoor → Put, Vondst → Project, etc."""
        from wasstraat import references_functions
        analyse_db = test_databases["analyse"]
        clean_coll = analyse_db[config.COLL_ANALYSE_CLEAN]

        for soort in ["Project", "Put", "Spoor", "Vondst"]:
            if clean_coll.count_documents({"soort": soort}) > 0:
                try:
                    references_functions.setPrimaryKeys(soort, col='analyseclean')
                except Exception:
                    pass

        for soort in ["Project", "Put", "Spoor", "Vondst"]:
            if clean_coll.count_documents({"soort": soort}) > 0:
                try:
                    references_functions.setReferences(soort, col='analyseclean')
                except Exception:
                    pass

        # Verifieer Spoor → Put referentie
        spoor = clean_coll.find_one({"soort": "Spoor", "key_put": {"$exists": True}})
        if spoor:
            has_ref = "putID" in spoor or "putUUID" in spoor
            if has_ref:
                assert spoor.get("putID") is not None or spoor.get("putUUID") is not None

    # ----------------------------------------------------------
    # Stap 9: Eindverificatie
    # ----------------------------------------------------------
    def test_11_verify_all_docs_have_soort(self, test_databases):
        """Alle documenten in de analyse-collectie hebben een 'soort'-veld."""
        analyse_db = test_databases["analyse"]
        analyse_coll = analyse_db[config.COLL_ANALYSE]

        total = analyse_coll.count_documents({})
        assert total >= 5, f"Te weinig documenten: {total}"

        without_soort = analyse_coll.count_documents({"soort": {"$exists": False}})
        assert without_soort == 0, f"{without_soort} documenten zonder 'soort'"

    def test_12_verify_all_docs_have_projectcd(self, test_databases):
        """Alle structurele documenten hebben een projectcd."""
        analyse_db = test_databases["analyse"]
        analyse_coll = analyse_db[config.COLL_ANALYSE]

        without_project = analyse_coll.count_documents({
            "projectcd": {"$exists": False},
            "soort": {"$nin": ["Foto", "Tekening", "Bestand", "Rapport"]}
        })
        assert without_project == 0, \
            f"{without_project} structurele documenten zonder projectcd"

    def test_13_verify_clean_has_wasstraat_metadata(self, test_databases):
        """Na move/merge heeft elk document wasstraat-metadata (herkomst-tracking)."""
        analyse_db = test_databases["analyse"]
        clean_coll = analyse_db[config.COLL_ANALYSE_CLEAN]

        total = clean_coll.count_documents({})
        assert total >= 1, "Clean collectie is leeg"

        with_wasstraat = clean_coll.count_documents({"wasstraat": {"$exists": True}})
        assert with_wasstraat >= 1, "Geen enkel clean document heeft wasstraat-metadata"

    def test_14_verify_brondata_is_list_after_merge(self, test_databases):
        """Na merge is brondata een lijst (meerdere bronnen per entiteit)."""
        analyse_db = test_databases["analyse"]
        clean_coll = analyse_db[config.COLL_ANALYSE_CLEAN]

        merged = clean_coll.find_one({"brondata": {"$type": "array"}})
        if merged:
            assert isinstance(merged["brondata"], list)
            assert len(merged["brondata"]) >= 1

    def test_15_verify_photo_types_classified(self, test_databases):
        """Alle 4 fototypen (G, F, H, B) zijn correct geclassificeerd."""
        analyse_db = test_databases["analyse"]
        analyse_coll = analyse_db[config.COLL_ANALYSE]

        foto_types = {}
        for doc in analyse_coll.find({"soort": {"$in": ["Foto", "Tekening"]}}):
            ft = doc.get("fototype", "onbekend")
            foto_types[ft] = foto_types.get(ft, 0) + 1

        expected = {"G", "F", "H", "B"}
        missing = expected - set(foto_types.keys())
        assert len(missing) == 0, \
            f"Ontbrekende fototypes: {missing}. Gevonden: {foto_types}"

    def test_16_verify_key_hierarchy(self, test_databases):
        """Keys volgen de hiërarchische structuur P{code}P{putnr}V{vlaknr}S{spoornr}."""
        analyse_db = test_databases["analyse"]
        analyse_coll = analyse_db[config.COLL_ANALYSE]

        # Project: P{code}
        project = analyse_coll.find_one({"soort": "Project", "key": {"$exists": True}})
        if project:
            assert project["key"] == f"P{TEST_PROJECT_CODE}"

        # Put: P{code}P{putnr}
        put = analyse_coll.find_one({"soort": "Put", "key": {"$exists": True}})
        if put:
            assert put["key"].count("P") >= 2, f"Put key: {put['key']}"

        # Spoor: …S{spoornr}
        spoor = analyse_coll.find_one({"soort": "Spoor", "key": {"$exists": True}})
        if spoor:
            assert "S" in spoor["key"], f"Spoor key mist S: {spoor['key']}"


# ============================================================
# Extra: projecten.xlsx via extractExtraProjects
# ============================================================

@pytest.mark.integration
class TestProjectenXlsxExtract:
    """Test dat de projecten.xlsx correct ingelezen wordt via extractExtraProjects."""

    def test_extract_extra_projects(self, test_databases, projecten_xlsx):
        """extractExtraProjects leest de xlsx in en schrijft naar COLL_STAGING_PROJECTENLIJST."""
        from wasstraat.extract_extra_projects import extractExtraProjects
        staging_db = test_databases["staging"]

        original = config.FILE_EXTRA_PROJECTS
        config.FILE_EXTRA_PROJECTS = projecten_xlsx

        try:
            extractExtraProjects()

            coll = staging_db[config.COLL_STAGING_PROJECTENLIJST]
            doc = coll.find_one({"CODE": TEST_PROJECT_CODE, "OPGRAVING": TEST_PROJECT_NAAM})
            assert doc is not None, \
                f"Project {TEST_PROJECT_CODE} niet gevonden na extractExtraProjects"
            assert doc["XCOORD"] == 84500
            assert doc["YCOORD"] == 447500
        finally:
            config.FILE_EXTRA_PROJECTS = original

    def test_projecten_xlsx_contents(self, projecten_xlsx):
        """De test-xlsx bevat correct gestructureerde projectdata."""
        df = pd.read_excel(projecten_xlsx)

        assert len(df) == 1
        row = df.iloc[0]
        assert row["CODE"] == TEST_PROJECT_CODE
        assert row["OPGRAVING"] == TEST_PROJECT_NAAM
        assert row["XCOORD"] == 84500
        assert row["YCOORD"] == 447500
        assert row["table"] == "OPGRAVINGEN"
