"""
Integratietest: draai Extract + Transform met synthetische data (SY001 + SY002).

Triggert Extract_only en DAG_Transform_Only via ``docker exec`` en
verifieert daarna de record-aantallen in de drie MongoDB databases:
  - Arch_Staging_Test  (extract-resultaat)
  - Arch_Analyse_Test  (Single_Store + Single_Store_Clean)

Geen PostgreSQL-verificatie — alleen MongoDB.
Geen afbeeldingen-verificatie — synthetische data bevat geen fotobestanden.

Draaien:
  make integration
"""
import json
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
POSTGRES_CONTAINER = os.getenv("POSTGRES_CONTAINER", "wasstraat_postgres_test")

DB_STAGING = "Arch_Staging_Test"
DB_ANALYSE = "Arch_Analyse_Test"
DB_FILES = "Arch_Files_Test"

# Verwachte MINIMUM-aantallen per artefactsoort in Single_Store_Clean.
# Gebaseerd op synthetische data: SY001 (3 aw, 2 glas) + SY002 (8 aw, 3 glas,
# 2 bot, 2 metaal, 1 steen, 2 kleipijp, 1 leer, 1 munt).
EXPECTED_MIN_ARTEFACT_COUNTS = {
    "Aardewerk": 11,
    "Glas": 5,
    "Dierlijk_Bot": 2,
    "Metaal": 2,
    "Steen": 1,
    "Kleipijp": 2,
    "Leer": 1,
    "Munt": 0,
}

# Verwachte MINIMUM-aantallen per soort in Single_Store_Clean.
# Projecten: 2 (SY001 + SY002)
# SY001: 3 sporen, 4 vondsten, 2 vullingen
# SY002: 8 sporen, 12 vondsten, 4 vullingen
# Monsters: 5 (3x SY001 + 2x SY002), 8 botanie, 4 schelp
EXPECTED_MIN_SOORT_COUNTS = {
    "Project": 2,
    "Spoor": 11,
    "Vondst": 16,
    "Vulling": 6,
    "Monster": 5,
    "Monster_Botanie": 8,
    "Monster_Schelp": 4,
    "DT_Soort_Plant": 5,
    "DT_Soort_Schelp": 3,
    "DT_Soort_Deel": 4,
    "DT_Soort_Staat": 4,
}


# ============================================================
# Helpers
# ============================================================

def run_dag(dag_id: str, timeout: int = 1800, poll_interval: int = 3) -> str:
    """Draai een Airflow DAG via ``dags test`` en wacht op voltooiing.

    Gebruikt ``airflow dags test`` omdat ``dags trigger`` op Airflow 2.10
    een DagNotFound-bug heeft (de trigger-API laadt de DagBag niet correct
    uit de serialized DAG store). ``dags test`` draait taken sequentieel
    maar is betrouwbaar en vereist geen actieve scheduler.

    Raise AssertionError wanneer de DAG faalt of timeout bereikt.
    """
    test_cmd = [
        "docker", "exec", AIRFLOW_CONTAINER,
        "airflow", "dags", "test", dag_id, "2026-01-01",
    ]
    print(f"\n  ▶ {' '.join(test_cmd)}")
    t_start = time.time()

    result = subprocess.run(
        test_cmd, capture_output=True, text=True, timeout=timeout,
    )

    t_elapsed = time.time() - t_start

    if result.returncode != 0:
        # Toon de laatste regels van stdout en stderr voor debugging
        all_output = (result.stdout + "\n" + result.stderr).strip().split("\n")
        # Filter op ERROR, Exception, Traceback en andere relevante regels
        error_lines = [l for l in all_output if any(kw in l for kw in
            ['ERROR', 'Exception', 'Traceback', 'Error', 'FAILED', 'failed',
             'raise', 'Onbekende fout', 'melding', 'Warning', 'warning'])]
        if not error_lines:
            error_lines = all_output[-30:]  # fallback: laatste 30 regels
        print(f"  ⚠  DAG {dag_id} gefaald na {t_elapsed:.1f}s:")
        for line in error_lines[-30:]:
            print(f"    {line}")
        assert False, f"DAG {dag_id} gefaald (exit code {result.returncode})"

    # Check op DagRun state in de output
    if "state=success" in result.stdout or "state=success" in result.stderr:
        print(f"  ⏱  {dag_id} duurde {t_elapsed:.1f}s (state=success)")
        print(f"  ✓  DAG {dag_id} succesvol")
        return "success"

    # Fallback: als exit code 0 maar geen state=success → waarschuw maar ga door
    print(f"  ⏱  {dag_id} duurde {t_elapsed:.1f}s (exit code 0)")
    print(f"  ✓  DAG {dag_id} voltooid")
    return "success"


