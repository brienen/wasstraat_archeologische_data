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

### `docker-compose.yml` — Basisbestand

Het hoofdbestand definieert alle services met hun basisinstellingen:

```yaml
services:
  postgres:      # PostgreSQL met custom Dockerfile
  airflow:       # Airflow met volume-mounts naar dags, scripts, config
  redis:         # Bitnami Redis image
  flask:         # Flask web-applicatie
  mongo:         # MongoDB 4.2.21
  jupyter:       # Jupyter Lab met notebook-volumes
  apache:        # Apache voor statische bestanden
  elasticsearch: # Elasticsearch 8.6.1
```

Elk service leest haar configuratie uit `.env`-bestanden in de `config/` directory.

### `docker-compose.develop.yml` — Ontwikkelomgeving

Overschrijft instellingen voor lokale ontwikkeling:

- **Airflow**: Eén parser-proces (`DAG_FILE_PROCESSOR_PROCESSES=1`), geen parallelle taken (`PARALLELISM=1`, `DAG_CONCURRENCY=1`), debugpy-poort open op `:5678`
- **Flask**: Container blijft draaien via infinite loop (voor handmatig starten via IDE), broncode wordt als volume gemount, `FLASK_DEBUG=1`

### `docker-compose.acc.yml` — Acceptatieomgeving

Tussenomgeving met debug-mogelijkheden maar productie-achtige configuratie:

- Flask met `FLASK_DEBUG=1` maar productie-entrypoint
- Broncode als volume (voor snelle iteratie)
- Geschikt voor testen door eindgebruikers

### `docker-compose.prod.yml` — Productieomgeving

Gebruikt gepubliceerde Docker-images van Docker Hub:

- `brienen/wasstraat_flask:1.0.0` — Vaste versie van Flask-app
- `brienen/wasstraat_apache:0.8.0` — Vaste versie van Apache
- `FLASK_DEBUG=0` — Geen debug-modus
- Geen broncode-volumes (alles zit in de image)

### `docker-compose.example.yml` — Voorbeeldconfiguratie

Template voor een minimale configuratie, bruikbaar als startpunt voor nieuwe omgevingen.

## Starten en Stoppen

De `Makefile` bevat targets voor elke omgeving. Bij het starten wordt automatisch `init-config.sh` aangeroepen om eventueel ontbrekende `.env`-bestanden te genereren.

```bash
# Ontwikkelomgeving (met debugpy en hot-reload)
make dev

# Lokale modus (alle services)
make app

# Voorbeeldconfiguratie
make example

# Acceptatieomgeving
make acc

# Productieomgeving (met gepubliceerde images)
make prod

# Stoppen van alle containers
make stop

# Starten van gestopte containers
make start

# Stop en verwijder alle containers
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

## Configuratie via Environment-bestanden

Alle services lezen configuratie uit bestanden in `config/`:

| Bestand | Inhoud |
|---------|--------|
| `postgres.env` | PostgreSQL-credentials en database-naam |
| `mongo.env` | MongoDB-gebruiker, wachtwoord en database-namen |
| `airflow.env` | Airflow scheduler-instellingen, executor-type |
| `airflow_db.env` | Airflow metadata-database credentials |
| `redis.env` | Redis wachtwoord |
| `flask.env` | Flask geheime sleutel, debug-modus, poort |
| `elasticsearch.env` | Elasticsearch-host |
| `version.env` | Huidige versie van de applicatie |

!!! warning "Gevoelige gegevens"
    De `.env`-bestanden bevatten wachtwoorden en credentials. Neem deze **nooit** op in versiebeheer. Gebruik het `config/`-directory als template en vul per omgeving de juiste waarden in.

## Volume-Mounts

### Data-volumes

De Airflow-container koppelt de invoerdata via volumes:

```
./data/delft/data/digidepot        → /input/projecten
./data/delft/data/Delf-IT          → /input/delfit
./data/delft/data/magazijnlijst    → /input/magazijnlijst
./data/delft/data/digifotos        → /input/digifotos
./data/delft/data/monsterdatabase  → /input/monsterdatabase
./data/delft/data/rapporten        → /input/rapporten
./data/delft/data/referentietabellen → /input/referentietabellen
```

### Persistente volumes

Docker beheert drie named volumes:

- `wasstraat_postgres_volume` — PostgreSQL-data
- `wasstraat_mongo_volume` — MongoDB-data
- `elasticsearch-data` — Elasticsearch-indices

### Gedeelde code

De `shared/` directory wordt in zowel Airflow als Flask gemount en bevat de gezamenlijke configuratie (`config.py`), database-utilities en constanten.

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

De backups worden opgeslagen in de `backup/` directory.

## CSV-export

Alle definitieve tabellen kunnen als CSV worden geëxporteerd:

```bash
make export
```

Dit exporteert alle `Def_*` tabellen (Project, Put, Spoor, Vondst, Artefact, Monster, etc.) naar CSV-bestanden in `backup/postgres_<timestamp>/`.

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
