"""
Flask smoke tests via Apache — verifieert dat de webapplicatie achter Apache opstart,
de kaart zichtbaar is en de media door Apache geserveerd worden.

Apache is de voordeur, net als in de echte installatie: hostpoort 5061 is apache-test
(docker-compose.test.yml). Apache serveert /archeomedia uit het gedeelde mediavolume en
stuurt al het overige door naar flask-test, dat geen hostpoort heeft.

Draait tegen echte Docker services (PostgreSQL + Redis + Flask + Apache).
Gebruik: make test-flask (zonder data), of make integration voor de volledige suite
"""
import pytest
import re
import subprocess
import time
import urllib.parse
import requests


# De voordeur: apache-test. Alles behalve /archeomedia komt bij flask-test terecht.
BASE_URL = "http://localhost:5061"
MAX_WAIT_SECONDS = 120
POLL_INTERVAL = 3
# Moet overeenkomen met FLASK_ADMIN_PASSWORD van flask-test in docker-compose.test.yml
FLASK_ADMIN_PASSWORD = "test-beheerder-wachtwoord"
POSTGRES_CONTAINER = "wasstraat_postgres_test"
# airflow-test schrijft de media in AIRFLOW_OUTPUT_MEDIA; apache-test serveert dezelfde map
AIRFLOW_CONTAINER = "wasstraat_airflow_test"
AIRFLOW_OUTPUT_MEDIA = "/tmp/archeomedia_test"


def logIn(gebruikersnaam, wachtwoord, sessie=None):
    """
    Log in via het loginformulier van Flask-AppBuilder.

    Args:
        gebruikersnaam: Gebruikersnaam voor het formulier.
        wachtwoord: Wachtwoord voor het formulier.
        sessie: Optionele requests.Session die na het inloggen ingelogd is; anders een nieuwe.

    Returns:
        requests.Response: Antwoord op de POST, zonder redirects te volgen.
    """
    sessie = sessie if sessie is not None else requests.Session()
    resp = sessie.get(f"{BASE_URL}/login/", timeout=10)
    match = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', resp.text)
    assert match, "Geen csrf_token gevonden op login-pagina"
    return sessie.post(
        f"{BASE_URL}/login/",
        data={"username": gebruikersnaam, "password": wachtwoord, "csrf_token": match.group(1)},
        timeout=10,
        allow_redirects=False,
    )