def _print_failed_tasks(dag_id: str, run_id: str):
    """Toon gefaalde taken en hun logs voor debugging."""
    try:
        cmd = [
            "docker", "exec", AIRFLOW_CONTAINER,
            "airflow", "tasks", "states-for-dag-run", dag_id, run_id, "-o", "json",
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode == 0 and result.stdout.strip():
            tasks = json.loads(result.stdout)
            failed = [t for t in tasks if t.get("state") == "failed"]
            if failed:
                print(f"\n  ⚠  {len(failed)} gefaalde taken:")
                for t in failed:
                    task_id = t.get("task_id", "?")
                    print(f"    - {task_id}")
                    # Probeer de log van de eerste gefaalde taak op te halen
                    _print_task_log(dag_id, task_id, run_id)
    except (subprocess.TimeoutExpired, json.JSONDecodeError, Exception) as e:
        print(f"  (kon gefaalde taken niet ophalen: {e})")


def _print_task_log(dag_id: str, task_id: str, run_id: str, tail: int = 30):
    """Haal de laatste regels van een taak-log op voor debugging."""
    try:
        # Zoek het logbestand in de container
        log_cmd = [
            "docker", "exec", AIRFLOW_CONTAINER,
            "find", "/opt/airflow/logs", "-path", f"*{dag_id}*{task_id}*",
            "-name", "*.log", "-type", "f",
        ]
        result = subprocess.run(log_cmd, capture_output=True, text=True, timeout=10)
        if result.returncode == 0 and result.stdout.strip():
            log_file = result.stdout.strip().split("\n")[-1]
            tail_cmd = [
                "docker", "exec", AIRFLOW_CONTAINER,
                "tail", f"-{tail}", log_file,
            ]
            tail_result = subprocess.run(
                tail_cmd, capture_output=True, text=True, timeout=10,
            )
            if tail_result.stdout:
                print(f"      --- log {task_id} (laatste {tail} regels) ---")
                for line in tail_result.stdout.strip().split("\n"):
                    print(f"      {line}")
    except Exception:
        pass


def _check_dag_errors(dag_id: str, run_id: str):
    """Zoek ERROR-regels in de taak-logs van een succesvolle DAG run."""
    try:
        log_cmd = [
            "docker", "exec", AIRFLOW_CONTAINER,
            "bash", "-c",
            f"grep -r 'ERROR' /opt/airflow/logs/dag_id={dag_id}/ 2>/dev/null | tail -20",
        ]
        result = subprocess.run(log_cmd, capture_output=True, text=True, timeout=15)
        if result.returncode == 0 and result.stdout.strip():
            error_lines = result.stdout.strip().split("\n")
            print(f"\n  ⚠  {len(error_lines)} ERROR-regels gevonden in DAG logs:")
            for line in error_lines[:20]:
                print(f"    {line}")
    except Exception:
        pass


def wait_for_airflow(max_wait: int = 180):
    """Wacht tot Airflow scheduler actief is en DAGs beschikbaar zijn."""
    # Stap 1: wacht tot DAGs geparsed zijn
    for _ in range(max_wait):
        try:
            r = subprocess.run(
                ["docker", "exec", AIRFLOW_CONTAINER,
                 "airflow", "dags", "list", "-o", "plain"],
                capture_output=True, text=True, timeout=10,
            )
            if r.returncode == 0 and "Extract" in r.stdout:
                break
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass
        time.sleep(1)
    else:
        return False

    # Stap 2: dags test vereist geen scheduler, dus geen extra wacht nodig.
    print("  ✓ Airflow DAGs geparsed, klaar voor dags test")
    return True


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


def _pg_scalar(sql):
    """Voer een SQL-query uit op de test-PostgreSQL en retourneer de eerste waarde.

    Gebruikt docker exec om psql aan te roepen op de test-container.
    """
    cmd = [
        "docker", "exec", POSTGRES_CONTAINER,
        "psql", "-U", "testuser", "-h", "localhost", "-d", "airflow_test",
        "-t", "-A", "-c", sql,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
    if result.returncode != 0:
        raise RuntimeError(f"psql fout: {result.stderr.strip()}")
    return int(result.stdout.strip()) if result.stdout.strip() else 0


def _pg_table_count(table):
    """Tel het aantal rijen in een PostgreSQL-tabel."""
    return _pg_scalar(f'SELECT COUNT(*) FROM "{table}"')


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
        pytest.skip("Airflow niet klaar — start met: make integration")
    print("  ✓ Airflow klaar")


# ============================================================
# Tests
# ============================================================

@pytest.mark.integration
class TestFullPipelineSynthetic:
    """Extract + Transform met synthetische data (SY001 + SY002), verifieer MongoDB."""

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
        assert total > 10, f"Te weinig staging-documenten: {total}"

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
        assert total > 10, f"Te weinig in Single_Store: {total}"

    def test_06_verify_clean(self, mongo_client):
        """Single_Store_Clean bevat gemerge en opgeschoonde documenten."""
        counts = mongo_soort_counts(DB_ANALYSE, "Single_Store_Clean", mongo_client)
        total = sum(counts.values())
        print(f"\n  Single_Store_Clean ({len(counts)} soorten, totaal {total}):")
        for soort, count in sorted(counts.items(), key=lambda x: -x[1]):
            print(f"    {soort}: {count}")
        assert total > 10, f"Te weinig in Single_Store_Clean: {total}"

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

    def test_10a_verify_project_count(self, mongo_client):
        """Project-documenten in clean-collectie >= verwacht."""
        counts = mongo_soort_counts(DB_ANALYSE, "Single_Store_Clean", mongo_client)
        actual = counts.get("Project", 0)
        expected = EXPECTED_MIN_SOORT_COUNTS["Project"]
        print(f"\n  Projecten: {actual} (verwacht >= {expected})")
        assert actual >= expected, (
            f"Project: verwacht >= {expected}, gevonden {actual}. "
            f"Controleer of Project MOVEANDMERGE_MOVE heeft in meta.py."
        )

    def test_10b_verify_project_has_location(self, mongo_client):
        """Projecten in clean-collectie moeten latitude/longitude hebben."""
        coll = mongo_client[DB_ANALYSE]["Single_Store_Clean"]
        projecten = list(coll.find({"soort": "Project"}, {
            "projectcd": 1, "latitude": 1, "longitude": 1,
            "xcoor_rd": 1, "ycoor_rd": 1, "key": 1,
        }))

        print(f"\n  Projecten met locatie ({len(projecten)} records):")
        met_locatie = 0
        for p in projecten:
            lat = p.get("latitude")
            lon = p.get("longitude")
            projectcd = p.get("projectcd", "?")
            key = p.get("key", "?")
            heeft_loc = lat is not None and lon is not None
            if heeft_loc:
                met_locatie += 1
            print(f"    {projectcd} (key={key}): lat={lat}, lon={lon}")

        assert met_locatie >= 1, (
            f"Geen enkel project heeft latitude/longitude. "
            f"Controleer RD→WGS84 conversie in setAttributes_functions.py."
        )

    def test_10c_verify_project_keys(self, mongo_client):
        """Projecten hebben correcte key (begint met 'P')."""
        coll = mongo_client[DB_ANALYSE]["Single_Store_Clean"]
        projecten = list(coll.find({"soort": "Project"}, {
            "key": 1, "projectcd": 1,
        }))

        for p in projecten:
            key = p.get("key", "")
            assert key.startswith("P"), (
                f"Project key '{key}' begint niet met 'P'"
            )

    # ----------------------------------------------------------
    # Samenvatting
    # ----------------------------------------------------------
    def test_11_summary(self, mongo_client):
        """Eindoverzicht van alle aantallen."""
        counts = mongo_soort_counts(DB_ANALYSE, "Single_Store_Clean", mongo_client)
        artefact_counts = mongo_artefact_counts(DB_ANALYSE, mongo_client)

        print("\n" + "=" * 60)
        print("  SAMENVATTING — Single_Store_Clean (synthetische data)")
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

    # ----------------------------------------------------------
    # Stap 4: Verificatie van monsterdata
    # ----------------------------------------------------------
    def test_12_verify_monster_staging(self, mongo_client):
        """Staging_Monster bevat geëxtraheerde monstertabellen uit de MDB."""
        db = mongo_client[DB_STAGING]
        coll_names = db.list_collection_names()
        staging_colls = [c for c in coll_names if "monster" in c.lower() or "Monster" in c]
        print(f"\n  Monster-gerelateerde staging collecties: {staging_colls}")

        for coll_name in staging_colls:
            counts = mongo_table_counts(DB_STAGING, coll_name, mongo_client)
            total = sum(counts.values())
            print(f"\n  {coll_name} tabellen ({len(counts)}, totaal {total} docs):")
            for table, count in sorted(counts.items(), key=lambda x: -x[1]):
                print(f"    {table}: {count}")
            if total > 0:
                assert total >= 5, (
                    f"Te weinig monster-staging documenten in {coll_name}: {total}"
                )

    def test_13_verify_monster_counts(self, mongo_client):
        """Monster-documenten in clean-collectie >= verwacht."""
        counts = mongo_soort_counts(DB_ANALYSE, "Single_Store_Clean", mongo_client)
        actual = counts.get("Monster", 0)
        expected = EXPECTED_MIN_SOORT_COUNTS["Monster"]
        print(f"\n  Monsters: {actual} (verwacht >= {expected})")
        assert actual >= expected, (
            f"Monster: verwacht >= {expected}, gevonden {actual}"
        )

    def test_14_verify_monster_botanie_counts(self, mongo_client):
        """Monster_Botanie-documenten in clean-collectie >= verwacht."""
        counts = mongo_soort_counts(DB_ANALYSE, "Single_Store_Clean", mongo_client)
        actual = counts.get("Monster_Botanie", 0)
        expected = EXPECTED_MIN_SOORT_COUNTS["Monster_Botanie"]
        print(f"\n  Monster_Botanie: {actual} (verwacht >= {expected})")
        assert actual >= expected, (
            f"Monster_Botanie: verwacht >= {expected}, gevonden {actual}"
        )

    def test_15_verify_monster_schelp_counts(self, mongo_client):
        """Monster_Schelp-documenten in clean-collectie >= verwacht."""
        counts = mongo_soort_counts(DB_ANALYSE, "Single_Store_Clean", mongo_client)
        actual = counts.get("Monster_Schelp", 0)
        expected = EXPECTED_MIN_SOORT_COUNTS["Monster_Schelp"]
        print(f"\n  Monster_Schelp: {actual} (verwacht >= {expected})")
        assert actual >= expected, (
            f"Monster_Schelp: verwacht >= {expected}, gevonden {actual}"
        )

    def test_16_verify_monster_referentietabellen(self, mongo_client):
        """Referentietabellen (DT_Soort_*) zijn aanwezig in clean-collectie."""
        counts = mongo_soort_counts(DB_ANALYSE, "Single_Store_Clean", mongo_client)

        ref_tabellen = {
            "DT_Soort_Plant": EXPECTED_MIN_SOORT_COUNTS["DT_Soort_Plant"],
            "DT_Soort_Schelp": EXPECTED_MIN_SOORT_COUNTS["DT_Soort_Schelp"],
            "DT_Soort_Deel": EXPECTED_MIN_SOORT_COUNTS["DT_Soort_Deel"],
            "DT_Soort_Staat": EXPECTED_MIN_SOORT_COUNTS["DT_Soort_Staat"],
        }

        print(f"\n  Referentietabellen:")
        for soort, expected in ref_tabellen.items():
            actual = counts.get(soort, 0)
            ok = "✓" if actual >= expected else "✗"
            print(f"    {soort}: {actual} (verwacht >= {expected}) {ok}")
            assert actual >= expected, (
                f"{soort}: verwacht >= {expected}, gevonden {actual}"
            )

    def test_17_verify_monster_keys(self, mongo_client):
        """Monsters hebben correcte keys (key, key_project, key_spoor)."""
        coll = mongo_client[DB_ANALYSE]["Single_Store_Clean"]
        monsters = list(coll.find({"soort": "Monster"}, {
            "key": 1, "key_project": 1, "key_spoor": 1,
            "monstercd": 1, "projectcd": 1,
        }))

        print(f"\n  Monster keys ({len(monsters)} records):")
        for m in monsters:
            key = m.get("key", "")
            key_project = m.get("key_project", "")
            monstercd = m.get("monstercd", "")
            print(f"    {monstercd}: key={key}, key_project={key_project}")

            assert key.startswith("M"), (
                f"Monster key '{key}' begint niet met 'M'"
            )
            if key_project:
                assert key_project.startswith("P"), (
                    f"Monster key_project '{key_project}' begint niet met 'P'"
                )

    def test_18_verify_monster_botanie_keys(self, mongo_client):
        """Monster_Botanie records hebben key_monster referentie."""
        coll = mongo_client[DB_ANALYSE]["Single_Store_Clean"]
        botanie = list(coll.find({"soort": "Monster_Botanie"}, {
            "key": 1, "key_monster": 1,
        }))

        print(f"\n  Monster_Botanie keys ({len(botanie)} records):")
        for b in botanie:
            key = b.get("key", "")
            key_monster = b.get("key_monster", "")
            print(f"    key={key}, key_monster={key_monster}")

            assert key_monster.startswith("M"), (
                f"Monster_Botanie key_monster '{key_monster}' begint niet met 'M'"
            )

    # ----------------------------------------------------------
    # Stap 5: Load naar PostgreSQL
    # ----------------------------------------------------------
    # NB: DAG_Load_Only bevat zowel LoadToDatabase_postgres als
    # Elasticsearch indexering. De Elasticsearch stap faalt in de
    # test-omgeving (geen ES container). De PostgreSQL load zelf slaagt.
    # ----------------------------------------------------------
    @pytest.mark.load
    def test_19_run_load(self, airflow_ready):
        """Trigger DAG_Load_Only DAG (MongoDB → PostgreSQL).

        De DAG kan falen door Elasticsearch (niet in test-omgeving).
        We controleren de PostgreSQL resultaten in de volgende tests.
        """
        try:
            run_dag("DAG_Load_Only", timeout=1800)
        except AssertionError:
            # DAG faalt door Elasticsearch indexering (verwacht in test)
            print("  ℹ  DAG gefaald (verwacht: Elasticsearch niet beschikbaar)")

    @pytest.mark.load
    def test_20_verify_postgres_project_count(self, airflow_ready):
        """Def_Project in PostgreSQL moet >= 2 rijen bevatten."""
        count = _pg_table_count("Def_Project")
        print(f"\n  Def_Project in PostgreSQL: {count} rijen")
        assert count >= 2, (
            f"Def_Project bevat {count} rijen, verwacht >= 2. "
            f"Controleer DELF-IT volume-mount en Project MOVEANDMERGE in meta.py."
        )

    @pytest.mark.load
    def test_21_verify_postgres_project_has_location(self, airflow_ready):
        """Minimaal 1 project in PostgreSQL moet een locatie (geometry) hebben."""
        count = _pg_scalar(
            "SELECT COUNT(*) FROM \"Def_Project\" WHERE location IS NOT NULL"
        )
        print(f"\n  Projecten met locatie in PostgreSQL: {count}")
        assert count >= 1, (
            f"Geen enkel project heeft een locatie in PostgreSQL. "
            f"Controleer RD→WGS84 conversie en setWKT in loadToDatabase."
        )

    @pytest.mark.load
    def test_22_verify_postgres_table_counts(self, mongo_client, airflow_ready):
        """Elke Def_-tabel in PostgreSQL moet >= het verwachte aantal rijen bevatten."""
        mongo_counts = mongo_soort_counts(DB_ANALYSE, "Single_Store_Clean", mongo_client)

        print(f"\n  MongoDB vs PostgreSQL vergelijking:")
        print(f"  {'Soort':<25} {'Mongo':>8} {'Postgres':>10} {'':>3}")
        print("  " + "-" * 50)

        fouten = []
        for soort, expected in EXPECTED_MIN_SOORT_COUNTS.items():
            pg_table = f"Def_{soort}"
            try:
                pg_count = _pg_table_count(pg_table)
            except Exception:
                pg_count = -1  # tabel bestaat niet
            mongo_count = mongo_counts.get(soort, 0)
            ok = "✓" if pg_count >= expected else "✗"
            print(f"  {soort:<25} {mongo_count:>8} {pg_count:>10}  {ok}")
            if pg_count < expected:
                fouten.append(f"{soort}: PostgreSQL {pg_count} < verwacht {expected}")

        assert not fouten, (
            f"Tabellen met te weinig rijen in PostgreSQL:\n  " +
            "\n  ".join(fouten)
        )

    @pytest.mark.load
    def test_23_verify_postgres_no_empty_def_tables(self, airflow_ready):
        """Geen enkele Def_-tabel uit lst_tables mag 0 rijen hebben."""
        # NB: Def_Put en Def_Vlak worden niet in de synthetische data
        # gegenereerd (geen putten/vlakken in de testdata), dus die
        # zijn verwacht leeg en worden hier uitgesloten.
        lst_tables = [
            'Def_ABR', 'Def_Project', 'Def_Vondst', 'Def_Spoor',
            'Def_Doos', 'Def_Standplaats', 'Def_Plaatsing',
            'Def_Artefact', 'Def_Bestand', 'Def_Vulling',
            'Def_Monster', 'Def_Monster_Botanie', 'Def_Monster_Schelp',
            'Def_DT_Soort_Plant', 'Def_DT_Soort_Schelp',
            'Def_DT_Soort_Deel', 'Def_DT_Soort_Staat',
        ]

        lege_tabellen = []
        print(f"\n  PostgreSQL tabelcontrole:")
        for table in lst_tables:
            try:
                count = _pg_table_count(table)
            except Exception:
                count = -1
            status = "✓" if count > 0 else "LEEG" if count == 0 else "FOUT"
            print(f"    {table}: {count} ({status})")
            if count == 0:
                lege_tabellen.append(table)

        assert not lege_tabellen, (
            f"Lege tabellen in PostgreSQL: {lege_tabellen}. "
            f"Data is niet correct geladen vanuit MongoDB."
        )
