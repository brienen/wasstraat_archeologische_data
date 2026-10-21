# Testen

De Wasstraat heeft een testsuite met twee niveaus: unit tests voor individuele functies en integratietests die de volledige verwerkingspipeline testen met echte databases in Docker.

## Quickstart

```bash
make install          # eenmalig: maakt .venv aan met alle dependencies
make test             # draai unit tests
make integration      # integratietests met synthetische voorbeelddata
make integration-delft # integratietests met Delftse data (indien aanwezig)
make test-all         # unit + integratietests
```

Typ `make help` voor alle beschikbare targets.

## Structuur

```
Makefile                                      # Alle commando's (make help)
requirements-test.txt                         # Python test-dependencies
docker-compose.test.yml                       # Lichtgewicht test-databases (synthetische data)
docker-compose.delft-test.yml                 # Zelfstandige testomgeving met Delftse testdata
tests/
├── conftest.py                               # Mocks voor shared.config, roman, etc.
├── run_tests.py                              # Fallback runner (zonder venv/pytest)
├── unit/
│   ├── test_archutils.py                     # convertToInt, convertToBool, fixDatering
│   ├── test_rijksdriehoek.py                 # RD ↔ WGS84 coördinaatconversie
│   ├── test_harmonizer.py                    # Pipeline-opbouw uit Excel config
│   ├── test_foto_parsing.py                  # Regex-patronen voor bestandsclassificatie
│   ├── test_profielen.py                     # Gemeenteprofielen: selectie, ConventieProfiel, DelftProfiel, VoorbeeldProfiel
│   ├── test_correcties_yml.py                # Correctiebestand laden en toepassen
│   ├── test_config_cache.py                  # Cache-instellingen uit shared/config.py zijn getallen
│   ├── test_encoding.py                      # UTF-8 encoding en conversie
│   ├── test_fixes_1_to_4.py                  # Bugfixes validatie
│   ├── test_fix_5_nonetype_foto.py           # NoneType fotobestanden
│   ├── test_fix_6_coordinaatvalidatie.py      # Rijksdriehoek coördinaatvalidatie
│   ├── test_fix_7_kolomselectie.py           # Kolomselectie robuustheid
│   ├── test_fix_8_dropna.py                  # dropna() edge cases
│   ├── test_importMDB_bash.py                # Bash import-functietests
│   ├── test_importMDB_lijstbestand.py        # importMDB.sh met lijstbestand (incrementeel laden)
│   ├── test_importMDB_kopregel.py            # importMDB.sh: kopregel en bijzondere tekens in tabelnamen
│   ├── test_verwerkingsrun.py                # Run-document van de incrementele cyclus
│   ├── test_bronbestanden.py                 # Registratie bronbestanden, vingerafdruk, delta, lijstbestanden
│   ├── test_opruimen.py                      # Opruimen oude records + delta-varianten van de extractie
│   ├── test_delta_transform.py               # Delta-varianten van de transformaties en stabiele sleutels
│   ├── test_load_incrementeel.py             # Upsert-load naar PostgreSQL en Elasticsearch-delta
│   ├── nep_mongo.py                          # In-memory nabootsing van pymongo (hulpmodule, geen tests)
│   ├── test_synthetic_data.py                # Validatie synthetische voorbeelddata
│   ├── test_synthetic_monster_data.py        # Validatie synthetische monsterdata
│   └── test_fix_monster_projectcds.py        # Projectcode-matching voor monsters
└── integration/
    ├── test_full_pipeline.py                 # Pipeline met directe MongoDB-seeding
    ├── test_full_pipeline_synthetic_data.py   # Volledige pipeline via Airflow (synthetische data)
    ├── test_full_pipeline_delft_data.py       # Volledige pipeline via Airflow (Delftse data)
    ├── test_harmonize_pipeline.py            # Harmonisatie met echte MongoDB
    ├── test_importMDB_bash.py                # MDB-import en encoding in Docker
    └── test_incremental_synthetic_data.py    # Incrementele cyclus via Airflow (synthetische data + SY003)
```

## Vereisten

Bij `make install` wordt automatisch een `.venv` aangemaakt met Python 3.11 (of 3.12/3.10 als fallback) en worden alle dependencies uit `requirements-test.txt` geïnstalleerd. Je hoeft zelf geen venv aan te maken.

De integratietests hebben daarnaast Docker nodig.

## Unit tests

```bash
make test       # uitgebreide output
make test-quick # korte output
```

Of handmatig:

```bash
source .venv/bin/activate
python -m pytest tests/unit/ -v
python -m pytest tests/unit/test_archutils.py -v   # één module
```

### Fallback zonder venv

Als je geen venv wilt of kunt gebruiken en de basispackages (pandas, numpy, openpyxl) al beschikbaar zijn:

