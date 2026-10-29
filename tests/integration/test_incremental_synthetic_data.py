"""
Integratietest: incrementeel laden met synthetische data (issue 61, fase 3).

Draait eerst de volledige cyclus op SY001 en SY002 en daarna acht keer de
incrementele cyclus (Extract_Transform_Load_Incremental) via
``airflow dags test``:

  a. volledige cyclus: aantallen, sleutels (key → primary_key) en
     Elasticsearch-aantallen vastleggen;
  b. een partij en een bruikleen toevoegen (gebruikersdata) die verwijzen naar
     een artefact en het project SY002;
  c. incrementele run zonder wijzigingen: niets verandert;
  c2. de database van SY002 opnieuw verwerkt zonder inhoudelijke wijziging
     (issue 81): alle rijen krijgen een nieuw _id, maar elke rij van elke tabel
     houdt zijn primary_key, ook artefacten zonder subnr, het artefact met twee
     bronrijen (hetzelfde subnummer, issue 83), monsters en plaatsingen;
  d. project SY003 als kopie van SY002 (database opgravingSY003.mdb, foto's
     SY003_*): SY003 komt erbij met nieuwe primary_keys, SY001/SY002 blijven gelijk;
     daarna een tweede bruikleen voor een artefact van SY003 dat in stap e verdwijnt;
  e. de database van SY003 vervangen door die van SY001 en één foto
     verwijderd: SY003 volgt de nieuwe inhoud, geen achtergebleven rijen; de
     bruikleen van het verdwenen artefact blijft bestaan met een lege
     verwijzing en een markering (issue 73) en alle FK's zijn geldig;
  e2. de database van SY003 weer die van SY002: het artefact keert terug met
     dezelfde key en de bruikleen wordt er weer aan gekoppeld;
  f. SY003 verwijderd: alles weer gelijk aan a; de bruikleen van het SY003-artefact
     is weer losgekoppeld en bestaat nog;
  g. een onleesbare foto in SY003 met drempel 0 (issue 70): de taak
     Controleer_Afbeeldingen faalt, Markeer_Run_Mislukt zet de run op
     'mislukt' en PostgreSQL blijft ongewijzigd;
  h. de onleesbare foto weggehaald: de volgende run slaagt, de openstaande
     entry in Filenames is opgeruimd en alles is weer gelijk aan a;
  h2. (issue 54) een onleesbare Access-database in SY003 (een kapotte kopie): de
     taak Controleer_Databases meldt een waarschuwing, de run slaagt en PostgreSQL
     blijft gelijk aan a;
  i. opnieuw de volledige cyclus (met de kapotte database, dus met een waarschuwing), na een conserveringsproject en een extra
     ABR-materiaal voor het artefact van de bruikleen (issue 71): de
     gebruikerstabellen zijn ongewijzigd (ook de losgekoppelde bruikleen van
     SY003), de bruikleen hangt aan hetzelfde artefact, alle sleutels en
     aantallen zijn gelijk aan a en alle FK's en sequences kloppen. Elke rij
     van elke tabel uit LOAD_TABELLEN heeft dezelfde primary_key als na de
     eerste volledige cyclus (issue 81).

Na elke run worden PostgreSQL (via ``docker exec psql``), MongoDB (run-document),
het verwerkingsrapport (issue 62: JSON en Markdown in de Airflow-container, met de
secties en totalen per tabel gelijk aan PostgreSQL, ook na de bewust mislukte run g)
en Elasticsearch (via ``docker exec curl`` in de Elasticsearch-container; die
heeft geen hostpoort) gecontroleerd. Ook de afgeleide velden (issue 72:
aantal_fotos, aantal_artefacten en de dateringen) worden na de volledige
cyclus en na elke incrementele run gecontroleerd, zonder Flask te herstarten;
na stap a en d ook door ze leeg te maken en init.init() van de webapplicatie
ze in de Flask-container opnieuw te laten berekenen (moet hetzelfde opleveren). De fixture ``sy003_opruimen`` verwijdert
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

import wasstraat.delta_transform as delta_transform
from wasstraat.loadToDatabase_functions import GEBRUIKERS_TABELLEN, LOAD_TABELLEN


# ============================================================
# Configuratie
# ============================================================

MONGO_TEST_URI = os.getenv("MONGO_TEST_URI", "mongodb://testroot:testpass@localhost:27117/")
AIRFLOW_CONTAINER = os.getenv("AIRFLOW_CONTAINER", "wasstraat_airflow_test")
POSTGRES_CONTAINER = os.getenv("POSTGRES_CONTAINER", "wasstraat_postgres_test")
ES_CONTAINER = os.getenv("ES_CONTAINER", "wasstraat_elasticsearch_test")
FLASK_CONTAINER = os.getenv("FLASK_CONTAINER", "wasstraat_flask_test")
DB_STAGING = "Arch_Staging_Test"
DB_FILES = "Arch_Files_Test"

PROJECTEN_DIR = os.path.abspath(os.path.join(
    os.path.dirname(__file__), "..", "..", "data", "synthetic", "data", "projecten"))
SY001_MDB = os.path.join(PROJECTEN_DIR, "SY001", "C Database", "opgravingSY001.mdb")
SY002_DIR = os.path.join(PROJECTEN_DIR, "SY002")
SY002_MDB = os.path.join(SY002_DIR, "C Database", "opgravingSY002.mdb")
SY003_DIR = os.path.join(PROJECTEN_DIR, "SY003")
SY003_MDB = os.path.join(SY003_DIR, "C Database", "opgravingSY003.mdb")
VERWIJDERDE_FOTO = "SY003_F002.jpg"
ONLEESBARE_FOTO = os.path.join(SY003_DIR, "L Fotos", "SY003_onleesbaar.jpg")
KAPOTTE_DATABASE = os.path.join(SY003_DIR, "C Database", "kapot.mdb")
CONTROLETAAK = "Extract_Group.Controleer_Afbeeldingen"
DATABASETAAK = "Extract_Group.Controleer_Databases"

# Verwerkingsrapport (issue 62): secties van het JSON-rapport en koppen van de Markdown
RAPPORT_SECTIES = ["run", "samenvatting", "foutbeleid", "bronbestanden", "objecttotalen", "kwaliteitsmeldingen",
                   "pipeline", "fouten_in_rapport"]
MARKDOWN_KOPPEN = ["## Foutbeleid", "## Bronbestanden", "## Objecttotalen", "## Kwaliteitsmeldingen", "## Pipeline",
                   "### Doorlooptijd per stap", "### Waarschuwingen", "### Access-databases"]
PAD_SY003_IN_CONTAINER = "/input/projecten/SY003/"

# Tabellen waarvan de sleutels (key → primary_key) vastgelegd en vergeleken worden
SLEUTEL_TABELLEN = ["Def_Project", "Def_Put", "Def_Vondst", "Def_Artefact", "Def_Bestand"]
# Tabellen met rijen per project; de key begint met 'P' + projectcode (artefacten: key_subnr|artefactsoort)
PROJECT_TABELLEN = ["Def_Put", "Def_Vlak", "Def_Spoor", "Def_Vondst", "Def_Vulling", "Def_Artefact", "Def_Bestand"]

TESTPARTIJ = "Testpartij incrementeel laden"
TESTCONSERVERING = "Testconservering volledige cyclus"

# Afgeleide velden van Def_Artefact (issue 72); Def_Project heeft aantal_artefacten
AFGELEIDE_KOLOMMEN = ["aantal_fotos", "vondstdatering_vanaf", "vondstdatering_tot", "spoordatering_vanaf",
                      "spoordatering_tot", "datering_vanaf", "datering_tot"]

# Toestand die de genummerde tests met elkaar delen
TOESTAND = {}


# ============================================================
# Helpers
# ============================================================

def draaiDag(dag_id, timeout=1200, omgeving=None, verwacht_mislukt=None):
    """Draai een DAG met ``airflow dags test`` en eis dat de DagRun slaagt (ook alle Index-taken).

    Args:
        dag_id: de DAG
        timeout: maximale looptijd in seconden
        omgeving: extra omgevingsvariabelen voor deze run (``docker exec -e``)
        verwacht_mislukt: lijst met task_id's die moeten mislukken; de DagRun moet dan 'failed' zijn
            en er mogen geen andere taken mislukken

    Returns:
        Tuple (looptijd in seconden, uitvoer van ``airflow dags test``)
    """
    cmd = ["docker", "exec"]
    for naam, waarde in (omgeving or {}).items():
        cmd += ["-e", f"{naam}={waarde}"]
    cmd += [AIRFLOW_CONTAINER, "airflow", "dags", "test", dag_id, "2026-01-01"]
    print(f"\n  ▶ {' '.join(cmd)}")
    start = time.time()
    resultaat = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    uitvoer = resultaat.stdout + "\n" + resultaat.stderr
    duur = time.time() - start
    status = re.findall(r"DagRun Finished: dag_id=\S+.*?state=(\w+)", uitvoer)
    mislukt = sorted(set(re.findall(r"Marking task as FAILED\. dag_id=\S+, task_id=([\w.]+)", uitvoer)))
    if verwacht_mislukt is None:
        geslaagd = resultaat.returncode == 0 and status and status[-1] == "success" and not mislukt
    else:
        geslaagd = status and status[-1] == "failed" and mislukt == sorted(verwacht_mislukt)
    if not geslaagd:
        regels = [r for r in uitvoer.split("\n") if any(w in r for w in ("ERROR", "Error", "Traceback", "FAILED"))]
        for regel in (regels or uitvoer.split("\n"))[-40:]:
            print(f"    {regel}")
        verwacht = "geslaagd" if verwacht_mislukt is None else f"mislukt met alleen {sorted(verwacht_mislukt)}"
        pytest.fail(f"DAG {dag_id} niet {verwacht} (exit {resultaat.returncode}, status {status[-1:]}, "
                    f"mislukte taken {mislukt}) na {duur:.0f}s")
    print(f"  ✓  {dag_id} {'geslaagd' if verwacht_mislukt is None else 'mislukt zoals verwacht'} in {duur:.1f}s")
    return duur, uitvoer


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


def rijIdentiteiten(tabel):
    """Set met (primary_key, key, bronsleutel, map/bestandsnaam) van alle rijen van een tabel (issue 81).

    De bronsleutel wordt uit de kolom brondata afgeleid, zoals Transform 4 dat doet; samen met de
    key en (bij Def_Bestand) map en bestandsnaam identificeert hij een rij ook als de key vaker
    voorkomt. Zo is te zien of een rij na een nieuwe extractie dezelfde primary_key heeft.
    """
    bestand = ', "directory", "fileName"' if tabel == "Def_Bestand" else ""
    rijen = pgRijen(f'SELECT primary_key, {tekst("key")}, {tekst("brondata")}{bestand} FROM "{tabel}"')
    identiteiten = set()
    for rij in rijen:
        brondata = None if rij[2] == "NULL" else delta_transform.leesBrondataTekst(rij[2])
        identiteiten.add((int(rij[0]), None if rij[1] == "NULL" else rij[1],
                          delta_transform.getBronsleutel(brondata), "/".join(rij[3:]) or None))
    return identiteiten


def alleRijIdentiteiten():
    """rijIdentiteiten van alle tabellen uit LOAD_TABELLEN."""
    return {t: rijIdentiteiten(t) for t in LOAD_TABELLEN}


def vergelijkRijIdentiteiten(verwacht):
    """Eis dat elke rij van elke tabel dezelfde primary_key heeft als in verwacht (issue 81)."""
    nu = alleRijIdentiteiten()
    fouten = {}
    for tabel in LOAD_TABELLEN:
        weg, erbij = verwacht[tabel] - nu[tabel], nu[tabel] - verwacht[tabel]
        if weg or erbij:
            fouten[tabel] = {"weg": sorted(weg, key=str)[:3], "erbij": sorted(erbij, key=str)[:3],
                             "aantal": (len(weg), len(erbij))}
    assert not fouten, f"Rijen met een andere primary_key, key of bronsleutel: {fouten}"


def filterProject(projectcd):
    """SQL-voorwaarde voor de rijen van een project (op de key)."""
    return f"key LIKE 'P{projectcd}%'"


def filterNietProject(projectcd):
    """SQL-voorwaarde voor alle rijen die niet bij een project horen (ook rijen zonder key)."""
    return f"COALESCE(key, '') NOT LIKE 'P{projectcd}%'"


def verwijderSy003():
    """Verwijder de map van SY003 op de host en wacht tot de Airflow-container haar niet meer ziet.

    Docker Desktop (macOS) houdt de inhoud van een eerder gelezen map in een
    cache: na een ``os.walk`` door de pipeline blijft een op de host verwijderde
    map voor ``test -e`` in de container meer dan 45 s bestaan, tot de map
    opnieuw wordt gelezen. Daarom leest elke poging eerst de projectenmap
    opnieuw (``ls -R``) en wacht de test tot de map echt weg is; anders zou een
    openstaande Filenames-entry van een eerder mislukte foto blijven staan en
    als mislukt tellen.
    """
    shutil.rmtree(SY003_DIR)
    einde = time.time() + 30
    while time.time() < einde:
        resultaat = subprocess.run(
            ["docker", "exec", AIRFLOW_CONTAINER, "sh", "-c",
             f"ls -R /input/projecten >/dev/null 2>&1; test -e '{PAD_SY003_IN_CONTAINER}'"],
            capture_output=True)
        if resultaat.returncode != 0:
            return
        time.sleep(0.5)
    raise AssertionError(f"{PAD_SY003_IN_CONTAINER} is na 30 s nog zichtbaar in {AIRFLOW_CONTAINER}")


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


def laatsteRun(mongo_client, soort="incrementeel"):
    """Het run-document van de laatste run van een soort (sinds issue 54 bewaard over volledige cycli heen)."""
    return mongo_client[DB_STAGING]["Verwerkingsruns"].find_one(
        {"soort": soort}, sort=[("gestart_op", pymongo.DESCENDING)])


def leesUitContainer(pad):
    """Lees een bestand uit de Airflow-testcontainer (de rapporten staan in AIRFLOW_OUTPUT_RAPPORTEN)."""
    resultaat = subprocess.run(["docker", "exec", AIRFLOW_CONTAINER, "cat", pad], capture_output=True, text=True,
                               timeout=30)
    assert resultaat.returncode == 0, f"{pad} niet te lezen in {AIRFLOW_CONTAINER}: {resultaat.stderr.strip()}"
    return resultaat.stdout


def controleerRapport(run, uitkomst=None):
    """Issue 62: de run heeft een rapport als JSON en Markdown, met alle secties en koppen.

    Het run-document noemt de paden (veld rapport); het rapport hoort bij de run en heeft dezelfde
    status. Met uitkomst wordt ook de uitkomst van het foutbeleid gecontroleerd.

    Returns:
        Tuple (rapport als dict, Markdown-tekst)
    """
    info = run.get("rapport")
    assert info and info.get("json") and info.get("markdown"), f"Run {run['run_id']} heeft geen rapport: {info}"
    assert os.path.basename(info["json"]).startswith(f"verwerkingsrapport_{run['run_id']}_{run['soort']}_")
    rapport = json.loads(leesUitContainer(info["json"]))
    markdown = leesUitContainer(info["markdown"])
    for sectie in RAPPORT_SECTIES:
        assert sectie in rapport, f"Sectie {sectie} ontbreekt in {info['json']}"
    for kop in MARKDOWN_KOPPEN:
        assert f"\n{kop}\n" in markdown, f"Kop {kop} ontbreekt in {info['markdown']}"
    assert markdown.startswith(f"# Verwerkingsrapport {run['run_id']}")
    assert rapport["run"]["run_id"] == run["run_id"] and rapport["run"]["status"] == run["status"]
    assert rapport["fouten_in_rapport"] == [], rapport["fouten_in_rapport"]
    assert info["samenvatting"]["uitkomst"] == rapport["foutbeleid"]["uitkomst"]
    assert rapport["pipeline"]["stappen"], "Geen doorlooptijden per stap"
    if uitkomst is not None:
        assert rapport["foutbeleid"]["uitkomst"] == uitkomst, (
            f"Uitkomst {rapport['foutbeleid']['uitkomst']}, verwacht {uitkomst}; waarschuwingen "
            f"{[m['melding'][:200] for m in rapport['foutbeleid']['waarschuwingen']]}")
    print(f"  Rapport {os.path.basename(info['json'])}: {info['samenvatting']}")
    return rapport, markdown


def controleerObjecttotalen(rapport):
    """De totalen per tabel in het rapport zijn gelijk aan het aantal rijen in PostgreSQL."""
    totalen = {t: v["totaal"] for t, v in rapport["objecttotalen"]["tabellen"].items()}
    assert totalen == telTabellen(), f"Totalen in het rapport {totalen} wijken af van PostgreSQL"


def controleerRun(mongo_client):
    """Controleer dat de laatste incrementele run is afgerond en retourneer het run-document.

    Controleert ook de tellingen van de afbeeldingen (issue 70): geen mislukte of
    onverwerkte bestanden, en precies de nieuwe en gewijzigde afbeeldingen uit de
    delta zijn in deze run verwerkt of overgeslagen.
    """
    run = laatsteRun(mongo_client)
    assert run is not None, "Geen run-document van een incrementele run gevonden"
    assert run["status"] == "afgerond", f"Run {run['run_id']} heeft status {run['status']}: {run.get('melding')}"
    assert "load" in run.get("tellingen", {}), "tellingen.load ontbreekt in het run-document"
    assert "afgeleide_velden" in run["tellingen"], "tellingen.afgeleide_velden ontbreekt in het run-document"
    afbeeldingen = run["tellingen"].get("afbeeldingen")
    assert afbeeldingen is not None, "tellingen.afbeeldingen ontbreekt in het run-document"
    assert afbeeldingen["mislukt"] == 0 and afbeeldingen["onverwerkt"] == 0, afbeeldingen
    delta_afbeeldingen = run["tellingen"]["delta"].get("afbeeldingen", {})
    assert afbeeldingen["totaal"] == delta_afbeeldingen.get("nieuw", 0) + delta_afbeeldingen.get("gewijzigd", 0)
    assert afbeeldingen["verwerkt"] + afbeeldingen["overgeslagen"] == afbeeldingen["totaal"]
    print(f"  Run {run['run_id']}: delta {run['tellingen']['delta']['totaal']}, "
          f"load {run['tellingen']['load']['totaal']}, afbeeldingen "
          f"{ {k: afbeeldingen[k] for k in ('totaal', 'verwerkt', 'overgeslagen', 'mislukt')} }")
    # Foutbeleid (issue 54): geen fouten in het run-document; verwerkingsrapport (issue 62) met kloppende totalen
    assert not [m for m in run.get("meldingen", []) if m["niveau"] == "fout"], run.get("meldingen")
    assert "extractie" in run["tellingen"], "tellingen.extractie (Controleer_Databases) ontbreekt"
    rapport, _ = controleerRapport(run)
    assert rapport["foutbeleid"]["uitkomst"] != "mislukt"
    controleerObjecttotalen(rapport)
    load = run["tellingen"]["load"]
    for tabel, telling in rapport["objecttotalen"]["tabellen"].items():
        if tabel in load:
            assert (telling["aangemaakt"], telling["bijgewerkt"], telling["verwijderd"]) == (
                load[tabel]["ingevoegd"], load[tabel]["bijgewerkt"], load[tabel]["verwijderd"]), tabel
    TOESTAND["rapport"] = rapport
    return run


def controleerBruikleen():
    """De bruikleen uit stap b bestaat nog en zijn artefact heeft dezelfde primary_key en key."""
    b = TOESTAND["bruikleen"]
    rij = pgRijen(f'SELECT "artefactID", "projectID", {tekst("artefact_verdwenen_key")}, '
                  f'{tekst("artefact_verdwenen_op")} FROM "Def_Bruikleen" WHERE primary_key = {b["primary_key"]}')
    assert rij, "De bruikleen is verdwenen"
    assert int(rij[0][0]) == b["artefact_pk"] and int(rij[0][1]) == b["project_pk"]
    assert rij[0][2:] == ["NULL", "NULL"], f"De bruikleen uit stap b heeft een markering: {rij[0][2:]}"
    artefact = pgRijen(f'SELECT key FROM "Def_Artefact" WHERE primary_key = {b["artefact_pk"]}')
    assert artefact and artefact[0][0] == b["artefact_key"], (
        f"Artefact {b['artefact_pk']} van de bruikleen heeft niet meer key {b['artefact_key']}: {artefact}")
    project = pgRijen(f'SELECT projectcd FROM "Def_Project" WHERE primary_key = {b["project_pk"]}')
    assert project and project[0][0] == "SY002"


def bruikleenSY003():
    """De bruikleen van het SY003-artefact (stap d): (artefactID, projectID, markering key, markering tijdstip).

    Lege waarden zijn 'NULL' (zie tekst()); het tijdstip als tekst van PostgreSQL.
    """
    kolommen = ", ".join(tekst(k) for k in ('"artefactID"', '"projectID"', "artefact_verdwenen_key",
                                             "artefact_verdwenen_op"))
    rij = pgRijen(f'SELECT {kolommen} FROM "Def_Bruikleen" '
                  f'WHERE primary_key = {TOESTAND["bruikleen_sy003"]["primary_key"]}')
    assert rij, "De bruikleen van het SY003-artefact is verdwenen"
    return rij[0]


def pgTijd():
    """Het huidige tijdstip van de test-PostgreSQL (LOCALTIMESTAMP, zoals de markering), als tekst."""
    return pgRijen("SELECT LOCALTIMESTAMP::text")[0][0]


def controleerBruikleenSY003Losgekoppeld(run, van, tot):
    """De bruikleen van het SY003-artefact bestaat, zonder artefact, met de key en een tijdstip tussen van en tot.

    De verwijzing naar project SY002 blijft staan; de run telt één losgekoppelde bruikleen.
    """
    b = TOESTAND["bruikleen_sy003"]
    artefact, project, key, op = bruikleenSY003()
    assert artefact == "NULL", f"De bruikleen verwijst nog naar artefact {artefact}"
    assert key == b["artefact_key"], f"Markering {key} in plaats van {b['artefact_key']}"
    binnen_run = pgWaarde(f'SELECT COUNT(*) FROM "Def_Bruikleen" WHERE primary_key = {b["primary_key"]} '
                          f"AND artefact_verdwenen_op BETWEEN '{van}' AND '{tot}'")
    assert op != "NULL" and binnen_run == 1, f"Tijdstip {op} van de markering ligt niet tussen {van} en {tot}"
    assert int(project) == b["project_pk"], "De verwijzing naar het (bestaande) project is gewijzigd"
    telling = run["tellingen"]["gebruikersdata"]["Def_Bruikleen"]["artefactID"]
    assert telling["losgekoppeld"] == 1 and telling["teruggekoppeld"] == 0, telling
    print(f"  Bruikleen {b['primary_key']} losgekoppeld: key {key}, op {op}")


def controleerFkGeldig(run):
    """Geen enkele FK-constraint is NOT VALID (pg_constraint.convalidated) en de run meldt er geen."""
    ongeldig = pgRijen("SELECT conrelid::regclass::text, conname FROM pg_constraint "
                       "WHERE contype = 'f' AND NOT convalidated")
    assert ongeldig == [], f"FK-constraints die NOT VALID zijn: {ongeldig}"
    assert run["tellingen"]["load"]["fk_niet_gevalideerd"] == []


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


def tekst(kolom):
    """SQL-expressie die een kolom als tekst geeft, met 'NULL' voor een lege waarde (psql -A laat lege velden
    aan het eind van de uitvoer anders wegvallen)."""
    return f"COALESCE({kolom}::text, 'NULL')"


def afgeleideVelden():
    """De afgeleide velden (issue 72) per primary_key: artefacten (AFGELEIDE_KOLOMMEN) en projecten."""
    kolommen = ", ".join(tekst(f'"{k}"') for k in AFGELEIDE_KOLOMMEN)
    return {
        "Def_Artefact": {int(r[0]): tuple(r[1:]) for r in pgRijen(f'SELECT primary_key, {kolommen} FROM "Def_Artefact"')},
        "Def_Project": {int(r[0]): r[1] for r in pgRijen(
            f'SELECT primary_key, {tekst("aantal_artefacten")} FROM "Def_Project"')},
    }


def controleerAfgeleideVelden():
    """De afgeleide velden kloppen met een onafhankelijke telling en met de voorrangsregels van de dateringen.

    aantal_fotos: aantal objectfoto's per artefact in Def_Bestand; aantal_artefacten:
    aantal artefacten per project; vondst- en spoordatering: die van de vondst en
    zijn spoor; datering_vanaf en datering_tot: artefact, anders vondst, anders spoor
    ('anders' = leeg of 0, zoals de observers van models.py in init.init()).

    Returns:
        Dict met het aantal artefacten met foto's en met een datering (ter controle van de dekking)
    """
    fout_fotos = pgWaarde('''SELECT COUNT(*) FROM "Def_Artefact" a WHERE a.aantal_fotos IS DISTINCT FROM
        (SELECT COUNT(*) FROM "Def_Bestand" b WHERE b."artefactID" = a.primary_key AND b.bestandsoort::text = 'Objectfoto')''')
    assert fout_fotos == 0, f"{fout_fotos} artefacten met een verkeerd aantal_fotos"
    fout_projecten = pgWaarde('''SELECT COUNT(*) FROM "Def_Project" p WHERE p.aantal_artefacten IS DISTINCT FROM
        (SELECT COUNT(*) FROM "Def_Artefact" a WHERE a."projectID" = p.primary_key)''')
    assert fout_projecten == 0, f"{fout_projecten} projecten met een verkeerd aantal_artefacten"

    rijen = pgRijen('''SELECT a.primary_key, ''' + ", ".join(tekst(k) for k in [
        "a.artefactdatering_vanaf", "a.artefactdatering_tot", "v.vondstdatering_vanaf", "v.vondstdatering_tot",
        "s.spoordatering_vanaf", "s.spoordatering_tot", "a.vondstdatering_vanaf", "a.vondstdatering_tot",
        "a.spoordatering_vanaf", "a.spoordatering_tot", "a.datering_vanaf", "a.datering_tot"]) + '''
        FROM "Def_Artefact" a
        LEFT JOIN "Def_Vondst" v ON v.primary_key = a."vondstID"
        LEFT JOIN "Def_Spoor" s ON s.primary_key = v."spoorID"''')
    fouten = []
    for rij in rijen:
        art_van, art_tot, vnd_van, vnd_tot, spr_van, spr_tot = [None if w == "NULL" else int(w) for w in rij[1:7]]
        opgeslagen = [None if w == "NULL" else int(w) for w in rij[7:]]
        verwacht = [vnd_van, vnd_tot, spr_van, spr_tot,
                    art_van if art_van else (vnd_van if vnd_van else spr_van),
                    art_tot if art_tot else (vnd_tot if vnd_tot else spr_tot)]
        if opgeslagen != verwacht:
            fouten.append(f"artefact {rij[0]}: {opgeslagen} in plaats van {verwacht}")
    assert not fouten, f"{len(fouten)} artefacten met verkeerde dateringen: {fouten[:5]}"

    dekking = {
        "met_fotos": pgWaarde('SELECT COUNT(*) FROM "Def_Artefact" WHERE aantal_fotos > 0'),
        "met_datering": pgWaarde('SELECT COUNT(*) FROM "Def_Artefact" WHERE datering_vanaf IS NOT NULL'),
        "artefacten": len(rijen),
    }
    print(f"  Afgeleide velden kloppen: {dekking}")
    return dekking


def vergelijkMetFlaskInit():
    """De afgeleide velden van de pipeline zijn gelijk aan die van init.init() in de webapplicatie.

    Legt de velden vast, maakt ze leeg en laat init.init() (ORM, models.py met de
    observers) ze in de Flask-container opnieuw berekenen. init.init() vangt zijn
    eigen fouten af; een mislukte berekening laat de velden leeg en valt zo op.
    """
    pipeline = afgeleideVelden()
    pgRijen('UPDATE "Def_Artefact" SET ' + ", ".join(f'"{k}" = NULL' for k in AFGELEIDE_KOLOMMEN))
    pgRijen('UPDATE "Def_Project" SET aantal_artefacten = NULL')
    script = "import logging; logging.basicConfig(level=logging.INFO); import init; init.init()"
    resultaat = subprocess.run(["docker", "exec", FLASK_CONTAINER, "python", "-c", script],
                               capture_output=True, text=True, timeout=600)
    assert resultaat.returncode == 0 and "Error while Initializing" not in resultaat.stderr, \
        f"init.init() in {FLASK_CONTAINER} mislukt: {resultaat.stderr[-2000:]}"
    flask = afgeleideVelden()
    verschillen = [(pk, waarden, flask["Def_Artefact"].get(pk)) for pk, waarden in pipeline["Def_Artefact"].items()
                   if flask["Def_Artefact"].get(pk) != waarden]
    assert not verschillen, (f"{len(verschillen)} artefacten wijken af van init.init() "
                             f"(primary_key, pipeline, init): {verschillen[:5]}")
    assert flask == pipeline
    print(f"  Gelijk aan init.init() van de webapplicatie: {len(pipeline['Def_Artefact'])} artefacten, "
          f"{len(pipeline['Def_Project'])} projecten")


def controleerAantalFotosInElasticsearch():
    """aantal_fotos in de index van Def_Artefact is gelijk aan PostgreSQL, als de kolom geïndexeerd wordt.

    shared/fulltext.getCols indexeert alleen primary_key en tekstkolommen; de
    afgeleide velden zijn getallen en staan dan niet in de index.
    """
    mapping = esJson("def_artefact/_mapping")
    velden = set()
    for index in mapping.values():
        velden.update(index.get("mappings", {}).get("properties", {}))
    if "aantal_fotos" not in velden:
        print("  aantal_fotos staat niet in de index van Def_Artefact (alleen tekstkolommen worden geïndexeerd)")
        return
    antwoord = esJson("def_artefact/_search?size=10000&_source=aantal_fotos&filter_path=hits.hits._id,hits.hits._source")
    in_es = {int(h["_id"]): h["_source"].get("aantal_fotos") for h in antwoord.get("hits", {}).get("hits", [])}
    in_pg = {int(r[0]): r[1] for r in pgRijen('SELECT primary_key, COALESCE(aantal_fotos::text, \'\') FROM "Def_Artefact"')}
    assert in_es == in_pg, "aantal_fotos in Elasticsearch wijkt af van PostgreSQL"


def afgeleideVeldenPerKey(projectcd, ander_projectcd):
    """Gesorteerde lijst (key met ander_projectcd in plaats van projectcd, afgeleide velden) van de artefacten van een project.

    Keys zijn niet altijd uniek, daarom een gesorteerde lijst in plaats van een dict. De projectcode
    wordt overal in de key vervangen, ook in het pad van de hulpsleutel van artefacten zonder subnr
    (bron:projecten/SY003/C Database/opgravingSY003.mdb:...).
    """
    kolommen = ", ".join(tekst(f'"{k}"') for k in AFGELEIDE_KOLOMMEN)
    rijen = pgRijen(f'SELECT replace(key, \'{projectcd}\', \'{ander_projectcd}\'), {kolommen} '
                    f'FROM "Def_Artefact" WHERE {filterProject(projectcd)}')
    return sorted(tuple(r) for r in rijen)


def alleTellingenNul(afgeleid):
    """True als de herberekening in tellingen.afgeleide_velden niets heeft gewijzigd."""
    return all(aantal == 0 for tabel in afgeleid.values() for aantal in tabel.values())


def gebruikersTabellen():
    """De volledige inhoud van de gebruikerstabellen: per tabel een gesorteerde lijst met rijen als tekst."""
    return {t: sorted(r[0] for r in pgRijen(f'SELECT t::text FROM "{t}" AS t')) for t in GEBRUIKERS_TABELLEN}


def controleerSequences(tabellen):
    """Elke tabel heeft een sequence op primary_key met nextval boven max(primary_key) (zonder nextval aan te roepen)."""
    for tabel in tabellen:
        sequence = pgRijen(f"SELECT COALESCE(pg_get_serial_sequence('\"{tabel}\"', 'primary_key'), '')")[0][0]
        assert sequence, f"{tabel}.primary_key heeft geen sequence"
        maximum = pgWaarde(f'SELECT COALESCE(MAX(primary_key), -1) FROM "{tabel}"')
        volgende = pgWaarde(f"SELECT CASE WHEN is_called THEN last_value + 1 ELSE last_value END FROM {sequence}")
        assert volgende > maximum, f"{tabel}: volgende primary_key {volgende} niet boven max(primary_key) {maximum}"


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
    """Verwijder het testproject SY003 vóór en na de test (ook bij falen), en de testgebruikersdata achteraf."""
    shutil.rmtree(SY003_DIR, ignore_errors=True)
    try:
        yield
    finally:
        shutil.rmtree(SY003_DIR, ignore_errors=True)
        try:
            testpartij = f'(SELECT primary_key FROM "Def_Partij" WHERE naam = \'{TESTPARTIJ}\')'
            pgRijen(f'DELETE FROM "Def_artefact_conservering" WHERE conservering_id IN '
                    f'(SELECT primary_key FROM "Def_Conserveringsproject" WHERE "uitvoerderID" IN {testpartij})')
            pgRijen(f'DELETE FROM "Def_Conserveringsproject" WHERE "uitvoerderID" IN {testpartij}')
            if "abr_koppeling" in TOESTAND:
                pgRijen(f'DELETE FROM "Def_artefact_abr" WHERE id = {TOESTAND["abr_koppeling"]}')
            pgRijen(f'DELETE FROM "Def_Bruikleen" WHERE "partijID" IN {testpartij}')
            pgRijen(f'DELETE FROM "Def_Partij" WHERE naam = \'{TESTPARTIJ}\'')
        except Exception as err:
            print(f"  (testbruikleen niet opgeruimd: {err})")


# ============================================================
# Tests
# ============================================================

@pytest.mark.integration
@pytest.mark.load
class TestIncrementeelSynthetic:
    """Volledige cyclus, acht incrementele runs op SY001, SY002 en een tijdelijk project SY003, en opnieuw de volledige cyclus."""

    # ----------------------------------------------------------
    # a. Volledige cyclus
    # ----------------------------------------------------------
    def test_01_volledige_cyclus(self, mongo_client):
        assert not os.path.exists(SY003_DIR)
        duur, uitvoer = draaiDag("Extract_Transform_Load_Full_Cycle")
        TOESTAND["duur"] = {"volledig": duur}
        assert re.search(rf"Marking task as SUCCESS\. dag_id=\S+, task_id={re.escape(CONTROLETAAK)},", uitvoer), \
            f"{CONTROLETAAK} niet geslaagd in de volledige cyclus"
        filenames = mongo_client[DB_FILES]["Filenames"]
        assert filenames.count_documents({"processed": False}) == 0, "Onverwerkte of mislukte afbeeldingen"

        # Issue 54: de volledige cyclus heeft vanaf het begin een run-document met tellingen en meldingen
        run = laatsteRun(mongo_client, "volledig")
        assert run["status"] == "afgerond" and run["dag_id"] == "Extract_Transform_Load_Full_Cycle", run.get("melding")
        for telling in ["extractie", "afbeeldingen", "load", "gebruikersdata", "afgeleide_velden", "registratie"]:
            assert telling in run["tellingen"], f"tellingen.{telling} ontbreekt in het run-document van de volledige cyclus"
        assert run["tellingen"]["extractie"]["onleesbaar"] == 0 and run["tellingen"]["extractie"]["databases"] > 0
        assert not [m for m in run["meldingen"] if m["niveau"] == "fout"], run["meldingen"]
        TOESTAND["volledig"] = run

        # Issue 62: het rapport, met totalen gelijk aan PostgreSQL en de bronbestanden van de registratie
        rapport, markdown = controleerRapport(run)
        controleerObjecttotalen(rapport)
        geregistreerd = {r[0]: int(r[1]) for r in pgRijen(
            f'SELECT categorie, COUNT(*) FROM "Def_Bronbestand" WHERE run_id = \'{run["run_id"]}\' GROUP BY categorie')}
        # Het rapport telt ook de paden die paden_overslaan (correcties.yml) overslaat; die zijn niet geregistreerd
        overgeslagen = rapport["bronbestanden"]["paden_overgeslagen"]
        in_rapport = {c: sum(t.values()) - overgeslagen.get(c, 0) for c, t in rapport["bronbestanden"]["totalen"].items()}
        assert {c: n for c, n in in_rapport.items() if n} == geregistreerd, (
            f"Bronbestanden in het rapport {in_rapport} (zonder {overgeslagen}), geregistreerd {geregistreerd}")
        assert rapport["bronbestanden"]["registratie_uitgevoerd"] is True
        assert all(t["status"] == "success" for t in rapport["pipeline"]["taken"]
                   if not t["taak"].endswith("Markeer_Run_Mislukt")), "Niet alle taken geslaagd volgens het rapport"
        stappen = [s["stap"] for s in rapport["pipeline"]["stappen"]]
        for stap in ["voorbereiding", "extractie", "transform1", "transform2", "transform3", "transform5",
                     "transform4", "load", "index", "registratie"]:
            assert stap in stappen, f"Stap {stap} ontbreekt in de doorlooptijden"

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

        # Issue 81: de synthetische data heeft artefacten zonder subnr (hulpsleutel uit de bronrij) en
        # twee bronrijen met hetzelfde subnummer; monsters en plaatsingen hebben een key
        zonder_subnr = pgRijen('SELECT key FROM "Def_Artefact" WHERE key LIKE \'PSY002%|bron:%\' ORDER BY key')
        assert len(zonder_subnr) == 2, f"Verwacht twee artefacten zonder subnr in SY002: {zonder_subnr}"
        assert zonder_subnr[0][0].startswith("PSY002P3V7|Aardewerk|bron:projecten/SY002/C Database/opgravingSY002.mdb:AARDEWERK 1:")
        # Issue 83: de twee rijen met hetzelfde subnummer worden samengevoegd tot één artefact met twee
        # bronrijen (tot dan bleef de verplaatste rij er ook naast staan, met dezelfde key)
        assert pgWaarde('SELECT COUNT(*) FROM "Def_Artefact" WHERE key = \'PSY002P1V1A2|Aardewerk\'') == 1
        for tabel in ["Def_Artefact", "Def_Plaatsing", "Def_Monster_Botanie", "Def_Monster_Schelp", "Def_Monster"]:
            assert pgWaarde(f'SELECT COUNT(*) FROM "{tabel}"') > 0, f"{tabel} heeft geen rijen: de test dekt die tabel niet"
            assert pgWaarde(f'SELECT COUNT(*) FROM "{tabel}" WHERE key IS NULL') == 0, f"{tabel} heeft rijen zonder key"
        assert pgWaarde('SELECT COUNT(*) FROM "Def_Plaatsing" WHERE key NOT LIKE \'bron:magazijnlijst/%\'') == 0
        assert pgWaarde('SELECT COUNT(*) FROM "Def_Monster_Botanie" WHERE key !~ \'^M.+ID[0-9]+$\'') == 0
        assert pgWaarde('SELECT COUNT(*) FROM "Def_Monster_Schelp" WHERE key !~ \'^M.+ID[0-9]+$\'') == 0
        TOESTAND["identiteiten"] = alleRijIdentiteiten()
        for tabel, identiteiten in TOESTAND["identiteiten"].items():
            if tabel == "Def_ABR":
                continue  # de ABR wordt op de primary_key uit de bron teruggevonden
            zonder_pk = [i[1:] for i in identiteiten]
            assert len(set(zonder_pk)) == len(zonder_pk), f"{tabel}: rijen die niet van elkaar te onderscheiden zijn"

        # De Index-taken van de volledige cyclus zijn geslaagd: Elasticsearch gelijk aan PostgreSQL
        TOESTAND["es"] = controleerElasticsearchGelijkAanTabellen()

        # De volledige cyclus registreert alle bronbestanden (SY003 kan van een eerdere testrun als verwijderd staan)
        statussen = bronbestandStatussen(f"pad NOT LIKE '{PAD_SY003_IN_CONTAINER}%'")
        assert set(statussen) == {"verwerkt"} and statussen["verwerkt"] > 0, statussen
        TOESTAND["bronbestanden"] = statussen["verwerkt"]

    def test_02b_afgeleide_velden_na_volledige_cyclus(self):
        """Issue 72: de volledige cyclus vult de afgeleide velden zelf, zonder Flask te herstarten,
        met dezelfde uitkomst als init.init() van de webapplicatie."""
        dekking = controleerAfgeleideVelden()
        assert dekking["met_fotos"] > 0, "Geen artefact met objectfoto's: de test dekt aantal_fotos niet"
        assert dekking["met_datering"] > 0, "Geen artefact met een datering: de test dekt de dateringen niet"
        assert pgWaarde('SELECT COUNT(*) FROM "Def_Project" WHERE aantal_artefacten > 0') == 2
        vergelijkMetFlaskInit()
        controleerAantalFotosInElasticsearch()
        TOESTAND["afgeleid"] = afgeleideVelden()

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
        TOESTAND["duur"]["c"], _ = draaiDag("Extract_Transform_Load_Incremental")
        run = controleerRun(mongo_client)
        assert TOESTAND["rapport"]["foutbeleid"]["uitkomst"] == "geslaagd", TOESTAND["rapport"]["foutbeleid"]
        assert all(t["aangemaakt"] == 0 and t["verwijderd"] == 0
                   for t in TOESTAND["rapport"]["objecttotalen"]["tabellen"].values())
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

        # Afgeleide velden: niets herschreven, gelijk aan stap a
        assert alleTellingenNul(run["tellingen"]["afgeleide_velden"]), run["tellingen"]["afgeleide_velden"]
        assert afgeleideVelden() == TOESTAND["afgeleid"]
        vergelijkRijIdentiteiten(TOESTAND["identiteiten"])

    # ----------------------------------------------------------
    # c2. SY002 opnieuw verwerkt zonder inhoudelijke wijziging (issue 81)
    # ----------------------------------------------------------
    def test_04b_ongewijzigde_database_opnieuw_verwerkt(self, mongo_client):
        """Een opnieuw ingelezen database met dezelfde inhoud verandert geen enkele primary_key.

        De registratie van opgravingSY002.mdb krijgt een andere vingerafdruk, zodat de incrementele run
        de database als gewijzigd opnieuw verwerkt: alle documenten van SY002 krijgen een nieuw _id. Elke
        rij houdt zijn primary_key: op de unieke key (sinds issue 83 ook het artefact PSY002P1V1A2|Aardewerk
        met twee bronrijen, dat niet meer dubbel voorkomt), en anders op de bronsleutel.
        """
        pad = "/input/projecten/SY002/C Database/opgravingSY002.mdb"
        assert pgWaarde(f"SELECT COUNT(*) FROM \"Def_Bronbestand\" WHERE pad = '{pad}'") == 1
        pgRijen(f"UPDATE \"Def_Bronbestand\" SET sha256 = repeat('0', 64), mtime = 0 WHERE pad = '{pad}'")
        TOESTAND["duur"]["c2"], _ = draaiDag("Extract_Transform_Load_Incremental")
        run = controleerRun(mongo_client)
        delta = run["tellingen"]["delta"]["totaal"]
        assert delta["gewijzigd"] == 1 and delta["nieuw"] == 0 and delta["verwijderd"] == 0, delta
        load = run["tellingen"]["load"]["totaal"]
        assert load["ingevoegd"] == 0 and load["verwijderd"] == 0, load

        sleutels_t4 = run["tellingen"]["transform"]["primary_keys"]
        print(f"\n  Transform 4 Artefact: {sleutels_t4['Artefact']}")
        # Soorten zonder tabel (Fotobeschrijving, Fotokoppel) worden niet geladen en krijgen altijd nieuwe ID's
        nieuw = {soort: telling["nieuw"] for soort, telling in sleutels_t4.items()
                 if telling.get("tabel") and telling.get("nieuw")}
        assert not nieuw, f"Transform 4 deelde nieuwe nummers uit: {nieuw}"
        assert sleutels_t4["Artefact"]["op_key"] >= 1, "Geen artefact op de key teruggevonden"

        assert telTabellen() == TOESTAND["aantallen"]
        vergelijkRijIdentiteiten(TOESTAND["identiteiten"])
        controleerBruikleen()
        telling = run["tellingen"]["gebruikersdata"]["Def_Bruikleen"]["artefactID"]
        assert telling["losgekoppeld"] == 0, telling
        assert esAantallen() == TOESTAND["es"]
        assert afgeleideVelden() == TOESTAND["afgeleid"]
        statussen = bronbestandStatussen(f"pad NOT LIKE '{PAD_SY003_IN_CONTAINER}%'")
        assert statussen == {"verwerkt": TOESTAND["bronbestanden"]}, statussen

    # ----------------------------------------------------------
    # d. Nieuw project SY003 (kopie van SY002)
    # ----------------------------------------------------------
    def test_05_nieuw_project_sy003(self, mongo_client):
        maakSY003AlsKopieVanSY002()
        TOESTAND["duur"]["d"], _ = draaiDag("Extract_Transform_Load_Incremental")
        run = controleerRun(mongo_client)
        assert run["tellingen"]["delta"]["totaal"]["nieuw"] == telBestanden(SY003_DIR)
        assert run["tellingen"]["afbeeldingen"]["verwerkt"] > 0, "Geen foto's van SY003 verwerkt"

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
        # Het rapport noemt per tabel precies de nieuwe rijen van SY003 als aangemaakt (issue 62)
        for tabel, ids in TOESTAND["sy003_ids"].items():
            assert TOESTAND["rapport"]["objecttotalen"]["tabellen"][tabel]["aangemaakt"] == len(ids), tabel
        bronnen = {b["bestand"] for b in TOESTAND["rapport"]["bronbestanden"]["bestanden"]}
        assert any(PAD_SY003_IN_CONTAINER in b and b.endswith("opgravingSY003.mdb") for b in bronnen), bronnen

        controleerSY001SY002Ongewijzigd()
        controleerBruikleen()
        controleerElasticsearchGelijkAanTabellen()

        # Afgeleide velden (issue 72): de nieuwe artefacten zijn bijgewerkt (leeg → waarde), de bestaande
        # rijen niet; SY003 heeft dezelfde waarden als SY002, waarvan het een kopie is. SY003 staat niet in
        # de projectenlijst en krijgt dus geen rij in Def_Project (aantal ongewijzigd, zie hierboven); de
        # aantallen artefacten van SY001 en SY002 veranderen niet.
        afgeleid = run["tellingen"]["afgeleide_velden"]
        print(f"  Afgeleide velden: {afgeleid}")
        nieuwe_artefacten = len(TOESTAND["sy003_ids"]["Def_Artefact"])
        assert afgeleid["Def_Artefact"]["aantal_fotos"] == nieuwe_artefacten
        assert afgeleid["Def_Artefact"]["rijen"] == nieuwe_artefacten
        assert afgeleid["Def_Project"] == {"aantal_artefacten": 0, "rijen": 0}
        controleerAfgeleideVelden()
        assert afgeleideVeldenPerKey("SY003", "SY002") == afgeleideVeldenPerKey("SY002", "SY002")
        nu = afgeleideVelden()
        for tabel, rijen in TOESTAND["afgeleid"].items():
            assert {pk: nu[tabel][pk] for pk in rijen} == rijen, f"{tabel}: afgeleide velden van SY001/SY002 gewijzigd"
        vergelijkMetFlaskInit()
        controleerAantalFotosInElasticsearch()

    def test_05b_bruikleen_voor_artefact_van_sy003(self):
        """Issue 73: een bruikleen voor een artefact van SY003 dat in stap e verdwijnt.

        In stap e krijgt SY003 de inhoud van SY001; een artefact van SY003 (kopie van SY002) waarvan
        de key met SY003 in plaats van SY001 niet bij SY001 voorkomt, verdwijnt dan. SY003 staat
        niet in de projectenlijst (geen rij in Def_Project); de bruikleen hangt aan project SY002.
        """
        keys_na_e = {r[0] for r in pgRijen(f"SELECT replace(key, 'PSY001', 'PSY003') FROM \"Def_Artefact\" "
                                            f"WHERE {filterProject('SY001')}")}
        rijen_sy003 = pgRijen(f'SELECT primary_key, key FROM "Def_Artefact" WHERE {filterProject("SY003")} '
                              f'ORDER BY primary_key')
        aantal_per_key = {}
        for _, key in rijen_sy003:
            aantal_per_key[key] = aantal_per_key.get(key, 0) + 1
        # Een key die vaker voorkomt is niet terug te koppelen (issue 81); daarom alleen unieke keys
        kandidaten = [r for r in rijen_sy003 if r[1] not in keys_na_e and aantal_per_key[r[1]] == 1]
        assert kandidaten, "Geen artefact van SY003 dat in stap e verdwijnt"
        artefact_pk, artefact_key = int(kandidaten[0][0]), kandidaten[0][1]
        assert pgWaarde(f"SELECT COUNT(*) FROM \"Def_Artefact\" WHERE key = '{artefact_key}'") == 1
        b = TOESTAND["bruikleen"]
        bruikleen_pk = pgWaarde(
            f'INSERT INTO "Def_Bruikleen" (datum_uitgeleend, "projectID", "artefactID", "partijID") '
            f'VALUES (DATE \'2026-10-15\', {b["project_pk"]}, {artefact_pk}, {b["partij_pk"]}) RETURNING primary_key')
        TOESTAND["bruikleen_sy003"] = {"primary_key": bruikleen_pk, "artefact_pk": artefact_pk,
                                       "artefact_key": artefact_key, "project_pk": b["project_pk"]}
        print(f"\n  Bruikleen SY003 {TOESTAND['bruikleen_sy003']}")
        assert bruikleenSY003() == [str(artefact_pk), str(b["project_pk"]), "NULL", "NULL"]

    # ----------------------------------------------------------
    # e. Database van SY003 vervangen door die van SY001, één foto verwijderd
    # ----------------------------------------------------------
    def test_06_sy003_vervangen_en_foto_verwijderd(self, mongo_client):
        shutil.copyfile(SY001_MDB, SY003_MDB)
        os.remove(os.path.join(SY003_DIR, "L Fotos", VERWIJDERDE_FOTO))
        van = pgTijd()
        TOESTAND["duur"]["e"], _ = draaiDag("Extract_Transform_Load_Incremental")
        tot = pgTijd()
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

        # Afgeleide velden (issue 72) volgen de nieuwe inhoud van SY003
        print(f"  Afgeleide velden: {run['tellingen']['afgeleide_velden']}")
        controleerAfgeleideVelden()

        # Issue 73: het artefact van de bruikleen is verdwenen; de bruikleen blijft bestaan met een lege
        # verwijzing en een markering (key en tijdstip), de bruikleen uit stap b is ongemoeid (hierboven) en
        # alle FK's zijn geldig
        b = TOESTAND["bruikleen_sy003"]
        assert pgWaarde(f'SELECT COUNT(*) FROM "Def_Artefact" WHERE primary_key = {b["artefact_pk"]} '
                        f"OR key = '{b['artefact_key']}'") == 0, "Het artefact van de bruikleen bestaat nog"
        controleerBruikleenSY003Losgekoppeld(run, van, tot)
        controleerFkGeldig(run)
        print(f"  Gebruikersdata: {run['tellingen']['gebruikersdata']}")

    # ----------------------------------------------------------
    # e2. Database van SY003 weer die van SY002: het artefact keert terug
    # ----------------------------------------------------------
    def test_06b_artefact_keert_terug(self, mongo_client):
        """Issue 73: een artefact met dezelfde key keert terug; de bruikleen wordt er weer aan gekoppeld."""
        shutil.copyfile(SY002_MDB, SY003_MDB)
        TOESTAND["duur"]["e2"], _ = draaiDag("Extract_Transform_Load_Incremental")
        run = controleerRun(mongo_client)
        delta = run["tellingen"]["delta"]["totaal"]
        assert delta["gewijzigd"] == 1 and delta["nieuw"] == 0 and delta["verwijderd"] == 0, delta
        assert telProject("Def_Artefact", "SY003") == telProject("Def_Artefact", "SY002")

        b = TOESTAND["bruikleen_sy003"]
        teruggekeerd = pgRijen(f"SELECT primary_key FROM \"Def_Artefact\" WHERE key = '{b['artefact_key']}'")
        assert len(teruggekeerd) == 1, f"Artefact {b['artefact_key']} is niet (eenmaal) teruggekeerd: {teruggekeerd}"
        assert bruikleenSY003() == [teruggekeerd[0][0], str(b["project_pk"]), "NULL", "NULL"]
        telling = run["tellingen"]["gebruikersdata"]["Def_Bruikleen"]["artefactID"]
        assert telling == {"losgekoppeld": 0, "teruggekoppeld": 1, "dubbele_key": 0}, telling
        print(f"  Bruikleen {b['primary_key']} weer gekoppeld aan artefact {teruggekeerd[0][0]} "
              f"(was {b['artefact_pk']})")

        controleerSY001SY002Ongewijzigd()
        controleerBruikleen()
        controleerFkGeldig(run)
        controleerElasticsearchGelijkAanTabellen()
        controleerAfgeleideVelden()

    # ----------------------------------------------------------
    # f. SY003 verwijderd
    # ----------------------------------------------------------
    def test_07_sy003_verwijderd(self, mongo_client):
        aantal_bestanden = telBestanden(SY003_DIR)
        verwijderSy003()
        van = pgTijd()
        TOESTAND["duur"]["f"], _ = draaiDag("Extract_Transform_Load_Incremental")
        tot = pgTijd()
        run = controleerRun(mongo_client)
        assert run["tellingen"]["delta"]["totaal"]["verwijderd"] == aantal_bestanden

        for tabel in PROJECT_TABELLEN:
            assert telProject(tabel, "SY003") == 0, f"{tabel}: nog rijen van SY003"
        assert pgWaarde('SELECT COUNT(*) FROM "Def_Bestand" WHERE projectcd = \'SY003\'') == 0
        assert telTabellen() == TOESTAND["aantallen"]
        for tabel in SLEUTEL_TABELLEN:
            assert sleutels(tabel) == TOESTAND["sleutels"][tabel], f"{tabel}: sleutels niet gelijk aan stap a"
        controleerBruikleen()

        # Issue 73: het artefact van de bruikleen is met SY003 weer verdwenen; de bruikleen bestaat nog
        controleerBruikleenSY003Losgekoppeld(run, van, tot)
        controleerFkGeldig(run)

        # Elasticsearch: geen SY003 meer, gelijk aan stap a
        assert controleerElasticsearchGelijkAanTabellen() == TOESTAND["es"]
        assert esJson('def_bestand/_count?q=projectcd:SY003')["count"] == 0

        # Afgeleide velden (issue 72): de overgebleven rijen veranderen niet en zijn gelijk aan stap a
        assert alleTellingenNul(run["tellingen"]["afgeleide_velden"]), run["tellingen"]["afgeleide_velden"]
        assert afgeleideVelden() == TOESTAND["afgeleid"]

        # Registratie: alle bestanden van SY003 staan op verwijderd
        statussen = bronbestandStatussen(f"pad LIKE '{PAD_SY003_IN_CONTAINER}%'")
        assert set(statussen) == {"verwijderd"} and statussen["verwijderd"] > 0, statussen
        print(f"\n  Bronbestanden SY003: {statussen}; looptijden: "
              f"{ {k: round(v, 1) for k, v in TOESTAND['duur'].items()} }")

    # ----------------------------------------------------------
    # g. Onleesbare foto boven de drempel (issue 70)
    # ----------------------------------------------------------
    def test_08_onleesbare_foto_boven_drempel(self, mongo_client):
        """Controleer_Afbeeldingen faalt bij drempel 0; Markeer_Run_Mislukt zet de run op 'mislukt'."""
        os.makedirs(os.path.dirname(ONLEESBARE_FOTO), exist_ok=True)
        with open(ONLEESBARE_FOTO, "wb") as f:
            f.write(b"dit is geen afbeelding")
        drempel_nul = {"AIRFLOW_MAX_MISLUKTE_AFBEELDINGEN": "0", "AIRFLOW_MAX_MISLUKTE_AFBEELDINGEN_PCT": "0"}
        TOESTAND["duur"]["g"], uitvoer = draaiDag("Extract_Transform_Load_Incremental", omgeving=drempel_nul,
                                                  verwacht_mislukt=[CONTROLETAAK])
        assert re.search(r"Marking task as SUCCESS\. dag_id=\S+, task_id=Markeer_Run_Mislukt,", uitvoer), \
            "Markeer_Run_Mislukt is niet geslaagd"
        # De controle faalt direct (AirflowFailException), zonder herhalingen
        herhaald = sorted(set(re.findall(r"Marking task as UP_FOR_RETRY\. dag_id=\S+, task_id=([\w.]+)", uitvoer)))
        for regel in [r for r in uitvoer.split("\n") if "UP_FOR_RETRY" in r or "Immediate failure" in r][:10]:
            print(f"    {regel[:300]}")
        assert CONTROLETAAK not in herhaald, f"{CONTROLETAAK} is herhaald: {herhaald}"
        assert "SY003_onleesbaar.jpg" in uitvoer, "De foutmelding noemt het onleesbare bestand niet"

        run = laatsteRun(mongo_client)
        assert run["status"] == "mislukt", f"Run {run['run_id']} heeft status {run['status']}"
        afbeeldingen = run["tellingen"]["afbeeldingen"]
        assert afbeeldingen["totaal"] == 1 and afbeeldingen["mislukt"] == 1, afbeeldingen
        assert afbeeldingen["boven_drempel"] is True and afbeeldingen["drempel"] == 0
        assert afbeeldingen["voorbeelden"][0]["filename"].endswith("SY003_onleesbaar.jpg")
        assert afbeeldingen["voorbeelden"][0]["fout"]
        assert "load" not in run["tellingen"], "De run is na de mislukte controle toch doorgegaan naar de load"

        doc = mongo_client[DB_FILES]["Filenames"].find_one({"filename": {"$regex": "SY003_onleesbaar\\.jpg$"}})
        assert doc is not None and doc["processed"] is False and doc.get("fout") and doc.get("fout_op")

        # Niets geladen: PostgreSQL gelijk aan stap a
        assert telTabellen() == TOESTAND["aantallen"]
        controleerBruikleen()

        # Issue 54: de fout staat in de meldingen van het run-document (met de foto) en de run noemt de taak
        assert run["melding"] == f"Mislukte taak in Airflow-run {run['airflow_run_id']}: {CONTROLETAAK}.", run["melding"]
        fouten = [m for m in run["meldingen"] if m["niveau"] == "fout"]
        assert [m["taak"] for m in fouten] == [CONTROLETAAK], fouten
        assert fouten[0]["soort"] == "afbeeldingen_mislukt"
        assert fouten[0]["details"][0]["filename"].endswith("SY003_onleesbaar.jpg")

        # Issue 62: ook na een bewust mislukte run is er een rapport, dat de fout en de stoppende taak noemt
        rapport, markdown = controleerRapport(run, uitkomst="mislukt")
        assert rapport["foutbeleid"]["gestopt_door"]["taak"] == CONTROLETAAK
        assert "drempel" in rapport["foutbeleid"]["gestopt_door"]["melding"]
        assert rapport["objecttotalen"]["load_uitgevoerd"] is False
        controleerObjecttotalen(rapport)
        foto = [b for b in rapport["bronbestanden"]["bestanden"] if b["bestand"].endswith("SY003_onleesbaar.jpg")]
        assert foto and foto[0]["status"] == "mislukt" and foto[0]["reden"], foto
        assert f"De run is gestopt door taak `{CONTROLETAAK}`" in markdown
        niet_uitgevoerd = {t["taak"] for t in rapport["pipeline"]["taken"] if t["status"] == "upstream_failed"}
        assert "Load_Upsert" in niet_uitgevoerd and "Registreer_Run" in niet_uitgevoerd

    # ----------------------------------------------------------
    # h. Onleesbare foto weggehaald: herstel
    # ----------------------------------------------------------
    def test_09_herstel_na_mislukte_controle(self, mongo_client):
        """Na het weghalen van de foto slaagt de volgende run en is de openstaande entry opgeruimd."""
        verwijderSy003()
        TOESTAND["duur"]["h"], _ = draaiDag("Extract_Transform_Load_Incremental")
        run = controleerRun(mongo_client)
        assert run["tellingen"]["afbeeldingen"]["totaal"] == 0
        assert mongo_client[DB_FILES]["Filenames"].count_documents(
            {"filename": {"$regex": "SY003_onleesbaar\\.jpg$"}}) == 0
        assert mongo_client[DB_FILES]["Filenames"].count_documents({"processed": False}) == 0
        assert telTabellen() == TOESTAND["aantallen"]
        for tabel in SLEUTEL_TABELLEN:
            assert sleutels(tabel) == TOESTAND["sleutels"][tabel], f"{tabel}: sleutels niet gelijk aan stap a"
        controleerBruikleen()
        assert controleerElasticsearchGelijkAanTabellen() == TOESTAND["es"]
        assert afgeleideVelden() == TOESTAND["afgeleid"]
        print(f"\n  Looptijden: { {k: round(v, 1) for k, v in TOESTAND['duur'].items()} }")

    # ----------------------------------------------------------
    # h2. Onleesbare Access-database: waarschuwing, de run gaat door (issue 54)
    # ----------------------------------------------------------
    def test_09b_onleesbare_database_is_waarschuwing(self, mongo_client):
        """Een kapotte kopie van een Access-database stopt de run niet: Controleer_Databases meldt een waarschuwing.

        importMDB.sh slaat de database over (mdb-tables kan hem niet lezen); de controle telt hem als
        onleesbaar, onder de drempel (standaard max(2, 5%)). De run slaagt, het rapport noemt de
        database als mislukt met de reden, en PostgreSQL blijft gelijk aan stap a. De database blijft
        staan voor de volledige cyclus van stap i (de fixture ruimt SY003 na de test op).
        """
        os.makedirs(os.path.dirname(KAPOTTE_DATABASE), exist_ok=True)
        with open(KAPOTTE_DATABASE, "wb") as f:
            f.write(b"Dit is geen Access-database, maar een kapotte kopie.\n" * 200)
        TOESTAND["duur"]["h2"], uitvoer = draaiDag("Extract_Transform_Load_Incremental")
        assert re.search(rf"Marking task as SUCCESS\. dag_id=\S+, task_id={re.escape(DATABASETAAK)},", uitvoer)
        run = controleerRun(mongo_client)
        assert run["tellingen"]["delta"]["totaal"]["nieuw"] == 1
        extractie = run["tellingen"]["extractie"]
        assert extractie["databases"] == 1 and extractie["onleesbaar"] == 1 and extractie["boven_drempel"] is False
        assert extractie["onleesbare_databases"][0]["bestand"] == PAD_SY003_IN_CONTAINER + "C Database/kapot.mdb"
        waarschuwingen = [m for m in run["meldingen"] if m["soort"] == "database_onleesbaar"]
        assert len(waarschuwingen) == 1 and waarschuwingen[0]["niveau"] == "waarschuwing"
        assert waarschuwingen[0]["taak"] == DATABASETAAK and waarschuwingen[0]["stap"] == "extractie"

        rapport, markdown = controleerRapport(run, uitkomst="geslaagd met waarschuwingen")
        bestand = [b for b in rapport["bronbestanden"]["bestanden"] if b["bestand"].endswith("kapot.mdb")]
        assert bestand and bestand[0]["status"] == "mislukt" and "onleesbaar" in bestand[0]["reden"], bestand
        assert rapport["kwaliteitsmeldingen"]["databases"]["onleesbaar"] == 1
        assert "kapot.mdb" in markdown and "| extractie | Extract_Group.Controleer_Databases | database_onleesbaar |" in markdown

        # Niets geladen uit de kapotte database
        assert telTabellen() == TOESTAND["aantallen"]
        for tabel in SLEUTEL_TABELLEN:
            assert sleutels(tabel) == TOESTAND["sleutels"][tabel], f"{tabel}: sleutels gewijzigd"
        controleerBruikleen()

    # ----------------------------------------------------------
    # i. Opnieuw de volledige cyclus (issue 71)
    # ----------------------------------------------------------
    def test_10_volledige_cyclus_bewaart_gebruikersdata(self, mongo_client):
        """De volledige cyclus leegt de gebruikerstabellen niet en houdt de sleutels stabiel (issue 71).

        Vooraf komen er een conserveringsproject met een koppeling naar het artefact van de bruikleen
        en een extra ABR-materiaal voor dat artefact bij, zodat alle gebruikerstabellen rijen hebben.
        De bruikleen van het SY003-artefact staat sinds stap f losgekoppeld met een markering.
        """
        b = TOESTAND["bruikleen"]
        conservering_pk = pgWaarde(
            f'INSERT INTO "Def_Conserveringsproject" (korte_omschrijving, begindatum, "uitvoerderID") '
            f'VALUES (\'{TESTCONSERVERING}\', DATE \'2026-10-20\', {b["partij_pk"]}) RETURNING primary_key')
        pgRijen(f'INSERT INTO "Def_artefact_conservering" (conservering_id, artefact_id) '
                f'VALUES ({conservering_pk}, {b["artefact_pk"]})')
        abr_pk = pgWaarde('SELECT MIN(primary_key) FROM "Def_ABR"')
        TOESTAND["abr_koppeling"] = pgWaarde(
            f'INSERT INTO "Def_artefact_abr" (abr_materiaal_id, artefact_id) VALUES ({abr_pk}, {b["artefact_pk"]}) '
            f'RETURNING id')
        voor = gebruikersTabellen()
        for tabel in GEBRUIKERS_TABELLEN:
            assert voor[tabel], f"{tabel} heeft geen rijen: de test dekt die tabel niet"
        print(f"\n  Gebruikerstabellen vóór de volledige cyclus: { {t: len(r) for t, r in voor.items()} }")

        TOESTAND["duur"]["i"], uitvoer = draaiDag("Extract_Transform_Load_Full_Cycle")
        assert "Sleutels niet stabiel" not in uitvoer, "loadAll meldt hernummerde sleutels na een volledige cyclus"

        # Issue 54/62: de kapotte database van stap h2 is in de volledige cyclus een waarschuwing; de run
        # slaagt. Het rapport telt geen nieuwe of verwijderde rijen (stabiele sleutels, dezelfde data).
        run = laatsteRun(mongo_client, "volledig")
        assert run["run_id"] != TOESTAND["volledig"]["run_id"] and run["status"] == "afgerond", run.get("melding")
        eerder = {m["soort"] for m in TOESTAND["volledig"]["meldingen"] if m["niveau"] == "waarschuwing"}
        assert {m["soort"] for m in run["meldingen"] if m["niveau"] == "waarschuwing"} == eerder | {"database_onleesbaar"}, \
            run["meldingen"]
        assert not [m for m in run["meldingen"] if m["niveau"] == "fout"], run["meldingen"]
        assert mongo_client[DB_STAGING]["Verwerkingsruns"].count_documents({"_id": TOESTAND["volledig"]["run_id"]}) == 1, \
            "Het run-document van de eerste volledige cyclus is verdwenen"
        rapport, _ = controleerRapport(run, uitkomst="geslaagd met waarschuwingen")
        assert rapport["objecttotalen"]["totaal"]["aangemaakt"] == 0, rapport["objecttotalen"]["totaal"]
        assert rapport["objecttotalen"]["totaal"]["verwijderd"] == 0, rapport["objecttotalen"]["totaal"]

        # Gebruikerstabellen ongewijzigd, ook de markering van de losgekoppelde SY003-bruikleen
        assert gebruikersTabellen() == voor
        controleerBruikleen()
        artefact, _, key, _ = bruikleenSY003()
        assert artefact == "NULL" and key == TOESTAND["bruikleen_sy003"]["artefact_key"]

        # Sleutels, aantallen, Elasticsearch en afgeleide velden gelijk aan stap a
        assert telTabellen() == TOESTAND["aantallen"]
        for tabel in SLEUTEL_TABELLEN:
            assert sleutels(tabel) == TOESTAND["sleutels"][tabel], f"{tabel}: sleutels of primary_keys gewijzigd"
        assert controleerElasticsearchGelijkAanTabellen() == TOESTAND["es"]
        assert afgeleideVelden() == TOESTAND["afgeleid"]

        # Issue 81: elke rij van elke tabel heeft dezelfde primary_key als na de eerste volledige cyclus,
        # ook artefacten zonder subnr, het artefact met twee bronrijen, monsters, plaatsingen en standplaatsen
        vergelijkRijIdentiteiten(TOESTAND["identiteiten"])

        # Alle FK's geldig (ook die van de gebruikerstabellen) en de sequences kloppen
        ongeldig = pgRijen("SELECT conrelid::regclass::text, conname FROM pg_constraint "
                           "WHERE contype = 'f' AND NOT convalidated")
        assert ongeldig == [], f"FK-constraints die NOT VALID zijn: {ongeldig}"
        controleerSequences(LOAD_TABELLEN + ["Def_Bruikleen", "Def_Partij", "Def_Conserveringsproject"])
        controleerObjecttotalen(rapport)
        print(f"  Looptijden: { {k: round(v, 1) for k, v in TOESTAND['duur'].items()} }")
