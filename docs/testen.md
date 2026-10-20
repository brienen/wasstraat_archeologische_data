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
│   ├── test_synthetic_data.py                # Validatie synthetische voorbeelddata
│   ├── test_synthetic_monster_data.py        # Validatie synthetische monsterdata
│   └── test_fix_monster_projectcds.py        # Projectcode-matching voor monsters
└── integration/
    ├── test_full_pipeline.py                 # Pipeline met directe MongoDB-seeding
    ├── test_full_pipeline_synthetic_data.py   # Volledige pipeline via Airflow (synthetische data)
    ├── test_full_pipeline_delft_data.py       # Volledige pipeline via Airflow (Delftse data)
    ├── test_harmonize_pipeline.py            # Harmonisatie met echte MongoDB
    └── test_importMDB_bash.py                # MDB-import en encoding in Docker
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
2. Start MongoDB 7.0, PostgreSQL 18 met PostGIS, Redis, Airflow en Flask in Docker (databases in tmpfs voor snelheid)
3. Mount de synthetische data als input-volumes
4. Triggert de Airflow DAGs (Extract, Transform, Load) en valideert de resultaten
5. Controleert verwachte aantallen per entiteitstype (sporen, vondsten, artefacten) in MongoDB en PostgreSQL
6. Draait de Flask smoke tests tegen de geladen database
7. Ruimt de containers en volumes op

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
| `harmonizer.py` | `getKolomValues` ($ifNull-ketens), `getAggrTables` (regex-matching), `loadHarmonizer` (Excel → DataFrame), pipeline-structuur ($match, $merge), overerving (Artefact→Aardewerk) |
| `foto_parsing.py` | Objectfoto-regex (met put/subnr/BP), tekening-types (A-E, P, T, LZW), projectfoto's (F/G), DAN/DAR rapporten, artefactsoort-detectie uit bestandspad |
| `encoding.py` | UTF-8 conversie, CP1252-detectie, dubbele CSV-headers |
| `fixes_*.py` | Robuustheid van transformaties bij ontbrekende/ongeldige data |
| `synthetic_data.py` | Validatie dat de synthetische MDB-bestanden de juiste tabellen en kolomstructuur bevatten |
| `synthetic_monster_data.py` | Structuur, kolomaantallen, referentiële integriteit en projectverwijzingen van synthetische monsterdata |
| `fix_monster_projectcds.py` | Projectcode-matching logica voor de monsterdatabase (mocking van MongoDB) |
| `config_cache.py` | Cache-instellingen uit de echte `shared/config.py` zijn getallen en worden door cachelib geaccepteerd |

### Integratietests

| Test | Wat wordt getest |
|------|-----------------|
| `test_full_pipeline.py` | Volledige harmonisatie-pipeline met directe MongoDB-seeding: harmonisatie, enhance, keys, move & merge, references |
| `test_full_pipeline_synthetic_data.py` | Volledige ETL via Airflow DAGs met synthetische MDB-data: extract, transform, verwachte aantallen per soort (inclusief monsters, botanische/schelpdeterminaties en referentietabellen) |
| `test_full_pipeline_delft_data.py` | Zelfde pipeline maar met Delftse data en Delft-specifieke verwachte aantallen |
| `test_harmonize_pipeline.py` | Individuele harmonisatie-pipelines (Vondst, Spoor, alle objecttypen) |
| `test_importMDB_bash.py` | MDB-import shell-script: encoding-conversie, CSV-generatie, mongoimport |

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
