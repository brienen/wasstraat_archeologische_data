"""
Unit tests voor de pakketten van de Jupyter-image (issue 78).

Notebooks gebruiken de pipelinecode (airflow_app/dags, in de container /opt/wasstraat).
Die importeert 'roman', dat in de image ontbrak. Daarnaast legde de image een
Elasticsearch-client 9.x vast, terwijl de server 8.17 draait; een 9.x-client weigert
een 8.x-server. Deze tests bewaken de pip-opdracht in services/jupyter/Dockerfile en de
vastgelegde versies in services/jupyter/constraints.txt.
"""
import os
import re

import pytest
import yaml


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def leesBestand(pad):
    with open(os.path.join(PROJECT_ROOT, pad), encoding="utf-8") as f:
        return f.read()


def leesConstraints(pad):
    """Lees een constraints-bestand als dict {pakketnaam in kleine letters: versie}."""
    versies = {}
    for regel in leesBestand(pad).splitlines():
        regel = regel.strip()
        if regel and not regel.startswith("#"):
            naam, _, versie = regel.partition("==")
            versies[naam.lower()] = versie
    return versies


def pipOpdrachtJupyter():
    """De pip install-opdracht uit de Jupyter-Dockerfile, met de regelvoortzettingen samengevoegd."""
    dockerfile = leesBestand("services/jupyter/Dockerfile").replace("\\\n", " ")
    opdrachten = [r for r in dockerfile.splitlines() if "pip install" in r]
    assert len(opdrachten) == 1, opdrachten
    return opdrachten[0]


def elasticsearchServerVersie():
    """Versie van de Elasticsearch-server uit docker-compose.yml, bijv. '8.17.0'."""
    image = yaml.safe_load(leesBestand("docker-compose.yml"))["services"]["elasticsearch"]["image"]
    return image.rsplit(":", 1)[1]


@pytest.mark.unit
class TestJupyterImage:
    """De Jupyter-image kan de pipelinecode importeren en praat met de Elasticsearch-server."""

    def test_pipelinecode_gebruikt_roman(self):
        """Voorwaarde van deze tests: de pipelinecode importeert roman echt."""
        for pad in ("airflow_app/dags/wasstraat/archutils.py", "airflow_app/dags/wasstraat/references_functions.py"):
            assert re.search(r"^import roman$", leesBestand(pad), re.M), pad

    def test_pip_installeert_roman(self):
        assert re.search(r'"roman[>=<,.\d]*"|\sroman\s', pipOpdrachtJupyter())

    def test_roman_vastgelegd(self):
        assert "roman" in leesConstraints("services/jupyter/constraints.txt")

    def test_pip_begrenst_elasticsearch_op_minorversie_van_de_server(self):
        hoofd, minor = elasticsearchServerVersie().split(".")[:2]
        grens = f'"elasticsearch>={hoofd}.{minor},<{hoofd}.{int(minor) + 1}"'
        assert grens in pipOpdrachtJupyter(), f"verwacht {grens} in de pip-opdracht"

    def test_elasticsearch_client_vastgelegd_op_versie_van_de_server(self):
        server = elasticsearchServerVersie()
        client = leesConstraints("services/jupyter/constraints.txt")["elasticsearch"]
        assert client.split(".")[:2] == server.split(".")[:2], (
            f"Jupyter legt elasticsearch {client} vast, de server is {server}"
        )

    @pytest.mark.parametrize("pad", ["services/flask/constraints.txt", "services/jupyter/constraints.txt"])
    def test_elasticsearch_client_heeft_hoofdversie_van_de_server(self, pad):
        """Een client met een hogere hoofdversie (9.x bij server 8.x) weigert de server."""
        server = elasticsearchServerVersie()
        constraints = leesConstraints(pad)
        for pakket in ("elasticsearch", "elastic-transport"):
            if pakket in constraints:
                assert constraints[pakket].split(".")[0] == server.split(".")[0], (
                    f"{pad}: {pakket}=={constraints[pakket]} bij server {server}"
                )
