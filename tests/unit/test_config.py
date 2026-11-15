"""
Unit tests voor shared/config.py en de sjablonen config/*.env.example (issue 87).

- Standaardwaarden voor AIRFLOW_TEMPDIR, AIRFLOW_LOGDIR en AIRFLOW_WASSTRAAT_CONFIG,
  gelijk aan de image, de compose-bestanden en importMDB.sh;
- de POSTGRES_-variabelen per variabele: één ontbrekende variabele geeft een
  foutmelding, maar slaat de overige instellingen niet meer over;
- MAIL_USE_TLS als ja/nee-instelling (tekst naar bool, standaard True);
- de drempels voor afbeeldingen in shared/config.py, net als de andere drempels;
- de sjablonen: geen variabelen die niemand leest, geldige regels, de juiste naam
  van de basis-URL van Airflow en dezelfde collectienaam voor de rapporten als de code;
- de versie in de ontwikkelomgeving en de map rapporten in alle compose-bestanden.

Net als test_config_cache.py laden deze tests de echte config-module (niet de mock
uit conftest.py) met gezette omgevingsvariabelen.
"""
import glob
import importlib.util
import logging
import os
import re
import shutil
import subprocess

import pytest
import yaml

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
CONFIG_PAD = os.path.join(PROJECT_ROOT, 'shared', 'config.py')
IMPORT_SCRIPT = os.path.join(PROJECT_ROOT, 'airflow_app', 'scripts', 'importMDB.sh')

BASIS_OMGEVING = {"POSTGRES_DB": "test", "POSTGRES_USER": "test", "POSTGRES_PASSWORD": "test"}
# Variabelen die de tests zelf zetten of weglaten; de omgeving van de testrunner telt niet mee
BETROKKEN = ["POSTGRES_DB", "POSTGRES_USER", "POSTGRES_PASSWORD", "AIRFLOW_TEMPDIR", "AIRFLOW_LOGDIR",
             "AIRFLOW_WASSTRAAT_CONFIG", "MAIL_USE_TLS", "MONGO_SERVER", "ES_HOST", "COLL_STAGING_RAPPORTEN",
             "AIRFLOW_MAX_MISLUKTE_AFBEELDINGEN", "AIRFLOW_MAX_MISLUKTE_AFBEELDINGEN_PCT"]

# Variabelen uit de sjablonen die niet shared/config.py maar een ander onderdeel leest,
# met het bestand dat ze leest
ELDERS_GELEZEN = {
    "SECURITY__ADMIN_USERNAME": "scripts/airflow/init.sh",
    "SECURITY__ADMIN_FIRSTNAME": "scripts/airflow/init.sh",
    "SECURITY__ADMIN_LASTNAME": "scripts/airflow/init.sh",
    "SECURITY__ADMIN_EMAIL": "scripts/airflow/init.sh",
    "SECURITY__ADMIN_PASSWORD": "scripts/airflow/init.sh",
    "FLASK_ADMIN_PASSWORD": "app/app/beheerder.py",
}
# Verwijderd in issue 87: door niemand gelezen
VERWIJDERD = ["AIRFLOW__WEBSERVER_BASE_URL", "AIRFLOW_INPUTDIR", "AIRFLOW_VAR_TEMPDIR",
              "_AIRFLOW_WWW_USER_USERNAME", "_AIRFLOW_WWW_USER_PASSWORD", "MONGO_MINPOOLSIZE",
              "COLL_STAGING_NIEUW", "COLL_ANALYSE_FOTO", "COLL_ANALYSE_ARTEFACT", "COLL_ANALYSE_PROJECT",
              "COLL_ANALYSE_VONDST", "COLL_ANALYSE_SPOOR", "COLL_ANALYSE_VLAK", "COLL_ANALYSE_PUT",
              "COLL_ANALYSE_STANDPLAATS", "COLL_ANALYSE_STELLING", "COLL_ANALYSE_PLAATSING",
              "COLL_ANALYSE_VINDPLAATS"]


