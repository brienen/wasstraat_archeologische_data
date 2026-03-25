# Wasstraat v2: Generalisatie en incrementeel laden

## Samenvatting

De Wasstraat is gebouwd als Delft-specifieke batch-pipeline. Om het platform bruikbaar te maken voor andere gemeenten en schaalbaar voor groeiende datasets, zijn vijf samenhangende wijzigingen nodig: multi-architectuur Docker-ondersteuning, een profielensysteem voor sleutelafleiding, externalisering van hard-coded Delft-logica, synthetische voorbeelddata, en incrementeel laden.

---

## 1. Multi-architectuur Docker en productie-deployment

### Probleem

De Docker images zijn alleen gebouwd voor Mac (ARM) en draaien op verouderde base images. Er ontbreekt een eenvoudige manier om productiecontainers te deployen zonder de volledige repository te clonen.

### Oplossing

1. **Multi-architectuur support** — Docker images bouwen voor zowel ARM als x86_64 (linux/amd64).
2. **Base images upgraden** — Verouderde base images vervangen door actuele versies.
3. **Productie-deployment via Make** — `make`-target toevoegen dat productiecontainers bouwt en pusht naar de Wasstraat Docker-repo.
4. **Volume mounts voor I/O** — Productiecontainers moeten data kunnen lezen en output schrijven via directories op de host.
5. **Standalone gebruiksdocumentatie** — Beschrijving van hoe je alleen de productiecontainers draait met een losse `docker-compose.prod.yml`, zonder de hele repo.
6. **Command-line installer** — Script dat de benodigde compose-bestanden ophaalt en de productieomgeving opzet.

---

## 2. Profielensysteem voor sleutelafleiding

### Probleem

