# Configuratie

## Overzicht

De configuratiemodule vormt het controlecentrum voor gemeentelijke aanpassingen en systeembeheer in Wasstraat Archeologische Data. Dit onderdeel stelt beheerders in staat hun eigen gegevensbronnen in te stellen, mappings te definiëren en lokale specifieke instellingen in te voeren zonder de kernarchitectuur te beschadigen.

## Kernfunctionaliteiten

### 1. Databronnen Configuratie

Gestructureerde definities voor externe databronnen:

```json
{
  "databron": {
    "id": "amsterdam_gemeente_2024",
    "naam": "Amsterdam Gemeente Vondsten",
    "type": "excel",
    "locatie": "/data/imports/amsterdam_2024.xlsx",
    "schema": {
      "sheet_naam": "Vondsten",
      "rijen_skip": 2,
      "koppen_rij": 1
    },
    "frequentie_import": "maandelijks",
    "volgende_import": "2024-04-09T02:00:00Z",
    "validatie_profiel": "amsterdam_standaard",
    "contactpersoon": "j.de.vries@amsterdam.nl"
  }
}
```

#### Ondersteunde Brontypen

```
┌──────────────────────────────────┐
│    Ondersteunde Brontypen        │
├──────────────────────────────────┤
│ • Excel (.xls, .xlsx)            │
│ • CSV (diverse scheidingstekens) │
│ • Access Database (.mdb)         │
│ • Word Document (.docx)          │
│ • XML                            │
│ • JSON                           │
│ • Custom API                     │
│ • Gescande documenten (OCR)      │
└──────────────────────────────────┘
```

### 2. Kolom-Mappings

Mapping van bronkolommen naar standaard Wasstraat schema:

```json
{
  "mapping": {
    "bron_id": "amsterdam_gemeente_2024",
    "kolom_mappings": {
      "VONDST_NR": {
        "target": "object_id",
        "type": "string",
        "verplicht": true
      },
      "DATUM_VONDST": {
        "target": "discovery_date",
        "type": "date",
        "format": "DD-MM-YYYY",
        "transformatie": "iso8601"
      },
      "PLAATS": {
        "target": "location_name",
        "type": "string",
        "normalisatie": "plaats_standaardisering"
      },
      "X_COORD": {
        "target": "longitude",
        "type": "float",
        "bron_crs": "EPSG:28992",
        "target_crs": "EPSG:4326"
      },
      "Y_COORD": {
        "target": "latitude",
        "type": "float",
        "bron_crs": "EPSG:28992",
        "target_crs": "EPSG:4326"
      },
      "BESCHRIJVING": {
        "target": "description",
        "type": "text",
        "max_length": 2000
      }
    }
  }
}
```

### 3. Alternatieve Kolomnamen

Ondersteuning voor variatiebewuste kolommappings:

```json
{
  "kolom_aliassen": {
    "object_id": [
      "VONDST_NR",
      "object_number",
      "FIND_ID",
      "artefact_nummer"
    ],
    "discovery_date": [
      "DATUM_VONDST",
      "vondstdatum",
      "DISCOVERY_DATE",
      "datum_vondst"
    ],
    "location_name": [
      "PLAATS",
      "plaats",
      "LOCATION",
      "LOCATIE"
    ]
  }
}
```

Dit vermindert handmatige configuratie door automatische herkenning van veelgebruikte naamgevingspatronen.

### 4. Categorieën en Woordenlijsten

Lokale categorietisering en thesaurus-extensies:

