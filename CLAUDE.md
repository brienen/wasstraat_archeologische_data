# CLAUDE.md — Wasstraat Archeologische Data

## Projectoverzicht

De Wasstraat is een open-source ETL-platform dat archeologische gegevens verzamelt, verwerkt en toegankelijk maakt. Ontwikkeld voor de gemeente Delft: ~1.000 opgravingen, ~100.000 foto's, bijna 1 TB aan data. Het platform draait als Docker Compose-stack met twee hoofdapplicaties (Airflow voor ETL, Flask voor webinterface) en ondersteunende services (PostgreSQL, MongoDB, Elasticsearch, Redis).

## Eisenpakket en afspraken

[Analyse/eisenpakket.md](Analyse/eisenpakket.md) bundelt de werkafspraken met de opdrachtgever, de producteisen, de stand van zaken en de bekende vervolgpunten. Dit bestand is leidend naast CLAUDE.md:

- **Lees het aan het begin van elke sessie** die aan de pipeline, de installatie, de publicatie of de planning werkt, en volg de werkafspraken erin (onder meer: geen commits of pushes door Claude, commitberichten zonder verwijzing naar Claude, de echte `wasstraat_*`-containers nooit aanraken).
- **Werk het bij in dezelfde sessie** waarin iets verandert: een nieuwe of gewijzigde eis of afspraak van de opdrachtgever, een afgeronde of geparkeerde stap in de stand van zaken, een nieuw of opgelost vervolgpunt. Zet de datum in de kopregel. Houd de bestaande hoofdstukindeling aan (werkafspraken, producteisen, stand van zaken, beperkingen en vervolgpunten, vindplaatsen) en neem wijzigingen eraan mee in de commit van het bijbehorende werk.
- Zet er geen zaken in die de repo al vastlegt (code, git-geschiedenis, documentatie in `docs/`); verwijs daar dan naar.

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
deploy/                    # Live installatie uit gepubliceerde images (compose, Makefile, kopieën van init-config.sh en config/*.env.example)
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
2. Extract — Lees brondata in (Access-databases, bestanden); de taak `Controleer_Afbeeldingen` telt daarna verwerkte, overgeslagen en mislukte afbeeldingen en rapporten (statusvelden in `Filenames`) en laat de DAG falen boven de drempel `AIRFLOW_MAX_MISLUKTE_AFBEELDINGEN` / `_PCT`; een vol mediavolume is altijd een harde fout
3. Transform1 Harmonize — Harmoniseer veldnamen over alle bronnen + brondata-correcties uit correcties.yml
4. Transform2 Enhance Attributes — Normaliseer inhoud (datums, codes, metadata) + projectcode-correcties uit correcties.yml
5. Transform3 Set Keys — Genereer unieke sleutels per entiteit
6. Transform5 Move and Merge (`Transform5_Move_And_Merge_Group`; de nummers in de namen volgen de historische volgorde, Airflow draait eerst Transform 5 en dan Transform 4) — Voeg dubbele entiteiten samen (polymorfisme). Voor artefacten is de verplaatsing sinds issue 83 precies het complement (`$nor`) van de merge-voorwaarde in `merge_functions.py`, zodat een bronrij die in een merge-groep zit niet ook als los document overblijft; de artefactsoort wordt vóór de `$group` genormaliseerd; `artefact_niet_mergen`, `ROMEINS AARDEWERK` en de RAAP-tabel `ARTEFACT` blijven uitgezonderd
7. Transform4 Set References (`Transform4_Set_References_Group`) — Ken integer-sleutels toe voor PostgreSQL; sinds issue 71 in elke DAG stabiel (`setPrimaryKeys(stabiel=True)`): bestaande `primary_key`s worden uit PostgreSQL herleid via `key` (ABR via de bron-`primary_key`, bestanden via map en bestandsnaam), alleen nieuwe entiteiten krijgen een nummer boven het maximum. Rijen zonder unieke `key` (artefacten zonder subnr, monsters, plaatsingen, vindplaatsen, dubbele keys) worden sinds issue 81 gekoppeld op een hulpsleutel uit de bronrij (`delta_transform.getBronsleutel`: pad, tabel en autonummer van de bronrij, anders een hash van de rij-inhoud; bij samengevoegde documenten de gesorteerde lijst), die in PostgreSQL uit de kolom `brondata` wordt afgeleid (`leesBrondataTekst`, AST-parser zonder eval); de load schrijft voor zulke rijen een leesbare key `...|bron:<hulpsleutel>` (`vulLaadKey`). Draai na een update met deze wijziging eerst de volledige cyclus
8. Load to Database & Index — Kopieer naar PostgreSQL + bouw Elasticsearch-index

