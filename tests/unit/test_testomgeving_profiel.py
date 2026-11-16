"""
Unit tests voor het gemeenteprofiel van de synthetische testomgeving.

De synthetische testomgeving draait standaard met het profiel delft; een ander profiel
kies je met GEMEENTE (make integration GEMEENTE=voorbeeld). De pipelinetests lezen het
actieve profiel uit de Airflow-container en kiezen daarmee hun verwachtingen voor
bestanden (tests/integration/testomgeving.py). Tot 16 november 2026 stond het profiel
nergens in de testomgeving en gingen de tests stilzwijgend uit van het Delftse profiel;
een run met het voorbeeldprofiel liet 14 van de 111 pipelinetests falen.

Ook getest: splitsPsqlUitvoer, de parser achter pgRijen van de integratietests. Die liet
tot dezelfde datum een lege eerste waarde van de eerste rij wegvallen.
"""
import importlib
import os
import re
import types

import pytest
import yaml

import wasstraat.profielen as profielen
from tests.integration import testomgeving


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# Objectfoto uit de synthetische data, in de Delftse naamconventie
OBJECTFOTO = {"fileName": "SY002_P2_H4_1_1.jpg",
              "fullFileName": "/input/projecten/SY002/L Fotos/H (Objectfoto's)/Aardewerk/SY002_P2_H4_1_1.jpg"}


def leesBestand(pad):
    with open(os.path.join(PROJECT_ROOT, pad), encoding="utf-8") as f:
        return f.read()


def leesCompose(pad):
    return yaml.safe_load(leesBestand(pad))


@pytest.mark.unit
class TestProfielInTestomgeving:

    def test_synthetische_testomgeving_instelbaar_met_standaard_delft(self):
        omgeving = leesCompose("docker-compose.test.yml")["services"]["airflow-test"]["environment"]
        assert omgeving["WASSTRAAT_GEMEENTE"] == "${WASSTRAAT_GEMEENTE:-delft}"

    def test_delftse_testomgeving_vast_op_delft(self):
        """De Delftse testdata en de referentie-uitkomst horen bij het Delftse profiel."""
        omgeving = leesCompose("docker-compose.delft-test.yml")["services"]["airflow-test"]["environment"]
        assert omgeving["WASSTRAAT_GEMEENTE"] == "delft"

    def test_makefile_geeft_gemeente_door_aan_synthetische_testomgeving(self):
        makefile = leesBestand("Makefile")
        assert re.search(r"^GEMEENTE \?= delft$", makefile, re.M), "GEMEENTE heeft niet de standaard delft"
        compose_test = re.search(r"^COMPOSE_TEST := (.*)$", makefile, re.M).group(1)
        assert compose_test.startswith("WASSTRAAT_GEMEENTE=$(GEMEENTE) "), compose_test
        assert "-p wasstraat-test -f docker-compose.test.yml" in compose_test
        compose_delft_test = re.search(r"^COMPOSE_DELFT_TEST := (.*)$", makefile, re.M).group(1)
        assert "GEMEENTE" not in compose_delft_test

    def test_standaard_gelijk_aan_pipeline(self):
        assert testomgeving.STANDAARD_PROFIEL == profielen.STANDAARD_GEMEENTE

    def test_lijst_bevat_alleen_bekende_profielen(self):
        assert set(testomgeving.PROFIELEN_MET_DELFTSE_BESTANDSNAMEN) <= set(profielen.PROFIELEN)

    @pytest.mark.parametrize("gemeente", sorted(profielen.PROFIELEN))
    def test_lijst_klopt_met_de_profielen(self, gemeente):
        """Een profiel staat in de lijst precies als het de synthetische objectfoto als objectfoto herkent.

        Komt er een profiel bij dat de Delftse bestandsnamen ontleedt, of valt de herkenning in
        een bestaand profiel weg, dan faalt deze test en moet de lijst (of het profiel) worden aangepast.
        """
        module, klasse = profielen.PROFIELEN[gemeente]
        profiel = getattr(importlib.import_module(module), klasse)()
        uitkomst = profiel.identificeer_foto(dict(OBJECTFOTO), "SY002")
        herkend = uitkomst is not None and uitkomst.get("bestandsoort") == "Objectfoto"
        assert herkend == testomgeving.herkentBestandsnamen(gemeente), (
            f"Profiel {gemeente}: objectfoto herkend = {herkend}; "
            f"werk PROFIELEN_MET_DELFTSE_BESTANDSNAMEN in tests/integration/testomgeving.py bij")

    def test_pipelinetests_gebruiken_het_actieve_profiel(self):
        """De tests met verwachtingen voor bestanden kiezen die op het profiel van de testomgeving."""
        keten = leesBestand("tests/integration/test_full_pipeline_synthetic_data.py")
        for test in ("test_10e_verify_objectfotos_genormaliseerd", "test_10f_verify_objectfotos_gekoppeld_aan_artefact",
                     "test_22b_verify_postgres_bestand_gekoppeld_aan_artefact"):
            romp = keten.split(f"def {test}(")[1].split("\n    def ")[0]
            assert "alleenMetHerkenningVanBestandsnamen()" in romp, test
        romp = keten.split("def test_10h_verify_bestanden_zonder_herkenning_van_bestandsnamen(")[1].split("\n    def ")[0]
        assert "alleenZonderHerkenningVanBestandsnamen()" in romp
        assert "testomgeving.herkentBestandsnamen()" in leesBestand("tests/integration/test_incremental_synthetic_data.py")


