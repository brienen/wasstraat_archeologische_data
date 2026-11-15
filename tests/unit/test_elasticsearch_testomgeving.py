"""
Unit tests voor Elasticsearch in de testomgevingen.

Beide testomgevingen (synthetisch en Delfts) hebben een eigen Elasticsearch, zodat de
Index_*-taken van DAG_Load_Only en van de cycli daar slagen en de pipelinetests streng
kunnen zijn. Zonder Elasticsearch faalden de Index-taken in de Delftse testomgeving en
accepteerde de laadtest een mislukte DAG_Load_Only (tot 2026-10-21).
"""
import os

import pytest
import yaml


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TESTCOMPOSES = ["docker-compose.test.yml", "docker-compose.delft-test.yml"]


def leesBestand(pad):
    with open(os.path.join(PROJECT_ROOT, pad), encoding="utf-8") as f:
        return f.read()


def leesCompose(pad):
    return yaml.safe_load(leesBestand(pad))


@pytest.mark.unit
class TestElasticsearchInTestomgeving:

    @pytest.mark.parametrize("pad", TESTCOMPOSES)
    def test_eigen_elasticsearch_zonder_hostpoort(self, pad):
        """Poort 9200 op de host is van de echte installatie."""
        es = leesCompose(pad)["services"]["elasticsearch-test"]
        assert es["image"].startswith("docker.elastic.co/elasticsearch/elasticsearch:8.")
        assert "ports" not in es
        assert es["environment"]["discovery.type"] == "single-node"
        assert es["environment"]["xpack.security.enabled"] == "false"
        assert "healthcheck" in es

    @pytest.mark.parametrize("pad", TESTCOMPOSES)
    def test_bereikbaar_als_elasticsearch(self, pad):
        """ES_HOST van Airflow en Flask wijst naar de netwerkalias elasticsearch."""
        services = leesCompose(pad)["services"]
        netwerken = services["elasticsearch-test"]["networks"]
        assert any("elasticsearch" in n.get("aliases", []) for n in netwerken.values())
        for naam in ("airflow-test", "flask-test"):
            assert services[naam]["environment"]["ES_HOST"] == "http://elasticsearch:9200", naam

    @pytest.mark.parametrize("pad", TESTCOMPOSES)
    def test_airflow_wacht_op_gezonde_elasticsearch(self, pad):
        depends = leesCompose(pad)["services"]["airflow-test"]["depends_on"]
        assert isinstance(depends, dict), "depends_on moet de dict-vorm hebben voor condition"
        assert depends["elasticsearch-test"]["condition"] == "service_healthy"

    def test_containernamen_verschillen(self):
        namen = {leesCompose(pad)["services"]["elasticsearch-test"]["container_name"] for pad in TESTCOMPOSES}
        assert namen == {"wasstraat_elasticsearch_test", "wasstraat_elasticsearch_delft_test"}

    def test_makefile_start_elasticsearch_naast_airflow_test(self):
        """Elke up-regel van een testomgeving die airflow-test start, start ook elasticsearch-test."""
        for regel in leesBestand("Makefile").splitlines():
            if "up -d" in regel and "airflow-test" in regel:
                assert "elasticsearch-test" in regel, regel

    def test_delftse_laadtest_eist_geslaagde_load(self):
        """De Delftse test accepteert geen mislukte DAG_Load_Only meer."""
        test = leesBestand("tests/integration/test_full_pipeline_delft_data.py")
        assert "verwacht: Elasticsearch niet beschikbaar" not in test
        assert "test_33c_verify_elasticsearch_gelijk_aan_postgres" in test