Dit is de volledige cyclus (`Extract_Transform_Load_Full_Cycle`). Daarnaast is er de **incrementele cyclus** (`Extract_Transform_Load_Incremental`, issue 61): die verwerkt alleen nieuwe, gewijzigde en verwijderde bronbestanden en leegt niets. Volgorde: `Start_Run` → `Bepaal_Delta` (vergelijkt met de registratie in `Def_Bronbestand`) → `Opruimen_Oude_Records` → Extract (delta) → Transform 1 → 2 → 3 → 5 → 4 (delta, stabiele `primary_key`s) → `Load_Upsert` (upsert naar PostgreSQL) → `Registreer_Run`, en na `Load_Upsert` parallel de `Index_<tabel>`-taken (Elasticsearch-delta). De taken lezen het run-document (`wasstraat/verwerkingsrun.py`, collectie `Verwerkingsruns`) in plaats van XCom; `Markeer_Run_Mislukt` zet de run op `mislukt` als een bewaakte taak faalt (de Index-taken zijn bewust niet bewaakt). Eerst één keer de volledige cyclus draaien (die registreert alle bronbestanden); de volledige cyclus blijft nodig na wijzigingen in de harmonisatie-Excel, `correcties.yml` of de pipelinecode. Ontwerp en keuzes: [docs/componenten/incrementeel-laden.md](docs/componenten/incrementeel-laden.md).

DAG-bestanden volgen het patroon `DAG_[Naam].py`, taken `tasks_[actie]_[onderwerp].py`.

**Foutbeleid en verwerkingsrapport (issues 54 en 62).** Alle drie de DAG's (volledige cyclus, incrementele cyclus, `DAG_Load_Only`) beginnen met `Start_Run` (run-document in `Verwerkingsruns`, soort `volledig`, `incrementeel` of `laden`; faalt als er al een run actief is; `max_active_runs=1`) en eindigen met `Verwerkingsrapport` (`trigger_rule='all_done'`, hangt aan alle taken) en een eindtaak die de status van de DAG bepaalt. `wasstraat/foutbeleid.py` legt per fout vast of hij cruciaal is (`CrucialeFout`, de bewaakte taken zetten via `Markeer_Run_Mislukt` de run op `mislukt`) of een waarschuwing (geteld en gemeld in de lijst `meldingen` van het run-document, maximaal 500): onleesbare Access-databases en overgeslagen tabellen (`Controleer_Databases` na de import, drempel `AIRFLOW_MAX_MISLUKTE_DATABASES` / `_PCT`), verwerkingsfouten van Transform 2 (`AIRFLOW_MAX_VERWERKINGSFOUTEN` / `_PCT`, per taak), FK's die niet hersteld of gevalideerd zijn, instabiele sleutels, afgeleide velden (SAVEPOINT) en mislukte `Index_*`-taken (`Index_Klaar` met `all_done`: de DAG slaagt, de waarschuwing staat in het rapport). Elke taak heeft een `on_failure_callback` die de fout in het run-document zet. `wasstraat/verwerkingsrapport.py` schrijft per run een JSON- en Markdown-rapport in `AIRFLOW_OUTPUT_RAPPORTEN` (standaard `/output/rapporten`, terugval `AIRFLOW_LOGDIR/rapporten`) met run, samenvatting, foutbeleid, bronbestanden (inclusief `paden_overgeslagen`), objecttotalen, kwaliteitsmeldingen en doorlooptijd per stap; een compacte verwijzing komt in het run-document onder `rapport`. Documentatie: [docs/componenten/verwerkingsrapport.md](docs/componenten/verwerkingsrapport.md).

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

