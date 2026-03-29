# Transformatie

## Overzicht

De transformatielaag voert kritieke gegevenshomogenisering uit. Dit onderdeel zorgt ervoor dat gegevens uit diverse bronnen naar één gemeenschappelijk format worden omgezet en dat semantische variaties worden genormaliseerd.

## Kernfunctionaliteiten

### 1. ABR Thesaurus Afstemming

De ABR (Archeologische Basisregistratie) thesaurus vormt de basis voor standaardisering. De transformatielaag brengt alle periodebetekeningen in kaart naar officiële ABR-termen:

```
Originele waarde      →    ABR Term
────────────────────     ──────────
"Bronstijd"           →    "Bronstijd" (3000-800 vC)
"Bronze Age"          →    "Bronstijd"
"Brons periode"       →    "Bronstijd"
"3000-800 vC"         →    "Bronstijd"
```

!!! info "ABR Standaard"
    De ABR biedt gestandaardiseerde termen voor periodes, monumenttypen, materialen en andere archeologische concepten.

### 2. Spellingsnotering

Systematische correctie van spellingsfouten en inconsistenties:

```python
from transformatie import SpellingNormalizer

normalizer = SpellingNormalizer()

# Variaties worden naar standaardspelling omgezet
normalizer.normalize("aerdewerk") → "aardewerk"
normalizer.normalize("potscherf") → "potscherf"
normalizer.normalize("grondwerken") → "grondwerken"
```

#### Ondersteuning voor Diakritische Tekens

- Accenten: é, è, ê → e
- Umlauts: ü, ö, ä → u, o, a
- Aanhalingstekens: " " ' ' → "standaard

### 3. Harmonisering van Sleutels

Verschillende bronnen gebruiken verschillende naamgeving voor hetzelfde concept:

```
Bron A              Bron B              Genormaliseerd
──────              ──────              ──────────────
FIND_ID        →    ObjectID      →    object_id
GRONDWERK      →    Werktype      →    werk_type
DATUM_VONDST   →    DiscoveryDate →    discovery_date
COORDS_X       →    lon           →    longitude
COORDS_Y       →    lat           →    latitude
```

### 4. Datumnotering

Alle datums worden naar ISO 8601-format omgezet voor consistentie:

```
Invoer                      Genormaliseerd
──────                      ──────────────
"03-06-2024"           →    "2024-06-03"
"June 3, 2024"         →    "2024-06-03"
"3 juni 2024"          →    "2024-06-03"
"2024-06-03T14:30:00Z" →    "2024-06-03"
```

Onvolledig gespecificeerde datums:

```json
{
  "datum_exacte": null,
  "datum_jaar": 2024,
  "datum_seizoen": "zomer",
  "datum_geschatte_periode": "Vroeg Middeleeuwen"
}
```

### 5. Locatienotering

Normalisatie van coördinatensystemen en localiteitsaanduidingen:

#### Coördinatensystemen

```python
from transformatie import CoordinateNormalizer

normalizer = CoordinateNormalizer()

# Alle coördinaten worden naar WGS84 (EPSG:4326) omgezet
normalizer.convert(
  x=120000, y=400000,
  from_crs="EPSG:28992"  # RD Nieuw
) → (52.3702, 4.8952)    # WGS84
```

Ondersteunde coördinatensystemen:
- **WGS84** (EPSG:4326) - standaard
- **RD Nieuw** (EPSG:28992) - Nederlands coördinatensysteem
- **UTM Zone 31N** (EPSG:32631)
- **ETRS89** (EPSG:4258)

#### Plaats- en Adresbeschrijvingen

```json
{
  "plaats_omschrijving": "Waterlooplein, Amsterdam",
  "plaats_genormaliseerd": "Amsterdam",
  "gemeente": "Amsterdam",
  "provincie": "Noord-Holland",
  "land": "Nederland"
}
```

### 6. Deduplicatie

Identificatie en afhandeling van duplicaten:

