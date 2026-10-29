# Technologie Stack

## Overzicht

Deze pagina beschrijft de techniek die de Wasstraat op dit moment gebruikt. De versies volgen uit de Dockerfiles in `services/`, de `requirements.txt`-bestanden en de vastgelegde versies in `services/*/constraints.txt` (zie [Configuratie: pakketversies](../componenten/configuratie.md#7-pakketversies)). Bij twijfel zijn die bestanden leidend.

## Containers en basis-images

| Service | Basis-image | Rol |
|---------|-------------|-----|
| **Airflow** | `apache/airflow:2.10.5-python3.11` | ETL-orchestratie (LocalExecutor) |
| **Flask** | `python:3.11-slim-bookworm` | Webapplicatie, draait onder gunicorn met gevent |
| **PostgreSQL** | `kartoza/postgis:18-3.6` | Definitieve relationele opslag met PostGIS |
| **MongoDB** | `mongo:7.0` | Werkgeheugen van de pipeline: staging, `Single_Store`, `Single_Store_Clean`, run-documenten |
| **Elasticsearch** | `elasticsearch:8.17.0` | Fulltext-zoekindex (single-node, zonder beveiliging) |
| **Redis** | `redis:7.2-alpine` | Cache voor de webapplicatie |
| **Apache** | `httpd:2.4` | Voordeur van de webapplicatie: reverse proxy naar Flask (`mod_proxy_http`) en serveert foto's en andere bestanden onder `/archeomedia` uit de uitvoermap |
| **Jupyter** | `quay.io/jupyter/datascience-notebook:python-3.11` (op een digest) | Notebooks voor analyse, alleen in de ontwikkelomgeving |

Alles draait via Docker Compose. De bediening loopt via een `Makefile` en enkele bash-scripts. De eigen images (Airflow, Flask, PostgreSQL, Apache) worden gepubliceerd op `ghcr.io/brienen` voor `linux/amd64` en `linux/arm64`; de live installatie in `deploy/` gebruikt alleen die images.

## ETL-pipeline (Airflow)

| Component | Versie | Rol |
|-----------|--------|-----|
| **Python** | 3.11 | Taal van de DAGs en transformatiemodules |
| **pandas** | 2.1 (< 2.2) | Dataframes, onder meer voor het inlezen van de Excel-bestanden. Airflow 2.10 pint SQLAlchemy < 2.0, en pandas 2.2 vereist SQLAlchemy 2; de laadstap gebruikt daarom geen pandas maar psycopg2 |
| **pymongo** | 4.19 | Toegang tot MongoDB en aggregatie-pipelines |
| **psycopg2** | 2.9 | Laden naar PostgreSQL met `execute_values` |
| **openpyxl** | 3.1 | Inlezen van de harmonisatie-Excel en ABR-tabellen |
| **geopandas / shapely** | 1.1 / 2.x | Geometrie en coördinaten |
| **Pillow, pdf2image** | 11.3, 1.17 | Afbeeldingen en PDF's omzetten naar drie formaten in de mediamap |
| **python-magic** | 0.4 | Bestandstypen herkennen |
| **nltk, editdistance, roman** | | Tekstnormalisatie, fuzzy vergelijken en Romeinse cijfers in dateringen |
| **elasticsearch** | 8.x (client, gelijk aan de hoofdversie van de server) | Bouwen van de zoekindex |
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
| **Flask** | 2.3.3 | Webframework, onder gunicorn met gevent (poort 5051) |
| **Flask-AppBuilder** | 4.8 | Beheerschermen, rechten, standaardviews en de REST-API |
| **SQLAlchemy** | 1.4.54 | ORM voor de modellen in `app/app/models.py` |
| **GeoAlchemy2** | 0.20 | Geometriekolommen, met de eigen extensie `fab_addon_geoalchemy` |
| **Flask-Caching** | 2.4 | Cache in Redis (`CACHE_*` in `config/redis.env`) |
| **Flask-Migrate** | 4.1 | Geïnitialiseerd, maar de opstartprocedure draait geen migraties: de tabellen ontstaan met `db.create_all()` en de kolommen voor gebruikersdata met `gebruikersdata.migreerSchema` |
| **Flask-Dropzone** | 1.x | Uploaden van bestanden |
| **Flask-DebugToolbar** | 0.x | Debugwerkbalk (`DEBUG_TB_PROFILER_ENABLED`) |
| **folium** | 0.20 | Interactieve kaart op de startpagina |
| **Jinja2** | 3.x | Templates |

De tabellen in PostgreSQL worden bij het opstarten door de Flask-app aangemaakt. De Load-stap van Airflow verwacht dat die tabellen bestaan.

Flask draait achter Apache en heeft geen hostpoort; `ProxyFix` van Werkzeug neemt de host en het protocol van de buitenkant over uit de `X-Forwarded`-headers die Apache meestuurt.

## Opslag

| Laag | Techniek | Inhoud |
|------|----------|--------|
| **Staging** | MongoDB, database `Arch_Staging` | Ruwe brondata zoals ingelezen, `Plaatjes`, run-documenten (`Verwerkingsruns`) |
| **Analyse** | MongoDB, database `Arch_Analyse` | Geharmoniseerde data (`Single_Store`) en samengevoegde data met sleutels (`Single_Store_Clean`) |
| **Bestanden** | MongoDB, database `Arch_Files`, en de uitvoermap op de host | De lijst met te verwerken afbeeldingen (`Filenames`); de verwerkte bestanden zelf staan in drie formaten in de uitvoermap (`AIRFLOW_OUTPUT_MEDIA`) |
| **Definitief** | PostgreSQL met PostGIS, database `flask` | Relationeel model voor de webapplicatie, zie [Gegevensmodel](gegevensmodel.md) |
| **Zoeken** | Elasticsearch | Index per tabel, zie [Zoeken en indexering](../componenten/zoeken.md) |

## Standaarden

| Standaard | Gebruik |
|-----------|---------|
| **ABR** | Archeologisch Basisregister, ingelezen uit een Excel-export. Vooral materialen en submaterialen worden gebruikt |
| **Rijksdriehoek (EPSG:28992)** | Coördinaten uit de brondata, omgerekend naar WGS84 voor de kaart |
| **GGM** | Gemeentelijk Gegevensmodel: referentie voor het doelmodel; een vertaling bestaat nog niet (zie [Toekomstvisie](../toekomstvisie.md)) |

## Ontwikkelen en testen

| Tool | Rol |
|------|-----|
| **pytest** | Unit- en integratietests, zie [Testen](../testen.md) |
| **debugpy** | Debuggen van Airflow via `make dev` |
| **MkDocs** | Deze documentatie, met het thema readthedocs |
| **Jackcess + JPype** | Genereren van de synthetische Access-databases (`make synthetic`) |
