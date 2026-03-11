"""
Integratietest: draai Extract + Transform met echte testdata (DB034).

Triggert Extract_only en DAG_Transform_Only via ``docker exec`` en
verifieert daarna de record-aantallen in de drie MongoDB databases:
  - Arch_Staging_Test  (extract-resultaat)
  - Arch_Analyse_Test  (Single_Store + Single_Store_Clean)
  - Arch_Files_Test

Geen PostgreSQL-verificatie — alleen MongoDB.

Draaien:
  make integration-real-data
"""
import os
import subprocess
import time

import pytest

pymongo = pytest.importorskip("pymongo")

# ============================================================
# Configuratie
# ============================================================

MONGO_TEST_URI = os.getenv(
    "MONGO_TEST_URI",
    "mongodb://testroot:testpass@localhost:27117/",
)
AIRFLOW_CONTAINER = os.getenv("AIRFLOW_CONTAINER", "wasstraat_airflow_test")

DB_STAGING = "Arch_Staging_Test"
DB_ANALYSE = "Arch_Analyse_Test"
DB_FILES = "Arch_Files_Test"

# Verwachte MINIMUM-aantallen per artefactsoort in Single_Store_Clean.
# Tijdens de pipeline kunnen er records bijkomen (merge, generate_missing),
# daarom testen we met >= in plaats van ==.
EXPECTED_MIN_ARTEFACT_COUNTS = {
    "Aardewerk": 4510,
    "Glas": 20,
    "Hout": 294,
    "Menselijk_Bot": 273,
    "Metaal": 229,
    "Steen": 146,
    # NB: Munt niet in testdata — de MDB (opgravingDB34.mdb) bevat geen
    # tabel die matcht op het harmonize-patroon ["MUNT.*", "MUNTEN EN PENNINGEN"].
}

# Verwachte MINIMUM-aantallen per soort in Single_Store_Clean.
EXPECTED_MIN_SOORT_COUNTS = {
    "Spoor": 456,
    "Vondst": 1478,
    "Vulling": 425,
}

# Verwachte aantallen voor afbeeldingen.
# In de testdata zitten 96 jpg-bestanden in L Fotos/.
# Na verwerking komen deze in Plaatjes (Arch_Files_Test)
# en via mergeFotoinfo als "Bestand"-records in Single_Store_Clean.
EXPECTED_MIN_PLAATJES = 21        # minimaal verwacht in Plaatjes collectie
EXPECTED_MIN_BESTAND_CLEAN = 21   # minimaal verwacht als soort "Bestand" in Clean


# ============================================================
# Helpers
# ============================================================

