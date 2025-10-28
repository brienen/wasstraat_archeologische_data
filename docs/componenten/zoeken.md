# Zoeken en Indexering

## Overzicht

Het zoeken en indexeringsysteem van Wasstraat Archeologische Data biedt krachtige, snelle queryopties over het hele gegevensreservoir. Dit onderdeel is bewust gemaakt voor polymorfische gegevens en multidimensionale zoekmogelijkheden.

## Kernfunctionaliteiten

### 1. Fulltext-Zoeking

Geavanceerde tekstzoeking over alle ongestructureerde velden:

```python
# Voorbeelden van fulltext-queries
results = search.fulltext("handgevormd aardewerk Amsterdam")
results = search.fulltext("Bronstijd fragment")
results = search.fulltext("potscherf kwarts")
```

#### Zoekmechanisme

```
Zoekinvoer: "handgevormd aardewerk"
            │
            ▼
┌───────────────────────────────────┐
│ Tokenisering                      │
│ "handgevormd" | "aardewerk"       │
└────────────┬──────────────────────┘
             │
             ▼
┌───────────────────────────────────┐
│ Lemmatisering (Nederlands)        │
│ "handgevormd" → "hand"+"gevormd"  │
│ "aardewerk" → "aard"+"werk"       │
└────────────┬──────────────────────┘
             │
             ▼
┌───────────────────────────────────┐
│ Index Lookup                      │
│ Alle documenten met beide termen  │
└────────────┬──────────────────────┘
             │
             ▼
┌───────────────────────────────────┐
│ Ranking (BM25 algoritme)          │
│ • Termfrequentie                  │
│ • Inverse documentfrequentie      │
│ • Documentlengte normalisatie     │
└────────────┬──────────────────────┘
             │
             ▼
┌───────────────────────────────────┐
│ Zoekresultaten (gesorteerd)       │
└───────────────────────────────────┘
```

### 2. Fuzzy-Zoeking

Tolerantie voor typografische fouten en spellingsvarianties:

```
Zoekinvoer: "potscherf"
            │
            ├─→ Exacte match: "potscherf" (score: 1.0)
            │
            ├─→ Fuzzy matches:
            │   ├─ "potscherven" (1 toevoeging) - score: 0.85
            │   ├─ "potsherd" (Engels) - score: 0.80
            │   ├─ "potscherp" (typografiefout) - score: 0.75
            │   └─ "pottenscherf" (spellingsvariant) - score: 0.70
            │
            └─→ Gefilterde resultaten (score > 0.70)
```

#### Fuzzy-Algoritme

Het systeem gebruikt een combinatie van:

- **Levenshtein-afstand**: Minste aantal edits nodig
- **Jaro-Winkler**: Voor gelijkaardige prefixteksten
- **N-gram matching**: Voor fragmentaire overeenkomsten

### 3. AI-Gebaseerde Indexering (In Ontwikkeling)

Geavanceerde semantische indexering met machine learning:

```
Vectorrepresentatie van Documenten:

Artefact 1: "handgevormd aardewerk fragment"
                    │
                    ▼
        ┌──────────────────────┐
        │  NLP-Model (BERT)    │
        └──────────┬───────────┘
                   │
                   ▼
        Semantische vector [n-dimensies]
        Bijv: [0.45, 0.82, 0.12, ..., 0.63]

Artefact 2: "hand crafted pottery shard"
                    │
                    ▼
        ┌──────────────────────┐
        │  NLP-Model (BERT)    │
        └──────────┬───────────┘
                   │
                   ▼
        Semantische vector [n-dimensies]
        Bijv: [0.43, 0.84, 0.11, ..., 0.61]

Gelijkenis-berekening (cosinus-overeenkomst):
cos(vector_1, vector_2) = 0.98 (zeer gelijk!)
```

#### Voordelen

- Begrijpt semantische betekenis
- Werkt in meerdere talen
- Vindt conceptueel soortgelijke items
- Tolerant voor variaties

## Indexering Componenten

### 1. Fulltext Index

```json
{
  "index_type": "fulltext",
  "index_name": "artefacten_text",
  "velden": [
    "beschrijving",
    "materiaal_omschrijving",
    "locatie_notities",
    "onderzoeksnota's"
  ],
  "taal": "nederlands",
  "analyzer": {
    "type": "standard",
    "stopwords": ["de", "het", "een", "van"]
  },
  "parameters": {
    "min_term_length": 3,
    "max_term_length": 100
  }
}
```

### 2. Fuzzy Index

```json
{
  "index_type": "fuzzy",
  "index_name": "artefacten_fuzzy",
  "velden": [
    "object_id",
    "artefact_type",
    "materiaal",
    "periode"
  ],
  "fuzzy_parameters": {
    "max_edits": 2,
    "prefix_length": 1,
    "boost": 1.5
  }
}
```

### 3. Geografische Index

```json
{
  "index_type": "geospatial",
  "index_name": "artefacten_geo",
  "velden": [
    "locatie.coördinaten"
  ],
  "type": "geohash",
  "precision": 10
}
```

### 4. Chronologische Index

```json
{
  "index_type": "temporal",
  "index_name": "artefacten_chrono",
  "velden": [
    "discovery_date",
    "periode_start",
    "periode_eind"
  ],
  "resolutie": "dag"
}
```

## Querytypen

### Eenvoudige Queries

```python
# Fulltext-zoeking
search.find_text("handgevormd aardewerk")

# Fuzzy-zoeking
search.find_fuzzy("potscherf", tolerance=0.8)

# Gelijk aan
search.equal("artefact_type", "aardewerk")
```

