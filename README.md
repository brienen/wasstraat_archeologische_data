# Wasstraat Archeologische Data

[![License: EUPL-1.2](https://img.shields.io/badge/License-EUPL--1.2-yellow.svg)](https://joinup.ec.europa.eu/collection/eupl/eupl-text-eupl-12)
[![Version](https://img.shields.io/badge/version-1.0.1-blue.svg)](https://github.com/brienen/wasstraat_archeologische_data/releases)
[![Python](https://img.shields.io/badge/python-3.11-3776ab.svg)](https://www.python.org/)
[![Docker](https://img.shields.io/badge/docker-compose-2496ed.svg)](https://docs.docker.com/compose/)

> Een open-source platform dat archeologische gegevens verzamelt, verwerkt en toegankelijk maakt — van ruwe data naar gestructureerd inzicht.

[![Wasstraat Overzicht](image/wasstraat-overzicht.jpeg)](image/wasstraat-overzicht.jpeg)

## Over het project

De Wasstraat functioneert als een digitale wasstraat voor archeologische data. Verspreide bronbestanden — Access-databases, Excel-sheets, foto's, rapporten en GIS-bestanden — worden geautomatiseerd ingelezen, opgeschoond, gekoppeld en gestructureerd opgeslagen.

Ontwikkeld voor de **gemeente Delft**, waar meer dan 1.000 opgravingen met tienduizenden foto's, vondstlijsten en rapporten (bijna 1 Terabyte aan data) zijn gedigitaliseerd.

## Documentatie 

Zie de [volledige documentatie](https://brienen.github.io/wasstraat_archeologische_data/) voor het uitgeklapte procesmodel en gedetailleerde uitleg per stap.

## Architectuur

Het platform bestaat uit twee hoofdapplicaties die als Docker-containers draaien:

| Applicatie | Doel | Poort |
|------------|------|-------|
| **Airflow** (`airflow_app/`) | Data verwerken (ETL-pipeline) | :8080 |
| **Flask App** (`app/`) | Data inzichtelijk maken (web-interface) | :5052 (via Apache) |

Daarnaast draaien de volgende ondersteunende services:

| Service | Rol | Poort |
|---------|-----|-------|
| **PostgreSQL** | Definitieve relationele opslag | :5432 |
| **MongoDB** | Ruwe opslag en staging | :27017 |
| **Elasticsearch** | Fulltext-zoekindex | :9200 |
| **Redis** | Caching | :6379 |
| **Apache** | Voordeur: stuurt de webapplicatie door naar Flask en serveert de foto's (`/archeomedia`) | :5052 |
| **Jupyter** | Data-analyse notebooks | :8888 |

Apache is de voordeur van de webapplicatie: de browser praat alleen met poort 5052. Apache serveert de verwerkte foto's en documenten onder `/archeomedia` rechtstreeks uit de uitvoermap en stuurt alle overige verzoeken door naar Flask (reverse proxy). Flask zelf heeft geen hostpoort.

## Verwerken van archeologische data

Het verwerken van alle archeologische data is uitgewerkt in procesmodellen in [Apache Airflow](https://airflow.apache.org). Het hoofdproces kent de volgende stappen:

[![Hoofdprocessen Verwerken Data](image/Airflow_Hoofdprocessen.png)](image/Airflow_Hoofdprocessen.png)

1. **Drop All Databases** — Schoon alle data zodat gestart kan worden met verse databases.
2. **Extract** — Lees alle data uit externe bronnen in, as-is zonder transformatie. Voor Archeologie Delft zijn dat ongeveer 1.000 databases, ~100.000 foto's en enkele duizenden rapporten — in totaal bijna 1 TB aan data.
3. **Transform1 Harmonize** — Harmoniseer de veldnamen van alle ingelezen data over alle bronnen heen.
4. **Transform2 Enhance Attributes** — Maak de inhoud van alle velden consistent. Datumformaten, codes, projectnummers en metadata worden genormaliseerd.
5. **Transform3 Set Keys** — Genereer unieke sleutels en verwijzende sleutels voor alle entiteiten.
6. **Transform4 Move and Merge** — Voeg dubbele entiteiten samen met behoud van [polymorfisme](https://nl.wikipedia.org/wiki/Polymorfisme_(informatica)). Artefacten en Bestanden kunnen zo verschillende soorten hebben met eigen attributen.
7. **Transform5 Set References** — Ken integer-sleutels toe voor gebruik in de relationele database.
8. **Load to Database & Index** — Kopieer data naar PostgreSQL en bouw de Elasticsearch-zoekindex op.

## Ondersteunde data

| Categorie | Entiteiten |
|-----------|-----------|
| **Basisgegevens** | Project, Vindplaats, Vondst, Put, Vlak, Spoor, Vulling, Artefact, Monster, Bestand |
| **Depotgegevens** | Stelling, Standplaats, Plaatsing, Doos |
| **Bestanden** | Foto's, Tekeningen, Rapporten — elk met automatische metadata-extractie |
| **Artefacten** | Aardewerk, Glas, Metaal, Hout, Steen, Leer, Dierlijk Bot, Menselijk Bot, Kleipijp, Bouwaardewerk, Munt, Schelp, Textiel |
| **Standaarden** | [ABR](https://thesaurus.cultureelerfgoed.nl/search;schemes=abr:b6df7840-67bf-48bd-aa56-7ee39435d2ed), GGM, CIDOC CRM, DANS e-Depot, Archis |

Elke artefactcategorie kent eigen specifieke velden:

| | |
|---|---|
| [![Artefact Aardewerk](image/Attributen_Aardewerk.png)](image/Attributen_Aardewerk.png) | [![Artefact Glas](image/Attributen_Glas.png)](image/Attributen_Glas.png) |

## Snel starten

Er zijn twee manieren om de Wasstraat te draaien:

- **Installeren voor gebruik**, zonder te bouwen: de gepubliceerde images van `ghcr.io/brienen` met de map [`deploy/`](deploy/). Volg [Installatie met images](https://brienen.github.io/wasstraat_archeologische_data/deployment/installatie-met-images/). Dit is de route voor gemeenten.
- **De ontwikkelomgeving**: deze repository clonen en de images zelf bouwen, zoals hieronder. Hier draai je ook de tests en publiceer je nieuwe versies (`make publish`).

### Vereisten

- [Docker](https://www.docker.com/) en Docker Compose
- [GNU Make](https://www.gnu.org/software/make/) en bash. Op Linux installeer je Make zo nodig via de pakketbeheerder, bijvoorbeeld `sudo apt install make`. Op macOS komt Make mee met de Xcode Command Line Tools (`xcode-select --install`). Na een Xcode-update moet je eenmalig de licentie accepteren met `sudo xcodebuild -license`, anders weigert `make` te starten.
- Op Windows gebruik je [WSL 2](https://learn.microsoft.com/windows/wsl/) met Docker Desktop, omdat de scripts bash en Make nodig hebben. Voer alle commando's uit in de Linux-shell van WSL.
- Minimaal 8 GB RAM beschikbaar voor Docker, 12 GB aanbevolen
- Alleen voor de tests: Python 3.10, 3.11 of 3.12

### Installatie

```bash
# Clone de repository
git clone https://github.com/brienen/wasstraat_archeologische_data.git
cd wasstraat_archeologische_data

# Start de wasstraat
# (config/*.env bestanden worden automatisch gegenereerd met unieke wachtwoorden)
make app
```

> **Tip:** Bij de eerste start genereert `init-config.sh` automatisch alle `config/*.env` bestanden met unieke wachtwoorden. Om handmatig opnieuw te genereren: `./init-config.sh --force`

Typ `make help` voor een overzicht van alle beschikbare commando's.

### Inloggen

| Applicatie | Adres | Inloggegevens |
|------------|-------|---------------|
| Airflow | http://localhost:8080 | `admin`, wachtwoord in `config/airflow.env` (`SECURITY__ADMIN_PASSWORD`) |
| Flask App | http://localhost:5052 | `admin`, wachtwoord in `config/flask.env` (`FLASK_ADMIN_PASSWORD`) |
| Jupyter Lab | http://localhost:8888 | token in `config/jupyter.env` (`JUPYTER_PASSWORD`) |

Het Flask-wachtwoord uit `config/flask.env` wordt alleen gebruikt als de beheerder nog niet bestaat; een bestaande beheerder houdt zijn wachtwoord. Ontbreekt `FLASK_ADMIN_PASSWORD` (installaties van vóór oktober 2026), dan krijgt een nieuwe beheerder het wachtwoord `admin` en staat er een waarschuwing in de log. Wijzig het in dat geval direct via het gebruikersmenu.

### Bestaande installatie bijwerken

Installaties van vóór oktober 2026 hebben hun PostgreSQL-data in de container staan in plaats van in het Docker-volume. Draai bij zo'n installatie eerst `make backup`, dan `make stop` en `make migrate-postgres-data`, en pas daarna `make app` of `make delft`. Zie [Omgevingen](https://brienen.github.io/wasstraat_archeologische_data/deployment/omgevingen/) voor de achtergrond.

### Omgevingen starten

```bash
make app          # Alle services, met de synthetische voorbeelddata
make delft        # Alle services, met eigen data uit data/delft/
make dev          # Ontwikkelomgeving (met hot-reload volumes)
make stop         # Stop alle containers
make start        # Herstart gestopte containers
make logs         # Toon live logs
make ps           # Toon status van alle services
```

### Eerste data verwerken

De repo bevat **synthetische voorbeelddata** in `data/synthetic/data/` — twee fictieve opgravingsprojecten (SY001 en SY002) waarmee je de volledige pipeline kunt testen zonder eigen brondata. Dit is het startpunt om het platform te leren kennen.

**Eigen data gebruiken?** Zet je bronbestanden in `data/delft/data/` en je configuratie in `data/delft/wasstraat_config/`, en start met `make delft`. De naam `delft` is historisch: het bestand `docker-compose.delft.yml` leest gewoon uit die mappen. Wil je een eigen omgevingsnaam, kopieer dan dat bestand en pas de paden aan. De bronbestanden volgen deze structuur:

| Directory | Inhoud | Formaat |
|-----------|--------|---------|
| `projecten/` | Per opgraving een subdirectory met projectdatabase + foto's | `.mdb` / `.accdb` |
| `projectenlijst/` | Projectoverzicht (tabel `OPGRAVINGEN`: code, locatie, jaar) | `.mdb` |
| `magazijnlijst/` | Depotadministratie (tabel `magazijnlijst`: stellingen, dozen) | `.mdb` |
| `fotolijst/` | Fotocatalogus (tabel `Fotos`: koppeling foto ↔ vondst) | `.mdb` |
| `monsterdatabase/` | Grondmonsters met botanische/zoölogische determinaties | `.mdb` |
| `referentietabellen/` | ABR-thesaurus (`abr_versie_*.xlsx`) | `.xlsx` |
| `rapporten/` | Rapportbestanden en rapportendatabases | `.mdb` / `.pdf` |

De Wasstraat doorzoekt elke directory recursief op `.mdb`/`.accdb` bestanden. In `projecten/` bepaalt de directorynaam de projectcode. Zie `data/synthetic/data/` als werkend voorbeeld en de [documentatie](https://brienen.github.io/wasstraat_archeologische_data/aan-de-slag/) voor details.

1. Open Airflow UI op [http://localhost:8080](http://localhost:8080)
2. Start de DAG **`Extract_Transform_Load_Full_Cycle`**
3. Bekijk het resultaat in de Flask App op [http://localhost:5052](http://localhost:5052)

### Backup en restore

```bash
make backup                              # Backup PostgreSQL + MongoDB
make restore TS=2024-03-15_14-30-00      # Restore vanuit timestamp
make export                              # Exporteer alle tabellen als CSV
```

### Testen

```bash
make install          # Eenmalig: maakt .venv aan met test-dependencies
make test             # Draai unit tests
make integration      # Integratietests met synthetische data
make integration-delft # Integratietests met Delftse data (indien aanwezig)
make test-all         # Unit + integratietests
```

### Publiceren

```bash
make publish                      # Bouw alle images voor linux/amd64 en linux/arm64 en push naar ghcr.io/brienen
make publish SERVICE=flask        # Eén image
make publish PUSH=0               # Alleen lokaal bouwen, om deploy/ te testen
make release VERSION=1.2.3 MSG="Release notes"   # Versie vastleggen, taggen, pushen en publiceren
```

Inloggen op de registry gebeurt vooraf met `docker login ghcr.io`. Zie [Omgevingen](https://brienen.github.io/wasstraat_archeologische_data/deployment/omgevingen/#publicatie-van-images).

## Projectstructuur

```
wasstraat_archeologische_data/
├── airflow_app/          # Airflow ETL-applicatie
│   ├── dags/             # DAG-definities en transformatielogica
│   └── scripts/          # Shell-scripts voor data-import
├── app/                  # Flask web-applicatie
│   └── app/              # Models, views, API, templates
├── shared/               # Gedeelde modules (config, database, constanten)
├── config/               # Environment-bestanden (.env)
├── deploy/               # Live installatie uit gepubliceerde images (zonder broncode)
├── services/             # Dockerfiles per service
├── data/                 # Input- en outputdata
│   ├── delft/            # Eigen data voor 'make delft' (inhoud niet in repo)
│   ├── synthetic/        # Synthetische voorbeelddata (in repo)
│   └── test/             # Configuratie voor de Delftse integratietests
├── tests/                # Unit- en integratietests
├── notebooks/            # Jupyter notebooks voor analyse
├── docs/                 # MkDocs documentatie
├── image/                # Afbeeldingen voor README
├── Makefile              # Alle commando's (make help)
├── docker-compose.yml          # Alle services met synthetische data (make app)
├── docker-compose.delft.yml    # Alle services met eigen data (make delft)
├── docker-compose.develop.yml  # Development overrides (make dev)
├── docker-compose.test.yml     # Testomgeving met synthetische data (make integration)
└── docker-compose.delft-test.yml # Testomgeving met Delftse testdata (make integration-delft)
```

## Documentatie

De volledige technische documentatie is beschikbaar als [MkDocs-site](https://brienen.github.io/wasstraat_archeologische_data/):

```bash
make docs       # Start MkDocs dev-server op localhost:8000
make docs-build # Bouw statische site
```

De documentatie bevat:

- **Projectoverzicht** — Inleiding, probleemstelling en doelstellingen
- **Aan de slag** — Stap-voor-stap handleiding voor eerste gebruik
- **Architectuur** — Systeemarchitectuur, dataflow, componentenmodel, gegevensmodel en stack
- **Componenten** — Extractie, SingleStore, Transformatie, Crossviews, Validatie, Configuratie, Zoeken
- **Deployment** — Installatie met images, omgevingen, Airflow vs. App, proefdata inlezen
- **Testen** — Unit tests, integratietests en testinfrastructuur
- **Diagrammen** — draw.io architectuurdiagrammen

## Technische stack

| Categorie | Technologieën |
|-----------|---------------|
| **Orchestratie** | Apache Airflow 2.10.5 |
| **Backend** | Python 3.11, Flask, Flask-AppBuilder |
| **Databases** | MongoDB 7.0, PostgreSQL 18 met PostGIS 3.6, Elasticsearch 8.17 |
| **Caching** | Redis 7.2 |
| **Infrastructuur** | Docker Compose |
| **Analyse** | Jupyter Lab, Pandas, GeoPandas |
| **Data-import** | mdbtools, Pillow, pdf2image |

## Bijdragen

Bijdragen zijn welkom! Het project is open-source onder de EUPL-licentie.

1. Fork de repository
2. Maak een feature-branch (`git checkout -b feature/mijn-verbetering`)
3. Commit je wijzigingen (`git commit -m 'Voeg verbetering toe'`)
4. Push naar de branch (`git push origin feature/mijn-verbetering`)
5. Open een Pull Request

Bij vragen of suggesties, open een [issue](https://github.com/brienen/wasstraat_archeologische_data/issues).

## Licentie

Dit project is uitgegeven onder de [EUPL-1.2 licentie](https://joinup.ec.europa.eu/collection/eupl/eupl-text-eupl-12).

## Contact

Ontwikkeld door **E-Space** (Arjen Brienen) in opdracht van de gemeente Delft.
Het project wordt uitgebreid tot een generiek systeem voor andere Nederlandse gemeenten via Stichting Reuvens.
