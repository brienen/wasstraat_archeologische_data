"""
Unit tests voor het maskeren van wachtwoorden in de logs (issue 77).

shared/database.py, shared/fulltext.py en de laadstap logden de volledige
SQLALCHEMY_DATABASE_URI, inclusief het PostgreSQL-wachtwoord. Ze loggen nu
via shared.logutils.maskeerWachtwoord(). Deze tests bewaken de helper en
controleren met caplog dat de drie plekken het wachtwoord niet meer loggen.
"""
import importlib.util
import logging
import os
import sys
from unittest.mock import MagicMock

import pytest

from shared.logutils import MASKER, maskeerWachtwoord


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
WACHTWOORD = "Geheim-Wachtwoord-77"
URI_MET_WACHTWOORD = f"postgresql://wasstraat:{WACHTWOORD}@postgres:5432/wasstraat"
GEMASKEERDE_URI = "postgresql://wasstraat:***@postgres:5432/wasstraat"


class StopNaLog(Exception):
    """Breekt de geteste functie af direct na de logregel, vóór er iets verbindt."""


def laadSharedModule(naam):
    """Laad een echte module uit shared/ als losse module (conftest mockt het pakket 'shared').

    Args:
        naam: Bestandsnaam zonder .py, bijv. 'database'.

    Returns:
        De geladen module; shared.config is daarin de mock uit conftest.py.
    """
    pad = os.path.join(PROJECT_ROOT, "shared", f"{naam}.py")
    spec = importlib.util.spec_from_file_location(f"wasstraat_echte_{naam}", pad)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def uriMetWachtwoord(monkeypatch):
    """Zet in de gemockte shared.config een database-URI met een herkenbaar wachtwoord."""
    monkeypatch.setattr(sys.modules["shared.config"], "SQLALCHEMY_DATABASE_URI", URI_MET_WACHTWOORD)
    return URI_MET_WACHTWOORD


@pytest.mark.unit
class TestMaskeerWachtwoord:
    """maskeerWachtwoord vervangt alleen het wachtwoord door '***'."""

    @pytest.mark.parametrize("uri,verwacht", [
        ("postgresql://wasstraat:geheim@postgres/wasstraat",
         "postgresql://wasstraat:***@postgres/wasstraat"),
        ("postgresql+psycopg2://testuser:testpass@postgres:5432/airflow_test",
         "postgresql+psycopg2://testuser:***@postgres:5432/airflow_test"),
        ("mongodb://root:geheim@mongo/?authSource=admin",
         "mongodb://root:***@mongo/?authSource=admin"),
        ("mongodb://root:geheim@mongo/Arch_Staging?authSource=admin",
         "mongodb://root:***@mongo/Arch_Staging?authSource=admin"),
        ("mongodb://root:geheim@mongo1:27017,mongo2:27017/db?replicaSet=rs0",
         "mongodb://root:***@mongo1:27017,mongo2:27017/db?replicaSet=rs0"),
        ("redis://:geheim@redis:6379/0", "redis://:***@redis:6379/0"),
    ])
    def test_wachtwoord_vervangen(self, uri, verwacht):
        assert maskeerWachtwoord(uri) == verwacht

    @pytest.mark.parametrize("wachtwoord", ["ge@heim", "ge/heim", "ge:heim", "ge%40heim", "a@b/c:d"])
    def test_wachtwoord_met_bijzondere_tekens_volledig_gemaskeerd(self, wachtwoord):
        resultaat = maskeerWachtwoord(f"postgresql://wasstraat:{wachtwoord}@postgres/wasstraat")
        assert resultaat == "postgresql://wasstraat:***@postgres/wasstraat"
        assert wachtwoord not in resultaat

    @pytest.mark.parametrize("uri", [
        "postgresql://postgres/wasstraat",
        "postgresql://wasstraat@postgres/wasstraat",
        "mongodb://mongo:27017/?authSource=admin",
        "http://elasticsearch:9200",
        "sqlite:///app.db",
        "geen uri",
    ])
    def test_zonder_wachtwoord_ongewijzigd(self, uri):
        assert maskeerWachtwoord(uri) == uri

    @pytest.mark.parametrize("leeg", [None, ""])
    def test_leeg_of_none_ongewijzigd(self, leeg):
        assert maskeerWachtwoord(leeg) == leeg

    def test_ongevulde_config_logt_geen_none_wachtwoord(self):
        """Zonder omgevingsvariabelen bouwt config.py 'postgresql://None:None@postgres/None'."""
        assert maskeerWachtwoord("postgresql://None:None@postgres/None") == "postgresql://None:***@postgres/None"

    def test_object_met_uri_als_tekst(self):
        class UriObject:
            def __str__(self):
                return "mongodb://root:geheim@mongo/"

        assert maskeerWachtwoord(UriObject()) == "mongodb://root:***@mongo/"

    def test_masker_is_drie_sterretjes(self):
        assert MASKER == "***"


@pytest.mark.unit
class TestGeenWachtwoordInLog:
    """De plekken die met PostgreSQL verbinden loggen de URI zonder wachtwoord."""

    def test_database_get_all_tables(self, uriMetWachtwoord, caplog):
        database = laadSharedModule("database")
        database.create_engine = MagicMock()
        metadata = MagicMock()
        metadata.tables.keys.return_value = ["Def_Project", "Def_Bronbestand", "ab_user"]
        database.MetaData = MagicMock(return_value=metadata)

        with caplog.at_level(logging.INFO):
            tabellen = database.getAllTables()

        assert tabellen == ["Def_Project"]
        database.create_engine.assert_called_once_with(URI_MET_WACHTWOORD)
        assert WACHTWOORD not in caplog.text
        assert f"Connecting to {GEMASKEERDE_URI}" in caplog.text

    def test_fulltext_index_table(self, uriMetWachtwoord, caplog):
        fulltext = laadSharedModule("fulltext")
        fulltext.create_engine = MagicMock()
        fulltext.Elasticsearch = MagicMock(side_effect=StopNaLog)

        with caplog.at_level(logging.INFO):
            with pytest.raises(StopNaLog):
                fulltext.indexTable("Def_Project")

        assert WACHTWOORD not in caplog.text
        assert f"Connecting to {GEMASKEERDE_URI}" in caplog.text

    def test_load_all(self, uriMetWachtwoord, caplog, monkeypatch):
        import wasstraat.loadToDatabase_functions as load

        monkeypatch.setattr(load, "getPgConnection", MagicMock(side_effect=StopNaLog))

        with caplog.at_level(logging.INFO):
            with pytest.raises(StopNaLog):
                load.loadAll()

        assert WACHTWOORD not in caplog.text
        assert f"Connecting to {GEMASKEERDE_URI}" in caplog.text
