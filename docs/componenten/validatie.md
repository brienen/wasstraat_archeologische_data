# Validatie

## Overzicht

De validatielaag vormt de kwaliteitscontroleur van Wasstraat Archeologische Data. Dit onderdeel voert systematische controles uit op alle opgeslagen gegevens en vergewist zich van semantische integriteit en logische consistentie.

## Kernfunctionaliteiten

### 1. Gegevenslogica Validatie

Controle van gegevens tegen voorafgestelde logische regels:

```
Validatieregels Voorbeelden:
──────────────────────────────────────────────────

1. Datumlógica
   ├─ Vondstdatum ≤ Verwerkingsdatum
   ├─ Onderzoeksstartdatum ≤ Onderzoekseindatum
   └─ Periode moet chronologisch plausibel zijn

2. Geografische lógica
   ├─ Coördinaten moeten in Nederland liggen
   ├─ Graafvak moet binnen onderzoeksgebied liggen
   └─ Diepte moet positief zijn

3. Semantische lógica
   ├─ Materiaaltype moet geldig zijn
   ├─ Artefacttype moet erkend zijn
   └─ Bouwperiode moet geldig zijn

4. Relationele lógica
   ├─ Artefact moet aan een locatie gekoppeld zijn
   ├─ Verwijzingen moeten bestaan
   └─ Hiërarchie moet consistent zijn
```

#### Voorbeeld Validatieregels

```python
from validatie import ValidationRule, Validator

# Definitie van validatieregels
regel_datum = ValidationRule(
    name="vondstdatum_logisch",
    check=lambda record: record.get('vondstdatum') <= record.get('verwerkingsdatum'),
    error_message="Vondstdatum kan niet na verwerkingsdatum liggen"
)

regel_coördinaten = ValidationRule(
    name="coördinaten_nederland",
    check=lambda record: (50.75 <= record.get('latitude') <= 53.5 and
                         3.4 <= record.get('longitude') <= 7.2),
    error_message="Coördinaten liggen buiten Nederlands grondgebied"
)

# Toepassing
validator = Validator([regel_datum, regel_coördinaten])
resultaten = validator.validate(dataset)
```

### 2. Caching Mechanisme

Intelligente opslag van validatieresultaten ter vermindering van computationele overhead:

```
Primera validatie:
┌─────────────────────────────┐
│  Record WSTR-001            │
│  ├─ Datum-regel: PASS       │
│  ├─ Coördinaten-regel: PASS │
│  ├─ Materiaal-regel: PASS   │
│  └─ Caching → Opslaan
└─────────────────────────────┘

Vervolgzoeking (uit cache):
┌─────────────────────────────┐
│  Record WSTR-001            │
│  ├─ Cache Hit!              │
│  ├─ Resultaat: PASS (snel)  │
│  └─ Geen re-berekening      │
└─────────────────────────────┘
```

#### Cache-Structuur

```json
{
  "cache_entry": {
    "record_id": "WSTR-001",
    "timestamp_validatie": "2024-03-09T10:30:00Z",
    "timestamp_record_wijziging": "2024-03-08T15:45:00Z",
    "validatie_status": "PASS",
    "regels_gecontroleerd": [
      "vondstdatum_logisch",
      "coördinaten_nederland",
      "materiaal_geldig"
    ],
    "cache_geldig_tot": "2024-03-16T10:30:00Z"
  }
}
```

### 3. Cache-Consistentie Beheer

Automatische invalidatie en vernieuwing van cache bij gegevenswijzigingen:

```
Scenario: Record Wijziging
         │
         ▼
┌────────────────────────────┐
│ Detectie: Record Modified  │
│ (timestamp check)          │
└────────────┬───────────────┘
             │
             ▼
┌────────────────────────────┐
│ Cache Invalidation         │
│ (gerelateerde records)     │
└────────────┬───────────────┘
             │
             ▼
┌────────────────────────────┐
│ Herschedulering            │
│ (validatie opnieuw qeued)  │
└────────────────────────────┘
```

#### Invalidatie-Triggers

- Record wijzigd
- Gerelateerde records wijzigen
- Validatieregels bijgewerkt
- Cache TTL (Time To Live) verstreken

### 4. Gelijktijdigheid Beheer

Robuuste afhandeling van concurrent verwerkende threads en processes:

