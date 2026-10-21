"""
Integratietest: draai Extract + Transform met synthetische data (SY001 + SY002).

Triggert Extract_only en DAG_Transform_Only via ``docker exec`` en
verifieert daarna de record-aantallen in de drie MongoDB databases:
  - Arch_Staging_Test  (extract-resultaat)
  - Arch_Analyse_Test  (Single_Store + Single_Store_Clean)

Daarna DAG_Load_Only (marker load) met verificatie in PostgreSQL.
Afbeeldingen: na Extract_only heeft geen enkel bestand in Filenames de status
mislukt of onverwerkt en is de controletaak Controleer_Afbeeldingen geslaagd
(issue 70); de synthetische objectfoto's van SY002 moeten na Transform 4
aan hun artefact en vondst gekoppeld zijn (artefactID, vondstID), ook in Def_Bestand.

Draaien:
  make integration
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
AIRFLOW_CONTAINER = os.getenv("AIRFLOW_CONTAINER", "wasstraat_airflow_test")
POSTGRES_CONTAINER = os.getenv("POSTGRES_CONTAINER", "wasstraat_postgres_test")

DB_STAGING = "Arch_Staging_Test"
DB_ANALYSE = "Arch_Analyse_Test"
DB_FILES = "Arch_Files_Test"

# Verwachte MINIMUM-aantallen per artefactsoort in Single_Store_Clean.
# Gebaseerd op synthetische data: SY001 (3 aw, 2 glas) + SY002 (8 aw, 3 glas,
# 2 bot, 2 metaal, 1 steen, 2 kleipijp, 1 leer, 1 munt).
# Munt: de tabel MUNTEN EN PENNINGEN heeft kolomnamen met een komma; sinds
# importMDB.sh de kopregel zelf gequote schrijft, wordt de munt correct
# geïmporteerd en geharmoniseerd (daarvoor verschoven de velden en was dit 0).
EXPECTED_MIN_ARTEFACT_COUNTS = {
    "Aardewerk": 11,
    "Glas": 5,
    "Dierlijk_Bot": 2,
    "Metaal": 2,
    "Steen": 1,
    "Kleipijp": 2,
    "Leer": 1,
    "Munt": 1,
}

# Verwachte MINIMUM-aantallen per soort in Single_Store_Clean.
# Projecten: 2 (SY001 + SY002)
# SY001: 2 putten, 2 vlakken, 3 sporen, 4 vondsten, 2 vullingen
# SY002: 4 putten, 8 vlakken, 8 sporen, 12 vondsten, 4 vullingen
# Monsters: 6 (3x SY001 + 2x SY002 + 1x SYNTFOUT, gecorrigeerd naar SY001), 8 botanie, 4 schelp
# Putten en vlakken hebben geen eigen tabel in de MDB's; Transform5 genereert
# ze uit de putnr/vlaknr van sporen, vondsten, tekeningen en foto's.
EXPECTED_MIN_SOORT_COUNTS = {
    "Project": 2,
    "Put": 6,
    "Vlak": 10,
    "Spoor": 11,
    "Vondst": 16,
    "Vulling": 6,
    "Monster": 6,
    "Monster_Botanie": 8,
    "Monster_Schelp": 4,
    "DT_Soort_Plant": 5,
    "DT_Soort_Schelp": 3,
    "DT_Soort_Deel": 4,
    "DT_Soort_Staat": 4,
}

# Verwachte putnummers en (putnr, vlaknr)-combinaties per project.
EXPECTED_PUTTEN = {
    "SY001": {1, 2},
    "SY002": {1, 2, 3, 4},
}
EXPECTED_VLAKKEN = {
    "SY001": {(1, 1), (2, 1)},
    "SY002": {(1, 1), (1, 2), (2, 1), (2, 2), (3, 1), (3, 2), (4, 1), (4, 3)},
}

# Objectfoto's in de synthetische data, in de Delftse naamconventie
# <project>_P<put>_H<vondst>_<subnr>_<fotonr> in een materiaalmap onder
# "L Fotos/H (Objectfoto's)". Transform 4 koppelt ze via key_foto1
# (projectcd + artefactsoort + putnr + vondstnr + subnr) aan precies één
# artefact van SY002 en via key_vondst aan de vondst.
EXPECTED_OBJECTFOTO_KOPPELING = {
    "SY002_P2_H4_1_1.jpg": {"artefactsoort": "Aardewerk", "putnr": 2, "vondstnr": 4, "subnr": 1},
    "SY002_P4_H11_1_1.jpg": {"artefactsoort": "Munt", "putnr": 4, "vondstnr": 11, "subnr": 1},
}


# Beschrijving (memo-veld) van spoor 4 van SY002, met een regeleinde (issue 74). In de MDB
# staat CR LF; mongoimport leest een CR LF binnen een gequote veld in als LF.
SPOOR4_BESCHRIJVING = "Gemetselde beerput, vierkant\nBinnenwerk met tonvormige bodem"

# Staging-collecties die importMDB.sh vult (met de kolommen table, projectcd, bron, loadtime en mdbfile)
STAGING_MDB_COLLECTIES = [
    "Staging_Projecten_Oud", "Staging_Projecten_Projectenlijst", "Staging_Projecten_Magazijnlijst",
    "Staging_Projecten_Fotolijst", "Staging_Projecten_Monster", "Staging_Rapporten",
]
EXTRA_KOLOMMEN = ["table", "projectcd", "bron", "loadtime", "mdbfile"]

# Controletaak van de extractie van afbeeldingen (issue 70) per DAG die afbeeldingen importeert
CONTROLETAAK_PER_DAG = {
    "Extract_only": "Extract_Group.Controleer_Afbeeldingen",
    "Extract_Transform_Load_Full_Cycle": "Extract_Group.Controleer_Afbeeldingen",
    "Extract_Transform_Load_Incremental": "Extract_Group.Controleer_Afbeeldingen",
    "Redo_Images": "Controleer_Afbeeldingen",
}

# Uitvoer van de laatste 'airflow dags test' per DAG (voor controles op afzonderlijke taken)
DAG_UITVOER = {}


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
    DAG_UITVOER[dag_id] = result.stdout + "\n" + result.stderr

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

    # 'airflow dags test' eindigt ook met exit code 0 als een taak faalt; de eindstatus
    # staat in de regel 'DagRun Finished: ... state=...'. Retourneer die, zodat een test
    # kan eisen dat alle taken slagen.
    eindstatus = re.findall(r"DagRun Finished: .*?state=(\w+)", result.stdout + "\n" + result.stderr)
    if eindstatus:
        print(f"  ⏱  {dag_id} duurde {t_elapsed:.1f}s (state={eindstatus[-1]})")
        return eindstatus[-1]

    # Fallback: als exit code 0 maar geen eindstatus → waarschuw maar ga door
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


def controleerToegevoegdeKolommen(client, db_name):
    """Controleer de kolommen die importMDB.sh aan elk staging-document toevoegt (issue 74).

    Elk document in de staging-collecties van importMDB.sh heeft een gevuld
    mdbfile (ook de extra projecten uit Excel), en geen ander tekstveld bevat
    de waarde van mdbfile of de kolomnamen ",table,projectcd,": dat gebeurde
    toen sed de kolommen per regel toevoegde en een tekstveld een regeleinde had.

    Returns:
        Lijst met beschrijvingen van de gevonden fouten (leeg als alles klopt)
    """
    db = client[db_name]
    fouten = []
    for naam in STAGING_MDB_COLLECTIES:
        if naam not in db.list_collection_names():
            continue
        for doc in db[naam].find({}):
            mdbfile = doc.get("mdbfile")
            if not isinstance(mdbfile, str) or not mdbfile:
                fouten.append(f"{naam} {doc['_id']}: mdbfile leeg of ontbreekt (table={doc.get('table')!r})")
                continue
            for veld, waarde in doc.items():
                if veld in EXTRA_KOLOMMEN or not isinstance(waarde, str):
                    continue
                if mdbfile in waarde or ",table,projectcd," in waarde:
                    fouten.append(f"{naam} {doc['_id']} ({doc.get('table')}): veld {veld!r} bevat de extra kolommen")
    return fouten


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


def _pg_tekst(sql):
    """Voer een SQL-query uit op de test-PostgreSQL en retourneer de eerste waarde als tekst ('' bij NULL)."""
    cmd = [
        "docker", "exec", "-e", "PGPASSWORD=testpass", POSTGRES_CONTAINER,
        "psql", "-U", "testuser", "-h", "localhost", "-d", "airflow_test",
        "-t", "-A", "-c", sql,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
    if result.returncode != 0:
        raise RuntimeError(f"psql fout: {result.stderr.strip()}")
    return result.stdout.strip()


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

    def test_01a_verify_afbeeldingen_status(self, mongo_client):
        """Na Extract_only is elk bestand in Filenames verwerkt of bewust overgeslagen (issue 70).

        Geen enkel bestand heeft de status mislukt (processed False met fout) of
        onverwerkt (processed False zonder fout), en de controletaak
        Extract_Group.Controleer_Afbeeldingen is geslaagd.
        """
        col = mongo_client[DB_FILES]["Filenames"]
        totaal = col.count_documents({})
        verwerkt = col.count_documents({"processed": True, "overgeslagen": {"$exists": False}})
        overgeslagen = col.count_documents({"processed": True, "overgeslagen": {"$exists": True}})
        mislukt = list(col.find({"processed": False, "fout": {"$exists": True}}, {"_id": 0, "filename": 1, "fout": 1}))
        onverwerkt = col.count_documents({"processed": False, "fout": {"$exists": False}})
        print(f"\n  Filenames: {totaal} totaal, {verwerkt} verwerkt, {overgeslagen} overgeslagen, "
              f"{len(mislukt)} mislukt, {onverwerkt} onverwerkt")
        assert totaal > 0, "Filenames is leeg"
        assert not mislukt, f"{len(mislukt)} bestanden mislukt: {mislukt[:5]}"
        assert onverwerkt == 0, f"{onverwerkt} bestanden niet verwerkt (processed False zonder fout)"
        assert verwerkt + overgeslagen == totaal
        assert col.count_documents({"processed": True, "verwerkt_op": {"$exists": False}}) == 0, \
            "Verwerkte of overgeslagen bestanden zonder verwerkt_op"

        uitvoer = DAG_UITVOER.get("Extract_only", "")
        assert re.search(r"Marking task as SUCCESS\. dag_id=Extract_only, task_id=Extract_Group\.Controleer_Afbeeldingen,",
                         uitvoer), "Taak Extract_Group.Controleer_Afbeeldingen niet geslaagd in Extract_only"
        assert f"Controle afbeeldingen: {totaal} bestanden, {verwerkt} verwerkt" in uitvoer

    def test_01b_verify_controletaak_in_dags(self, airflow_ready):
        """Elke DAG die afbeeldingen importeert controleert ze na alle import-taken en vóór de transformatie.

        Leest de DagBag in de Airflow-container. In de incrementele cyclus moet
        Markeer_Run_Mislukt stroomafwaarts van de controletaak liggen, zodat een
        mislukte controle de run op 'mislukt' zet.
        """
        script = (
            "import json\n"
            "from airflow.models import DagBag\n"
            "bag = DagBag(include_examples=False)\n"
            f"taken = {CONTROLETAAK_PER_DAG!r}\n"
            "uit = {}\n"
            "for dag_id, taak_id in taken.items():\n"
            "    dag = bag.get_dag(dag_id)\n"
            "    if dag is None or not dag.has_task(taak_id):\n"
            "        uit[dag_id] = None\n"
            "        continue\n"
            "    taak = dag.get_task(taak_id)\n"
            "    uit[dag_id] = {\n"
            "        'upstream': sorted(taak.upstream_task_ids),\n"
            "        'downstream': sorted(t.task_id for t in taak.get_flat_relatives(upstream=False)),\n"
            "        'imports': sorted(t for t in dag.task_ids if t.split('.')[-1].startswith('Extract_Data_From_Fotos_')),\n"
            "    }\n"
            "print('RESULTAAT:' + json.dumps(uit))\n"
        )
        result = subprocess.run(["docker", "exec", AIRFLOW_CONTAINER, "python", "-c", script],
                                capture_output=True, text=True, timeout=300)
        regels = [r for r in result.stdout.split("\n") if r.startswith("RESULTAAT:")]
        assert result.returncode == 0 and regels, f"DagBag niet gelezen: {result.stderr[-2000:]}"
        structuur = json.loads(regels[-1][len("RESULTAAT:"):])

        for dag_id, taak_id in CONTROLETAAK_PER_DAG.items():
            info = structuur.get(dag_id)
            assert info is not None, f"{dag_id}: taak {taak_id} ontbreekt"
            print(f"\n  {dag_id}: {taak_id} na {len(info['upstream'])} import-taken")
            assert info["imports"], f"{dag_id}: geen import-taken gevonden"
            assert info["upstream"] == info["imports"], (
                f"{dag_id}: {taak_id} moet direct na alle import-taken komen, upstream is {info['upstream']}")
        for dag_id in ["Extract_only", "Extract_Transform_Load_Full_Cycle", "Extract_Transform_Load_Incremental"]:
            assert "Extract_Group.last" in structuur[dag_id]["downstream"]
        for dag_id in ["Extract_Transform_Load_Full_Cycle", "Extract_Transform_Load_Incremental"]:
            assert any(t.startswith("Transform1_Harmonize_Group.") for t in structuur[dag_id]["downstream"]), (
                f"{dag_id}: de transformatie hangt niet af van de controle van de afbeeldingen")
        assert "Markeer_Run_Mislukt" in structuur["Extract_Transform_Load_Incremental"]["downstream"], (
            "Markeer_Run_Mislukt bewaakt Controleer_Afbeeldingen niet in de incrementele cyclus")

    def test_02_verify_staging(self, mongo_client):
        """Staging-collectie bevat geëxtraheerde tabellen uit de MDB."""
        print_all_collections(mongo_client, DB_STAGING, "Na Extract:")
        counts = mongo_table_counts(DB_STAGING, "Staging_Projecten_Oud", mongo_client)
        total = sum(counts.values())
        print(f"\n  Staging-tabellen ({len(counts)}, totaal {total} docs):")
        for table, count in sorted(counts.items(), key=lambda x: -x[1]):
            print(f"    {table}: {count}")
        assert total > 10, f"Te weinig staging-documenten: {total}"

    def test_02a_verify_tekstveld_met_regeleinde(self, mongo_client):
        """Een tekstveld met een regeleinde komt als één veld in de staging, met de extra kolommen erachter (issue 74).

        Spoor 4 van SY002 heeft een beschrijving (memo-veld) met een regeleinde
        (CR LF); de CSV-export beslaat voor dat record twee regels. Tot issue 74
        zette sed de waarden van table, projectcd, bron, loadtime en mdbfile
        achter elke regel, dus ook midden in de beschrijving.
        """
        coll = mongo_client[DB_STAGING]["Staging_Projecten_Oud"]
        docs = list(coll.find({"table": "SPOREN", "projectcd": "SY002", "SPOORNO": 4}))
        assert len(docs) == 1, f"Verwacht één staging-document voor spoor 4 van SY002, gevonden {len(docs)}"
        doc = docs[0]
        beschrijving = doc.get("BESCHRIJVING")
        print(f"\n  BESCHRIJVING spoor 4 SY002: {beschrijving!r}")
        assert isinstance(beschrijving, str) and "\n" in beschrijving, \
            f"BESCHRIJVING bevat geen regeleinde: {beschrijving!r}"
        assert beschrijving.replace("\r\n", "\n") == SPOOR4_BESCHRIJVING
        # De extra kolommen staan op hun plek en de rest van de rij is niet verschoven
        assert doc["table"] == "SPOREN"
        assert doc["projectcd"] == "SY002"
        assert doc["CODENAAM"] == "SY002"
        assert doc["bron"] == "opgravingSY002"
        assert doc["mdbfile"].endswith("/SY002/C Database/opgravingSY002.mdb")
        assert doc.get("INTERPRETATIE") == "Beerput"
        assert doc.get("DATUM") == "05-06-2024"

        fouten = controleerToegevoegdeKolommen(mongo_client, DB_STAGING)
        assert not fouten, f"Staging-documenten met ontbrekende of verplaatste extra kolommen: {fouten[:10]}"

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

    def test_08_1_verify_spoorbeschrijving_met_regeleinde(self, mongo_client):
        """De beschrijving met een regeleinde van spoor 4 (SY002) komt ongeschonden in Single_Store_Clean (issue 74)."""
        coll = mongo_client[DB_ANALYSE]["Single_Store_Clean"]
        sporen = list(coll.find({"soort": "Spoor", "projectcd": "SY002", "spoornr": 4}))
        assert len(sporen) == 1, f"Verwacht één spoor 4 van SY002, gevonden {len(sporen)}"
        beschrijving = sporen[0].get("beschrijving")
        assert isinstance(beschrijving, str) and beschrijving.replace("\r\n", "\n") == SPOOR4_BESCHRIJVING, \
            f"beschrijving van spoor 4: {beschrijving!r}"

    def test_08a_verify_putten_per_project(self, mongo_client):
        """Elk project heeft precies de putten die in de brondata voorkomen."""
        coll = mongo_client[DB_ANALYSE]["Single_Store_Clean"]
        putten = list(coll.find({"soort": "Put"}, {"projectcd": 1, "putnr": 1, "key": 1}))
        print(f"\n  Putten ({len(putten)}): {sorted(p.get('key') or '?' for p in putten)}")

        for projectcd, verwacht in EXPECTED_PUTTEN.items():
            gevonden = {p.get("putnr") for p in putten if p.get("projectcd") == projectcd}
            assert gevonden == verwacht, (
                f"{projectcd}: verwacht putten {sorted(verwacht)}, gevonden {gevonden}. "
                f"Controleer MOVEANDMERGE_GENERATE_MISSING_PIPELINES voor Put in meta.py."
            )

    def test_08b_verify_vlakken_per_project(self, mongo_client):
        """Elk project heeft precies de vlakken die in de brondata voorkomen."""
        coll = mongo_client[DB_ANALYSE]["Single_Store_Clean"]
        vlakken = list(coll.find({"soort": "Vlak"}, {"projectcd": 1, "putnr": 1, "vlaknr": 1, "key": 1}))
        print(f"\n  Vlakken ({len(vlakken)}): {sorted(v.get('key') or '?' for v in vlakken)}")

        for projectcd, verwacht in EXPECTED_VLAKKEN.items():
            gevonden = {(v.get("putnr"), v.get("vlaknr"))
                        for v in vlakken if v.get("projectcd") == projectcd}
            assert gevonden == verwacht, (
                f"{projectcd}: verwacht vlakken {sorted(verwacht)}, gevonden {gevonden}. "
                f"Controleer MOVEANDMERGE_GENERATE_MISSING_PIPELINES voor Vlak in meta.py."
            )

    def test_08c_verify_geen_dubbele_keys(self, mongo_client):
        """Gegenereerde entiteiten mogen bestaande niet dupliceren (zelfde key)."""
        coll = mongo_client[DB_ANALYSE]["Single_Store_Clean"]
        # Records zonder key tellen niet mee: de dozen in de synthetische magazijnlijst
        # hebben DOOSNO 'D001' enz., dat Transform2 als niet-numeriek verwijdert.
        dubbel = list(coll.aggregate([
            {"$match": {"soort": {"$in": ["Put", "Vlak", "Spoor", "Vondst", "Doos"]},
                        "key": {"$ne": None}}},
            {"$group": {"_id": {"soort": "$soort", "key": "$key"}, "aantal": {"$sum": 1}}},
            {"$match": {"aantal": {"$gt": 1}}},
        ]))
        print(f"\n  Dubbele keys: {len(dubbel)}")
        assert not dubbel, (
            f"Dubbele keys in Single_Store_Clean: {[d['_id'] for d in dubbel]}. "
            f"De key van een gegenereerd record wijkt af van het bestaande record; "
            f"controleer MOVEANDMERGE_GENERATE_MISSING_PIPELINES in meta.py."
        )

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
    # Stap 3b: Foto's — Transform 2 en koppeling aan artefacten
    # ----------------------------------------------------------
    def test_10d_verify_geen_transform2_fouten_voor_bestanden(self, mongo_client):
        """Transform 2 slaat geen foto's, tekeningen of rapporten over (_processing_errors).

        Tot 2026-10-21 koos de dispatcher identificeer('Foto', doc) de
        bestandsnaam-parser identificeer_foto(doc, projectcd); elke foto gaf
        een TypeError, hield zijn tekstnummers en ongenormaliseerde projectcode
        en kon in Transform 4 nooit aan een artefact gekoppeld worden.
        """
        fouten = list(mongo_client[DB_ANALYSE]["_processing_errors"].find({"fase": "enhance_attributes"}))
        bestand_fouten = [f for f in fouten if f.get("soort") in ("Foto", "Tekening", "Rapport")]
        print(f"\n  enhance_attributes-fouten: {len(fouten)}, waarvan voor foto's/tekeningen/rapporten: {len(bestand_fouten)}")
        for f in bestand_fouten[:5]:
            print(f"    {f.get('soort')} {f.get('original_id')}: {f.get('error_type')}: {f.get('error_msg')}")
        assert not bestand_fouten, (
            f"{len(bestand_fouten)} foto's/tekeningen/rapporten zijn in Transform 2 overgeslagen; "
            f"controleer de dispatcher identificeer() in profielen/conventie.py")

    def test_10e_verify_objectfotos_genormaliseerd(self, mongo_client):
        """Objectfoto's in Single_Store_Clean hebben integers voor putnr/vondstnr/subnr en de sleutel key_foto1."""
        coll = mongo_client[DB_ANALYSE]["Single_Store_Clean"]
        for bestand, verwacht in EXPECTED_OBJECTFOTO_KOPPELING.items():
            foto = coll.find_one({"soort": "Bestand", "bestandsoort_XX": "Foto", "fileName": bestand})
            assert foto is not None, f"Objectfoto {bestand} ontbreekt in Single_Store_Clean"
            print(f"\n  {bestand}: projectcd={foto.get('projectcd')} putnr={foto.get('putnr')!r} "
                  f"vondstnr={foto.get('vondstnr')!r} subnr={foto.get('subnr')!r} key_foto1={foto.get('key_foto1')}")
            assert foto.get("projectcd") == "SY002"
            assert foto.get("bestandsoort") == "Objectfoto"
            for veld in ("putnr", "vondstnr", "subnr"):
                assert foto.get(veld) == verwacht[veld], f"{bestand}: {veld}={foto.get(veld)!r}, verwacht {verwacht[veld]}"
            verwachte_key = (f"PSY002M{verwacht['artefactsoort']}P{verwacht['putnr']}"
                             f"V{verwacht['vondstnr']}A{verwacht['subnr']}")
            assert foto.get("key_foto1") == verwachte_key, (
                f"{bestand}: key_foto1={foto.get('key_foto1')!r}, verwacht {verwachte_key}. "
                f"Controleer mergeFotoinfo (FOTO_VELDEN) in merge_functions.py.")

    def test_10f_verify_objectfotos_gekoppeld_aan_artefact(self, mongo_client):
        """Elke objectfoto verwijst met artefactID en vondstID naar het juiste artefact en de juiste vondst."""
        coll = mongo_client[DB_ANALYSE]["Single_Store_Clean"]
        for bestand, verwacht in EXPECTED_OBJECTFOTO_KOPPELING.items():
            foto = coll.find_one({"soort": "Bestand", "bestandsoort_XX": "Foto", "fileName": bestand})
            assert foto is not None, f"Objectfoto {bestand} ontbreekt in Single_Store_Clean"
            assert foto.get("artefactID") is not None, (
                f"{bestand} heeft geen artefactID; controleer Set_Reference_Images_to_Foto1 (key_foto1) in Transform 4")
            artefact = coll.find_one({"soort": "Artefact", "ID": foto["artefactID"]})
            assert artefact is not None, f"{bestand}: artefactID {foto['artefactID']} bestaat niet"
            print(f"\n  {bestand} → artefact {foto['artefactID']}: {artefact.get('artefactsoort')} "
                  f"put {artefact.get('putnr')} vondst {artefact.get('vondstnr')} subnr {artefact.get('subnr')}")
            assert artefact.get("artefactsoort") == verwacht["artefactsoort"]
            assert (artefact.get("putnr"), artefact.get("vondstnr"), artefact.get("subnr")) == \
                (verwacht["putnr"], verwacht["vondstnr"], verwacht["subnr"])

            assert foto.get("vondstID") is not None, f"{bestand} heeft geen vondstID (key_vondst)"
            vondst = coll.find_one({"soort": "Vondst", "ID": foto["vondstID"]})
            assert vondst is not None, f"{bestand}: vondstID {foto['vondstID']} bestaat niet"
            assert (vondst.get("putnr"), vondst.get("vondstnr")) == (verwacht["putnr"], verwacht["vondstnr"])

        # Project- en sfeerfoto's (G/F) horen niet bij een vondst en mogen geen artefact krijgen
        onterecht = coll.count_documents({"soort": "Bestand", "bestandsoort_XX": "Foto",
                                          "bestandsoort": {"$ne": "Objectfoto"}, "artefactID": {"$exists": True}})
        assert onterecht == 0, f"{onterecht} foto's die geen objectfoto zijn hebben een artefactID"

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
    # NB: DAG_Load_Only bevat zowel LoadToDatabase_postgres als de
    # Elasticsearch-indexering (Index_*-taken). De testomgeving heeft een
    # eigen Elasticsearch-container (elasticsearch-test), dus alle taken
    # moeten slagen.
    # ----------------------------------------------------------
    @pytest.mark.load
    def test_19_run_load(self, airflow_ready):
        """Trigger DAG_Load_Only DAG (MongoDB → PostgreSQL + Elasticsearch)."""
        assert run_dag("DAG_Load_Only", timeout=1800) == "success", (
            "DAG_Load_Only niet geslaagd; controleer LoadToDatabase_postgres en de Index_*-taken "
            "(draait elasticsearch-test?)")

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
    def test_22a_verify_postgres_putten_vlakken_per_project(self, airflow_ready):
        """Def_Put en Def_Vlak in PostgreSQL bevatten de putten en vlakken van elk project."""
        fouten = []
        print(f"\n  Putten en vlakken per project in PostgreSQL:")
        for projectcd in EXPECTED_PUTTEN:
            putten = _pg_scalar(
                'SELECT COUNT(*) FROM "Def_Put" p JOIN "Def_Project" pr '
                f"ON p.\"projectID\" = pr.primary_key WHERE pr.projectcd = '{projectcd}'"
            )
            vlakken = _pg_scalar(
                'SELECT COUNT(*) FROM "Def_Vlak" v JOIN "Def_Project" pr '
                f"ON v.\"projectID\" = pr.primary_key JOIN \"Def_Put\" p "
                f"ON v.\"putID\" = p.primary_key WHERE pr.projectcd = '{projectcd}'"
            )
            print(f"    {projectcd}: {putten} putten, {vlakken} vlakken (met put)")
            if putten != len(EXPECTED_PUTTEN[projectcd]):
                fouten.append(f"{projectcd}: {putten} putten, verwacht {len(EXPECTED_PUTTEN[projectcd])}")
            if vlakken != len(EXPECTED_VLAKKEN[projectcd]):
                fouten.append(f"{projectcd}: {vlakken} vlakken, verwacht {len(EXPECTED_VLAKKEN[projectcd])}")

        assert not fouten, "\n  ".join(fouten)

    @pytest.mark.load
    def test_22b_verify_postgres_bestand_gekoppeld_aan_artefact(self, airflow_ready):
        """Def_Bestand bevat de objectfoto's met een artefactID naar hun artefact (lijst 'Alle artefacten met foto')."""
        gekoppeld = _pg_scalar(
            'SELECT COUNT(*) FROM "Def_Bestand" b JOIN "Def_Artefact" a ON b."artefactID" = a.primary_key')
        print(f"\n  Def_Bestand-rijen met een artefactID: {gekoppeld}")
        assert gekoppeld >= len(EXPECTED_OBJECTFOTO_KOPPELING), (
            f"Def_Bestand heeft {gekoppeld} rijen met artefactID, verwacht >= {len(EXPECTED_OBJECTFOTO_KOPPELING)}")
        for bestand, verwacht in EXPECTED_OBJECTFOTO_KOPPELING.items():
            soort = _pg_tekst(
                'SELECT a.artefactsoort FROM "Def_Bestand" b JOIN "Def_Artefact" a ON b."artefactID" = a.primary_key '
                f"WHERE b.\"fileName\" = '{bestand}'")
            print(f"  {bestand} → {soort or '-'}")
            assert soort == verwacht["artefactsoort"], (
                f"{bestand}: gekoppeld aan artefactsoort {soort!r}, verwacht {verwacht['artefactsoort']}")

    @pytest.mark.load
    def test_22c_verify_postgres_verwijzingskolommen_volledig(self, mongo_client, airflow_ready):
        """Elke verwijzingskolom (<soort>ID) in PostgreSQL is even vaak gevuld als het veld in Single_Store_Clean.

        Bewaakt de veldselectie van de load. getFields kijkt naar meta.py plus een
        steekproef van tien documenten; een verwijzing die pas later in de pipeline
        wordt gezet (artefactID op foto's, door setReferences) kan in die tien
        ontbreken. Zonder de kolommen van de doeltabel in de projectie verloor
        Def_Bestand in de Delftse data alle artefactID's, terwijl Single_Store_Clean
        er ruim duizend had. Deze test vergelijkt per tabel en per ID-kolom de
        aantallen, zodat zo'n verlies in de laadstap direct zichtbaar is.
        """
        clean = mongo_client[DB_ANALYSE]["Single_Store_Clean"]
        tabellen = _pg_tekst(
            "SELECT string_agg(table_name, ',') FROM information_schema.tables "
            "WHERE table_schema = 'public' AND table_name LIKE 'Def\\_%'")
        fouten = []
        print("\n  Verwijzingskolommen: Mongo (veld gevuld) vs PostgreSQL (kolom gevuld)")
        for table in sorted(t for t in tabellen.split(",") if t):
            soort = table[4:]
            if clean.count_documents({"soort": soort}) == 0:
                continue  # gebruikerstabellen en pipelinetabellen zonder documenten
            kolommen = _pg_tekst(
                "SELECT string_agg(column_name, ',') FROM information_schema.columns "
                f"WHERE table_name = '{table}' AND column_name LIKE '%ID'")
            for kolom in sorted(k for k in kolommen.split(",") if k):
                in_mongo = clean.count_documents({"soort": soort, kolom: {"$exists": True, "$ne": None}})
                in_pg = _pg_scalar(f'SELECT COUNT(*) FROM "{table}" WHERE "{kolom}" IS NOT NULL')
                status = "✓" if in_mongo == in_pg else "✗"
                print(f"  {table}.{kolom:<20} mongo {in_mongo:>6}  postgres {in_pg:>6}  {status}")
                if in_mongo != in_pg:
                    fouten.append(f"{table}.{kolom}: {in_mongo} gevuld in Single_Store_Clean, {in_pg} in PostgreSQL")
        assert not fouten, "Verwijzingen gaan verloren in de laadstap:\n  " + "\n  ".join(fouten)

    @pytest.mark.load
    def test_23_verify_postgres_no_empty_def_tables(self, airflow_ready):
        """Geen enkele Def_-tabel uit lst_tables mag 0 rijen hebben."""
        lst_tables = [
            'Def_ABR', 'Def_Project', 'Def_Put', 'Def_Vlak', 'Def_Vondst', 'Def_Spoor',
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

    @pytest.mark.load
    @pytest.mark.parametrize("table", ["Def_Project", "Def_Vondst"])
    def test_24_verify_postgres_primary_key_sequence(self, airflow_ready, table):
        """Na DAG_Load_Only heeft primary_key een sequence en default, en nextval > max(primary_key).

        De atomic swap van loadAll dropt de oude tabel met CASCADE; daarmee verdwijnen
        de sequence en de default van primary_key. FASE 3 herstelt ze (zetSequence),
        anders kan de webapplicatie geen rijen aanmaken.
        """
        sequence = _pg_tekst(f"SELECT pg_get_serial_sequence('\"{table}\"', 'primary_key')")
        default = _pg_tekst(
            "SELECT column_default FROM information_schema.columns "
            f"WHERE table_name = '{table}' AND column_name = 'primary_key'")
        maximum = _pg_scalar(f'SELECT COALESCE(MAX(primary_key), 0) FROM "{table}"')
        print(f"\n  {table}: sequence={sequence or '-'}, default={default or '-'}, max(primary_key)={maximum}")
        assert sequence, f"{table}.primary_key heeft geen sequence na de volledige load"
        assert default.startswith("nextval("), f"{table}.primary_key heeft geen default nextval(...): {default!r}"
        volgende = _pg_scalar(f"SELECT nextval('{sequence}')")
        print(f"  {table}: nextval={volgende}")
        assert volgende > maximum, f"{table}: nextval {volgende} is niet groter dan max(primary_key) {maximum}"