- **Type A — database-entiteiten** (`identificeer(soort, doc)` dispatcher → `identificeer_put/vlak/spoor/vondst/artefact/...`): normaliseer projectcd, converteer identificerende integers. Voor Foto, Tekening en Rapport (`const.BESTANDSOORTEN`) kiest de dispatcher `identificeer_foto_db/tekening_db/rapport_db(doc)`, omdat de naam zonder `_db` daar de bestandsnaam-parser is.
- **Type B — bestands-entiteiten** (`identificeer_foto(doc, projectcd)`, `identificeer_tekening(doc, projectcd)`): parse bestandsnaam naar velden. Standaard retourneert `None`; DelftProfiel implementeert regex-parsing. Alleen `parseFotobestanden()` roept deze aan.

**Aanroep in de pipeline:**
- `parseFotobestanden()` — `identificeer_foto()` / `identificeer_tekening()` voor bestandsnaam-parsing
- `enhanceAllAttributes()` — `identificeer(soort, doc)` voor alle soorten; de dispatcher kiest voor Foto/Tekening/Rapport de `_db`-variant

**Tests:** `tests/unit/test_profielen.py` — profielselectie, caching, ConventieProfiel, DelftProfiel, VoorbeeldProfiel.

Zie [docs/componenten/gemeenteprofielen.md](docs/componenten/gemeenteprofielen.md) voor volledige documentatie.

## Gemeente-specifieke correcties (correcties.yml)

Per omgeving (delft, synthetic, test) kan een `correcties.yml` in `wasstraat_config/` staan. Dit bestand bevat datacorrecties die de pipeline toepast zonder dat de code aangepast hoeft te worden.

**Twee secties:**

- **`projectcode_correcties`** — eenvoudige regex→projectcode vervangingen, toegepast op het `projectcd` veld in Single_Store na harmonisatie (Transform2). Geen collectie of veldnaam nodig.
- **`brondata_correcties`** — correcties op raw velden in staging-collecties vóór harmonisatie (Transform1). Nodig als brondata afwijkende codes bevat die niet matchen met de projectenlijst. Vereist `collectie`, `zoek_veld`, `patroon` en `waarde`.

Overige secties: `artefact_niet_mergen`, `rapportcode_prefixen` en `paden_overslaan` (issue 84: glob-patronen relatief aan de invoermap, hoofdletterongevoelig, voor Access-databases, de registratie van bronbestanden én afbeeldingen en rapporten; logica in `wasstraat/paden_overslaan.py`, toegepast in `importMDB.sh` via `airflow_app/scripts/paden_overslaan.py`, `bronbestanden.py` en `image_import.py`; overgeslagen paden komen in het run-document onder `paden_overgeslagen`).

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

# Publiceren (images voor deploy/)
make publish          # Bouw alle images multi-arch en push naar ghcr.io/brienen/wasstraat-<service>:<versie> en :latest
make publish SERVICE=flask PUSH=0   # Eén image, alleen lokaal bouwen
make release VERSION=1.2.3 MSG="..."  # Versie vastleggen, committen, taggen, pushen en publiceren

# Onderhoud
make backup           # Backup PostgreSQL + MongoDB
make restore TS=...   # Restore vanuit timestamp
make export           # Exporteer tabellen als CSV
make stop / start     # Containers stoppen/starten
make constraints      # Leg pakketversies Flask, Jupyter en Airflow opnieuw vast (daarna make test-all)
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

