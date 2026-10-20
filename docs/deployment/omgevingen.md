# Omgevingen & Docker Compose

De Wasstraat draait als een set Docker-containers die via `docker-compose` worden georkestreerd. Er zijn meerdere compose-bestanden die samen de verschillende omgevingen definiëren.

## Services Overzicht

Het platform bestaat uit de volgende services:

| Service | Container | Poort | Beschrijving |
|---------|-----------|-------|-------------|
| **PostgreSQL** | `wasstraat_postgres` | 5432 | Definitieve relationele opslag (GGM-compatibel) |
| **MongoDB** | `wasstraat_mongo` | 27017 | Ruwe opslag, staging, bestands-metadata |
| **Airflow** | `wasstraat_airflow` | 8080 | ETL-orchestratie en dataverwerkingspipeline |
| **Flask** | `wasstraat_flask` | 5051 | Web-applicatie voor data-inzicht en -beheer |
| **Elasticsearch** | `wasstraat_elasticsearch` | 9200 | Fulltext-zoekindex |
| **Redis** | `wasstraat_redis` | 6379 | Caching-laag voor de web-applicatie |
| **Apache** | `wasstraat_apache` | 5052 | Statische bestandsserver (foto's, rapporten) |
| **Jupyter** | `wasstraat_jupyter` | 8888 | Notebooks voor data-analyse en exploratie |

## Docker Compose Bestanden

### `docker-compose.yml` — Basisbestand (`make app`)

Het hoofdbestand definieert alle services en gebruikt de synthetische voorbeelddata uit `data/synthetic/`:

```yaml
services:
  postgres:      # PostgreSQL 18 met PostGIS 3.6 (kartoza/postgis), eigen Dockerfile
  airflow:       # Apache Airflow 2.10.5 met Python 3.11, eigen Dockerfile
  redis:         # redis:7.2-alpine
  flask:         # Flask-webapplicatie op python:3.11-slim, eigen Dockerfile
  mongo:         # mongo:7.0
  jupyter:       # Jupyter Lab (jupyter/datascience-notebook, Python 3.11)
  apache:        # httpd:2.4 voor statische bestanden
  elasticsearch: # Elasticsearch 8.17.0
```

Elke service leest haar configuratie uit `.env`-bestanden in de `config/` directory.

### `docker-compose.delft.yml` — Eigen data (`make delft`)

Zelfde services als het basisbestand, maar met de brondata uit `data/delft/data/`, de configuratie uit `data/delft/wasstraat_config/` en de uitvoer en backups in `data/delft/`. De naam is historisch: dit is het bestand voor elke installatie met eigen brondata. Wil je een eigen omgevingsnaam, kopieer het dan en pas de paden aan.

### `docker-compose.develop.yml` — Ontwikkelomgeving (`make dev`)

Overschrijft instellingen voor lokale ontwikkeling:

- **Airflow**: Eén parser-proces (`DAG_FILE_PROCESSOR_PROCESSES=1`), geen parallelle taken (`PARALLELISM=1`, `DAG_CONCURRENCY=1`), debugpy-poort open op `:5678`
- **Flask**: Container blijft draaien via infinite loop (voor handmatig starten via IDE), broncode wordt als volume gemount, `FLASK_DEBUG=1`

### `docker-compose.test.yml` en `docker-compose.delft-test.yml` — Testomgevingen

Zelfstandige testomgevingen voor `make integration` en `make integration-delft`, met eigen containernamen, poorten en databases in het geheugen. Zie [Testen](../testen.md).

## Starten en Stoppen

De `Makefile` bevat targets voor elke omgeving. Bij het starten wordt automatisch `init-config.sh` aangeroepen om eventueel ontbrekende `.env`-bestanden te genereren.

```bash
# Alle services met synthetische voorbeelddata
make app

# Alle services met eigen data uit data/delft/
make delft

# Ontwikkelomgeving (met debugpy en hot-reload)
make dev

# Stoppen van alle containers
make stop

# Starten van gestopte containers
make start

# Stop en verwijder alle containers (de volumes blijven bestaan)
make down

# Toon live logs
make logs

# Toon status van alle services
make ps
```

!!! tip "Achterliggend commando"
    Elk target voert het bijbehorende `docker compose` commando uit. Bijvoorbeeld `make dev` draait:
    ```
    docker compose -f docker-compose.yml -f docker-compose.develop.yml up -d
    ```
    Typ `make help` voor een overzicht van alle beschikbare commando's.

!!! note "Eén installatie per Docker-host"
    De containers hebben vaste namen, zoals `wasstraat_postgres`. Er kan daarom maar één Wasstraat-installatie tegelijk op een Docker-host bestaan. `make app` en `make delft` gebruiken dezelfde containers.

## Configuratie via Environment-bestanden

Alle services lezen configuratie uit bestanden in `config/`:

| Bestand | Inhoud |
|---------|--------|
| `postgres.env` | PostgreSQL-credentials en database-namen |
| `mongo.env` | MongoDB-gebruiker, wachtwoord en database-namen |
| `airflow.env` | Airflow scheduler-instellingen, executor-type, beheerder |
| `airflow_db.env` | Airflow metadata-database credentials |
| `redis.env` | Redis-wachtwoord en cache-instellingen |
| `flask.env` | Flask geheime sleutel, wachtwoord van de beheerder (`FLASK_ADMIN_PASSWORD`) en mailinstellingen |
| `jupyter.env` | Token voor Jupyter Lab (`JUPYTER_PASSWORD`) |
| `elasticsearch.env` | Wordt niet ingelezen; de services gebruiken standaard `http://elasticsearch:9200` |
| `version.env` | Versienummer, alleen gebruikt door `make release` |

Daarnaast leest de Airflow-container configuratie uit `wasstraat_config/` (gemount als `/opt/airflow/config/`):

| Bestand | Inhoud |
|---------|--------|
| `Wasstraat_Config_HarmonizeV3.xlsx` | Harmonisatie-mapping (veldnamen per objecttype) |
| `correcties.yml` | Gemeente-specifieke datacorrecties (projectcodes, rapportprefixen) |

!!! warning "Gevoelige gegevens"
    De `.env`-bestanden bevatten wachtwoorden en credentials. Neem deze **nooit** op in versiebeheer. Gebruik het `config/`-directory als template en vul per omgeving de juiste waarden in.

## Volume-Mounts

### Data-volumes

De Airflow-container koppelt de invoerdata via volumes. Bij `make app` komen die uit `data/synthetic/data/`, bij `make delft` uit `data/delft/data/`:

```
./data/<omgeving>/data/projecten          → /input/projecten
./data/<omgeving>/data/projectenlijst     → /input/projectenlijst
./data/<omgeving>/data/magazijnlijst      → /input/magazijnlijst
./data/<omgeving>/data/fotolijst          → /input/fotolijst
./data/<omgeving>/data/monsterdatabase    → /input/monsterdatabase
./data/<omgeving>/data/rapporten          → /input/rapporten          (alleen make delft)
./data/<omgeving>/data/referentietabellen → /input/referentietabellen
./data/<omgeving>/output/archeomedia      → /output/archeomedia
./data/<omgeving>/wasstraat_config        → /opt/airflow/config
```

### Persistente volumes

Docker beheert vier named volumes:

| Volume | Pad in de container | Inhoud |
|--------|---------------------|--------|
| `wasstraat_postgres_volume` | `/data/postgres` | PostgreSQL-data (Flask-database en Airflow-metadata) |
| `wasstraat_mongo_volume` | `/data/db` | MongoDB-data |
| `wasstraat_mongo_config_volume` | `/data/configdb` | MongoDB-configuratie |
| `elasticsearch-data` | `/usr/share/elasticsearch/data` | Elasticsearch-indices |

Docker Compose zet de projectnaam voor de volumenaam, standaard de naam van de map, bijvoorbeeld `wasstraat_archeologische_data_wasstraat_postgres_volume`.

!!! warning "PGDATA en het volume horen bij elkaar"
    PostgreSQL schrijft naar de map uit `PGDATA`. Die staat in de compose-bestanden op `/data/postgres`, precies waar het volume hangt. Wijzig je de een, wijzig dan ook de ander. Staan ze uit elkaar, dan komt de database in de container zelf terecht en verdwijnt die zodra Docker Compose de container opnieuw aanmaakt.

### Bestaande installatie: PostgreSQL-data naar het volume

Tot oktober 2026 hing het PostgreSQL-volume op `/var/lib/postgresql/data`, terwijl `PGDATA` op `/data/postgres` stond. Bij installaties uit die tijd staat de database daardoor in de container zelf, en is het volume leeg. Zodra je zo'n installatie start met de nieuwe compose-bestanden, maakt Docker Compose de PostgreSQL-container opnieuw aan en is die database weg. Migreer de data daarom eerst:

```bash
make start                   # start de bestaande containers zonder ze opnieuw aan te maken
make backup                  # extra zekerheid: dump van PostgreSQL en MongoDB
make stop
make migrate-postgres-data   # kopieert de data uit de oude container naar het volume
make app                     # of: make delft
```

`make migrate-postgres-data` wijzigt de oude container niet. Het script stopt zonder iets te doen als de container nog draait, als het volume al data bevat of als de migratie al is gedaan. Na het kopiëren telt het de bestanden in bron en volume en meldt het een fout als die niet gelijk zijn. Gebruik je een andere containernaam, geef die dan mee: `make migrate-postgres-data PG_CONTAINER=<naam>`.

!!! danger "Niet eerst make app of make down"
    Draai bij een bestaande installatie geen `make app`, `make delft`, `make down` of `docker compose up` voordat de migratie klaar is. Elk van die commando's kan de oude PostgreSQL-container verwijderen, en daarmee de database.

### Gedeelde code

De `shared/` directory wordt in zowel Airflow als Flask gebruikt en bevat de gezamenlijke configuratie (`config.py`), database-utilities en constanten.

## Backup en Restore

De Makefile bevat targets voor backup en restore:

```bash
# Backup van PostgreSQL en MongoDB (met timestamp)
make backup

# Restore vanuit een eerder backup-timestamp
make restore TS=2024-03-15_14-30-00
```

Bij een backup worden de Flask- en Airflow-containers tijdelijk gestopt. De backup bevat:

- PostgreSQL: `pg_dump` als tar-archief
- MongoDB: `mongodump` van staging-, bestands- en analyse-databases

De backups komen in `data/<omgeving>/backup/postgres/` en `data/<omgeving>/backup/mongo/`, dus in `data/synthetic/backup/` bij `make app` en in `data/delft/backup/` bij `make delft`.

## CSV-export

Alle definitieve tabellen kunnen als CSV worden geëxporteerd:

```bash
make export
```

Dit exporteert alle `Def_*` tabellen (Project, Put, Spoor, Vondst, Artefact, Monster, etc.) naar CSV-bestanden in `data/<omgeving>/backup/postgres/postgres_<timestamp>/`.

## Release en Publicatie

Voor het publiceren van een nieuwe versie:

```bash
make release VERSION=<versie> MSG="<beschrijving>"
# Voorbeeld: make release VERSION=1.1.0 MSG="Nieuwe zoekfunctionaliteit"
```

Dit voert de volgende stappen uit:

1. Schrijft versienummer naar `config/version.env`
2. Maakt een git-tag aan
3. Commit en pusht alle wijzigingen
4. Bouwt multi-platform Docker-images (linux/amd64 + linux/arm64) via `docker buildx`
5. Pusht images naar Docker Hub onder `brienen/wasstraat_flask:<versie>`
