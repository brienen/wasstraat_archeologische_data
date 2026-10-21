"""
Integratietest: incrementeel laden met synthetische data (issue 61, fase 3).

Draait eerst de volledige cyclus op SY001 en SY002 en daarna vier keer de
incrementele cyclus (Extract_Transform_Load_Incremental) via
``airflow dags test``:

  a. volledige cyclus: aantallen, sleutels (key → primary_key) en
     Elasticsearch-aantallen vastleggen;
  b. een partij en een bruikleen toevoegen (gebruikersdata) die verwijzen naar
     een artefact en het project SY002;
  c. incrementele run zonder wijzigingen: niets verandert;
  d. project SY003 als kopie van SY002 (database opgravingSY003.mdb, foto's
     SY003_*): SY003 komt erbij met nieuwe primary_keys, SY001/SY002 blijven gelijk;
  e. de database van SY003 vervangen door die van SY001 en één foto
     verwijderd: SY003 volgt de nieuwe inhoud, geen achtergebleven rijen;
  f. SY003 verwijderd: alles weer gelijk aan a.

Na elke run worden PostgreSQL (via ``docker exec psql``), MongoDB (run-document)
en Elasticsearch (via ``docker exec curl`` in de Elasticsearch-container; die
heeft geen hostpoort) gecontroleerd. De fixture ``sy003_opruimen`` verwijdert
data/synthetic/data/projecten/SY003 vóór en na de test, ook als de test faalt.

Draaien:
  make integration   (na de andere integratietests, met markers integration en load)
"""
import json
import os
import re
import shutil
import subprocess
import time

import pytest

pymongo = pytest.importorskip("pymongo")

from wasstraat.loadToDatabase_functions import LOAD_TABELLEN


# ============================================================
# Configuratie
# ============================================================

MONGO_TEST_URI = os.getenv("MONGO_TEST_URI", "mongodb://testroot:testpass@localhost:27117/")
AIRFLOW_CONTAINER = os.getenv("AIRFLOW_CONTAINER", "wasstraat_airflow_test")
POSTGRES_CONTAINER = os.getenv("POSTGRES_CONTAINER", "wasstraat_postgres_test")
ES_CONTAINER = os.getenv("ES_CONTAINER", "wasstraat_elasticsearch_test")
DB_STAGING = "Arch_Staging_Test"

PROJECTEN_DIR = os.path.abspath(os.path.join(
    os.path.dirname(__file__), "..", "..", "data", "synthetic", "data", "projecten"))
SY001_MDB = os.path.join(PROJECTEN_DIR, "SY001", "C Database", "opgravingSY001.mdb")
SY002_DIR = os.path.join(PROJECTEN_DIR, "SY002")
SY003_DIR = os.path.join(PROJECTEN_DIR, "SY003")
SY003_MDB = os.path.join(SY003_DIR, "C Database", "opgravingSY003.mdb")
VERWIJDERDE_FOTO = "SY003_F002.jpg"
PAD_SY003_IN_CONTAINER = "/input/projecten/SY003/"

# Tabellen waarvan de sleutels (key → primary_key) vastgelegd en vergeleken worden
SLEUTEL_TABELLEN = ["Def_Project", "Def_Put", "Def_Vondst", "Def_Artefact", "Def_Bestand"]
# Tabellen met rijen per project; de key begint met 'P' + projectcode (artefacten: key_subnr|artefactsoort)
PROJECT_TABELLEN = ["Def_Put", "Def_Vlak", "Def_Spoor", "Def_Vondst", "Def_Vulling", "Def_Artefact", "Def_Bestand"]

TESTPARTIJ = "Testpartij incrementeel laden"

# Toestand die de genummerde tests met elkaar delen
TOESTAND = {}


# ============================================================
# Helpers
# ============================================================

