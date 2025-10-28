# GGM Integratie: Gemeentelijk Gegevensmodel

De Wasstraat moet zich niet als isolatd systeem presenteren, maar als onderdeel van de bredere gemeentelijke data-governance. Dit document beschrijft hoe integratie met het Gemeentelijk Gegevensmodel (GGM) plaatsvindt.

## GGM: Context en Principes

### Wat is GGM?

Het Gemeentelijk Gegevensmodel (GGM) is het raamwerk waarbinnen Nederlandse gemeenten hun data organiseren:

- **Centraal concept**: Alle gemeentelijke gegevens (burgers, gebouwen, percelen, diensten, etc.) zijn semantisch verbonden
- **Common Ground principes**: Data belongs to citizen; systems are modular; APIs are first-class
- **Interoperabiliteit**: Systemen kunnen met elkaar communiceren zonder propriëtaire integratie
- **Transparantie**: Datamodellen zijn openbaar en standaard

### GGM in Delft

Delft implementeert GGM via:
- **Informatiemodel**: Formele beschrijving van data-entiteiten en relaties
- **Register-benadering**: Gegevens zijn bron-of-truth registers (NOT geduplcieerd in verschillende systemen)
- **API-laag**: Toegang via RESTful APIs
- **Metadata**: Beschrijving van data-ownership, kwaliteit, actualiteit

Erfgoeddata in GGM context:
- **Monumenten**: Protégé gebouwen en structuren
- **Archeologie**: Ondergrondse erfgoed en archeologische sites
- **Topografische gegevens**: Historische kaarten en cartografie
- **Bouwhistorie**: Evolutie van gebouwen over tijd

## Huidige Toestand: Wasstraat & GGM

### Positief
- Delft heeft GGM ingevoerd
- Wasstraat is geïnformeerd door GGM-concepten
- Data-governance principles zijn gerespecteerd

### Problematisch
- Wasstraat is nog niet formeel in GGM opgenomen
- Koppeling met GGM-registers is ad-hoc
- Semantiek van archeologische data is niet expliciet in GGM
- Geen publieke API conform GGM-standaarden

## Integratie-Plan: 4 Pijlers

### Pijler 1: Semantische Mapping

**Doel**: Definiëren van hoe archeologische entiteiten mapping naar GGM-concepten.

#### Entiteit: Opgraving (Excavation)

```yaml
# GGM semantische mapping
gis_entity:
  name: "Opgraving"
  description: "Archeologische onderzoeksoperatie"
  subclass_of: "ResearchProject"  # Generiek GGM-concept

  attributes:
    - name: "opgraving_naam"
      gis_type: "Text"
      gis_description: "Officiële naam van opgraving"
      mapping: "Wasstraat.excavation_name"

    - name: "opgraving_locatie"
      gis_type: "Geometry"
      gis_description: "Geografische locatie van opgraving"
      mapping: "Wasstraat.location.geometry"
      note: "Coordinatensysteem moet RD (EPSG:28992) zijn"

    - name: "opgraving_periode_start"
      gis_type: "DateTime"
      gis_description: "Begin van onderzoeks-activiteiten"
      mapping: "Wasstraat.dates.start"

    - name: "opgraving_periode_einde"
      gis_type: "DateTime"
      gis_description: "Einde van onderzoeks-activiteiten"
      mapping: "Wasstraat.dates.end"

    - name: "opgraving_verantwoordelijke"
      gis_type: "Reference"
      gis_reference_type: "Organisatie"  # Existing GGM-entiteit
      mapping: "Wasstraat.responsible_parties[role='project_lead'].organization"

    - name: "opgraving_beschrijving"
      gis_type: "Text"
      gis_description: "Beschrijving van onderzoeksdoelstellingen en -resultaten"
      mapping: "Wasstraat.description"

  relations:
    - name: "opgraving_raakt_perceel"
      description: "Opgraving vindt plaats op bepaald perceel"
      target_entity: "Perceel"  # Existing GGM-entiteit
      cardinality: "many-to-many"
      mapping: "Wasstraat.location.geometry INTERSECT Perceel.geometry"

    - name: "opgraving_raakt_monument"
      description: "Opgraving raakt beschermd monument"
      target_entity: "Monument"  # Existing GGM-entiteit
      cardinality: "many-to-many"
      mapping: "Wasstraat.location.geometry BUFFER(100m) INTERSECT Monument.geometry"

    - name: "opgraving_opslaat_vonden"
      description: "Opgraving resulteert in archeologische vonden"
      target_entity: "ArcheologischVondst"  # Nieuwe Wasstraat-entiteit
      cardinality: "one-to-many"
```

