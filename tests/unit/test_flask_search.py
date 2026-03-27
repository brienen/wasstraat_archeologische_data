"""
Unit tests voor de search-logica.

Test het gedrag van query_index en remove_from_index bij ontbrekende
Elasticsearch-verbinding — zonder de volledige Flask app op te starten.
"""
import pytest
import sys
import os
import types
from unittest.mock import MagicMock

# Mock de 'app' module voordat search.py geïmporteerd wordt
# (search.py doet 'from app import db' op module-level)
_app_path = os.path.join(os.path.dirname(__file__), '..', '..', 'app', 'app')
if os.path.abspath(_app_path) not in sys.path:
    sys.path.insert(0, os.path.abspath(_app_path))


@pytest.fixture
def search_module():
    """Laad search.py met gemockte app/db/cache dependencies."""
    # Mock de 'app' module
    mock_app_module = types.ModuleType("app")
    mock_app_module.db = MagicMock()
    mock_app_module.appbuilder = MagicMock()

    # Mock caching module
    mock_cache_module = types.ModuleType("caching")
    mock_cache = MagicMock()
    mock_cache.memoize = lambda *a, **kw: lambda f: f
    mock_cache.delete_memoized = MagicMock()
    mock_cache_module.cache = mock_cache

    # Mock fulltext module
    mock_fulltext = types.ModuleType("shared.fulltext")
    mock_fulltext.getCols = MagicMock(return_value=[])

    # Mock models
    mock_models = types.ModuleType("models")
    mock_models.Bestand = type("Bestand", (), {"__mapper_args__": {}})
    mock_models.Artefact = type("Artefact", (), {"__mapper_args__": {}})

    # Bewaar originele modules
    saved = {}
    for mod_name in ["app", "caching", "shared.fulltext", "models"]:
        if mod_name in sys.modules:
            saved[mod_name] = sys.modules[mod_name]

    sys.modules["app"] = mock_app_module
    sys.modules["caching"] = mock_cache_module
    sys.modules["shared.fulltext"] = mock_fulltext
    sys.modules["models"] = mock_models

    # Verwijder search uit cache zodat het opnieuw geladen wordt
    if "search" in sys.modules:
        del sys.modules["search"]

    import search

    yield search, mock_cache

    # Herstel originele modules
    for mod_name, mod in saved.items():
        sys.modules[mod_name] = mod
    if "search" in sys.modules:
        del sys.modules["search"]


class TestQueryIndex:
    """Test query_index() bij ontbrekende Elasticsearch."""

    def test_no_elasticsearch_returns_empty(self, search_module):
        search, _ = search_module
        from flask import Flask
        app = Flask(__name__)
        app.elasticsearch = None

        with app.app_context():
            class FakeModel:
                __tablename__ = "test"

            result, count = search.query_index(FakeModel, "zoekterm")
            assert result == []
            assert count == 0

    def test_no_tablename_returns_empty(self, search_module):
        search, _ = search_module
        from flask import Flask
        app = Flask(__name__)
        app.elasticsearch = MagicMock()

        with app.app_context():
            class BadModel:
                pass

            result, count = search.query_index(BadModel, "zoekterm")
            assert result == []
            assert count == 0


class TestRemoveFromIndex:
    """Test remove_from_index() bij ontbrekende Elasticsearch."""

    def test_no_elasticsearch_does_nothing(self, search_module):
        search, _ = search_module
        from flask import Flask
        app = Flask(__name__)
        app.elasticsearch = None

        with app.app_context():
            class FakeModel:
                __tablename__ = "test"
                primary_key = 1

            search.remove_from_index(FakeModel)
            # Geen exception = succes