def draaiDag(dag_id, timeout=1200):
    """Draai een DAG met ``airflow dags test`` en eis dat de DagRun slaagt (ook alle Index-taken)."""
    cmd = ["docker", "exec", AIRFLOW_CONTAINER, "airflow", "dags", "test", dag_id, "2026-01-01"]
    print(f"\n  ▶ {' '.join(cmd)}")
    start = time.time()
    resultaat = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    uitvoer = resultaat.stdout + "\n" + resultaat.stderr
    duur = time.time() - start
    status = re.findall(r"DagRun Finished: dag_id=\S+.*?state=(\w+)", uitvoer)
    mislukt = sorted(set(re.findall(r"Marking task as FAILED\. dag_id=\S+, task_id=([\w.]+)", uitvoer)))
    if resultaat.returncode != 0 or not status or status[-1] != "success" or mislukt:
        regels = [r for r in uitvoer.split("\n") if any(w in r for w in ("ERROR", "Error", "Traceback", "FAILED"))]
        for regel in (regels or uitvoer.split("\n"))[-40:]:
            print(f"    {regel}")
        pytest.fail(f"DAG {dag_id} niet geslaagd (exit {resultaat.returncode}, status {status[-1:]}, "
                    f"mislukte taken {mislukt}) na {duur:.0f}s")
    print(f"  ✓  {dag_id} geslaagd in {duur:.1f}s")
    return duur


def pgRijen(sql):
    """Voer een query uit op de test-PostgreSQL en retourneer de rijen als lijsten met tekst."""
    cmd = ["docker", "exec", "-e", "PGPASSWORD=testpass", POSTGRES_CONTAINER, "psql", "-U", "testuser",
           "-h", "localhost", "-d", "airflow_test", "-q", "-t", "-A", "-F", "\t", "-v", "ON_ERROR_STOP=1", "-c", sql]
    resultaat = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    if resultaat.returncode != 0:
        raise RuntimeError(f"psql fout: {resultaat.stderr.strip()}")
    return [regel.split("\t") for regel in resultaat.stdout.strip().split("\n") if regel.strip()]


def pgWaarde(sql):
    """Retourneer de eerste waarde van een query als integer (of None)."""
    rijen = pgRijen(sql)
    return int(rijen[0][0]) if rijen and rijen[0][0] != "" else None


def telTabellen():
    """Aantal rijen per tabel uit LOAD_TABELLEN."""
    return {t: pgWaarde(f'SELECT COUNT(*) FROM "{t}"') for t in LOAD_TABELLEN}


def sleutels(tabel, filter_sql="TRUE"):
    """Set met (key, primary_key) van een tabel (keys zijn niet altijd uniek, bijv. foto's)."""
    return {(r[0], int(r[1])) for r in pgRijen(f'SELECT key, primary_key FROM "{tabel}" WHERE {filter_sql}')}


def primaryKeys(tabel, filter_sql="TRUE"):
    return {int(r[0]) for r in pgRijen(f'SELECT primary_key FROM "{tabel}" WHERE {filter_sql}')}


def filterProject(projectcd):
    """SQL-voorwaarde voor de rijen van een project (op de key)."""
    return f"key LIKE 'P{projectcd}%'"


def filterNietProject(projectcd):
    """SQL-voorwaarde voor alle rijen die niet bij een project horen (ook rijen zonder key)."""
    return f"COALESCE(key, '') NOT LIKE 'P{projectcd}%'"


def telBestanden(map_):
    """Aantal (niet-verborgen) bestanden in een map en submappen."""
    return sum(1 for _, _, namen in os.walk(map_) for naam in namen if not naam.startswith("."))


def bronbestandStatussen(filter_sql="TRUE"):
    """Aantal geregistreerde bronbestanden per status."""
    return dict((r[0], int(r[1])) for r in pgRijen(
        f'SELECT status, COUNT(*) FROM "Def_Bronbestand" WHERE {filter_sql} GROUP BY status'))


def telProject(tabel, projectcd):
    return pgWaarde(f'SELECT COUNT(*) FROM "{tabel}" WHERE {filterProject(projectcd)}')


def esJson(pad):
    """GET op Elasticsearch in de testcontainer (geen hostpoort)."""
    cmd = ["docker", "exec", ES_CONTAINER, "curl", "-s", f"http://localhost:9200/{pad}"]
    resultaat = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    if resultaat.returncode != 0:
        raise RuntimeError(f"curl fout: {resultaat.stderr.strip()}")
    return json.loads(resultaat.stdout)


