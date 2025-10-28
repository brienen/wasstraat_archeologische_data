# Crossviews

## Overzicht

Crossviews is het geavanceerde relatieidentificatie-systeem van Wasstraat Archeologische Data. Dit innovatieve onderdeel vormt de backbone voor herkenning van verbanden tussen gegevens, deduplicatie en gegevensintelligentie.

!!! success "Kerninnov "
    Crossviews wordt momenteel ontwikkeld als zelf-leerend (machine learning) systeem voor verhoogde universaliteit en automatische inlierzoeking. Dit is een sleutelinnovatie van het platform.

## Functionaliteit

### 1. Relatie-Identificatie

Crossviews identificeert verborgen relaties tussen records die aanvankelijk niet verbonden lijken:

```
Record A: "Potscherf, Amsterdam, Bronstijd"
Record B: "Aardewerk fragment, Amsterdam, 1800 vC"
Record C: "Pottery sherd, Amsterdam, Bronze Age"

           │
           ▼
      Crossviews
           │
    ┌──────┼──────┐
    │      │      │
    ▼      ▼      ▼
 Taal   Context Periode
analyse analyse analyse
    │      │      │
    └──────┼──────┘
           │
           ▼
   Waarschijnlijke Verbanden:
   - B en A: dezelfde plaats, soortgelijke periode
   - C en B: dezelfde semantiek (aardewerk/pottery)
   - A en C: waarschijnlijk hetzelfde object
```

### 2. Record-Matching

Geavanceerde algoritmes voor het paarsgewijze vergelijken van records:

```
Gelijkenismetriek               Score
──────────────────────────────  ─────
Exacte tekstovereenkomst        95-100%
Fuzzy string matching           70-94%
Semantische gelijkenis          50-69%
Contextafhankelijke gelijkenis  30-49%
Geen gelijkenis                 <30%
```

#### Voorbeeld Matching

```json
{
  "record_a": {
    "id": "WSTR-001",
    "beschrijving": "handgevormd aardewerk",
    "periode": "Vroeg Bronstijd",
    "locatie": "Amsterdam"
  },
  "record_b": {
    "id": "AMS-47",
    "beschrijving": "hand made pottery",
    "periode": "2000-1500 vC",
    "locatie": "Amsterdam"
  },
  "match_score": 0.87,
  "overeenkomsten": [
    "locatie: exact (Amsterdam)",
    "periode: zeer waarschijnlijk (chronologische overlap)",
    "beschrijving: semantisch equivalent (aardewerk)",
    "vervaardigingstechniek: match (handgevormd)"
  ],
  "aanbeveling": "WAARSCHIJNLIJK_DUPLICATE"
}
```

### 3. Bronenintuïtie

Crossviews herkennen welke bronnen elkaar overlappen of aanvullen:

```
Bron 1 (Amsterdam Gemeente):
├─ 450 records
├─ Periode: 2500-1000 vC
├─ Thema's: huishoudartefacten
└─ Dekking: Amsterdam centrum

Bron 2 (Universiteit Amsterdam):
├─ 320 records
├─ Periode: 2000-500 vC
├─ Thema's: speciale vondsten
└─ Dekking: Amsterdam regio

         │
         ▼
    Crossviews Analyse
         │
    ┌────┴────┐
    │          │
    ▼          ▼
 Overlap   Aanvulling
 (~220     (~230 unieke
  records)  records per bron)

Bevinding: ~49% overlap, complementaire datasets
```

### 4. Machine Learning Mogelijkheden (In Ontwikkeling)

Het systeem wordt momenteel uitgebreid met ML-capaciteiten:

#### Zelf-Lerend Systeem

- **Trainingsfase**: Systeem leert van handmatig geverifieerde matches
- **Generalisering**: Patronen worden gegeneraliseerd naar nieuwe datasituaties
- **Adaptatie**: Algoritmes verbeteren naarmate meer data wordt verwerkt

#### Automatische Fouterkenning

```
Fuzzy Matching Voorbeelden:
"aardewerk"      ≈ "aardewerken"     (spellingsvariant)
"potscherf"      ≈ "potscherf"       (exact)
"Bronstijd"      ≈ "Bronze Age"      (semantiek)
"52.3702"        ≈ "52.37"           (afrondingsfout)
```

