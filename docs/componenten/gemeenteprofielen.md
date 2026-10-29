# Gemeenteprofielen

## Overzicht

Het profielensysteem maakt het mogelijk om de Wasstraat in te zetten voor verschillende gemeenten zonder de kerncode aan te passen. Elke gemeente kan een eigen profiel definiëren dat de gemeente-specifieke logica voor herkenning, normalisatie en identificatie van entiteiten bevat.

Het profiel regelt twee typen logica:

- **Bestands-entiteiten** (Foto, Tekening, Rapport) — parsing van bestandsnamen naar velden
- **Database-entiteiten** (Project, Put, Vlak, Spoor, Vondst, Artefact, Monster, Doos, …) — normalisatie en identificatie van velden die uit de harmonisatie komen

## Structuur

```
airflow_app/dags/wasstraat/profielen/
├── __init__.py        # get_profiel() + reset_profiel()
├── conventie.py       # Basisprofiel: directe velden, geen transformatie
├── delft.py           # Delft-specifiek profiel
└── voorbeeld.py       # PoC profiel: erft ConventieProfiel ongewijzigd
```

## Profielselectie

Het actieve profiel wordt bepaald door de omgevingsvariabele `WASSTRAAT_GEMEENTE`:

```bash
WASSTRAAT_GEMEENTE=delft    # standaard als niet ingesteld
WASSTRAAT_GEMEENTE=voorbeeld
```

De `get_profiel()` functie laadt het profiel éénmalig en cachet het resultaat:

```python
from wasstraat.profielen import get_profiel

profiel = get_profiel()   # geeft altijd hetzelfde object terug
```

Als `WASSTRAAT_GEMEENTE` niet is ingesteld of leeg is, wordt `delft` gebruikt. Hoofdletters en spaties maken niet uit. Een andere waarde dan `delft` of `voorbeeld` geeft de fout `Onbekend gemeenteprofiel` (`ConventieProfiel` is de basisklasse en niet zelf te kiezen; `voorbeeld` gedraagt zich precies zo).

Waar je de variabele zet:

| Omgeving | Plek |
|----------|------|
| Ontwikkelomgeving, `make delft` | `environment:` van de service `airflow` in `docker-compose.delft.yml` (staat op `delft`) |
| Ontwikkelomgeving, `make app` | Niet gezet, dus `delft`; voeg een `environment:`-regel toe in `docker-compose.yml` om te wisselen |
| Live installatie | `WASSTRAAT_GEMEENTE` in `deploy/.env` |