De logica voor het afleiden van primaire sleutels (projectcodes, fotonamen, vondst-ID's, etc.) is verspreid over meerdere packages en hard-coded op de conventies van de gemeente Delft. Hierdoor is de Wasstraat niet herbruikbaar voor andere gemeenten die andere naamgevingsconventies hanteren, en zijn de afleidingsregels lastig te onderhouden.

### Oplossing

1. **Centraliseer sleutelafleiding** — Verzamel alle logica voor het herkennen en ontrafelen van primaire sleutels (projectcodes, fotonamen, artefact-ID's, etc.) op één plek in de codebase.
2. **Profielensysteem** — Maak de afleidingsregels configureerbaar per gemeente. Het huidige gedrag wordt het profiel "Delft".
3. **Ondersteuning voor directe referenties** — Naast afleiding uit bestandsnamen of samengestelde velden ook ondersteuning bieden voor brondata die al expliciete kolommen bevat (projectcode, putcode, etc.), zodat afleiding overgeslagen kan worden.
4. **Nieuw profiel** — Minimaal één extra profiel uitwerken naast Delft als proof of concept.

### Alternatieven voor implementatie

**A. Hardcoded profielen in Python** — Eén module (`wasstraat/profiles/`) met per gemeente een Python-bestand dat een vast interface (`SleutelProfiel`) implementeert. Volledige flexibiliteit voor arbitraire afleidingslogica. Elke nieuwe gemeente vereist een developer, maar dat is realistisch: de kans dat een niet-technische gemeente-medewerker zelf profielen schrijft is klein.

**B. Hybride: convention + overrides** — Een standaardprofiel dat uitgaat van de simpelste case (directe kolommen zoals `projectcode`, `putcode`). Alleen uitzonderingen worden geconfigureerd. Houdt de configuratie minimaal; gemeenten die netjes kolommen aanleveren hoeven niets te definiëren.

**C. YAML-configuratie** — Profielen volledig declaratief in YAML: regex-patronen, kolomnamen en afleidingsregels per objecttype. Nieuwe gemeenten toevoegen zonder code te schrijven. Risico: regex in YAML wordt snel onleesbaar, en zodra afleidingslogica conditioneel wordt bouw je een mini-DSL die lastig te onderhouden is.

**D. Plugin-architectuur** — Profielen als installeerbare Python-packages die zich registreren via `setuptools` entry points. Meest schaalbaar, maar alleen zinvol bij tientallen gemeenten.

**Aanbeveling:** optie A of B. Python-code wint van YAML op leesbaarheid, testbaarheid en flexibiliteit voor de doelgroep (developers). De hybride variant (B) is het pragmatischst als het merendeel van toekomstige gemeenten gestructureerde brondata aanlevert.

### Context

Voorbeelden van huidige afleidingslogica in het Delft-profiel:

- Projectcode: 2 letters + 3 cijfers (bijv. `DH045`)
- Fotonaam: regex `^([a-zA-Z0-9]+)(_B?P([0-9Xx]+))?_H([a-zA-Z0-9]+)(_([a-zA-Z0-9]+))?_([0-9Xx]+)\.[a-z]{3}$`

---

## 3. Externalisering van hard-coded Delft-logica

### Probleem

De broncode bevat op meerdere plekken hard-coded Delft-specifieke logica: projectcode-correcties, bestandsnaam-mappings en datafix-statements die direct verwijzen naar Delftse opgravingen (DC027, DC018, DC039, etc.). Dit maakt de code onbruikbaar voor andere gemeenten zonder deze regels handmatig aan te passen, en mengt dataproblemen met applicatielogica.

### Oplossing

1. **Inventariseer alle hard-coded Delft-referenties** — Doorzoek de codebase systematisch op gemeente-specifieke waarden: projectcodes, bestandsnaam-patronen, update-statements en overige Delft-specifieke correcties.
2. **Verplaats naar databestanden** — Extraheer deze waarden naar configuratiebestanden (bijv. YAML of CSV) die per gemeente de correctieregels beschrijven: bron-patroon → doel-waarde.
3. **Generaliseer de code** — Vervang hard-coded statements door een generiek mechanisme dat de correctieregels uit het databestand inleest en toepast, onafhankelijk van de gemeente.
4. **Validatie** — Controleer dat de pipeline met het Delft-correctiebestand identieke resultaten oplevert als de huidige hard-coded versie.

### Alternatieven

**A. Correctiebestanden (YAML/CSV)** — Eén bestand per gemeente met regels als `{bron_patroon: "DC027_Voorstraat", veld: "project", waarde: "DC027"}`. Eenvoudig te begrijpen en te bewerken, ook voor niet-developers. Beperking: alleen geschikt voor simpele patroon→waarde-mappings.

**B. Correctielogica in Python per gemeente** — Vergelijkbaar met het profielensysteem: een Python-module per gemeente die een `fix_project_names()`-interface implementeert. Meer flexibiliteit voor complexe correcties, maar vereist een developer voor elke nieuwe gemeente.

**C. Correcties in de brondata oplossen** — De problemen in de Access-databases zelf fixen in plaats van in de pipeline. Elimineert de noodzaak voor runtime-correcties, maar is niet altijd mogelijk (bronbestanden zijn soms read-only of worden extern beheerd).

**Aanbeveling:** optie A voor eenvoudige mappings (het gros van de huidige gevallen), met optie B als fallback voor correcties die niet declaratief uit te drukken zijn.

### Context

Voorbeeld van huidige hard-coded logica in `fixProjectNames()`:

```python
# Bestandsnaam → projectcode correcties
stagingcollection.update_many(
    {"mdbfile": {"$regex": "DC027_Voorstraat"}},
    {"$set": {"project": "DC027"}})

# Projectcode-aliassen
monstercollection.update_many(
    {"PROJECT": {"$regex": "SCHE"}},
    {"$set": {"PROJECT": "DC039"}})
```

Dit soort regels zou er in een correctiebestand zo uitzien:

```yaml
# correcties_delft.yml
projectcode_fixes:
  - bron_veld: mdbfile
    patroon: "DC027_Voorstraat"
    doel_veld: project
    waarde: "DC027"
  - bron_veld: PROJECT
    patroon: "SCHE"
    doel_veld: PROJECT
    waarde: "DC039"
```

---

## 4. Synthetische voorbeelddata

### Probleem

De repo bevat echte opgravingsdata uit Delft. Dit heeft twee nadelen: de data kan niet publiek gedeeld worden zonder privacyoverwegingen, en andere gemeenten krijgen geen neutraal voorbeeld van hoe een werkende dataset eruitziet.

### Oplossing

1. **Synthetische dataset genereren** — Op basis van de bestaande MDB-tabelstructuren (projectdatabases, C Database, DigiFotolijst, Magazijnlijst) een fictieve maar realistische dataset genereren die dezelfde tabelstructuren, kolomnamen, relaties en datapatronen bevat, maar niet herleidbaar is naar Delft.
2. **Meerdere voorbeeldscenario's** — Minimaal twee voorbeeldprojecten uitwerken met variatie in complexiteit: een klein project (enkele putten, beperkte vondsten) en een groter project (meerdere vlakken, artefactsubtypen, foto's, tekeningen).
3. **Meeleveren met de repo** — De synthetische data opnemen als standaard voorbeelddata, zodat de applicatie out-of-the-box een werkende demo heeft.
4. **Echte Delftse data verwijderen** — De huidige bronbestanden uit de repo verwijderen en alleen via de gemeente beschikbaar stellen.

### Alternatieven

**A. Handmatig geanonimiseerd** — De bestaande Delftse data anonimiseren door projectcodes, locaties en namen te vervangen. Risico: bij onvolledige anonimisering blijft data herleidbaar; lastig te onderhouden bij updates.

**B. Volledig synthetisch gegenereerd** — Data programmatisch genereren (bijv. met Python Faker/Pandas) op basis van de tabelstructuren en waardepatronen uit de huidige brondata. Geen herleidbaarheid, reproduceerbaar, schaalbaar naar meerdere voorbeeldscenario's. Vereist eenmalige investering in een generatorscript.

**C. Minimale seed-data** — Alleen het absolute minimum aan records opnemen dat nodig is om de pipeline succesvol te doorlopen (vergelijkbaar met de huidige integratietest-fixtures). Lichtgewicht, maar geeft geen representatief beeld van een echte dataset.

**Aanbeveling:** optie B. Een generatorscript is herbruikbaar, kan meegroeien met het datamodel, en kan ook dienen als basis voor geautomatiseerde tests.

### Context

De huidige brondata omvat onder andere: `opgravingDC36.mdb` (912 KB), `AW 1-9.mdb` (272 KB), referentietabellen (ABR, magazijn, schelpen). De integratietests bevatten al synthetische MongoDB-documenten (`SAMPLE_VONDST_DOCS`, `SAMPLE_SPOOR_DOCS`) die als startpunt kunnen dienen. Terugschrijven naar MDB-formaat is niet triviaal (mdbtools is read-only); CSV of SQLite als bronformaat is een pragmatisch alternatief dat compatibel is met de bestaande importpipeline.

---

## 5. Incrementeel laden (delta-verwerking)

### Probleem

De Wasstraat ondersteunt uitsluitend een volledige run waarbij alle databases worden leeggemaakt en opnieuw opgebouwd vanuit de bronbestanden. Bij ~1 TB aan data is dat voor het toevoegen van een handvol nieuwe opgravingen disproportioneel. Er is geen mogelijkheid om aanvullingen (nieuwe projecten, vondsten, foto's) toe te voegen aan een bestaande, draaiende database.

### Oplossing

Een incrementeel laadmechanisme waarbij aangeboden bronbestanden als delta worden behandeld: alles wat wordt aangeboden wordt verwerkt en samengevoegd met de bestaande data. Dit geldt voor alle objecttypen.

1. **Bestandsregistratie met hash** — Bij elke verwerking wordt een SHA-256 hash van het bronbestand opgeslagen (nieuwe tabel `Def_Bronbestand`). Bij een volgende aanbieding bepaalt de hash het scenario:
   - *Nieuw bestand* (onbekende naam) — Volledig verwerken en samenvoegen.
   - *Gewijzigd bestand* (zelfde naam, andere hash) — Oude records van dit bestand verwijderen, opnieuw verwerken.
   - *Ongewijzigd bestand* (zelfde hash) — Overslaan.
2. **Incrementele transformatie** — De transform-stappen draaien alleen op de aangeboden delta-data en voegen het resultaat samen met de bestaande analyse-collectie.
3. **Upsert in plaats van replace** — PostgreSQL-load via `INSERT ... ON CONFLICT ... DO UPDATE`. Elasticsearch via incrementele bulk-upsert.
4. **Stabiele sleutels** — Composite keys en integer `primary_key` blijven stabiel tussen runs.

### Alternatieven: bron van waarheid

De kernvraag is welke datalaag leidend is bij het samenvoegen van delta-data met bestaande data.

**A. MongoDB staging als bron van waarheid** — Nieuwe bestanden importeren in de bestaande staging-collecties (zonder `dropAll`). Het `mdbfile`-veld en de bestandshash markeren welke documenten bij welk bronbestand horen. Bij een gewijzigd bestand: oude documenten met dat `mdbfile` verwijderen, nieuwe importeren. Alleen de nieuwe/gewijzigde documenten door de transformatie-pipeline sturen en via `$merge` samenvoegen met `COLL_ANALYSE_CLEAN`. Voordeel: de staging-laag bevat altijd de volledige ruwe data en is herstelbaar. Nadeel: de merge-stap (`$group`) werkt nu alleen op documenten binnen dezelfde aggregation pipeline — nieuwe records vinden hun bestaande duplicaten niet zonder aanpassing.

**B. PostgreSQL als bron van waarheid** — De bestaande PostgreSQL-data als leidend beschouwen. Nieuwe brondata transformeren en via upsert direct in PostgreSQL laden. Voordeel: simpelste model voor de load-fase. Nadeel: de volledige transformatielogica is nu in MongoDB-aggregaties geschreven; die moet deels herschreven worden.

**C. Hybride: MongoDB voor transformatie, PostgreSQL voor persistentie** — MongoDB staging en analyse worden gebruikt als werkgeheugen voor de transformatie van de delta. Na transformatie worden de resultaten via upsert naar PostgreSQL geschreven. MongoDB wordt niet als langetermijnopslag behandeld. Voordeel: bestaande transformatielogica blijft grotendeels intact; PostgreSQL is de single source of truth. Nadeel: bij een gewijzigd bestand moet je de oude records uit `COLL_ANALYSE_CLEAN` pre-fetchen om de merge correct uit te voeren.

| Aspect | A (Mongo = waarheid) | B (PG = waarheid) | C (Hybride) |
|---|---|---|---|
| Bestandshash-registratie | In MongoDB | In PostgreSQL | In PostgreSQL |
| Bestaande transformatielogica | Grotendeels herbruikbaar | Herschrijven vereist | Grotendeels herbruikbaar |
| Merge/dedup bij delta | Aanpassing nodig | In SQL (nieuw) | Aanpassing nodig |
| Consistentie Mongo↔PG | Gegarandeerd | PG leidend, Mongo disposable | PG leidend, Mongo tijdelijk |
| Herstelbaarheid | Volledige rebuild vanuit staging | Rebuild vereist re-import | Rebuild vereist re-import |

**Aanbeveling:** optie C. PostgreSQL is de bron van waarheid (daar draait de applicatie op), MongoDB dient als werkgeheugen voor transformatie.

### Grootste technische uitdaging

De merge-stap (Transform5) is de kernblokkade. De huidige `$group`-aggregatie in MongoDB veronderstelt dat alle duplicaten van een entiteit in dezelfde pipeline zitten. Bij incrementeel laden moet de merge-stap:

- Bestaande records met dezelfde composite key ophalen uit `COLL_ANALYSE_CLEAN`
- Deze combineren met de nieuwe delta-records
- De `brondata`-array aanvullen (niet vervangen)
- Het samengevoegde resultaat terugschrijven

Dit vereist een aanpassing van `merge_functions.py`: van een enkelvoudige `$group`-aggregatie naar een twee-staps-proces (pre-fetch bestaand + merge met nieuw).

### Context

Voorbeeld van de bestandshash-registratie:

```
Def_Bronbestand
├── id: 1
├── bestandsnaam: "opgravingDC036.mdb"
├── sha256: "a3f2b8c..."
├── verwerkingsdatum: "2026-03-14T10:30:00"
├── status: "verwerkt"
└── aantal_records: 1247
```

De huidige pipeline doorloopt deze stappen, elk met full-batch aannames:

1. `dropAll()` — dropt MongoDB staging, files en analyse databases
2. Extract — volledige MDB-import via `mongoimport --mode upsert` (maar met auto-generated `_id`)
3. Transform1-5 — MongoDB-aggregaties op complete collecties
4. Load — PostgreSQL tabelswap via temp-tabellen; `primary_key` wordt sequentieel opnieuw toegekend
5. Index — Elasticsearch volledige herindexering met alias-swap

---

## Onderlinge afhankelijkheden

```
1. Docker multi-arch ──────────────────────────────────┐
                                                       ├── Deployment
5. Incrementeel laden ─── volume mounts voor delta ────┘
                    │
                    ├── vereist stabiele sleutels ──── 2. Profielensysteem
                    │
                    ├── correctieregels incrementeel ─ 3. Externalisering Delft-logica
                    │
                    └── testbaar met ──────────────── 4. Synthetische voorbeelddata
```

**Aanbevolen volgorde:**

1. **Externalisering Delft-logica** (3) — voorwaarde voor generalisatie
2. **Profielensysteem** (2) — voorwaarde voor stabiele sleutels
3. **Synthetische voorbeelddata** (4) — nodig om 2 en 3 te testen met niet-Delft data
4. **Incrementeel laden** (5) — bouwt voort op stabiele sleutels uit 2
5. **Docker multi-arch + productie-deployment** (1) — kan parallel aan 3 en 4
