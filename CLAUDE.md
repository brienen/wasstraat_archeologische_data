# CLAUDE.md — Wasstraat Archeologische Data

## Projectoverzicht

De Wasstraat is een open-source ETL-platform dat archeologische gegevens verzamelt, verwerkt en toegankelijk maakt. Ontwikkeld voor de gemeente Delft: ~1.000 opgravingen, ~100.000 foto's, bijna 1 TB aan data. Het platform draait als Docker Compose-stack met twee hoofdapplicaties (Airflow voor ETL, Flask voor webinterface) en ondersteunende services (PostgreSQL, MongoDB, Elasticsearch, Redis).

## Projectstructuur

```
airflow_app/dags/          # Airflow DAG-definities en transformatielogica
airflow_app/dags/wasstraat/ # Kernmodules: harmonizer, archutils, merge_functions
airflow_app/dags/wasstraat/profielen/ # Gemeenteprofielen: conventie, delft, voorbeeld
airflow_app/scripts/       # Shell-scripts voor data-import
app/app/                   # Flask webapp: models.py, views, API, templates
app/fab_addon_geoalchemy/  # Custom GeoAlchemy-extensie voor geodata
shared/                    # Gedeelde modules: config.py, const.py, database.py
tests/unit/                # Unit tests (pytest)
tests/integration/         # Integratietests (Docker-based)
docs/                      # MkDocs documentatie (Nederlands)
config/                    # Environment-bestanden (.env, gegenereerd door init-config.sh)
services/                  # Dockerfiles per service
data/delft/data/           # Delftse bronbestanden (.mdb Access-databases, niet in repo)
data/delft/output/         # Verwerkte Delftse data (niet in repo)
data/delft/wasstraat_config/ # Harmonisatie-configuratie + correcties.yml voor Delft
data/delft/backup/         # Backups Postgres + MongoDB (niet in repo)
data/synthetic/data/       # Synthetische voorbeelddata (MDB-bestanden, in repo)
data/synthetic/generatie/  # Generator-script voor synthetische data
data/test/                 # Testdata voor Delft-subtests
notebooks/                 # Jupyter notebooks voor analyse
```

## Technische stack

- **Orchestratie:** Apache Airflow 2.10.5
- **Backend:** Python 3.11, Flask, Flask-AppBuilder
- **Databases:** PostgreSQL 18 met PostGIS 3.6 (definitieve opslag), MongoDB 7.0 (staging), Elasticsearch 8.17 (zoekindex)
- **Caching:** Redis
- **Infrastructuur:** Docker Compose (dev/test/acc/prod)
- **Analyse:** Jupyter Lab, Pandas, GeoPandas

## ETL-pipeline (Airflow)

De verwerkingsvolgorde is strikt:
1. Drop All Databases (schone start)
2. Extract — Lees brondata in (Access-databases, bestanden)
3. Transform1 Harmonize — Harmoniseer veldnamen over alle bronnen + brondata-correcties uit correcties.yml
4. Transform2 Enhance Attributes — Normaliseer inhoud (datums, codes, metadata) + projectcode-correcties uit correcties.yml
5. Transform3 Set Keys — Genereer unieke sleutels per entiteit
6. Transform4 Move and Merge — Voeg dubbele entiteiten samen (polymorfisme)
7. Transform5 Set References — Ken integer-sleutels toe voor PostgreSQL
8. Load to Database & Index — Kopieer naar PostgreSQL + bouw Elasticsearch-index

