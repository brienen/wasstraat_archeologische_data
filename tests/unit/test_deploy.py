"""
Unit tests voor de live installatie uit gepubliceerde images (deploy/) en 'make publish'.

De map deploy/ moet zelfstandig bruikbaar zijn zonder de rest van de repository.
Daarom bevat die kopieën van init-config.sh, config/*.env.example en de
harmonisatie-Excel; deze tests bewaken dat die kopieën gelijk blijven aan het
origineel en dat het compose-bestand alleen gepubliceerde images gebruikt.
"""
import filecmp
import glob
import os
import re
import shutil
import subprocess

import pytest
import yaml


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DEPLOY = os.path.join(PROJECT_ROOT, "deploy")
# Jupyter is een ontwikkelvoorziening en wordt niet gepubliceerd
EIGEN_IMAGES = {"airflow", "flask", "postgres", "apache"}
# De env-bestanden die deploy/docker-compose.yml gebruikt (geen jupyter, elasticsearch of version)
DEPLOY_ENV_EXAMPLES = {"airflow", "airflow_db", "flask", "mongo", "postgres", "redis"}
BRONCODE_MAPPEN = ("airflow_app", "shared", "app", ".vscode", "scripts")


def leesCompose():
    """Lees deploy/docker-compose.yml als dict (zonder variabelen te vervangen)."""
    with open(os.path.join(DEPLOY, "docker-compose.yml"), encoding="utf-8") as f:
        return yaml.safe_load(f)


def leesVariabele(pad, naam):
    """Lees de waarde van NAAM=waarde uit een .env-achtig bestand."""
    with open(pad, encoding="utf-8") as f:
        for regel in f:
            match = re.match(rf"^{naam}=(.*)$", regel.strip())
            if match:
                return match.group(1)
    return None


@pytest.mark.unit
class TestDeployKopieen:
    """De kopieën in deploy/ zijn gelijk aan het origineel."""

    def test_init_config_identiek(self):
        assert filecmp.cmp(
            os.path.join(PROJECT_ROOT, "init-config.sh"),
            os.path.join(DEPLOY, "init-config.sh"),
            shallow=False,
        ), "deploy/init-config.sh wijkt af van init-config.sh; kopieer het bestand opnieuw"

    def test_init_config_uitvoerbaar(self):
        assert os.access(os.path.join(DEPLOY, "init-config.sh"), os.X_OK)

    def test_env_examples_identiek(self):
        kopie = sorted(os.path.basename(p) for p in glob.glob(os.path.join(DEPLOY, "config", "*.env.example")))
        assert kopie == sorted(f"{naam}.env.example" for naam in DEPLOY_ENV_EXAMPLES), kopie
        for naam in kopie:
            assert filecmp.cmp(
                os.path.join(PROJECT_ROOT, "config", naam),
                os.path.join(DEPLOY, "config", naam),
                shallow=False,
            ), f"deploy/config/{naam} wijkt af van config/{naam}; kopieer het bestand opnieuw"

    def test_harmonisatie_excel_identiek(self):
        assert filecmp.cmp(
            os.path.join(PROJECT_ROOT, "data", "synthetic", "wasstraat_config", "Wasstraat_Config_HarmonizeV3.xlsx"),
            os.path.join(DEPLOY, "wasstraat_config", "Wasstraat_Config_HarmonizeV3.xlsx"),
            shallow=False,
        ), "deploy/wasstraat_config/Wasstraat_Config_HarmonizeV3.xlsx wijkt af van de synthetische configuratie"

    def test_correcties_sjabloon_is_geldige_dictionary(self):
        with open(os.path.join(DEPLOY, "wasstraat_config", "correcties.yml"), encoding="utf-8") as f:
            correcties = yaml.safe_load(f)
        assert isinstance(correcties, dict), "laadCorrecties() verwacht een YAML-dictionary"
        assert correcties.get("projectcode_correcties") == []
        assert correcties.get("brondata_correcties") == []

    def test_versie_gelijk_aan_version_env_example(self):
        versie = leesVariabele(os.path.join(PROJECT_ROOT, "config", "version.env.example"), "VERSION")
        deploy_versie = leesVariabele(os.path.join(DEPLOY, ".env.example"), "WASSTRAAT_VERSION")
        assert versie and deploy_versie == versie, (
            f"deploy/.env.example heeft WASSTRAAT_VERSION={deploy_versie}, config/version.env.example VERSION={versie}"
        )

    def test_datamappen_aanwezig(self):
        for map_ in ("projecten", "projectenlijst", "magazijnlijst", "fotolijst",
                     "monsterdatabase", "rapporten", "referentietabellen"):
            assert os.path.isfile(os.path.join(DEPLOY, "data", "input", map_, ".gitkeep")), map_
        for map_ in ("backup/postgres", "backup/mongo", "output"):
            assert os.path.isfile(os.path.join(DEPLOY, "data", map_, ".gitkeep")), map_
        assert not os.path.exists(os.path.join(DEPLOY, "notebooks")), "Jupyter hoort niet in de live installatie"