```
Thread 1                     Thread 2
────────                     ────────
Validate Record A            Validate Record A
    │                             │
    ├─ Read Cache                 ├─ Read Cache
    │ (miss)                       │ (miss)
    │                             │
    ├─ Lock Record                │
    │ (acquire)                    │ (waiting...)
    │                             │
    ├─ Validate                   │
    │ (compute)                    │
    │                             │
    ├─ Write Cache                │
    │                             │
    ├─ Unlock                     │
    │                             │ (acquire lock)
    │                             │
    │                             ├─ Read Cache
    │                             │ (hit!)
    │                             │
    │                             ├─ Return Result
    │                             │
```

#### Implementatie

```python
from threading import Lock, RLock
from queue import Queue

class ThreadSafeValidator:
    def __init__(self):
        self.cache = {}
        self.locks = {}  # Per-record locks
        self.lock = RLock()  # Global lock

    def validate(self, record_id):
        # Verkrijg record-specifieke lock
        with self._get_lock(record_id):
            # Controleer cache
            if record_id in self.cache:
                return self.cache[record_id]

            # Voer validatie uit
            resultaat = self._validate_impl(record_id)

            # Cache resultaat
            self.cache[record_id] = resultaat
            return resultaat
```

## Architectuur

```
┌─────────────────────────────────┐
│  Opgeslagen Data (SingleStore)  │
└────────────┬────────────────────┘
             │
             ▼
┌─────────────────────────────────┐
│  Validatieregels Basisbibliotheek│
│  ├─ Datumvalidatie              │
│  ├─ Geografische validatie      │
│  ├─ Semantische validatie       │
│  └─ Relationele validatie       │
└────────────┬────────────────────┘
             │
             ▼
┌─────────────────────────────────┐
│  Validatie Engine               │
├─────────────────────────────────┤
│ ✓ Regeltoepassing               │
│ ✓ Cachecontrole                 │
│ ✓ Thread-Safety                 │
│ ✓ Gelijktijdighed Management    │
└────────────┬────────────────────┘
             │
             ▼
┌─────────────────────────────────┐
│  Cache Manager                  │
├─────────────────────────────────┤
│ • Resultaat-caching             │
│ • TTL Management                │
│ • Invalidatie-logica            │
│ • Lock Coordination             │
└────────────┬────────────────────┘
             │
             ▼
┌─────────────────────────────────┐
│  Validatierapporten & Logging   │
└─────────────────────────────────┘
```

## Validatie-Niveaus

### Niveau 1: Syntactische Validatie

Controle van basisgegevensstructuur:

```
✓ Verplichte velden aanwezig
✓ Gegevenstypen correct
✓ Geen null-waarden waar verboden
```

### Niveau 2: Semantische Validatie

Controle van betekenis en inhoud:

```
✓ Waarden liggen in toegestaan bereik
✓ Gekenmerkte categorieën
✓ Referentie-integriteit
```

### Niveau 3: Logische Validatie

Controle van relaties en consistentie:

```
✓ Temporale consistentie (datums)
✓ Geografische plausibiliteit
✓ Semantische coherentie
```

## Rapporten

### Validatiesamenvattingen

```json
{
  "validatierapport": {
    "moment": "2024-03-09T10:30:00Z",
    "dataset": "Alle records",
    "statistieken": {
      "totaal_records": 12500,
      "succesvol": 12475,
      "waarschuwingen": 15,
      "fouten": 10,
      "succes_percentage": 99.88
    },
    "fouten": [
      {
        "record_id": "WSTR-001",
        "regel": "vondstdatum_logisch",
        "ernst": "KRITIEK",
        "boodschap": "Vondstdatum na verwerkingsdatum"
      }
    ],
    "waarschuwingen": [
      {
        "record_id": "WSTR-042",
        "regel": "coördinaten_precisie",
        "ernst": "WAARSCHUWING",
        "boodschap": "Coördinaten hebben lage precisie"
      }
    ]
  }
}
```

## Best Practices

!!! warning "Regelconfiguratie"
    Validatieregels moeten zorgvuldig worden ingesteld. Te strenge regels kunnen valide data verwerpen; te soepele regels laten fouten door.

- Test nieuwe regels op steekproefgegevens
- Houdt regelwijzigingen in versiecontrole
- Document alle aangepaste regels
- Voer periodieke validatie-audits uit

!!! tip "Performance"
    Cache-instellingen afstemmen op update-frequentie:
    - Weinig updates: langere TTL (meer cache-hits)
    - Veel updates: kortere TTL (meer nauwkeurigheid)

## Integratie

De validatielaag werkt samen met:

- **SingleStore**: Valideert opgeslagen records
- **Transformatie**: Valideert transformatieresultaten
- **Crossviews**: Valideert geïdentificeerde relaties
- **Configuratie**: Maakt aangepaste validatieregels mogelijk
- **Zoeken**: Kan alleen gevalideerde data indexeren

