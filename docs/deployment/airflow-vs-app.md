# Airflow Transformatie vs. Web Applicatie

De Wasstraat bevat twee hoofdapplicaties die elk een eigen rol vervullen. Beide draaien als aparte Docker-containers maar delen dezelfde databases en configuratie.

## Overzicht

| Aspect | Airflow (`airflow_app/`) | Flask App (`app/`) |
|--------|--------------------------|---------------------|
| **Doel** | Data verwerken (ETL) | Data inzichtelijk maken |
| **Gebruiker** | Data-engineers, beheerders | Archeologen, onderzoekers |
| **Interface** | Airflow Web UI (:8080) | Web-applicatie (:5052, via Apache) |
| **Richting** | Bron → MongoDB → PostgreSQL | PostgreSQL → Gebruiker |
| **Modus** | Batch (handmatig of gepland) | Interactief (request/response) |
| **Framework** | Apache Airflow 2.10.5 | Flask + Flask-AppBuilder |
| **Database-rol** | Schrijft naar MongoDB, PostgreSQL en Elasticsearch | Leest uit PostgreSQL en Elasticsearch; schrijft gebruikersdata (bruiklenen, conservering) en wijzigingen |

## Airflow Transformatie-applicatie (`airflow_app/`)

### Functie

De Airflow-applicatie is de **dataverwerkingsmotor**. Zij leest ruwe bronbestanden in (Access-databases, foto's, rapporten), transformeert deze door een reeks stappen, en laadt het resultaat in de definitieve databases.

### Structuur

```
airflow_app/
├── dags/                           # DAG-definities (workflows)
│   ├── DAG_Extract_Transform_Load_Full_Cycle.py   # Volledige ETL-cyclus
│   ├── DAG_Extract_Transform_Load_Incremental.py  # Incrementele cyclus (alleen gewijzigde bronbestanden)
│   ├── DAG_Extract_Only.py                        # Alleen extractie
│   ├── DAG_Transform1_Harmonize_Only.py           # Alleen harmonisatie
│   ├── DAG_Transform2_Enhance_Attributes_Only.py  # Alleen attribuut-verbetering
│   ├── DAG_Transform3_Keys_Only.py                # Alleen sleutels instellen
│   ├── DAG_Transform4_Refs_Only.py                # Alleen referenties
│   ├── DAG_Transform_Move_Only.py                 # Alleen verplaatsen en samenvoegen
│   ├── DAG_Transform_Move_And_References_Only.py  # Verplaatsen, samenvoegen en referenties
│   ├── DAG_Transform_Only.py                      # Alle transformaties, zonder laden
│   ├── DAG_Transform_Load_Only.py                 # Alle transformaties en laden
│   ├── DAG_Extract_Projects_Only.py               # Alleen de opgravingsdatabases inlezen
│   ├── DAG_Load_Only.py                           # Alleen laden naar PostgreSQL en indexeren
│   ├── DAG_Redo_Images.py                         # Mislukte foto's opnieuw verwerken
│   ├── tasks_*.py                                 # Taakgroepen per stap
│   └── wasstraat/                                 # Verwerkingslogica (zie hieronder)
├── scripts/                        # Shell-scripts (MDB-import, etc.)
└── .vscode/                        # VS Code debug-configuratie
```

### DAGs (Directed Acyclic Graphs)

Elke DAG definieert een workflow die via de Airflow UI handmatig wordt gestart; geen DAG is ingepland. De belangrijkste DAG is de **volledige cyclus**:

```
Start_Run (run-document)
  → Drop All Databases
  → Extract (6 MDB-bronnen + foto's + referentietabellen, met controles)
  → Transform 1: Harmonize (veldnamen standaardiseren)
  → Transform 2: Enhance Attributes (waarden opschonen)
  → Transform 3: Set Keys (sleutels genereren)
  → Transform 5: Move & Merge (verplaatsen, samenvoegen, polymorfisme)
  → Transform 4: Set References (stabiele integer-sleutels en verwijzingen)
  → Load to Database & Index (PostgreSQL + Elasticsearch)
  → Registreer_Bronbestanden
  → Verwerkingsrapport → End
```

Alle taken staan in [Verwerkingspipeline](../architectuur/dataflow.md).

### Extractie-bronnen

De extractie-stap leest data uit zes Access-databases (`.mdb`) plus foto- en referentiebestanden:

| Bron | Inhoud | Volume |
|------|--------|--------|
| Projectendatabase (projecten) | Opgravingsprojecten, putten, sporen, vondsten | ~1000 databases |
| Projectenlijst | Administratieve gegevens | 1 database |
| Magazijnlijst | Depot-informatie (stellingen, dozen) | 1 database |
| DigiFotolijst | Foto-metadata | 1 database |
| MonsterDB | Monster-gegevens (botanie, schelpen) | 1 database |
| Rapportendatabases | Rapporten en tekeningen | Meerdere databases |
| Foto's | Originele afbeeldingen | ~100.000 bestanden |
| Referentietabellen | ABR-codes, materiaaltypen | Handmatige tabellen |

De Access-databases worden met `mdbtools` (een open-source MDB-lezer) per tabel als CSV geëxporteerd en met `mongoimport` in MongoDB geladen (`airflow_app/scripts/importMDB.sh`).

### Transformatiestappen

Elke transformatiestap werkt op de MongoDB staging-collecties:

1. **Harmonize** (`tasks_transform1_harmonize.py`): Standaardiseert veldnamen over bronnen heen, volgens de harmonisatie-Excel. Bijvoorbeeld de kolommen `PUT` en `PUTNO` worden allebei het veld `putnr`.

2. **Enhance Attributes** (`tasks_transform2_attributes.py`): Schoont waarden op, corrigeert datatypes, normaliseert datums en coderingen.

3. **Set Keys** (`tasks_transform3_keys.py`): Genereert unieke sleutels voor elk record zodat relaties tussen entiteiten gelegd kunnen worden.

4. **Move & Merge** (`tasks_transform5_moveAndMerge.py`): Verplaatst de documenten naar `Single_Store_Clean`, voegt documenten met dezelfde sleutel samen en maakt ontbrekende putten, vlakken, sporen, vondsten en dozen aan. Artefacten van alle materialen staan daarbij in één collectie, elk met hun eigen velden (polymorfisme).

5. **Set References** (`tasks_transform4_references.py`): Kent stabiele integer-sleutels toe (bestaande nummers worden uit PostgreSQL overgenomen) en zet de verwijzingen tussen de entiteiten.

6. **Load to Database & Index** (`tasks_load_to_database_and_index.py`): Kopieert de getransformeerde data naar PostgreSQL-tabellen, berekent de afgeleide velden die de webapplicatie toont (aantal foto's per artefact, aantal artefacten per project, dateringen; `herberekenAfgeleideVelden`) en bouwt de Elasticsearch-zoekindex op.

### Kernmodule: `wasstraat/`

De gedeelde verwerkingslogica zit in `airflow_app/dags/wasstraat/`:

- `meta.py` — Definieert alle entiteitstypen, hun verwerkingspipelines, en MongoDB-aggregatieschema's. Dit is het hart van de dataverwerking.
- `mongoUtils.py` — Database-operaties (drop, indexering, queries)
- `harmonize_functions.py` — Veldnaam-harmonisatie per entiteitstype
- `setAttributes_functions.py` — Waarde-opschoning en -conversie
- `merge_functions.py` — Deduplicatie en samenvoeglogica
- `references_functions.py` — Referentie-resolutie
- `loadToDatabase_functions.py` — PostgreSQL-laden via psycopg2: atomic swap (`loadAll`, volledige cyclus) en upsert (`loadIncrementeel`, incrementele cyclus), beide gevolgd door de herberekening van de afgeleide velden (`herberekenAfgeleideVelden`); de gebruikerstabellen (bruiklenen, partijen, conservering) blijven in beide staan
- `image_import.py` — Parallelle foto-import (8 taken)
- `paden_overslaan.py` — Bestanden en mappen overslaan volgens `correcties.yml`
- `controle_extractie.py` — Controles na de extractie (`Controleer_Databases`, `Controleer_Afbeeldingen`)
- `foutbeleid.py` — Welke fouten cruciaal zijn en welke een waarschuwing; drempels en meldingen
- `verwerkingsrapport.py` — Het verwerkingsrapport per run
- `verwerkingsrun.py` — Run-document van de cycli (`Verwerkingsruns`)
- `profielen/` — Gemeenteprofielen (`WASSTRAAT_GEMEENTE`)
- `bronbestanden.py` — Registratie van bronbestanden (`Def_Bronbestand`) en bepaling van de delta
- `opruimen.py` — Opruimen van records van gewijzigde en verwijderde bronbestanden
- `delta_transform.py` — Delta-varianten van de transformaties (incrementele cyclus) en stabiele sleutels (beide cycli)

Naast de volledige cyclus is er een **incrementele cyclus** (`Extract_Transform_Load_Incremental`) die alleen nieuwe, gewijzigde en verwijderde bronbestanden verwerkt, de tabellen in PostgreSQL bijwerkt met een upsert en daarna de Elasticsearch-indexen bijwerkt (`shared/fulltext.py`, `indexTableIncrementeel`). Zie [Incrementeel laden](../componenten/incrementeel-laden.md).

## Web-applicatie (`app/`)

### Functie

De Flask web-applicatie is de **presentatielaag**. Zij maakt de verwerkte data inzichtelijk voor archeologen, onderzoekers en beleidsmedewerkers via een interactieve webinterface.

### Structuur

```
app/
├── app/
│   ├── app.py          # Flask-initialisatie, database-connectie, caching, ProxyFix
│   ├── patched_app.py  # De app zoals gunicorn hem start
│   ├── models.py       # SQLAlchemy ORM-modellen van alle Def_-tabellen
│   ├── views.py        # Flask-AppBuilder views (lijsten, detailpagina's, formulieren)
│   ├── api.py          # REST API-endpoints onder /api/v1/
│   ├── search.py       # Elasticsearch fulltext-zoekfunctie
│   ├── filters.py      # Filters, waaronder Fulltext Zoeken
│   ├── route.py        # Eigen routes (bestanden, voorbeeldafbeeldingen)
│   ├── init.py         # Bij het starten: zoekindex en vangnet voor de afgeleide velden
│   ├── beheerder.py    # Aanmaken van de beheerder admin
│   ├── caching.py      # Redis-cache
│   ├── validators.py   # Formuliervalidatie
│   ├── foto_util.py    # Kantelen van foto's en pdf's
│   ├── modelevents.py  # SQLAlchemy event-listeners (afgeleide velden, markering bij verwijderen)
│   ├── static/         # JavaScript, CSS
│   ├── templates/      # Jinja2 HTML-templates
│   └── translations/   # Internationalisatie (Babel)
├── fab_addon_geoalchemy/ # Eigen uitbreiding voor geometriekolommen
├── gunicorn.conf.py    # Gunicorn-configuratie (scripts/flask/init.sh start gunicorn op poort 5051)
└── run.py              # Alleen voor lokaal debuggen (Flask-ontwikkelserver)
```

### Technische Stack

- **Flask** + **Flask-AppBuilder**: Genereert automatisch CRUD-interfaces op basis van SQLAlchemy-modellen
- **SQLAlchemy ORM**: Alle `Def_*` PostgreSQL-tabellen zijn als Python-klassen gemodelleerd in `models.py`
- **Elasticsearch**: Fulltext-zoekfunctie over alle entiteiten
- **Redis**: Caching van veelgebruikte queries en weergaven
- **Apache**: De voordeur op poort 5052: serveert de media onder `/archeomedia` uit de uitvoermap en stuurt alle overige verzoeken door naar Flask (reverse proxy)
- **Jinja2 templates**: HTML-rendering met Bootstrap (via Flask-AppBuilder)

### Functionaliteiten

De web-applicatie biedt:

- **Projectoverzicht**: Lijst van alle opgravingsprojecten met filtering en sortering
- **Entiteiten-browser**: Navigatie door putten, vlakken, sporen, vullingen, vondsten, artefacten en monsters
- **Foto-viewer**: Bekijken van gekoppelde foto's per vondst of spoor
- **Depot-beheer**: Dozen en stellingen, en het invoeren van bruiklenen, partijen en conserveringsprojecten (gebruikersdata die bij elke cyclus blijft staan)
- **Zoekfunctie**: Fulltext-zoeken over alle archeologische records via Elasticsearch
- **REST API**: Programmatische toegang onder `/api/v1/` (`abrmaterialen`, `projecten`, `putten`, `sporen`, `vondsten`, `dozen`, `artefacten`)
- **Bestandsupload**: Drag-and-drop upload van nieuwe bestanden via Flask-Dropzone

### ORM-modellen

Het bestand `models.py` (~62KB) definieert alle databasetabellen als Python-klassen. De belangrijkste entiteiten:

| Model | Tabel | Beschrijving |
|-------|-------|-------------|
| `Project` | `Def_Project` | Opgravingsproject |
| `Vindplaats` | `Def_Vindplaats` | Archeologische vindplaats |
| `Put` | `Def_Put` | Opgravingsput |
| `Vlak` | `Def_Vlak` | Vlak binnen een put |
| `Spoor` | `Def_Spoor` | Grondspoor |
| `Vulling` | `Def_Vulling` | Vulling van een spoor |
| `Vondst` | `Def_Vondst` | Vondstmelding |
| `Artefact` | `Def_Artefact` | Fysiek artefact |
| `Monster` | `Def_Monster` | Wetenschappelijk monster |
| `Bestand` | `Def_Bestand` | Foto, tekening of rapport |

## Samenspel tussen beide applicaties

De twee applicaties vormen samen de complete Wasstraat-pipeline:

```
                    AIRFLOW (airflow_app/)
                    ════════════════════════
Bronbestanden ──→ │ Extract ──→ MongoDB    │
 (MDB, foto's)    │    ↓       (staging)   │
                   │ Transform (5 stappen)  │
                   │    ↓                   │
                   │ Load ──→ PostgreSQL    │
                   │       ──→ Elasticsearch│
                    ════════════════════════
                              ↓
                    FLASK APP (app/)
                    ════════════════════════
                   │ PostgreSQL ──→ Views   │──→ Webbrowser
                   │ Elasticsearch ──→ Zoek │    (archeologen)
                   │ Redis ──→ Cache        │
                   │ Apache ──→ voordeur:   │
                   │   proxy naar Flask     │
                   │   + foto's (media)     │
                    ════════════════════════
```

### Gedeelde componenten

Beide applicaties gebruiken de `shared/` directory:

- `shared/config.py` — Centrale configuratie (database-URLs, collectienamen, paden)
- `shared/const.py` — Constanten (entiteitstypen, ABR-codes, materiaaltypen)
- `shared/database.py` — PostgreSQL tabel-discovery
- `shared/fulltext.py` — Elasticsearch indexering
- `shared/image_util.py` — Beeldverwerking
- `shared/gebruikersdata.py` — Verwijzingen vanuit gebruikerstabellen naar verdwenen rijen
- `shared/logutils.py` — Wachtwoorden maskeren in de logs

### Wanneer gebruik je welke applicatie?

| Scenario | Applicatie | Hoe |
|----------|-----------|-----|
| Nieuwe data importeren | Airflow | Start DAG via Airflow UI (:8080) |
| Bestaande data bekijken | Flask App | Open webbrowser op :5052 (Apache) |
| Zoeken in data | Flask App | Gebruik zoekbalk in web-interface |
| Transformaties debuggen | Airflow | Bekijk task-logs in Airflow UI |
| Data-model aanpassen | Beide | Pas `meta.py` of de harmonisatie-Excel (Airflow) en `models.py` (Flask) aan |
| API gebruiken | Flask App | `GET /api/v1/projecten/` etc. |
| Ad-hoc analyse | Jupyter | Open notebook op :8888 |
