# Aan de slag

Deze handleiding neemt je stap voor stap mee om de Wasstraat Archeologische Data voor het eerst te installeren, te configureren en te draaien. Na het doorlopen heb je een werkende omgeving met verwerkte archeologische data die je kunt bekijken in de webapplicatie.

## 1. Downloaden en installeren

### Vereisten

Zorg dat de volgende software op je systeem is geïnstalleerd:

- **[Docker Desktop](https://www.docker.com/products/docker-desktop/)** — Minimaal versie 20.10
- **Docker Compose** — Wordt meegeleverd met Docker Desktop
- **Git** — Voor het clonen van de repository
- **Minimaal 12 GB RAM** beschikbaar voor Docker (stel dit in via Docker Desktop → Settings → Resources)
- **Minimaal 2 Cores** beschikbaar voor Docker (stel dit in via Docker Desktop → Settings → Resources)
- **Minimaal 256 GB** schijfruimte beschikbaar voor Docker (stel dit in via Docker Desktop → Settings → Resources)

!!! tip "Docker Desktop resources"
    De Wasstraat draait 8 containers tegelijk. Stel in Docker Desktop het beschikbare geheugen in op minimaal 12 GB met 2 cores. Bij productiegebruik zijn meer resources aangeraden; voor Delft is gewerkt met 32 GB RAM, 10 Cores en 521 GB Schijfruimte. 

    Je hebt deze resources overigens maar heel tijdelijk nodig: denk aan een run om alle data te "wassen" van 20 min tot uiterlijk 24 uur.  

### Repository clonen

```bash
git clone https://github.com/brienen/wasstraat_archeologische_data.git
cd wasstraat_archeologische_data
```

### Configuratie

Bij de eerste start genereert het systeem automatisch alle configuratiebestanden met unieke wachtwoorden. Je hoeft zelf niets in te stellen — het werkt direct out-of-the-box.

De configuratiebestanden worden aangemaakt in `config/` op basis van de meegeleverde `.env.example` templates. Elk bestand krijgt automatisch een veilig, willekeurig wachtwoord. De gegenereerde wachtwoorden worden in de terminal getoond zodat je ze kunt bewaren.

!!! tip "Handmatig configureren"
    Wil je de configuratie handmatig aanpassen? Kopieer de `.env.example` bestanden:
    ```bash
    for f in config/*.env.example; do cp "$f" "${f%.example}"; done
    ```
    Pas vervolgens de wachtwoorden in `config/*.env` aan naar wens.

## 2. Wasstraat starten

Start de wasstraat:

```bash
make app
```

Bij de allereerste start duurt het enkele minuten omdat Docker alle images moet downloaden en bouwen. Je ziet de voortgang in de terminal.

Controleer of alle containers draaien:

```bash
make ps
```

Je zou deze 8 containers moeten zien:

| Container | Poort | Status verwacht |
|-----------|-------|-----------------|
| `wasstraat_airflow` | :8080 | Up |
| `wasstraat_flask` | :5051 | Up |
| `wasstraat_postgres` | :5432 | Up |
| `wasstraat_mongo` | :27017 | Up |
| `wasstraat_elasticsearch` | :9200 | Up |
| `wasstraat_redis` | :6379 | Up |
| `wasstraat_apache` | :5052 | Up |
| `wasstraat_jupyter` | :8888 | Up |

!!! warning "Containers starten niet?"
    Als een container niet wil starten, bekijk de logs:
    ```bash
    make logs
    # Of voor één specifieke container:
    docker logs wasstraat_airflow
    ```
    De meest voorkomende oorzaak is onvoldoende geheugen in Docker Desktop.

## 3. Webpagina's bekijken

Na het starten zijn er drie webapplicaties beschikbaar:

### Airflow — Data verwerken (ETL)

```
http://localhost:8080
```

Hier beheer je de dataverwerkingspipeline. Je ziet een overzicht van alle beschikbare DAGs (Directed Acyclic Graphs — de verwerkingsprocessen). Inloggen doe je met de standaard Airflow-credentials die bij de installatie zijn gegenereerd (standaard: `admin` / het gegenereerde wachtwoord, te vinden in `config/airflow.env` onder `SECURITY__ADMIN_PASSWORD`).

### Flask App — Data inzien

```
http://localhost:5051
```

De webapplicatie voor het bekijken van de verwerkte data. Na een succesvolle verwerking zie je hier een interactieve kaart van Delft met alle opgravingslocaties, en kun je doorklikken naar projecten, vondsten, artefacten, foto's en meer.

!!! tip "Nog geen data?"
    Bij een verse installatie is de Flask App nog leeg. Dat klopt — je moet eerst data verwerken via Airflow (stap 5–7 van deze handleiding).

### Jupyter Lab — Data analyseren

```
http://localhost:8888
```

Jupyter Lab voor eigen data-analyse. Er zijn 68+ bestaande notebooks beschikbaar met voorbeelden van data-exploratie en transformatie-validatie. Het wachtwoord staat in `config/jupyter.env`.


## 4. Bestanden klaarzetten

### Voorbeelddata: direct aan de slag

De repository bevat **synthetische voorbeelddata** in `data/synthetic/data/` — twee fictieve opgravingsprojecten waarmee je de volledige pipeline kunt testen zonder eigen brondata. Deze data wordt automatisch gebruikt bij `make integration` en dient als werkend voorbeeld van de verwachte bestandsstructuur.

!!! tip "Snel testen zonder eigen data"
    De synthetische data is klaar voor gebruik. Start de Wasstraat met `make app` en trigger de verwerkingspipeline in Airflow om te zien hoe het platform werkt. Zie `data/synthetic/README.md` voor de inhoud van de voorbeeldprojecten.

### Eigen data klaarzetten

Gemeenten kunnen hun eigen opgravingsdata klaarzetten conform dezelfde directorystructuur als de Delftse pijplijn. De echte Delftse data is niet opgenomen in de repository, maar de synthetische voorbeelddata in `data/synthetic/data/` toont exact welke bestanden en structuren het platform verwacht.

De Wasstraat leest brondata uit de directory `data/delft/data/`. Elke subdirectory heeft een specifiek doel:

```
data/delft/data/
├── projecten/           ← Projectdatabases (.mdb/.accdb) + foto's
├── projectenlijst/      ← Projectenlijst administratie (.mdb)
├── magazijnlijst/       ← Depotregistratie (.mdb)
├── fotolijst/           ← Foto-metadata (.mdb)
├── monsterdatabase/     ← Monsterregistratie (.mdb/.accdb)
├── rapporten/           ← Rapportbestanden (.mdb, .pdf)
└── referentietabellen/  ← ABR-codes en standaardtabellen (.xlsx/.mdb)
```

### Wat moet waar?

| Directory | Wat erin hoort | Bestandstype | Verplicht? |
|-----------|---------------|-------------|-----------|
| `projecten/` | Per opgraving een subdirectory met de projectdatabase en foto's | `.mdb` / `.accdb` + afbeeldingen | Ja — dit is de hoofdbron |
| `projectenlijst/` | Centrale administratiedatabase met projectoverzicht (tabel `OPGRAVINGEN`) | `.mdb` | Ja — bevat projectoverzicht |
| `magazijnlijst/` | Depot- en magazijnadministratie (tabel `magazijnlijst`) | `.mdb` | Aanbevolen |
| `fotolijst/` | Digitale fotocatalogus met metadata (tabel `Fotos`) | `.mdb` | Aanbevolen (voor foto-koppeling) |
| `monsterdatabase/` | Monsterdata met botanische en zoölogische determinaties | `.mdb` / `.accdb` | Optioneel |
| `rapporten/` | Rapportbestanden en rapportendatabases | `.mdb` / `.pdf` | Optioneel |
| `referentietabellen/` | ABR-classificatie (`abr_versie_*.xlsx`) en bestandslijsten | `.xlsx` / `.mdb` | Ja — nodig voor harmonisatie |

### Structuur per directory

#### projecten/ — Opgravingsdatabases

Per opgraving een subdirectory. De directorynaam bepaalt de projectcode (het eerste alfanumerieke deel). De Wasstraat doorzoekt recursief op `.mdb` en `.accdb` bestanden.

```
projecten/
├── DB008_Leeuwenstein/
│   ├── C Database/
│   │   └── DB008.mdb              ← Projectdatabase
│   └── L Fotos/
│       ├── G (Opgravingsfoto's)/  ← Overzichtsfoto's
│       └── H (Objectfoto's)/      ← Vondstfoto's per materiaal
│           ├── Aardewerk/
│           ├── Glas/
│           └── Metaal/
└── DC001_Oude_Delft_96/
    └── C Database/
        └── DC001.mdb
```

Elke projectdatabase bevat tabellen zoals `VONDSTENLIJST`, `SPOREN`, `VULLINGEN`, `AARDEWERK 1`, `GLAS`, `METAAL`, `BEEN`, `TEKENINGEN`, `DIAOPGRAVING` etc. De exacte tabellen en kolomnamen worden geconfigureerd via `Wasstraat_Config_HarmonizeV3.xlsx`.

#### projectenlijst/ — Projectoverzicht

Eén `.mdb`-bestand met een tabel `OPGRAVINGEN` die alle projecten beschrijft:

| Kolom | Beschrijving |
|-------|-------------|
| `CODE` | Projectcode (bijv. DB008, DC001) |
| `TOPONIEM` | Locatienaam |
| `OPGRAVING` | Beschrijving van de opgraving |
| `XCOORD`, `YCOORD` | Rijksdriehoek-coördinaten |
| `JAAR` | Opgravingsjaar |

#### magazijnlijst/ — Depotadministratie

Eén `.mdb`-bestand met een tabel `magazijnlijst` met kolommen: `CODE`, `PROJECT`, `STELLING`, `VAKNO`, `VOLGLETTER`, `INHOUD`, `DOOSNO`.

#### fotolijst/ — Fotocatalogus

Eén `.mdb`-bestand met een tabel `Fotos` die digitale foto's koppelt aan projecten, putten en vondsten:

| Kolom | Beschrijving |
|-------|-------------|
| `FOTONR` | Uniek fotonummer |
| `PROJECTCD` | Projectcode |
| `PUTNO`, `VLAKNR`, `SPOORNR`, `VONDSTNR` | Verwijzingen naar archeologische context |
| `BESTANDSNAAM` | Bestandsnaam van de foto |
| `FOTOSOORT` | Type foto (Opgravingsfoto, Voorwerpfoto) |

#### monsterdatabase/ — Monsters en determinaties

Eén `.mdb`-bestand met meerdere tabellen:

| Tabel | Inhoud |
|-------|--------|
| `Monster_gegevens` | Grondmonsters met locatie, grondsoort, zeefresultaten |
| `Monster_waardering` | Waardering per monstercode (botanisch, zoölogisch materiaal) |
| `Monster_botanie_determinatie` | Botanische determinaties (plantsoorten, delen, conservering) |
| `Monster_schelp_determinatie` | Schelpdeterminaties (soorten, delen) |
| `R_PLANT`, `R_SCHELP`, `R_DEEL`, `R_STAAT` | Referentietabellen |

#### referentietabellen/ — Standaardtabellen

| Bestand | Inhoud |
|---------|--------|
| `abr_versie_*.xlsx` | ABR-thesaurus: archeologische perioden, monumenttypen, materialen |
| `Alle Bestanden Archeologisch Depot.xlsx` | Inventarisatie van bestanden in het depot |
| Overige `.mdb`-bestanden | Specifieke referentietabellen (bakselcodes, pijpmakersmerken, etc.) |

### Foto's en media

Foto's worden op twee manieren gevonden:

1. **In de projectdirectory** (`projecten/<project>/L Fotos/`): de Wasstraat zoekt in paden die `velddocument`, `fotos` of `tekening` bevatten
2. **Via de fotocatalogus** (`fotolijst/`): koppelt bestandsnamen aan projecten en vondsten

Ondersteunde bestandstypen: `.jpg`, `.jpeg`, `.png`, `.gif`, `.tif`, `.psd`, `.pdf`, `.jp2`, `.doc`, `.docx`.

!!! tip "Minimale proefset"
    Voor een eerste test volstaat het om één `.mdb` projectdatabase in `projecten/` te plaatsen, samen met de referentietabellen en een projectenlijst. De extractie verwerkt dan alleen dat ene project.

## 5. Wasstraat_Config_HarmonizeV3 configureren

Het bestand `Wasstraat_Config_HarmonizeV3.xlsx` is het hart van de dataverwerkingsconfiguratie. Het vertelt de Wasstraat hoe brondata uit diverse Access-databases moet worden omgezet naar een geüniformeerd datamodel.

Het bestand bevindt zich in:

```
data/delft/wasstraat_config/Wasstraat_Config_HarmonizeV3.xlsx
```

De locatie wordt geconfigureerd via de environment-variabele `AIRFLOW_WASSTRAAT_CONFIG` in `config/airflow.env`.

### Structuur van het configuratiebestand

Het Excel-bestand bevat twee soorten tabbladen:

#### Tabblad "Objecten" — Het hoofdoverzicht

Dit tabblad definieert welke entiteiten (objecten) de Wasstraat herkent en hoe tabellen in de brondatabases daaraan worden gekoppeld:

| Kolom | Uitleg | Voorbeeld |
|-------|--------|-----------|
| **Object** | Naam van het entiteitstype | `Vondst`, `Artefact`, `Aardewerk` |
| **Tabellen** | Regex-patronen die brontabellen matchen | `["^VONDSTENLIJST", "^VONDST$"]` |
| **Overerven** | Ouder-entiteit waarvan attributen worden overgenomen | `Artefact` (voor `Aardewerk`, `Glas`, etc.) |
| **Samenvoegen** | Entiteit waarmee samengevoegd wordt | — |
| **ABR-materiaal** | URI naar ABR-materiaalclassificatie | `https://data.cultureelerfgoed.nl/...` |
| **ABR-submateriaal** | URI naar ABR-submateriaalclassificatie | `https://data.cultureelerfgoed.nl/...` |

De kolom **Tabellen** bevat regex-patronen als JSON-lijst. Wanneer een tabel in een brondatabase overeenkomt met een van deze patronen, wordt deze herkend als dat objecttype. Bijvoorbeeld: een tabel genaamd `VONDSTENLIJST_2019` matcht het patroon `^VONDSTENLIJST` en wordt dus behandeld als `Vondst`.

De speciale rij **Ignore** bevat patronen voor tabellen die moeten worden overgeslagen, zoals `.*backup.*`, `.*kopie.*` en `.*tijdelijk.*`.

#### Overerving van artefacten

Artefacttypen zoals `Aardewerk`, `Glas`, `Metaal`, `Hout` enzovoort hebben in de kolom **Overerven** de waarde `Artefact`. Dit betekent dat ze eerst de standaard artefact-attributen overnemen en daar hun eigen specifieke attributen aan toevoegen. Zo heeft Aardewerk naast de algemene artefactvelden ook velden voor baksel, glazuur en vormcode.

#### Attributen-tabbladen — Eén per objecttype

Voor elk objecttype in het Objecten-tabblad bestaat een apart tabblad met dezelfde naam (bijv. "Vondst", "Spoor", "Aardewerk"). Elk attributen-tabblad heeft twee kolommen:

| Kolom | Uitleg | Voorbeeld |
|-------|--------|-----------|
| **Attribute** | De geharmoniseerde veldnaam in het doelmodel | `putnr`, `spoornr`, `datum` |
| **Kolommen** | Bronkolommen als JSON-lijst met fallback-volgorde | `["PUT", "PUTNO"]` |

De **Kolommen**-lijst werkt als een prioriteitsvolgorde: de Wasstraat probeert eerst de eerste kolomnaam, dan de tweede, enzovoort. Dit is essentieel omdat verschillende brondatabases andere kolomnamen gebruiken voor hetzelfde gegeven. Bijvoorbeeld: het putnummer kan in de ene database `PUT` heten en in een andere `PUTNO`.

Voorbeeld uit het tabblad "Spoor":

| Attribute | Kolommen |
|-----------|----------|
| `aard` | `["AARD", "INTERPRET", "INTERPRETATIE", "SPOORAARD"]` |
| `putnr` | `["PUT", "PUTNO"]` |
| `spoornr` | `["SPOOR", "SPOORNO"]` |
| `beschrijving` | `["BESCHRIJVING"]` |

### Aanpassen voor je eigen situatie

Om de Wasstraat te gebruiken voor je eigen archeologische data, pas je het configuratiebestand aan in drie stappen:

#### Stap 1: Tabellen herkennen

Open je eigen `.mdb`-bestanden en noteer welke tabellen erin zitten. Pas vervolgens de regex-patronen in het tabblad "Objecten" aan zodat jouw tabelnamen worden herkend. Als jouw vondstentabel bijvoorbeeld `Vondsten_Registratie` heet, voeg dan `"Vondsten_Registratie"` toe aan de Tabellen-lijst van het object "Vondst".

!!! tip "Tabellen bekijken"
    Je kunt de tabellen in een `.mdb`-bestand bekijken met:
    ```bash
    # Vanuit de Airflow-container:
    docker exec wasstraat_airflow mdb-tables /input/projecten/<jouw_bestand>.mdb
    ```

#### Stap 2: Kolomnamen toevoegen

Bekijk de kolomnamen in je tabellen en voeg ontbrekende namen toe aan de Kolommen-lijsten in het attributen-tabblad. Als jouw database het veld `PUTNUMMER` gebruikt in plaats van `PUT` of `PUTNO`, voeg je dit toe:

Van: `["PUT", "PUTNO"]`
Naar: `["PUT", "PUTNO", "PUTNUMMER"]`

!!! tip "Kolomnamen bekijken"
    ```bash
    docker exec wasstraat_airflow mdb-export -H /input/projecten/<bestand>.mdb <tabelnaam> | head -1
    ```

#### Stap 3: Nieuwe objecttypen toevoegen (optioneel)

Als je een entiteitstype hebt dat nog niet bestaat (bijvoorbeeld een specifiek artefacttype), voeg dan een nieuwe rij toe aan het "Objecten"-tabblad en maak een bijbehorend attributen-tabblad aan. Als het een artefacttype is, zet dan `Artefact` in de kolom "Overerven" zodat de standaard artefact-attributen worden overgenomen.

### Huidige objecttypen

Het configuratiebestand bevat de volgende objecttypen:

**Basisentiteiten**: Put, Vlak, Spoor, Vulling, Vondst, Monster, Tekening, Foto, Rapport

**Artefacttypen** (overerven van Artefact): Aardewerk, Bouwaardewerk, Dierlijk Bot, Glas, Hout, Kleipijp, Leer, Menselijk Bot, Metaal, Munt, Schelp, Steen, Textiel

**Referentiedata**: ABR, DT_Soort_Plant, DT_Soort_Schelp, DT_Soort_Deel, DT_Soort_Staat

**Speciaal**: Monster_Botanie, Monster_Schelp, Fotobeschrijving, Fotokoppel


## 5b. Correcties configureren (optioneel)

Naast de harmonisatie-Excel kan je een `correcties.yml` aanmaken in dezelfde `wasstraat_config/`-directory. Dit bestand bevat gemeente-specifieke datacorrecties die de pipeline automatisch toepast.

```
data/<omgeving>/wasstraat_config/correcties.yml
```

### Projectcode-correcties

Als na verwerking bepaalde projectcodes fout zijn (bijv. afkortingen of oude codes), kun je ze automatisch laten corrigeren:

```yaml
projectcode_correcties:
  - patroon: "SCHE"
    projectcode: "DC039"
  - patroon: "PPG"
    projectcode: "DC067"
```

Elke regel matcht het regex-patroon op het `projectcd`-veld in alle verwerkte documenten en vervangt het door de opgegeven projectcode. Dit gebeurt na harmonisatie (Transform2).

### Brondata-correcties

Als bronbestanden afwijkende waarden bevatten die niet matchen met de projectenlijst, kun je die vóór harmonisatie laten corrigeren:

```yaml
brondata_correcties:
  - collectie: COLL_STAGING_MONSTER
    zoek_veld: PROJECT
    patroon: "SCHE"
    waarde: "DC039"
```

### Overige opties

```yaml
# Projecten waarvan artefacten niet gemerged worden
artefact_niet_mergen:
  projectcodes: ["DC112"]

# Rapportcode-prefixen voor bestandsclassificatie
rapportcode_prefixen:
  - prefix: "DAR"
    type: "archeologische_rapportage"
  - prefix: "DAN"
    type: "archeologische_notitie"
```

!!! tip "Leeg bestand is prima"
    Als je geen correcties nodig hebt, laat het bestand leeg of maak het niet aan. De pipeline draait gewoon door zonder correcties.

!!! info "Foutbestendig"
    Als het YAML-bestand fouten bevat (ongeldige syntax, ontbrekende velden), slaat de pipeline de ongeldige regels over en gaat door. Fouten worden gelogd in Airflow.


## 6. Voor de eerste keer draaien

### Airflow UI openen

Ga naar [http://localhost:8080](http://localhost:8080) en log in. Je ziet een overzicht van alle beschikbare DAGs:

| DAG | Beschrijving | Wanneer gebruiken |
|-----|-------------|-------------------|
| `Extract_Transform_Load_Full_Cycle` | Volledige pipeline | **Eerste keer — gebruik deze** |
| `Extract_Only` | Alleen data inlezen | Testen of extractie werkt |
| `Transform1_Harmonize_Only` | Alleen harmonisatie | Stapsgewijs debuggen |
| `Load_Only` | Alleen naar PostgreSQL laden | Na handmatige correcties |

### Volledige verwerking starten

1. Klik op de DAG **`Extract_Transform_Load_Full_Cycle`**
2. Zet de DAG aan met de schakelaar links (van "paused" naar "active")
3. Klik rechtsboven op de **play-knop** (▶) → **Trigger DAG**
4. De verwerking start nu automatisch

### Voortgang volgen

Klik op de DAG en open de **Graph**-weergave om de voortgang live te volgen. Elke stap wordt gekleurd:

- **Groen** — Succesvol afgerond
- **Geel** — Bezig met uitvoeren
- **Rood** — Fout opgetreden (klik op de stap voor details in de logs)

De volledige verwerking doorloopt deze stappen:

1. **Drop All Databases** — Schoont de tussentijdse databases op
2. **Extract** — Leest alle bronbestanden in naar MongoDB (as-is, zonder transformatie)
3. **Transform1 Harmonize** — Harmoniseert veldnamen over alle bronnen heen
4. **Transform2 Enhance Attributes** — Normaliseert inhoud (datumformaten, codes, metadata)
5. **Transform3 Set Keys** — Genereert unieke sleutels per entiteit
6. **Transform4 Move and Merge** — Voegt dubbele entiteiten samen
7. **Transform5 Set References** — Zet referenties om naar integer-sleutels
8. **Load to Database & Index** — Kopieert naar PostgreSQL en bouwt de Elasticsearch-index

!!! warning "Verwerkingstijd"
    Voor een kleine proefset (1–5 projectdatabases) duurt de verwerking enkele minuten. Voor de volledige Delft-dataset (1.000+ databases, ~1 TB) kan het enkele uren duren.

### Stapsgewijs draaien (optioneel)

Als je stap voor stap wilt werken, draai de individuele DAGs in deze volgorde:

```
1. Extract_Only
2. Transform1_Harmonize_Only
3. Transform2_Enhance_Attributes_Only
4. Transform3_Keys_Only
5. Transform_Move_Only
6. Transform4_Refs_Only
7. Load_Only
```

Dit is handig voor het debuggen van je configuratie: na stap 3 (Harmonize) kun je in MongoDB controleren of de veldnamen correct zijn geharmoniseerd.


## 7. Resultaten bekijken

### Flask webapplicatie

Open [http://localhost:5051](http://localhost:5051). Na een succesvolle verwerking zie je:

- **Interactieve kaart** — Een kaart van Delft met alle opgravingslocaties. Blauwe markers zijn projecten zonder verwerkte artefacten, rode markers projecten mét verwerkte artefacten. Klik op een marker om naar het project te navigeren.
- **Projecten** — Overzicht van alle geïmporteerde opgravingsprojecten met doorklik naar details
- **Vondsten, Sporen, Putten** — Alle archeologische entiteiten met relaties onderling
- **Artefacten** — Per materiaalcategorie (aardewerk, glas, metaal, etc.) met hun specifieke attributen
- **Bestanden** — Foto's, tekeningen en rapporten, gekoppeld aan de bijbehorende entiteiten
- **Depot** — Dozen, stellingen en bruiklenen
- **Zoeken** — Fulltext-zoekmogelijkheid via Elasticsearch over alle data

### Tussenresultaten in MongoDB

Je kunt de ruwe en getransformeerde data direct in MongoDB bekijken:

```bash
# Verbind met MongoDB
docker exec -it wasstraat_mongo mongosh \
  --username root --password <wachtwoord> --authenticationDatabase admin

# Bekijk staging-data
use Arch_Staging
db.getCollectionNames().forEach(c => print(c + ": " + db[c].countDocuments()))

# Bekijk getransformeerde data
use Arch_Analyse
db.getCollectionNames().forEach(c => print(c + ": " + db[c].countDocuments()))
```

Het MongoDB-wachtwoord vind je in `config/mongo.env` (variabele `MONGO_INITDB_ROOT_PASSWORD`).

### Definitieve data in PostgreSQL

De uiteindelijke, gestructureerde data staat in PostgreSQL:

```bash
docker exec -it wasstraat_postgres psql -U airflow -d flask

-- Overzicht van alle tabellen met aantallen
SELECT schemaname, tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename;

-- Aantal records per hoofdtabel
SELECT 'Def_Project' as tabel, count(*) FROM public."Def_Project"
UNION ALL SELECT 'Def_Vondst', count(*) FROM public."Def_Vondst"
UNION ALL SELECT 'Def_Artefact', count(*) FROM public."Def_Artefact"
UNION ALL SELECT 'Def_Spoor', count(*) FROM public."Def_Spoor";
```

### Elasticsearch zoekindex

Controleer of de zoekindex is opgebouwd:

```bash
curl -s http://localhost:9200/_cat/indices?v
curl -s http://localhost:9200/_count | python3 -m json.tool
```

## Veelvoorkomende problemen

### Containers starten niet op

**Oorzaak**: Onvoldoende geheugen of poortconflicten.

**Oplossing**: Controleer dat poorten 8080, 5051, 5432, 27017, 9200, 6379, 5052 en 8888 niet door andere applicaties worden gebruikt. Verhoog het Docker-geheugen naar minimaal 8 GB.

### Extractie mislukt met mdb-export error

**Oorzaak**: Het `.mdb`-bestand is corrupt of in een niet-ondersteund formaat.

**Oplossing**: De `mdbtools`-suite werkt het best met Access 2000/2003 bestanden (`.mdb`). Modernere `.accdb` bestanden worden beperkt ondersteund.

### Tabellen worden niet herkend bij harmonisatie

**Oorzaak**: De tabelnamen in je database matchen niet met de regex-patronen in het configuratiebestand.

**Oplossing**: Bekijk de tabelnamen in je database en pas de patronen aan in `Wasstraat_Config_HarmonizeV3.xlsx` (zie sectie 5).

### Flask App toont lege lijsten

**Oorzaak**: De data is niet (volledig) verwerkt of de Load-stap is niet uitgevoerd.

**Oplossing**: Controleer in Airflow of alle stappen groen zijn. Controleer in PostgreSQL of de `Def_*`-tabellen records bevatten.

### Zoekfunctie werkt niet

**Oorzaak**: Elasticsearch-index is niet opgebouwd.

**Oplossing**: Controleer of Elasticsearch draait (`curl localhost:9200`) en herstart eventueel de `Load_Only` DAG.