Dit is de volledige cyclus (`Extract_Transform_Load_Full_Cycle`). Daarnaast is er de **incrementele cyclus** (`Extract_Transform_Load_Incremental`, issue 61): die verwerkt alleen nieuwe, gewijzigde en verwijderde bronbestanden en leegt niets. Volgorde: `Start_Run` → `Bepaal_Delta` (vergelijkt met de registratie in `Def_Bronbestand`) → `Opruimen_Oude_Records` → Extract (delta) → Transform 1 → 2 → 3 → 5 → 4 (delta, stabiele `primary_key`s) → `Load_Upsert` (upsert naar PostgreSQL) → `Registreer_Run`, en na `Load_Upsert` parallel de `Index_<tabel>`-taken (Elasticsearch-delta). De taken lezen het run-document (`wasstraat/verwerkingsrun.py`, collectie `Verwerkingsruns`) in plaats van XCom; `Markeer_Run_Mislukt` zet de run op `mislukt` als een bewaakte taak faalt (de Index-taken zijn bewust niet bewaakt). Eerst één keer de volledige cyclus draaien (die registreert alle bronbestanden); de volledige cyclus blijft nodig na wijzigingen in de harmonisatie-Excel, `correcties.yml` of de pipelinecode. Ontwerp en keuzes: [docs/componenten/incrementeel-laden.md](docs/componenten/incrementeel-laden.md).

DAG-bestanden volgen het patroon `DAG_[Naam].py`, taken `tasks_[actie]_[onderwerp].py`.

## Gemeenteprofielen

Het profielensysteem centraliseert alle gemeente-specifieke logica in één plek. Het actieve profiel wordt geselecteerd via de omgevingsvariabele `WASSTRAAT_GEMEENTE` (default: `delft`).

```
airflow_app/dags/wasstraat/profielen/
├── __init__.py       # get_profiel() + reset_profiel() — gecachede factory
├── conventie.py      # ConventieProfiel: basisprofiel, directe velden
├── delft.py          # DelftProfiel: Delft-specifieke normalisatie + bestandsparsing
└── voorbeeld.py      # VoorbeeldProfiel: PoC, erft ConventieProfiel ongewijzigd
```

**Twee typen methoden:**

- **Type A — database-entiteiten** (`identificeer(soort, doc)` dispatcher → `identificeer_put/vlak/spoor/vondst/artefact/...`): normaliseer projectcd, converteer identificerende integers.
- **Type B — bestands-entiteiten** (`identificeer_foto(doc, projectcd)`, `identificeer_tekening(doc, projectcd)`): parse bestandsnaam naar velden. Standaard retourneert `None`; DelftProfiel implementeert regex-parsing.

**Aanroep in de pipeline:**
- `parseFotobestanden()` — `identificeer_foto()` / `identificeer_tekening()` voor bestandsnaam-parsing
- `enhanceAllAttributes()` — `identificeer(soort, doc)` voor database-entiteiten; `identificeer_tekening_db()` / `identificeer_rapport_db()` voor Tekening/Rapport

**Tests:** `tests/unit/test_profielen.py` — profielselectie, caching, ConventieProfiel, DelftProfiel, VoorbeeldProfiel.

Zie [docs/componenten/gemeenteprofielen.md](docs/componenten/gemeenteprofielen.md) voor volledige documentatie.

## Gemeente-specifieke correcties (correcties.yml)

Per omgeving (delft, synthetic, test) kan een `correcties.yml` in `wasstraat_config/` staan. Dit bestand bevat datacorrecties die de pipeline toepast zonder dat de code aangepast hoeft te worden.

**Twee secties:**

- **`projectcode_correcties`** — eenvoudige regex→projectcode vervangingen, toegepast op het `projectcd` veld in Single_Store na harmonisatie (Transform2). Geen collectie of veldnaam nodig.
- **`brondata_correcties`** — correcties op raw velden in staging-collecties vóór harmonisatie (Transform1). Nodig als brondata afwijkende codes bevat die niet matchen met de projectenlijst. Vereist `collectie`, `zoek_veld`, `patroon` en `waarde`.

Overige secties: `artefact_niet_mergen`, `rapportcode_prefixen`.

**Pad:** `shared/config.py` → `AIRFLOW_CORRECTIES_CONFIG` (default `/opt/airflow/config/correcties.yml`).
**Laden:** `wasstraat/harmonize_functions.py` → `laadCorrecties()` (cached, robuust bij foute YAML).
**Tests:** `tests/unit/test_correcties_yml.py` — 27 tests inclusief foutscenario's.

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
make app              # Start alle services (synthetische data)
make delft            # Start alle services met eigen data uit data/delft/