```bash
python3 tests/run_tests.py
```

## Integratietests

### Standaard: synthetische data

```bash
make integration
```

Dit target gebruikt de **synthetische voorbeelddata** uit `data/synthetic/data/`. De tests controleren dat de volledige ETL-pipeline (Extract → Transform → Load) correct werkt met de meegeleverde fictieve opgravingsprojecten SY001 en SY002.

Het target:

1. Maakt de `.venv` aan als die nog niet bestaat
2. Start MongoDB 7.0, PostgreSQL 18 met PostGIS, Elasticsearch 8.17, Redis, Airflow, Flask en Apache in Docker (MongoDB, PostgreSQL en het mediavolume in tmpfs voor snelheid)
3. Mount de synthetische data als input-volumes
4. Triggert de Airflow DAGs (Extract, Transform, Load en indexering) en valideert de resultaten
5. Controleert verwachte aantallen per entiteitstype (sporen, vondsten, artefacten) in MongoDB en PostgreSQL
6. Draait de volledige en daarna de incrementele cyclus (`test_incremental_synthetic_data.py`, zie hieronder)
7. Draait de Flask smoke tests via Apache tegen de geladen database, inclusief de media uit het gedeelde mediavolume
8. Ruimt de containers en volumes op

### Elasticsearch in de testomgeving

`docker-compose.test.yml` heeft een eigen Elasticsearch (`elasticsearch-test`, container `wasstraat_elasticsearch_test`, image `docker.elastic.co/elasticsearch/elasticsearch:8.17.0`, zonder beveiliging, single-node, 512 MB heap). Airflow en Flask bereiken die via `ES_HOST=http://elasticsearch:9200`. Airflow start pas als Elasticsearch gezond is (healthcheck met `depends_on: condition: service_healthy`). De Index_*-taken van de volledige cyclus, van `DAG_Load_Only` en van de incrementele cyclus slagen daardoor ook in de testomgeving; `test_full_pipeline_synthetic_data.py` eist dat `DAG_Load_Only` volledig slaagt.

De container heeft bewust geen hostpoort: poort 9200 op de host is van de echte installatie. Tests benaderen Elasticsearch via `docker exec wasstraat_elasticsearch_test curl -s http://localhost:9200/...`.

### Apache in de testomgeving

Net als in de echte installatie is Apache de voordeur: `apache-test` (container `wasstraat_apache_test`, gebouwd uit `services/apache/Dockerfile`) luistert op hostpoort 5061, serveert `/archeomedia` en stuurt al het overige door naar `flask-test`, dat geen hostpoort heeft (netwerkalias `flask`, zoals `httpd.conf` verwacht). De media die `airflow-test` schrijft (`AIRFLOW_OUTPUT_MEDIA=/tmp/archeomedia_test`) staan in het volume `archeomedia-test`, een tmpfs-volume met de uid van de airflow-gebruiker, dat `apache-test` alleen-lezen mount onder `htdocs/archeomedia`.