```json
{
  "categorieen": {
    "artefact_type": {
      "standaard": ["aardewerk", "werktuig", "sieraad", "structuur"],
      "amsterdam_specifiek": [
        "houtwerk_amsterdam",
        "tegel_delft",
        "speelgoed_19e_eeuw"
      ]
    },
    "materiaal": {
      "standaard": ["aarde", "steen", "hout", "metaal"],
      "amsterdam_extensies": [
        "bakstenen",
        "tegelwerk",
        "touwwerk"
      ]
    },
    "periode": {
      "standaard_abr": [
        "Paleolithicum",
        "Mesolithicum",
        "Neolithicum",
        "Bronstijd"
      ],
      "amsterdam_lokaal": [
        "Vroeg Middeleeuwen Amsterdam",
        "Bloktijd (1000-1500)",
        "Amsterdamse Goudse Eeuw (1600-1700)"
      ]
    }
  }
}
```

### 5. Lokale Specifieke Uitbreidingen

Ondersteuning voor gemeentelijke unieke behoeften zonder kernmodel-breuk:

```json
{
  "lokale_extensies": {
    "amsterdam": {
      "extra_velden": {
        "grachtbouw_fase": {
          "type": "enum",
          "opties": ["fase_I", "fase_II", "fase_III", "fase_IV"],
          "beschrijving": "Specifiek voor Amsterdam Grachtenonderzoeken"
        },
        "pakhuis_relatie": {
          "type": "string",
          "beschrijving": "Verwijzing naar historisch pakhuis"
        }
      },
      "validatieregels_extra": [
        {
          "regel": "grachtbouw_fase_chronologie",
          "beschrijving": "Fase moet chronologisch consistent zijn"
        }
      ]
    },
    "rotterdam": {
      "extra_velden": {
        "havenbouw_periode": {
          "type": "enum",
          "opties": ["oud_havengebied", "nieuwe_haven", "container_terminal"]
        },
        "bouwwerk_referentie": {
          "type": "string"
        }
      }
    }
  }
}
```

## Configuratie-Interface

### Web Dashboard

Beheerders kunnen configuraties beheren via een intuïtief dashboard:

```
┌──────────────────────────────────────────────┐
│  Wasstraat Configuratie Dashboard            │
├──────────────────────────────────────────────┤
│                                              │
│  Databronnen                                 │
│  ├─ Amsterdam Gemeente (actief)              │
│  ├─ Universiteit Amsterdam (actief)          │
│  └─ + Nieuwe Databron Toevoegen              │
│                                              │
│  Kolom-Mappings                              │
│  ├─ Amsterdam Mapping (bewerken)             │
│  ├─ Universiteit Mapping (bewerken)          │
│  └─ + Nieuwe Mapping Toevoegen               │
│                                              │
│  Categorieën & Woordenlijsten                │
│  ├─ Artefacttypes (bewerken)                 │
│  ├─ Materialen (bewerken)                    │
│  ├─ Periodes (bewerken)                      │
│  └─ + Nieuwe Categorie Toevoegen             │
│                                              │
│  Validatieregels                             │
│  ├─ Basis Validatieregels (alleen-lezen)    │
│  ├─ Amsterdam Regels (bewerken)              │
│  └─ + Nieuwe Regel Toevoegen                 │
│                                              │
│  Gebruikersbeheer                            │
│  ├─ Rollen en Toestemmingen                  │
│  ├─ API-sleutels                             │
│  └─ Logboek                                  │
│                                              │
└──────────────────────────────────────────────┘
```

## Gegevensuitwisselingsbeheer

### Import/Export Configuraties

Overzicht van gegevensstromingen:

```json
{
  "gegevensuitwisselingen": [
    {
      "id": "exchange_amsterdam_gemeente",
      "type": "import",
      "bron": "amsterdam_gemeente_2024",
      "frequentie": "maandelijks",
      "volgende_uitvoering": "2024-04-09",
      "status": "actief",
      "statistieken": {
        "invoervermeldingen": 1247,
        "succesvol": 1243,
        "fouten": 4,
        "waarschuwingen": 12
      }
    },
    {
      "id": "export_abr_integratie",
      "type": "export",
      "bestemming": "ABR Centrale Dienst",
      "frequentie": "driemaandelijks",
      "volgende_uitvoering": "2024-04-15",
      "status": "actief",
      "statistieken": {
        "geëxporteerde_records": 3847
      }
    }
  ]
}
```

