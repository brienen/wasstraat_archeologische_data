# Testen

De Wasstraat heeft een testsuite met twee niveaus: unit tests voor individuele functies en integratietests die de volledige harmonisatie-pipeline testen met een echte MongoDB.

## Quickstart

```bash
make install    # eenmalig: maakt .venv aan met alle dependencies
make test       # draai unit tests
make integration # draai integratietests (start/stopt Docker automatisch)
```

Typ `make help` voor alle beschikbare targets.

## Structuur

```
Makefile                                 # Alle commando's (make help)
requirements-test.txt                    # Python test-dependencies
docker-compose.test.yml                  # Lichtgewicht test-databases
tests/
├── conftest.py                          # Mocks voor shared.config, roman, etc.
├── run_tests.py                         # Fallback runner (zonder venv/pytest)
├── unit/
│   ├── test_archutils.py                # convertToInt, convertToBool, fixDatering
│   ├── test_rijksdriehoek.py            # RD ↔ WGS84 coördinaatconversie
│   ├── test_harmonizer.py               # Pipeline-opbouw uit Excel config
│   └── test_foto_parsing.py             # Regex-patronen voor bestandsclassificatie
└── integration/
    └── test_harmonize_pipeline.py       # Harmonisatie met echte MongoDB
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

```bash
make integration
```

Dit target:

1. Maakt de `.venv` aan als die nog niet bestaat
2. Start MongoDB 4.2 en PostgreSQL 13 in Docker (tmpfs voor snelheid, poorten 27117/5433)
3. Wacht tot beide databases beschikbaar zijn
4. Draait de integratietests met pytest
5. Ruimt de containers en volumes op

### Handmatig

```bash
docker compose -f docker-compose.test.yml up -d

source .venv/bin/activate
MONGO_TEST_URI="mongodb://testroot:testpass@localhost:27117/" \
python -m pytest tests/integration/ -v -m integration

docker compose -f docker-compose.test.yml down -v
```

## Wat wordt getest?

### Unit tests (128 tests)

| Module | Wat wordt getest |
|--------|-----------------|
| `archutils.py` | `convertToInt` (type-conversie, force/no-force), `convertToBool` (ja/nee/true/false), `fixDatering` (eeuw-kwart notatie, Romeinse cijfers, LMEb, RT, gecombineerde dateringen) |
| `rijksdriehoek.py` | RD→WGS84 conversie met referentiepunten (Amsterdam, Rotterdam, Maastricht, Delft), WGS84→RD inversie, roundtrip-nauwkeurigheid |
| `harmonizer.py` | `getKolomValues` ($ifNull-ketens), `getAggrTables` (regex-matching), `loadHarmonizer` (Excel → DataFrame), pipeline-structuur ($match, $merge), overerving (Artefact→Aardewerk) |
| foto parsing | Objectfoto-regex (met put/subnr/BP), tekening-types (A-E, P, T, LZW), projectfoto's (F/G), DAN/DAR rapporten, artefactsoort-detectie uit bestandspad |

### Integratietests (4 tests)

De integratietests plaatsen testdocumenten in MongoDB en draaien de harmonisatie-pipeline:

- Vondst-harmonisatie: controleert dat de pipeline draait en output produceert met correcte structuur
- Spoor-harmonisatie: controleert dat spoor-documenten correct verwerkt worden
- Alle objecttypen: draait alle standaard pipelines om te controleren dat ze geldig zijn

## Nieuwe tests toevoegen

1. Maak een nieuw bestand aan in `tests/unit/` of `tests/integration/`
2. Gebruik `pytest.mark.unit` of `pytest.mark.integration` als marker
3. De `conftest.py` mockt automatisch `shared.config` en `shared.const`
4. Voor integratietests: gebruik de `mongo_client`, `staging_db` en `analyse_db` fixtures

## Opruimen

```bash
make clean          # verwijder .venv en caches
make clean-test-db  # stop test-database containers
```
