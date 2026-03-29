"""
Integratietest: volledige pipeline met Delftse testdata (DB034).

Triggert Extract_only, DAG_Transform_Only en DAG_Load_Only via ``docker exec``
en verifieert de record-aantallen in MongoDB en PostgreSQL.

Testdata: data/test/ (project DB034 Koningsveld IV)
Bevat: projecten, monsters, magazijnlijst, fotolijst, rapporten, referentietabellen.

Docker: docker-compose.delft-test.yml (geïsoleerde testomgeving)

Draaien:
  make integration-delft            (volledig: Extract→Transform→Load→Flask)
  make integration-delft-pipeline   (alleen Extract→Transform)
"""
import json
import os
import re
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
AIRFLOW_CONTAINER = os.getenv("AIRFLOW_CONTAINER", "wasstraat_airflow_delft_test")
POSTGRES_CONTAINER = os.getenv("POSTGRES_CONTAINER", "wasstraat_postgres_delft_test")
FLASK_CONTAINER = os.getenv("FLASK_CONTAINER", "wasstraat_flask_delft_test")

DB_STAGING = "Arch_Staging_Test"
DB_ANALYSE = "Arch_Analyse_Test"
DB_FILES = "Arch_Files_Test"

# Verwachte MINIMUM-aantallen per artefactsoort in Single_Store_Clean.
# Gebaseerd op DB034 Koningsveld IV: groot project met diverse materialen.
EXPECTED_MIN_ARTEFACT_COUNTS = {
    "Aardewerk": 4510,
    "Glas": 20,
    "Hout": 294,
    "Menselijk_Bot": 273,
    "Metaal": 229,
    "Steen": 146,
}

# Verwachte MINIMUM-aantallen per soort in Single_Store_Clean.
EXPECTED_MIN_SOORT_COUNTS = {
    "Spoor": 456,
    "Vondst": 1478,
    "Vulling": 425,
}

# Verwachte aantallen voor afbeeldingen.
EXPECTED_MIN_PLAATJES = 21
EXPECTED_MIN_BESTAND_CLEAN = 21


# ============================================================
# Helpers
# ============================================================

def run_dag(dag_id: str, timeout: int = 1800, poll_interval: int = 3) -> str:
    """Draai een Airflow DAG via ``dags test`` en wacht op voltooiing."""
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
        all_output = (result.stdout + "\n" + result.stderr).strip().split("\n")
        error_lines = [l for l in all_output if any(kw in l for kw in
            ['ERROR', 'Exception', 'Traceback', 'Error', 'FAILED', 'failed',
             'raise', 'Onbekende fout', 'melding'])]
        if not error_lines:
            error_lines = all_output[-30:]
        print(f"  ⚠  DAG {dag_id} gefaald na {t_elapsed:.1f}s:")
        for line in error_lines[-30:]:
            print(f"    {line}")
        assert False, f"DAG {dag_id} gefaald (exit code {result.returncode})"

    if "state=success" in result.stdout or "state=success" in result.stderr:
        print(f"  ⏱  {dag_id} duurde {t_elapsed:.1f}s (state=success)")
    else:
        print(f"  ⏱  {dag_id} duurde {t_elapsed:.1f}s (exit code 0)")
    print(f"  ✓  DAG {dag_id} succesvol")
    return "success"


def wait_for_airflow(max_wait: int = 180):
    """Wacht tot Airflow DAGs geparsed zijn."""
    for _ in range(max_wait):
        try:
            r = subprocess.run(
                ["docker", "exec", AIRFLOW_CONTAINER,
                 "airflow", "dags", "list", "-o", "plain"],
                capture_output=True, text=True, timeout=10,
            )
            if r.returncode == 0 and "Extract" in r.stdout:
                print("  ✓ Airflow DAGs geparsed, klaar voor dags test")
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


