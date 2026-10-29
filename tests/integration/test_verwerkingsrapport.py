"""
Integratietest: foutbeleid (issue 54) en verwerkingsrapport (issue 62) in de echte DAG's.

Synthetische testomgeving (markers integration en load, onderdeel van ``make integration``;
draait na test_incremental_synthetic_data.py, die de rapporten van de volledige en de
incrementele runs al per run controleert):

1. DagBag-test: in de volledige cyclus, de incrementele cyclus en DAG_Load_Only zijn de
   trigger rules en de bewaking volgens het beleid (``foutbeleid.controleerBewaking``: elke
   cruciale taak bewaakt door Markeer_Run_Mislukt en de eindtaak, geen Index-taak), heeft
   elke taak de on_failure_callback en wacht Verwerkingsrapport op alle andere taken;
2. elke beëindigde run in Verwerkingsruns heeft een rapport (JSON en Markdown) met alle
   secties; draait deze test los, dan eerst de volledige cyclus;
3. DAG_Load_Only: een run van soort laden met een rapport waarvan de totalen gelijk zijn
   aan PostgreSQL en dat geen nieuwe of verwijderde rijen telt;
4. een bewust mislukte run: DAG_Load_Only terwijl er al een run actief is. Alleen Start_Run
   faalt, er is een rapport zonder run-document dat Start_Run als oorzaak noemt, de andere
   run blijft ongemoeid en PostgreSQL is ongewijzigd.

Delftse testomgeving (marker delft_load, onderdeel van ``make integration-delft``; draait
na test_full_pipeline_delft_data.py): na DAG_Load_Only bestaat het rapport van de run met
totalen gelijk aan PostgreSQL.

De rapporten staan in de Airflow-container (AIRFLOW_OUTPUT_RAPPORTEN=/tmp/rapporten_test in
de testomgevingen) en worden met ``docker exec`` gelezen.
"""
import json
import os
import re
import subprocess
import time
from datetime import datetime, timezone

import pytest

pymongo = pytest.importorskip("pymongo")

from wasstraat.loadToDatabase_functions import LOAD_TABELLEN


MONGO_TEST_URI = os.getenv("MONGO_TEST_URI", "mongodb://testroot:testpass@localhost:27117/")
DB_STAGING = "Arch_Staging_Test"
SYNTHETISCH = {"airflow": os.getenv("AIRFLOW_CONTAINER", "wasstraat_airflow_test"),
               "postgres": os.getenv("POSTGRES_CONTAINER", "wasstraat_postgres_test")}
DELFT = {"airflow": os.getenv("DELFT_AIRFLOW_CONTAINER", "wasstraat_airflow_delft_test"),
         "postgres": os.getenv("DELFT_POSTGRES_CONTAINER", "wasstraat_postgres_delft_test")}

DAGS_MET_RUN = ["Extract_Transform_Load_Full_Cycle", "Extract_Transform_Load_Incremental", "DAG_Load_Only"]
RAPPORT_SECTIES = ["rapport_versie", "gemaakt_op", "run", "samenvatting", "foutbeleid", "bronbestanden",
                   "objecttotalen", "kwaliteitsmeldingen", "pipeline", "fouten_in_rapport"]
MARKDOWN_KOPPEN = ["## Foutbeleid", "### Fouten", "### Waarschuwingen", "### Mislukte taken", "## Bronbestanden",
                   "### Totalen per categorie", "### Bestanden", "## Objecttotalen", "## Kwaliteitsmeldingen",
                   "### Verwerkingsfouten (Transform 2)", "### Afbeeldingen en rapporten", "### Access-databases",
                   "### Verwijzingen (FK)", "### Gebruikersdata", "## Pipeline", "### Doorlooptijd per stap"]
TESTRUN = "test_actieve_run_verwerkingsrapport"

TOESTAND = {}


# ============================================================
# Helpers
# ============================================================

def dockerExec(container, *cmd, timeout=60):
    return subprocess.run(["docker", "exec", container, *cmd], capture_output=True, text=True, timeout=timeout)