def laadEchteConfig(monkeypatch, omgeving=None, zonder=()):
    """Laad shared/config.py als losse module met de opgegeven omgevingsvariabelen.

    Args:
        monkeypatch: pytest-fixture om omgevingsvariabelen tijdelijk te zetten.
        omgeving: dict met omgevingsvariabelen bovenop BASIS_OMGEVING.
        zonder: namen van variabelen die moeten ontbreken.

    Returns:
        De geladen config-module.
    """
    for naam in BETROKKEN:
        monkeypatch.delenv(naam, raising=False)
    for naam, waarde in {**BASIS_OMGEVING, **(omgeving or {})}.items():
        monkeypatch.setenv(naam, waarde)
    for naam in zonder:
        monkeypatch.delenv(naam, raising=False)
    spec = importlib.util.spec_from_file_location("wasstraat_config_onder_test", CONFIG_PAD)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def leesBestand(pad):
    with open(os.path.join(PROJECT_ROOT, pad), encoding="utf-8") as f:
        return f.read()


def leesSjabloon(naam):
    """Lees config/<naam>.env.example als lijst van (variabele, waarde); faalt op ongeldige regels."""
    regels = []
    for regel in leesBestand(f"config/{naam}.env.example").splitlines():
        if not regel.strip() or regel.lstrip().startswith("#"):
            continue
        match = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)=(.*)$", regel)
        assert match, f"config/{naam}.env.example: geen geldige regel NAAM=waarde: {regel!r}"
        regels.append((match.group(1), match.group(2)))
    return regels


def doorConfigGelezen():
    """Namen van de omgevingsvariabelen die shared/config.py leest."""
    return set(re.findall(r'(?:os\.getenv|os\.environ\.get|_lees\w+)\(\s*"([A-Z][A-Z0-9_]*)"',
                          leesBestand("shared/config.py")))


@pytest.mark.unit
class TestStandaardwaardenPaden:
    """AIRFLOW_TEMPDIR, AIRFLOW_LOGDIR en AIRFLOW_WASSTRAAT_CONFIG hebben een standaardwaarde."""

    VERWACHT = {
        "AIRFLOW_TEMPDIR": "/opt/airflow/tmp",
        "AIRFLOW_LOGDIR": "/opt/airflow/logs",
        "AIRFLOW_WASSTRAAT_CONFIG": "/opt/airflow/config/Wasstraat_Config_HarmonizeV3.xlsx",
    }

    def test_standaardwaarden_zonder_omgeving(self, monkeypatch):
        config = laadEchteConfig(monkeypatch)
        for naam, waarde in self.VERWACHT.items():
            assert getattr(config, naam) == waarde, naam

    def test_lege_waarde_geeft_standaard(self, monkeypatch):
        config = laadEchteConfig(monkeypatch, {"AIRFLOW_TEMPDIR": ""})
        assert config.AIRFLOW_TEMPDIR == "/opt/airflow/tmp"

    def test_omgeving_gaat_voor(self, monkeypatch):
        config = laadEchteConfig(monkeypatch, {"AIRFLOW_TEMPDIR": "/tmp/x", "AIRFLOW_LOGDIR": "/tmp/y",
                                               "AIRFLOW_WASSTRAAT_CONFIG": "/tmp/z.xlsx"})
        assert (config.AIRFLOW_TEMPDIR, config.AIRFLOW_LOGDIR, config.AIRFLOW_WASSTRAAT_CONFIG) == \
            ("/tmp/x", "/tmp/y", "/tmp/z.xlsx")

    def test_gelijk_aan_sjabloon_en_testomgevingen(self):
        sjabloon = dict(leesSjabloon("airflow"))
        for pad in ("docker-compose.test.yml", "docker-compose.delft-test.yml"):
            omgeving = yaml.safe_load(leesBestand(pad))["services"]["airflow-test"]["environment"]
            for naam, waarde in self.VERWACHT.items():
                assert omgeving[naam] == waarde, (pad, naam)
        for naam, waarde in self.VERWACHT.items():
            assert sjabloon[naam] == waarde, naam

    def test_importMDB_gebruikt_dezelfde_standaardwaarden(self):
        script = leesBestand("airflow_app/scripts/importMDB.sh")
        for naam in ("AIRFLOW_TEMPDIR", "AIRFLOW_LOGDIR"):
            match = re.search(rf"\$\{{{naam}:-([^}}]+)\}}", script)
            assert match and match.group(1) == self.VERWACHT[naam], naam

    def test_image_maakt_de_werkmap_aan(self):
        dockerfile = leesBestand("services/airflow/Dockerfile")
        assert "FROM apache/airflow:" in dockerfile  # AIRFLOW_HOME en werkmap /opt/airflow
        assert re.search(r"^RUN mkdir -p tmp$", dockerfile, re.M)