@pytest.mark.unit
class TestDeployCompose:
    """deploy/docker-compose.yml gebruikt alleen gepubliceerde images en geen broncode."""

    def test_alle_services_hebben_image_en_geen_build(self):
        services = leesCompose()["services"]
        assert set(services) == {"postgres", "airflow", "redis", "flask", "mongo", "apache", "elasticsearch"}
        for naam, service in services.items():
            assert "image" in service, f"service {naam} heeft geen image"
            assert "build" not in service, f"service {naam} bouwt zelf een image"

    def test_eigen_images_komen_van_registry_met_versievariabele(self):
        services = leesCompose()["services"]
        patroon = re.compile(
            r"^\$\{WASSTRAAT_REGISTRY:-ghcr\.io/brienen\}/wasstraat-(\w+):\$\{WASSTRAAT_VERSION:\?[^}]*\}$"
        )
        gevonden = set()
        for naam, service in services.items():
            match = patroon.match(service["image"])
            if naam in EIGEN_IMAGES:
                assert match, f"service {naam}: onverwachte image {service['image']}"
                assert match.group(1) == naam
                gevonden.add(naam)
            else:
                assert not match, f"service {naam} hoort een standaardimage te gebruiken"
        assert gevonden == EIGEN_IMAGES

    def test_env_files_hebben_een_sjabloon(self):
        """Elk env_file in de compose heeft een .env.example in deploy/config (init-config.sh maakt het aan)."""
        for naam, service in leesCompose()["services"].items():
            for env_file in service.get("env_file", []):
                sjabloon = os.path.join(DEPLOY, env_file + ".example")
                assert os.path.isfile(sjabloon), f"service {naam}: {env_file} heeft geen sjabloon"

    def test_geen_volumes_naar_broncode(self):
        for naam, service in leesCompose()["services"].items():
            for volume in service.get("volumes", []):
                bron = volume.split(":")[0]
                if bron.startswith(("./", "../", "/", "${")):
                    assert not any(f"/{m}" in bron or bron.startswith(f"./{m}") for m in BRONCODE_MAPPEN), (
                        f"service {naam} mount broncode: {volume}"
                    )

    def test_brondata_en_configuratie_alleen_lezen_in_airflow(self):
        airflow = leesCompose()["services"]["airflow"]
        for volume in airflow["volumes"]:
            if "/input/" in volume or "/opt/airflow/config" in volume:
                assert volume.endswith(":ro"), volume

    def test_postgres_pgdata_gelijk_aan_volume(self):
        postgres = leesCompose()["services"]["postgres"]
        pgdata = postgres["environment"]["PGDATA"]
        assert any(v == f"postgres:{pgdata}" for v in postgres["volumes"]), postgres["volumes"]

    def test_elasticsearch_zonder_hostpoort_en_zonder_beveiliging(self):
        es = leesCompose()["services"]["elasticsearch"]
        assert "ports" not in es
        assert "xpack.security.enabled=false" in es["environment"]

    def test_databasepoorten_standaard_alleen_lokaal(self):
        services = leesCompose()["services"]
        for naam in ("postgres", "mongo"):
            assert all(p.startswith("${WASSTRAAT_BIND_DB:-127.0.0.1}:") for p in services[naam]["ports"]), naam
        assert "ports" not in services["redis"]

    def test_compose_config_is_geldig(self, tmp_path):
        """docker compose valideert het bestand na init-config.sh, zoals bij een echte installatie.

        Overgeslagen zonder Docker. De env_file-bestanden moeten bestaan, dus eerst
        worden .env en config/*.env aangemaakt in een tijdelijke kopie van deploy/.
        """
        if not shutil.which("docker"):
            pytest.skip("docker niet geïnstalleerd")
        for naam in ("docker-compose.yml", "init-config.sh"):
            shutil.copy(os.path.join(DEPLOY, naam), tmp_path / naam)
        shutil.copy(os.path.join(DEPLOY, ".env.example"), tmp_path / ".env")
        shutil.copytree(os.path.join(DEPLOY, "config"), tmp_path / "config")
        init = subprocess.run(["bash", str(tmp_path / "init-config.sh")], capture_output=True, text=True, timeout=60)
        assert init.returncode == 0, init.stderr

        resultaat = subprocess.run(
            ["docker", "compose", "config", "--quiet"],
            cwd=tmp_path, capture_output=True, text=True, timeout=60,
        )
        if resultaat.returncode != 0 and "Cannot connect" in resultaat.stderr:
            pytest.skip("Docker daemon niet bereikbaar")
        assert resultaat.returncode == 0, resultaat.stderr


