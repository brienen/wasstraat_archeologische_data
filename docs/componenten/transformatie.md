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

### 7. Ontbrekende entiteiten aanvullen

Veel opgravingsdatabases hebben geen eigen tabel voor putten of vlakken; die staan alleen als nummer bij sporen, vondsten, tekeningen en foto's. De stap Move and Merge maakt daarom voor elke combinatie die in de data voorkomt een record aan als dat nog niet bestaat:

| Entiteit | Gegenereerd uit | Sleutel |
|----------|-----------------|---------|
| Put | `projectcd` + `putnr` | `P<project>P<put>` |
| Vlak | `projectcd` + `putnr` + `vlaknr` | `P<project>P<put>V<vlak>` |
| Spoor | `projectcd` + `putnr` + `spoornr` | `P<project>P<put>S<spoor>` |
| Vondst | `projectcd` + `putnr` + `vondstnr` | `P<project>[P<put>]V<vondst>` |
| Doos | `projectcd` + `doosnr` van artefacten | `P<project>D<doos>` |

Een gegenereerd record krijgt dezelfde key als een record uit de brondata, zodat alleen echt ontbrekende records worden toegevoegd. Daarom bevat de key van een spoor geen vlak (sporen uit de brondata hebben `vlaknrs`, meervoud) en neemt een gegenereerde vondst de vlag `vondstkey_met_putnr` van de bronrecords over, die bepaalt of het putnummer in de key van een vondst staat.

Nummer `0` telt niet mee. Gegenereerde records herken je aan `brondata.table` = `generated_put`, `generated_vlak`, enzovoort. Een PUT- of VLAK-tabel in de brondata is dus niet verplicht. Is die er wel, dan gebruikt de pipeline die records (met beschrijving en andere attributen) en genereert alleen wat ontbreekt.

De pipelines staan in `airflow_app/dags/wasstraat/meta.py` onder `MOVEANDMERGE_GENERATE_MISSING_PIPELINES`.

### 8. Incrementele variant

De incrementele cyclus (`Extract_Transform_Load_Incremental`) gebruikt dezelfde transformatiefuncties en taakgroepen, met `incrementeel=True`. Transform 1 harmoniseert dan alleen de staging-documenten uit nieuwe en gewijzigde bronbestanden en geeft ze het veld `delta_run`; Transform 2 en 3 werken alleen op die documenten (projectbrede stappen op de geraakte projecten). Transform 5 leegt `Single_Store_Clean` niet, maar verplaatst de delta-documenten, voegt alleen de geraakte sleutels opnieuw samen en genereert ontbrekende entiteiten opnieuw voor de geraakte projecten. Transform 4 kent stabiele sleutels toe: bestaande entiteiten houden hun `ID` (de `primary_key` in PostgreSQL), alleen nieuwe entiteiten krijgen een nieuw nummer; artefacten worden daarbij teruggevonden op `key_subnr|artefactsoort`. Sinds issue 71 doet Transform 4 dat in elke DAG, ook in de volledige cyclus (daar via de `primary_key` uit de bron, map en bestandsnaam of een unieke `key`, omdat het `_id` na een nieuwe extractie altijd nieuw is). Zonder die parameter werken de functies precies zoals in de volledige cyclus. Zie [Incrementeel laden](incrementeel-laden.md).

### 9. Sleutels

Elke entiteit krijgt in Transform 3 (`setReferenceKeys`, pipelines `SET_KEYS_PIPELINES` in `airflow_app/dags/wasstraat/meta.py`) een samengestelde sleutel `key` uit zijn identificerende velden, bijvoorbeeld `PDB034P10V460` voor vondst 460 in put 10 van project DB034, en sleutels naar de entiteiten waarnaar hij verwijst (`key_vondst`, `key_put`, `key_monster`, ...). Transform 4 koppelt op die sleutels (`setReferences`) en kent de integer-sleutels toe (`setPrimaryKeys`, in PostgreSQL `primary_key`).

| Soort | key | Bijzonderheden |
|-------|-----|----------------|
| Project | `P<projectcd>` | |
| Put, Vlak, Spoor, Vulling | `P<project>P<put>[V<vlak>][S<spoor>]...` | Een spoor kan in meer tabellen of databases van een project staan; de key komt dan vaker voor |
| Vondst | `P<project>[P<put>]V<vondst>` | Het putnummer staat erin als het vondstnummer in het project in meer putten voorkomt (vlag `vondstkey_met_putnr`) |
| Artefact | `P<project>[P<put>]V<vondst>A<artefactnr>[S<splitid>]`, samengevoegd op `key_subnr` (zelfde opbouw met het subnummer) en artefactsoort | `key` is meestal leeg (geen artefactnr); in PostgreSQL staat `key_subnr|artefactsoort` in de kolom `key`. Ongeveer twee derde van de Delftse artefacten heeft geen subnummer (determinatietabellen) en dus geen natuurlijke key |
| Monster | `M<monstercd>` | |
| Monster_Botanie, Monster_Schelp | `M<monstercd>ID<Id>` | `Id` is het autonummer van de bronrij; de harmonisatie neemt het niet over, daarom valt Transform 3 terug op `brondata.Id` (Delft) of `brondata.ID` (synthetische data) (issue 81; daarvoor was deze key altijd leeg) |
| Standplaats | `S<stelling>V<vak>L<letter>` | Eén document per regel van de magazijnlijst, dus dozen op dezelfde plek hebben dezelfde key |
| Doos | `P<project>D<doos>` | |
| Plaatsing, Vindplaats | geen | |
| Foto, Tekening, Rapport (Bestand) | o.a. `P<project>...S<fotonr>`, `R<rapportnr>` | In PostgreSQL herkend op map en bestandsnaam |