@pytest.mark.unit
class TestPostgresPerVariabele:
    """Een ontbrekende POSTGRES_-variabele slaat de overige instellingen niet meer over."""

    OVERIG = {"MONGO_SERVER": "mongo", "ES_HOST": "http://es:9200", "AIRFLOW_TEMPDIR": "/tmp/werk"}

    @pytest.mark.parametrize("ontbrekend", ["POSTGRES_DB", "POSTGRES_USER", "POSTGRES_PASSWORD"])
    def test_een_ontbrekende_variabele(self, monkeypatch, caplog, ontbrekend):
        with caplog.at_level(logging.ERROR):
            config = laadEchteConfig(monkeypatch, self.OVERIG, zonder=[ontbrekend])
        assert getattr(config, ontbrekend) is None
        assert config.MONGO_SERVER == "mongo"
        assert config.MONGO_URI.endswith("@mongo/?authSource=admin")
        assert config.ES_HOST == "http://es:9200"
        assert config.AIRFLOW_TEMPDIR == "/tmp/werk"
        assert config.COLL_STAGING_RAPPORTEN == "Staging_Rapporten"
        assert config.AIRFLOW_INPUT_RAPPORTEN == "/input/rapporten"
        meldingen = [r.getMessage() for r in caplog.records if r.levelno == logging.ERROR]
        assert len(meldingen) == 1 and ontbrekend in meldingen[0], meldingen

    def test_alles_aanwezig_geen_foutmelding(self, monkeypatch, caplog):
        with caplog.at_level(logging.ERROR):
            config = laadEchteConfig(monkeypatch, self.OVERIG)
        assert config.POSTGRES_DB == "test"
        assert not [r for r in caplog.records if r.levelno >= logging.ERROR]

    def test_geen_hulpvariabelen_als_flask_instelling(self, monkeypatch):
        """Flask (app.config.from_object) neemt alle namen in hoofdletters over; alleen echte instellingen."""
        config = laadEchteConfig(monkeypatch)
        instellingen = {naam for naam in dir(config) if naam.isupper()}
        assert not instellingen & {"WAAR", "ONWAAR", "_WAAR", "_ONWAAR", "POSTGRES_ONTBREKEND"}
        for naam in VERWIJDERD:
            if naam != "COLL_STAGING_NIEUW":  # blijft voor de notebooks, met een standaardwaarde
                assert not hasattr(config, naam), naam


@pytest.mark.unit
class TestMailUseTls:

    @pytest.mark.parametrize("waarde, verwacht", [
        ("True", True), ("true", True), ("1", True), ("ja", True), ("yes", True), ("on", True),
        ("False", False), ("false", False), ("0", False), ("nee", False), ("no", False), ("off", False),
        ("'False'", False), (" FALSE ", False), ('"true"', True),
    ])
    def test_tekst_naar_bool(self, monkeypatch, waarde, verwacht):
        config = laadEchteConfig(monkeypatch, {"MAIL_USE_TLS": waarde})
        assert config.MAIL_USE_TLS is verwacht

    @pytest.mark.parametrize("waarde", [None, ""])
    def test_standaard_true(self, monkeypatch, waarde):
        omgeving = {} if waarde is None else {"MAIL_USE_TLS": waarde}
        config = laadEchteConfig(monkeypatch, omgeving)
        assert config.MAIL_USE_TLS is True

    def test_ongeldige_waarde_geeft_standaard_met_waarschuwing(self, monkeypatch, caplog):
        with caplog.at_level(logging.WARNING):
            config = laadEchteConfig(monkeypatch, {"MAIL_USE_TLS": "misschien"})
        assert config.MAIL_USE_TLS is True
        assert "Ongeldige waarde 'misschien' voor MAIL_USE_TLS" in caplog.text

    def test_sjabloon_geeft_een_geldige_waarde(self, monkeypatch):
        waarde = dict(leesSjabloon("flask"))["MAIL_USE_TLS"]
        config = laadEchteConfig(monkeypatch, {"MAIL_USE_TLS": waarde})
        assert config.MAIL_USE_TLS is True


