# Architectuurdiagrammen

Deze pagina biedt een overzicht van alle architectuurdiagrammen die zijn opgesteld voor het Wasstraat Archeologische Data-platform. De diagrammen zijn beschikbaar in [draw.io](https://www.diagrams.net/) formaat en kunnen direct worden geopend en bewerkt.

## Beschikbare diagrammen

### 1. Systeemarchitectuur

**Bestand:** `assets/diagrams/systeem-architectuur.drawio`

Het systeemarchitectuurdiagram toont de volledige opbouw van het platform in drie hoofdlagen:

- **Bronbestanden** — de diverse invoerformaten (Excel, CSV, Word, PDF, Access, dBase, foto's, GIS-bestanden, XML/XMI)
- **Wasstraat Core** — het verwerkingshart met extractie, ruwe opslag (MongoDB/SingleStore), transformatie, definitieve opslag (PostgreSQL/Oracle), en ondersteunende modules (Crossviews, Validatie, Configuratie, Zoeken, Handmatige Schoning, Monitoring)
- **Uitvoer** — de diverse outputkanalen (Website, GIS-export, Data Warehouse, Linked Open Data)

Daarnaast worden de externe standaarden en referenties weergegeven: ABR Thesaurus, CIDOC CRM/CRMarchaeo, GGM, DANS e-Depot, Archis/RCE en FAIR-principes.

### 2. Dataflow Pipeline

**Bestand:** `assets/diagrams/dataflow-pipeline.drawio`

Dit diagram beschrijft de zevenledige dataverwerkingspipeline:

| Fase | Naam | Beschrijving |
|------|------|-------------|
| 1 | Ingest | Ontvangen van eenmalige en periodieke bronnen |
| 2 | Extractie | Formatdetectie, encoding-afhandeling, parsing en veldherkenning |
| 3 | Ruwe Opslag | Bewaren in MongoDB/SingleStore met polymorf metadateringsmodel |
| 4 | Transformatie | ABR-harmonisatie, spellingnormalisatie, sleutel-/locatieharmonisatie, deduplicatie |
| 5 | Validatie | Datalogicavalidatie en cachemechanisme |
| 6 | Definitieve Opslag | Gestructureerde opslag in PostgreSQL/Oracle (GGM-compatibel) |
| 7 | Uitvoer | Website, GIS-export, Data Warehouse, Linked Open Data |

De Crossviews Engine en het handmatige schoningsproces zijn als parallelle processen weergegeven.

### 3. Componentenmodel

**Bestand:** `assets/diagrams/componenten-model.drawio`

Het componentenmodel visualiseert de functionele indeling in vier lagen:

- **Verwerkingslaag** — Extractie → Mapping → Transformatie → Validatie, aangevuld met Crossviews en Zoek & Indexering
- **Opslaglaag** — MongoDB (schema-vrij), PostgreSQL (relationeel/GGM) en Oracle (optioneel/enterprise)
- **Beheer & Configuratie** — Configuratiemodule (gemeenteprofielen, mappings) en Monitoring (logging, procesvoortgang, foutafhandeling)
- **Presentatielaag** — Website (Django + Vue/Vuetify), REST API, GIS-export, Data Warehouse en Linked Open Data

De infrastructuurlaag (Docker, Kubernetes, Airflow, Celery, Luigi, Spark) vormt de basis. Het toekomstige UML-Transformer-component is met een stippellijn aangegeven.

### 4. Semantisch Model

**Bestand:** `assets/diagrams/semantisch-model.drawio`

Dit diagram toont de semantische architectuur van het platform:

- **CIDOC CRM-familie** — de hiërarchie van CRM-core, CRMarchaeo, CRMsci, CRMba en CRMgeo
- **22 Semantische Referentie Data Modellen (SRDMs)** — de modelleringsgroepen voor vondsten, structuren, locaties, documentatie, actoren en analyse
- **Nederlandse standaarden** — ABR Thesaurus, GGM, Archis/RCE en DANS e-Depot
- **Internationale standaarden** — ARIADNE, FAIR-principes en Linked Open Data

Alle elementen convergeren naar de centrale Wasstraat-node, die als integratielaag fungeert.

## Gebruik van de diagrammen

De `.drawio`-bestanden kunnen worden geopend met:

- [draw.io Desktop](https://github.com/jgraph/drawio-desktop/releases) (offline)
- [draw.io Online](https://app.diagrams.net/) (browser)
- De draw.io-extensie voor VS Code

!!! tip "Kleurcodering"
    Alle diagrammen hanteren een consistente kleurcodering:

    - **Groen** — Verwerkingscomponenten (extractie, transformatie)
    - **Rood** — Opslagcomponenten (databases)
    - **Blauw** — In- en uitvoercomponenten
    - **Geel** — Ondersteunende componenten (crossviews, validatie, zoeken)
    - **Paars** — Handmatige/beheerprocessen en externe standaarden
