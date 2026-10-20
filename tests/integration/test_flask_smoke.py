"""
Flask smoke tests — verifieert dat de Flask app opstart en de kaart zichtbaar is.

Draait tegen echte Docker services (PostgreSQL + Redis + Flask).
Gebruik: make test-flask
"""
import pytest
import re
import time
import requests


FLASK_BASE_URL = "http://localhost:5061"
MAX_WAIT_SECONDS = 90
POLL_INTERVAL = 3
# Moet overeenkomen met FLASK_ADMIN_PASSWORD van flask-test in docker-compose.test.yml
FLASK_ADMIN_PASSWORD = "test-beheerder-wachtwoord"


def logIn(gebruikersnaam, wachtwoord):
    """
    Log in via het loginformulier van Flask-AppBuilder.

    Args:
        gebruikersnaam: Gebruikersnaam voor het formulier.
        wachtwoord: Wachtwoord voor het formulier.

    Returns:
        requests.Response: Antwoord op de POST, zonder redirects te volgen.
    """
    sessie = requests.Session()
    resp = sessie.get(f"{FLASK_BASE_URL}/login/", timeout=10)
    match = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', resp.text)
    assert match, "Geen csrf_token gevonden op login-pagina"
    return sessie.post(
        f"{FLASK_BASE_URL}/login/",
        data={"username": gebruikersnaam, "password": wachtwoord, "csrf_token": match.group(1)},
        timeout=10,
        allow_redirects=False,
    )


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
class TestFlaskBeheerder:
    """Verifieer dat de beheerder het wachtwoord uit FLASK_ADMIN_PASSWORD heeft."""

    def test_inloggen_met_wachtwoord_uit_configuratie(self):
        """Inloggen als admin met FLASK_ADMIN_PASSWORD moet lukken."""
        resp = logIn("admin", FLASK_ADMIN_PASSWORD)
        assert resp.status_code == 302, f"Verwacht redirect, kreeg {resp.status_code}"
        assert "/login" not in resp.headers.get("Location", ""), \
            "Inloggen met FLASK_ADMIN_PASSWORD mislukt (terug naar login-pagina)"

    def test_inloggen_met_oud_standaardwachtwoord_mislukt(self):
        """Het oude vaste wachtwoord 'admin' mag niet meer werken."""
        resp = logIn("admin", "admin")
        assert resp.status_code != 302 or "/login" in resp.headers.get("Location", ""), \
            "Inloggen met admin/admin lukte, terwijl FLASK_ADMIN_PASSWORD gezet is"


@pytest.mark.flask_smoke
class TestFlaskKaartProjecten:
    """Verifieer dat projecten zichtbaar zijn op de kaart."""

    def test_index_page_contains_project_markers(self):
        """De kaart moet minimaal 2 projectmarkers bevatten (SY001 + SY002)."""
        resp = requests.get(f"{FLASK_BASE_URL}/", timeout=10, allow_redirects=True)
        html = resp.text

        # Folium genereert L.circleMarker() calls in de HTML
        marker_count = html.lower().count("l.circlemarker")
        assert marker_count >= 2, (
            f"Verwacht minimaal 2 CircleMarkers op de kaart, gevonden {marker_count}. "
            f"Controleer of Def_Project gevuld is in PostgreSQL."
        )

    def test_index_page_contains_project_codes(self):
        """De projectcodes SY001 en SY002 moeten in de kaart-popups staan."""
        resp = requests.get(f"{FLASK_BASE_URL}/", timeout=10, allow_redirects=True)
        html = resp.text
        assert "SY001" in html, "Projectcode SY001 niet gevonden in kaart-HTML"
        assert "SY002" in html, "Projectcode SY002 niet gevonden in kaart-HTML"

    def test_index_page_contains_map_bounds(self):
        """De kaart moet automatisch ingezoomd zijn op de projectlocaties (fitBounds)."""
        resp = requests.get(f"{FLASK_BASE_URL}/", timeout=10, allow_redirects=True)
        html = resp.text
        assert "fitBounds" in html, \
            "Geen fitBounds gevonden — kaart zou automatisch moeten inzoomen op projectlocaties"

    def test_index_page_has_layer_control(self):
        """De kaart moet een LayerControl bevatten met project-lagen."""
        resp = requests.get(f"{FLASK_BASE_URL}/", timeout=10, allow_redirects=True)
        html = resp.text
        assert "Ingelezen Projecten" in html or "ingelezen" in html.lower(), \
            "Geen LayerControl met 'Ingelezen Projecten' gevonden"


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
