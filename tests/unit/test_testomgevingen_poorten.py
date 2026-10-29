"""
Unit tests voor de hostpoorten van de testomgevingen (issue 87).

De synthetische testomgeving (docker-compose.test.yml, make integration) en de
Delftse (docker-compose.delft-test.yml, make integration-delft) moeten tegelijk
kunnen draaien, en allebei naast een installatie (docker-compose.yml). Tot
issue 87 gebruikten beide testomgevingen MongoDB-hostpoort 27117. Deze tests
parsen de compose-bestanden en eisen dat de hostpoorten disjunct zijn, en dat
de integratietests en de Makefile de juiste MongoDB-poort gebruiken.
"""
import os
import re

import pytest
import yaml


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SYNTHETISCH = "docker-compose.test.yml"
DELFT = "docker-compose.delft-test.yml"
INSTALLATIE = ["docker-compose.yml", "docker-compose.delft.yml", "docker-compose.develop.yml"]


def leesBestand(pad):
    with open(os.path.join(PROJECT_ROOT, pad), encoding="utf-8") as f:
        return f.read()


def hostpoort(poort):
    """Hostpoort uit een poortregel van een compose-bestand ('27117:27017', '127.0.0.1:8080:8080', 9200)."""
    delen = str(poort).split(":")
    if len(delen) == 1:
        return None  # alleen een containerpoort: Docker kiest een willekeurige hostpoort
    return int(delen[-2])


def hostpoorten(pad):
    """Dict van hostpoort naar service voor alle services in een compose-bestand."""
    poorten = {}
    for naam, service in yaml.safe_load(leesBestand(pad))["services"].items():
        for poort in (service or {}).get("ports", []):
            host = hostpoort(poort)
            if host is None:
                continue
            assert host not in poorten, f"{pad}: hostpoort {host} dubbel ({poorten[host]} en {naam})"
            poorten[host] = naam
    return poorten


def mongoPoort(pad):
    """Hostpoort van de MongoDB-service van een testomgeving."""
    return {service: poort for poort, service in hostpoorten(pad).items()}["mongo-test"]


def standaardMongoPoort(testbestand, variabele="MONGO_TEST_URI"):
    """Poort in de standaardwaarde van os.getenv(variabele, 'mongodb://...:<poort>/') in een testbestand."""
    match = re.search(rf'os\.getenv\(\s*"{variabele}",\s*"mongodb://[^"]*@localhost:(\d+)/', leesBestand(testbestand))
    assert match, f"Geen standaardwaarde voor {variabele} in {testbestand}"
    return int(match.group(1))


@pytest.mark.unit
class TestHostpoortenTestomgevingen:

    def test_testomgevingen_hebben_disjuncte_hostpoorten(self):
        synthetisch, delft = hostpoorten(SYNTHETISCH), hostpoorten(DELFT)
        assert synthetisch and delft
        gedeeld = set(synthetisch) & set(delft)
        assert not gedeeld, f"Hostpoorten in beide testomgevingen: {sorted(gedeeld)}"

    def test_testomgevingen_naast_een_installatie(self):
        installatie = set()
        for pad in INSTALLATIE:
            installatie |= set(hostpoorten(pad))
        for pad in (SYNTHETISCH, DELFT):
            gedeeld = set(hostpoorten(pad)) & installatie
            assert not gedeeld, f"{pad} gebruikt hostpoorten van de installatie: {sorted(gedeeld)}"

    def test_mongo_hostpoorten(self):
        assert mongoPoort(SYNTHETISCH) == 27117
        assert mongoPoort(DELFT) == 27118

    def test_makefile_geeft_delftse_tests_de_delftse_mongo(self):
        makefile = leesBestand("Makefile")
        match = re.search(r"^MONGO_TEST_URI_DELFT := mongodb://[^@]*@localhost:(\d+)/$", makefile, re.M)
        assert match and int(match.group(1)) == mongoPoort(DELFT)
        # Elke pytest-aanroep van de Delftse targets krijgt die URI mee
        for doel in ("integration-delft", "integration-delft-pipeline"):
            recept = re.search(rf"^{doel}:.*?(?=^\S|\Z)", makefile, re.M | re.S).group(0)
            aanroepen = [r for r in recept.splitlines() if "$(PYTEST)" in r]
            assert aanroepen, doel
            assert all("MONGO_TEST_URI=$(MONGO_TEST_URI_DELFT)" in r for r in aanroepen), (doel, aanroepen)

    def test_standaardpoorten_in_de_integratietests(self):
        """Losse pytest-aanroepen zonder MONGO_TEST_URI vinden de juiste MongoDB."""
        assert standaardMongoPoort("tests/integration/test_full_pipeline_delft_data.py") == mongoPoort(DELFT)
        assert standaardMongoPoort("tests/integration/test_verwerkingsrapport.py",
                                   "MONGO_TEST_URI_DELFT") == mongoPoort(DELFT)
        for testbestand in ("tests/integration/test_full_pipeline_synthetic_data.py",
                            "tests/integration/test_incremental_synthetic_data.py",
                            "tests/integration/test_verwerkingsrapport.py"):
            assert standaardMongoPoort(testbestand) == mongoPoort(SYNTHETISCH), testbestand