```
Invoer records:
┌─────────────┬─────────────┬──────────────┐
│ Bron A      │ Bron B      │ Bron C       │
├─────────────┼─────────────┼──────────────┤
│ Object 001  │ Artefact 47 │ WSTR-2024-01 │
│ Fragmentair │ Fragment    │ Fragmentair  │
│ aardewerk   │ pottery     │ aardewerk    │
│ Amsterdam   │ Amsterdam   │ Amsterdam    │
│ 52.3702,    │ 52.37,      │ 52.37,       │
│ 4.8952      │ 4.89        │ 4.90         │
└─────────────┴─────────────┴──────────────┘
        │         │               │
        └─────────┴───────────────┘
                │
        Deduplicatie-analyse
                │
                ▼
        ┌──────────────────────┐
        │ Geconsolideerd record │
        │ ID: WSTR-2024-001    │
        │ [bron geïntegreerd]  │
        └──────────────────────┘
```

!!! warning "Deduplicatie Voorzichtigheid"
    Deduplicatie vereist zorgvuldige validatie. Foutieve deduplicatie kan tot verlies van informatie leiden. Alle consolidaties worden vastgelegd met bronverwijzingen.

## Architectuur

```
┌─────────────────────────────────┐
│  Ruwe Data uit SingleStore       │
└────────────┬────────────────────┘
             │
             ▼
┌─────────────────────────────────┐
│  ABR Thesaurus Afstemming       │
│  (Standaardisering)             │
└────────────┬────────────────────┘
             │
             ▼
┌─────────────────────────────────┐
│  Spellingsnotering & Tekens      │
│  (Normalisatie)                 │
└────────────┬────────────────────┘
             │
             ▼
┌─────────────────────────────────┐
│  Sleutel- en Datumharmonisering │
├─────────────────────────────────┤
│  Coördinaat Transformatie       │
│  Deduplicatie                   │
└────────────┬────────────────────┘
             │
             ▼
┌─────────────────────────────────┐
│  Getransformeerde Data          │
└─────────────────────────────────┘
```

## Configuratie

De transformatielaag wordt aangestuurd door twee configuratiebestanden in de `wasstraat_config/`-directory:

### Harmonisatie-mapping (Excel)

Het bestand `Wasstraat_Config_HarmonizeV3.xlsx` definieert de veldmapping per objecttype: welke kolom in de brondata correspondeert met welk veld in het geharmoniseerde datamodel. Zie [Aan de slag](../aan-de-slag.md#5-wasstraat_config_harmonizev3-configureren) voor details.

### Datacorrecties (YAML)

Het bestand `correcties.yml` bevat gemeente-specifieke datacorrecties die automatisch door de pipeline worden toegepast:

**Projectcode-correcties** — worden na harmonisatie (Transform2) toegepast op het `projectcd`-veld:

```yaml
projectcode_correcties:
  - patroon: "SCHE"        # regex-match op projectcd
    projectcode: "DC039"   # vervangende waarde
```

**Brondata-correcties** — worden vóór harmonisatie (Transform1) toegepast op raw velden in staging:

```yaml
brondata_correcties:
  - collectie: COLL_STAGING_MONSTER  # config-constante van de collectie
    zoek_veld: PROJECT               # veld waarop gematcht wordt
    patroon: "SCHE"                  # regex-patroon
    waarde: "DC039"                  # vervangende waarde
```

**Overige opties**: `artefact_niet_mergen` (projecten uitsluiten van merge) en `rapportcode_prefixen` (bestandsclassificatie).

Het correctiebestand is optioneel en foutbestendig: bij ongeldige YAML of ontbrekende velden worden de betreffende regels overgeslagen en gelogd
```

## Foutafhandeling

De transformatielaag registreert alle transformaties en mogelijke fouten:

!!! error "Kritieke Fouten"
    - Onleesbare data (geen parsering mogelijk)
    - Conflicterende waarden in deduplicatie
    - Onherkenbare coördinatensystemen

!!! warning "Waarschuwingen"
    - Onbekende thesaurustermen
    - Potentiële spellingsfouten
    - Coördinaten buiten verwachte grenzen
    - Datums in toekomst of te ver verleden

!!! note "Informatie"
    - Succesvol getransformeerde records
    - Gemaakte deduplicaties
    - Geïnterpreteerde waarden

## Best Practices

- Controleer transformatieregels vóór volledige batch-verwerking
- Test met kleine datasets eerst
- Behoud logboeken van alle transformaties
- Valideer het resultado na transformatie

