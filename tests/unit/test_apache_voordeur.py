"""
Unit tests voor Apache als voordeur van de Wasstraat.

Apache serveert /archeomedia zelf uit de uitvoermap en stuurt alle overige verzoeken door
naar Flask (reverse proxy). Flask heeft geen hostpoort; Apache is de enige ingang. Deze
tests bewaken de Apache-configuratie, de compose-bestanden (ontwikkel-, deploy- en
testomgeving), de Makefile en ProxyFix in de Flask-app.
"""
import os
import re

import pytest
import yaml


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
HTTPD_CONF = os.path.join(PROJECT_ROOT, "services", "apache", "httpd.conf")

# (compose-bestand, naam flask-service, naam apache-service)
COMPOSE_MET_VOORDEUR = [
    ("docker-compose.yml", "flask", "apache"),
    ("docker-compose.delft.yml", "flask", "apache"),
    ("deploy/docker-compose.yml", "flask", "apache"),
    ("docker-compose.test.yml", "flask-test", "apache-test"),
    ("docker-compose.delft-test.yml", "flask-test", "apache-test"),
]


def leesBestand(pad):
    with open(os.path.join(PROJECT_ROOT, pad), encoding="utf-8") as f:
        return f.read()


def leesCompose(pad):
    """Lees een compose-bestand als dict (zonder variabelen te vervangen)."""
    return yaml.safe_load(leesBestand(pad))


def dependsOn(service):
    """Namen in depends_on, zowel de lijst- als de dict-vorm."""
    waarde = service.get("depends_on", [])
    return list(waarde.keys()) if isinstance(waarde, dict) else list(waarde)


def hostPoorten(service):
    """De gepubliceerde hostpoorten (tekstvorm 'host:container' of 'bind:host:container')."""
    return [str(p) for p in service.get("ports", [])]


@pytest.mark.unit
class TestHttpdConf:
    """services/apache/httpd.conf: modules, reverse proxy en media uit de uitvoermap."""

    @pytest.fixture(autouse=True)
    def conf(self):
        self.conf = leesBestand("services/apache/httpd.conf")
        # Alleen de werkzame regels (zonder commentaar)
        self.regels = [r.strip() for r in self.conf.splitlines() if r.strip() and not r.strip().startswith("#")]

    def test_proxy_modules_geladen(self):
        for module in ("proxy_module", "proxy_http_module", "headers_module"):
            assert any(r.startswith(f"LoadModule {module} ") for r in self.regels), f"{module} niet geladen"

    def test_luistert_op_5052(self):
        assert "Listen 5052" in self.regels

    def test_geen_open_proxy_en_host_doorgegeven(self):
        assert "ProxyRequests Off" in self.regels
        assert "ProxyPreserveHost On" in self.regels

    def test_archeomedia_uitgezonderd_voor_de_algemene_regel(self):
        proxypass = [r for r in self.regels if r.startswith("ProxyPass ")]
        assert proxypass[0] == 'ProxyPass "/archeomedia/" "!"', proxypass
        assert proxypass[1].startswith('ProxyPass "/" "http://flask:5051/"'), proxypass
        assert 'ProxyPassReverse "/" "http://flask:5051/"' in self.regels

    def test_flask_direct_opnieuw_proberen_na_opstarten(self):
        """retry=0: geen minuut lang 503 nadat Flask (later dan Apache) is opgestart."""
        assert any(r.startswith('ProxyPass "/" ') and "retry=0" in r for r in self.regels)

    def test_protocol_van_tls_proxy_doorgegeven(self):
        assert any(r.startswith("RequestHeader setifempty X-Forwarded-Proto") for r in self.regels)

    def test_uitvoermap_is_documentroot_zonder_directory_listing(self):
        assert 'DocumentRoot "/usr/local/apache2/htdocs"' in self.regels
        blok = re.search(r'<Directory "/usr/local/apache2/htdocs">(.*?)</Directory>', self.conf, re.S).group(1)
        assert "Require all granted" in blok
        assert not re.search(r"^\s*Options.*Indexes", blok, re.M), "geen directory listing van de media"

    def test_dockerfile_kopieert_de_configuratie(self):
        dockerfile = leesBestand("services/apache/Dockerfile")
        assert "httpd:2.4" in dockerfile
        assert re.search(r"^COPY \./services/apache/httpd\.conf /usr/local/apache2/conf/httpd\.conf$", dockerfile, re.M)