def draaiDag(omgeving, dag_id, verwacht_mislukt=None, timeout=1500):
    """Draai een DAG met ``airflow dags test``; zonder verwacht_mislukt moet alles slagen.

    Returns:
        Uitvoer van ``airflow dags test``
    """
    print(f"\n  ▶ airflow dags test {dag_id} ({omgeving['airflow']})")
    start = time.time()
    resultaat = dockerExec(omgeving["airflow"], "airflow", "dags", "test", dag_id, "2026-01-01", timeout=timeout)
    uitvoer = resultaat.stdout + "\n" + resultaat.stderr
    status = re.findall(r"DagRun Finished: dag_id=\S+.*?state=(\w+)", uitvoer)
    mislukt = sorted(set(re.findall(r"Marking task as FAILED\. dag_id=\S+, task_id=([\w.]+)", uitvoer)))
    if verwacht_mislukt is None:
        geslaagd = resultaat.returncode == 0 and status and status[-1] == "success" and not mislukt
    else:
        geslaagd = status and status[-1] == "failed" and mislukt == sorted(verwacht_mislukt)
    if not geslaagd:
        for regel in [r for r in uitvoer.split("\n") if any(w in r for w in ("ERROR", "Traceback", "FAILED"))][-40:]:
            print(f"    {regel}")
        pytest.fail(f"DAG {dag_id}: status {status[-1:]}, mislukte taken {mislukt}, verwacht mislukt {verwacht_mislukt}")
    print(f"  ✓  {dag_id} in {time.time() - start:.1f}s (status {status[-1]})")
    return uitvoer


def pgRijen(omgeving, sql):
    cmd = ["docker", "exec", "-e", "PGPASSWORD=testpass", omgeving["postgres"], "psql", "-U", "testuser", "-h",
           "localhost", "-d", "airflow_test", "-q", "-t", "-A", "-F", "\t", "-v", "ON_ERROR_STOP=1", "-c", sql]
    resultaat = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    if resultaat.returncode != 0:
        raise RuntimeError(f"psql fout: {resultaat.stderr.strip()}")
    return [regel.split("\t") for regel in resultaat.stdout.strip().split("\n") if regel.strip()]


def telTabellen(omgeving):
    return {t: int(pgRijen(omgeving, f'SELECT COUNT(*) FROM "{t}"')[0][0]) for t in LOAD_TABELLEN}


def leesBestand(omgeving, pad):
    resultaat = dockerExec(omgeving["airflow"], "cat", pad)
    assert resultaat.returncode == 0, f"{pad} niet te lezen in {omgeving['airflow']}: {resultaat.stderr.strip()}"
    return resultaat.stdout


def controleerRapportbestanden(omgeving, json_pad, md_pad):
    """Lees een rapport en controleer de secties en de koppen; retourneer (rapport, markdown)."""
    rapport = json.loads(leesBestand(omgeving, json_pad))
    markdown = leesBestand(omgeving, md_pad)
    for sectie in RAPPORT_SECTIES:
        assert sectie in rapport, f"Sectie {sectie} ontbreekt in {json_pad}"
    for kop in MARKDOWN_KOPPEN:
        assert f"\n{kop}\n" in markdown, f"Kop {kop} ontbreekt in {md_pad}"
    assert rapport["rapport_versie"] == 1
    return rapport, markdown


def rapportVanRun(omgeving, run):
    info = run.get("rapport")
    assert info, f"Run {run['run_id']} ({run['soort']}, {run['status']}) heeft geen rapport"
    rapport, markdown = controleerRapportbestanden(omgeving, info["json"], info["markdown"])
    assert rapport["run"]["run_id"] == run["run_id"] and rapport["run"]["soort"] == run["soort"]
    assert markdown.startswith(f"# Verwerkingsrapport {run['run_id']}")
    return rapport, markdown


def laatsteRun(mongo_client, soort):
    return mongo_client[DB_STAGING]["Verwerkingsruns"].find_one({"soort": soort}, sort=[("gestart_op", pymongo.DESCENDING)])


@pytest.fixture(scope="module")
def mongo_client():
    client = pymongo.MongoClient(MONGO_TEST_URI, serverSelectionTimeoutMS=5000)
    try:
        client.admin.command("ping")
    except pymongo.errors.ConnectionFailure:
        pytest.skip("MongoDB niet bereikbaar op " + MONGO_TEST_URI)
    yield client
    client.close()


# ============================================================
# 1. DagBag: trigger rules en bewaking (issue 54)
# ============================================================

