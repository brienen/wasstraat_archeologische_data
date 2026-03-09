# Testen

De Wasstraat heeft een testsuite met twee niveaus: unit tests voor individuele functies en integratietests die de volledige harmonisatie-pipeline testen met een echte MongoDB.

## Structuur

```
tests/
├── setup_venv.sh                        # Maakt .venv aan met alle dependencies
├── conftest.py                          # Mocks voor shared.config, roman, etc.
├── run_tests.py                         # Fallback runner (zonder pytest/venv)
├── run_integration.sh                   # Start databases + draait integratietests
├── unit/
│   ├── test_archutils.py                # convertToInt, convertToBool, fixDatering
│   ├── test_rijksdriehoek.py            # RD ↔ WGS84 coördinaatconversie
│   ├── test_harmonizer.py               # Pipeline-opbouw uit Excel config
│   └── test_foto_parsing.py             # Regex-patronen voor bestandsclassificatie
└── integration/
    └── test_harmonize_pipeline.py       # Harmonisatie met echte MongoDB
```

## Venv opzetten

De tests draaien in een Python virtual environment. Dit hoeft maar één keer:

```bash
./tests/setup_venv.sh
source .venv/bin/activate
```

Het script zoekt automatisch naar Python 3.11, 3.12 of 3.10 en installeert alle dependencies uit `requirements-test.txt` (pytest, pandas, numpy, openpyxl, roman, pymongo, etc.).

## Unit tests draaien

```bash
source .venv/bin/activate
python -m pytest tests/unit/ -v
```

Of één specifieke module:

```bash
python -m pytest tests/unit/test_archutils.py -v
python -m pytest tests/unit/test_rijksdriehoek.py -v
```

### Fallback zonder venv

Als je geen venv wilt gebruiken en de basispackages (pandas, numpy, openpyxl) al beschikbaar zijn:

```bash
python3 tests/run_tests.py
```

Deze runner bevat een pytest-stub die `@pytest.mark.parametrize` ondersteunt en draait alle tests met het standaard `unittest`-framework. De mocks voor `roman` en `timeperiod2daterange` worden automatisch geladen.

## Integratietests draaien

De integratietests gebruiken een aparte `docker-compose.test.yml` met een lichtgewicht MongoDB en PostgreSQL op afwijkende poorten (27117 en 5433) zodat ze niet conflicteren met de productie-omgeving.

```bash
./tests/run_integration.sh
```

Dit script:

1. Activeert de `.venv` (als die bestaat)
2. Start MongoDB 4.2 en PostgreSQL 13 in Docker (tmpfs voor snelheid)
3. Wacht tot beide databases beschikbaar zijn
4. Draait de integratietests met pytest
5. Ruimt de containers en volumes op

### Handmatig

```bash
# 1. Start test-databases
docker compose -f docker-compose.test.yml up -d

# 2. Draai tests
source .venv/bin/activate
MONGO_TEST_URI="mongodb://testroot:testpass@localhost:27117/" \
PYTHONPATH="airflow_app/dags:." \
python -m pytest tests/integration/ -v -m integration

# 3. Opruimen
docker compose -f docker-compose.test.yml down -v
```

## Wat wordt getest?

### Unit tests (127 tests)

| Module | Wat wordt getest |
|--------|-----------------|
| `archutils.py` | `convertToInt` (type-conversie, force/no-force), `convertToBool` (ja/nee/true/false), `fixDatering` (eeuw-kwart notatie, Romeinse cijfers, LMEb, RT, gecombineerde dateringen) |
| `rijksdriehoek.py` | RD→WGS84 conversie met referentiepunten (Amsterdam, Rotterdam, Maastricht, Delft), WGS84→RD inversie, roundtrip-nauwkeurigheid |
| `harmonizer.py` | `getKolomValues` ($ifNull-ketens), `getAggrTables` (regex-matching), `loadHarmonizer` (Excel → DataFrame), pipeline-structuur ($match, $merge), overerving (Artefact→Aardewerk) |
| foto parsing | Objectfoto-regex (met put/subnr/BP), tekening-types (A-E, P, T, LZW), projectfoto's (F/G), DAN/DAR rapporten, artefactsoort-detectie uit bestandspad |

### Integratietests

De integratietests plaatsen testdocumenten in MongoDB en draaien de harmonisatie-pipeline:

- Vondst-harmonisatie: controleert dat de pipeline draait en output produceert
- Spoor-harmonisatie: controleert dat spoor-documenten correct verwerkt worden
- Alle objecttypen: draait alle standaard pipelines om te controleren dat ze geldig zijn

## Nieuwe tests toevoegen

1. Maak een nieuw bestand aan in `tests/unit/` of `tests/integration/`
2. Gebruik `pytest.mark.unit` of `pytest.mark.integration` als marker
3. De `conftest.py` mockt automatisch `shared.config` en `shared.const`
4. Voor integratietests: gebruik de `mongo_client`, `staging_db` en `analyse_db` fixtures