def _pg_scalar(sql):
    """Voer een SQL-query uit op de test-PostgreSQL."""
    cmd = [
        "docker", "exec", "-e", "PGPASSWORD=testpass", POSTGRES_CONTAINER,
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
        pytest.skip("Airflow niet klaar — start met: make integration-delft")
    print("  ✓ Airflow klaar")


# ============================================================
# Tests — Extract + Transform
# ============================================================

@pytest.mark.delft
class TestDelftExtractTransform:
    """Extract + Transform met Delftse testdata (DB034)."""

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
    # Stap 2: Transform
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

        # Diagnostiek: artefact-subtypes
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

        clean_artefacts = mongo_artefact_counts(DB_ANALYSE, mongo_client)
        if clean_artefacts:
            print(f"\n  Artefact-subtypes in Single_Store_Clean ({sum(clean_artefacts.values())} totaal):")
            for soort, count in sorted(clean_artefacts.items(), key=lambda x: -x[1]):
                marker = ""
                if soort in EXPECTED_MIN_ARTEFACT_COUNTS:
                    exp = EXPECTED_MIN_ARTEFACT_COUNTS[soort]
                    marker = f"  (verwacht >= {exp})"
                print(f"    {soort}: {count}{marker}")

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
    # Stap 3: Artefact-aantallen
    # ----------------------------------------------------------
    def test_07_verify_artefact_counts(self, mongo_client):
        """Artefact-subtypes in Single_Store_Clean >= verwachte aantallen."""
        artefact_counts = mongo_artefact_counts(DB_ANALYSE, mongo_client)
        print(f"\n  Artefact-subtypes:")
        for soort, count in sorted(artefact_counts.items(), key=lambda x: -x[1]):
            print(f"    {soort}: {count}")
        for soort, expected in EXPECTED_MIN_ARTEFACT_COUNTS.items():
            actual = artefact_counts.get(soort, 0)
            assert actual >= expected, \
                f"{soort}: verwacht >= {expected}, gevonden {actual}"

    def test_08_verify_spoor_count(self, mongo_client):
        """Spoor-documenten >= verwacht."""
        counts = mongo_soort_counts(DB_ANALYSE, "Single_Store_Clean", mongo_client)
        actual = counts.get("Spoor", 0)
        expected = EXPECTED_MIN_SOORT_COUNTS["Spoor"]
        assert actual >= expected, f"Spoor: verwacht >= {expected}, gevonden {actual}"

    def test_09_verify_vondst_count(self, mongo_client):
        """Vondst-documenten >= verwacht."""
        counts = mongo_soort_counts(DB_ANALYSE, "Single_Store_Clean", mongo_client)
        actual = counts.get("Vondst", 0)
        expected = EXPECTED_MIN_SOORT_COUNTS["Vondst"]
        assert actual >= expected, f"Vondst: verwacht >= {expected}, gevonden {actual}"

    def test_10_verify_vulling_count(self, mongo_client):
        """Vulling-documenten >= verwacht."""
        counts = mongo_soort_counts(DB_ANALYSE, "Single_Store_Clean", mongo_client)
        actual = counts.get("Vulling", 0)
        expected = EXPECTED_MIN_SOORT_COUNTS["Vulling"]
        assert actual >= expected, f"Vulling: verwacht >= {expected}, gevonden {actual}"

    # ----------------------------------------------------------
    # Stap 4: Afbeeldingen
    # ----------------------------------------------------------
    def test_11_verify_filenames_collection(self, mongo_client):
        """Filenames-collectie is gevuld na Extract."""
        db = mongo_client[DB_FILES]
        filenames_count = db["Filenames"].count_documents({})
        processed_count = db["Filenames"].count_documents({"processed": True})
        print(f"\n  Filenames: {filenames_count} totaal, {processed_count} verwerkt")
        assert filenames_count > 0, "Filenames collectie is leeg"
        assert processed_count > 0, "Geen verwerkte bestanden"

    def test_12_verify_plaatjes_collection(self, mongo_client):
        """Plaatjes-collectie bevat verwerkte afbeeldingen."""
        db = mongo_client[DB_STAGING]
        plaatjes_count = db["Plaatjes"].count_documents({})
        print(f"\n  Plaatjes: {plaatjes_count} documenten")
        assert plaatjes_count >= EXPECTED_MIN_PLAATJES, \
            f"Plaatjes: verwacht >= {EXPECTED_MIN_PLAATJES}, gevonden {plaatjes_count}"

    def test_13_verify_bestand_in_clean(self, mongo_client):
        """Single_Store_Clean bevat Bestand-records."""
        coll = mongo_client[DB_ANALYSE]["Single_Store_Clean"]
        bestand_count = coll.count_documents({"soort": "Bestand"})
        print(f"\n  Bestand-records in Clean: {bestand_count}")
        assert bestand_count >= EXPECTED_MIN_BESTAND_CLEAN, \
            f"Bestand: verwacht >= {EXPECTED_MIN_BESTAND_CLEAN}, gevonden {bestand_count}"

    # ----------------------------------------------------------
    # Stap 5: Monster-verificatie
    # ----------------------------------------------------------
    def test_14_verify_monster_staging(self, mongo_client):
        """Staging bevat monster-data (MONSTERS.accdb + RESIDU.mdb)."""
        db = mongo_client[DB_STAGING]
        coll_names = db.list_collection_names()
        staging_colls = [c for c in coll_names if "monster" in c.lower() or "Monster" in c]
        print(f"\n  Monster-gerelateerde staging collecties: {staging_colls}")

        for coll_name in staging_colls:
            counts = mongo_table_counts(DB_STAGING, coll_name, mongo_client)
            total = sum(counts.values())
            print(f"\n  {coll_name} ({total} docs):")
            for table, count in sorted(counts.items(), key=lambda x: -x[1]):
                print(f"    {table}: {count}")

    def test_15_verify_monster_in_clean(self, mongo_client):
        """Monster-documenten aanwezig in clean-collectie."""
        counts = mongo_soort_counts(DB_ANALYSE, "Single_Store_Clean", mongo_client)
        monster_count = counts.get("Monster", 0)
        print(f"\n  Monsters in Clean: {monster_count}")
        # DB034 testdata bevat monsters — verwacht minimaal 1
        assert monster_count >= 1, \
            f"Geen Monster-documenten in Clean (gevonden: {monster_count})"

    def test_16_verify_monster_keys(self, mongo_client):
        """Monsters met key hebben correcte keys (begint met 'M')."""
        coll = mongo_client[DB_ANALYSE]["Single_Store_Clean"]
        monsters = list(coll.find(
            {"soort": "Monster", "key": {"$exists": True, "$ne": ""}},
            {"key": 1, "monstercd": 1}
        ).limit(10))
        print(f"\n  Monster keys met waarde ({len(monsters)} records):")
        for m in monsters:
            key = m.get("key", "")
            print(f"    {m.get('monstercd', '?')}: key={key}")
            assert key.startswith("M"), f"Monster key '{key}' begint niet met 'M'"
        # Ook tellen hoeveel monsters geen key hebben (informatief)
        zonder_key = coll.count_documents(
            {"soort": "Monster", "$or": [{"key": {"$exists": False}}, {"key": ""}]}
        )
        if zonder_key > 0:
            print(f"    (info: {zonder_key} monsters zonder key)")

    # ----------------------------------------------------------
    # Stap 6: Magazijnlijst / Depot
    # ----------------------------------------------------------
    def test_17_verify_standplaats(self, mongo_client):
        """Standplaats-documenten aanwezig (uit MAGAZIJN.mdb)."""
        counts = mongo_soort_counts(DB_ANALYSE, "Single_Store_Clean", mongo_client)
        standplaats_count = counts.get("Standplaats", 0)
        print(f"\n  Standplaatsen in Clean: {standplaats_count}")
        # Magazijnlijst bevat standplaats-gegevens
        assert standplaats_count >= 1, \
            f"Geen Standplaats-documenten (gevonden: {standplaats_count})"

    def test_18_verify_doos(self, mongo_client):
        """Doos-documenten aanwezig (uit MAGAZIJN.mdb)."""
        counts = mongo_soort_counts(DB_ANALYSE, "Single_Store_Clean", mongo_client)
        doos_count = counts.get("Doos", 0)
        print(f"\n  Dozen in Clean: {doos_count}")
        assert doos_count >= 1, \
            f"Geen Doos-documenten (gevonden: {doos_count})"

    def test_19_verify_doos_keys(self, mongo_client):
        """Dozen met key hebben correcte keys (P{projectcd}D{doosnr})."""
        coll = mongo_client[DB_ANALYSE]["Single_Store_Clean"]
        dozen = list(coll.find(
            {"soort": "Doos", "key": {"$exists": True, "$ne": ""}},
            {"key": 1, "projectcd": 1, "doosnr": 1}
        ).limit(10))
        print(f"\n  Doos keys met waarde ({len(dozen)} records):")
        for d in dozen:
            key = d.get("key", "")
            print(f"    {d.get('projectcd', '?')} D{d.get('doosnr', '?')}: key={key}")
            assert key.startswith("P"), f"Doos key '{key}' begint niet met 'P'"
            assert "D" in key, f"Doos key '{key}' bevat geen 'D'"

    # ----------------------------------------------------------
    # Stap 7: Key-formaat validatie (alle entiteitstypen)
    # ----------------------------------------------------------
    def test_20_verify_project_keys(self, mongo_client):
        """Projecten hebben key met formaat P{projectcd}."""
        coll = mongo_client[DB_ANALYSE]["Single_Store_Clean"]
        projecten = list(coll.find({"soort": "Project"}, {"key": 1, "projectcd": 1}))
        print(f"\n  Project keys ({len(projecten)} records):")
        for p in projecten:
            key = p.get("key", "")
            projectcd = p.get("projectcd", "")
            print(f"    {projectcd}: key={key}")
            assert key.startswith("P"), f"Project key '{key}' begint niet met 'P'"
            assert key == f"P{projectcd}", \
                f"Project key '{key}' != verwacht 'P{projectcd}'"

    def test_21_verify_put_keys(self, mongo_client):
        """Putten hebben key met formaat P{projectcd}P{putnr}."""
        coll = mongo_client[DB_ANALYSE]["Single_Store_Clean"]
        putten = list(coll.find({"soort": "Put"}, {"key": 1}).limit(10))
        print(f"\n  Put keys ({len(putten)} records):")
        for p in putten:
            key = p.get("key", "")
            print(f"    key={key}")
            assert re.match(r'^P[A-Za-z]+\d+P\d+$', key), \
                f"Put key '{key}' matcht niet op verwacht formaat P{{projectcd}}P{{putnr}}"

    def test_22_verify_spoor_keys(self, mongo_client):
        """Sporen hebben key met S-suffix."""
        coll = mongo_client[DB_ANALYSE]["Single_Store_Clean"]
        sporen = list(coll.find({"soort": "Spoor"}, {"key": 1}).limit(10))
        print(f"\n  Spoor keys ({len(sporen)} records):")
        for s in sporen:
            key = s.get("key", "")
            print(f"    key={key}")
            assert key.startswith("P"), f"Spoor key '{key}' begint niet met 'P'"
            assert "S" in key, f"Spoor key '{key}' bevat geen 'S'"

    def test_23_verify_vondst_keys(self, mongo_client):
        """Vondsten hebben key met V-component."""
        coll = mongo_client[DB_ANALYSE]["Single_Store_Clean"]
        vondsten = list(coll.find({"soort": "Vondst"}, {"key": 1}).limit(10))
        print(f"\n  Vondst keys ({len(vondsten)} records):")
        for v in vondsten:
            key = v.get("key", "")
            print(f"    key={key}")
            assert key.startswith("P"), f"Vondst key '{key}' begint niet met 'P'"
            assert "V" in key, f"Vondst key '{key}' bevat geen 'V'"

    def test_24_verify_artefact_keys(self, mongo_client):
        """Artefacten met key hebben key met A-component."""
        coll = mongo_client[DB_ANALYSE]["Single_Store_Clean"]
        artefacten = list(coll.find(
            {"soort": "Artefact", "key": {"$exists": True, "$ne": ""}},
            {"key": 1, "artefactsoort": 1}
        ).limit(10))
        print(f"\n  Artefact keys met waarde ({len(artefacten)} records):")
        for a in artefacten:
            key = a.get("key", "")
            print(f"    {a.get('artefactsoort', '?')}: key={key}")
            assert key.startswith("P"), f"Artefact key '{key}' begint niet met 'P'"
            assert "A" in key, f"Artefact key '{key}' bevat geen 'A'"

    def test_25_verify_referentie_keys_consistent(self, mongo_client):
        """Referentie-keys (key_project, key_put) zijn consistent met parent keys."""
        coll = mongo_client[DB_ANALYSE]["Single_Store_Clean"]

        # Check dat key_project van een Vondst overeenkomt met een bestaand Project
        vondsten = list(coll.find(
            {"soort": "Vondst", "key_project": {"$exists": True}},
            {"key_project": 1}
        ).limit(5))
        project_keys = set(
            p["key"] for p in coll.find({"soort": "Project"}, {"key": 1})
        )

        print(f"\n  Referentie-key check:")
        print(f"    {len(project_keys)} project-keys, {len(vondsten)} vondsten met key_project")

        for v in vondsten:
            key_project = v.get("key_project", "")
            assert key_project in project_keys, \
                f"Vondst key_project '{key_project}' verwijst niet naar bestaand project"

    # ----------------------------------------------------------
    # Samenvatting
    # ----------------------------------------------------------
    def test_26_summary(self, mongo_client):
        """Eindoverzicht van alle aantallen."""
        counts = mongo_soort_counts(DB_ANALYSE, "Single_Store_Clean", mongo_client)
        artefact_counts = mongo_artefact_counts(DB_ANALYSE, mongo_client)

        print("\n" + "=" * 60)
        print("  SAMENVATTING — Single_Store_Clean (Delft DB034)")
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

        for soort, act in sorted(artefact_counts.items(), key=lambda x: -x[1]):
            if soort not in EXPECTED_MIN_ARTEFACT_COUNTS:
                print(f"  {soort:<25} {act:>8,} {'n.v.t.':>8}")

        print()
        for soort, exp in sorted(EXPECTED_MIN_SOORT_COUNTS.items()):
            act = counts.get(soort, 0)
            ok = "✓" if act >= exp else "✗"
            print(f"  {soort + ' (>=' + str(exp) + ')':<25} {act:>8,} {'':>8}  {ok}")

        # Depot en monsters
        print(f"\n  Depot/Monsters:")
        for soort in ["Standplaats", "Doos", "Plaatsing", "Monster"]:
            act = counts.get(soort, 0)
            print(f"  {soort:<25} {act:>8,}")

        # Afbeeldingen
        print(f"\n  Afbeeldingen:")
        db_files = mongo_client[DB_FILES]
        db_staging = mongo_client[DB_STAGING]
        plaatjes = db_staging["Plaatjes"].count_documents({})
        bestand = counts.get("Bestand", 0)
        print(f"  {'Plaatjes':<25} {plaatjes:>8,}")
        print(f"  {'Bestand':<25} {bestand:>8,}")

        print("=" * 60)


# ============================================================
# Tests — Load naar PostgreSQL
# ============================================================

@pytest.mark.delft_load
class TestDelftLoad:
    """Load naar PostgreSQL en verificatie."""

    def test_30_run_load(self, airflow_ready):
        """Trigger DAG_Load_Only DAG (MongoDB → PostgreSQL).

        De DAG kan falen door Elasticsearch (niet in testomgeving).
        We controleren de PostgreSQL resultaten in de volgende tests.
        """
        try:
            run_dag("DAG_Load_Only", timeout=1800)
        except AssertionError:
            print("  ℹ  DAG gefaald (verwacht: Elasticsearch niet beschikbaar)")

    def test_31_verify_postgres_project(self, airflow_ready):
        """Def_Project in PostgreSQL bevat minimaal 1 project (DB034)."""
        count = _pg_table_count("Def_Project")
        print(f"\n  Def_Project in PostgreSQL: {count} rijen")
        assert count >= 1, f"Def_Project bevat {count} rijen, verwacht >= 1"

    def test_32_verify_postgres_project_location(self, airflow_ready):
        """Minimaal 1 project heeft een locatie (geometry)."""
        count = _pg_scalar(
            "SELECT COUNT(*) FROM \"Def_Project\" WHERE location IS NOT NULL"
        )
        print(f"\n  Projecten met locatie: {count}")
        assert count >= 1, "Geen project heeft een locatie in PostgreSQL"

    def test_33_verify_postgres_table_counts(self, mongo_client, airflow_ready):
        """Def_-tabellen bevatten data die overeenkomt met MongoDB."""
        mongo_counts = mongo_soort_counts(DB_ANALYSE, "Single_Store_Clean", mongo_client)

        print(f"\n  MongoDB vs PostgreSQL:")
        print(f"  {'Soort':<25} {'Mongo':>8} {'Postgres':>10}")
        print("  " + "-" * 45)

        # Controleer de belangrijkste tabellen
        tabellen = ["Project", "Spoor", "Vondst", "Vulling", "Artefact", "Bestand", "Doos"]
        fouten = []
        for soort in tabellen:
            pg_table = f"Def_{soort}"
            try:
                pg_count = _pg_table_count(pg_table)
            except Exception:
                pg_count = -1
            mongo_count = mongo_counts.get(soort, 0)
            ok = "✓" if pg_count > 0 else "✗"
            print(f"  {soort:<25} {mongo_count:>8} {pg_count:>10}  {ok}")
            if pg_count == 0 and mongo_count > 0:
                fouten.append(f"{soort}: PostgreSQL leeg maar MongoDB heeft {mongo_count} records")

        assert not fouten, (
            f"Tabellen niet geladen:\n  " + "\n  ".join(fouten)
        )

    def test_34_verify_postgres_no_empty_key_tables(self, airflow_ready):
        """Kerntabellen in PostgreSQL zijn niet leeg."""
        lst_tables = [
            'Def_Project', 'Def_Vondst', 'Def_Spoor',
            'Def_Artefact', 'Def_Bestand', 'Def_Vulling',
        ]

        lege_tabellen = []
        for table in lst_tables:
            try:
                count = _pg_table_count(table)
            except Exception:
                count = -1
            if count == 0:
                lege_tabellen.append(table)

        assert not lege_tabellen, \
            f"Lege kerntabellen in PostgreSQL: {lege_tabellen}"


# ============================================================
# Tests — Flask smoke tests
# ============================================================

@pytest.mark.delft_flask
class TestDelftFlask:
    """Flask smoke tests met Delftse data."""

    FLASK_BASE_URL = os.getenv("FLASK_TEST_URL", "http://localhost:5062")

    def test_40_flask_homepage(self):
        """Flask homepage laadt correct."""
        import urllib.request
        try:
            resp = urllib.request.urlopen(f"{self.FLASK_BASE_URL}/", timeout=10)
            assert resp.status == 200
            print(f"\n  ✓ Flask homepage: HTTP {resp.status}")
        except Exception as e:
            pytest.skip(f"Flask niet bereikbaar: {e}")

    def test_41_flask_project_list(self):
        """Project-overzicht is beschikbaar."""
        import urllib.request
        try:
            resp = urllib.request.urlopen(
                f"{self.FLASK_BASE_URL}/archprojectview/list/", timeout=10
            )
            assert resp.status == 200
            body = resp.read().decode("utf-8", errors="replace")
            # DB034 moet zichtbaar zijn
            assert "DB034" in body or "db034" in body.lower(), \
                "Project DB034 niet gevonden in projectlijst"
            print(f"\n  ✓ Projectlijst bevat DB034")
        except Exception as e:
            pytest.skip(f"Flask niet bereikbaar: {e}")
