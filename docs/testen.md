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
│   ├── test_importMDB_kopregel.py            # importMDB.sh: kopregel van de CSV-export
│   ├── test_csv_kolommen.py                  # importMDB.sh: extra kolommen per record (csv_kolommen.py)
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

Beide testomgevingen hebben een eigen Elasticsearch (`elasticsearch-test`; container `wasstraat_elasticsearch_test` in `docker-compose.test.yml` en `wasstraat_elasticsearch_delft_test` in `docker-compose.delft-test.yml`; image `docker.elastic.co/elasticsearch/elasticsearch:8.17.0`, zonder beveiliging, single-node, 512 MB heap). Airflow en Flask bereiken die via `ES_HOST=http://elasticsearch:9200`. Airflow start pas als Elasticsearch gezond is (healthcheck met `depends_on: condition: service_healthy`). De Index_*-taken van de volledige cyclus, van `DAG_Load_Only` en van de incrementele cyclus slagen daardoor ook in de testomgeving; `test_full_pipeline_synthetic_data.py` en `test_full_pipeline_delft_data.py` eisen dat `DAG_Load_Only` volledig slaagt, en de Delftse test vergelijkt daarna per geïndexeerde tabel het aantal documenten in Elasticsearch met het aantal rijen in PostgreSQL.

De container heeft bewust geen hostpoort: poort 9200 op de host is van de echte installatie. Tests benaderen Elasticsearch via `docker exec wasstraat_elasticsearch_test curl -s http://localhost:9200/...` (Delft: `wasstraat_elasticsearch_delft_test`).

### Apache in de testomgeving

Net als in de echte installatie is Apache de voordeur: `apache-test` (container `wasstraat_apache_test`, gebouwd uit `services/apache/Dockerfile`) luistert op hostpoort 5061, serveert `/archeomedia` en stuurt al het overige door naar `flask-test`, dat geen hostpoort heeft (netwerkalias `flask`, zoals `httpd.conf` verwacht). De media die `airflow-test` schrijft (`AIRFLOW_OUTPUT_MEDIA=/tmp/archeomedia_test`) staan in het volume `archeomedia-test`, een tmpfs-volume met de uid van de airflow-gebruiker, dat `apache-test` alleen-lezen mount onder `htdocs/archeomedia`.