def pgTekst(sql):
    """Voer een query uit op de test-PostgreSQL en geef de eerste waarde als tekst ('' bij NULL)."""
    cmd = [
        "docker", "exec", "-e", "PGPASSWORD=testpass", POSTGRES_CONTAINER,
        "psql", "-U", "testuser", "-h", "localhost", "-d", "airflow_test",
        "-t", "-A", "-c", sql,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
    if result.returncode != 0:
        raise RuntimeError(f"psql fout: {result.stderr.strip()}")
    return result.stdout.strip()


def airflowShell(script):
    """Voer een shellscript uit in de Airflow-testcontainer (de schrijver van het mediavolume)."""
    return subprocess.run(
        ["docker", "exec", AIRFLOW_CONTAINER, "sh", "-c", script],
        capture_output=True, text=True, timeout=30,
    )


def mediaUrl(pad):
    """Bouw de URL van een mediabestand zoals de webapplicatie dat doet: /archeomedia + imageID."""
    return f"{BASE_URL}/archeomedia{urllib.parse.quote(pad)}"


@pytest.fixture(scope="module", autouse=True)
def wait_for_flask():
    """Wacht tot Flask via Apache beschikbaar is voordat tests starten (503 = Flask start nog)."""
    print(f"\n  Wachten op Flask via Apache ({BASE_URL})...")
    deadline = time.time() + MAX_WAIT_SECONDS
    last_error = None
    while time.time() < deadline:
        try:
            resp = requests.get(f"{BASE_URL}/login/", timeout=5)
            if resp.status_code < 500:
                print(f"  Flask is klaar (status {resp.status_code})")
                return
            last_error = f"status {resp.status_code}"
        except requests.ConnectionError as e:
            last_error = e
        time.sleep(POLL_INTERVAL)
    pytest.fail(f"Flask niet bereikbaar via Apache na {MAX_WAIT_SECONDS}s: {last_error}")


@pytest.mark.flask_smoke
class TestFlaskStartup:
    """Verifieer dat Flask zonder fouten opstart."""

    def test_index_page_returns_200(self):
        """De indexpagina moet HTTP 200 retourneren."""
        resp = requests.get(f"{BASE_URL}/", timeout=10, allow_redirects=True)
        assert resp.status_code == 200, f"Verwacht 200, kreeg {resp.status_code}"

    def test_index_page_contains_folium_map(self):
        """De indexpagina moet een Folium/Leaflet kaart bevatten."""
        resp = requests.get(f"{BASE_URL}/", timeout=10, allow_redirects=True)
        html = resp.text.lower()
        assert "leaflet" in html or "l.map" in html or "folium" in html, \
            "Geen Leaflet/Folium kaart gevonden in de indexpagina"

    def test_login_page_accessible(self):
        """De login-pagina moet bereikbaar zijn (FAB security werkt)."""
        resp = requests.get(f"{BASE_URL}/login/", timeout=10)
        assert resp.status_code == 200

    def test_login_page_contains_form(self):
        """De login-pagina moet een inlogformulier bevatten."""
        resp = requests.get(f"{BASE_URL}/login/", timeout=10)
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
class TestApacheVoordeur:
    """Apache is de voordeur: Flask erachter, media uit de uitvoermap, redirects naar de buitenkant."""

    def test_homepage_via_apache(self):
        """De homepage komt via Apache van Flask (geen 'It works!' van de httpd-image)."""
        resp = requests.get(f"{BASE_URL}/", timeout=10, allow_redirects=True)
        assert resp.status_code == 200, f"Verwacht 200, kreeg {resp.status_code}"
        assert "It works!" not in resp.text, "Apache serveert zijn eigen index.html in plaats van Flask"
        assert "login" in resp.text.lower(), "Geen Flask-pagina via Apache"

    def test_login_redirect_volgt_host_van_de_browser(self):
        """De redirect van /login naar /login/ noemt de buitenkant (Host van de browser), niet flask:5051.

        Flask ziet door ProxyPreserveHost en ProxyFix de Host-header van de browser, ook een
        andere naam dan localhost.
        """
        resp = requests.get(f"{BASE_URL}/login", timeout=10, allow_redirects=False,
                            headers={"Host": "wasstraat.example:5061"})
        assert resp.status_code in (301, 302, 307, 308), f"Verwacht redirect, kreeg {resp.status_code}"
        locatie = resp.headers.get("Location", "")
        assert "flask:5051" not in locatie and "localhost:5051" not in locatie, locatie
        assert locatie in ("/login/", "http://wasstraat.example:5061/login/"), locatie

    def test_login_post_redirect_wijst_naar_buitenkant(self):
        """Na inloggen stuurt Flask door naar een adres op de buitenkant (relatief of via Apache)."""
        resp = logIn("admin", FLASK_ADMIN_PASSWORD)
        assert resp.status_code == 302, f"Verwacht redirect, kreeg {resp.status_code}"
        locatie = resp.headers.get("Location", "")
        assert locatie.startswith("/") or locatie.startswith(BASE_URL), locatie
        assert "flask:5051" not in locatie and ":5051" not in locatie, locatie

    def test_protocol_van_tls_proxy_wordt_doorgegeven(self):
        """Staat er een TLS-proxy vóór Apache, dan volgt Flask het protocol uit X-Forwarded-Proto.

        Apache zet de header alleen als die leeg is (setifempty); ProxyFix neemt hem over.
        """
        resp = requests.get(f"{BASE_URL}/login", timeout=10, allow_redirects=False,
                            headers={"X-Forwarded-Proto": "https"})
        assert resp.status_code in (301, 302, 307, 308), f"Verwacht redirect, kreeg {resp.status_code}"
        locatie = resp.headers.get("Location", "")
        assert locatie == "/login/" or locatie.startswith("https://localhost:5061/"), locatie

    def test_archeomedia_map_zonder_bestand_geeft_apache_404(self):
        """Een onbekend mediabestand geeft een 404 van Apache zelf, niet van Flask."""
        resp = requests.get(f"{BASE_URL}/archeomedia/bestaat-niet/foto.jpg", timeout=10)
        assert resp.status_code == 404
        assert "Apache" in resp.headers.get("Server", ""), resp.headers.get("Server")

    def test_archeomedia_geen_directory_listing(self):
        """De uitvoermap is niet te bladeren (geen Indexes)."""
        resp = requests.get(f"{BASE_URL}/archeomedia/", timeout=10)
        assert resp.status_code == 403, f"Verwacht 403, kreeg {resp.status_code}"

    def test_media_uit_def_bestand_via_apache(self):
        """Een media-URL uit Def_Bestand (zoals de webapplicatie die opbouwt) geeft via Apache 200."""
        pad = pgTekst('SELECT "imageMiddleID" FROM "Def_Bestand" WHERE "imageMiddleID" IS NOT NULL '
                      'ORDER BY "fileName" LIMIT 1')
        if not pad:
            pytest.skip("Def_Bestand bevat geen media: pipeline niet gedraaid (make integration)")
        print(f"\n  Media-URL uit Def_Bestand: {mediaUrl(pad)}")
        resp = requests.get(mediaUrl(pad), timeout=10)
        assert resp.status_code == 200, f"{mediaUrl(pad)} gaf {resp.status_code}"
        assert resp.headers.get("Content-Type", "").startswith("image/"), resp.headers.get("Content-Type")
        assert len(resp.content) > 0

    def test_alle_media_uit_def_bestand_bereikbaar(self):
        """Alle drie formaten van alle foto's in Def_Bestand zijn via Apache bereikbaar."""
        rijen = pgTekst('SELECT "imageID" || \'|\' || "imageMiddleID" || \'|\' || "imageThumbID" '
                        'FROM "Def_Bestand" WHERE "imageID" IS NOT NULL ORDER BY "fileName"')
        if not rijen:
            pytest.skip("Def_Bestand bevat geen media: pipeline niet gedraaid (make integration)")
        paden = [pad for rij in rijen.splitlines() for pad in rij.split("|")]
        fouten = [pad for pad in paden if requests.get(mediaUrl(pad), timeout=10).status_code != 200]
        print(f"\n  Mediabestanden via Apache gecontroleerd: {len(paden)}, onbereikbaar: {len(fouten)}")
        assert not fouten, f"Niet bereikbaar via Apache: {fouten[:5]}"

    def test_media_pad_met_spaties_en_diakritische_tekens(self):
        """Paden met spaties en diakritische tekens (zoals 'L Fotos') werken via Apache."""
        controle = airflowShell(f"test -d {AIRFLOW_OUTPUT_MEDIA}")
        if controle.returncode != 0:
            pytest.skip("Airflow-testcontainer of mediavolume niet beschikbaar (make integration)")
        pad = "/Smoke test/Fotó ünïek ß.jpg"
        inhoud = "JPEG-inhoud voor de smoke test"
        aangemaakt = airflowShell(
            f"mkdir -p '{AIRFLOW_OUTPUT_MEDIA}/Smoke test' && printf '%s' '{inhoud}' > '{AIRFLOW_OUTPUT_MEDIA}{pad}'"
        )
        assert aangemaakt.returncode == 0, aangemaakt.stderr
        try:
            resp = requests.get(mediaUrl(pad), timeout=10)
            assert resp.status_code == 200, f"{mediaUrl(pad)} gaf {resp.status_code}"
            assert resp.content.decode("utf-8") == inhoud
            assert resp.headers.get("Content-Type", "").startswith("image/jpeg")
        finally:
            airflowShell(f"rm -rf '{AIRFLOW_OUTPUT_MEDIA}/Smoke test'")


@pytest.mark.flask_smoke
class TestVerdwenenUitBrondata:
    """Issue 73: bruikleen en conservering van een artefact dat uit de brondata verdween, zijn te bekijken.

    De laadstap maakt de verwijzing leeg en vult een markering; hier wordt zo'n rij met SQL aangemaakt
    (ook zonder geladen data) en opgevraagd als beheerder.
    """

    KEY = "PSMOKE1P1V1A1|Glas"

    @pytest.fixture
    def sessie(self):
        sessie = requests.Session()
        resp = logIn("admin", FLASK_ADMIN_PASSWORD, sessie)
        assert resp.status_code == 302 and "/login" not in resp.headers.get("Location", ""), "Inloggen mislukt"
        return sessie

    @pytest.fixture
    def losgekoppeld(self):
        """Partij, bruikleen en conserveringsproject met een losgekoppeld artefact; achteraf opgeruimd."""
        def eerste(sql):
            return pgTekst(sql).splitlines()[0]

        partij = eerste("INSERT INTO \"Def_Partij\" (naam) VALUES ('Smoke test verdwenen artefact') "
                        "RETURNING primary_key")
        try:
            bruikleen = eerste(
                'INSERT INTO "Def_Bruikleen" (datum_uitgeleend, "projectID", "artefactID", "partijID", '
                'artefact_verdwenen_key, artefact_verdwenen_op) VALUES (DATE \'2026-10-01\', '
                f'(SELECT MIN(primary_key) FROM "Def_Project"), NULL, {partij}, \'{self.KEY}\', '
                "TIMESTAMP '2026-10-22 03:00') RETURNING primary_key")
            conservering = eerste(
                'INSERT INTO "Def_Conserveringsproject" (korte_omschrijving, begindatum, "uitvoerderID") '
                f"VALUES ('Smoke test conservering', DATE '2026-09-01', {partij}) RETURNING primary_key")
            pgTekst('INSERT INTO "Def_artefact_conservering" (conservering_id, artefact_id, artefact_verdwenen_key, '
                    f"artefact_verdwenen_op) VALUES ({conservering}, NULL, '{self.KEY}', TIMESTAMP '2026-10-22 03:00')")
            yield {"bruikleen": bruikleen, "conservering": conservering}
        finally:
            pgTekst(f'DELETE FROM "Def_artefact_conservering" WHERE conservering_id IN '
                    f'(SELECT primary_key FROM "Def_Conserveringsproject" WHERE "uitvoerderID" = {partij})')
            pgTekst(f'DELETE FROM "Def_Conserveringsproject" WHERE "uitvoerderID" = {partij}')
            pgTekst(f'DELETE FROM "Def_Bruikleen" WHERE "partijID" = {partij}')
            pgTekst(f'DELETE FROM "Def_Partij" WHERE primary_key = {partij}')

    def test_bruiklenen_lijst_met_losgekoppelde_bruikleen(self, sessie, losgekoppeld):
        resp = sessie.get(f"{BASE_URL}/archbruikleenview/list/", timeout=30)
        assert resp.status_code == 200, f"Lijst bruiklenen gaf {resp.status_code}"
        assert f"Artefact {self.KEY} verdwenen op 22-10-2026" in resp.text

    def test_bruikleen_detail_met_markering(self, sessie, losgekoppeld):
        resp = sessie.get(f"{BASE_URL}/archbruikleenview/show/{losgekoppeld['bruikleen']}", timeout=30)
        assert resp.status_code == 200, f"Detail bruikleen gaf {resp.status_code}"
        assert self.KEY in resp.text and "Verdwenen artefact (key)" in resp.text

    def test_conserveringsproject_toont_verdwenen_artefact(self, sessie, losgekoppeld):
        resp = sessie.get(f"{BASE_URL}/conserveringsprojectview/show/{losgekoppeld['conservering']}", timeout=30)
        assert resp.status_code == 200, f"Detail conserveringsproject gaf {resp.status_code}"
        assert f"Artefact {self.KEY} verdwenen op 22-10-2026" in resp.text


@pytest.mark.flask_smoke
class TestFlaskKaartProjecten:
    """Verifieer dat projecten zichtbaar zijn op de kaart."""

    def test_index_page_contains_project_markers(self):
        """De kaart moet minimaal 2 projectmarkers bevatten (SY001 + SY002)."""
        resp = requests.get(f"{BASE_URL}/", timeout=10, allow_redirects=True)
        html = resp.text

        # Folium genereert L.circleMarker() calls in de HTML
        marker_count = html.lower().count("l.circlemarker")
        assert marker_count >= 2, (
            f"Verwacht minimaal 2 CircleMarkers op de kaart, gevonden {marker_count}. "
            f"Controleer of Def_Project gevuld is in PostgreSQL."
        )

    def test_index_page_contains_project_codes(self):
        """De projectcodes SY001 en SY002 moeten in de kaart-popups staan."""
        resp = requests.get(f"{BASE_URL}/", timeout=10, allow_redirects=True)
        html = resp.text
        assert "SY001" in html, "Projectcode SY001 niet gevonden in kaart-HTML"
        assert "SY002" in html, "Projectcode SY002 niet gevonden in kaart-HTML"

    def test_index_page_contains_map_bounds(self):
        """De kaart moet automatisch ingezoomd zijn op de projectlocaties (fitBounds)."""
        resp = requests.get(f"{BASE_URL}/", timeout=10, allow_redirects=True)
        html = resp.text
        assert "fitBounds" in html, \
            "Geen fitBounds gevonden — kaart zou automatisch moeten inzoomen op projectlocaties"

    def test_index_page_has_layer_control(self):
        """De kaart moet een LayerControl bevatten met project-lagen."""
        resp = requests.get(f"{BASE_URL}/", timeout=10, allow_redirects=True)
        html = resp.text
        assert "Ingelezen Projecten" in html or "ingelezen" in html.lower(), \
            "Geen LayerControl met 'Ingelezen Projecten' gevonden"


@pytest.mark.flask_smoke
class TestFlaskStaticAssets:
    """Verifieer dat statische bestanden van Flask via Apache geserveerd worden."""

    def test_static_css_served(self):
        """Custom CSS moet beschikbaar zijn."""
        resp = requests.get(f"{BASE_URL}/static/css/arch.css", timeout=10)
        assert resp.status_code == 200, "arch.css niet gevonden"

    def test_static_js_served(self):
        """Custom JavaScript moet beschikbaar zijn."""
        resp = requests.get(f"{BASE_URL}/static/js/main.js", timeout=10)
        # 200 of 304 (cached) zijn beide acceptabel
        assert resp.status_code in (200, 304), f"main.js niet gevonden: {resp.status_code}"
