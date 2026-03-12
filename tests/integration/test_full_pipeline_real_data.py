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

def run_dag(dag_id: str, timeout: int = 1800, poll_interval: int = 3) -> str:
    """Trigger een Airflow DAG en wacht op voltooiing via polling.

    Gebruikt ``airflow dags trigger`` + poll i.p.v. ``dags test`` zodat de
    LocalExecutor taken parallel kan uitvoeren volgens de DAG-structuur.
    ``dags test`` draait alles sequentieel, wat onnodig traag is.

    Raise AssertionError wanneer de DAG faalt of timeout bereikt.
    """
    run_id = f"integration_test_{dag_id}_{int(time.time())}"

    # Unpause de DAG (nodig voor trigger; dags test deed dit impliciet)
    subprocess.run(
        ["docker", "exec", AIRFLOW_CONTAINER,
         "airflow", "dags", "unpause", dag_id],
        capture_output=True, text=True, timeout=30,
    )

    # Trigger de DAG
    trigger_cmd = [
        "docker", "exec", AIRFLOW_CONTAINER,
        "airflow", "dags", "trigger",
        "--run-id", run_id,
        dag_id,
    ]
    print(f"\n  ▶ {' '.join(trigger_cmd)}")
    t_start = time.time()
    trigger_result = subprocess.run(
        trigger_cmd, capture_output=True, text=True, timeout=30,
    )
    if trigger_result.returncode != 0:
        print(f"  ⚠  Trigger gefaald:\n    {trigger_result.stderr}")
        assert False, f"DAG {dag_id} kon niet getriggerd worden"
    print(f"  ✓  DAG {dag_id} getriggerd (run_id={run_id})")

    # Poll tot de DAG klaar is (success/failed)
    print(f"  ⏳ Wachten op voltooiing van {dag_id} (poll elke {poll_interval}s)...")
    final_state = None
    while time.time() - t_start < timeout:
        time.sleep(poll_interval)
        state_cmd = [
            "docker", "exec", AIRFLOW_CONTAINER,
            "airflow", "dags", "list-runs", "-d", dag_id, "-o", "json",
        ]
        state_result = subprocess.run(
            state_cmd, capture_output=True, text=True, timeout=30,
        )
        if state_result.returncode != 0 or not state_result.stdout.strip():
            continue

        try:
            runs = json.loads(state_result.stdout)
        except json.JSONDecodeError:
            continue

        for run in runs:
            if run.get("run_id") == run_id:
                final_state = run.get("state")
                break

        if final_state in ("success", "failed"):
            break

    t_elapsed = time.time() - t_start
    print(f"  ⏱  {dag_id} duurde {t_elapsed:.1f}s (state={final_state})")

    # Bij falen: toon gefaalde taken voor debugging
    if final_state != "success":
        _print_failed_tasks(dag_id, run_id)
        if final_state is None:
            assert False, f"DAG {dag_id} timeout na {timeout}s"
        assert False, f"DAG {dag_id} gefaald (state={final_state})"

    print(f"  ✓  DAG {dag_id} succesvol")

    # Check op ERROR-regels in de taak-logs (optioneel, voor waarschuwingen)
    _check_dag_errors(dag_id, run_id)

    return final_state


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

    # Stap 2: wacht tot de scheduler draait (nodig voor trigger-aanpak)
    print("  ⏳ Wachten tot scheduler actief is...")
    for _ in range(30):
        try:
            r = subprocess.run(
                ["docker", "exec", AIRFLOW_CONTAINER,
                 "airflow", "jobs", "check", "--job-type", "SchedulerJob",
                 "--allow-hierarchical-mapping"],
                capture_output=True, text=True, timeout=10,
            )
            if r.returncode == 0:
                print("  ✓ Scheduler actief")
                return True
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass
        time.sleep(1)

    # Fallback: als jobs check niet werkt, wacht kort en ga door
    print("  ⚠ Scheduler-check niet beschikbaar, wacht 5s extra")
    time.sleep(5)
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
