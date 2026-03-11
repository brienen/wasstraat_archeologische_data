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
    # Samenvatting
    # ----------------------------------------------------------
    def test_11_summary(self, mongo_client):
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

        print("=" * 60)
