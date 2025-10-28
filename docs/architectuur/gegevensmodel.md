# Gegevensmodel en Semantiek

## Overzicht

Het gegevensmodel van Wasstraat is gegrondvest op de CIDOC CRM-familie van ontologieën, aangevuld met gespecialiseerde archeologische en wetenschappelijke extensies. Het model organiseert archeologische informatie rond 22 semantische referentiedatamodellen (SRDM's), die de kernentiteiten en hun relaties definiëren.

## Semantische Grondslag

### CIDOC CRM Familie

Het systeem bouwt voort op internationale standaarden voor informatiemodellering:

| Ontologie | Focus | Toepassing |
|-----------|-------|-----------|
| **CIDOC CRM** | Cultureel erfgoed in het algemeen | Basis voor alle domeinmodellering |
| **CRMarchaeo** | Archeologische processen en gegevens | Opgravingen, contexten, vondsten |
| **CRMsci** | Wetenschappelijke observatie en analyse | Laboratoriumwerk, dateringen, analyses |
| **CRMba** | Bouwkundig erfgoed | Architecturale elementen |
| **CRMgeo** | Geografische en ruimtelijke concepten | Locaties, coördinaten, grenzen |

### Thesauribronnen

Het systeem normaliseert terminologie via:

| Thesaurus | Beschrijving |
|-----------|-------------|
| **ABR** | Archeologisch Basisregister - Nederlandse standaard voor archeologische termen |
| **Gemeentelijk Gegevensmodel (GGM)** | Lokale administratieve gegevensdefinities |
| **Lokale Thesauribronnen** | Project- en archief-specifieke terminologie |

## Semantische Referentiedatamodellen (SRDM's)

22 kernmodellen structureren de archeologische informatie:

### Primaire Entiteiten

**Projecten & Onderzoek**
1. **Archaeological Project** - Overkoepelend onderzoeksproject
2. **Excavation** - Systematische opgraving
3. **Survey** - Oppervlakte- of luchtfotografisch onderzoek
4. **Analysis** - Wetenschappelijke analyse van vondsten/samples

**Ruimtelijke Eenheden**
5. **Site** - Archeologische locatie
6. **Place** - Geografische plaats
7. **Stratigraphic Unit** - Geologische/archeologische stratificatielaag
8. **Context** - Archeologische context (bijv. huisplaats, greppel)
9. **Area** - Onderzochte ruimte (rooster, quadrant)
10. **Trench** - Opgravingssleuf

**Materiaalkunde**
11. **Finds Collection** - Groep van samen gevonden objecten
12. **Artefact** - Vervaardigd voorwerp
13. **Feature** - In-situ structuur (bijv. vuurplaats, weg)
14. **Sample** - Monstermateriaal voor analyse
15. **Biological Object** - Biologisch/faunaal materiaal

**Documentatie**
16. **Image** - Fotografische opname
17. **Digital Object** - Gedigitaliseerde bron
18. **Textual Work** - Publicatie, rapport, artikel
19. **Archival Unit** - Archiefstuk

**Thesaurale Eenheden**
20. **Period** - Chronologische periode
21. **Person** - Individueel persoon
22. **Institution** - Organisatie of instelling

## CIDOC CRM Structuur

De CIDOC CRM organisatie van informatie volgt dit patroon:

```
E1: CRM Entity
├── E2: Temporal Entity
│   ├── E4: Persistent Item
│   │   ├── E18: Physical Thing
│   │   │   ├── E21: Person
│   │   │   ├── E39: Actor
│   │   │   └── E22: Man-Made Object
│   │   │       ├── E84: Information Carrier
│   │   │       └── E57: Archaeological Object
│   │   └── E41: Appellation
│   └── E5: Event
│       ├── E7: Activity
│       │   ├── E13: Attribute Assignment
│       │   ├── E19: Physical Object
│       │   └── ... [andere events]
│       └── E81: Transformation
└── E13: Attribute Assignment
```

## Relationele Model

Kern-entiteitsrelaties:

### Project → Excavation → Context → Finds

```
Archaeological Project
    │
    ├─→ Excavation (E7: Activity)
    │       │
    │       ├─→ Area (E26: Physical Feature)
    │       │   └─→ Trench (E26: Physical Feature)
    │       │
    │       ├─→ Stratigraphic Unit (E26: Physical Feature)
    │       │   └─→ Context (E26: Physical Feature)
    │       │       └─→ Finds Collection
    │       │           ├─→ Artefact (E22: Man-Made Object)
    │       │           ├─→ Biological Object (E18: Physical Thing)
    │       │           └─→ Sample (E18: Physical Thing)
    │       │
    │       └─→ Image (E38: Image)
    │
    └─→ Analysis (E7: Activity)
            ├─→ Input: Sample
            └─→ Output: Attribute Assignment
```

## Gegevensattributen per SRDM

### Archaeological Project
```json
{
  "id": "project_uuid",
  "title": "string",
  "description": "text",
  "startDate": "ISO 8601",
  "endDate": "ISO 8601",
  "location": "Place reference",
  "responsible": "Person/Institution reference",
  "relatedExcavations": ["excavation_uuid"],
  "relatedSurveys": ["survey_uuid"],
  "relatedAnalyses": ["analysis_uuid"]
}
```

### Excavation
```json
{
  "id": "excavation_uuid",
  "title": "string",
  "description": "text",
  "date": "ISO 8601",
  "season": "string",
  "location": "Place reference",
  "relatedProject": "project_uuid",
  "areas": ["area_uuid"],
  "trenches": ["trench_uuid"],
  "stratigraphicUnits": ["strunit_uuid"],
  "findCollections": ["collection_uuid"],
  "images": ["image_uuid"]
}
```

### Stratigraphic Unit
```json
{
  "id": "strunit_uuid",
  "description": "string",
  "depth_top": "float",
  "depth_bottom": "float",
  "color": "string (ABR-gestandaardiseerd)",
  "texture": "string (ABR-gestandaardiseerd)",
  "interpretation": "string (ABR-mapped)",
  "relatedContexts": ["context_uuid"],
  "relatedExcavation": "excavation_uuid",
  "datingEvidence": ["sample_uuid"]
}
```

### Context
```json
{
  "id": "context_uuid",
  "name": "string",
  "type": "string (ABR-mapped)",
  "description": "text",
  "stratigraphicUnit": "strunit_uuid",
  "area": "area_uuid",
  "findCollections": ["collection_uuid"],
  "cuts": ["context_uuid"],
  "cutBy": ["context_uuid"],
  "seals": ["context_uuid"],
  "sealedBy": ["context_uuid"]
}
```

### Artefact
```json
{
  "id": "artefact_uuid",
  "name": "string",
  "type": "string (ABR-mapped)",
  "material": "string (ABR-mapped)",
  "period": "period_uuid",
  "description": "text",
  "dimensions": {
    "length": "float",
    "width": "float",
    "height": "float"
  },
  "findCollection": "collection_uuid",
  "images": ["image_uuid"],
  "analyses": ["analysis_uuid"]
}
```

## Linked Open Data (LOD)

Het gegevensmodel ondersteunt Linked Open Data publishing:

- URIs voor alle kernentiteiten
- RDF-uitvoering via RDFLib
- CIDOC CRM property-mappingen
- Links naar externe autoriteiten (AAT, GeoNames, Wikidata)

## FAIR Data Principes

Alle gegevens volgen FAIR-principes:

| Principe | Implementatie |
|----------|--------------|
| **Findable** | Unieke URIs, thesaurus-gebaseerde indexering, gestructureerde metadaten |
| **Accessible** | HTTP REST API's, multiple export-formaten (JSON, RDF, CSV) |
| **Interoperable** | CIDOC CRM basis, ABR-harmonisering, SRDM-conformiteit |
| **Reusable** | Licentie-gestandaardiseerde metadata, volledige provenance-tracking, FAIR Data Maturity Levels |

## Uitbreidbaarheid

Het semantische model is ontworpen voor uitbreiding:

### Lokale Extensies
Instellingen kunnen lokale SRDM's definiëren die voortbouwen op het basismodel:

```xml
<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
         xmlns:crm="http://www.cidoc-crm.org/cidoc-crm/">
  <rdfs:Class rdf:about="http://wasstraat.nl/model/CustomContext"
             rdfs:subClassOf="&crm;E26">
    <!-- Lokale uitbreiding -->
  </rdfs:Class>
</rdf:RDF>
```

### Multi-Source Reconciliation
De UML-Transformer ondersteunt het merger van meerdere lokale modellen in het centrale CIDOC CRM-raamwerk.

## Data Validation

Alle inkomende gegevens worden gevalideerd tegen SRDM-definities:

| Validatieniveau | Beschrijving |
|---|---|
| **Syntactisch** | XML/JSON schema-conformiteit |
| **Semantisch** | CIDOC CRM property-constraints |
| **Domein** | ABR-thesaurus conformiteit |
| **Relatie** | Integriteitsconstraints tussen entiteiten |

Validatieresultaten voeden de handmatige schoonmaakinterface.