Een `environment:`-regel in het compose-bestand gaat vóór dezelfde variabele in `config/airflow.env`. Het profiel wordt alleen door Airflow gebruikt (Transform 1 en 2). Maak na een wijziging de Airflow-container opnieuw aan en draai de volledige cyclus. Zie ook [Configuratie](configuratie.md#5-gemeenteprofiel).

## ConventieProfiel (basisprofiel)

`ConventieProfiel` is de basisklasse waarvan alle profielen erven. Het implementeert een standaard-aanpak: velden uit de brondata worden direct overgenomen zonder transformatie.

### IDENTIFICERENDE_VELDEN

De klasse documenteert expliciet welke velden elke entiteit identificeren:

```python
IDENTIFICERENDE_VELDEN = {
    'Project':     {'verplicht': ['projectcd'],                                         'integer': []},
    'Put':         {'verplicht': ['projectcd', 'putnr'],                                'integer': ['putnr']},
    'Vlak':        {'verplicht': ['projectcd', 'vlaknr'],       'optioneel': ['putnr'], 'integer': ['putnr', 'vlaknr']},
    'Spoor':       {'verplicht': ['projectcd', 'spoornr'],      'optioneel': ['putnr', 'vlaknr'], 'integer': ['putnr', 'vlaknr', 'spoornr']},
    'Vondst':      {'verplicht': ['projectcd', 'vondstnr'],     'optioneel': ['putnr'], 'integer': ['putnr', 'vondstnr']},
    'Artefact':    {'verplicht': ['projectcd', 'artefactnr'],   'optioneel': ['putnr', 'vondstnr', 'splitid'], 'integer': ['putnr', 'vondstnr', 'artefactnr', 'subnr']},
    'Monster':     {'verplicht': ['projectcd', 'monstercd'],                            'integer': []},
    'Doos':        {'verplicht': ['doosnr'],                    'optioneel': ['projectcd'],           'integer': ['doosnr']},
    'Foto':        {'verplicht': ['projectcd'],                 'optioneel': ['putnr', 'vondstnr', 'subnr', 'fotonr'], 'integer': ['putnr', 'vondstnr', 'subnr', 'fotonr']},
    'Tekening':    {'verplicht': ['projectcd', 'tekeningcd'],                           'integer': []},
    'Rapport':     {'verplicht': ['rapportnr'],                 'optioneel': ['projectcd'],           'integer': []},
    'Standplaats': {'verplicht': ['stelling'],                  'optioneel': ['vaknr', 'volgletter'], 'integer': []},
}
```

### Dispatcher: identificeer()

De centrale methode `identificeer(soort, doc)` delegeert naar de juiste per-entiteit methode:

```python
profiel.identificeer('Put', doc)       # → identificeer_put(doc)
profiel.identificeer('Artefact', doc)  # → identificeer_artefact(doc)
profiel.identificeer('Vondst', doc)    # → identificeer_vondst(doc)
profiel.identificeer('Foto', doc)      # → identificeer_foto_db(doc)
profiel.identificeer('Tekening', doc)  # → identificeer_tekening_db(doc)
profiel.identificeer('Rapport', doc)   # → identificeer_rapport_db(doc)
```

Bij een onbekend soort wordt de standaard-methode gebruikt: normaliseer `projectcd` + converteer integer-velden.

Voor de bestands-entiteiten (`const.BESTANDSOORTEN`: Foto, Tekening, Rapport) kiest de dispatcher de `_db`-variant. De methode zonder `_db` is voor die soorten de bestandsnaam-parser met twee argumenten (`identificeer_foto(doc, projectcd)`), die alleen `parseFotobestanden()` aanroept. Tot oktober 2026 koos de dispatcher voor `Foto` die parser; elke foto gaf dan een `TypeError` in Transform 2, hield zijn ongenormaliseerde projectcode (`DB34` in plaats van `DB034`) en tekstnummers, en werd in Transform 4 nooit aan een artefact gekoppeld.

### Per-entiteit methoden

Elke entiteit heeft een eigen methode die de identificerende velden normaliseert:

| Methode | Werking (standaard) |
|---------|---------------------|
| `identificeer_project(doc)` | Normaliseer `projectcd` |
| `identificeer_put(doc)` | Normaliseer `projectcd` + `putnr` → int |
| `identificeer_vlak(doc)` | Normaliseer `projectcd` + `putnr`, `vlaknr` → int |
| `identificeer_spoor(doc)` | Normaliseer `projectcd` + integers |
| `identificeer_vondst(doc)` | Normaliseer `projectcd` + `putnr`, `vondstnr` → int |
| `identificeer_artefact(doc)` | Normaliseer `projectcd` + integers (`vondstnr` optioneel) |
| `identificeer_monster(doc)` | Normaliseer `projectcd` |
| `identificeer_doos(doc)` | Normaliseer `projectcd` (optioneel) + `doosnr` → int |
| `identificeer_foto_db(doc)` | Normaliseer `projectcd` + `putnr`, `vondstnr`, `subnr`, `fotonr` → int (dezelfde `key_foto1`/`key_foto3` als het artefact) |
| `identificeer_tekening_db(doc)` | Normaliseer `projectcd` + `tekeningcd` via `normaliseer_tekeningcode()` |
| `identificeer_rapport_db(doc)` | Normaliseer `projectcd` + `rapportnr` via `normaliseer_rapportnr()` |
| `identificeer_foto(doc, projectcd)` | Bestandsnaam-parser; standaard: `None` (niet herkend) |
| `identificeer_tekening(doc, projectcd)` | Bestandsnaam-parser; standaard: `None` (niet herkend) |

### Normalisatie-helpers

```python
profiel.normaliseer_projectcode("dc016")    # standaard: passthrough → "dc016"
profiel.normaliseer_tekeningcode("B2")      # standaard: passthrough → "B2"
profiel.normaliseer_rapportnr("DAR123", {}) # standaard: passthrough → "DAR123"
profiel.detecteer_artefactsoort("/fotos/aardewerk/test.jpg")  # → const.ARTF_AARDEWERK
```

`detecteer_artefactsoort()` is gemeenteonafhankelijk en matcht op keywords in het bestandspad (`aardewerk`, `glas`, `metaal`, `bot`, etc.).

## DelftProfiel

`DelftProfiel` erft van `ConventieProfiel` en overschrijft de Delft-specifieke methoden.

### Projectcode-normalisatie

Delftse projectcodes volgen het patroon `[2 letters][3 cijfers]`, bijv. `DC016`, `DB034`:

```python
profiel.normaliseer_projectcode("dc-16")  # → "DC016"
profiel.normaliseer_projectcode("DC016")  # → "DC016"
profiel.normaliseer_projectcode("dc16")   # → "DC016"
profiel.normaliseer_projectcode("DB")     # → "DB"  (geen cijfers → geen padding)
```

### Tekeningcode-normalisatie

Tekeningcodes volgen het patroon `[letter][3 cijfers]`:

```python
profiel.normaliseer_tekeningcode("B2")    # → "B002"
profiel.normaliseer_tekeningcode("A15")   # → "A015"
profiel.normaliseer_tekeningcode("B002")  # → "B002"
profiel.normaliseer_tekeningcode("tekst") # → "tekst"  (geen match → passthrough)
```

### Rapportnummer-normalisatie

Delftse rapportnummers gebruiken de prefixen `DAR` (Delft Archeologisch Rapport) of `DAN` (Delft Archeologische Notitie):

```python
profiel.normaliseer_rapportnr("DAR 123", {})           # → "DAR123"
profiel.normaliseer_rapportnr("45", {"DARnr": 45})     # → "DAR045"
profiel.normaliseer_rapportnr("7", {"DANnr": 7})       # → "DAN007"
profiel.normaliseer_rapportnr("123", {})               # → ""  (prefix onbekend)
```

### Bestandsnaam-parsing: foto's

Het DelftProfiel herkent twee patronen:

**Objectfoto's** (`_H` patroon):

```
DC001_P3_H456_789_002.jpg
  │    │   │   │   └── fotonr: 2
  │    │   │   └────── subnr: 789
  │    │   └────────── vondstnr: 456
  │    └────────────── putnr: 3
  └─────────────────── projectcd: DC001
```

**Projectfoto's** (`F`/`G` patroon):

```
DC001_F001.jpg   → bestandsoort: FOTO_SFEERFOTO
DC001_G002.jpg   → bestandsoort: FOTO_OPGRAVINGSFOTO
```

### Bestandsnaam-parsing: tekeningen

Tekeningtypes worden bepaald door de letter in de bestandsnaam:

| Letter | Type |
|--------|------|
| `A` | Bouwtekening |
| `B` | Veldtekening |
| `C` | Overzichtstekening |
| `D` | Objecttekening |
| `E` | Uitwerkingstekening |
| `P` | Veldtekening (publicatie) |
| `T` | Objecttekening (publicatie) |

Voorbeeld: `DC001_B002.tif` → tekeningcd: `B002`, bestandsoort: `TEK_VELDTEKENING`.

### Artefactsoort uit typevoorwerp

Als `artefactsoort` nog niet is ingesteld, leidt het DelftProfiel deze af uit het `typevoorwerp`-veld:

- `Kleipijp` → `'Kleipijp'`
- Patroon `^[a-z]{1,2}(_|-)` → `'Aardewerk'`
- Patroon `^gl(_|-)` → `'Glas'`

### Bestands-entiteiten vanuit de database

Voor Foto-, Tekening- en Rapport-records in Transform 2 (uit de harmonisatie én uit `parseFotobestanden()`) kiest de dispatcher de `_db`-varianten. Het DelftProfiel overschrijft er twee:

```python
doc = profiel.identificeer('Foto', doc)      # identificeer_foto_db: geërfd, DB34 → DB034 en nummers → int
doc = profiel.identificeer('Tekening', doc)  # identificeer_tekening_db: tekeningcd normaliseren
doc = profiel.identificeer('Rapport', doc)   # identificeer_rapport_db: rapportnr normaliseren
```

### Projectcode uit bestandsnaam

```python
profiel.extract_projectcode_uit_bestandsnaam("DC001_F001.jpg", "/map")     # → "DC001"
profiel.extract_projectcode_uit_bestandsnaam("test.jpg", "/DC045/fotos")  # → "DC045"  (via directory)
```

Als noch de bestandsnaam noch de directory een `DB`/`DC`-prefix bevat, wordt de eerste alfanumerieke reeks uit de bestandsnaam teruggegeven.

## VoorbeeldProfiel

`VoorbeeldProfiel` is een minimaal PoC-profiel dat volledig erft van `ConventieProfiel` zonder aanpassingen. Het dient als startpunt voor een nieuwe gemeente die de standaardconventie wil volgen:

```python
class VoorbeeldProfiel(ConventieProfiel):
    naam = "voorbeeld"
```

## Nieuw profiel toevoegen

Om een profiel voor een nieuwe gemeente toe te voegen:

1. **Maak een nieuw bestand** `airflow_app/dags/wasstraat/profielen/[gemeente].py`:

```python
from wasstraat.profielen.conventie import ConventieProfiel

class MijnGemeenteProfiel(ConventieProfiel):
    naam = "mijn_gemeente"

    def normaliseer_projectcode(self, projectcd):
        # Gemeente-specifieke normalisatie
        return projectcd.upper()
```

2. **Registreer het profiel** in `airflow_app/dags/wasstraat/profielen/__init__.py`:

```python
elif gemeente == 'mijn_gemeente':
    from wasstraat.profielen.mijn_gemeente import MijnGemeenteProfiel
    _profiel_cache = MijnGemeenteProfiel()
```

3. **Stel de omgevingsvariabele in** (zie [Profielselectie](#profielselectie) voor de plek per omgeving):

```bash
WASSTRAAT_GEMEENTE=mijn_gemeente
```

   Een nieuw profiel bestaat alleen in de code; voor de live installatie is het dus pas bruikbaar in een nieuwe versie van de images.

4. **Schrijf unit tests** in `tests/unit/test_profielen.py` voor de nieuwe klasse.

## Gebruik in de pipeline

Het profiel wordt op twee plaatsen aangeroepen:

### parseFotobestanden() — bestandsnaam-parsing

```python
profiel = get_profiel()
projectcd = profiel.extract_projectcode_uit_bestandsnaam(doc['fileName'], doc.get('directory', ''))

parsed = profiel.identificeer_foto(doc, projectcd)
if parsed is not None:
    # Foto-record opslaan
    continue

parsed = profiel.identificeer_tekening(doc, projectcd)
if parsed is not None:
    # Tekening-record opslaan
    continue
```

### enhanceAllAttributes() — entiteit-identificatie

```python
profiel = get_profiel()
soort = doc.get('soort', '')

# De dispatcher kiest per soort de methode; voor Foto, Tekening en Rapport
# de _db-variant en niet de bestandsnaam-parser.
doc = profiel.identificeer(soort, doc)
```