De 3-fase atomic swap is ongewijzigd: (1) laad naar `_new` tabellen, (2a) atomic rename swap met FK drop/restore, (2b) FK herstel met SAVEPOINTs, (3) opruimen `_old` tabellen. De publieke interface `loadAll()` is ongewijzigd — DAGs en tasks hoefden niet aangepast te worden. Sinds issue 71 leegt `loadAll` de gebruikerstabellen niet meer: in fase 1 bepaalt `bepaalVervallenSleutels` welke rijen hun `primary_key` verliezen (verdwenen, of hernummerd als de key niet uniek is), vóór de rename koppelt `koppelGebruikersdataLos` gebruikersdata los (met markering) en verwijdert het koppelrijen, na de rename koppelt `werkGebruikersdataBijNaSwap` op een unieke key weer terug. Hernummerde rijen geven de waarschuwing "Sleutels niet stabiel" (bijvoorbeeld `DAG_Load_Only` op MongoDB-data die niet bij deze database hoort). Koppeltabellen zonder `primary_key` (`Def_artefact_abr`, `Def_artefact_conservering`) worden niet geïndexeerd. De FK-mechaniek staat in herbruikbare helpers (`leesFkConstraints`, `verwijderFkConstraints`, `herstelFkConstraints`, `valideerFkConstraints`) die ook de incrementele load gebruikt.

### Incrementele load (upsert)

`loadIncrementeel()` (taak `Load_Upsert` van de incrementele cyclus) werkt de bestaande tabellen bij in plaats van ze te vervangen, in één transactie: betrokken FK's verwijderen, per tabel uit `LOAD_TABELLEN` een `INSERT ... ON CONFLICT (primary_key) DO UPDATE` van alle documenten (inclusief `_id`; alleen echte wijzigingen worden geschreven), rijen verwijderen waarvan de `primary_key` niet meer in `Single_Store_Clean` staat, geometrie bijwerken, sequence van `primary_key` op max + 1 (en opnieuw aanmaken als de atomic swap hem kwijt is), FK's herstellen met `NOT VALID`, commit, valideren. `SET CONSTRAINTS ALL DEFERRED` werkt niet: niet alle FK's zijn deferrable. Gebruikerstabellen (`GEBRUIKERS_TABELLEN`: bruiklenen, partijen, conservering, `Def_artefact_abr`) en `Def_Bronbestand` blijven ongemoeid. Tellingen per tabel komen in het run-document onder `tellingen.load`. De rijen worden opgebouwd met dezelfde helpers als `transferToDB` (`leesDocumenten`, `transformRow`); artefacten zonder `key` krijgen daarbij in beide cycli de samengestelde sleutel `key_subnr|artefactsoort` in de kolom `key`.

### Gebruikersdata bij verdwenen rijen

`shared/gebruikersdata.py` legt vast wat er gebeurt met gebruikersdata die verwijst naar een rij die bij een incrementele run uit de brondata verdwijnt (`VERWIJZINGEN`): bruiklenen (`artefactID`, `projectID`) en conservering (`artefact_id`) worden losgekoppeld met een markering (`<verwijzing>_verdwenen_key` met de `key` van de verdwenen rij en `<verwijzing>_verdwenen_op`), pure koppelrijen (`Def_artefact_abr`) worden verwijderd; keert een rij met dezelfde `key` terug, dan wordt de verwijzing hersteld (`koppelVerwijzingenTerug`). De nodige schemawijzigingen (nullable, markeringskolommen) doet `migreerSchema` idempotent aan het begin van elke load en bij het starten van Flask (na `db.create_all()`), omdat `create_all` bestaande tabellen niet aanpast. Tellingen in het run-document onder `tellingen.gebruikersdata`.

### Afgeleide velden