@pytest.mark.unit
class TestPublish:
    """'make publish' in de Makefile van de repository en de inhoud van de images."""

    @pytest.fixture(autouse=True)
    def vereistMake(self):
        if not shutil.which("make"):
            pytest.skip("make niet geïnstalleerd")

    def draaiMake(self, *args):
        return subprocess.run(
            ["make", "-n", "-C", PROJECT_ROOT, *args],
            capture_output=True, text=True, timeout=60,
        )

    def test_publish_pusht_multi_arch_naar_ghcr(self):
        resultaat = self.draaiMake("publish", "SERVICE=flask", "VERSION=9.9.9")
        assert resultaat.returncode == 0, resultaat.stderr
        assert "--platform linux/amd64,linux/arm64" in resultaat.stdout
        assert "--push" in resultaat.stdout
        # De servicenaam wordt pas in de shell-lus ingevuld ($s)
        assert "for s in flask;" in resultaat.stdout
        assert "-t ghcr.io/brienen/wasstraat-$s:9.9.9" in resultaat.stdout
        assert "-t ghcr.io/brienen/wasstraat-$s:latest" in resultaat.stdout
        assert "-f services/$s/Dockerfile" in resultaat.stdout

    def test_publish_zonder_push_bouwt_lokaal(self):
        resultaat = self.draaiMake("publish", "SERVICE=apache", "PUSH=0", "VERSION=9.9.9")
        assert resultaat.returncode == 0, resultaat.stderr
        assert "--load" in resultaat.stdout
        assert "--push" not in resultaat.stdout
        assert "--platform" not in resultaat.stdout

    def test_publish_leest_versie_uit_version_env(self):
        """Zonder VERSION= komt de versie uit config/version.env of version.env.example."""
        resultaat = self.draaiMake("publish", "SERVICE=apache", "PUSH=0")
        assert resultaat.returncode == 0, resultaat.stderr
        assert re.search(r"wasstraat-\$s:\d+\.\d+\.\d+", resultaat.stdout), resultaat.stdout

    def test_publish_weigert_onbekende_service(self):
        resultaat = subprocess.run(
            ["make", "-C", PROJECT_ROOT, "publish", "SERVICE=bestaatniet", "PUSH=0", "VERSION=9.9.9"],
            capture_output=True, text=True, timeout=60,
        )
        assert resultaat.returncode != 0
        assert "Onbekende service" in resultaat.stderr + resultaat.stdout

    def test_release_vereist_versie_op_commandoregel(self):
        resultaat = self.draaiMake("release", "MSG=test")
        assert resultaat.returncode != 0
        assert "Geef een versie op" in resultaat.stderr

    def test_release_publiceert_en_verwijst_niet_naar_docker_hub(self):
        with open(os.path.join(PROJECT_ROOT, "Makefile"), encoding="utf-8") as f:
            makefile = f.read()
        assert "brienen/wasstraat_flask" not in makefile
        resultaat = self.draaiMake("release", "VERSION=9.9.9", "MSG=test")
        assert resultaat.returncode == 0, resultaat.stderr
        assert "publish VERSION=9.9.9" in resultaat.stdout
        assert "WASSTRAAT_VERSION=9.9.9" in resultaat.stdout

    def test_airflow_image_bevat_code_en_scripts(self):
        with open(os.path.join(PROJECT_ROOT, "services", "airflow", "Dockerfile"), encoding="utf-8") as f:
            dockerfile = f.read()
        assert re.search(r"^COPY .*\./airflow_app/dags \./dags$", dockerfile, re.M)
        assert re.search(r"^COPY .*\./airflow_app/scripts \./scripts$", dockerfile, re.M)
        assert re.search(r"^COPY .*\./shared \./dags/shared$", dockerfile, re.M)

    def test_buildcontext_zonder_data_en_notebooks(self):
        with open(os.path.join(PROJECT_ROOT, ".dockerignore"), encoding="utf-8") as f:
            regels = {r.strip() for r in f if r.strip() and not r.startswith("#")}
        for map_ in ("data", "notebooks", "docs", "deploy"):
            assert map_ in regels, f"{map_} hoort in .dockerignore"
