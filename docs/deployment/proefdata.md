# Proefdata Inlezen en Omzetten

Deze pagina beschrijft hoe je een eerste set proefdata kunt inlezen, transformeren en beschikbaar maken in de Wasstraat.

!!! tip "Synthetische voorbeelddata"
    De repository bevat kant-en-klare **synthetische voorbeelddata** in `data/synthetic/data/` — twee fictieve opgravingsprojecten (SY001 en SY002) waarmee je direct de volledige pipeline kunt testen zonder eigen brondata. Gemeenten die hun eigen data willen verwerken, kunnen de voorbeelddata als referentie gebruiken voor de verwachte bestandsstructuur. Zie `data/synthetic/README.md` voor details.

## Vereisten

Zorg dat alle Docker-containers draaien:

```bash
make dev    # Of: make app
```

Controleer of alle services actief zijn:

```bash
make ps
```

Je zou minimaal de volgende containers moeten zien:

- `wasstraat_postgres` (poort 5432)
- `wasstraat_mongo` (poort 27017)
- `wasstraat_airflow` (poort 8080)
- `wasstraat_flask` (poort 5051)
- `wasstraat_elasticsearch` (poort 9200)

## Stap 1: Bronbestanden klaarzetten

### Locatie van invoerdata

De Airflow-container verwacht invoerdata op specifieke paden. Deze worden via Docker-volumes gemount vanuit de `data/delft/data/` directory:

```
data/delft/data/
├── digidepot/          # Projectdatabases (MDB-bestanden)
├── Delf-IT/            # DelfIT administratie
├── magazijnlijst/      # Depot-registratie
├── digifotos/          # Foto-metadata database
├── monsterdatabase/    # Monster-registratie
├── rapporten/          # Rapportendatabases
└── referentietabellen/ # ABR-codes en standaardtabellen
```

### Proefdata plaatsen

Voor een eerste proef is het voldoende om een beperkte set bestanden te plaatsen:

1. **Projectdatabase**: Kopieer een of meerdere `.mdb` bestanden naar `data/delft/data/digidepot/`
2. **Referentietabellen**: Zorg dat de standaard referentietabellen aanwezig zijn in `data/delft/data/referentietabellen/`
3. **Foto's** (optioneel): Plaats testfoto's in de bijbehorende directory

!!! tip "Minimale proefset"
    Voor een snelle test volstaat het om één `.mdb` projectdatabase in de `digidepot/` directory te plaatsen. De extractie zal dan alleen dat project verwerken.

## Stap 2: Airflow UI openen

Open de Airflow web-interface in je browser:

```
http://localhost:8080
```

Je ziet een overzicht van alle beschikbare DAGs. De belangrijkste voor het eerste inlezen:

| DAG | Beschrijving | Gebruik |
|-----|-------------|---------|
| `Extract_Transform_Load_Full_Cycle` | Volledige pipeline (extract + transform + load) | Eerste keer, volledige run |
| `Extract_Only` | Alleen extractie uit bronbestanden | Testen of extractie werkt |
| `Transform1_Harmonize_Only` | Alleen veldnaam-harmonisatie | Stapsgewijs debuggen |
| `Load_Only` | Alleen laden naar PostgreSQL | Na handmatige correcties in MongoDB |

## Stap 3: Volledige ETL-cyclus starten

### Optie A: Via Airflow UI (aanbevolen)

1. Klik op de DAG **`Extract_Transform_Load_Full_Cycle`**
2. Klik rechtsboven op de **play-knop** (▶) → **Trigger DAG**
3. De DAG start nu de volledige verwerking

Je kunt de voortgang volgen in de **Graph**-weergave. Elke stap wordt groen bij succes, rood bij een fout.

### Optie B: Stapsgewijs (voor debugging)

Als je stap voor stap wilt werken, kun je de individuele DAGs in volgorde starten:

```
1. Extract_Only                      → Laadt ruwe data in MongoDB
2. Transform1_Harmonize_Only         → Harmoniseert veldnamen
3. Transform2_Enhance_Attributes_Only → Schoont attributen op
4. Transform3_Keys_Only              → Genereert unieke sleutels
5. Transform_Move_Only               → Verplaatst en merged data
6. Transform4_Refs_Only              → Zet referenties om
7. Load_Only                         → Laadt naar PostgreSQL + Elasticsearch
```

!!! warning "Volgorde is belangrijk"
    De transformatiestappen moeten in de juiste volgorde worden uitgevoerd. Elke stap bouwt voort op het resultaat van de vorige. De volledige ETL-cyclus DAG handelt deze volgorde automatisch af.