@pytest.mark.unit
class TestComposeVoordeur:
    """In alle omgevingen heeft alleen Apache een hostpoort en staat Flask erachter."""

    @pytest.mark.parametrize("pad,flask,apache", COMPOSE_MET_VOORDEUR)
    def test_flask_zonder_hostpoort_apache_met(self, pad, flask, apache):
        services = leesCompose(pad)["services"]
        assert "ports" not in services[flask], f"{pad}: {flask} hoort geen hostpoort te hebben"
        poorten = hostPoorten(services[apache])
        assert poorten and all(p.endswith(":5052") for p in poorten), f"{pad}: {poorten}"

    @pytest.mark.parametrize("pad,flask,apache", COMPOSE_MET_VOORDEUR)
    def test_apache_wacht_op_flask(self, pad, flask, apache):
        services = leesCompose(pad)["services"]
        assert flask in dependsOn(services[apache]), f"{pad}: {apache} hoort op {flask} te wachten"
        assert apache not in dependsOn(services[flask]), f"{pad}: {flask} hoort niet op {apache} te wachten"

    @pytest.mark.parametrize("pad", ["docker-compose.yml", "docker-compose.delft.yml", "deploy/docker-compose.yml"])
    def test_apache_serveert_de_uitvoermap_alleen_lezen(self, pad):
        volumes = leesCompose(pad)["services"]["apache"]["volumes"]
        # De bron kan '${WASSTRAAT_OUTPUT:-./data/output}' zijn, dus van rechts splitsen
        media = [v for v in volumes if v.rsplit(":", 2)[1] == "/usr/local/apache2/htdocs"]
        assert len(media) == 1, volumes
        bron, _, opties = media[0].rsplit(":", 2)
        assert opties == "ro", media[0]
        assert "output" in bron, media[0]

    def test_ontwikkelomgeving_geeft_flask_een_debugpoort(self):
        flask = leesCompose("docker-compose.develop.yml")["services"]["flask"]
        assert "5051:5051" in hostPoorten(flask)

    def test_deploy_env_example_zonder_flask_poort(self):
        env = leesBestand("deploy/.env.example")
        assert re.search(r"^WASSTRAAT_PORT_APACHE=5052$", env, re.M)
        assert not re.search(r"^WASSTRAAT_PORT_FLASK=", env, re.M), "Flask heeft geen hostpoort meer"
        compose = leesBestand("deploy/docker-compose.yml")
        assert "WASSTRAAT_PORT_FLASK" not in compose

    def test_deploy_inloggegevens_wijzen_naar_apache(self):
        makefile = leesBestand("deploy/Makefile")
        assert "WASSTRAAT_PORT_FLASK" not in makefile
        assert re.search(r'Flask App\s+http://localhost:\$\$\{WASSTRAAT_PORT_APACHE:-5052\}', makefile)


@pytest.mark.unit
class TestTestomgeving:
    """apache-test deelt het mediavolume met airflow-test en is de voordeur van de smoke tests."""

    @pytest.mark.parametrize("pad,volume,poort,mediapad", [
        ("docker-compose.test.yml", "archeomedia-test", "5061:5052", "/tmp/archeomedia_test"),
        ("docker-compose.delft-test.yml", "archeomedia-delft-test", "5062:5052", "/output/archeomedia"),
    ])
    def test_mediavolume_gedeeld_met_apache(self, pad, volume, poort, mediapad):
        services = leesCompose(pad)["services"]
        assert f"{volume}:{mediapad}" in services["airflow-test"]["volumes"]
        assert services["airflow-test"]["environment"]["AIRFLOW_OUTPUT_MEDIA"] == mediapad
        assert f"{volume}:/usr/local/apache2/htdocs/archeomedia:ro" in services["apache-test"]["volumes"]
        assert poort in hostPoorten(services["apache-test"])

    def test_synthetisch_mediavolume_tmpfs_schrijfbaar_voor_airflow(self):
        """De airflow-gebruiker (uid 50000) moet in het tmpfs-volume kunnen schrijven."""
        opties = leesCompose("docker-compose.test.yml")["volumes"]["archeomedia-test"]["driver_opts"]
        assert opties["type"] == "tmpfs"
        assert "uid=50000" in opties["o"]

    def test_delfts_mediavolume_op_schijf_in_map_van_de_image(self):
        """De Delftse testdata (circa 5 GB rapporten) past niet in tmpfs.

        Een vol tmpfs liet op 2026-10-21 93 van de 541 bestanden stil onverwerkt. Het volume
        staat daarom op schijf en wordt gemount op /output/archeomedia, de map die de
        Airflow-image aanmaakt met airflow als eigenaar: een leeg named volume neemt die
        rechten over, zodat airflow-test erin kan schrijven.
        """
        volume = leesCompose("docker-compose.delft-test.yml")["volumes"]["archeomedia-delft-test"]
        assert not volume or (volume.get("driver_opts") or {}).get("type") != "tmpfs"
        dockerfile = leesBestand("services/airflow/Dockerfile")
        assert "mkdir -p /output/archeomedia && chown airflow:root /output/archeomedia" in dockerfile

    @pytest.mark.parametrize("pad", ["docker-compose.test.yml", "docker-compose.delft-test.yml"])
    def test_flask_test_heet_flask_in_het_netwerk(self, pad):
        """httpd.conf stuurt door naar http://flask:5051/."""
        netwerken = leesCompose(pad)["services"]["flask-test"]["networks"]
        assert any("flask" in n.get("aliases", []) for n in netwerken.values())

    def test_makefile_start_apache_test_naast_flask_test(self):
        for regel in leesBestand("Makefile").splitlines():
            if "up -d" in regel and "flask-test" in regel:
                assert "apache-test" in regel, regel

    def test_smoke_tests_lopen_via_apache(self):
        smoke = leesBestand("tests/integration/test_flask_smoke.py")
        assert 'BASE_URL = "http://localhost:5061"' in smoke
        assert "5051" not in smoke.replace("flask:5051", "").replace(":5051", ""), "smoke tests benaderen Flask rechtstreeks"


@pytest.mark.unit
class TestProxyFix:
    """De Flask-app volgt via ProxyFix de buitenkant (host en protocol) uit de X-Forwarded-headers."""

    def test_proxyfix_om_de_wsgi_app(self):
        app = leesBestand("app/app/app.py")
        assert "from werkzeug.middleware.proxy_fix import ProxyFix" in app
        assert re.search(r"app\.wsgi_app = ProxyFix\(app\.wsgi_app, x_for=1, x_proto=1, x_host=1\)", app)
        # x_port niet: de hostpoort van Apache (bijvoorbeeld 15052) wijkt af van de containerpoort 5052
        assert "x_port" not in app
