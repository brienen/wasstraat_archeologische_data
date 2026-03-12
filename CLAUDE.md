# CLAUDE.md — Wasstraat Archeologische Data

## Projectoverzicht

De Wasstraat is een open-source ETL-platform dat archeologische gegevens verzamelt, verwerkt en toegankelijk maakt. Ontwikkeld voor de gemeente Delft: ~1.000 opgravingen, ~100.000 foto's, bijna 1 TB aan data. Het platform draait als Docker Compose-stack met twee hoofdapplicaties (Airflow voor ETL, Flask voor webinterface) en ondersteunende services (PostgreSQL, MongoDB, Elasticsearch, Redis).

## Projectstructuur

```
airflow_app/dags/          # Airflow DAG-definities en transformatielogica
airflow_app/dags/wasstraat/ # Kernmodules: harmonizer, archutils, merge_functions
airflow_app/scripts/       # Shell-scripts voor data-import
app/app/                   # Flask webapp: models.py, views, API, templates
app/fab_addon_geoalchemy/  # Custom GeoAlchemy-extensie voor geodata
shared/                    # Gedeelde modules: config.py, const.py, database.py
tests/unit/                # Unit tests (pytest)
tests/integration/         # Integratietests (Docker-based)
docs/                      # MkDocs documentatie (Nederlands)
config/                    # Environment-bestanden (.env, gegenereerd door init-config.sh)
services/                  # Dockerfiles per service
data/input/basefiles/      # Bronbestanden (.mdb Access-databases)
notebooks/                 # Jupyter notebooks voor analyse
```

## Technische stack

- **Orchestratie:** Apache Airflow 2.3.3
- **Backend:** Python 3.10, Flask, Flask-AppBuilder
- **Databases:** PostgreSQL (definitieve opslag), MongoDB 4.2 (staging), Elasticsearch 8.6 (zoekindex)
- **Caching:** Redis
- **Infrastructuur:** Docker Compose (dev/test/acc/prod)
- **Analyse:** Jupyter Lab, Pandas, GeoPandas

## ETL-pipeline (Airflow)

De verwerkingsvolgorde is strikt:
1. Drop All Databases (schone start)
2. Extract — Lees brondata in (Access-databases, bestanden)
3. Transform1 Harmonize — Harmoniseer veldnamen over alle bronnen
4. Transform2 Enhance Attributes — Normaliseer inhoud (datums, codes, metadata)
5. Transform3 Set Keys — Genereer unieke sleutels per entiteit
6. Transform4 Move and Merge — Voeg dubbele entiteiten samen (polymorfisme)
7. Transform5 Set References — Ken integer-sleutels toe voor PostgreSQL
8. Load to Database & Index — Kopieer naar PostgreSQL + bouw Elasticsearch-index

DAG-bestanden volgen het patroon `DAG_[Naam].py`, taken `tasks_[actie]_[onderwerp].py`.

## Codeerstijl en conventies

- **Taal:** Docstrings, comments en documentatie zijn in het Nederlands
- **Functies:** camelCase (bestaande conventie, bijv. `convertToInt`, `fixDatering`)
- **Constanten:** UPPER_SNAKE_CASE (bijv. `COLL_STAGING_VONDST`, `DB_STAGING`)
- **Bestanden:** snake_case met beschrijvende namen
- **Geen type hints** in bestaande code — volg deze conventie bij wijzigingen
- **Docstrings:** Drievoudige aanhalingstekens, Nederlands, met Args/Returns secties
- **Imports:** standaardbibliotheek, dan third-party, dan lokale modules
- **Logging:** Gebruik `logger.info()` en `logger.error()` (Airflow logger)

## Commando's

```bash
# Ontwikkelen
make install          # Maak .venv aan met test-dependencies
make dev              # Start development-omgeving (hot-reload)
make app              # Start alle services

# Testen
make test             # Unit tests (tests/unit/)
make integration      # Integratietests (start/stopt Docker automatisch)
make test-all         # Unit + integratietests

# Documentatie
make docs             # MkDocs dev-server op localhost:8000
make docs-build       # Bouw statische site

# Onderhoud
make backup           # Backup PostgreSQL + MongoDB
make restore TS=...   # Restore vanuit timestamp
make export           # Exporteer tabellen als CSV
make stop / start     # Containers stoppen/starten
make clean            # Verwijder .venv en caches
```

## Testconventies

- **Framework:** pytest met markers `@pytest.mark.unit` en `@pytest.mark.integration`
- **Structuur:** Testklassen per functiegroep (`TestConvertToInt`, `TestFixDatering`)
- **Naamgeving:** `test_[scenario]` (bijv. `test_single_year`, `test_invalid_date_force_returns_nat`)
- **Parametrized tests:** Gebruik `@pytest.mark.parametrize` voor meerdere inputs
- **Fixtures:** `conftest.py` mockt externe dependencies (MongoDB URI, config, etc.)
- **Draai altijd `make test` na wijzigingen** om regressies te vangen

## Datamodel (kernentiteiten)

**Basis:** Project → Vindplaats → Put → Vlak → Spoor → Vulling → Vondst → Artefact
**Depot:** Stelling → Standplaats → Plaatsing → Doos
**Bestanden:** Foto, Tekening, Rapport (met metadata-extractie)
**Artefacttypen:** Aardewerk, Glas, Metaal, Hout, Steen, Leer, Dierlijk Bot, Menselijk Bot, Kleipijp, Bouwaardewerk, Munt, Schelp, Textiel
**Standaarden:** ABR-thesaurus, GGM, CIDOC CRM, DANS e-Depot, Archis

## Git-workflow

- Werk altijd in de huidige branch. Maak GEEN nieuwe branches aan.
- Maak geen commits zonder expliciete toestemming.
- Commit-messages in het Nederlands, beschrijvend (bijv. "Verbeter error handling in transform2").

## Belangrijke aandachtspunten

- `app/app/models.py` (62 KB) bevat 100+ SQLAlchemy-modellen — wees voorzichtig met wijzigingen
- De custom `fab_addon_geoalchemy/` extensie is project-specifiek
- `shared/config.py` leest environment-variabelen — wijzig nooit `.env` bestanden direct
- `shared/const.py` bevat alle constanten en enums voor het hele project
- De Airflow DAGs hebben een strikte verwerkingsvolgorde — verander deze niet zonder overleg
- Documentatie staat in `docs/` als MkDocs Markdown — houd deze synchroon met codewijzigingen
