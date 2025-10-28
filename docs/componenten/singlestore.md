# SingleStore

## Overzicht

SingleStore is de centrale gegevensopslaglaag van Wasstraat Archeologische Data. Het is een **aangepast NoSQL-systeem** (gebouwd op MongoDB) dat ongegenereerde flexibiliteit biedt bij het opslaan van archeologische gegevens.

!!! note "Belangrijk"
    SingleStore is geen commercieel product, maar een speciaal ontworpen, interne NoSQL-opslagsysteem. Dit geeft volledige controle over datastructuren en queryoptimalisatie.

## Kernprincipes

### Schema-vrijheid

In tegenstelling tot traditionele relationele databases legt SingleStore geen vast schema op. Dit maakt het ideaal voor archeologische data met:

- Heterogene structuren
- Variabele attributen
- Ongestructureerde metadata

```json
{
  "artefact": "WSTR-2024-001",
  "type": "aardewerk",
  "descriptie": "Fragmentarisch aardewerk, handgevormd",
  "dateringen": [
    {"periode": "Vroeg Bronstijd", "type": "gis_analyse"},
    {"periode": "circa 2000 vC", "type": "schatting_expert"}
  ],
  "locatie": {
    "coördinaten": [52.3702, 4.8952],
    "graafvak": "G12",
    "diepte": "0.65m"
  },
  "materiaal": ["aarde", "kwarts"],
  "fotografie": {
    "aantal": 4,
    "referenties": ["WSTR-2024-001-001.jpg", "WSTR-2024-001-002.jpg"]
  }
}
```

### Polymorfisme en Metadatering

SingleStore ondersteunt polymorfische gegevenstypen door middel van geavanceerde metadatering:

- **Type-informatie**: Metatags geven aan wat het gegevenstype is
- **Hiërarchische thesauri**: Categorisering en ondergroeperingen van gegevenstypen
- **Dynamische velden**: Velden kunnen naar behoefte worden toegevoegd of gewijzigd

!!! tip "Metadatering"
    Metadata helpt het systeem te begrijpen wat elk gegevensveld betekent en hoe het moet worden geïnterpreteerd, ook al ontbreekt een vast schema.

## Architectuur

### Opslagstructuur

```
┌─────────────────────────────────┐
│  SingleStore (NoSQL Database)   │
└────────┬────────────────────────┘
         │
         ├─► Collections
         │   ├─ artefacten
         │   ├─ locaties
         │   ├─ dateringen
         │   └─ ...
         │
         ├─► Metadatering
         │   ├─ Typesinformatie
         │   ├─ Thesauri
         │   └─ Validatieregels
         │
         └─► Indexen
             ├─ Fulltext
             ├─ Geografisch
             └─ Chronologisch
```

### Hiërarchische Thesauri

SingleStore beheerst complexe woordenlijsten met hiërarchische structuren:

```
Periode
├─ Prehistorie
│  ├─ Steentijd
│  │  ├─ Paleolithicum
│  │  ├─ Mesolithicum
│  │  └─ Neolithicum
│  └─ Bronstijd
│     ├─ Vroeg Bronstijd
│     ├─ Midden Bronstijd
│     └─ Laat Bronstijd
└─ Historisch
   ├─ Romaans
   ├─ Middeleeuwen
   └─ Moderner
```

## Flexibele Datastructuren

### Voorbeeld: Verschillende Artefacttypes

Een van de voornaamste voordelen is dat verschillende artefacttypes zonder problemen kunnen worden opgeslagen:

```json
{
  "_id": "WSTR-2024-001",
  "type": "aardewerk",
  "vorm": "pot",
  "decoratie": "ingedrukt motief"
}
```

```json
{
  "_id": "WSTR-2024-002",
  "type": "werktuig",
  "materiaal": "steen",
  "schnittechniek": "debitage"
}
```

```json
{
  "_id": "WSTR-2024-003",
  "type": "structuur",
  "soort": "paalspoor",
  "diameter": 0.35,
  "diepte": 0.78
}
```

Alle drie de records kunnen zonder problemen in dezelfde collection worden opgeslagen.

## Data-onafhankelijkheid

Een cruciaal voordeel van SingleStore is dat het **geen erfenis neemt van de originele opslagstructuur**. Dit betekent:

- Data wordt **gelijk gesteld** wanneer het wordt opgeslagen
- De originele structuur uit Excel, Word of Access wordt niet meegenomen
- Normalisatie en harmonisering vinden plaats in de transformatie- en validatielagen

!!! success "Voordeel"
    Dit maakt het eenvoudig om data uit heel verschillende bronnen in één enkel systeem samen te voegen, zonder dat de oorspronkelijke diversiteit aan structuren problemen veroorzaakt.

## Best Practices

### Naamgeving

- Gebruik consistent naamschema voor collections (bijv. `artefacten`, `locaties`, `structuren`)
- Vermijd speciale karakters in veldnamen
- Gebruik snake_case voor veldnamen

### Documenten

- Houd documenten logisch gegroepeerd
- Vermijd zeer diep geneste structuren (meer dan 5 niveaus)
- Gebruik arrays voor herhalende gegevens

### Performance

- Creëer indexen voor veelgebruikte zoekcriteria
- Monitor de grootte van documenten
- Denormaliseer voorzichtig voor veel voorkomende querys

## Queries

SingleStore ondersteunt krachtige queryinterfaces:

```javascript
// Alle artefacten uit periode "Bronstijd"
db.artefacten.find({
  "dateringen.periode": "Bronstijd"
})

// Artefacten in geografisch gebied
db.artefacten.find({
  "locatie.coördinaten": {
    $near: [52.3702, 4.8952],
    $maxDistance: 5000
  }
})

// Fulltextzoeking
db.artefacten.find({
  $text: { $search: "handgevormd aardewerk" }
})
```

## Integratie met andere Lagen

SingleStore werkt nauw samen met:

- **Extractie**: Ontvangt en slaat opgehaalde data op
- **Transformatie**: Verwerkt en normaliseert opgeslagen data
- **Validatie**: Voert controles uit op opgeslagen records
- **Crossviews**: Identificeert verbanden en duplicaten
- **Zoeken**: Voert geavanceerde queries uit