De Flask smoke tests (`tests/integration/test_flask_smoke.py`, marker `flask_smoke`) lopen daardoor via Apache. Naast de kaart, het inloggen en de statische bestanden controleren ze dat een media-URL uit `Def_Bestand` via Apache 200 geeft (alle drie formaten van alle foto's), dat paden met spaties en diakritische tekens werken, dat redirects de `Host`-header van de browser en `X-Forwarded-Proto` van een TLS-proxy volgen, en dat `/archeomedia/` niet te bladeren is. Klasse `TestVerdwenenUitBrondata` (issue 73) maakt met SQL een bruikleen en een conserveringsproject aan waarvan het artefact uit de brondata is verdwenen (lege verwijzing met markering) en vraagt als beheerder de lijst en het detail van de bruiklenen en het detail van het conserveringsproject op: HTTP 200 en de markering in de pagina. `make test-flask` start de omgeving zonder pipeline; de mediatests slaan dan over. De Delftse testomgeving (`docker-compose.delft-test.yml`) heeft dezelfde opzet op hostpoort 5062, maar met een gewoon schijfvolume (`archeomedia-delft-test`) op `/output/archeomedia` in plaats van tmpfs: de Delftse testdata bevat circa 5 GB aan rapporten die de extractie integraal naar de mediamap kopieert, en in een vol tmpfs mislukt de verwerking van de overige bestanden stil (ze blijven op `processed: False` staan). De Airflow-image maakt `/output/archeomedia` aan met de airflow-gebruiker als eigenaar, zodat een leeg named volume die rechten overneemt. Heb je een test-image van vóór deze wijziging, bouw hem dan opnieuw met `docker compose -p wasstraat-delft-test -f docker-compose.delft-test.yml build airflow-test`. De unit tests in `tests/unit/test_apache_voordeur.py` bewaken de Apache-configuratie en de compose-bestanden.

### Incrementele cyclus

`tests/integration/test_incremental_synthetic_data.py` (markers `integration` en `load`, draait in `make integration` na de andere tests) begint zelf met de volledige cyclus en controleert daarna de incrementele cyclus in zeven runs (c tot en met h; g en h gaan over onleesbare foto's, issue 70, zie [Incrementeel laden](componenten/incrementeel-laden.md#testen)):

| Stap | Wijziging | Wat wordt gecontroleerd |
|------|-----------|-------------------------|
| a | Volledige cyclus | Aantallen per `Def_`-tabel, `key` → `primary_key` van `Def_Project`, `Def_Put`, `Def_Vondst`, `Def_Artefact`, `Def_Bestand` en de aantallen per Elasticsearch-index (gelijk aan de tabellen) worden vastgelegd |
| b | Een partij en een bruikleen toegevoegd (SQL) | Gebruikersdata die naar een artefact en het project SY002 verwijst |
| c | Geen | Run afgerond, alle bronbestanden ongewijzigd, niets ingevoegd, bijgewerkt of verwijderd, aantallen en sleutels gelijk, bruikleen aanwezig, Elasticsearch gelijk |
| d | Project SY003 als kopie van SY002 (`opgravingSY003.mdb`, foto's `SY003_*`); daarna een tweede bruikleen (SQL) voor een artefact van SY003 dat in stap e verdwijnt | SY003 heeft evenveel rijen als SY002, nieuwe `primary_key`s boven het oude maximum, SY001/SY002 ongewijzigd, bruikleen en zijn artefact ongewijzigd, Elasticsearch gelijk aan de tabellen |
| e | Database van SY003 vervangen door die van SY001, één foto verwijderd | SY003 volgt SY001 (4 vondsten, plus de put en vondst die Transform 5 aanmaakt voor de objectfoto `SY003_P4_H11_1_1.jpg`), geen rij meer voor de verwijderde foto, geen achtergebleven rijen, verdwenen id's ook uit Elasticsearch; de bruikleen van het verdwenen artefact bestaat nog met `artefactID` leeg, de key in `artefact_verdwenen_key` en een tijdstip binnen de run in `artefact_verdwenen_op` (issue 73), de bruikleen uit stap b is ongemoeid en geen enkele FK is `NOT VALID` (`pg_constraint.convalidated`) |
| e2 | Database van SY003 weer die van SY002 | Het artefact keert terug met dezelfde key (nieuwe `primary_key`); de bruikleen is er weer aan gekoppeld en de markering is leeg (`tellingen.gebruikersdata`: één teruggekoppeld), FK's geldig |
| f | SY003 verwijderd | Geen SY003-rijen meer in PostgreSQL en Elasticsearch, `Def_Bronbestand` op `verwijderd`, alle sleutels en aantallen gelijk aan stap a; de bruikleen van het SY003-artefact is weer losgekoppeld en bestaat nog, FK's geldig |

De fixture `sy003_opruimen` verwijdert `data/synthetic/data/projecten/SY003` vóór en na de test, ook als die faalt. De test duurt ongeveer twee minuten. Los draaien (met een draaiende testomgeving):

```bash
python -m pytest tests/integration/test_incremental_synthetic_data.py -v -s
```

!!! warning "Images worden niet opnieuw gebouwd"
    `make integration` start de test-containers met de images die al op je machine staan. Wijzigingen in een Dockerfile, in `requirements.txt` of `constraints.txt`, of in `shared/` (die in de Flask-image wordt gekopieerd) zie je pas na een nieuwe build. De Flask- en Airflow-pakketten blijven bij een nieuwe build op de vastgelegde versies (zie [Pakketversies bijwerken](#pakketversies-bijwerken)). Bouw de images daarom opnieuw na zulke wijzigingen, en zonder cache als je een schone installatie wilt nabootsen:
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

De Flask-, de Jupyter- en de Airflow-image installeren hun Python-pakketten met vaste versies uit `services/flask/constraints.txt`, `services/jupyter/constraints.txt` en `services/airflow/constraints.txt`. Een verse build levert zo dezelfde versies op als de build waarmee de tests geslaagd zijn. De `requirements.txt` van Flask en Airflow bevatten alleen de directe pakketten, met ruime grenzen; bij Jupyter staan ze in de pip-opdracht van de Dockerfile.

- **Flask** bouwt op `python:3.11-slim-bookworm`. Daarom staan in `constraints.txt` alle pakketten, ook de afgeleide pakketten die pip zelf meeneemt.
- **Jupyter en Airflow** bouwen voort op een basisimage die haar eigen versies vastlegt: Jupyter op een digest, Airflow via de constraints waarmee `apache/airflow:2.10.5-python3.11` is gebouwd. In hun `constraints.txt` staat alleen wat pip bovenop de basisimage installeert of wijzigt: de directe pakketten en hun afgeleide pakketten. Pakketten die de basisimage al vastlegt staan er niet nog eens in, zodat de twee nooit botsen.
- **Airflow** gaat nog een stap verder: de build legt eerst de versies van de basisimage vast (`pip list --format=freeze`) en geeft die als extra constraints aan pip. Pip mag dus alleen pakketten toevoegen, nooit Airflow of een van zijn pakketten bij- of terugwerken, en `pip check` moet slagen. Vraagt `services/airflow/requirements.txt` een versie die de basisimage niet heeft, dan stopt de build; verruim dan de grens in `requirements.txt` (zo staat `opentelemetry-api` op `>=1.27`, de versie van de basisimage).

De Flask- en de Airflow-build controleren de versies: wijken de geïnstalleerde versies af van `constraints.txt`, dan stopt de build met de melding dat je `make constraints` moet draaien. Dat gebeurt bijvoorbeeld als je een pakket aan `requirements.txt` toevoegt of een grens verandert.

Zo werk je de versies bij:

```bash
make constraints
git diff services/*/constraints.txt
docker compose -p wasstraat-test -f docker-compose.test.yml build --no-cache --pull
make test-all
```

`make constraints` bouwt de drie images zonder cache en zonder vaste versies, zodat pip de nieuwste versies binnen de grenzen kiest, en schrijft die versies weg. Werk je maar één image bij, gebruik dan `bash scripts/leg_pakketversies_vast.sh flask` (of `jupyter` of `airflow`). Het script bouwt eigen images (`wasstraat-pakketversies-*`), verwijdert ze na afloop en laat draaiende containers ongemoeid.

Commit de nieuwe constraints-bestanden alleen als `make test-all` slaagt. Faalt een test door een nieuwere versie, zet dan een bovengrens in `requirements.txt` (bij Jupyter in de Dockerfile) en draai `make constraints` opnieuw. De Jupyter-image valt buiten de tests; open na het bijwerken een paar notebooks om te controleren of ze nog werken.

De basisimage van Jupyter staat vast op een digest in `services/jupyter/Dockerfile`. De Flask-image gebruikt `python:3.11-slim-bookworm` zonder digest, zodat beveiligingsupdates van Python en Debian wel binnenkomen. Ook `apache/airflow:2.10.5-python3.11` staat niet op een digest; de Python-pakketten van die tag liggen vast via de constraints van Airflow 2.10.5. De `apt-get`-opdrachten in de Dockerfiles proberen een mislukte download drie keer opnieuw (`-o Acquire::Retries=3`), zodat een verse build niet stukloopt op een tijdelijke netwerkfout.

## Wat wordt getest?

### Unit tests

| Module | Wat wordt getest |
|--------|-----------------|
| `archutils.py` | `convertToInt` (type-conversie, force/no-force), `convertToBool` (ja/nee/true/false), `fixDatering` (eeuw-kwart notatie, Romeinse cijfers, LMEb, RT, gecombineerde dateringen) |
| `rijksdriehoek.py` | RD→WGS84 conversie met referentiepunten (Amsterdam, Rotterdam, Maastricht, Delft), WGS84→RD inversie, roundtrip-nauwkeurigheid |
| `harmonizer.py` | `getKolomValues` ($ifNull-ketens), `getAggrTables` (regex-matching), `loadHarmonizer` (Excel → DataFrame), pipeline-structuur ($match, $merge), overerving (Artefact→Aardewerk), `getHarmonizeAggr` wijzigt de gecachete pipeline niet |
| `foto_parsing.py` | Objectfoto-regex (met put/subnr/BP), tekening-types (A-E, P, T, LZW), projectfoto's (F/G), DAN/DAR rapporten, artefactsoort-detectie uit bestandspad |
| `encoding.py` | UTF-8 conversie, CP1252-detectie, dubbele CSV-headers |
| `importMDB_kopregel.py` | `importMDB.sh`: de kopregel van de CSV-export (zelf gequote, ook bij komma's in kolomnamen) |
| `csv_kolommen.py` | `airflow_app/scripts/csv_kolommen.py` en de aanroep in `importMDB.sh` (issue 74): `table`, `projectcd`, `bron`, `loadtime` en `mdbfile` achter elk record, ook bij een tekstveld met een regeleinde; gewone rijen, lege velden, komma's en aanhalingstekens, bijzondere tekens (`&`, `\`) in tabelnamen en paden, lege tabel, niet-UTF-8-bytes, grote tabel; byte voor byte gelijk aan de vroegere `sed`-regels zolang er geen regeleinde in een veld staat; `importMDB.sh` als geheel met nagebootste mdbtools en mongoimport (aantal records als teller) |
| `fixes_*.py` | Robuustheid van transformaties bij ontbrekende/ongeldige data |
| `synthetic_data.py` | Validatie dat de synthetische MDB-bestanden de juiste tabellen en kolomstructuur bevatten |
| `synthetic_monster_data.py` | Structuur, kolomaantallen, referentiële integriteit en projectverwijzingen van synthetische monsterdata |
| `fix_monster_projectcds.py` | Projectcode-matching logica voor de monsterdatabase (mocking van MongoDB) |
| `config_cache.py` | Cache-instellingen uit de echte `shared/config.py` zijn getallen en worden door cachelib geaccepteerd |
| `afgeleide_velden.py` | `herberekenAfgeleideVelden` (laadstap): SQL-opbouw, randgevallen op SQLite en gelijkheid met `init.init()` van de webapplicatie inclusief de observers uit `models.py` |
| `wachtwoord_maskeren.py` | `maskeerWachtwoord` (`shared/logutils.py`) voor PostgreSQL-, MongoDB- en Redis-URI's, wachtwoorden met bijzondere tekens, URI's zonder wachtwoord en lege waarden; `shared/database.py`, `shared/fulltext.py` en `loadAll` loggen de verbinding zonder wachtwoord (caplog) |
| `jupyter_image.py` | De Jupyter-image installeert `roman` (nodig voor de pipelinecode) en een Elasticsearch-client met de hoofd- en minorversie van de server uit `docker-compose.yml`; geen client met een hogere hoofdversie in de Flask- en Jupyter-constraints |
| `pakketversies.py` | `services/*/constraints.txt` bevatten alleen exacte versies; de Airflow-constraints leggen Airflow zelf niet vast, de Airflow-build houdt de pakketten van de basisimage op hun versie, installeert met constraints, draait `pip check` en controleert de versies; `apt-get` met retries in de Dockerfiles; `make constraints` kent Airflow en raakt geen draaiende containers |
| `verwerkingsrun.py`, `bronbestanden.py`, `opruimen.py`, `delta_transform.py` | Incrementeel laden: run-document, registratie en delta van bronbestanden, opruimen, delta-transformaties en stabiele sleutels (ook de samengestelde sleutel van artefacten) |
| `load_incrementeel.py` | Upsert-load (`loadIncrementeel`: upsert, verwijderen, FK-mechaniek, sequence, gebruikerstabellen ongemoeid, tellingen) en de Elasticsearch-delta (`indexTableIncrementeel`) met nagebootste databases |

### Integratietests

| Test | Wat wordt getest |
|------|-----------------|
| `test_full_pipeline.py` | Volledige harmonisatie-pipeline met directe MongoDB-seeding: harmonisatie, enhance, keys, move & merge, references |
| `test_full_pipeline_synthetic_data.py` | Volledige ETL via Airflow DAGs met synthetische MDB-data: extract, transform, verwachte aantallen per soort (inclusief monsters, botanische/schelpdeterminaties en referentietabellen), objectfoto's gekoppeld aan hun artefact en vondst (`artefactID`/`vondstID` in Single_Store_Clean en `Def_Bestand`), geen Transform 2-fouten voor foto's; een memo-veld met een regeleinde (spoor 4 van SY002) komt als één veld in de staging en in Single_Store_Clean, en geen staging-document heeft de extra kolommen van `importMDB.sh` midden in een ander veld (issue 74) |
| `test_full_pipeline_delft_data.py` | Zelfde pipeline maar met Delftse data en Delft-specifieke verwachte aantallen; objectfoto's met projectcode `DB034`, integers en een `artefactID`; het aantal staging-records met een regeleinde in een tekstveld per tabel, zonder de extra kolommen midden in een veld (issue 74) |
| `test_harmonize_pipeline.py` | Individuele harmonisatie-pipelines (Vondst, Spoor, alle objecttypen) |
| `test_importMDB_bash.py` | MDB-import shell-script: encoding-conversie, CSV-generatie, mongoimport |
| `test_incremental_synthetic_data.py` | Volledige cyclus gevolgd door vier incrementele runs (geen wijziging, nieuw project, vervangen database en verwijderde foto, verwijderd project): PostgreSQL, Elasticsearch, registratie en gebruikersdata |

## Nieuwe tests toevoegen

1. Maak een nieuw bestand aan in `tests/unit/` of `tests/integration/`
2. Gebruik `pytest.mark.unit` of `pytest.mark.integration` als marker
3. Gebruik `pytest.mark.delft` voor tests die Delftse data vereisen
4. De `conftest.py` mockt automatisch `shared.config` en laadt de echte `shared.const` en `shared.logutils`
5. Voor integratietests: gebruik de `mongo_client`, `staging_db` en `analyse_db` fixtures

## Opruimen

```bash
make clean          # verwijder .venv en caches
make clean-test-db  # stop test-database containers
```
