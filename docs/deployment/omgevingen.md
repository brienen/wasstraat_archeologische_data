# Omgevingen & Docker Compose

De Wasstraat draait als een set Docker-containers die via `docker compose` worden georkestreerd. Er zijn meerdere compose-bestanden die samen de verschillende omgevingen definiëren.

!!! info "Ontwikkelomgeving en live installatie"
    De compose-bestanden in de repository bouwen de images uit de broncode en mounten die broncode in de containers: dit is de **ontwikkelomgeving**. Een installatie voor gebruik draait uit de **gepubliceerde images** op `ghcr.io/brienen`, met het compose-bestand in de map `deploy/`, zonder broncode. Zie [Installatie met images](installatie-met-images.md). Deze pagina beschrijft de ontwikkelomgeving en, onderaan, het publiceren van de images.

## Services Overzicht

Het platform bestaat uit de volgende services:

| Service | Container | Poort | Beschrijving |
|---------|-----------|-------|-------------|
| **PostgreSQL** | `wasstraat_postgres` | 5432 | Definitieve relationele opslag (GGM-compatibel) |
| **MongoDB** | `wasstraat_mongo` | 27017 | Ruwe opslag, staging, bestands-metadata |
| **Airflow** | `wasstraat_airflow` | 8080 | ETL-orchestratie en dataverwerkingspipeline |
| **Flask** | `wasstraat_flask` | — (via Apache) | Web-applicatie voor data-inzicht en -beheer |
| **Elasticsearch** | `wasstraat_elasticsearch` | 9200 | Fulltext-zoekindex |
| **Redis** | `wasstraat_redis` | 6379 | Caching-laag voor de web-applicatie |
| **Apache** | `wasstraat_apache` | 5052 | Voordeur: reverse proxy naar Flask en bestandsserver voor `/archeomedia` (foto's, rapporten) |
| **Jupyter** | `wasstraat_jupyter` | 8888 | Notebooks voor data-analyse en exploratie |

!!! info "Apache is de voordeur van de webapplicatie"
    De browser praat alleen met Apache (poort 5052). Apache serveert de verwerkte media onder `/archeomedia` rechtstreeks uit de uitvoermap (`data/<omgeving>/output`, alleen-lezen gemount) en stuurt alle overige verzoeken door naar `http://flask:5051/` binnen het compose-netwerk (`services/apache/httpd.conf`: `ProxyPass`, `ProxyPreserveHost On`, `X-Forwarded-Proto`). Flask heeft daardoor geen hostpoort. De webapplicatie verwijst naar foto's met relatieve paden `/archeomedia/...`; rechtstreeks op Flask blijven die leeg. In Flask neemt `ProxyFix` (`app/app/app.py`) de host en het protocol van de buitenkant over uit de `X-Forwarded`-headers, zodat redirects kloppen, ook achter een TLS-proxy vóór Apache.

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
  apache:        # httpd:2.4: voordeur, reverse proxy naar Flask en bestandsserver voor /archeomedia
  elasticsearch: # Elasticsearch 8.17.0
```

Elke service leest haar configuratie uit `.env`-bestanden in de `config/` directory.

### `docker-compose.delft.yml` — Eigen data (`make delft`)

Zelfde services als het basisbestand, maar met de brondata uit `data/delft/data/`, de configuratie uit `data/delft/wasstraat_config/` en de uitvoer en backups in `data/delft/`. De naam is historisch: dit is het bestand voor elke installatie met eigen brondata. Wil je een eigen omgevingsnaam, kopieer het dan en pas de paden aan.

### `docker-compose.develop.yml` — Ontwikkelomgeving (`make dev`)

Overschrijft instellingen voor lokale ontwikkeling:

- **Airflow**: Eén parser-proces (`DAG_FILE_PROCESSOR_PROCESSES=1`), geen parallelle taken (`PARALLELISM=1`, `DAG_CONCURRENCY=1`), debugpy-poort open op `:5678`
- **Flask**: Container blijft draaien via infinite loop (voor handmatig starten via IDE), broncode wordt als volume gemount, `FLASK_DEBUG=1`, en hostpoort 5051 om Flask rechtstreeks te benaderen (normaal loopt alles via Apache op 5052)

### `docker-compose.test.yml` en `docker-compose.delft-test.yml` — Testomgevingen

Zelfstandige testomgevingen voor `make integration` en `make integration-delft`, met eigen containernamen, een eigen projectnaam (`wasstraat-test`, `wasstraat-delft-test`), eigen poorten (Airflow 8081 en 8082, Apache 5061 en 5062) en MongoDB en PostgreSQL in het geheugen. Ze kunnen naast een installatie draaien, maar niet naast elkaar (beide gebruiken MongoDB-poort 27117). Zie [Testen](../testen.md).

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

Alle services lezen configuratie uit bestanden in `config/`. Hieronder in het kort; elke variabele met zijn standaardwaarde staat in [Configuratie](../componenten/configuratie.md#2-omgevingsvariabelen).

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
| `version.env` | Versienummer voor `make publish` en `make release` (zie [Publicatie van images](#publicatie-van-images)) |

Daarnaast leest de Airflow-container configuratie uit `wasstraat_config/` (gemount als `/opt/airflow/config/`):

| Bestand | Inhoud |
|---------|--------|
| `Wasstraat_Config_HarmonizeV3.xlsx` | Harmonisatie-mapping (veldnamen per objecttype) |
| `correcties.yml` | Gemeente-specifieke datacorrecties en uitzonderingen: brondata- en projectcodecorrecties, `artefact_niet_mergen`, `rapportcode_prefixen`, `paden_overslaan` en `harmonisatie_voorrang` (zie [Configuratie](../componenten/configuratie.md#3-correctiesyml)) |

!!! warning "Gevoelige gegevens"
    De `.env`-bestanden bevatten wachtwoorden en credentials. Neem deze **nooit** op in versiebeheer. Gebruik het `config/`-directory als template en vul per omgeving de juiste waarden in.

    De logs van Airflow en Flask tonen de databaseverbinding zonder wachtwoord (`postgresql://gebruiker:***@postgres/database`). Log je in nieuwe code een verbindings-URI zoals `SQLALCHEMY_DATABASE_URI` of `MONGO_URI`, gebruik dan `maskeerWachtwoord()` uit `shared/logutils.py`.

## Volume-Mounts

### Data-volumes

De Airflow-container koppelt de invoerdata via volumes. Bij `make app` komen die uit `data/synthetic/data/`, bij `make delft` uit `data/delft/data/`:

```
Airflow
./data/<omgeving>/data/projecten          → /input/projecten
./data/<omgeving>/data/projecten          → /input/images             (dezelfde map: foto's staan in de projectmappen)
./data/<omgeving>/data/projectenlijst     → /input/projectenlijst
./data/<omgeving>/data/magazijnlijst      → /input/magazijnlijst
./data/<omgeving>/data/fotolijst          → /input/fotolijst
./data/<omgeving>/data/monsterdatabase    → /input/monsterdatabase
./data/<omgeving>/data/rapporten          → /input/rapporten          (alleen make delft)
./data/<omgeving>/data/referentietabellen → /input/referentietabellen
./data/<omgeving>/output/archeomedia      → /output/archeomedia       (verwerkte media)
./data/<omgeving>/output/rapporten        → /output/rapporten         (verwerkingsrapporten)
./data/<omgeving>/wasstraat_config        → /opt/airflow/config       (harmonisatie-Excel, correcties.yml)

Flask
./data/<omgeving>/output/archeomedia      → /output/archeomedia       (schrijfbaar, voor het kantelen van foto's)

Apache
./data/<omgeving>/output                  → /usr/local/apache2/htdocs (alleen-lezen; gepubliceerd onder /archeomedia)

PostgreSQL en MongoDB
./data/<omgeving>/backup/postgres         → /backup
./data/<omgeving>/backup/mongo            → /backup
```

De paden in de container kun je met omgevingsvariabelen wijzigen (`AIRFLOW_INPUT_*`, `AIRFLOW_OUTPUT_*`); zie [Configuratie: paden en mounts](../componenten/configuratie.md#27-paden-en-mounts).

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

### Broncode in de images

De Dockerfiles kopiëren de code in de images: de Flask-image bevat `app/` en `shared/`, de Airflow-image `airflow_app/dags`, `airflow_app/scripts` en `shared/` (als `/opt/airflow/dags/shared`). De gepubliceerde images draaien daardoor zonder volumes naar broncode. In de ontwikkelomgeving mounten `docker-compose.yml` en `docker-compose.delft.yml` de mappen `airflow_app/dags`, `airflow_app/scripts` en `shared/` over die kopieën heen, zodat wijzigingen direct zichtbaar zijn zonder opnieuw te bouwen. Jupyter is een **ontwikkelvoorziening**: de Jupyter-container krijgt de notebooks en de code via volumes, hoort alleen bij de ontwikkelomgeving en wordt niet gepubliceerd. `.dockerignore` houdt `data/`, `notebooks/`, `docs/` en `deploy/` buiten de buildcontext.

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

## Publicatie van images

De images voor de live installatie staan op de GitHub Container Registry, onder `ghcr.io/brienen/wasstraat-<service>` voor de vier eigen services: `airflow`, `flask`, `postgres` en `apache`. MongoDB, Elasticsearch en Redis komen rechtstreeks van Docker Hub en Elastic. Jupyter is een ontwikkelvoorziening en wordt niet gepubliceerd. Elke image krijgt twee tags: het versienummer en `latest`.

```bash
make publish                      # alle vier images, linux/amd64 + linux/arm64, push naar ghcr.io
make publish SERVICE=flask        # één image
make publish PUSH=0               # alleen lokaal bouwen voor dit platform, niet pushen
make publish NO_CACHE=1           # schone build met verse basisimages
make publish VERSION=1.2.0        # andere versie dan die in config/version.env
```

`make publish` bouwt met `docker buildx` in één keer voor beide platformen en pusht het resultaat als multi-arch image. Daarvoor maakt het eenmalig een builder `wasstraat` aan met de `docker-container`-driver (een gewone `docker build` kan niet voor twee platformen tegelijk bouwen). Met `PUSH=0` gebruikt het de standaardbuilder, bouwt het alleen voor het eigen platform en laadt het de images in de lokale Docker (`--load`); daarmee test je `deploy/` voordat je publiceert. Elke image krijgt de OCI-labels `org.opencontainers.image.source` (de repository, waardoor GitHub het package aan de repository koppelt), `version` en `licenses`.

| Variabele | Standaard | Betekenis |
|-----------|-----------|-----------|
| `VERSION` | `VERSION=` uit `config/version.env`, anders uit `config/version.env.example` | Versietag |
| `SERVICE` | `airflow flask postgres apache` | Te bouwen services |
| `PUSH` | `1` | `0`: alleen lokaal bouwen |
| `PLATFORMS` | `linux/amd64,linux/arm64` | Doelplatformen bij `PUSH=1` |
| `NO_CACHE` | `0` | `1`: `--no-cache --pull` |
| `REGISTRY` | `ghcr.io/brienen` | Registry en naamruimte |
| `BUILDER` | `wasstraat` | Naam van de buildx-builder |

!!! note "Bouwtijd"
    De Airflow-image installeert GDAL en veel Python-pakketten; het bouwen voor het andere platform gebeurt onder emulatie en kan op een laptop een half uur tot een uur duren. Met `SERVICE=` publiceer je alleen wat gewijzigd is.

### Inloggen op de registry

Inloggen gebeurt buiten `make publish` om, eenmalig per machine:

```bash
echo "$GHCR_TOKEN" | docker login ghcr.io -u brienen --password-stdin
```

Het token is een GitHub *personal access token (classic)* met de scope **`write:packages`** (die omvat `read:packages`); `delete:packages` is alleen nodig om oude versies te verwijderen. Fine-grained tokens werken niet voor de Container Registry. Maak het aan onder GitHub → Settings → Developer settings → Personal access tokens.

Na de eerste publicatie zijn de vier packages **privé**. Zet ze op publiek, zodat gemeenten ze zonder inloggen kunnen ophalen: open het package op <https://github.com/brienen?tab=packages>, kies *Package settings* en wijzig onder *Danger Zone* de zichtbaarheid naar *Public*. Controleer daar ook of het package aan de repository is gekoppeld (dat gebeurt automatisch via het label `org.opencontainers.image.source`).

### Een versie uitbrengen

```bash
make release VERSION=1.1.0 MSG="Incrementeel laden en installatie met images"
```

Dit schrijft het versienummer naar `config/version.env.example` (in de repository), `config/version.env` (lokaal, genegeerd door git) en `deploy/.env.example` (de standaardversie voor nieuwe installaties), staget alleen `config/version.env.example` en `deploy/.env.example`, commit die met het bericht uit `MSG`, maakt de geannoteerde git-tag `1.1.0` op die commit, pusht alleen de huidige branch (`git push origin HEAD`) en de nieuwe tag, en roept `make publish` aan. Andere wijzigingen in de werkmap gaan dus niet mee in de releasecommit; commit die vooraf. De map `deploy/` van de tag is daarmee precies wat gebruikers ophalen; `tests/unit/test_deploy.py` bewaakt dat `deploy/.env.example` en `config/version.env.example` dezelfde versie noemen.

Controleer vóór een release dat `make test-all` slaagt en test de images met `make publish PUSH=0` in een installatie uit `deploy/`. Een `latest`-tag wijst altijd naar de laatst gepubliceerde versie; installaties horen een versienummer te gebruiken.