def esAantallen():
    """Aantal documenten per alias (tabelnaam in kleine letters) van LOAD_TABELLEN."""
    esJson("_refresh")
    return {t: esJson(f"{t.lower()}/_count")["count"] for t in LOAD_TABELLEN}


def esIds(tabel):
    """Set met de document-id's in de index achter de alias van een tabel."""
    antwoord = esJson(f"{tabel.lower()}/_search?size=10000&_source=false&filter_path=hits.hits._id")
    return {int(hit["_id"]) for hit in antwoord.get("hits", {}).get("hits", [])}


def laatsteRun(mongo_client):
    """Het run-document van de laatste incrementele run."""
    return mongo_client[DB_STAGING]["Verwerkingsruns"].find_one(
        {"soort": "incrementeel"}, sort=[("gestart_op", pymongo.DESCENDING)])


def controleerRun(mongo_client):
    """Controleer dat de laatste incrementele run is afgerond en retourneer het run-document."""
    run = laatsteRun(mongo_client)
    assert run is not None, "Geen run-document van een incrementele run gevonden"
    assert run["status"] == "afgerond", f"Run {run['run_id']} heeft status {run['status']}: {run.get('melding')}"
    assert "load" in run.get("tellingen", {}), "tellingen.load ontbreekt in het run-document"
    print(f"  Run {run['run_id']}: delta {run['tellingen']['delta']['totaal']}, "
          f"load {run['tellingen']['load']['totaal']}")
    return run


def controleerBruikleen():
    """De bruikleen uit stap b bestaat nog en zijn artefact heeft dezelfde primary_key en key."""
    b = TOESTAND["bruikleen"]
    rij = pgRijen(f'SELECT "artefactID", "projectID" FROM "Def_Bruikleen" WHERE primary_key = {b["primary_key"]}')
    assert rij, "De bruikleen is verdwenen"
    assert int(rij[0][0]) == b["artefact_pk"] and int(rij[0][1]) == b["project_pk"]
    artefact = pgRijen(f'SELECT key FROM "Def_Artefact" WHERE primary_key = {b["artefact_pk"]}')
    assert artefact and artefact[0][0] == b["artefact_key"], (
        f"Artefact {b['artefact_pk']} van de bruikleen heeft niet meer key {b['artefact_key']}: {artefact}")
    project = pgRijen(f'SELECT projectcd FROM "Def_Project" WHERE primary_key = {b["project_pk"]}')
    assert project and project[0][0] == "SY002"


def controleerSY001SY002Ongewijzigd():
    """Sleutels en primary_keys van alle rijen die niet bij SY003 horen zijn gelijk aan stap a."""
    for tabel in SLEUTEL_TABELLEN:
        assert sleutels(tabel, filterNietProject("SY003")) == TOESTAND["sleutels"][tabel], (
            f"{tabel}: sleutels of primary_keys van SY001/SY002 gewijzigd")


def controleerElasticsearchGelijkAanTabellen():
    """Per tabel: dezelfde id's in Elasticsearch als primary_keys in PostgreSQL."""
    aantallen = esAantallen()
    tabellen = telTabellen()
    assert aantallen == tabellen, f"Elasticsearch {aantallen} wijkt af van PostgreSQL {tabellen}"
    for tabel in PROJECT_TABELLEN:
        assert esIds(tabel) == primaryKeys(tabel), f"{tabel}: id's in Elasticsearch wijken af van PostgreSQL"
    return aantallen


def maakSY003AlsKopieVanSY002():
    """Kopieer SY002 naar SY003 (met submappen): database als opgravingSY003.mdb, foto's SY002_* als SY003_*."""
    shutil.rmtree(SY003_DIR, ignore_errors=True)
    for bron_map, _, namen in os.walk(SY002_DIR):
        doel_map = os.path.join(SY003_DIR, os.path.relpath(bron_map, SY002_DIR))
        os.makedirs(doel_map, exist_ok=True)
        for naam in namen:
            if naam.startswith("."):
                continue
            nieuwe_naam = "opgravingSY003.mdb" if naam == "opgravingSY002.mdb" else naam.replace("SY002", "SY003")
            shutil.copyfile(os.path.join(bron_map, naam), os.path.join(doel_map, nieuwe_naam))


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