@pytest.mark.unit
class TestDrempels:
    """Alle drempels, ook die voor de afbeeldingen, staan in shared/config.py."""

    def test_standaard_drempel_afbeeldingen(self, monkeypatch):
        config = laadEchteConfig(monkeypatch)
        assert config.AIRFLOW_MAX_MISLUKTE_AFBEELDINGEN == 10
        assert config.AIRFLOW_MAX_MISLUKTE_AFBEELDINGEN_PCT == 1.0

    def test_drempel_afbeeldingen_uit_omgeving_is_getal(self, monkeypatch):
        config = laadEchteConfig(monkeypatch, {"AIRFLOW_MAX_MISLUKTE_AFBEELDINGEN": "0",
                                               "AIRFLOW_MAX_MISLUKTE_AFBEELDINGEN_PCT": "0,5"})
        assert config.AIRFLOW_MAX_MISLUKTE_AFBEELDINGEN == 0
        assert isinstance(config.AIRFLOW_MAX_MISLUKTE_AFBEELDINGEN, int)
        assert config.AIRFLOW_MAX_MISLUKTE_AFBEELDINGEN_PCT == 0.5

    @pytest.mark.parametrize("waarde, soort, verwacht", [
        (None, int, 10), ('', int, 10), ('25', int, 25), (' 3 ', int, 3), ('0', int, 0),
        ('abc', int, 10), ('-1', int, 10), ('0,5', float, 0.5), ('2.5', float, 2.5),
    ])
    def test_getal_uit_omgeving(self, monkeypatch, waarde, soort, verwacht):
        config = laadEchteConfig(monkeypatch)
        if waarde is None:
            monkeypatch.delenv('WASSTRAAT_TEST_GETAL', raising=False)
        else:
            monkeypatch.setenv('WASSTRAAT_TEST_GETAL', waarde)
        assert config._leesGetal('WASSTRAAT_TEST_GETAL', 10, soort) == verwacht

    def test_image_import_leest_niet_zelf_de_omgeving(self):
        code = leesBestand("airflow_app/dags/wasstraat/image_import.py")
        assert "os.getenv" not in code and "os.environ" not in code


@pytest.mark.unit
class TestSjablonen:
    """De sjablonen bevatten alleen variabelen die gelezen worden, met geldige regels."""

    @pytest.mark.parametrize("naam", ["airflow", "mongo", "flask"])
    def test_elke_variabele_wordt_gelezen(self, naam):
        gelezen = doorConfigGelezen()
        for variabele, _ in leesSjabloon(naam):
            if variabele.startswith("AIRFLOW__"):
                continue  # Airflow zelf, zie test_airflow_variabelen_hebben_sectie_en_sleutel
            if variabele in ELDERS_GELEZEN:
                assert variabele in leesBestand(ELDERS_GELEZEN[variabele]), variabele
                continue
            assert variabele in gelezen, f"{variabele} uit config/{naam}.env.example wordt niet gelezen"

    def test_verwijderde_variabelen_staan_in_geen_sjabloon(self):
        paden = glob.glob(os.path.join(PROJECT_ROOT, "config", "*.env.example")) + \
            glob.glob(os.path.join(PROJECT_ROOT, "deploy", "config", "*.env.example"))
        assert paden
        for pad in paden:
            with open(pad, encoding="utf-8") as f:
                tekst = f.read()
            for naam in VERWIJDERD:
                assert not re.search(rf"^\s*{naam}\s*=", tekst, re.M), f"{naam} in {pad}"

    @pytest.mark.parametrize("pad", ["docker-compose.test.yml", "docker-compose.delft-test.yml"])
    def test_verwijderde_variabelen_niet_in_testomgevingen(self, pad):
        for dienst in ("airflow-test", "flask-test"):
            omgeving = yaml.safe_load(leesBestand(pad))["services"][dienst]["environment"]
            assert not set(omgeving) & set(VERWIJDERD), (pad, dienst, set(omgeving) & set(VERWIJDERD))

    def test_alle_regels_geldig(self):
        for pad in glob.glob(os.path.join(PROJECT_ROOT, "config", "*.env.example")):
            leesSjabloon(os.path.basename(pad)[:-len(".env.example")])

    def test_geen_sjabloon_voor_elasticsearch(self):
        """ES_HOST heeft een standaardwaarde; geen service las elasticsearch.env."""
        assert not os.path.exists(os.path.join(PROJECT_ROOT, "config", "elasticsearch.env.example"))
        for pad in ["docker-compose.yml", "docker-compose.delft.yml", "deploy/docker-compose.yml"]:
            assert "elasticsearch.env" not in leesBestand(pad), pad

    def test_airflow_variabelen_hebben_sectie_en_sleutel(self):
        """Airflow leest alleen AIRFLOW__<SECTIE>__<SLEUTEL> (twee keer een dubbele underscore)."""
        for variabele, _ in leesSjabloon("airflow"):
            if variabele.startswith("AIRFLOW__"):
                assert re.match(r"^AIRFLOW__[A-Z0-9]+(?:_[A-Z0-9]+)*__[A-Z0-9_]+$", variabele), variabele

    def test_basis_url_wijst_naar_de_poort_van_airflow(self):
        """Airflow staat niet achter Apache: de basis-URL is de hostpoort van Airflow."""
        url = dict(leesSjabloon("airflow"))["AIRFLOW__WEBSERVER__BASE_URL"]
        poort = int(re.match(r"^http://localhost:(\d+)$", url).group(1))
        airflow = yaml.safe_load(leesBestand("docker-compose.yml"))["services"]["airflow"]
        assert f"{poort}:8080" in airflow["ports"]
        assert re.search(rf"^WASSTRAAT_PORT_AIRFLOW={poort}$", leesBestand("deploy/.env.example"), re.M)

    def test_collectie_rapporten_gelijk_aan_code(self, monkeypatch):
        """Het sjabloon en de standaard in shared/config.py noemen dezelfde collectie (zoals in productie)."""
        config = laadEchteConfig(monkeypatch)
        assert dict(leesSjabloon("mongo"))["COLL_STAGING_RAPPORTEN"] == config.COLL_STAGING_RAPPORTEN \
            == "Staging_Rapporten"


