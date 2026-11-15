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
import io
import re
import subprocess
import time
import urllib.parse
import requests
from PIL import Image


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
# flask-test heeft hetzelfde volume schrijfbaar op zijn standaardpad (Kantelen, issue 34)
FLASK_CONTAINER = "wasstraat_flask_test"
FLASK_OUTPUT_MEDIA = "/output/archeomedia"
REDIS_CONTAINER = "wasstraat_redis_test"


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


def ingelogdeSessie():
    """Geef een requests.Session die als beheerder is ingelogd."""
    sessie = requests.Session()
    resp = logIn("admin", FLASK_ADMIN_PASSWORD, sessie)
    assert resp.status_code == 302 and "/login" not in resp.headers.get("Location", ""), "Inloggen mislukt"
    return sessie


def csrfToken(html):
    """Haal het CSRF-token uit een formulier van Flask-AppBuilder."""
    match = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert match, "Geen csrf_token in het formulier"
    return match.group(1)


def meldingen(html):
    """Geef de meldingen (flash) op een pagina als lijst van (soort, tekst), bijvoorbeeld ('success', '...')."""
    gevonden = re.findall(r'<div class="alert alert-(\w+)[^"]*"[^>]*>(.*?)</div>', html, re.S)
    return [(soort, " ".join(re.sub(r"<[^>]+>|&times;|×", " ", tekst).split())) for soort, tekst in gevonden]


def flaskPython(script):
    """Voer een Python-script uit in de Flask-testcontainer, met de code van de webapplicatie op het pad."""
    return subprocess.run(
        ["docker", "exec", "-i", "-w", "/app/app", FLASK_CONTAINER, "python", "-"],
        input=script, capture_output=True, text=True, timeout=120,
    )


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


