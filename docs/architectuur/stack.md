# Technologie Stack

## Overzicht

Deze pagina beschrijft de techniek die de Wasstraat op dit moment gebruikt. De versies volgen uit de Dockerfiles in `services/` en de `requirements.txt`-bestanden. Bij twijfel zijn die bestanden leidend.

## Containers en basis-images

| Service | Basis-image | Rol |
|---------|-------------|-----|
| **Airflow** | `apache/airflow:2.10.5-python3.11` | ETL-orchestratie (LocalExecutor) |
| **Flask** | `python:3.11-slim-bookworm` | Webapplicatie, draait onder gunicorn met gevent |
| **PostgreSQL** | `kartoza/postgis:18-3.6` | Definitieve relationele opslag met PostGIS |
| **MongoDB** | `mongo:7.0` | Staging- en analyse-opslag, plus GridFS voor bestanden |
| **Elasticsearch** | `elasticsearch:8.17.0` | Fulltext-zoekindex (single-node, zonder beveiliging) |
| **Redis** | `redis:7.2-alpine` | Cache voor de webapplicatie |
| **Apache** | `httpd:2.4` | Voordeur van de webapplicatie: reverse proxy naar Flask (`mod_proxy_http`) en serveert foto's en andere bestanden onder `/archeomedia` uit de uitvoermap |
| **Jupyter** | `quay.io/jupyter/datascience-notebook:python-3.11` | Notebooks voor analyse |

Alles draait via Docker Compose. De bediening loopt via een `Makefile` en enkele bash-scripts.

## ETL-pipeline (Airflow)

| Component | Versie | Rol |
|-----------|--------|-----|
| **Python** | 3.11 | Taal van de DAGs en transformatiemodules |
| **pandas** | < 2.2 | Dataframes. Airflow 2.10 pint SQLAlchemy < 2.0, en pandas 2.2 vereist SQLAlchemy 2 |
| **pymongo** | 4.x | Toegang tot MongoDB en aggregatie-pipelines |
| **psycopg2** | 2.9 | Laden naar PostgreSQL met `execute_values` |
| **openpyxl** | 3.x | Inlezen van de harmonisatie-Excel en ABR-tabellen |
| **geopandas / shapely** | 1.x / 2.x | Geometrie en coördinaten |
| **Pillow, pdf2image** | 11.x, 1.17 | Afbeeldingen en PDF's omzetten naar webformaten |
| **python-magic** | 0.4 | Bestandstypen herkennen |
| **nltk, editdistance, roman** | | Tekstnormalisatie, fuzzy vergelijken en Romeinse cijfers in dateringen |
| **elasticsearch** | 8.x | Bouwen van de zoekindex |
| **PyYAML** | | Inlezen van `correcties.yml` |

Systeemtools in de Airflow-image:

| Tool | Rol |
|------|-----|
| **mdbtools** | Tabellen uit Access-databases (`.mdb`, `.accdb`) exporteren |
| **MongoDB Database Tools** | `mongoimport` en `mongodump` |
| **mongosh** | MongoDB-shell voor scripts |
| **poppler-utils, GDAL** | PDF-verwerking en geodata |

## Webapplicatie (Flask)

| Component | Versie | Rol |
|-----------|--------|-----|
| **Flask** | 2.3 | Webframework |
| **Flask-AppBuilder** | 4.x | Beheerschermen, rechten en standaardviews |
| **SQLAlchemy** | 1.4 | ORM voor de ruim honderd modellen in `app/app/models.py` |
| **GeoAlchemy2** | | Geometriekolommen, met de eigen extensie `fab_addon_geoalchemy` |
| **Flask-Caching** | 2.x | Cache in Redis |
| **Flask-Migrate** | 4.x | Databasemigraties via Alembic |
| **Flask-Dropzone** | | Uploaden van bestanden |
| **folium** | | Interactieve kaart op de homepage |
| **Jinja2** | 3.x | Templates |

De tabellen in PostgreSQL worden bij het opstarten door de Flask-app aangemaakt. De Load-stap van Airflow verwacht dat die tabellen bestaan.

Flask draait achter Apache en heeft geen hostpoort; `ProxyFix` van Werkzeug neemt de host en het protocol van de buitenkant over uit de `X-Forwarded`-headers die Apache meestuurt.

## Opslag

| Laag | Techniek | Inhoud |
|------|----------|--------|
| **Staging** | MongoDB, database `Arch_Staging` | Ruwe brondata, zoals ingelezen |
| **Analyse** | MongoDB, database `Arch_Analyse` | Geharmoniseerde data in de collectie `Single_Store` |
| **Bestanden** | MongoDB GridFS, database `Arch_Files` | Bestandsinhoud en metadata |
| **Definitief** | PostgreSQL met PostGIS, database `flask` | Relationeel model voor de webapplicatie |
| **Zoeken** | Elasticsearch | Index per tabel |

## Standaarden

| Standaard | Gebruik |
|-----------|---------|
| **ABR** | Archeologisch Basisregister, ingelezen uit een Excel-export. Vooral materialen en submaterialen worden gebruikt |
| **Rijksdriehoek (EPSG:28992)** | Coördinaten uit de brondata, omgerekend naar WGS84 voor de kaart |
| **GGM** | Gemeentelijk Gegevensmodel als referentie voor het doelmodel |

## Ontwikkelen en testen

| Tool | Rol |
|------|-----|
| **pytest** | Unit- en integratietests, zie [Testen](../testen.md) |
| **debugpy** | Debuggen van Airflow via `make dev` |
| **MkDocs** | Deze documentatie, met het thema readthedocs |
| **Jackcess + JPype** | Genereren van de synthetische Access-databases (`make synthetic`) |
