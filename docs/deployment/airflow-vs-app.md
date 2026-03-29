# Airflow Transformatie vs. Web Applicatie

De Wasstraat bevat twee hoofdapplicaties die elk een eigen rol vervullen. Beide draaien als aparte Docker-containers maar delen dezelfde databases en configuratie.

## Overzicht

| Aspect | Airflow (`airflow_app/`) | Flask App (`app/`) |
|--------|--------------------------|---------------------|
| **Doel** | Data verwerken (ETL) | Data inzichtelijk maken |
| **Gebruiker** | Data-engineers, beheerders | Archeologen, onderzoekers |
| **Interface** | Airflow Web UI (:8080) | Web-applicatie (:5051) |
| **Richting** | Bron → MongoDB → PostgreSQL | PostgreSQL → Gebruiker |
| **Modus** | Batch (handmatig of gepland) | Interactief (request/response) |
| **Framework** | Apache Airflow 2.3.3 | Flask + Flask-AppBuilder |
| **Database-rol** | Schrijft naar MongoDB en PostgreSQL | Leest uit PostgreSQL en Elasticsearch |

## Airflow Transformatie-applicatie (`airflow_app/`)

### Functie

De Airflow-applicatie is de **dataverwerkingsmotor**. Zij leest ruwe bronbestanden in (Access-databases, foto's, rapporten), transformeert deze door een reeks stappen, en laadt het resultaat in de definitieve databases.

### Structuur

```
airflow_app/
├── dags/                           # DAG-definities (workflows)
│   ├── DAG_Extract_Transform_Load_Full_Cycle.py   # Volledige ETL-cyclus
│   ├── DAG_Extract_Only.py                        # Alleen extractie
│   ├── DAG_Transform1_Harmonize_Only.py           # Alleen harmonisatie
│   ├── DAG_Transform2_Enhance_Attributes_Only.py  # Alleen attribuut-verbetering
│   ├── DAG_Transform3_Keys_Only.py                # Alleen sleutels instellen
│   ├── DAG_Transform4_Refs_Only.py                # Alleen referenties
│   ├── DAG_Transform_Move_Only.py                 # Alleen verplaatsen
│   ├── DAG_Load_Only.py                           # Alleen laden naar PostgreSQL
│   └── DAG_Redo_Images.py                         # Herverwerken van foto's
├── scripts/                        # Shell-scripts (MDB-import, etc.)
└── .vscode/                        # VS Code debug-configuratie
```

### DAGs (Directed Acyclic Graphs)

Elke DAG definieert een workflow die via de Airflow UI handmatig kan worden gestart of ingepland. De belangrijkste DAG is de **volledige ETL-cyclus** die 8 stappen sequentieel uitvoert:

```
Start → Drop All Databases
      → Extract (6 MDB-bronnen + foto's + referentietabellen)
      → Transform 1: Harmonize (veldnamen standaardiseren)
      → Transform 2: Enhance Attributes (waarden opschonen)
      → Transform 3: Set Keys (unieke sleutels genereren)
      → Transform 5: Move & Merge (deduplicatie, polymorfisme)
      → Transform 4: Set References (referenties als integer PKs)
      → Load to Database & Index (PostgreSQL + Elasticsearch)
      → End
```

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

De Access-databases worden via `mdbtools` (een open-source MDB-lezer) als JSON naar MongoDB geëxporteerd.

### Transformatiestappen

Elke transformatiestap werkt op de MongoDB staging-collecties:

1. **Harmonize** (`tasks_transform1_harmonize.py`): Standaardiseert veldnamen over bronnen heen. Bijvoorbeeld `opgrNaam`, `project_naam` en `Naam_opgraving` worden allemaal `opgraving_naam`.

2. **Enhance Attributes** (`tasks_transform2_attributes.py`): Schoont waarden op, corrigeert datatypes, normaliseert datums en coderingen.

3. **Set Keys** (`tasks_transform3_keys.py`): Genereert unieke sleutels voor elk record zodat relaties tussen entiteiten gelegd kunnen worden.

4. **Move & Merge** (`tasks_transform5_moveAndMerge.py`): Verplaatst data naar definitieve collecties, voegt duplicaten samen, en handelt polymorfisme af (een vondst kan tegelijk een artefact en een monster zijn).

5. **Set References** (`tasks_transform4_references.py`): Converteert tekstuele verwijzingen naar integer-PKs voor de relationele database.

6. **Load to Database & Index** (`tasks_load_to_database_and_index.py`): Kopieert de getransformeerde data naar PostgreSQL-tabellen en bouwt de Elasticsearch-zoekindex op.

### Kernmodule: `wasstraat/`

De gedeelde verwerkingslogica zit in `airflow_app/dags/wasstraat/`:

- `meta.py` — Definieert alle entiteitstypen, hun verwerkingspipelines, en MongoDB-aggregatieschema's. Dit is het hart van de dataverwerking.
- `mongoUtils.py` — Database-operaties (drop, indexering, queries)
- `harmonize_functions.py` — Veldnaam-harmonisatie per entiteitstype
- `setAttributes_functions.py` — Waarde-opschoning en -conversie
- `merge_functions.py` — Deduplicatie en samenvoeglogica
- `references_functions.py` — Referentie-resolutie
- `loadToDatabase_functions.py` — PostgreSQL-laden via SQLAlchemy
- `image_import.py` — Parallelle foto-import (8 processen)

## Web-applicatie (`app/`)

### Functie

De Flask web-applicatie is de **presentatielaag**. Zij maakt de verwerkte data inzichtelijk voor archeologen, onderzoekers en beleidsmedewerkers via een interactieve webinterface.

### Structuur

```
app/
├── app/
│   ├── app.py          # Flask-initialisatie, database-connectie, caching
│   ├── models.py       # SQLAlchemy ORM-modellen (alle entiteiten)
│   ├── views.py        # Flask-AppBuilder views (CRUD-interfaces)
│   ├── api.py          # REST API-endpoints
│   ├── search.py       # Elasticsearch fulltext-zoekfunctie
│   ├── route.py        # Custom routes (bestandsupload, redirects)
│   ├── init.py         # Database-initialisatie en vulling
│   ├── caching.py      # Redis cache-configuratie
│   ├── models.py       # ~62KB aan ORM-modellen
│   ├── views.py        # ~47KB aan view-definities
│   ├── validators.py   # Formulier-validatie
│   ├── filters.py      # Jinja2 template-filters
│   ├── foto_util.py    # Foto-weergave utilities
│   ├── modelevents.py  # SQLAlchemy event-listeners
│   ├── static/         # JavaScript, CSS
│   ├── templates/      # Jinja2 HTML-templates
│   └── translations/   # Internationalisatie (Babel)
├── run.py              # Entrypoint (start Flask op 0.0.0.0:8080)
└── gunicorn.conf.py    # uWSGI/Gunicorn productie-config
```

### Technische Stack

- **Flask** + **Flask-AppBuilder**: Genereert automatisch CRUD-interfaces op basis van SQLAlchemy-modellen
- **SQLAlchemy ORM**: Alle `Def_*` PostgreSQL-tabellen zijn als Python-klassen gemodelleerd in `models.py`
- **Elasticsearch**: Fulltext-zoekfunctie over alle entiteiten
- **Redis**: Caching van veelgebruikte queries en weergaven
- **Apache**: Serveert statische bestanden (foto's, rapporten) via een apart volume
- **Jinja2 templates**: HTML-rendering met Bootstrap (via Flask-AppBuilder)

### Functionaliteiten

De web-applicatie biedt:

- **Projectoverzicht**: Lijst van alle opgravingsprojecten met filtering en sortering
- **Entiteiten-browser**: Navigatie door putten, vlakken, sporen, vullingen, vondsten, artefacten en monsters
- **Foto-viewer**: Bekijken van gekoppelde foto's per vondst of spoor
- **Depot-beheer**: Overzicht van fysieke opslaglocaties (stellingen, standplaatsen, dozen)
- **Zoekfunctie**: Fulltext-zoeken over alle archeologische records via Elasticsearch
- **REST API**: Programmatische toegang voor externe systemen (ABR-materialen, projecten, putten)
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
                   │ Apache ──→ Foto's      │
                    ════════════════════════
```

### Gedeelde componenten

Beide applicaties gebruiken de `shared/` directory:

- `shared/config.py` — Centrale configuratie (database-URLs, collectienamen, paden)
- `shared/const.py` — Constanten (entiteitstypen, ABR-codes, materiaaltypen)
- `shared/database.py` — PostgreSQL tabel-discovery
- `shared/fulltext.py` — Elasticsearch indexering
- `shared/image_util.py` — Beeldverwerking

### Wanneer gebruik je welke applicatie?

| Scenario | Applicatie | Hoe |
|----------|-----------|-----|
| Nieuwe data importeren | Airflow | Start DAG via Airflow UI (:8080) |
| Bestaande data bekijken | Flask App | Open webbrowser op :5051 |
| Zoeken in data | Flask App | Gebruik zoekbalk in web-interface |
| Transformaties debuggen | Airflow | Bekijk task-logs in Airflow UI |
| Data-model aanpassen | Beide | Pas `meta.py` (Airflow) en `models.py` (Flask) aan |
| API gebruiken | Flask App | `GET /api/v1/projects/` etc. |
| Ad-hoc analyse | Jupyter | Open notebook op :8888 |