@pytest.mark.flask_smoke
class TestProjectZonderLocatie:
    """Issue 27: een project zonder locatie aanmaken, en bij bewerken de locatie leegmaken.

    Via de formulieren van de webapplicatie, zoals een gebruiker dat doet (inloggen,
    CSRF-token uit het formulier). Flask-AppBuilder stuurt na opslaan ook bij een databasefout
    door (302), dus de tests kijken in PostgreSQL. De testprojecten worden achteraf verwijderd.
    """

    PREFIX = "ZS27"

    @pytest.fixture
    def sessie(self):
        return ingelogdeSessie()

    @pytest.fixture(autouse=True)
    def opruimen(self):
        yield
        pgTekst(f"DELETE FROM \"Def_Project\" WHERE projectcd LIKE '{self.PREFIX}%'")

    def aanmaken(self, sessie, projectcd, velden):
        """Vul het formulier voor een nieuw project in en geef de primary_key ('' als het niet is opgeslagen)."""
        resp = sessie.get(f"{BASE_URL}/archprojectview/add", timeout=30)
        assert resp.status_code == 200, f"Formulier nieuw project gaf {resp.status_code}"
        data = {"csrf_token": csrfToken(resp.text), "projectcd": projectcd,
                "projectnaam": f"Smoke test {projectcd}", "jaar": "2026", **velden}
        resp = sessie.post(f"{BASE_URL}/archprojectview/add", data=data, timeout=30, allow_redirects=False)
        assert resp.status_code == 302, f"Opslaan nieuw project gaf {resp.status_code}: {resp.text[:500]}"
        return pgTekst(f"SELECT primary_key FROM \"Def_Project\" WHERE projectcd = '{projectcd}'")

    def locatie(self, pk):
        return pgTekst(f"SELECT COALESCE(ST_AsText(location), 'LEEG') FROM \"Def_Project\" WHERE primary_key = {pk}")

    def geenFouten(self, sessie):
        """De meldingen na opslaan verschijnen op de volgende pagina; daar mag geen foutmelding tussen zitten."""
        resp = sessie.get(f"{BASE_URL}/archprojectview/list/", timeout=30)
        assert resp.status_code == 200, f"Lijst projecten gaf {resp.status_code}"
        fouten = [tekst for soort, tekst in meldingen(resp.text) if soort == "danger"]
        assert not fouten, fouten
        return resp

    def test_aanmaken_met_lege_locatie(self, sessie):
        pk = self.aanmaken(sessie, f"{self.PREFIX}1", {"location_lat": "", "location_lon": ""})
        assert pk, "Project zonder locatie is niet opgeslagen"
        assert self.locatie(pk) == "LEEG"
        assert f"{self.PREFIX}1" in self.geenFouten(sessie).text

    def test_aanmaken_zonder_locatievelden(self, sessie):
        """Ook zonder de velden location_lat en location_lon in het verzoek."""
        pk = self.aanmaken(sessie, f"{self.PREFIX}2", {})
        assert pk, "Project zonder locatievelden is niet opgeslagen"
        assert self.locatie(pk) == "LEEG"
        self.geenFouten(sessie)

    def test_detail_en_bewerkformulier_zonder_locatie(self, sessie):
        pk = self.aanmaken(sessie, f"{self.PREFIX}3", {"location_lat": "", "location_lon": ""})
        assert pk
        resp = sessie.get(f"{BASE_URL}/archprojectview/show/{pk}", timeout=30)
        assert resp.status_code == 200, f"Detail project gaf {resp.status_code}"
        # De kaart op de detailpagina krijgt geen coördinaten en zet dan geen marker
        assert 'createROPointMap("fieldname_map", null, null)' in resp.text
        resp = sessie.get(f"{BASE_URL}/archprojectview/edit/{pk}", timeout=30)
        assert resp.status_code == 200, f"Bewerkformulier project gaf {resp.status_code}"
        veld = re.search(r'<input[^>]*name="location_lat"[^>]*>', resp.text)
        assert veld and "value=" not in veld.group(0), veld.group(0) if veld else "geen veld location_lat"

    def test_locatie_leegmaken_bij_bewerken(self, sessie):
        pk = self.aanmaken(sessie, f"{self.PREFIX}4", {"location_lat": "52.0116", "location_lon": "4.3571"})
        assert pk and self.locatie(pk) == "POINT(4.3571 52.0116)"
        resp = sessie.get(f"{BASE_URL}/archprojectview/edit/{pk}", timeout=30)
        assert 'value="52.0116"' in resp.text, "Bewerkformulier toont de locatie niet"
        data = {"csrf_token": csrfToken(resp.text), "projectcd": f"{self.PREFIX}4",
                "projectnaam": "Smoke test locatie leeggemaakt", "jaar": "2026",
                "location_lat": "", "location_lon": ""}
        resp = sessie.post(f"{BASE_URL}/archprojectview/edit/{pk}", data=data, timeout=30, allow_redirects=False)
        assert resp.status_code == 302, f"Opslaan bewerkt project gaf {resp.status_code}: {resp.text[:500]}"
        assert self.locatie(pk) == "LEEG"
        assert pgTekst(f'SELECT projectnaam FROM "Def_Project" WHERE primary_key = {pk}') == \
            "Smoke test locatie leeggemaakt"
        self.geenFouten(sessie)

    def test_kaart_met_project_zonder_locatie(self, sessie):
        """De startpagina (kaart) slaat projecten zonder locatie over; de cache wordt eerst geleegd."""
        assert self.aanmaken(sessie, f"{self.PREFIX}5", {"location_lat": "", "location_lon": ""})
        leeg = subprocess.run(["docker", "exec", REDIS_CONTAINER, "redis-cli", "FLUSHALL"],
                              capture_output=True, text=True, timeout=30)
        assert leeg.returncode == 0, leeg.stderr
        resp = requests.get(f"{BASE_URL}/", timeout=30)
        assert resp.status_code == 200, f"Startpagina gaf {resp.status_code}"
        assert "SY001" in resp.text and "SY002" in resp.text
        assert f"{self.PREFIX}5" not in resp.text


