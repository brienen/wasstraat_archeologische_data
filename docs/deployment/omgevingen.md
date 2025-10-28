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

Het startscript `runws.sh` combineert de juiste compose-bestanden per omgeving:

```bash
# Ontwikkelomgeving (met debugpy)
./runws.sh dev

# Lokale modus (basis compose)
./runws.sh app

# Acceptatieomgeving
./runws.sh acc

# Productieomgeving (met gepubliceerde images)
./runws.sh prod

# Stoppen van alle containers
./runws.sh stop

# Starten van gestopte containers
./runws.sh start
```

!!! tip "Achterliggend commando"
    Elk commando voert het bijbehorende `docker-compose` commando uit. Bijvoorbeeld `./runws.sh dev` draait:
    ```
    docker-compose -f docker-compose.yml -f docker-compose.develop.yml up -d
    ```

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
./data/input/basefiles/projectdatabase/digidepot → /input/projecten
./data/input/basefiles/projectdatabase/Delf-IT   → /input/delfit
./data/input/basefiles/projectdatabase/magazijnlijst → /input/magazijnlijst
./data/input/basefiles/projectdatabase/digifotos → /input/digifotos
./data/input/basefiles/projectdatabase/monsterdatabase → /input/monsterdatabase
./data/input/basefiles/projectdatabase/rapporten → /input/rapporten
./data/input/basefiles/projectdatabase/referentietabellen → /input/referentietabellen
```

### Persistente volumes

Docker beheert drie named volumes:

- `wasstraat_postgres_volume` — PostgreSQL-data
- `wasstraat_mongo_volume` — MongoDB-data
- `elasticsearch-data` — Elasticsearch-indices

### Gedeelde code

De `shared/` directory wordt in zowel Airflow als Flask gemount en bevat de gezamenlijke configuratie (`config.py`), database-utilities en constanten.

## Backup en Restore

Het startscript biedt ingebouwde backup-functionaliteit:

```bash
# Backup van PostgreSQL en MongoDB (met timestamp)
./runws.sh backup

# Restore vanuit een eerder backup-timestamp
./runws.sh restore 2024-03-15_14-30-00
```

Bij een backup worden de Flask- en Airflow-containers tijdelijk gestopt. De backup bevat:

- PostgreSQL: `pg_dump` als tar-archief
- MongoDB: `mongodump` van staging-, bestands- en analyse-databases

De backups worden opgeslagen in de `backup/` directory.

## CSV-export

Alle definitieve tabellen kunnen als CSV worden geëxporteerd:

```bash
./runws.sh export
```

Dit exporteert alle `Def_*` tabellen (Project, Put, Spoor, Vondst, Artefact, Monster, etc.) naar CSV-bestanden in `backup/postgres_<timestamp>/`.

## Release en Publicatie

Voor het publiceren van een nieuwe versie:

```bash
./runws.sh release <versie> "<beschrijving>"
# Voorbeeld: ./runws.sh release 1.1.0 "Nieuwe zoekfunctionaliteit"
```

Dit voert de volgende stappen uit:

1. Schrijft versienummer naar `config/version.env`
2. Maakt een git-tag aan
3. Commit en pusht alle wijzigingen
4. Bouwt multi-platform Docker-images (linux/amd64 + linux/arm64) via `docker buildx`
5. Pusht images naar Docker Hub onder `brienen/wasstraat_flask:<versie>`
