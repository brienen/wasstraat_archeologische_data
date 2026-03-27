"""
Flask smoke tests — verifieert dat de Flask app opstart en de kaart zichtbaar is.

Draait tegen echte Docker services (PostgreSQL + Redis + Flask).
Gebruik: make test-flask
"""
import pytest
import time
import requests


FLASK_BASE_URL = "http://localhost:5061"
MAX_WAIT_SECONDS = 90
POLL_INTERVAL = 3


@pytest.fixture(scope="module", autouse=True)
def wait_for_flask():
    """Wacht tot Flask beschikbaar is voordat tests starten."""
    print(f"\n  Wachten op Flask ({FLASK_BASE_URL})...")
    deadline = time.time() + MAX_WAIT_SECONDS
    last_error = None
    while time.time() < deadline:
        try:
            resp = requests.get(f"{FLASK_BASE_URL}/login/", timeout=5)
            if resp.status_code < 500:
                print(f"  Flask is klaar (status {resp.status_code})")
                return
        except requests.ConnectionError as e:
            last_error = e
        time.sleep(POLL_INTERVAL)
    pytest.fail(f"Flask niet bereikbaar na {MAX_WAIT_SECONDS}s: {last_error}")


@pytest.mark.flask_smoke
class TestFlaskStartup:
    """Verifieer dat Flask zonder fouten opstart."""

    def test_index_page_returns_200(self):
        """De indexpagina moet HTTP 200 retourneren."""
        resp = requests.get(f"{FLASK_BASE_URL}/", timeout=10, allow_redirects=True)
        assert resp.status_code == 200, f"Verwacht 200, kreeg {resp.status_code}"

    def test_index_page_contains_folium_map(self):
        """De indexpagina moet een Folium/Leaflet kaart bevatten."""
        resp = requests.get(f"{FLASK_BASE_URL}/", timeout=10, allow_redirects=True)
        html = resp.text.lower()
        assert "leaflet" in html or "l.map" in html or "folium" in html, \
            "Geen Leaflet/Folium kaart gevonden in de indexpagina"

    def test_index_page_contains_delft_coordinates(self):
        """De kaart moet gecentreerd zijn op Delft (52.00667, 4.35556)."""
        resp = requests.get(f"{FLASK_BASE_URL}/", timeout=10, allow_redirects=True)
        html = resp.text
        assert "52.00667" in html or "52.006" in html, \
            "Delft latitude (52.00667) niet gevonden in kaart"
        assert "4.35556" in html or "4.355" in html, \
            "Delft longitude (4.35556) niet gevonden in kaart"

    def test_login_page_accessible(self):
        """De login-pagina moet bereikbaar zijn (FAB security werkt)."""
        resp = requests.get(f"{FLASK_BASE_URL}/login/", timeout=10)
        assert resp.status_code == 200

    def test_login_page_contains_form(self):
        """De login-pagina moet een inlogformulier bevatten."""
        resp = requests.get(f"{FLASK_BASE_URL}/login/", timeout=10)
        html = resp.text.lower()
        assert "<form" in html, "Geen formulier gevonden op login-pagina"
        assert "password" in html, "Geen wachtwoordveld op login-pagina"


@pytest.mark.flask_smoke
class TestFlaskStaticAssets:
    """Verifieer dat statische bestanden geserveerd worden."""

    def test_static_css_served(self):
        """Custom CSS moet beschikbaar zijn."""
        resp = requests.get(f"{FLASK_BASE_URL}/static/css/arch.css", timeout=10)
        assert resp.status_code == 200, "arch.css niet gevonden"

    def test_static_js_served(self):
        """Custom JavaScript moet beschikbaar zijn."""
        resp = requests.get(f"{FLASK_BASE_URL}/static/js/main.js", timeout=10)
        # 200 of 304 (cached) zijn beide acceptabel
        assert resp.status_code in (200, 304), f"main.js niet gevonden: {resp.status_code}"