### Geavanceerde Queries

```python
# Combinatie met operatoren
search.find({
  "must": [
    {"text": "aardewerk"},
    {"equal": {"periode": "Bronstijd"}}
  ],
  "should": [
    {"text": "handgevormd"},
    {"text": "ingegraven motief"}
  ],
  "must_not": [
    {"equal": {"status": "verloren"}}
  ]
})

# Geografische range-query
search.find_geo_within(
  center=[52.3702, 4.8952],
  radius_m=5000,
  must=[{"period": "Bronstijd"}]
)

# Chronologische range-query
search.find_temporal(
  date_start="2000-01-01 vC",
  date_end="500-01-01 vC",
  must=[{"material": "aarde"}]
)
```

### Faceted Search

Classificatie van resultaten in kategoriën:

```python
results = search.find_text("aardewerk")
results.facets = {
  "periode": {
    "Bronstijd": 245,
    "IJzertijd": 187,
    "Romeins": 92,
    "Middeleeuwen": 34
  },
  "materiaal": {
    "aarde": 487,
    "steen": 12,
    "andere": 59
  },
  "status": {
    "compleet": 82,
    "fragmentair": 437,
    "verloren": 39
  }
}
```

## Architectuur

```
┌─────────────────────────────────────────┐
│  SingleStore Gegevens               │
└────────────┬────────────────────────────┘
             │
             ▼
┌─────────────────────────────────────────┐
│  Indexering Pipeline                │
├─────────────────────────────────────────┤
│ 1. Data Extraction                  │
│    (Velden selecteren)              │
│                                         │
│ 2. Preprocessing                    │
│    (Tokenisering, Normalisatie)     │
│                                         │
│ 3. Indexing                         │
│    (Fulltext, Fuzzy, Geo, etc.)     │
│                                         │
│ 4. Indexen Persistentie             │
│    (Opslag in Search Engine)        │
└────────────┬────────────────────────────┘
             │
         ┌───┴───┬───────┬──────┐
         │       │       │      │
         ▼       ▼       ▼      ▼
    Fulltext  Fuzzy   Geo   Chrono
    Index    Index   Index  Index
         │       │       │      │
         └───┬───┴───────┴──────┘
             │
             ▼
┌─────────────────────────────────────────┐
│  Query Engine                       │
│  ├─ Query Parser                    │
│  ├─ Query Optimizer                 │
│  └─ Results Ranking                 │
└────────────┬────────────────────────────┘
             │
             ▼
┌─────────────────────────────────────────┐
│  Zoekresultaten                     │
│  (Gesorteerd, Gefacetteerd)         │
└─────────────────────────────────────────┘
```

## Polymorfische Gegevens

Een van de kernuitdagingen is zoeken in polymorfische data. Wasstraat behandelt dit door:

```json
{
  "universal_fields": [
    "object_id",
    "beschrijving",
    "locatie",
    "discovery_date",
    "periode"
  ],
  "type_specific_fields": {
    "aardewerk": ["vorm", "decoratie", "branding"],
    "werktuig": ["functie", "schijf_techniek"],
    "structuur": ["type", "afmetingen", "diepte"]
  }
}
```

Alle universele velden worden standaard geïndexeerd. Type-specifieke velden worden optioneel geïndexeerd.

## Performance Optimalisering

### Indexen Caching

```
┌────────────────────────────────┐
│  Populaire Queries Cache       │
├────────────────────────────────┤
│ Query 1: "Bronstijd"           │
│ Hit Rate: 87%                  │
│ Avg Response: 15ms             │
│                                │
│ Query 2: "Amsterdam aardewerk" │
│ Hit Rate: 62%                  │
│ Avg Response: 45ms             │
│                                │
│ Query 3: "Handgevormd"         │
│ Hit Rate: 54%                  │
│ Avg Response: 127ms            │
│                                │
│ (Minder hits = indexering      │
│  moet geoptimaliseerd worden)  │
└────────────────────────────────┘
```

### Incrementele Indexering

Bij wijzigingen worden alleen gemodificeerde velden opnieuw geïndexeerd:

```
Record Wijziging:
  Field 1 (geïndexeerd): gewijzigd
  Field 2 (geïndexeerd): ongewijzigd
  Field 3 (niet geïndexeerd): gewijzigd

→ Alleen Field 1 wordt opnieuw geïndexeerd
→ Field 2 behoudt bestaande index
→ Field 3 vereist geen indexering
```

## Best Practices

!!! warning "Indexoptimalisatie"
    Niet alle velden hoeven te worden geïndexeerd. Over-indexering verslechtert performance.

- Indexeer alleen veelgebruikte zoekvelden
- Monitor query-performance regelmatig
- Verwijder ongebruikte indexen
- Test grote query's op testomgeving

!!! tip "Zoekinstructies"
    Gebruikers kunnen beste resultaten behalen door:
    - Nauwkeurige zoekwoorden gebruiken
    - Operators combineren (AND, OR, NOT)
    - Filters toe te passen voor nauwkeurigheid
    - Faceten te gebruiken voor verfijning

## Integratie

Het zoeken en indexeringssysteem werkt samen met:

- **SingleStore**: Databestand voor indexering
- **Validatie**: Indexeert alleen gevalideerde records
- **Crossviews**: Kan "soortgelijke items" suggeren
- **Configuratie**: Maakt aangepaste indexen mogelijk