@pytest.fixture
def nepDocker(monkeypatch):
    """Vervang docker exec door een antwoord per test; onthoudt de aanroepen en leegt de cache."""
    aanroepen = []
    antwoord = {"stdout": "", "returncode": 0, "stderr": ""}

    def run(cmd, **kwargs):
        aanroepen.append(cmd)
        return types.SimpleNamespace(**antwoord)

    monkeypatch.setattr(testomgeving.subprocess, "run", run)
    monkeypatch.setattr(testomgeving, "_profiel_per_container", {})
    return antwoord, aanroepen


@pytest.mark.unit
class TestActiefProfiel:

    @pytest.mark.parametrize("uitvoer, verwacht", [
        ("voorbeeld\n", "voorbeeld"),
        ("delft\n", "delft"),
        (" VoorBeeld \n", "voorbeeld"),
        ("\n", "delft"),
        ("", "delft"),
    ])
    def test_leest_profiel_uit_container(self, nepDocker, uitvoer, verwacht):
        antwoord, aanroepen = nepDocker
        antwoord["stdout"] = uitvoer
        assert testomgeving.actiefProfiel() == verwacht
        assert aanroepen[0][:3] == ["docker", "exec", testomgeving.AIRFLOW_CONTAINER]
        assert "WASSTRAAT_GEMEENTE" in aanroepen[0][-1]

    def test_onthoudt_het_profiel_per_container(self, nepDocker):
        antwoord, aanroepen = nepDocker
        antwoord["stdout"] = "voorbeeld\n"
        assert testomgeving.actiefProfiel("container_a") == "voorbeeld"
        antwoord["stdout"] = "delft\n"
        assert testomgeving.actiefProfiel("container_a") == "voorbeeld"
        assert testomgeving.actiefProfiel("container_b") == "delft"
        assert len(aanroepen) == 2

    def test_onbereikbare_container_geeft_fout(self, nepDocker):
        antwoord, _ = nepDocker
        antwoord.update(returncode=1, stderr="Error response from daemon: No such container: wasstraat_airflow_test")
        with pytest.raises(RuntimeError, match="niet te lezen uit wasstraat_airflow_test"):
            testomgeving.actiefProfiel("wasstraat_airflow_test")

    @pytest.mark.parametrize("profiel, verwacht", [("delft", True), ("voorbeeld", False), ("rotterdam", False)])
    def test_herkent_bestandsnamen(self, profiel, verwacht):
        assert testomgeving.herkentBestandsnamen(profiel) is verwacht

    def test_herkent_bestandsnamen_van_het_actieve_profiel(self, nepDocker):
        antwoord, _ = nepDocker
        antwoord["stdout"] = "voorbeeld\n"
        assert testomgeving.herkentBestandsnamen() is False


@pytest.mark.unit
class TestSplitsPsqlUitvoer:

    @pytest.mark.parametrize("uitvoer, verwacht", [
        ("PSY001\t0\nPSY002\t1\n", [["PSY001", "0"], ["PSY002", "1"]]),
        # Lege key in de eerste rij: bestanden zonder key bij een profiel zonder herkenning van bestandsnamen
        ("\t0\nR/input/projecten/SY001/Dagrapport.docx\t14\n", [["", "0"], ["R/input/projecten/SY001/Dagrapport.docx", "14"]]),
        # Lege laatste waarde van de laatste rij
        ("1\ta\n2\t\n", [["1", "a"], ["2", ""]]),
        # Rij met alleen lege waarden blijft een rij
        ("\t\n3\tb\n", [["", ""], ["3", "b"]]),
        # Spaties in een waarde blijven staan
        (" a \t1\n", [[" a ", "1"]]),
        ("5\n", [["5"]]),
        ("", []),
        ("\n", []),
    ])
    def test_rijen(self, uitvoer, verwacht):
        assert testomgeving.splitsPsqlUitvoer(uitvoer) == verwacht

    @pytest.mark.parametrize("pad", ["tests/integration/test_incremental_synthetic_data.py",
                                     "tests/integration/test_verwerkingsrapport.py"])
    def test_pgRijen_gebruikt_de_parser(self, pad):
        test = leesBestand(pad)
        assert "testomgeving.splitsPsqlUitvoer(resultaat.stdout)" in test
        assert "stdout.strip().split" not in test