#### Entiteit: Archeologische Vondst (Finding)

```yaml
gis_entity:
  name: "ArcheologischVondst"
  description: "Artefact of ecofact gevonden tijdens archeologisch onderzoek"
  subclass_of: "Artefact"  # Nieuwe base-klasse in GGM

  attributes:
    - name: "vondst_registratienummer"
      gis_type: "Text"
      mapping: "Wasstraat.finding.catalog_number"

    - name: "vondst_materiaal"
      gis_type: "Enum"
      gis_values: ["ceramics", "metal", "stone", "glass", "bone", "organic", "other"]
      mapping: "Wasstraat.finding.material"

    - name: "vondst_beschrijving"
      gis_type: "Text"
      mapping: "Wasstraat.finding.description"

    - name: "vondst_dateringsperiode"
      gis_type: "Reference"
      gis_reference_type: "Periode"  # Nieuw GGM-concept, of link naar ABR
      mapping: "Wasstraat.finding.dating_period"
      note: "Link naar ABR voor standaardisering"
```

### Pijler 2: Data-Flow Architectuur

**Doel**: Definiëren hoe data stroomt tussen Wasstraat en GGM-registers.

#### Scenario A: Wasstraat als "Bron-of-Truth"

Wasstraat beheert alle archeologische masterdata, GGM-systemen consumeren via API.

```
┌──────────────────┐
│   Delft Bron     │
│   - XML files    │
│   - Legacy DBs   │
└────────┬─────────┘
         │ Import
         ▼
┌──────────────────────────────┐
│   Wasstraat SingleStore      │
│   (Archaeological Master DB) │
└────────┬─────────────────────┘
         │ API
         ├─────────────────────────────┐
         │                             │
         ▼                             ▼
    ┌─────────────┐          ┌──────────────────┐
    │ GGM Monument│          │ GGM Landgebruik  │
    │ Register    │          │ Register         │
    └─────────────┘          └──────────────────┘
         │                             │
         └────────┬────────────────────┘
                  │
                  ▼
         ┌──────────────────┐
         │   Burgers/Apps   │
         │   (single view)  │
         └──────────────────┘
```

#### Scenario B: Wasstraat als "Federated Consumer"

Wasstraat consumeert data uit GGM-registers, enriches met archaeologische context.

```
┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐
│ GGM Monument     │  │ GGM Perceel      │  │ GGM Topografie   │
│ Register         │  │ Register         │  │ Register         │
└────────┬─────────┘  └────────┬─────────┘  └────────┬─────────┘
         │                     │                     │
         └─────────────────────┼─────────────────────┘
                               │ API calls
                               ▼
                   ┌──────────────────────────────┐
                   │   Wasstraat Federation       │
                   │   - Enriched view            │
                   │   - Archaeological context  │
                   │   - Crosslinks               │
                   └──────────────────────────────┘
                               │ Publish
                               ▼
                    ┌──────────────────────┐
                    │  GGM Archeologische  │
                    │  Vondsten Register   │
                    └──────────────────────┘
```

#### Praktisch: API-Implementatie