`herberekenAfgeleideVelden(cursor)` zet na elke load met set-based SQL de velden die de webapplicatie afleidt (`AFGELEIDE_VELDEN`: `Def_Artefact.aantal_fotos`, de vondst-, spoor- en gecombineerde dateringen van artefacten, `Def_Project.aantal_artefacten`), alleen voor rijen waarvan een waarde verandert. In `loadAll` is dat FASE 4 in een eigen transactie, in `loadIncrementeel` gebeurt het binnen de upsert-transactie vóór het FK-herstel; de tellingen komen in het run-document onder `tellingen.afgeleide_velden`. `app/app/init.py` (`initIfNotInit`) blijft alleen als vangnet bij het opstarten van Flask. `tests/unit/test_afgeleide_velden.py` eist dat de SQL dezelfde uitkomst geeft als `init.init()` met de observers uit `models.py`.

### Aandachtspunten bij wijzigingen

- `archutils.convertToBool()` retourneert `0`/`1` (integers) — wrap altijd met `bool()` voor psycopg2
- Geometry kolom `location` wordt NIET meegegeven in de INSERT maar via een aparte UPDATE bijgewerkt
- ENUM kolommen worden gedetecteerd via `pg_type.typtype = 'e'` — lege waarden worden `'Onbekend'`
- Beide testomgevingen hebben een eigen Elasticsearch (`elasticsearch-test`; containers `wasstraat_elasticsearch_test` en `wasstraat_elasticsearch_delft_test`, zonder hostpoort want 9200 is van de echte installatie); de Index_*-taken van de volledige cyclus, `DAG_Load_Only` en de incrementele cyclus slagen daar dus ook, en de pipelinetests eisen dat. Bewaakt door `tests/unit/test_elasticsearch_testomgeving.py`

## Integratietests en volgorde

`make integration` draait de volledige testsuite in twee stappen binnen één Docker-sessie:

1. **Stap 1:** Extract → Transform → Load pipeline (marker: `integration or load`), als laatste `test_incremental_synthetic_data.py`: volledige cyclus plus zes incrementele runs met een tijdelijk project SY003 (waaronder een onleesbare foto met drempel 0 en het opruimen daarna) (de fixture ruimt `data/synthetic/data/projecten/SY003` altijd op)
2. **Stap 2:** Flask smoke tests (marker: `flask_smoke`) — vereist geladen PostgreSQL-data uit stap 1

De Flask smoke tests controleren of projecten zichtbaar zijn op de kaart en hebben daarom gevulde `Def_Project` data nodig. Draai `make integration` voor de volledige suite, of `make integration-pipeline` voor alleen Extract + Transform zonder Load.

## Publicatie en live installatie (deploy/)

De repository is de ontwikkelomgeving; gebruikers installeren de Wasstraat vanuit de gepubliceerde images met de map `deploy/` (zie [docs/deployment/installatie-met-images.md](docs/deployment/installatie-met-images.md)).