@pytest.mark.flask_smoke
class TestFotoKantelen:
    """Issue 34: de acties Kantelen Linksom en Kantelen Rechtsom op foto's en pdf's.

    Maakt in de Flask-container een liggende foto en een liggende pdf (rood blok linksboven)
    met hun voorbeelden, zoals de extractie dat doet, en registreert ze met SQL in Def_Bestand.
    De afmetingen en de inhoud van de drie formaten worden gemeten via Apache, zoals de
    browser ze ophaalt. Alles wordt achteraf opgeruimd.
    """

    MAP = "/Smoke kantelen"
    FOTO = "/Smoke kantelen/kantelfoto.jpg"
    PDF = "/Smoke kantelen/kantelrapport.pdf"

    @pytest.fixture
    def sessie(self):
        return ingelogdeSessie()

    @pytest.fixture
    def bestanden(self):
        """Foto, pdf en Word-document in Def_Bestand; de foto en de pdf ook in de mediamap."""
        controle = subprocess.run(["docker", "exec", FLASK_CONTAINER, "test", "-w", FLASK_OUTPUT_MEDIA],
                                  capture_output=True, text=True, timeout=30)
        if controle.returncode != 0:
            pytest.skip(f"{FLASK_CONTAINER} heeft geen schrijfbaar mediavolume op {FLASK_OUTPUT_MEDIA}")
        script = f"""
import os
from PIL import Image
import pdf2image
import shared.image_util as image_util
map_ = '{FLASK_OUTPUT_MEDIA}{self.MAP}'
os.makedirs(map_, exist_ok=True)
foto = Image.new('RGB', (400, 200), 'white')
foto.paste((255, 0, 0), (0, 0, 100, 50))
print(image_util.putImageInGrid(foto, map_ + '/kantelfoto.tif', None, '{self.MAP}', ''))
pagina = Image.new('RGB', (842, 595), 'white')
pagina.paste((255, 0, 0), (0, 0, 200, 100))
pagina.save(map_ + '/kantelrapport.pdf')
eerste = pdf2image.convert_from_path(map_ + '/kantelrapport.pdf')[0]
print(image_util.putImageInGrid(eerste, map_ + '/kantelrapport.pdf', None, '{self.MAP}', '', filetype='.pdf'))
"""
        gemaakt = flaskPython(script)
        assert gemaakt.returncode == 0, gemaakt.stderr[-2000:]

        def rij(soort, naam, type_, mime, groot):
            basis = f"{self.MAP}/{naam.rsplit('.', 1)[0]}"
            return pgTekst(
                'INSERT INTO "Def_Bestand" (bestandsoort, "fileName", "fileType", directory, "imageID", '
                f'"imageMiddleID", "imageThumbID", mime_type, "projectID") VALUES (\'{soort}\', \'{naam}\', '
                f"'{type_}', '{self.MAP}', '{groot}', '{basis}-med.jpg', '{basis}-sml.jpg', '{mime}', "
                '(SELECT MIN(primary_key) FROM "Def_Project")) RETURNING primary_key').splitlines()[0]

        try:
            yield {
                "foto": rij("Opgravingsfoto", "kantelfoto.tif", ".tif", "image/jpeg", self.FOTO),
                "pdf": rij("Archeologische_Rapportage", "kantelrapport.pdf", ".pdf", "application/pdf", self.PDF),
                "word": rij("Overige_Rapportage", "kantelnotitie.docx", ".docx", "application/msword",
                            f"{self.MAP}/kantelnotitie.docx"),
            }
        finally:
            pgTekst(f"DELETE FROM \"Def_Bestand\" WHERE directory = '{self.MAP}'")
            subprocess.run(["docker", "exec", FLASK_CONTAINER, "rm", "-rf", f"{FLASK_OUTPUT_MEDIA}{self.MAP}"],
                           capture_output=True, text=True, timeout=30)

    def afbeelding(self, pad):
        """Haal een afbeelding via Apache op; geef de afbeelding en het antwoord."""
        resp = requests.get(mediaUrl(pad), timeout=30)
        assert resp.status_code == 200, f"{mediaUrl(pad)} gaf {resp.status_code}"
        return Image.open(io.BytesIO(resp.content)).convert("RGB"), resp

    def inhoud(self, pad):
        """Omhullende van alles wat niet wit is; briefkaart en thumbnail hebben een witte rand."""
        image, _ = self.afbeelding(pad)
        return image.convert("L").point(lambda waarde: 255 if waarde < 245 else 0).getbbox()

    def staand(self, pad):
        links, boven, rechts, onder = self.inhoud(pad)
        return (onder - boven) > (rechts - links)

    def isRood(self, image, punt):
        rood, groen, blauw = image.getpixel(punt)
        return rood > 200 and groen < 80 and blauw < 80

    def voorbeelden(self, pad):
        basis = pad.rsplit(".", 1)[0]
        return f"{basis}-med.jpg", f"{basis}-sml.jpg"

    def actieOpDetailpagina(self, sessie, pk, actie):
        """Voer een actie uit zoals de knop op de detailpagina dat doet; geef de pagina na de redirect."""
        resp = sessie.get(f"{BASE_URL}/archbestandview/show/{pk}", timeout=30)
        assert resp.status_code == 200, f"Detail bestand {pk} gaf {resp.status_code}"
        url = re.search(rf'action="([^"]*/action/{actie}/{pk})"', resp.text)
        assert url, f"Geen knop voor {actie} op de detailpagina van bestand {pk}"
        resp = sessie.post(f"{BASE_URL}{url.group(1)}", data={"action": ""}, timeout=60, allow_redirects=False)
        assert resp.status_code == 302, f"Actie {actie} gaf {resp.status_code}: {resp.text[:500]}"
        assert resp.headers["Location"].endswith(f"/show/{pk}"), \
            f"Na de actie terug naar de detailpagina verwacht, kreeg {resp.headers['Location']}"
        return sessie.get(urllib.parse.urljoin(BASE_URL, resp.headers["Location"]), timeout=30)

    def test_detailpagina_toont_kantelknoppen(self, sessie, bestanden):
        resp = sessie.get(f"{BASE_URL}/archbestandview/show/{bestanden['foto']}", timeout=30)
        assert resp.status_code == 200
        assert "Kantelen Linksom" in resp.text and "Kantelen Rechtsom" in resp.text

    def test_linksom_op_detailpagina(self, sessie, bestanden):
        middel, thumb = self.voorbeelden(self.FOTO)
        groot, antwoordVoor = self.afbeelding(self.FOTO)
        assert groot.size == (400, 200)
        assert not self.staand(middel) and not self.staand(thumb)

        pagina = self.actieOpDetailpagina(sessie, bestanden["foto"], "5linkskantelen")
        assert pagina.status_code == 200
        assert ("success", "1 bestand linksom gekanteld") in meldingen(pagina.text), meldingen(pagina.text)

        groot, antwoordNa = self.afbeelding(self.FOTO)
        assert groot.size == (200, 400)
        # Linksom: het rode blok linksboven staat nu linksonder
        assert self.isRood(groot, (10, 390)) and not self.isRood(groot, (10, 10))
        assert self.afbeelding(middel)[0].size == (1500, 1000) and self.staand(middel)
        assert self.afbeelding(thumb)[0].size == (300, 200) and self.staand(thumb)
        # De browser haalt de nieuwe versie op: Apache laat afbeeldingen direct verlopen en de ETag verandert
        assert antwoordNa.headers.get("Expires", "").endswith("2000 00:00:00 GMT")
        assert antwoordNa.headers.get("ETag") != antwoordVoor.headers.get("ETag")

    def test_rechtsom_selectie_in_lijst(self, sessie, bestanden):
        sessie.get(f"{BASE_URL}/archopgravingfotoview/list/", timeout=30)
        resp = sessie.post(f"{BASE_URL}/archopgravingfotoview/action_post",
                           data={"action": "6rechtskantelen", "rowid": [bestanden["foto"]]},
                           timeout=60, allow_redirects=False)
        assert resp.status_code == 302, f"Actie op de selectie gaf {resp.status_code}: {resp.text[:500]}"
        assert "/archopgravingfotoview/list/" in resp.headers["Location"], resp.headers["Location"]
        pagina = sessie.get(urllib.parse.urljoin(BASE_URL, resp.headers["Location"]), timeout=30)
        assert ("success", "1 bestand rechtsom gekanteld") in meldingen(pagina.text), meldingen(pagina.text)

        groot, _ = self.afbeelding(self.FOTO)
        assert groot.size == (200, 400)
        # Rechtsom: het rode blok linksboven staat nu rechtsboven
        assert self.isRood(groot, (190, 10)) and not self.isRood(groot, (10, 390))
        middel, thumb = self.voorbeelden(self.FOTO)
        assert self.staand(middel) and self.staand(thumb)

    def test_pdf_linksom(self, sessie, bestanden):
        middel, thumb = self.voorbeelden(self.PDF)
        assert not self.staand(middel) and not self.staand(thumb)
        assert not re.search(rb"/Rotate\s+[1-9]", requests.get(mediaUrl(self.PDF), timeout=30).content)

        pagina = self.actieOpDetailpagina(sessie, bestanden["pdf"], "5linkskantelen")
        assert ("success", "1 bestand linksom gekanteld") in meldingen(pagina.text), meldingen(pagina.text)

        # PyPDF2 draait met de klok mee: linksom is /Rotate 270
        pdf = requests.get(mediaUrl(self.PDF), timeout=30)
        assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")
        assert re.findall(rb"/Rotate\s+(\d+)", pdf.content) == [b"270"]
        assert self.staand(middel) and self.staand(thumb)

    def test_word_document_geeft_melding(self, sessie, bestanden):
        pagina = self.actieOpDetailpagina(sessie, bestanden["word"], "6rechtskantelen")
        assert pagina.status_code == 200
        assert ("danger", "Niet gekanteld: kantelnotitie.docx: een Word-document kan niet gekanteld worden") \
            in meldingen(pagina.text), meldingen(pagina.text)