# Testen
make test             # Unit tests (tests/unit/)
make integration      # Volledige suite: Extract → Transform → Load → Flask smoke tests
make integration-pipeline # Alleen Extract + Transform (zonder Load en Flask)
make integration-load # Extract + Transform + Load (zonder Flask)
make integration-delft # Integratietests met Delftse data (indien aanwezig)
make test-flask       # Alleen Flask smoke tests (vereist geladen PostgreSQL)
make test-all         # Unit tests + volledige integratie (= make test + make integration)

# Synthetische data
make synthetic        # Genereer synthetische MDB-bestanden opnieuw

# Documentatie
make docs             # MkDocs dev-server op localhost:8000
make docs-build       # Bouw statische site

# Onderhoud
make backup           # Backup PostgreSQL + MongoDB
make restore TS=...   # Restore vanuit timestamp
make export           # Exporteer tabellen als CSV
make stop / start     # Containers stoppen/starten
make constraints      # Leg pakketversies Flask/Jupyter opnieuw vast (daarna make test-all)
make migrate-postgres-data # Eenmalig: PostgreSQL-data van oude installatie naar het volume
make clean            # Verwijder .venv en caches
```

## Testconventies

- **Framework:** pytest met markers `@pytest.mark.unit`, `@pytest.mark.integration` en `@pytest.mark.delft`
- **Structuur:** Testklassen per functiegroep (`TestConvertToInt`, `TestFixDatering`)
- **Naamgeving:** `test_[scenario]` (bijv. `test_single_year`, `test_invalid_date_force_returns_nat`)
- **Parametrized tests:** Gebruik `@pytest.mark.parametrize` voor meerdere inputs
- **Fixtures:** `conftest.py` mockt externe dependencies (MongoDB URI, config, etc.)
- **Draai altijd `make test-all` na wijzigingen** om regressies te vangen

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

## Load naar PostgreSQL (loadToDatabase_functions.py)

De Load-stap (`loadToDatabase_functions.py`) is herschreven zonder pandas en zonder SQLAlchemy.

### Probleem

Airflow 2.10 pint SQLAlchemy < 2.0 voor interne compatibiliteit. pandas >= 2.2 vereist SQLAlchemy >= 2.0. Deze combinatie maakte `DataFrame.to_sql()` onbruikbaar — elke variant (Engine, Connection, DBAPI, URI string) faalde op een andere manier. Het pinnen van pandas < 2.2 in `requirements.txt` werd niet altijd correct overgenomen door de Docker-build, waardoor de incompatibiliteit bleef optreden.

### Gekozen oplossing

Volledige herschrijving met alleen **pymongo** + **psycopg2** + **pure Python**:

- `psycopg2.extras.execute_values()` voor batch inserts (vervangt `df.to_sql()`)
- `information_schema.columns` en `pg_type` queries voor tabelmetadata (vervangt `sqlalchemy.inspect()`)
- `ST_SetSRID(ST_MakePoint(lon, lat), 4326)` via UPDATE SQL voor geometry (vervangt GeoAlchemy2/Shapely)
- Pure Python type-conversie: `convertToInt()`, `convertToFloat()`, `convertToDatePure()` (vervangt pandas type coercion)
- `bool()` wrapper rond `convertToBool()` — psycopg2 vereist Python `True`/`False`, niet `0`/`1`

### Architectuur bewaard

De 3-fase atomic swap is ongewijzigd: (1) laad naar `_new` tabellen, (2a) atomic rename swap met FK drop/restore, (2b) FK herstel met SAVEPOINTs, (3) opruimen `_old` tabellen. De publieke interface `loadAll()` is ongewijzigd — DAGs en tasks hoefden niet aangepast te worden. De FK-mechaniek staat in herbruikbare helpers (`leesFkConstraints`, `verwijderFkConstraints`, `herstelFkConstraints`, `valideerFkConstraints`) die ook de incrementele load gebruikt.

### Incrementele load (upsert)

`loadIncrementeel()` (taak `Load_Upsert` van de incrementele cyclus) werkt de bestaande tabellen bij in plaats van ze te vervangen, in één transactie: betrokken FK's verwijderen, per tabel uit `LOAD_TABELLEN` een `INSERT ... ON CONFLICT (primary_key) DO UPDATE` van alle documenten (inclusief `_id`; alleen echte wijzigingen worden geschreven), rijen verwijderen waarvan de `primary_key` niet meer in `Single_Store_Clean` staat, geometrie bijwerken, sequence van `primary_key` op max + 1 (en opnieuw aanmaken als de atomic swap hem kwijt is), FK's herstellen met `NOT VALID`, commit, valideren. `SET CONSTRAINTS ALL DEFERRED` werkt niet: niet alle FK's zijn deferrable. Gebruikerstabellen (`GEBRUIKERS_TABELLEN`: bruiklenen, partijen, conservering, `Def_artefact_abr`) en `Def_Bronbestand` blijven ongemoeid. Tellingen per tabel komen in het run-document onder `tellingen.load`. De rijen worden opgebouwd met dezelfde helpers als `transferToDB` (`leesDocumenten`, `transformRow`); artefacten zonder `key` krijgen daarbij in beide cycli de samengestelde sleutel `key_subnr|artefactsoort` in de kolom `key`.

### Aandachtspunten bij wijzigingen

- `archutils.convertToBool()` retourneert `0`/`1` (integers) — wrap altijd met `bool()` voor psycopg2
- Geometry kolom `location` wordt NIET meegegeven in de INSERT maar via een aparte UPDATE bijgewerkt
- ENUM kolommen worden gedetecteerd via `pg_type.typtype = 'e'` — lege waarden worden `'Onbekend'`
- De testomgeving heeft een eigen Elasticsearch (`elasticsearch-test`, container `wasstraat_elasticsearch_test`, zonder hostpoort want 9200 is van de echte installatie); de Index_*-taken van de volledige cyclus, `DAG_Load_Only` en de incrementele cyclus slagen daar dus ook

## Integratietests en volgorde

`make integration` draait de volledige testsuite in twee stappen binnen één Docker-sessie:

1. **Stap 1:** Extract → Transform → Load pipeline (marker: `integration or load`), als laatste `test_incremental_synthetic_data.py`: volledige cyclus plus vier incrementele runs met een tijdelijk project SY003 (de fixture ruimt `data/synthetic/data/projecten/SY003` altijd op)
2. **Stap 2:** Flask smoke tests (marker: `flask_smoke`) — vereist geladen PostgreSQL-data uit stap 1

De Flask smoke tests controleren of projecten zichtbaar zijn op de kaart en hebben daarom gevulde `Def_Project` data nodig. Draai `make integration` voor de volledige suite, of `make integration-pipeline` voor alleen Extract + Transform zonder Load.

## Belangrijke aandachtspunten

- `app/app/models.py` (62 KB) bevat 100+ SQLAlchemy-modellen — wees voorzichtig met wijzigingen
- De custom `fab_addon_geoalchemy/` extensie is project-specifiek
- `shared/config.py` leest environment-variabelen — wijzig nooit `.env` bestanden direct
- `shared/const.py` bevat alle constanten en enums voor het hele project
- De Airflow DAGs hebben een strikte verwerkingsvolgorde — verander deze niet zonder overleg
- Documentatie staat in `docs/` als MkDocs Markdown — houd deze synchroon met codewijzigingen
- Omgevingsvariabelen zijn altijd tekst. Zet numerieke instellingen in `shared/config.py` om met `int()`; cachelib >= 0.14 weigert bijvoorbeeld een tekst als cache-timeout en dan start Flask niet
- `PGDATA` en het PostgreSQL-volume moeten hetzelfde pad hebben (`/data/postgres`). Installaties van vóór oktober 2026 hebben hun data in de container; die migreer je met `make migrate-postgres-data` vóór de eerste `make app`
- De Flask-app maakt bij het opstarten de PostgreSQL-tabellen aan (`db.create_all()`). De Load-stap faalt als Flask niet draait
- `make integration` hergebruikt bestaande images. Bouw de test-images opnieuw na wijzigingen in Dockerfiles, requirements of `shared/`, anders test je oude code en oude afhankelijkheden
