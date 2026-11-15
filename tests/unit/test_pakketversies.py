"""
Unit tests voor vastgelegde pakketversies en robuuste builds (issue 80).

De Flask-, Jupyter- en Airflow-image installeren hun Python-pakketten met vaste versies
uit services/*/constraints.txt; 'make constraints' (scripts/leg_pakketversies_vast.sh)
legt ze opnieuw vast. De Airflow-build houdt alle pakketten van de basisimage op hun
versie (de constraints van Airflow zelf); in constraints.txt staat alleen wat
requirements.txt daaraan toevoegt. De apt-get-opdrachten in de Dockerfiles proberen een
mislukte download opnieuw. Zie docs/testen.md, sectie 'Pakketversies bijwerken'.
"""
import os
import re
import shutil
import subprocess

import pytest


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
IMAGES_MET_CONSTRAINTS = ["airflow", "flask", "jupyter"]
SCRIPT = "scripts/leg_pakketversies_vast.sh"
PIN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*==[^=\s]+$")


def leesBestand(pad):
    with open(os.path.join(PROJECT_ROOT, pad), encoding="utf-8") as f:
        return f.read()


def leesPins(pad):
    """De niet-commentaarregels van een constraints-bestand."""
    return [r.strip() for r in leesBestand(pad).splitlines() if r.strip() and not r.startswith("#")]


def zonderVoortzetting(dockerfile):
    """Voeg regels met een backslash aan het eind samen tot één regel."""
    return dockerfile.replace("\\\n", " ")


def aptOpdrachten(dockerfile):
    """Alle apt-get-opdrachten (tot de volgende && of ;) uit een Dockerfile."""
    return [m.group(0) for m in re.finditer(r"apt-get[^&;\n]*", zonderVoortzetting(dockerfile))]


@pytest.mark.unit
class TestConstraintsBestanden:
    """Elke image met eigen pakketten heeft een geldig constraints-bestand."""

    @pytest.mark.parametrize("image", IMAGES_MET_CONSTRAINTS)
    def test_alleen_exacte_versies(self, image):
        pins = leesPins(f"services/{image}/constraints.txt")
        assert pins, f"services/{image}/constraints.txt is leeg"
        for pin in pins:
            assert PIN.match(pin), f"services/{image}/constraints.txt: geen exacte versie: {pin!r}"

    @pytest.mark.parametrize("image", IMAGES_MET_CONSTRAINTS)
    def test_geen_dubbele_pakketten(self, image):
        namen = [p.split("==")[0].lower().replace("_", "-") for p in leesPins(f"services/{image}/constraints.txt")]
        assert len(namen) == len(set(namen)), sorted(n for n in namen if namen.count(n) > 1)

    @pytest.mark.parametrize("image", IMAGES_MET_CONSTRAINTS)
    def test_kopregels_verwijzen_naar_make_constraints(self, image):
        assert "make constraints" in leesBestand(f"services/{image}/constraints.txt").splitlines()[1]