DAGBAG_SCRIPT = """
import json, sys
sys.path.insert(0, '/opt/airflow/dags')
from airflow.models import DagBag
import wasstraat.foutbeleid as foutbeleid
bag = DagBag(include_examples=False)
uit = {'import_errors': sorted(bag.import_errors)}
for dag_id in %r:
    dag = bag.get_dag(dag_id)
    if dag is None:
        uit[dag_id] = None
        continue
    def heeftCallback(taak):
        cb = taak.on_failure_callback
        cb = cb if isinstance(cb, list) else [cb]
        return any(getattr(c, '__name__', '') == 'registreerTaakfout' for c in cb)
    rapport = dag.get_task('Verwerkingsrapport')
    uit[dag_id] = {
        'problemen': foutbeleid.controleerBewaking(dag),
        'zonder_callback': sorted(t.task_id for t in dag.tasks if not heeftCallback(t)),
        'bladeren': sorted(t.task_id for t in dag.tasks if not t.downstream_task_ids),
        'taken': len(dag.tasks),
        'rapport_wacht_op': len(rapport.upstream_task_ids),
        'trigger_rules': {t.task_id: str(t.trigger_rule) for t in dag.tasks if str(t.trigger_rule) != 'all_success'},
        'max_active_runs': dag.max_active_runs,
    }
print('RESULTAAT:' + json.dumps(uit))
"""


@pytest.mark.integration
class TestDagStructuur:

    def test_trigger_rules_en_bewaking(self):
        resultaat = dockerExec(SYNTHETISCH["airflow"], "python", "-c", DAGBAG_SCRIPT % (DAGS_MET_RUN,), timeout=300)
        regels = [r for r in resultaat.stdout.split("\n") if r.startswith("RESULTAAT:")]
        assert resultaat.returncode == 0 and regels, f"DagBag niet gelezen: {resultaat.stderr[-2000:]}"
        uit = json.loads(regels[-1][len("RESULTAAT:"):])
        assert uit["import_errors"] == [], uit["import_errors"]
        eindtaak = {"Extract_Transform_Load_Full_Cycle": "End_ETL_full_cycle",
                    "Extract_Transform_Load_Incremental": "End_ETL_incremental", "DAG_Load_Only": "End_cycle"}
        for dag_id in DAGS_MET_RUN:
            info = uit[dag_id]
            assert info is not None, f"DAG {dag_id} niet gevonden"
            print(f"\n  {dag_id}: {info['taken']} taken, niet-standaard trigger rules {info['trigger_rules']}")
            assert info["problemen"] == [], f"{dag_id}: " + "\n".join(info["problemen"])
            assert info["zonder_callback"] == [], f"{dag_id}: taken zonder on_failure_callback {info['zonder_callback']}"
            assert info["bladeren"] == [eindtaak[dag_id]]
            assert info["rapport_wacht_op"] == info["taken"] - 2
            assert info["trigger_rules"]["Markeer_Run_Mislukt"] == "one_failed"
            assert info["trigger_rules"]["Verwerkingsrapport"] == "all_done"
            assert any(t.endswith("Index_Klaar") and r == "all_done" for t, r in info["trigger_rules"].items())
            assert info["max_active_runs"] == 1


# ============================================================
# 2-4. Rapporten in de synthetische omgeving (issue 62)
# ============================================================