## Stap 4: Verwerking volgen

### Airflow task logs

Klik in de Airflow UI op een specifieke task om de logs te bekijken. Hier zie je:

- Aantal verwerkte records per entiteitstype
- Waarschuwingen over onbekende velden of formaten
- Foutmeldingen bij corrupte of ontbrekende data

### MongoDB controleren

Je kunt de tussenresultaten direct in MongoDB bekijken:

```bash
# Verbind met MongoDB in de container
docker exec -it wasstraat_mongo mongosh \
  --username <user> --password <wachtwoord> --authenticationDatabase admin

# Bekijk beschikbare databases
show dbs

# Bekijk staging-collecties
use staging
show collections

# Tel records per collectie
db.getCollectionNames().forEach(c => print(c + ": " + db[c].countDocuments()))

# Bekijk een voorbeeld-record
db.Project.findOne()
```

### PostgreSQL controleren

Na de laadstap kun je de definitieve tabellen controleren:

```bash
# Verbind met PostgreSQL in de container
docker exec -it wasstraat_postgres psql -U airflow -d flask

# Lijst van tabellen
\dt public."Def_*"

# Tel records
SELECT 'Def_Project' as tabel, count(*) FROM public."Def_Project"
UNION ALL
SELECT 'Def_Put', count(*) FROM public."Def_Put"
UNION ALL
SELECT 'Def_Spoor', count(*) FROM public."Def_Spoor"
UNION ALL
SELECT 'Def_Vondst', count(*) FROM public."Def_Vondst";
```

## Stap 5: Data bekijken in de web-applicatie

Na succesvolle verwerking is de data beschikbaar in de Flask-applicatie:

```
http://localhost:5051
```

### Wat je ziet

- **Projectenlijst**: Alle geïmporteerde opgravingsprojecten
- **Entiteiten**: Klik door naar putten, vlakken, sporen, vondsten
- **Foto's**: Gekoppelde afbeeldingen (als deze zijn geïmporteerd)
- **Zoeken**: Gebruik de zoekbalk voor fulltext-doorzoeken

### Elasticsearch-index controleren

De zoekfunctie werkt via Elasticsearch. Controleer of de index is opgebouwd:

```bash
# Bekijk beschikbare indices
curl -s http://localhost:9200/_cat/indices?v

# Tel documenten in de index
curl -s http://localhost:9200/_count | python3 -m json.tool
```

## Veelvoorkomende problemen

### Extractie mislukt

**Probleem**: `Extract_Data_From_Projecten` faalt met `mdb-export` error.

**Oorzaak**: Het `.mdb` bestand is mogelijk corrupt of in een niet-ondersteund formaat.

**Oplossing**: Controleer of het bestand een geldig Access 2000/2003 bestand is. De `mdbtools`-suite ondersteunt geen `.accdb` (Access 2007+) bestanden.

### MongoDB-verbinding faalt

**Probleem**: Airflow-tasks falen met `pymongo.errors.ConnectionFailure`.

**Oorzaak**: MongoDB-container is nog niet volledig opgestart.

**Oplossing**: Wacht tot MongoDB klaar is (`docker logs wasstraat_mongo` toont "Waiting for connections"). Herstart de DAG.

### PostgreSQL-tabellen zijn leeg

**Probleem**: Na de Load-stap zijn de `Def_*` tabellen leeg.

**Oorzaak**: De transformatiestappen zijn niet (volledig) uitgevoerd.

**Oplossing**: Draai de volledige ETL-cyclus of controleer in MongoDB of de staging-collecties data bevatten.

### Elasticsearch toont geen resultaten

**Probleem**: De zoekfunctie in de Flask-app geeft geen resultaten.

**Oorzaak**: De Elasticsearch-index is niet opgebouwd na de Load-stap.

**Oplossing**: Controleer of Elasticsearch draait (`curl localhost:9200`) en herstart eventueel de Load-stap.

## Jupyter Notebooks voor Exploratie

Voor diepgaande data-exploratie kun je Jupyter Lab gebruiken:

```
http://localhost:8888
```

De notebook-omgeving heeft toegang tot:

- De bronbestanden (via `/home/jovyan/basefiles/`)
- De Airflow verwerkingslogica (via `/opt/wasstraat/`)
- De gedeelde configuratie (via `/home/jovyan/shared/`)
- De Wasstraat-configuratie (via `/home/jovyan/wasstraat_config/`)

Er zijn 68+ bestaande notebooks beschikbaar in de `notebooks/` directory die voorbeelden bevatten van data-exploratie, transformatie-validatie en analyse.