@pytest.mark.unit
class TestAirflowConstraints:
    """Airflow: alleen vastleggen wat requirements.txt bovenop de basisimage toevoegt."""

    def test_airflow_zelf_niet_vastgelegd(self):
        """Airflow en zijn providers legt de basisimage vast; een eigen pin zou daarmee botsen."""
        for pin in leesPins("services/airflow/constraints.txt"):
            assert not pin.lower().startswith("apache-airflow"), pin

    def test_dockerfile_installeert_met_constraints(self):
        dockerfile = zonderVoortzetting(leesBestand("services/airflow/Dockerfile"))
        assert re.search(r"^COPY \./services/airflow/requirements\.txt \./services/airflow/constraints\.txt /tmp/$",
                         dockerfile, re.M)
        assert "ARG VASTE_VERSIES=1" in dockerfile
        pip = [r for r in dockerfile.splitlines() if "pip install" in r]
        assert len(pip) == 1, pip
        assert "-c $VERSIES" in pip[0]
        assert "-r /tmp/requirements.txt" in pip[0]
        assert 'VERSIES=/tmp/constraints.txt' in pip[0]

    def test_dockerfile_houdt_basisimage_op_haar_versies(self):
        """De versies van de basisimage zijn constraints: pip voegt alleen pakketten toe."""
        pip = [r for r in zonderVoortzetting(leesBestand("services/airflow/Dockerfile")).splitlines() if "pip install" in r]
        assert "pip list --format=freeze > /tmp/basisimage.txt" in pip[0]
        assert "-c /tmp/basisimage.txt" in pip[0]
        assert pip[0].index("> /tmp/basisimage.txt") < pip[0].index("pip install")
        assert '"apache-airflow==${AIRFLOW_VERSION}"' in pip[0]

    def test_dockerfile_draait_pip_check(self):
        pip = [r for r in zonderVoortzetting(leesBestand("services/airflow/Dockerfile")).splitlines() if "pip install" in r]
        assert "pip check" in pip[0]

    def test_dockerfile_controleert_geinstalleerde_versies(self):
        dockerfile = leesBestand("services/airflow/Dockerfile")
        assert "pip list --format=freeze" in dockerfile
        assert "draai 'make constraints'" in dockerfile

    def test_basisimage_is_airflow_2_10_5(self):
        """De constraints horen bij deze basisimage; een nieuwe basisimage vraagt 'make constraints'."""
        assert re.search(r"^FROM apache/airflow:2\.10\.5-python3\.11$", leesBestand("services/airflow/Dockerfile"), re.M)

    def test_elasticsearch_client_hoofdversie_8(self):
        """De server is 8.17 (docker-compose.yml); een 9.x-client weigert die."""
        for pin in leesPins("services/airflow/constraints.txt"):
            naam, versie = pin.split("==")
            if naam.lower() in ("elasticsearch", "elastic-transport"):
                assert versie.startswith("8."), pin


@pytest.mark.unit
class TestAptRetries:
    """apt-get probeert een mislukte download opnieuw, zodat verse builds robuuster zijn."""

    @pytest.mark.parametrize("image", IMAGES_MET_CONSTRAINTS)
    def test_apt_get_update_en_install_met_retries(self, image):
        opdrachten = [o for o in aptOpdrachten(leesBestand(f"services/{image}/Dockerfile"))
                      if re.search(r"\b(update|install)\b", o)]
        assert opdrachten, f"geen apt-get update/install in services/{image}/Dockerfile"
        for opdracht in opdrachten:
            assert "-o Acquire::Retries=3" in opdracht, f"services/{image}/Dockerfile: {opdracht.strip()}"


@pytest.mark.unit
class TestMakeConstraints:
    """'make constraints' legt alle drie de images vast en laat draaiende containers ongemoeid."""

    def test_script_kent_airflow(self):
        script = leesBestand(SCRIPT)
        assert re.search(r"^\s+airflow\) legAirflowVast ;;$", script, re.M)
        assert re.search(r"^\s+set -- flask jupyter airflow$", script, re.M)

    def test_script_raakt_geen_draaiende_installatie(self):
        """Alleen eigen images en tijdelijke containers: geen compose, geen wasstraat_*-containers."""
        script = "\n".join(r for r in leesBestand(SCRIPT).splitlines() if not r.lstrip().startswith("#"))
        assert "docker compose" not in script and "docker-compose" not in script
        assert "wasstraat_" not in script
        for opdracht in re.findall(r"docker (\w+)", script):
            assert opdracht in ("build", "run", "image"), f"onverwachte docker-opdracht: docker {opdracht}"
        assert all("--rm" in r for r in script.splitlines() if "docker run" in r)

    def test_make_constraints_roept_script_aan(self):
        if not shutil.which("make"):
            pytest.skip("make niet geïnstalleerd")
        resultaat = subprocess.run(
            ["make", "-n", "-C", PROJECT_ROOT, "constraints"],
            capture_output=True, text=True, timeout=60,
        )
        assert resultaat.returncode == 0, resultaat.stderr
        assert f"bash {SCRIPT}" in resultaat.stdout

    def test_onbekende_image_geweigerd(self):
        resultaat = subprocess.run(
            ["bash", os.path.join(PROJECT_ROOT, SCRIPT), "bestaatniet"],
            capture_output=True, text=True, timeout=60,
        )
        assert resultaat.returncode != 0
        assert "kies flask, jupyter of airflow" in resultaat.stderr