De Flask smoke tests (`tests/integration/test_flask_smoke.py`, marker `flask_smoke`) lopen daardoor via Apache. Naast de kaart, het inloggen en de statische bestanden controleren ze dat een media-URL uit `Def_Bestand` via Apache 200 geeft (alle drie formaten van alle foto's), dat paden met spaties en diakritische tekens werken, dat redirects de `Host`-header van de browser en `X-Forwarded-Proto` van een TLS-proxy volgen, en dat `/archeomedia/` niet te bladeren is. `make test-flask` start de omgeving zonder pipeline; de mediatests slaan dan over. De Delftse testomgeving (`docker-compose.delft-test.yml`) heeft dezelfde opzet op hostpoort 5062. De unit tests in `tests/unit/test_apache_voordeur.py` bewaken de Apache-configuratie en de compose-bestanden.

### Incrementele cyclus

`tests/integration/test_incremental_synthetic_data.py` (markers `integration` en `load`, draait in `make integration` na de andere tests) begint zelf met de volledige cyclus en controleert daarna de incrementele cyclus in vier runs:

| Stap | Wijziging | Wat wordt gecontroleerd |
|------|-----------|-------------------------|
| a | Volledige cyclus | Aantallen per `Def_`-tabel, `key` → `primary_key` van `Def_Project`, `Def_Put`, `Def_Vondst`, `Def_Artefact`, `Def_Bestand` en de aantallen per Elasticsearch-index (gelijk aan de tabellen) worden vastgelegd |
| b | Een partij en een bruikleen toegevoegd (SQL) | Gebruikersdata die naar een artefact en het project SY002 verwijst |
| c | Geen | Run afgerond, alle bronbestanden ongewijzigd, niets ingevoegd, bijgewerkt of verwijderd, aantallen en sleutels gelijk, bruikleen aanwezig, Elasticsearch gelijk |
| d | Project SY003 als kopie van SY002 (`opgravingSY003.mdb`, foto's `SY003_*`) | SY003 heeft evenveel rijen als SY002, nieuwe `primary_key`s boven het oude maximum, SY001/SY002 ongewijzigd, bruikleen en zijn artefact ongewijzigd, Elasticsearch gelijk aan de tabellen |
| e | Database van SY003 vervangen door die van SY001, één foto verwijderd | SY003 volgt SY001 (4 vondsten, plus de put en vondst die Transform 5 aanmaakt voor de objectfoto `SY003_P4_H11_1_1.jpg`), geen rij meer voor de verwijderde foto, geen achtergebleven rijen, verdwenen id's ook uit Elasticsearch |
| f | SY003 verwijderd | Geen SY003-rijen meer in PostgreSQL en Elasticsearch, `Def_Bronbestand` op `verwijderd`, alle sleutels en aantallen gelijk aan stap a |

De fixture `sy003_opruimen` verwijdert `data/synthetic/data/projecten/SY003` vóór en na de test, ook als die faalt. De test duurt ongeveer twee minuten. Los draaien (met een draaiende testomgeving):

```bash
python -m pytest tests/integration/test_incremental_synthetic_data.py -v -s
```

!!! warning "Images worden niet opnieuw gebouwd"
    `make integration` start de test-containers met de images die al op je machine staan. Wijzigingen in een Dockerfile, in `requirements.txt` of `constraints.txt`, of in `shared/` (die in de Flask-image wordt gekopieerd) zie je pas na een nieuwe build. De Flask-pakketten blijven bij een nieuwe build op de vastgelegde versies (zie [Pakketversies bijwerken](#pakketversies-bijwerken)); die van Airflow kunnen dan wel nieuwer worden. Bouw de images daarom opnieuw na zulke wijzigingen, en zonder cache als je een schone installatie wilt nabootsen:
    ```bash
    docker compose -p wasstraat-test -f docker-compose.test.yml build --no-cache --pull
    ```

### Delft-specifiek: echte data

```bash
make integration-delft
```

Dit target test met de echte Delftse opgravingsdata en controleert op Delft-specifieke aantallen. De Delftse data is niet opgenomen in de repository — deze tests worden automatisch overgeslagen als de data niet aanwezig is in `data/test/`.

### Handmatig

```bash
docker compose -p wasstraat-test -f docker-compose.test.yml up -d

source .venv/bin/activate
MONGO_TEST_URI="mongodb://testroot:testpass@localhost:27117/" \
python -m pytest tests/integration/ -v -m integration

docker compose -p wasstraat-test -f docker-compose.test.yml down -v
```

## Pakketversies bijwerken

De Flask- en de Jupyter-image installeren hun Python-pakketten met vaste versies uit `services/flask/constraints.txt` en `services/jupyter/constraints.txt`. Daarin staan alle pakketten, ook de afgeleide pakketten die pip zelf meeneemt. Een verse build levert zo dezelfde versies op als de build waarmee de tests geslaagd zijn. `services/flask/requirements.txt` bevat alleen de directe pakketten, met ruime grenzen.

De Flask-build controleert dit: wijken de geïnstalleerde versies af van `constraints.txt`, dan stopt de build met de melding dat je `make constraints` moet draaien. Dat gebeurt bijvoorbeeld als je een pakket aan `requirements.txt` toevoegt of een grens verandert.

Zo werk je de versies bij:

```bash
make constraints
git diff services/flask/constraints.txt services/jupyter/constraints.txt
docker compose -p wasstraat-test -f docker-compose.test.yml build --no-cache --pull
make test-all
```

`make constraints` bouwt beide images zonder cache en zonder vaste versies, zodat pip de nieuwste versies binnen de grenzen kiest, en schrijft die versies weg. Werk je maar één image bij, gebruik dan `bash scripts/leg_pakketversies_vast.sh flask` (of `jupyter`).

Commit de nieuwe constraints-bestanden alleen als `make test-all` slaagt. Faalt een test door een nieuwere versie, zet dan een bovengrens in `requirements.txt` en draai `make constraints` opnieuw. De Jupyter-image valt buiten de tests; open na het bijwerken een paar notebooks om te controleren of ze nog werken.

De basisimage van Jupyter staat vast op een digest in `services/jupyter/Dockerfile`. De Flask-image gebruikt `python:3.11-slim-bookworm` zonder digest, zodat beveiligingsupdates van Python en Debian wel binnenkomen. De Airflow-image heeft geen constraints-bestand: de basisimage legt de versies van Airflow zelf vast, maar de extra pakketten uit `services/airflow/requirements.txt` kunnen bij een nieuwe build nog verschuiven.

## Wat wordt getest?

### Unit tests

| Module | Wat wordt getest |
|--------|-----------------|
| `archutils.py` | `convertToInt` (type-conversie, force/no-force), `convertToBool` (ja/nee/true/false), `fixDatering` (eeuw-kwart notatie, Romeinse cijfers, LMEb, RT, gecombineerde dateringen) |
| `rijksdriehoek.py` | RD→WGS84 conversie met referentiepunten (Amsterdam, Rotterdam, Maastricht, Delft), WGS84→RD inversie, roundtrip-nauwkeurigheid |
| `harmonizer.py` | `getKolomValues` ($ifNull-ketens), `getAggrTables` (regex-matching), `loadHarmonizer` (Excel → DataFrame), pipeline-structuur ($match, $merge), overerving (Artefact→Aardewerk), `getHarmonizeAggr` wijzigt de gecachete pipeline niet |
| `foto_parsing.py` | Objectfoto-regex (met put/subnr/BP), tekening-types (A-E, P, T, LZW), projectfoto's (F/G), DAN/DAR rapporten, artefactsoort-detectie uit bestandspad |
| `encoding.py` | UTF-8 conversie, CP1252-detectie, dubbele CSV-headers |
| `importMDB_kopregel.py` | `importMDB.sh`: de kopregel van de CSV-export (zelf gequote, ook bij komma's in kolomnamen) en bijzondere tekens (`&`, `\`, komma's) in tabelnamen bij het toevoegen van `table`, `projectcd`, `bron`, `loadtime` en `mdbfile` |
| `fixes_*.py` | Robuustheid van transformaties bij ontbrekende/ongeldige data |
| `synthetic_data.py` | Validatie dat de synthetische MDB-bestanden de juiste tabellen en kolomstructuur bevatten |
| `synthetic_monster_data.py` | Structuur, kolomaantallen, referentiële integriteit en projectverwijzingen van synthetische monsterdata |
| `fix_monster_projectcds.py` | Projectcode-matching logica voor de monsterdatabase (mocking van MongoDB) |
| `config_cache.py` | Cache-instellingen uit de echte `shared/config.py` zijn getallen en worden door cachelib geaccepteerd |
| `verwerkingsrun.py`, `bronbestanden.py`, `opruimen.py`, `delta_transform.py` | Incrementeel laden: run-document, registratie en delta van bronbestanden, opruimen, delta-transformaties en stabiele sleutels (ook de samengestelde sleutel van artefacten) |
| `load_incrementeel.py` | Upsert-load (`loadIncrementeel`: upsert, verwijderen, FK-mechaniek, sequence, gebruikerstabellen ongemoeid, tellingen) en de Elasticsearch-delta (`indexTableIncrementeel`) met nagebootste databases |

### Integratietests

| Test | Wat wordt getest |
|------|-----------------|
| `test_full_pipeline.py` | Volledige harmonisatie-pipeline met directe MongoDB-seeding: harmonisatie, enhance, keys, move & merge, references |
| `test_full_pipeline_synthetic_data.py` | Volledige ETL via Airflow DAGs met synthetische MDB-data: extract, transform, verwachte aantallen per soort (inclusief monsters, botanische/schelpdeterminaties en referentietabellen), objectfoto's gekoppeld aan hun artefact en vondst (`artefactID`/`vondstID` in Single_Store_Clean en `Def_Bestand`), geen Transform 2-fouten voor foto's |
| `test_full_pipeline_delft_data.py` | Zelfde pipeline maar met Delftse data en Delft-specifieke verwachte aantallen; objectfoto's met projectcode `DB034`, integers en een `artefactID` |
| `test_harmonize_pipeline.py` | Individuele harmonisatie-pipelines (Vondst, Spoor, alle objecttypen) |
| `test_importMDB_bash.py` | MDB-import shell-script: encoding-conversie, CSV-generatie, mongoimport |
| `test_incremental_synthetic_data.py` | Volledige cyclus gevolgd door vier incrementele runs (geen wijziging, nieuw project, vervangen database en verwijderde foto, verwijderd project): PostgreSQL, Elasticsearch, registratie en gebruikersdata |

## Nieuwe tests toevoegen

1. Maak een nieuw bestand aan in `tests/unit/` of `tests/integration/`
2. Gebruik `pytest.mark.unit` of `pytest.mark.integration` als marker
3. Gebruik `pytest.mark.delft` voor tests die Delftse data vereisen
4. De `conftest.py` mockt automatisch `shared.config` en `shared.const`
5. Voor integratietests: gebruik de `mongo_client`, `staging_db` en `analyse_db` fixtures

## Opruimen

```bash
make clean          # verwijder .venv en caches
make clean-test-db  # stop test-database containers
```
