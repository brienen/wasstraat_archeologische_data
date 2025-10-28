# Probleemstelling: Technische Uitdagingen

## Inleiding

Wanneer archeologische gegevens uit diverse bronnen worden geïntegreerd, ontstaan talrijke technische problemen. Wasstraat is specifiek ontworpen om deze uitdagingen aan te pakken.

## Gegevensintegriteit

### Ontbreken van Primaire Sleutels

Veel gegevensbronnen ontberen unieke, stabile identificatoren:

- Vondstlijsten hebben geen consistent ID-schema
- Foto's worden soms alleen benoemd naar opname-datum
- Rapportdocumenten verwijzen naar locaties zonder standarcoördinaten

!!! warning "Impact"
    Zonder unieke sleutels kunnen dezelfde fysieke objecten meerdere malen in het systeem voorkomen (duplicaten) of foutief gekoppeld worden.

### Referentiële Integriteit

Relationshipss tussen gegevens ontbreken vaak:

- Vondsten zijn niet expliciet gekoppeld aan opgravingen
- Foto's ontbreken verwijzingen naar de context waarin ze genomen zijn
- Contextuele informatie (bodemnummers, sporen) is onvolledig

## Polymorfische Gegevenstypen

### Diverse Structuren

Archeologische gegevens zijn inherent divers:

- Sommige vondstlijsten registreren alleen vondsttype en aantal
- Andere bevatten gedetailleerde metingen, materiaalanalyses, en conserveringsstoffen
- Foto's hebben EXIF-data; scans alleen bestandsnaam en uploadtijdstip
- Rapporten bevatten ongestructureerde tekst naast gestructureerde tabellen

Een traditioneel relationeel schema kan deze variatie moeilijk representeren zonder:

- Enorme hoeveelheden NULL-kolommen
- Ingewikkelde entity-type splitsingen
- Of verlies van informatie

### Monomorphic Storage Requirements

Dit dilemma werd opgelost door **SingleStore** (NoSQL/MongoDB) als intermediaire opslaglaag te introduceren, die flexibel polymorfische documenten aanvaardt.

## Coördinaten en Ruimtelijke Data

### Coördinaatsysteemambiguïteit

Archeologische datasets gebruiken diverse coördinaatsystemen:

- **RD (Rijksdriehoekstelsel)**: Nederlands standaardsysteem, maar verouderd
- **ETRS89 (WGS84)**: Modern GPS-standaard
- **Lokale vakindelingen**: Opgravingsvakken in interne nummering
- **Adresseringen**: "achter café De Zwaan" of historische straatnamen

!!! note "Transformaties Vereist"
    Correcte georeferentie vereist het herkennen en transformeren tussen deze systemen. Fouten bij transformaties kunnen tot meters afwijking leiden.

### Lage Precisie in Historische Data

Oudere gegevens hebben vaak slechts locatieprecisie tot op 10 of 25 meter. Dit moet duidelijk in metagegevens vastgelegd worden.

## Tekencodering en Taal

### Diacrietische Tekens en Lokale Variatie

Archeologische gegevens bevatten veel Nederlandse, Latijnse en andere tekens:

- **Diacrietische tekens**: é, ö, ü in naamgeving (bijv. "Theodoor")
- **Ligatures**: æ, œ in Latijnse beschrijvingen
- **Historische spelling**: Dezelfde naam in verschillende periodes anders gespeld
- **Coderingsconflicten**: Oudere bestanden in ISO-8859-1, nieuwere in UTF-8

Een geunificeerd tekencoderingsschema (UTF-8) met normalisatie is essentieel.

## Synchronisatie Tussen Systemen

### Dual-Write Problem

Wasstraat onderhoudt zowel:

- **NoSQL-laag** (SingleStore/MongoDB): flexibel, voor ingest en transformatie
- **Relationele laag** (PostgreSQL/Oracle): gestructureerd, voor analytics en GIS

!!! danger "Synchronisatieproblemen"
    Wanneer gegevens in beide systemen opleven, moet consistentie gegarandeerd worden. Race conditions, transactie-failures, en unidirectionele sync kunnen anomalieën veroorzaken.

### Change Data Capture

Dit vereist:

- Versieering van gegevens
- Event-logging voor alle mutaties
- Idempotente transformaties
- Reconciliation-mechanismen

## Prestaties en Schaal

### Large Volume Data

De Delft-dataset bevat:

- **40.000 foto's** (elk gigabytes aan BLOB-data)
- **Honderden miljoen metadata-punten**
- **Complexe queries** over miljarden documents

!!! info "Uitdagingen"
    - Index-keuzes die zoekopdrachten accelereren zonder schrijven te vertragen
    - Partitionering van data voor horizontale schaalbaarheid
    - Query-planning voor cross-source joins
    - Cache-coherentie tussen laagen

### Fuzzy Search Performance

Archaeologists zoeken vaak op onnauwkeurige termen:

- "Munten met Maria-afbeelding" (niet gespecificeerde periode)
- "Blauwe potscherven" (kleur is subjectief)
- "Gereedschap, mogelijk Romeins" (onzekerheid in datering)

Fuzzy indexering en full-text search met ranking moet snel werken op miljarden records.

## Data Governance

### Versioning en Reproduceerbaarheid

Voor FAIR-data moet elke analyse:

- **Traceerbaar zijn**: welke versie van welke brongegevens werd gebruikt?
- **Reproduceerbaar**: dezelfde inputs → dezelfde outputs
- **Archiveerbaar**: data vastgelegd voor lange-termijn behoud

Dit vereist:

- Versie-tracking voor alle transformaties
- Reproduceerbare transformatie-pipelines (Apache Spark, Airflow)
- Metadata-dokumentatie volgende CIDOC CRM

### Licenties en Attribuering

Archeologische data komt van diverse uitvoerders met verschillende licenties. De integratie moet:

- Provenance vastleggen
- Licentie-compliance garanderen
- Juiste attribuering faciliteren

## Samenvatting

De technische complexiteit van archeologische data-integratie is aanzienlijk. Wasstraat adresseert deze door:

1. **Polymorfische opslag** via NoSQL
2. **Metagegevens-gestuurde mapping** voor flexibiliteit
3. **Crossviews-technologie** voor multi-source queries
4. **Standaard-aansluiting** (GGM, ABR, CIDOC CRM) voor interoperabiliteit

Zie [Doelstellingen](doelstellingen.md) voor hoe Wasstraat deze problemen systematisch oploste.
