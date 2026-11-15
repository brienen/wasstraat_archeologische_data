# Systeemarchitectuur

De Wasstraat bestaat uit twee applicaties met ondersteunende services, die samen als Docker Compose-stack draaien:

- **Airflow** (`airflow_app/`) verwerkt de brondata: het leest Access-databases, Excel-bestanden, foto's en rapporten in, harmoniseert en koppelt ze in MongoDB en laadt het resultaat in PostgreSQL en Elasticsearch.
- **De webapplicatie** (`app/`, Flask met Flask-AppBuilder) maakt de verwerkte data doorzoekbaar en bewerkbaar. Apache is de voordeur: het serveert de verwerkte foto's en documenten zelf en stuurt alle andere verzoeken door naar Flask.

![Systeemarchitectuur](../assets/images/systeem-architectuur.svg)

## Services

| Service | Container | Image | Rol |
|---------|-----------|-------|-----|
| Apache | `wasstraat_apache` | eigen image op `httpd:2.4` | Voordeur op poort 5052: serveert `/archeomedia` uit de uitvoermap en stuurt al het overige door naar `http://flask:5051/` |
| Flask | `wasstraat_flask` | eigen image op `python:3.11-slim-bookworm` | Webapplicatie (gunicorn met gevent op poort 5051, zonder hostpoort); maakt bij het opstarten de tabellen in PostgreSQL aan |
| Airflow | `wasstraat_airflow` | eigen image op `apache/airflow:2.10.5-python3.11` | Verwerkingspipeline: webserver en scheduler met de LocalExecutor, plus mdbtools, MongoDB Database Tools, Poppler en GDAL |
| PostgreSQL | `wasstraat_postgres` | eigen image op `kartoza/postgis:18-3.6` | Definitieve opslag (database `flask`) en metadatabase van Airflow (database `airflow`) |
| MongoDB | `wasstraat_mongo` | `mongo:7.0` | Werkgeheugen van de pipeline: staging, `Single_Store`, `Single_Store_Clean`, run-documenten |
| Elasticsearch | `wasstraat_elasticsearch` | `elasticsearch:8.17.0` | Zoekindex, één index per `Def_`-tabel |
| Redis | `wasstraat_redis` | `redis:7.2-alpine` | Cache van de webapplicatie (pagina's en zoekresultaten) |
| Jupyter | `wasstraat_jupyter` | eigen image op `quay.io/jupyter/datascience-notebook:python-3.11` (vastgezet op een digest) | Alleen in de ontwikkelomgeving: notebooks voor analyse |

De eigen images (airflow, flask, postgres, apache) worden gepubliceerd op `ghcr.io/brienen/wasstraat-<service>`. Poorten en mounts per omgeving staan in [Configuratie](../componenten/configuratie.md#27-paden-en-mounts).

## Gegevensstromen

| Van | Naar | Wat |
|-----|------|-----|
| Invoermappen (`/input/...`, alleen gelezen) | Airflow | Access-databases, Excel-bestanden, foto's, tekeningen, rapporten |
| `wasstraat_config/` | Airflow | Harmonisatie-Excel en `correcties.yml` |
| Airflow | MongoDB | Staging, `Single_Store`, `Single_Store_Clean`, `Filenames`, `Plaatjes`, run-documenten |
| Airflow | Uitvoermap `archeomedia/` | Elke foto, tekening en elk rapport in drie formaten (groot, middel, thumbnail) |
| Airflow | Uitvoermap `rapporten/` | Verwerkingsrapport per run (JSON en Markdown) |
| Airflow | PostgreSQL | De `Def_`-tabellen (database `flask`) en de registratie van bronbestanden (`Def_Bronbestand`) |
| Airflow | Elasticsearch | Index per tabel |
| Browser | Apache | Alle verzoeken op poort 5052 |
| Apache | Uitvoermap `archeomedia/` | Foto's en documenten onder `/archeomedia/...` (alleen gelezen) |
| Apache | Flask | Alle andere verzoeken (reverse proxy, met `X-Forwarded-Proto` en de oorspronkelijke `Host`) |
| Flask | PostgreSQL, Elasticsearch, Redis | Lezen en bewerken van de data, zoeken, cache |
| Flask | Uitvoermap `archeomedia/` | Gekantelde foto's terugschrijven |

## Opslaglagen

| Laag | Techniek | Inhoud | Levensduur |
|------|----------|--------|------------|
| Bron | Bestanden op de host | Brondata van de gemeente | Onaangeroerd; de pipeline schrijft er nooit in |
| Staging | MongoDB, `Arch_Staging` en `Arch_Files` | De brondata zoals ingelezen, één document per rij | Geleegd door de volledige cyclus; de incrementele cyclus werkt hem bij |
| Analyse | MongoDB, `Arch_Analyse` | `Single_Store` (geharmoniseerd) en `Single_Store_Clean` (samengevoegd, met sleutels) | Idem |
| Definitief | PostgreSQL met PostGIS, database `flask` | Het relationele model van de webapplicatie (`Def_`-tabellen) | Blijvend; sleutels stabiel tussen cycli |
| Zoeken | Elasticsearch | Tekstvelden per tabel | Opnieuw op te bouwen uit PostgreSQL (`DAG_Load_Only`) |
| Media | Uitvoermap op de host | Verwerkte bestanden in drie formaten | Opnieuw te maken door de volledige cyclus |

Zie [MongoDB en Single_Store](../componenten/singlestore.md) en [Gegevensmodel](gegevensmodel.md).

## Gegevens van de pipeline en van gebruikers

De `Def_`-tabellen van de pipeline worden bij elke cyclus opnieuw gevuld uit de brondata. Een wijziging die je in de webapplicatie aanbrengt aan bijvoorbeeld een artefact of vondst, wordt bij de volgende cyclus weer overschreven; corrigeer brondata daarom in de bron of met [`correcties.yml`](../componenten/configuratie.md#3-correctiesyml).

Een paar tabellen zijn van de gebruikers: bruiklenen, partijen, conserveringsprojecten en extra ABR-materialen bij een artefact. Die voert men in de webapplicatie in en de pipeline laat ze staan. Verdwijnt een artefact of project waarnaar zo'n rij verwijst uit de brondata, dan blijft de rij bestaan met een lege verwijzing en een markering; keert de rij met dezelfde sleutel terug, dan wordt de verwijzing hersteld. Zie [Gegevensmodel](gegevensmodel.md#gebruikerstabellen).

## Omgevingen

| Omgeving | Compose-bestand | Images | Data |
|----------|-----------------|--------|------|
| Ontwikkelomgeving, synthetische data | `docker-compose.yml` (`make app`) | zelf gebouwd, broncode gemount | `data/synthetic/` |
| Ontwikkelomgeving, eigen data | `docker-compose.delft.yml` (`make delft`) | idem | `data/delft/` |
| Debuggen | `docker-compose.yml` + `docker-compose.develop.yml` (`make dev`) | idem, Flask en debugpy met hostpoort | `data/synthetic/` |
| Live installatie | `deploy/docker-compose.yml` | gepubliceerd op `ghcr.io/brienen` | `deploy/data/` of eigen mappen |
| Testomgevingen | `docker-compose.test.yml`, `docker-compose.delft-test.yml` | zelf gebouwd | `data/synthetic/`, `data/test/` |

De containers hebben vaste namen (`wasstraat_postgres`, ...); er kan per Docker-host maar één installatie tegelijk draaien. De testomgevingen hebben eigen containernamen en een eigen projectnaam en kunnen naast een installatie draaien. Zie [Omgevingen en Docker Compose](../deployment/omgevingen.md) en [Installatie met images](../deployment/installatie-met-images.md).

## Beveiliging

- Alle wachtwoorden worden per installatie gegenereerd door `init-config.sh` en staan alleen in `config/*.env` (niet in versiebeheer).
- De logs tonen verbindingen zonder wachtwoord (`shared/logutils.maskeerWachtwoord`).
- Elasticsearch draait zonder beveiliging; in de live installatie heeft het geen hostpoort en de databases luisteren standaard alleen op `127.0.0.1`.
- Apache serveert de media zonder inlog. Zet een installatie niet rechtstreeks aan het internet; gebruik een reverse proxy met TLS vóór Apache (zie [Installatie met images](../deployment/installatie-met-images.md#6-inloggen)).