### Logging en Auditing

Gedetailleerde verslaglegging van alle configuratie- en datautilischanges:

```json
{
  "logboekvermelding": {
    "timestamp": "2024-03-09T10:30:00Z",
    "gebruiker": "beheerder@amsterdam.nl",
    "actie": "KOLOMAPPING_WIJZIGING",
    "bron": "amsterdam_gemeente_2024",
    "wijzigingen": [
      {
        "veld": "PLAATS",
        "oud_doel": "location_name",
        "nieuw_doel": "location_name_norm"
      }
    ],
    "status": "GOEDGEKEURD",
    "goedkeuring_door": "systeembeheerder@amsterdam.nl"
  }
}
```

## Architectuur

```
┌────────────────────────────────────────────┐
│      Configuratie Module                   │
├────────────────────────────────────────────┤
│                                            │
│  ┌─────────────────────────────────────┐   │
│  │  Webinterface / API                 │   │
│  │  (Beheerders & Operators)           │   │
│  └────────────┬────────────────────────┘   │
│               │                            │
│  ┌────────────▼────────────────────────┐   │
│  │  Configuratie Storage               │   │
│  │  (MongoDB: config_db)               │   │
│  ├─────────────────────────────────────┤   │
│  │ • Databronnen                       │   │
│  │ • Kolom-mappings                    │   │
│  │ • Validatieregels                   │   │
│  │ • Categorieën                       │   │
│  │ • Lokale Extensies                  │   │
│  └────────────┬────────────────────────┘   │
│               │                            │
│  ┌────────────▼────────────────────────┐   │
│  │  Configuratie Services              │   │
│  │  ├─ Validator                       │   │
│  │  ├─ Applier                         │   │
│  │  └─ Auditlog                        │   │
│  └────────────┬────────────────────────┘   │
│               │                            │
│  ┌────────────▼────────────────────────┐   │
│  │  Systeemcomponenten                 │   │
│  │  (Extractie, Transformatie, etc.)   │   │
│  └─────────────────────────────────────┘   │
│                                            │
└────────────────────────────────────────────┘
```

## Best Practices

!!! warning "Configuratievalidatie"
    Alle configuratieveranderingen moeten worden gevalideerd voordat deze van kracht worden. Ongeldig instellingen kunnen systeemverstoring veroorzaken.

- Test configuraties op een testomgeving eerst
- Documenteer alle aangepaste instellingen
- Zorg voor regelmatige backups van configuraties
- Voer configuratiewijzigingen stap voor stap door

!!! success "Versiebeheer"
    Configuraties kunnen als code worden behandeld. Gebruik versiebeheer (Git) voor:
    - Sporen van wijzigingen
    - Rollback-mogelijkheid
    - Samenwerkingsoptimalisatie

## Integratie met andere Lagen

De configuratiemodule ondersteunt:

- **Extractie**: Definiëert databronnen en import-schema's
- **Transformatie**: Specificeert transformatieregels per gemeent
- **Validatie**: Biedt aangepaste validatieregels
- **Crossviews**: Kan ML-trainingsparameters configureren
- **Zoeken**: Configureert indexerings-strategieën

## Rollen & Toestemmingen

```json
{
  "rollen": [
    {
      "rol": "systeembeheerder",
      "rechten": [
        "alle_configuraties_lezen",
        "alle_configuraties_wijzigen",
        "gebruikersbeheer",
        "auditlog_lezen"
      ]
    },
    {
      "rol": "gemeente_beheerder",
      "rechten": [
        "eigen_databronnen_configureren",
        "eigen_mappings_wijzigen",
        "lokale_categorieën_beheren",
        "eigen_logs_lezen"
      ]
    },
    {
      "rol": "operator",
      "rechten": [
        "import_activeren",
        "export_activeren",
        "logs_lezen"
      ]
    }
  ]
}
```