```python
# wasstraat/api/ggm.py
from fastapi import FastAPI, Query
from wasstraat.models import Opgraving

app = FastAPI(title="Wasstraat GGM API")

@app.get("/ggm/opgraving/{id}",
         response_model=GGMOpraving)
async def get_opgraving_ggm(id: str):
    """
    Haal opgraving in GGM-formaat op.

    Returns:
        GGMOpraving: Opgraving-data conform GGM schema
    """
    opgraving = await Opgraving.get(id)

    # Map Wasstraat → GGM
    return GGMOpraving(
        opgraving_naam=opgraving.name,
        opgraving_locatie=opgraving.geometry,
        opgraving_periode_start=opgraving.start_date,
        opgraving_periode_einde=opgraving.end_date,
        opgraving_verantwoordelijke=opgraving.responsible_party_id,
    )

@app.get("/ggm/opgraving/",
         response_model=List[GGMOpraving])
async def list_opgraving_by_perceel(
    perceel_id: str = Query(...)
):
    """
    Vind alle opgravingen die een perceel raken.

    Args:
        perceel_id: GGM Perceel identifier
    """
    # Fetch perceel geometrie uit GGM
    perceel = await ggm_api.get_perceel(perceel_id)

    # Find opgravingen die geometrie raken
    opgravingen = await Opgraving.find_by_geometry(
        geometry=perceel.geometry,
        buffer_meters=100
    )

    return [GGMOpraving.from_wasstraat(o) for o in opgravingen]
```

### Pijler 3: Common Ground Compliance

**Doel**: Vasststellen dat Wasstraat Common Ground principes implementeert.

| Principe | Beschrijving | Wasstraat Status | Actie |
|----------|-------------|-----------------|--------|
| **API first** | Data via APIs accessible | Primitief | Standaard REST API builden |
| **Data bij source** | Gemeente is bron | ✓ Delft eigenaar | Blijven, vastleggen in governance |
| **Citizen-centric** | Burger staat centraal | Partial | Focus op erfgoed-professionals iniceel |
| **No copy principle** | Geen data duplicatie | ✓ SingleStore centraal | Blijven handhaven |
| **Open standaards** | Gebruik open standaards | Partial | Adopt CIDOC CRM, RDF, etc. |
| **Modulair** | Losse componenten | ✓ Modular arch | Sterkte huiden |
| **Transparant** | Open governance | ✓ Open source | Sterkte huiden |

**Implementatie per principe:**

#### API First
```yaml
# In fase 2 van roadmap
- OpenAPI 3.0 spec voor alle endpoints
- Versionering (v1, v2, etc.)
- Rate limiting en quota's
- Standard HTTP status codes
- REST conventions
```

#### Data bij Source
```yaml
# Governance document
Data Stewardship:
  archeologische_data:
    owner: "Gemeente Delft / Stichting Reuvens"
    custodian: "Wasstraat platform"
    access_model: "Read via GGM API, Write via authenticated upload"
    retention: "Permanent (erfgoed)"
    backup: "Daily, DANS e-Depot long-term archival"
```

#### Open Standaards
```yaml
# Configuration
open_standards:
  - name: "CIDOC CRM"
    role: "Semantic data model"
    mapping_file: "standards/cidoc_crm_mapping.rdf"

  - name: "SKOS"
    role: "Concept schemes (dating periods, materials)"
    url: "https://www.w3.org/TR/skos-reference/"

  - name: "OGC GeoJSON"
    role: "Spatial data exchange"
    usage: "All geometry in API responses"

  - name: "ISO 8601"
    role: "Temporal data"
    usage: "All date/time fields"

  - name: "BagAPI"
    role: "Building/address reference"
    usage: "Link buildings to excavations"
```

### Pijler 4: Data Governance & Quality

**Doel**: Vastleggen van data-ownership, -qualiteit, en -lifecycle.

#### Data Governance Charter

