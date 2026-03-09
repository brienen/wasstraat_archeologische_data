"""
Integratietests voor de harmonize-pipeline.

Vereist een draaiende MongoDB (via docker-compose.test.yml).
Draai eerst:
    docker compose -f docker-compose.test.yml up -d

Vervolgens:
    python -m pytest tests/integration/ -v -m integration
"""
import pytest
import os

# Probeer pymongo te importeren; skip als het niet beschikbaar is
pymongo = pytest.importorskip("pymongo")

import shared.config as config
from wasstraat.harmonizer import getHarmonizeAggr, loadHarmonizer

# ============================================================
# Test-configuratie
# ============================================================

MONGO_TEST_URI = os.getenv(
    "MONGO_TEST_URI",
    "mongodb://testroot:testpass@localhost:27117/"
)
DB_STAGING = os.getenv("DB_STAGING", "Arch_Staging_Test")
DB_ANALYSE = os.getenv("DB_ANALYSE", "Arch_Analyse_Test")


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
def staging_db(mongo_client):
    """Geeft een schone staging database terug."""
    db = mongo_client[DB_STAGING]
    yield db
    mongo_client.drop_database(DB_STAGING)


@pytest.fixture(scope="module")
def analyse_db(mongo_client):
    """Geeft een schone analyse database terug."""
    db = mongo_client[DB_ANALYSE]
    yield db
    mongo_client.drop_database(DB_ANALYSE)


@pytest.fixture(autouse=True)
def patch_config(monkeypatch):
    """Patch shared.config zodat de harmonize-functies de test-DB gebruiken."""
    monkeypatch.setattr(config, "MONGO_URI", MONGO_TEST_URI)
    monkeypatch.setattr(config, "DB_STAGING", DB_STAGING)
    monkeypatch.setattr(config, "DB_ANALYSE", DB_ANALYSE)
    monkeypatch.setattr(config, "COLL_ANALYSE", "Single_Store_Test")


# ============================================================
# Testdata: minimale documenten voor de staging-database
# ============================================================

SAMPLE_VONDST_DOCS = [
    {
        "_id": "TEST_DC001_V001",
        "table": "VONDSTEN",
        "project": "DC001",
        "brondata": {
            "VONDSTNR": "1",
            "PUTNR": "3",
            "SPOORNR": "5",
            "MATERIAAL": "Aardewerk",
            "AANTAL": "12",
            "GEWICHT": "250",
            "DATERING": "1600-1700",
        },
    },
    {
        "_id": "TEST_DC001_V002",
        "table": "VONDSTEN",
        "project": "DC001",
        "brondata": {
            "VONDSTNR": "2",
            "PUTNR": "3",
            "SPOORNR": "7",
            "MATERIAAL": "Glas",
            "AANTAL": "3",
            "GEWICHT": "50",
            "DATERING": "17cd",
        },
    },
]

SAMPLE_SPOOR_DOCS = [
    {
        "_id": "TEST_DC001_S005",
        "table": "SPOREN",
        "project": "DC001",
        "brondata": {
            "SPOORNR": "5",
            "PUTNR": "3",
            "VLAKNR": "1",
            "AARD": "Kuil",
            "KLEUR": "Bruin",
            "DATERING": "1600-1700",
        },
    },
]


# ============================================================
# Tests
# ============================================================

@pytest.mark.integration
class TestHarmonizePipelineVondst:
    """Test de volledige Vondst-harmonisatie op een echte MongoDB."""

    def test_pipeline_runs_without_error(self, staging_db, analyse_db):
        """De pipeline moet zonder fouten draaien op testdata."""
        coll = staging_db["Single_Store_Test"]
        coll.drop()
        coll.insert_many(SAMPLE_VONDST_DOCS)

        pipeline = getHarmonizeAggr("Vondst", reload=True)

        # Pas de $merge target aan naar de test-DB
        for stage in pipeline:
            if "$merge" in stage:
                stage["$merge"]["into"]["db"] = DB_ANALYSE
                stage["$merge"]["into"]["coll"] = "Single_Store_Test"

        # Voer de pipeline uit
        list(coll.aggregate(pipeline))

        # Controleer dat er resultaten in de analyse-DB staan
        result_coll = analyse_db["Single_Store_Test"]
        count = result_coll.count_documents({})
        assert count >= 1, f"Verwachtte minstens 1 document, maar vond {count}"

    def test_output_has_expected_fields(self, staging_db, analyse_db):
        """Het output-document moet de verwachte geharmoniseerde velden bevatten.

        De harmonisatie-pipeline plaatst het hele brondocument in 'brondata'
        en voegt metadata-velden toe op het hoogste niveau (soort, etc.).
        De oorspronkelijke bronvelden staan in brondata.brondata.
        """
        result_coll = analyse_db["Single_Store_Test"]
        doc = result_coll.find_one({"_id": "TEST_DC001_V001"})

        if doc is None:
            pytest.skip("Geen output-document gevonden (pipeline niet succesvol)")

        # De pipeline voegt 'soort' toe en nest het brondocument in 'brondata'
        assert "soort" in doc, f"'soort' ontbreekt in output: {list(doc.keys())}"
        assert doc["soort"] == "Vondst", f"Verwachtte soort='Vondst', kreeg '{doc['soort']}'"
        assert "brondata" in doc, f"'brondata' ontbreekt in output: {list(doc.keys())}"

        # Oorspronkelijke velden zijn bereikbaar via brondata
        brondata = doc["brondata"]
        assert "brondata" in brondata or "VONDSTNR" in brondata, \
            f"Brondata-velden ontbreken in genest document: {list(brondata.keys())}"


@pytest.mark.integration
class TestHarmonizePipelineSpoor:
    """Test de Spoor-harmonisatie."""

    def test_spoor_pipeline_runs(self, staging_db, analyse_db):
        coll = staging_db["Single_Store_Test"]
        # Voeg spoor-documenten toe (naast bestaande vondsten)
        coll.insert_many(SAMPLE_SPOOR_DOCS)

        pipeline = getHarmonizeAggr("Spoor", reload=True)

        for stage in pipeline:
            if "$merge" in stage:
                stage["$merge"]["into"]["db"] = DB_ANALYSE
                stage["$merge"]["into"]["coll"] = "Single_Store_Test"

        list(coll.aggregate(pipeline))

        result_coll = analyse_db["Single_Store_Test"]
        spoor_doc = result_coll.find_one({"_id": "TEST_DC001_S005"})
        assert spoor_doc is not None, "Spoor-document niet gevonden in output"


@pytest.mark.integration
class TestHarmonizeMultipleObjects:
    """Test dat meerdere objecttypen achter elkaar geharmoniseerd kunnen worden."""

    def test_all_standard_objects(self, staging_db, analyse_db):
        """Draai harmonisatie voor alle standaard objecttypen (zonder data).
        Dit test of de pipelines geldig zijn en MongoDB ze accepteert."""
        from wasstraat.harmonizer import getObjects

        coll = staging_db["Single_Store_Test"]

        for obj in getObjects(inherit=False, merge=False):
            pipeline = getHarmonizeAggr(obj, reload=True)

            for stage in pipeline:
                if "$merge" in stage:
                    stage["$merge"]["into"]["db"] = DB_ANALYSE
                    stage["$merge"]["into"]["coll"] = "Single_Store_Test"

            # Moet niet crashen, ook zonder data
            try:
                list(coll.aggregate(pipeline))
            except Exception as e:
                pytest.fail(f"Pipeline voor '{obj}' faalde: {e}")