#### Uitbijtingsdetectie

Automatische herkenning van anomalieën en ongewone waarden:

```json
{
  "anomalieën_gedetecteerd": [
    {
      "record": "WSTR-2024-042",
      "veld": "diepte",
      "waarde": 125.5,
      "eenheid": "meter",
      "waarschijnlijkheid": 0.94,
      "verklaring": "Diepte onplausibel voor oppervlakte-vondsten"
    },
    {
      "record": "WSTR-2024-089",
      "veld": "datum_vondst",
      "waarde": "2127-03-15",
      "waarschijnlijkheid": 0.99,
      "verklaring": "Toekomstige datum, waarschijnlijk invoerfout"
    }
  ]
}
```

## Architectuur

```
┌─────────────────────────────────┐
│  Opgeslagen Data (SingleStore)  │
└────────────┬────────────────────┘
             │
             ▼
┌─────────────────────────────────┐
│   Crossviews Engine             │
├─────────────────────────────────┤
│ ✓ Tekstvergelijking             │
│ ✓ Semantische analyse           │
│ ✓ Contextafhankelijke matching  │
│ ✓ ML-gebaseerde patroonherkenning│
└────────────┬────────────────────┘
             │
         ┌───┴───┐
         │       │
         ▼       ▼
    Relatie- Anomalie-
    grafiek  rapportage
         │       │
         └───┬───┘
             │
             ▼
┌─────────────────────────────────┐
│  Deduplica-analyse & Rapporten  │
└─────────────────────────────────┘
```

## Verwerkingsfases

### Fase 1: Voorbereiding

- Normalisatie van invoegegevens
- Indeksering voor snelle opzoeking
- Cacheconstructie voor veelgebruikte queries

### Fase 2: Paarsgewijze Vergelijking

```python
# Pseudo-code
for record_a in dataset:
    for record_b in dataset:
        if record_a.id < record_b.id:  # Geen dubbele vergelijking
            similarity = calculate_similarity(
                record_a, record_b,
                metrics=['text', 'semantic', 'context']
            )
            if similarity > threshold:
                candidates.append((record_a, record_b, similarity))
```

### Fase 3: Contextanalyse

- Geografische nabijheid
- Chronologische overlap
- Materiaalconsistentie
- Bronspiegel

### Fase 4: ML-Classificatie

- Training op handmatig geverifieerde matches
- Classificatie van onbekende paren
- Continuous learning van feedback

### Fase 5: Rapportage

- Generatie van deduplicatie-aanbevelingen
- Anomalieverslagen
- Relatiegrafiek

## Uitvoer

### Deduplicatie-Aanbevelingen

```json
{
  "potentiële_duplicaten": [
    {
      "paar": ["WSTR-001", "AMS-047"],
      "overeenkomsten_percentage": 87,
      "vertrouwensniveau": "hoog",
      "aanbeveling": "WAARSCHIJNLIJK_DUPLICATE",
      "details": {
        "locatie_match": "exact",
        "periode_match": "zeer waarschijnlijk",
        "beschrijving_match": "fuzzy (87%)"
      }
    }
  ]
}
```

### Anomalierapporten

```json
{
  "anomalieën": [
    {
      "record_id": "WSTR-2024-042",
      "anomalie_type": "onplausibele_waarde",
      "veld": "diepte",
      "verwachte_bereik": "0.0 - 10.0",
      "geobserveerde_waarde": 125.5,
      "aanbeveling": "HANDMATIGE_VERIFICATIE_VEREIST"
    }
  ]
}
```

## Best Practices

!!! warning "Handmatige Verificatie"
    Hoewel Crossviews zeer accuraat is, wordt altijd handmatige verificatie van kritieke matches aanbevolen voordat records worden geconsolideerd.

- Controleer matches met hoge vertrouwensscore eerst
- Verifieer anomaliedetectie tegen bronwaarden
- Documenteer alle handmatig aangepaste matches
- Train het ML-systeem met feedback

## Integratie

Crossviews werkt samen met:

- **Transformatie**: Leert van transformatiepatronen
- **Validatie**: Kan abnormaliteiten valideren
- **Zoeken**: Ondersteunt "vind gelijkaardige records"
- **Configuratie**: Kan per gemeente fijn afgestemd worden