@pytest.mark.integration
@pytest.mark.load
class TestRapportenSynthetisch:

    def test_01_elke_run_heeft_een_rapport(self, mongo_client):
        """Alle beëindigde runs (ook mislukte) hebben een rapport; zonder eerdere runs eerst de volledige cyclus."""
        runs = mongo_client[DB_STAGING]["Verwerkingsruns"]
        if runs.count_documents({"soort": "volledig", "status": "afgerond"}) == 0:
            draaiDag(SYNTHETISCH, "Extract_Transform_Load_Full_Cycle")
        beeindigd = list(runs.find({"status": {"$ne": "actief"}}).sort("gestart_op", 1))
        assert beeindigd, "Geen runs in Verwerkingsruns"
        per_soort = {}
        for run in beeindigd:
            rapport, _ = rapportVanRun(SYNTHETISCH, run)
            assert rapport["run"]["status"] == run["status"]
            assert (rapport["foutbeleid"]["uitkomst"] == "mislukt") == (run["status"] == "mislukt"), run["run_id"]
            per_soort.setdefault(run["soort"], []).append(run["status"])
        print(f"\n  Runs met rapport: {per_soort}")
        assert "volledig" in per_soort

    def test_02_load_only(self, mongo_client):
        voor = telTabellen(SYNTHETISCH)
        draaiDag(SYNTHETISCH, "DAG_Load_Only")
        run = laatsteRun(mongo_client, "laden")
        assert run["status"] == "afgerond" and run["dag_id"] == "DAG_Load_Only", run.get("melding")
        assert "load" in run["tellingen"] and not [m for m in run["meldingen"] if m["niveau"] == "fout"]
        rapport, markdown = rapportVanRun(SYNTHETISCH, run)
        assert rapport["foutbeleid"]["uitkomst"] in ("geslaagd", "geslaagd met waarschuwingen")
        assert rapport["bronbestanden"]["van_toepassing"] is False
        assert "alleen laden" in markdown
        # Totalen gelijk aan PostgreSQL; dezelfde data opnieuw geladen: niets nieuw of verwijderd
        na = telTabellen(SYNTHETISCH)
        assert na == voor
        assert {t: v["totaal"] for t, v in rapport["objecttotalen"]["tabellen"].items()} == na
        assert rapport["objecttotalen"]["totaal"]["aangemaakt"] == 0
        assert rapport["objecttotalen"]["totaal"]["verwijderd"] == 0
        assert sum(rapport["objecttotalen"]["artefactsoorten"].values()) == na["Def_Artefact"]
        stappen = {s["stap"] for s in rapport["pipeline"]["stappen"]}
        assert {"voorbereiding", "load", "index", "registratie"} <= stappen, stappen
        assert rapport["kwaliteitsmeldingen"]["fk"]["niet_gevalideerd"] == []

    def test_03_mislukte_start_geeft_rapport_zonder_run(self, mongo_client):
        """Een bewust mislukte run: er is al een run actief, dus Start_Run faalt en er wordt niets geladen."""
        runs = mongo_client[DB_STAGING]["Verwerkingsruns"]
        assert runs.count_documents({"status": "actief"}) == 0, "Er is al een actieve run"
        nu = datetime.now(timezone.utc).replace(tzinfo=None)
        runs.insert_one({"_id": TESTRUN, "run_id": TESTRUN, "soort": "incrementeel", "status": "actief",
                         "airflow_run_id": "handmatig_test", "gestart_op": nu, "meldingen": [], "tellingen": {}})
        try:
            voor = telTabellen(SYNTHETISCH)
            uitvoer = draaiDag(SYNTHETISCH, "DAG_Load_Only", verwacht_mislukt=["Start_Run"])
            paden = re.findall(r"Rapport: (\S+\.json) en (\S+\.md)", uitvoer)
            assert paden, "Geen rapport gemeld in het log van Verwerkingsrapport"
            json_pad, md_pad = paden[-1]
            assert "verwerkingsrapport_zonder-run_DAG_Load_Only_" in json_pad
            rapport, markdown = controleerRapportbestanden(SYNTHETISCH, json_pad, md_pad)
            assert rapport["run"]["run_id"] is None and rapport["foutbeleid"]["uitkomst"] == "mislukt"
            assert rapport["foutbeleid"]["gestopt_door"]["taak"] == "Start_Run"
            assert "De run is gestopt door taak `Start_Run`" in markdown
            niet_uitgevoerd = {t["taak"] for t in rapport["pipeline"]["taken"] if t["status"] == "upstream_failed"}
            assert "Load_To_Database_And_Inxdex_Group.LoadToDatabase_postgres" in niet_uitgevoerd
            # De andere run is ongemoeid en er is niets geladen
            ander = runs.find_one({"_id": TESTRUN})
            assert ander["status"] == "actief" and ander["meldingen"] == [] and "rapport" not in ander
            assert telTabellen(SYNTHETISCH) == voor
        finally:
            runs.delete_one({"_id": TESTRUN})


# ============================================================
# 5. Delftse testomgeving: rapport na DAG_Load_Only (issue 62)
# ============================================================

@pytest.mark.delft_load
class TestRapportDelft:

    def test_rapport_na_load_only(self, mongo_client):
        run = laatsteRun(mongo_client, "laden")
        assert run is not None, "Geen run van DAG_Load_Only in de Delftse testomgeving"
        assert run["status"] == "afgerond", run.get("melding")
        rapport, markdown = rapportVanRun(DELFT, run)
        print(f"\n  Rapport {run['rapport']['json']}: {run['rapport']['samenvatting']}")
        assert rapport["foutbeleid"]["uitkomst"] in ("geslaagd", "geslaagd met waarschuwingen")
        assert rapport["fouten_in_rapport"] == []
        totalen = {t: v["totaal"] for t, v in rapport["objecttotalen"]["tabellen"].items()}
        assert totalen == telTabellen(DELFT), "Totalen in het rapport wijken af van PostgreSQL"
        assert totalen["Def_Artefact"] > 0 and totalen["Def_Project"] > 0
        # De eerste load in een lege database: alle rijen zijn nieuw
        load = run["tellingen"]["load"]
        assert rapport["objecttotalen"]["totaal"]["aangemaakt"] == load["totaal"]["ingevoegd"]
        assert {"load", "index"} <= {s["stap"] for s in rapport["pipeline"]["stappen"]}