@pytest.fixture(scope="module", autouse=True)
def sy003_opruimen():
    """Verwijder het testproject SY003 vóór en na de test (ook bij falen), en de testbruikleen achteraf."""
    shutil.rmtree(SY003_DIR, ignore_errors=True)
    try:
        yield
    finally:
        shutil.rmtree(SY003_DIR, ignore_errors=True)
        try:
            pgRijen(f'DELETE FROM "Def_Bruikleen" WHERE "partijID" IN '
                    f'(SELECT primary_key FROM "Def_Partij" WHERE naam = \'{TESTPARTIJ}\')')
            pgRijen(f'DELETE FROM "Def_Partij" WHERE naam = \'{TESTPARTIJ}\'')
        except Exception as err:
            print(f"  (testbruikleen niet opgeruimd: {err})")


# ============================================================
# Tests
# ============================================================

@pytest.mark.integration
@pytest.mark.load
class TestIncrementeelSynthetic:
    """Volledige cyclus gevolgd door vier incrementele runs op SY001, SY002 en een tijdelijk project SY003."""

    # ----------------------------------------------------------
    # a. Volledige cyclus
    # ----------------------------------------------------------
    def test_01_volledige_cyclus(self, mongo_client):
        assert not os.path.exists(SY003_DIR)
        TOESTAND["duur"] = {"volledig": draaiDag("Extract_Transform_Load_Full_Cycle")}

    def test_02_uitgangssituatie_vastleggen(self):
        TOESTAND["aantallen"] = telTabellen()
        TOESTAND["sleutels"] = {t: sleutels(t) for t in SLEUTEL_TABELLEN}
        TOESTAND["max_pk"] = {t: pgWaarde(f'SELECT COALESCE(MAX(primary_key), -1) FROM "{t}"') for t in PROJECT_TABELLEN}
        print(f"\n  Aantallen na de volledige cyclus: {TOESTAND['aantallen']}")

        for tabel in PROJECT_TABELLEN:
            assert telProject(tabel, "SY003") == 0
            assert telProject(tabel, "SY002") > 0, f"{tabel}: geen rijen van SY002"
        assert TOESTAND["aantallen"]["Def_Project"] == 2

        # Artefacten hebben een key: key_subnr|artefactsoort (fase 3)
        assert pgWaarde('SELECT COUNT(*) FROM "Def_Artefact" WHERE key IS NULL') == 0
        assert pgWaarde('SELECT COUNT(*) FROM "Def_Artefact" WHERE key LIKE \'%|%\'') > 0

        # De Index-taken van de volledige cyclus zijn geslaagd: Elasticsearch gelijk aan PostgreSQL
        TOESTAND["es"] = controleerElasticsearchGelijkAanTabellen()

        # De volledige cyclus registreert alle bronbestanden (SY003 kan van een eerdere testrun als verwijderd staan)
        statussen = bronbestandStatussen(f"pad NOT LIKE '{PAD_SY003_IN_CONTAINER}%'")
        assert set(statussen) == {"verwerkt"} and statussen["verwerkt"] > 0, statussen
        TOESTAND["bronbestanden"] = statussen["verwerkt"]

    # ----------------------------------------------------------
    # b. Gebruikersdata: partij en bruikleen
    # ----------------------------------------------------------
    def test_03_bruikleen_toevoegen(self):
        artefact = pgRijen(f'SELECT primary_key, key FROM "Def_Artefact" WHERE {filterProject("SY002")} '
                           f'ORDER BY primary_key LIMIT 1')[0]
        project_pk = pgWaarde('SELECT primary_key FROM "Def_Project" WHERE projectcd = \'SY002\'')
        partij_pk = pgWaarde(f'INSERT INTO "Def_Partij" (naam) VALUES (\'{TESTPARTIJ}\') RETURNING primary_key')
        bruikleen_pk = pgWaarde(
            f'INSERT INTO "Def_Bruikleen" (datum_uitgeleend, "projectID", "artefactID", "partijID") '
            f'VALUES (DATE \'2026-10-01\', {project_pk}, {artefact[0]}, {partij_pk}) RETURNING primary_key')
        TOESTAND["bruikleen"] = {"primary_key": bruikleen_pk, "partij_pk": partij_pk, "project_pk": project_pk,
                                 "artefact_pk": int(artefact[0]), "artefact_key": artefact[1]}
        print(f"\n  Bruikleen {TOESTAND['bruikleen']}")
        controleerBruikleen()

    # ----------------------------------------------------------
    # c. Incrementele run zonder wijzigingen
    # ----------------------------------------------------------
    def test_04_incrementeel_zonder_wijzigingen(self, mongo_client):
        TOESTAND["duur"]["c"] = draaiDag("Extract_Transform_Load_Incremental")
        run = controleerRun(mongo_client)
        delta = run["tellingen"]["delta"]["totaal"]
        assert delta["nieuw"] == 0 and delta["gewijzigd"] == 0 and delta["verwijderd"] == 0, delta
        assert delta["ongewijzigd"] == TOESTAND["bronbestanden"]
        load = run["tellingen"]["load"]["totaal"]
        assert load["ingevoegd"] == 0 and load["bijgewerkt"] == 0 and load["verwijderd"] == 0, load
        assert run["tellingen"]["load"]["fk_niet_gevalideerd"] == []

        statussen = bronbestandStatussen(f"pad NOT LIKE '{PAD_SY003_IN_CONTAINER}%'")
        assert statussen == {"verwerkt": TOESTAND["bronbestanden"]}, statussen

        assert telTabellen() == TOESTAND["aantallen"]
        for tabel in SLEUTEL_TABELLEN:
            assert sleutels(tabel) == TOESTAND["sleutels"][tabel], f"{tabel}: sleutels gewijzigd"
        controleerBruikleen()
        assert esAantallen() == TOESTAND["es"]

    # ----------------------------------------------------------
    # d. Nieuw project SY003 (kopie van SY002)
    # ----------------------------------------------------------
    def test_05_nieuw_project_sy003(self, mongo_client):
        maakSY003AlsKopieVanSY002()
        TOESTAND["duur"]["d"] = draaiDag("Extract_Transform_Load_Incremental")
        run = controleerRun(mongo_client)
        assert run["tellingen"]["delta"]["totaal"]["nieuw"] == telBestanden(SY003_DIR)

        aantallen = telTabellen()
        TOESTAND["sy003_ids"] = {}
        for tabel in LOAD_TABELLEN:
            if tabel in PROJECT_TABELLEN:
                nieuw = telProject(tabel, "SY003")
                assert nieuw == telProject(tabel, "SY002"), f"{tabel}: SY003 is geen kopie van SY002"
                assert aantallen[tabel] == TOESTAND["aantallen"][tabel] + nieuw
                ids = primaryKeys(tabel, filterProject("SY003"))
                assert min(ids) > TOESTAND["max_pk"][tabel], f"{tabel}: nieuwe primary_keys niet boven het oude maximum"
                TOESTAND["sy003_ids"][tabel] = ids
            else:
                assert aantallen[tabel] == TOESTAND["aantallen"][tabel], f"{tabel}: aantal gewijzigd"
        print(f"\n  Rijen van SY003: { {t: len(i) for t, i in TOESTAND['sy003_ids'].items()} }")

        controleerSY001SY002Ongewijzigd()
        controleerBruikleen()
        controleerElasticsearchGelijkAanTabellen()

    # ----------------------------------------------------------
    # e. Database van SY003 vervangen door die van SY001, één foto verwijderd
    # ----------------------------------------------------------
    def test_06_sy003_vervangen_en_foto_verwijderd(self, mongo_client):
        shutil.copyfile(SY001_MDB, SY003_MDB)
        os.remove(os.path.join(SY003_DIR, "L Fotos", VERWIJDERDE_FOTO))
        TOESTAND["duur"]["e"] = draaiDag("Extract_Transform_Load_Incremental")
        run = controleerRun(mongo_client)
        delta = run["tellingen"]["delta"]["totaal"]
        assert delta["gewijzigd"] == 1 and delta["verwijderd"] == 1, delta

        # SY003 volgt de inhoud van SY001; de foto's van SY003 blijven (op één na). De objectfoto
        # SY003_P4_H11_1_1.jpg verwijst naar put 4 en vondst 11, die SY001 niet heeft: Transform 5
        # (Generate_Missing) maakt die put en vondst aan, zoals bij elke foto zonder bijbehorend record.
        # De andere objectfoto (put 2, vondst 4) past bij een bestaande vondst van SY001.
        gegenereerd_uit_foto = {"Def_Put": 1, "Def_Vondst": 1}
        assert telProject("Def_Vondst", "SY003") == 4 + gegenereerd_uit_foto["Def_Vondst"]
        for tabel in PROJECT_TABELLEN:
            if tabel == "Def_Bestand":
                continue
            assert telProject(tabel, "SY003") == telProject(tabel, "SY001") + gegenereerd_uit_foto.get(tabel, 0), \
                f"{tabel}: SY003 volgt SY001 niet"
        assert telProject("Def_Bestand", "SY003") == len(TOESTAND["sy003_ids"]["Def_Bestand"]) - 1
        assert pgWaarde(f'SELECT COUNT(*) FROM "Def_Bestand" WHERE "fileName" = \'{VERWIJDERDE_FOTO}\'') == 0

        # Geen achtergebleven rijen: alles buiten SY003 is gelijk aan stap a
        aantallen = telTabellen()
        for tabel in LOAD_TABELLEN:
            extra = telProject(tabel, "SY003") if tabel in PROJECT_TABELLEN else 0
            assert aantallen[tabel] == TOESTAND["aantallen"][tabel] + extra, f"{tabel}: achtergebleven rijen"
        controleerSY001SY002Ongewijzigd()
        controleerBruikleen()

        # Elasticsearch gelijk aan de tabellen; verdwenen id's zijn weg
        controleerElasticsearchGelijkAanTabellen()
        for tabel in PROJECT_TABELLEN:
            verdwenen = TOESTAND["sy003_ids"][tabel] - primaryKeys(tabel)
            assert not (verdwenen & esIds(tabel)), f"{tabel}: verdwenen id's staan nog in Elasticsearch"

    # ----------------------------------------------------------
    # f. SY003 verwijderd
    # ----------------------------------------------------------
    def test_07_sy003_verwijderd(self, mongo_client):
        aantal_bestanden = telBestanden(SY003_DIR)
        shutil.rmtree(SY003_DIR)
        TOESTAND["duur"]["f"] = draaiDag("Extract_Transform_Load_Incremental")
        run = controleerRun(mongo_client)
        assert run["tellingen"]["delta"]["totaal"]["verwijderd"] == aantal_bestanden

        for tabel in PROJECT_TABELLEN:
            assert telProject(tabel, "SY003") == 0, f"{tabel}: nog rijen van SY003"
        assert pgWaarde('SELECT COUNT(*) FROM "Def_Bestand" WHERE projectcd = \'SY003\'') == 0
        assert telTabellen() == TOESTAND["aantallen"]
        for tabel in SLEUTEL_TABELLEN:
            assert sleutels(tabel) == TOESTAND["sleutels"][tabel], f"{tabel}: sleutels niet gelijk aan stap a"
        controleerBruikleen()

        # Elasticsearch: geen SY003 meer, gelijk aan stap a
        assert controleerElasticsearchGelijkAanTabellen() == TOESTAND["es"]
        assert esJson('def_bestand/_count?q=projectcd:SY003')["count"] == 0

        # Registratie: alle bestanden van SY003 staan op verwijderd
        statussen = bronbestandStatussen(f"pad LIKE '{PAD_SY003_IN_CONTAINER}%'")
        assert set(statussen) == {"verwijderd"} and statussen["verwijderd"] > 0, statussen
        print(f"\n  Bronbestanden SY003: {statussen}; looptijden: "
              f"{ {k: round(v, 1) for k, v in TOESTAND['duur'].items()} }")