**Hulpsleutel uit de bronrij (issue 81).** Rijen zonder key of met een key die vaker voorkomt, worden teruggevonden op de identiteit van hun bronrij: `<pad>:<tabel>:<autonummer>` (bijv. `projecten/DB034_Koningsveld IV/C Database/opgravingDB34.mdb:AW1DeterminatiesJohan:4`), of een hash van de inhoud als de Access-tabel geen autonummer heeft, en voor een samengevoegd document de lijst van al zijn bronrijen (`delta_transform.getBronsleutel`). Die hulpsleutel wordt afgeleid uit `brondata`, in MongoDB en uit de kolom `brondata` in PostgreSQL. Rijen zonder natuurlijke key krijgen in PostgreSQL een leesbare key met de hulpsleutel (`P<project>[P<put>][V<vondst>]|<artefactsoort>|bron:<hulpsleutel>` voor artefacten, `bron:<hulpsleutel>` voor andere soorten); het veld `key` in MongoDB blijft de natuurlijke key, omdat de verwijzingen daarop koppelen. De natuurlijke key heeft bij het toekennen van de `primary_key` voorrang; de hulpsleutel beslist alleen waar die key ontbreekt of niet uniek is. Zie [Incrementeel laden: hulpsleutel uit de bronrij](incrementeel-laden.md#hulpsleutel-uit-de-bronrij-issue-81) voor de analyse, de dekking en de eerste cyclus op een bestaande installatie.

### 10. Verplaatsen en samenvoegen van artefacten (issue 83)

Transform 5 (`Transform5_Move_And_Merge_Group`) zet de documenten uit `Single_Store` over naar `Single_Store_Clean`: eerst verplaatsen de taken `Move_<soort>` documenten één op één (`merge_functions.moveSoort`), daarna voegen de taken `Merge_<soort>` documenten met dezelfde sleutel samen (`merge_functions.mergeSoort`). Voor artefacten doen beide stappen elk een deel:

| Artefact in `Single_Store` | Stap | Resultaat in `Single_Store_Clean` |
|----------------------------|------|-----------------------------------|
| Met `subnr`, zonder kolom `ARTEFACT` in de bronrij, niet uit een tabel in `ARTEFACT_NOT_MERGE_TABLES` (`ROMEINS AARDEWERK`) en niet uit een project in `artefact_niet_mergen` (`correcties.yml`) | Samenvoegen (`getArtefactMergeVoorwaarde`) | Eén document per `key_subnr` en artefactsoort |
| Alle andere artefacten | Verplaatsen (`getInverseMatchArtefact`) | Eén document per bronrij |
| Uit de tabel `ARTEFACT` (`ARTEFACT_NOT_MOVE_TABLES`) die niet worden samengevoegd | Geen | Geen document (zie hieronder) |

De verplaatsing is precies het complement (`$nor`) van de voorwaarde voor het samenvoegen: elke bronrij komt in één document terecht. Een samengevoegd document heeft de velden van de bronrijen samen (`$mergeObjects`: bij een veld dat in meer bronrijen voorkomt telt de laatste bronrij, ook voor het `_id`), alle bronrijen in `brondata` en hun aantal in `brondata_count`. De artefactsoort wordt vóór het groeperen gelijkgetrokken (leeg, `-` en `onbekend` worden `Onbekend`, spaties aan begin en eind vallen weg; `AGGR_PHASE_ARTEFACTSOORT`), zodat varianten van dezelfde soort bij één `key_subnr` niet als aparte documenten met dezelfde key eindigen.

Zo'n groep kan bestaan uit dezelfde scherf in meer tabellen (Delft DC026: `AARDEWERK 1` en `AARDEWERK 3` met dezelfde inhoud), in kopieën van dezelfde database (DC097: `GLAS`, `LEER`, `HOUT`, `STEEN` en `AARDEWERK 1` in `HHD2.mdb`, `dc79a1.mdb` en `opgravingDC97.mdb`), in een aparte determinatiedatabase (DB034: `AARDEWERK 1`, `CATALOGUS AW1`, `Huismerken op aardewerk` en `Aardewerk` uit `aardewerk_ivonne_060725.mdb`), of uit meer rijen van één tabel over hetzelfde voorwerp (twee huismerken op één pot). In dat laatste geval (22 groepen met 83 bronrijen in Delft) toont het samengevoegde document de waarden van de laatste rij; de andere rijen staan in `brondata`.

**Wat issue 83 veranderde.** Tot issue 83 had de verplaatsing een eigen lijst met voorwaarden, die ook alle artefacten uit tabellen waarvan de naam niet met `ARTEFACT` begint (de regel stond er sinds maart 2026) en alle artefacten zonder artefactsoort verplaatste. Die werden ook samengevoegd. Het samengevoegde document krijgt het `_id` van de laatste bronrij en verving daardoor één verplaatst exemplaar; bij een groep van *n* bronrijen bleven de andere *n* − 1 naast het samengevoegde document staan, met dezelfde key (`key_subnr|artefactsoort`). In de Delftse productiedata (22 oktober 2026) ging het om 2.433 groepen met 5.746 bronrijen in DC026 (1.509 groepen), DC097 (646), DB034 (277) en DC093 (1): 3.313 artefacten te veel, die in de webapplicatie en de zoekindex dubbel stonden. In de Delftse testdata (`data/test`, een oudere kopie van `opgravingDB34.mdb`) gaat het om 261 groepen van een rij uit `AARDEWERK 1` en een uit `CATALOGUS AW1`: 261 artefacten minder (Aardewerk: 4.917 → 4.656, zie de referentie-uitkomst `tests/integration/fixtures/delft_golden_snapshot.json`).

**Eerste volledige cyclus na de wijziging.** De samengevoegde documenten blijven precies zoals ze waren (dezelfde bronrijen, dus dezelfde hulpsleutel), alleen de losse exemplaren vervallen. Transform 4 vindt de samengevoegde artefacten terug op hun hulpsleutel én key (stap 5 van `bepaalStabieleIds`, zie [Hulpsleutel uit de bronrij](incrementeel-laden.md#hulpsleutel-uit-de-bronrij-issue-81)); daarna is hun key uniek. Een simulatie op de productie-installatie (alleen lezen: de nieuwe pipelines op `Single_Store`, met nieuwe `_id`'s zoals in de volledige cyclus, tegen `Def_Artefact`) geeft 29.214 artefacten in plaats van 32.527: geen enkel artefact krijgt een nieuw nummer, 3.313 nummers vervallen. Gebruikersdata op een vervallen exemplaar (bruikleen, conservering) wordt losgekoppeld met een markering en meteen weer gekoppeld aan het samengevoegde artefact, omdat de key in de markering nu uniek is (`koppelVerwijzingenTerug`); op productie stond er op 29 oktober 2026 geen gebruikersdata op artefacten. De incrementele cyclus ruimt de losse exemplaren alleen op voor bestanden in de delta: draai na deze wijziging eerst de volledige cyclus.

**Dubbele keys die blijven.** Na de wijziging komen artefactkeys alleen nog dubbel voor bij artefacten die bewust apart blijven (project DC112 uit `artefact_niet_mergen`, 53 artefacten; `ROMEINS AARDEWERK` van DC022, 20), bij een natuurlijke key (`artefactnr` en `splitid`) die in de brondata zelf dubbel is (DC024 `ARTF_ODL`, 29) en bij de kopieën van de databases van DC024 in de werkmap van Joris (6.663 artefacten die alleen uit die kopieën komen; issue 84). De integratietests eisen dat geen artefact met een key uit een merge-groep ook als los document voorkomt (Delft, `test_24a`) en dat in de synthetische data elke key in `Single_Store_Clean` en `Def_Artefact` uniek is (`test_08d`, `test_22d`); `tests/unit/test_merge_artefacten.py` toetst de voorwaarden en bootst move en merge na.

**Tabel `ARTEFACT`.** Artefacten uit de tabel `ARTEFACT` worden nooit verplaatst (ontwerp van 2022); zonder subnummer, met een kolom `ARTEFACT` of in een project uit `artefact_niet_mergen` worden ze ook niet samengevoegd en komen ze niet in `Single_Store_Clean`. In Delft zijn dat 244 rijen (de RAAP-tabel `ARTEFACT` van DC112 (103), DC024 (28, en 4 × 28 in de kopieën in de werkmap) en DC008 (1)). Issue 83 verandert dat niet; of deze rijen alsnog als artefact moeten worden geladen, is een vraag voor de opdrachtgever.

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

**Overige opties**: `artefact_niet_mergen` (projecten uitsluiten van merge, zie [Verplaatsen en samenvoegen van artefacten](#10-verplaatsen-en-samenvoegen-van-artefacten-issue-83)) en `rapportcode_prefixen` (bestandsclassificatie).

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

