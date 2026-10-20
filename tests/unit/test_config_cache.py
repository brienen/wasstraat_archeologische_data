"""
Unit tests voor de cache-instellingen in shared/config.py.

Omgevingsvariabelen zijn altijd tekst. Flask-Caching geeft de timeout door
aan cachelib, en vanaf cachelib 0.14 leidt een tekstwaarde tot een TypeError
waardoor de Flask-app niet start. Deze tests laden de echte config-module
(niet de mock uit conftest.py) met gezette omgevingsvariabelen.
"""
import importlib.util
import os

import pytest

CONFIG_PAD = os.path.abspath(
    os.path.join(os.path.dirname(__file__), '..', '..', 'shared', 'config.py')
)

BASIS_OMGEVING = {
    "POSTGRES_DB": "test",
    "POSTGRES_USER": "test",
    "POSTGRES_PASSWORD": "test",
}


def laadEchteConfig(monkeypatch, extra_omgeving):
    """Laad shared/config.py als losse module met de opgegeven omgevingsvariabelen.

    Args:
        monkeypatch: pytest-fixture om omgevingsvariabelen tijdelijk te zetten.
        extra_omgeving: dict met aanvullende omgevingsvariabelen.

    Returns:
        De geladen config-module.
    """
    for naam, waarde in {**BASIS_OMGEVING, **extra_omgeving}.items():
        monkeypatch.setenv(naam, waarde)
    spec = importlib.util.spec_from_file_location("wasstraat_echte_config", CONFIG_PAD)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.unit
class TestCacheInstellingen:
    """Cache-instellingen moeten getallen zijn, ook als ze uit de omgeving komen."""

    def test_timeout_uit_omgeving_is_int(self, monkeypatch):
        config = laadEchteConfig(monkeypatch, {"CACHE_DEFAULT_TIMEOUT": "300"})
        assert config.CACHE_DEFAULT_TIMEOUT == 300
        assert isinstance(config.CACHE_DEFAULT_TIMEOUT, int)

    def test_timeout_default_is_int(self, monkeypatch):
        monkeypatch.delenv("CACHE_DEFAULT_TIMEOUT", raising=False)
        config = laadEchteConfig(monkeypatch, {})
        assert config.CACHE_DEFAULT_TIMEOUT == 300

    @pytest.mark.parametrize("naam,waarde,verwacht", [
        ("CACHE_REDIS_PORT", "6380", 6380),
        ("CACHE_REDIS_DB", "2", 2),
    ])
    def test_redis_instellingen_uit_omgeving_zijn_int(self, monkeypatch, naam, waarde, verwacht):
        config = laadEchteConfig(monkeypatch, {naam: waarde})
        assert getattr(config, naam) == verwacht
        assert isinstance(getattr(config, naam), int)

    def test_cachelib_accepteert_timeout(self, monkeypatch):
        """De timeout moet door cachelib geaccepteerd worden, ongeacht de versie."""
        cachelib = pytest.importorskip("cachelib")
        config = laadEchteConfig(monkeypatch, {"CACHE_DEFAULT_TIMEOUT": "60"})
        cache = cachelib.SimpleCache(default_timeout=config.CACHE_DEFAULT_TIMEOUT)
        assert cache.default_timeout == 60