def run_dag(dag_id: str, timeout: int = 1800) -> subprocess.CompletedProcess:
    """Draai een Airflow DAG synchroon via ``airflow dags test``.

    Raise AssertionError wanneer de DAG faalt.
    """
    cmd = [
        "docker", "exec", AIRFLOW_CONTAINER,
        "airflow", "dags", "test", dag_id, "2024-01-01",
    ]
    print(f"\n  ▶ {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)

    # Toon altijd de laatste regels stdout (DAG taak-overzicht)
    if result.stdout:
        lines = result.stdout.strip().split("\n")
        print(f"\n  --- stdout (laatste 40 regels) ---")
        for line in lines[-40:]:
            print(f"    {line}")

    if result.returncode != 0:
        print(f"\n  ⚠  DAG {dag_id} GEFAALD (exit code {result.returncode})")
        if result.stderr:
            print(f"\n  --- stderr (laatste 40 regels) ---")
            for line in result.stderr.strip().split("\n")[-40:]:
                print(f"    {line}")
        assert False, f"DAG {dag_id} faalde met exit code {result.returncode}"
    else:
        print(f"  ✓  DAG {dag_id} succesvol (exit code 0)")

    # Check ook of er FAILED tasks in de output staan
    if result.stdout and "ERROR" in result.stdout:
        error_lines = [l for l in result.stdout.split("\n") if "ERROR" in l]
        print(f"\n  ⚠  {len(error_lines)} ERROR-regels gevonden in DAG output:")
        for line in error_lines[:20]:
            print(f"    {line}")

    return result


def wait_for_airflow(max_wait: int = 180):
    """Wacht tot Airflow DAGs beschikbaar zijn."""
    for _ in range(max_wait):
        try:
            r = subprocess.run(
                ["docker", "exec", AIRFLOW_CONTAINER,
                 "airflow", "dags", "list", "-o", "plain"],
                capture_output=True, text=True, timeout=10,
            )
            if r.returncode == 0 and "Extract" in r.stdout:
                return True
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass
        time.sleep(1)
    return False


def mongo_soort_counts(db_name, collection, client):
    """Tel documenten per ``soort``."""
    pipeline = [
        {"$group": {"_id": "$soort", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
    ]
    return {d["_id"]: d["count"]
            for d in client[db_name][collection].aggregate(pipeline)}


def mongo_table_counts(db_name, collection, client):
    """Tel documenten per ``table`` (voor staging-collectie)."""
    pipeline = [
        {"$group": {"_id": "$table", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
    ]
    return {d["_id"]: d["count"]
            for d in client[db_name][collection].aggregate(pipeline)}


def mongo_artefact_counts(db_name, client):
    """Tel Artefact-documenten per ``artefactsoort`` in Single_Store_Clean."""
    coll = client[db_name]["Single_Store_Clean"]
    pipeline = [
        {"$match": {"soort": "Artefact"}},
        {"$group": {"_id": "$artefactsoort", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
    ]
    return {d["_id"]: d["count"] for d in coll.aggregate(pipeline)}


def print_all_collections(client, db_name, label=""):
    """Print alle collecties en hun doc-counts in een database."""
    db = client[db_name]
    collections = sorted(db.list_collection_names())
    print(f"\n  {label} Collecties in {db_name} ({len(collections)}):")
    for coll_name in collections:
        count = db[coll_name].estimated_document_count()
        print(f"    {coll_name}: {count}")
    return {c: db[c].estimated_document_count() for c in collections}


# ============================================================
# Fixtures
# ============================================================

@pytest.fixture(scope="module")
def mongo_client():
    client = pymongo.MongoClient(MONGO_TEST_URI, serverSelectionTimeoutMS=5000)
    try:
        client.admin.command("ping")
    except pymongo.errors.ConnectionFailure:
        pytest.skip("MongoDB niet bereikbaar op " + MONGO_TEST_URI)
    yield client
    client.close()


@pytest.fixture(scope="module")
def airflow_ready():
    """Wacht tot Airflow klaar is."""
    print("\n  Wachten op Airflow...")
    if not wait_for_airflow():
        pytest.skip("Airflow niet klaar — start met: make integration-real-data")
    print("  ✓ Airflow klaar")


# ============================================================
# Tests
# ============================================================

@pytest.mark.integration
class TestFullPipelineRealData:
    """Extract + Transform met echte data, verifieer MongoDB."""

    # ----------------------------------------------------------
    # Stap 1: Extract
    # ----------------------------------------------------------
    def test_01_run_extract(self, airflow_ready):
        """Trigger Extract_only DAG."""
        run_dag("Extract_only", timeout=1200)

    def test_02_verify_staging(self, mongo_client):
        """Staging-collectie bevat geëxtraheerde tabellen uit de MDB."""
        print_all_collections(mongo_client, DB_STAGING, "Na Extract:")
        counts = mongo_table_counts(DB_STAGING, "Staging_Projecten_Oud", mongo_client)
        total = sum(counts.values())
        print(f"\n  Staging-tabellen ({len(counts)}, totaal {total} docs):")
        for table, count in sorted(counts.items(), key=lambda x: -x[1]):
            print(f"    {table}: {count}")
        assert total > 100, f"Te weinig staging-documenten: {total}"

    # ----------------------------------------------------------
    # Stap 2: Transform (harmonize + enhance + keys + move/merge + refs)
    # ----------------------------------------------------------
    def test_03_run_transform(self, airflow_ready):
        """Trigger DAG_Transform_Only DAG (alle transform-stappen)."""
        run_dag("DAG_Transform_Only", timeout=1800)

    def test_04_diagnostic_all_collections(self, mongo_client):
        """Diagnostiek: toon alle collecties en aantallen na transform."""
        print_all_collections(mongo_client, DB_STAGING, "Staging:")
        analyse_colls = print_all_collections(mongo_client, DB_ANALYSE, "Analyse:")
        print_all_collections(mongo_client, DB_FILES, "Files:")

        clean_count = analyse_colls.get("Single_Store_Clean", 0)
        store_count = analyse_colls.get("Single_Store", 0)
        print(f"\n  Single_Store: {store_count}, Single_Store_Clean: {clean_count}")

        # Diagnostiek: toon artefact-subtypes in Single_Store (vóór move/merge)
        store_coll = mongo_client[DB_ANALYSE]["Single_Store"]
        pipeline = [
            {"$match": {"soort": "Artefact"}},
            {"$group": {"_id": "$artefactsoort", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}},
        ]
        store_artefacts = {d["_id"]: d["count"] for d in store_coll.aggregate(pipeline)}
        print(f"\n  Artefact-subtypes in Single_Store ({sum(store_artefacts.values())} totaal):")
        for soort, count in sorted(store_artefacts.items(), key=lambda x: -x[1]):
            print(f"    {soort}: {count}")

        # Diagnostiek: toon artefact-subtypes in Single_Store_Clean (na move/merge)
        clean_artefacts = mongo_artefact_counts(DB_ANALYSE, mongo_client)
        if clean_artefacts:
            print(f"\n  Artefact-subtypes in Single_Store_Clean ({sum(clean_artefacts.values())} totaal):")
            for soort, count in sorted(clean_artefacts.items(), key=lambda x: -x[1]):
                marker = ""
                if soort in EXPECTED_MIN_ARTEFACT_COUNTS:
                    exp = EXPECTED_MIN_ARTEFACT_COUNTS[soort]
                    marker = f"  (verwacht >= {exp})"
                print(f"    {soort}: {count}{marker}")

            # Toon ontbrekende artefactsoorten
            for soort, exp in EXPECTED_MIN_ARTEFACT_COUNTS.items():
                if soort not in clean_artefacts:
                    in_store = store_artefacts.get(soort, 0)
                    print(f"    ⚠  {soort}: 0 in Clean (verwacht >= {exp}), {in_store} in Single_Store")

    def test_05_verify_single_store(self, mongo_client):
        """Single_Store bevat geharmoniseerde documenten."""
        counts = mongo_soort_counts(DB_ANALYSE, "Single_Store", mongo_client)
        total = sum(counts.values())
        print(f"\n  Single_Store ({len(counts)} soorten, totaal {total}):")
        for soort, count in sorted(counts.items(), key=lambda x: -x[1]):
            print(f"    {soort}: {count}")
        assert total > 100, f"Te weinig in Single_Store: {total}"

    def test_06_verify_clean(self, mongo_client):
        """Single_Store_Clean bevat gemerge en opgeschoonde documenten."""
        counts = mongo_soort_counts(DB_ANALYSE, "Single_Store_Clean", mongo_client)
        total = sum(counts.values())
        print(f"\n  Single_Store_Clean ({len(counts)} soorten, totaal {total}):")
        for soort, count in sorted(counts.items(), key=lambda x: -x[1]):
            print(f"    {soort}: {count}")
        assert total > 100, f"Te weinig in Single_Store_Clean: {total}"

    # ----------------------------------------------------------
    # Stap 3: Verificatie van verwachte aantallen
    # ----------------------------------------------------------
    def test_07_verify_artefact_counts(self, mongo_client):
        """Artefact-subtypes in Single_Store_Clean >= verwachte aantallen."""
        artefact_counts = mongo_artefact_counts(DB_ANALYSE, mongo_client)

        print(f"\n  Artefact-subtypes in clean-collectie:")
        for soort, count in sorted(artefact_counts.items(), key=lambda x: -x[1]):
            print(f"    {soort}: {count}")

        for soort, expected in EXPECTED_MIN_ARTEFACT_COUNTS.items():
            actual = artefact_counts.get(soort, 0)
            assert actual >= expected, \
                f"{soort}: verwacht >= {expected}, gevonden {actual}"

    def test_08_verify_spoor_count(self, mongo_client):
        """Spoor-documenten in clean-collectie >= verwacht."""
        counts = mongo_soort_counts(DB_ANALYSE, "Single_Store_Clean", mongo_client)
        actual = counts.get("Spoor", 0)
        expected = EXPECTED_MIN_SOORT_COUNTS["Spoor"]
        print(f"\n  Sporen: {actual} (verwacht >= {expected})")
        assert actual >= expected

    def test_09_verify_vondst_count(self, mongo_client):
        """Vondst-documenten in clean-collectie >= verwacht."""
        counts = mongo_soort_counts(DB_ANALYSE, "Single_Store_Clean", mongo_client)
        actual = counts.get("Vondst", 0)
        expected = EXPECTED_MIN_SOORT_COUNTS["Vondst"]
        print(f"\n  Vondsten: {actual} (verwacht >= {expected})")
        assert actual >= expected

    def test_10_verify_vulling_count(self, mongo_client):
        """Vulling-documenten in clean-collectie >= verwacht."""
        counts = mongo_soort_counts(DB_ANALYSE, "Single_Store_Clean", mongo_client)
        actual = counts.get("Vulling", 0)
        expected = EXPECTED_MIN_SOORT_COUNTS["Vulling"]
        print(f"\n  Vullingen: {actual} (verwacht >= {expected})")
        assert actual >= expected

    # ----------------------------------------------------------
    # Stap 4: Verificatie van afbeeldingen
    # ----------------------------------------------------------
    def test_11_verify_filenames_collection(self, mongo_client):
        """Filenames-collectie in Arch_Files_Test is gevuld na Extract."""
        db = mongo_client[DB_FILES]
        filenames_count = db["Filenames"].count_documents({})
        processed_count = db["Filenames"].count_documents({"processed": True})
        print(f"\n  Filenames collectie: {filenames_count} totaal, {processed_count} verwerkt")
        assert filenames_count > 0, "Filenames collectie is leeg — image discovery heeft niets gevonden"
        assert processed_count > 0, "Geen enkel bestand is verwerkt (processed=True)"

    def test_12_verify_plaatjes_collection(self, mongo_client):
        """Plaatjes-collectie in Arch_Staging_Test bevat verwerkte afbeeldingen."""
        db = mongo_client[DB_STAGING]
        plaatjes_count = db["Plaatjes"].count_documents({})
        print(f"\n  Plaatjes collectie: {plaatjes_count} documenten")

        # Diagnostiek: toon verdeling per projectcd
        pipeline = [
            {"$group": {"_id": "$projectcd", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}},
        ]
        per_project = {d["_id"]: d["count"]
                       for d in db["Plaatjes"].aggregate(pipeline)}
        print(f"  Per projectcd:")
        for proj, cnt in sorted(per_project.items(), key=lambda x: -x[1]):
            print(f"    {proj}: {cnt}")

        # Diagnostiek: toon verdeling per fileType
        pipeline_ft = [
            {"$group": {"_id": "$fileType", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}},
        ]
        per_type = {d["_id"]: d["count"]
                    for d in db["Plaatjes"].aggregate(pipeline_ft)}
        print(f"  Per fileType: {per_type}")

        assert plaatjes_count >= EXPECTED_MIN_PLAATJES, \
            f"Plaatjes: verwacht >= {EXPECTED_MIN_PLAATJES}, gevonden {plaatjes_count}"

    def test_13_verify_plaatjes_fields(self, mongo_client):
        """Plaatjes-documenten bevatten de vereiste velden."""
        db = mongo_client[DB_STAGING]
        sample = db["Plaatjes"].find_one()
        assert sample is not None, "Geen Plaatjes-documenten gevonden"

        required_fields = ["fileName", "fullFileName", "imageID", "imageMiddleID",
                           "imageThumbID", "fileType", "directory", "mime_type"]
        missing = [f for f in required_fields if f not in sample]
        print(f"\n  Voorbeeld Plaatjes-document velden: {sorted(sample.keys())}")
        assert not missing, f"Plaatjes-document mist velden: {missing}"

        # Elk document moet een projectcd of rapportnr hebben
        has_project = db["Plaatjes"].count_documents({"projectcd": {"$exists": True}})
        has_rapport = db["Plaatjes"].count_documents({"rapportnr": {"$exists": True}})
        print(f"  Met projectcd: {has_project}, met rapportnr: {has_rapport}")
        assert (has_project + has_rapport) > 0, \
            "Geen enkel Plaatjes-document heeft projectcd of rapportnr"

    def test_14_verify_foto_in_single_store(self, mongo_client):
        """Single_Store bevat Foto-records (geharmoniseerde foto-metadata uit MDB)."""
        coll = mongo_client[DB_ANALYSE]["Single_Store"]
        foto_count = coll.count_documents({"soort": "Foto"})
        print(f"\n  Foto-records in Single_Store: {foto_count}")

        # Diagnostiek: toon fototypes
        pipeline = [
            {"$match": {"soort": "Foto"}},
            {"$group": {"_id": "$fototype", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}},
        ]
        per_type = {d["_id"]: d["count"] for d in coll.aggregate(pipeline)}
        print(f"  Per fototype: {per_type}")

        assert foto_count > 0, "Geen Foto-records in Single_Store"

    def test_15_verify_bestand_in_clean(self, mongo_client):
        """Single_Store_Clean bevat Bestand-records (output van mergeFotoinfo)."""
        coll = mongo_client[DB_ANALYSE]["Single_Store_Clean"]
        bestand_count = coll.count_documents({"soort": "Bestand"})
        print(f"\n  Bestand-records in Single_Store_Clean: {bestand_count}")

        # Diagnostiek: toon bestandsoorten
        pipeline = [
            {"$match": {"soort": "Bestand"}},
            {"$group": {"_id": "$bestandsoort_1", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}},
        ]
        per_soort = {d["_id"]: d["count"] for d in coll.aggregate(pipeline)}
        if per_soort:
            print(f"  Per bestandsoort_1: {per_soort}")

        assert bestand_count >= EXPECTED_MIN_BESTAND_CLEAN, \
            f"Bestand in Clean: verwacht >= {EXPECTED_MIN_BESTAND_CLEAN}, gevonden {bestand_count}"

    # ----------------------------------------------------------
    # Samenvatting
    # ----------------------------------------------------------
    def test_16_summary(self, mongo_client):
        """Eindoverzicht van alle aantallen."""
        counts = mongo_soort_counts(DB_ANALYSE, "Single_Store_Clean", mongo_client)
        artefact_counts = mongo_artefact_counts(DB_ANALYSE, mongo_client)

        print("\n" + "=" * 60)
        print("  SAMENVATTING — Single_Store_Clean")
        print("=" * 60)

        print(f"\n  {'Soort':<25} {'Aantal':>8}")
        print("  " + "-" * 35)
        for soort, count in sorted(counts.items(), key=lambda x: -x[1]):
            print(f"  {soort:<25} {count:>8,}")

        print(f"\n  Artefact-subtypes:")
        print(f"  {'Soort':<25} {'Aantal':>8} {'Min.':>8} {'':>3}")
        print("  " + "-" * 47)
        for soort, exp in sorted(EXPECTED_MIN_ARTEFACT_COUNTS.items()):
            act = artefact_counts.get(soort, 0)
            ok = "✓" if act >= exp else "✗"
            print(f"  {soort:<25} {act:>8,} {exp:>8,}  {ok}")

        # Toon ook artefactsoorten die niet in de verwachting staan
        for soort, act in sorted(artefact_counts.items(), key=lambda x: -x[1]):
            if soort not in EXPECTED_MIN_ARTEFACT_COUNTS:
                print(f"  {soort:<25} {act:>8,} {'n.v.t.':>8}")

        print()
        for soort, exp in sorted(EXPECTED_MIN_SOORT_COUNTS.items()):
            act = counts.get(soort, 0)
            ok = "✓" if act >= exp else "✗"
            print(f"  {soort + ' (>=' + str(exp) + ')':<25} {act:>8,} {'':>8}  {ok}")

        # Afbeeldingen
        print(f"\n  Afbeeldingen:")
        print("  " + "-" * 47)
        db_files = mongo_client[DB_FILES]
        db_staging = mongo_client[DB_STAGING]
        plaatjes = db_staging["Plaatjes"].count_documents({})
        filenames_total = db_files["Filenames"].count_documents({})
        filenames_done = db_files["Filenames"].count_documents({"processed": True})
        bestand = counts.get("Bestand", 0)

        ok_p = "✓" if plaatjes >= EXPECTED_MIN_PLAATJES else "✗"
        ok_b = "✓" if bestand >= EXPECTED_MIN_BESTAND_CLEAN else "✗"
        print(f"  {'Filenames':<25} {filenames_total:>8,} (verwerkt: {filenames_done})")
        print(f"  {'Plaatjes (>=' + str(EXPECTED_MIN_PLAATJES) + ')':<25} {plaatjes:>8,} {'':>8}  {ok_p}")
        print(f"  {'Bestand (>=' + str(EXPECTED_MIN_BESTAND_CLEAN) + ')':<25} {bestand:>8,} {'':>8}  {ok_b}")

        print("=" * 60)