```markdown
# Wasstraat Data Governance Charter

## Rollen en Verantwoordelijkheden

### Data Owner: Gemeenteraad Delft (via erfgoedcommissie)
- Bepaalt doeleinden van archeologische data-verzameling
- Goedkeurt publicatie en delen
- Beslist over dataretentie

### Data Custodian: Stichting Reuvens
- Onderhoudt Wasstraat platform
- Zorgt voor data-kwaliteit
- Faciliteert wetenschappelijk gebruik

### Data Steward: Gemeente Delft (erfgoed-afdeling)
- Beheerst dagelijks dataproces
- Onboardt nieuwe gegevensbronnen
- Handelt gebruiker-vragen af

## Data Kwaliteit Richtlijnen

### Minimale Kwaliteit voor Publicatie
- Volledigheid: ≥85% velden ingevuld (excl. optionele)
- Accuratesse: Geometrische validatie + expert review
- Uniciteit: Geen duplicaten
- Actualiteit: ≤1 maand oud voor actieve sites
- Compliance: Alle ABR-termen en standaard-codelijsten

### Data Quality Scorecard
```
Opgraving X "Rembrandtplein 2023"
├─ Completeness:      92% ✓
├─ Consistency:       98% ✓
├─ Accuracy:          95% ✓
├─ Temporal validity: 100% ✓
└─ Overall quality:   96% (PASS - publiceerbaar)
```

## Data Lifecycle

```
┌──────────┐     ┌──────────┐     ┌──────────┐     ┌──────────┐
│ Collection
│          │────▶│ Validation
│          │     │          │────▶│Publication
│          │     │          │     │          │────▶│ Archive
│ (Raw)    │     │ (QA)     │     │ (Live)   │     │ (Long-term)
└──────────┘     └──────────┘     └──────────┘     └──────────┘
     │                                                    │
     └────────────────────── Preservation Path ──────────┘
          (DANS e-Depot, Digital Heritage)
```

## Intellectual Property & Attribution

- **Datasets**: CC-BY 4.0 (with attribution to city/Reuvens)
- **Metadata**: Open data
- **Original excavation reports**: Separate copyright (usually public domain after 25 yrs)
- **Researcher contributions**: Cited, with option for CC-BY-NC

## Access Control

| Role | Collection | Validation | Publication | Archive |
|------|-----------|------------|-------------|---------|
| Public | Read | None | Read | Read |
| Archaeologist | Read | None | Read | Read |
| Data Manager | Read/Write | Read/Write | Read | Read |
| Administrator | Full | Full | Full | Full |
```

## Roadmap: GGM Integratie per Fase

### Fase 1: Inventory & Mapping (Maanden 1-3)
- [ ] GGM-entiteiten inventariseren
- [ ] Archaeologische concepten mappen naar GGM
- [ ] Formele beschrijving in GGM-schema's
- [ ] Governancedocument opstellen

### Fase 2: API & Technical Integration (Maanden 3-6)
- [ ] Standard REST API implementeren
- [ ] GGM-compliant data models
- [ ] Integration tests
- [ ] API documentatie (OpenAPI)

### Fase 3: Pilot Integration (Maanden 6-9)
- [ ] Test met GGM-systeem van Delft
- [ ] Validate data flows
- [ ] Performance testing
- [ ] Feedback loop

### Fase 4: Generalisatie (Maanden 9-12)
- [ ] Template voor andere gemeenten
- [ ] Configuration voor gemeente-specific GGM-interpretaties
- [ ] Community feedback

## Success Criteria

- ✓ Wasstraat-data beschikbaar via GGM API
- ✓ Data gemapped naar GGM-schema's
- ✓ Governancedocument ondertekend door stakeholders
- ✓ Minimum 3 externe systemen kunnen integreren
- ✓ Data-kwaliteit compliance ≥90%
- ✓ CIDOC CRM alignment gevalideerd

## Referenties

- [Common Ground Manifesto](https://commonground.nl)
- [CIDOC CRM Specification](http://www.cidoc-crm.org)
- [GGM Architectuur Delft](https://delft.nl/informatiemodel)
- [Archis Datastandaard](https://www.archis.nl)