- `make publish` bouwt de vier eigen images (airflow, flask, postgres, apache) met `docker buildx` voor linux/amd64 en linux/arm64 en pusht ze naar `ghcr.io/brienen/wasstraat-<service>` met de tags `<versie>` (uit `config/version.env`, anders `version.env.example`) en `latest`. `PUSH=0` bouwt alleen lokaal voor het eigen platform. Inloggen gebeurt buiten het doel om (`docker login ghcr.io`).
- De Airflow-image bevat `airflow_app/dags`, `airflow_app/scripts` en `shared/` (als `dags/shared`). De ontwikkel-compose-bestanden mounten de broncode daaroverheen; de gepubliceerde images draaien zonder volumes naar broncode. Jupyter is een ontwikkelvoorziening: geen image in `make publish` en geen service in `deploy/`.
- **Apache is de voordeur** (eis van 2026-10-21), in de ontwikkelomgeving, `deploy/` en de testomgevingen: Apache (poort 5052) serveert `/archeomedia` rechtstreeks uit de uitvoermap en stuurt alle overige verzoeken door naar `http://flask:5051/` (`services/apache/httpd.conf`: `ProxyPass`, `ProxyPreserveHost On`, `X-Forwarded-Proto` via `setifempty`, `retry=0`). Flask heeft geen hostpoort (alleen `docker-compose.develop.yml` geeft 5051 voor debuggen) en gebruikt `ProxyFix(x_for=1, x_proto=1, x_host=1)` in `app/app/app.py`; geen `x_port`, want de hostpoort kan afwijken van 5052. De webapplicatie verwijst naar foto's met relatieve paden `/archeomedia/...`, dus rechtstreeks op Flask blijven foto's leeg. In `docker-compose.test.yml` is `apache-test` (hostpoort 5061) de voordeur van de Flask smoke tests; het mediavolume `archeomedia-test` (tmpfs, uid 50000) wordt gedeeld door `airflow-test` en `apache-test`. In `docker-compose.delft-test.yml` is dat volume een gewoon schijfvolume op `/output/archeomedia`: de Delftse rapporten (circa 5 GB) passen niet in tmpfs en een vol volume laat bestanden stil onverwerkt. De Airflow-image maakt `/output/archeomedia` aan met airflow als eigenaar, zodat een leeg named volume daar schrijfbaar is. Bewaakt door `tests/unit/test_apache_voordeur.py`.
- `deploy/docker-compose.yml` heeft alleen `image:`-regels met `${WASSTRAAT_VERSION}` uit `deploy/.env`; brondata en `wasstraat_config` zijn alleen-lezen gemount. `deploy/init-config.sh`, `deploy/config/*.env.example` (alleen de zes die de compose gebruikt) en de harmonisatie-Excel zijn kopieën; `tests/unit/test_deploy.py` bewaakt dat ze gelijk blijven aan het origineel en dat `deploy/.env.example` dezelfde versie heeft als `config/version.env.example`. Wijzig je het origineel, kopieer het dan ook naar `deploy/`.
- `.dockerignore` houdt `data/`, `notebooks/`, `docs/` en `deploy/` buiten de buildcontext; geen Dockerfile kopieert daaruit.

## Belangrijke aandachtspunten

- `app/app/models.py` (62 KB) bevat 100+ SQLAlchemy-modellen — wees voorzichtig met wijzigingen
- De custom `fab_addon_geoalchemy/` extensie is project-specifiek
- `shared/config.py` leest environment-variabelen — wijzig nooit `.env` bestanden direct
- `shared/const.py` bevat alle constanten en enums voor het hele project
- De Airflow DAGs hebben een strikte verwerkingsvolgorde — verander deze niet zonder overleg
- Documentatie staat in `docs/` als MkDocs Markdown — houd deze synchroon met codewijzigingen; `docs/componenten/configuratie.md` is het naslagwerk voor alle configuratie (omgevingsvariabelen, `correcties.yml`, harmonisatie-Excel, profielen, `deploy/`), `mkdocs.yml` heeft een `validation`-blok en `.venv/bin/mkdocs build --strict` moet zonder waarschuwingen slagen; de diagrammen komen uit `docs/assets/diagrams/genereer_diagrammen.py`
- Omgevingsvariabelen zijn altijd tekst. Zet numerieke instellingen in `shared/config.py` om met `int()`; cachelib >= 0.14 weigert bijvoorbeeld een tekst als cache-timeout en dan start Flask niet
- `PGDATA` en het PostgreSQL-volume moeten hetzelfde pad hebben (`/data/postgres`). Installaties van vóór oktober 2026 hebben hun data in de container; die migreer je met `make migrate-postgres-data` vóór de eerste `make app`
- De Flask-app maakt bij het opstarten de PostgreSQL-tabellen aan (`db.create_all()`). De Load-stap faalt als Flask niet draait
- `make integration` hergebruikt bestaande images. Bouw de test-images opnieuw na wijzigingen in Dockerfiles, requirements of `shared/`, anders test je oude code en oude afhankelijkheden