@pytest.mark.unit
class TestOntwikkelomgeving:
    """Versie in het verwerkingsrapport en de map rapporten in de compose-bestanden."""

    def versie(self):
        for naam in ("config/version.env", "config/version.env.example"):
            pad = os.path.join(PROJECT_ROOT, naam)
            if os.path.isfile(pad):
                match = re.search(r"^VERSION=(.+)$", leesBestand(naam), re.M)
                if match:
                    return match.group(1).strip()
        return None

    @pytest.mark.parametrize("pad", ["docker-compose.yml", "docker-compose.delft.yml"])
    def test_compose_geeft_versie_aan_airflow(self, pad):
        omgeving = yaml.safe_load(leesBestand(pad))["services"]["airflow"]["environment"]
        assert omgeving["WASSTRAAT_VERSION"] == "${WASSTRAAT_VERSION:-}"

    @pytest.mark.parametrize("doel", ["app", "delft", "dev"])
    def test_make_geeft_versie_mee(self, doel):
        if not shutil.which("make"):
            pytest.skip("make niet geïnstalleerd")
        resultaat = subprocess.run(["make", "-n", "-C", PROJECT_ROOT, doel],
                                   capture_output=True, text=True, timeout=60)
        assert resultaat.returncode == 0, resultaat.stderr
        regels = [r for r in resultaat.stdout.splitlines() if "up -d" in r]
        assert regels and all(r.startswith(f"WASSTRAAT_VERSION={self.versie()} ") for r in regels), regels

    @pytest.mark.parametrize("pad, dienst", [
        ("docker-compose.yml", "airflow"), ("docker-compose.delft.yml", "airflow"),
        ("docker-compose.test.yml", "airflow-test"), ("docker-compose.delft-test.yml", "airflow-test"),
        ("deploy/docker-compose.yml", "airflow"),
    ])
    def test_rapporten_gekoppeld(self, pad, dienst):
        volumes = yaml.safe_load(leesBestand(pad))["services"][dienst]["volumes"]
        assert any(re.search(r"/rapporten:/input/rapporten(:ro)?$", v) for v in volumes), (pad, volumes)

    def test_synthetische_rapportenmap_bestaat(self):
        """De map staat in de repository (.gitkeep), zodat Docker hem niet als root aanmaakt."""
        assert os.path.isfile(os.path.join(PROJECT_ROOT, "data", "synthetic", "data", "rapporten", ".gitkeep"))
