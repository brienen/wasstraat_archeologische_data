# Installatie met images

Deze handleiding is voor gemeenten en andere organisaties die de Wasstraat willen **gebruiken**. Je installeert haar vanuit de gepubliceerde Docker-images op de GitHub Container Registry (`ghcr.io/brienen`), zonder de broncode te clonen en zonder iets te bouwen. Alles wat je nodig hebt staat in één map, `deploy/`.

De repository zelf is de **ontwikkelomgeving**: daar bouw je de images uit de broncode, draai je de tests en publiceer je nieuwe versies. Wil je aan de Wasstraat ontwikkelen, volg dan [Aan de slag](../aan-de-slag.md).

## Wat je krijgt

Zeven containers uit vaste images:

| Service | Image | Rol |
|---------|-------|-----|
| Airflow | `ghcr.io/brienen/wasstraat-airflow` | Verwerkingspipeline (ETL), inclusief de pipelinecode |
| Flask App | `ghcr.io/brienen/wasstraat-flask` | Webapplicatie om de verwerkte data te bekijken en te beheren |
| PostgreSQL | `ghcr.io/brienen/wasstraat-postgres` | PostgreSQL 18 met PostGIS, definitieve opslag |
| Apache | `ghcr.io/brienen/wasstraat-apache` | Voordeur van de webapplicatie: stuurt door naar Flask en serveert de verwerkte foto's en documenten |
| MongoDB | `mongo:7.0` | Tussenopslag van de pipeline |
| Elasticsearch | `elasticsearch:8.17.0` | Zoekindex, alleen bereikbaar binnen de installatie |
| Redis | `redis:7.2-alpine` | Cache van de webapplicatie |

Elke eigen image heeft twee tags: het versienummer (bijvoorbeeld `1.0.1`) en `latest`. Gebruik in een installatie altijd een versienummer, zodat een `docker compose pull` nooit onverwacht een nieuwe versie binnenhaalt.

Jupyter Lab, dat in de ontwikkelomgeving meedraait voor analyses op de broncode, maakt geen deel uit van de live installatie. Het is een ontwikkelvoorziening van de repository.

Van jouw kant komen alleen configuratie en data. De containers lezen en schrijven in deze mappen op de host:

| Map | Inhoud | Wie schrijft |
|-----|--------|--------------|
| `config/*.env` | Wachtwoorden en instellingen van de services | Jij (eenmalig gegenereerd) |
| `wasstraat_config/` | Harmonisatie-Excel en `correcties.yml` | Jij |
| `data/input/` | Brondata: Access-databases, foto's, rapporten | Jij; de containers lezen alleen |
| `data/output/` | Verwerkte foto's en documenten in drie formaten | Airflow en Flask |
| `data/backup/` | Backups van PostgreSQL en MongoDB | `make backup` |

De databases staan in Docker-volumes (`wasstraat_postgres`, `wasstraat_mongo`, `wasstraat_mongo_config`, `wasstraat_elasticsearch`) en de taaklogs van Airflow in `wasstraat_airflow_logs`. Die blijven bestaan bij het bijwerken en bij `docker compose down`.

## 1. Vereisten

- **Docker** met Docker Compose v2.20 of nieuwer: Docker Engine op een Linux-server (aanbevolen voor een installatie die blijft draaien) of Docker Desktop op macOS of Windows. De images zijn er voor `linux/amd64` en `linux/arm64`.
- **GNU Make en bash** voor de meegeleverde `Makefile`. Elk commando is één `docker compose`-aanroep; zonder Make typ je die zelf (zie `make -n <commando>`). Op Windows gebruik je WSL 2.
- **Geheugen**: minimaal 8 GB voor Docker, 12 GB aanbevolen. Voor de Delftse dataset (ruim 1.000 opgravingen) is gewerkt met 32 GB en 10 cores.
- **Schijfruimte**: ongeveer 15 GB voor de images, plus ruimte voor je brondata, de verwerkte media (ordegrootte van de foto's in de brondata) en de databases (in Delft tientallen GB).
- **Netwerk**: toegang tot `ghcr.io` en Docker Hub om de images op te halen. Op een Linux-server maak je een gebruiker met rechten op Docker (`docker`-groep).

!!! note "Vrije poorten"
    Standaard gebruikt de installatie de poorten 8080 (Airflow) en 5052 (de webapplicatie via Apache, inclusief de media) op alle netwerkkaarten, en 5432 (PostgreSQL) en 27017 (MongoDB) alleen op `127.0.0.1`. Flask, Elasticsearch en Redis krijgen geen hostpoort. Alle poorten zijn in te stellen in `.env`.

## 2. De map deploy ophalen

Haal de map `deploy/` van de gewenste versie op. Zonder Git, met één opdracht:

```bash
VERSIE=1.0.1
curl -L "https://github.com/brienen/wasstraat_archeologische_data/archive/refs/tags/$VERSIE.tar.gz" \
  | tar xz --strip-components=1 "wasstraat_archeologische_data-$VERSIE/deploy"
cd deploy
```

Je kunt ook het zip-bestand van de release downloaden op <https://github.com/brienen/wasstraat_archeologische_data/releases> en alleen de map `deploy/` bewaren. Hernoem de map gerust, bijvoorbeeld naar `wasstraat/`.

De map bevat:

```
deploy/
├── docker-compose.yml    # De services, alleen image:-regels naar ghcr.io/brienen
├── .env.example          # Versie, mappen en poorten → kopiëren naar .env
├── Makefile              # make help toont alle commando's
├── init-config.sh        # Maakt config/*.env aan met unieke wachtwoorden
├── config/               # Sjablonen (*.env.example) voor de configuratie van de services
├── wasstraat_config/     # Harmonisatie-Excel en correcties.yml voor de pipeline
└── data/
    ├── input/            # Brondata (zeven mappen, zie stap 4)
    ├── output/           # Verwerkte media
    └── backup/           # Backups
```

## 3. Configureren

```bash
make init
```

Dit maakt drie dingen aan:

1. **`.env`** uit `.env.example`, met de versie (`WASSTRAAT_VERSION`), de mappen, de poorten en het gemeenteprofiel. Pas dit bestand aan als je data op een andere schijf staat (`WASSTRAAT_INPUT`, `WASSTRAAT_OUTPUT`, `WASSTRAAT_BACKUP`) of als poorten bezet zijn.
2. **`config/*.env`** uit de sjablonen, met voor elke installatie unieke wachtwoorden. Ze worden eenmalig in de terminal getoond en staan daarna in de bestanden. Bestaande bestanden blijven ongemoeid.
3. De **datamappen** uit `.env`, schrijfbaar voor de containers.

Instellingen die je mogelijk wilt aanpassen:

| Bestand | Instelling | Wanneer |
|---------|-----------|---------|
| `.env` | `WASSTRAAT_GEMEENTE` | Het gemeenteprofiel van de pipeline: `delft` (standaard) of `voorbeeld`. Zie [Gemeenteprofielen](../componenten/gemeenteprofielen.md). |
| `.env` | `WASSTRAAT_BIND` | `127.0.0.1` als de webapplicaties alleen op de server zelf bereikbaar mogen zijn, bijvoorbeeld achter een reverse proxy. |
| `.env` | `WASSTRAAT_ES_GEHEUGEN` | Meer geheugen voor Elasticsearch bij grote datasets, bijvoorbeeld `2g`. |
| `config/flask.env` | `MAIL_*` | Mailserver voor meldingen vanuit de webapplicatie (optioneel). |
| `config/airflow.env` | `AIRFLOW__SCHEDULER__*` | Alleen voor gevorderden. |

!!! danger "Niet aanpassen"
    `PGDATA` staat vast in `docker-compose.yml` op `/data/postgres`, hetzelfde pad als het volume. Wijzig je het een, wijzig dan ook het ander, anders komt de database in de container terecht en verdwijnt die bij het bijwerken. De hostnamen in `config/*.env` (`postgres`, `wasstraat_postgres`, `mongo`, `redis`, `elasticsearch`) zijn de namen van de services en horen ook niet te veranderen.

## 4. Eigen data klaarzetten

Zet je brondata in `data/input/` (of in de map uit `WASSTRAAT_INPUT`). De structuur is dezelfde als in de ontwikkelomgeving; [Aan de slag, stap 4](../aan-de-slag.md#4-bestanden-klaarzetten) beschrijft per map welke bestanden en tabellen de pipeline verwacht.

```
data/input/
├── projecten/           ← Per opgraving een map met de projectdatabase (.mdb/.accdb) en foto's
├── projectenlijst/      ← Projectoverzicht (tabel OPGRAVINGEN)
├── magazijnlijst/       ← Depotregistratie
├── fotolijst/           ← Fotocatalogus
├── monsterdatabase/     ← Monsters en determinaties
├── rapporten/           ← Rapporten (.pdf) en rapportendatabases
└── referentietabellen/  ← ABR-thesaurus (abr_versie_*.xlsx) en bestandslijsten
```

De containers lezen deze mappen alleen; de pipeline wijzigt je bronbestanden nooit. Je kunt ze dus ook rechtstreeks vanaf een netwerkschijf koppelen door `WASSTRAAT_INPUT` daarnaar te laten wijzen.

De pipelineconfiguratie staat in `wasstraat_config/`:

- `Wasstraat_Config_HarmonizeV3.xlsx` vertaalt de tabel- en kolomnamen van jouw databases naar het datamodel van de Wasstraat. De meegeleverde versie is die van Delft; pas haar aan volgens [Aan de slag, stap 5](../aan-de-slag.md#5-wasstraat_config_harmonizev3-configureren).
- `correcties.yml` bevat optionele datacorrecties, zoals verkeerde projectcodes. Het meegeleverde sjabloon doet niets; zie [stap 5b](../aan-de-slag.md#5b-correcties-configureren-optioneel).

!!! tip "Eerst proberen met voorbeelddata"
    Wil je de installatie eerst zien werken? Download uit de repository de map `data/synthetic/data/` (twee fictieve opgravingen) en zet de inhoud in `data/input/`. De meegeleverde harmonisatie-Excel is daar al op afgestemd.

## 5. Starten

```bash
make up
```

De eerste keer haalt Docker ongeveer 15 GB aan images op; dat duurt enkele minuten tot een half uur. Daarna starten de containers. Controleer de status:

```bash
make ps
make logs S=airflow     # logs van één service; zonder S= van alle services
```

Alle zeven services moeten `Up` zijn (Elasticsearch `healthy`). Airflow en Flask wachten bij het starten zelf tot PostgreSQL klaar is; Flask maakt bij de eerste start de tabellen in PostgreSQL aan en de beheerder van de webapplicatie.

!!! warning "Linux: rechten op de mappen"
    De containers draaien als verschillende gebruikers (Airflow bijvoorbeeld als uid 50000). `make init` maakt de uitvoer- en backupmappen daarom schrijfbaar voor iedereen. Gebruik je eigen mappen via `.env`, geef die dan dezelfde rechten: `chmod -R a+rwX <map>`. Op macOS en Windows regelt Docker Desktop dit zelf.

## 6. Inloggen

```bash
make inloggegevens
```

| Applicatie | Adres | Inloggegevens |
|------------|-------|---------------|
| Airflow | http://localhost:8080 | `admin`, wachtwoord in `config/airflow.env` (`SECURITY__ADMIN_PASSWORD`) |
| Flask App | http://localhost:5052 | `admin`, wachtwoord in `config/flask.env` (`FLASK_ADMIN_PASSWORD`) |
| Media | http://localhost:5052/archeomedia/... | Geen inlog: Apache serveert `data/output/archeomedia/` rechtstreeks |

Apache is de voordeur van de webapplicatie: het serveert de media onder `/archeomedia` zelf en stuurt alle overige verzoeken door naar Flask, dat geen eigen hostpoort heeft. Vervang `localhost` door de naam van de server als je op afstand werkt. Het Flask-wachtwoord uit `config/flask.env` geldt alleen bij het aanmaken van de beheerder; wijzig je het later via het gebruikersmenu, dan blijft het nieuwe wachtwoord staan. Het Airflow-wachtwoord werkt op dezelfde manier.

!!! warning "Beveiliging"
    De webapplicaties luisteren standaard op alle netwerkkaarten en Apache serveert de media zonder inlog. Zet een installatie niet rechtstreeks aan het internet: gebruik een firewall of een reverse proxy met TLS vóór Apache en zet `WASSTRAAT_BIND=127.0.0.1` in `.env` als die proxy op dezelfde server draait. Laat die proxy de `Host`-header en `X-Forwarded-Proto: https` doorgeven; Apache en Flask nemen ze over, zodat redirects naar het juiste adres wijzen. De databases zijn standaard alleen vanaf de server zelf bereikbaar (`WASSTRAAT_BIND_DB=127.0.0.1`), bijvoorbeeld voor QGIS of pgAdmin.

## 7. De eerste volledige verwerking

De eerste keer verwerk je alle brondata met de DAG `Extract_Transform_Load_Full_Cycle`. Dat kan via de Airflow-webinterface (DAG aanzetten en op de play-knop klikken, zie [Aan de slag, stap 6](../aan-de-slag.md#6-voor-de-eerste-keer-draaien)) of vanaf de commandoregel:

```bash
make volledige-cyclus
```

Volg de voortgang in Airflow onder **Graph**. Voor een paar projecten duurt de verwerking enkele minuten, voor een volledige gemeentelijke collectie uren. Daarna zie je de projecten op de kaart in de Flask App (de startpagina wordt vijf minuten gecachet, dus eventueel even wachten) en zijn de foto's verwerkt in `data/output/archeomedia/`.

Komen er later opgravingen bij, of vervang of verwijder je bestanden, draai dan de incrementele cyclus. Die verwerkt alleen de wijzigingen en laat de rest van de database staan:

```bash
make incrementeel
```

Draai de volledige cyclus opnieuw na wijzigingen in de harmonisatie-Excel, in `correcties.yml` of na het bijwerken naar een versie met een gewijzigde pipeline (zie het volgende hoofdstuk). De volledige cyclus leegt de tussenopslag en de definitieve tabellen en bouwt alles opnieuw op; bruiklenen, partijen en conserveringsgegevens die in de webapplicatie zijn ingevoerd blijven staan. Zie [Incrementeel laden](../componenten/incrementeel-laden.md) voor de details.

## 8. Bijwerken naar een nieuwe versie

Nieuwe versies verschijnen op <https://github.com/brienen/wasstraat_archeologische_data/releases>. Bijwerken gaat in drie stappen:

```bash
make backup                                # 1. backup van PostgreSQL en MongoDB
sed -i 's/^WASSTRAAT_VERSION=.*/WASSTRAAT_VERSION=1.1.0/' .env   # 2. nieuwe versie in .env (of met een editor)
make update                                # 3. images ophalen en containers vervangen
```

Wat er gebeurt bij `make update`:

- Docker haalt de images van de nieuwe versie op en vervangt alleen de containers waarvan de image is veranderd. De volumes met de databases, de Airflow-logs en alle mappen op de host blijven staan.
- Airflow werkt bij het starten zijn eigen metadata-database bij (`airflow db upgrade`). De Flask App maakt nieuwe tabellen en kolommen aan die in de nieuwe versie zijn toegevoegd; bestaande data blijft staan.
- Lees de release-opmerkingen. Als de pipeline is gewijzigd, draai dan `make volledige-cyclus`, zodat de verwerkte data overeenkomt met de nieuwe code. Zijn de harmonisatie-Excel of `correcties.yml` gewijzigd, vergelijk ze dan met jouw versie in `wasstraat_config/`.
- Oude images blijven op de schijf staan; ruim ze op met `docker image prune`.

Teruggaan naar een oudere versie kan door de oude versie in `.env` te zetten en `make update` te draaien, maar een nieuwere versie kan het databaseschema hebben gewijzigd. Zet in dat geval ook de backup van vóór het bijwerken terug.

!!! warning "Grote PostgreSQL-versiesprong"
    De PostgreSQL-image is gebaseerd op PostgreSQL 18. Een toekomstige versie met een hogere hoofdversie van PostgreSQL kan het bestaande datavolume niet zomaar lezen. De release-opmerkingen vermelden dat dan, met de stappen (backup, volume leegmaken, restore).

!!! note "Overstappen van een installatie uit de repository"
    Draaide je de Wasstraat al vanuit een clone van de repository (`make app` of `make delft`)? Maak daar een backup (`make backup`), kopieer de bestanden uit `data/<omgeving>/backup/postgres/` en `.../mongo/` naar `data/backup/postgres/` en `data/backup/mongo/` van de nieuwe installatie, start die (`make up`) en zet de backup terug met `make restore TS=<tijdstempel>`. Kopieer ook `data/<omgeving>/output/archeomedia/` naar `data/output/archeomedia/`, en neem de wachtwoorden over uit de oude `config/*.env` als je dezelfde inloggegevens wilt houden. Een migratie van het oude PostgreSQL-volume (`make migrate-postgres-data`) is hier niet nodig.

## 9. Backup en restore

```bash
make backup                              # dump van PostgreSQL en MongoDB
make restore TS=2026-01-15_10-30-00      # terugzetten van één tijdstempel
```

`make backup` stopt Flask en Airflow kort, schrijft `data/backup/postgres/postgres_<tijdstempel>.tar` (`pg_dump`) en `data/backup/mongo/mongo_<tijdstempel>/` (`mongodump` van de drie databases van de pipeline) en start de containers weer. Plan dit bijvoorbeeld 's nachts in met `cron`, en kopieer de backupmap naar een andere locatie.

Niet in de backup zitten:

- **De verwerkte media** in `data/output/`. Neem die map op in je gewone bestandsbackup; de pipeline kan ze ook opnieuw aanmaken met de volledige cyclus.
- **De configuratie** `.env` en `config/*.env`. Bewaar daar een kopie van op een veilige plek: zonder de wachtwoorden kom je niet meer in de databases.
- **De zoekindex** van Elasticsearch. Die bouwt de volledige cyclus opnieuw op; de DAG `DAG_Load_Only` doet dat ook zonder de brondata opnieuw in te lezen.

`make restore` zet de PostgreSQL-dump terug met `pg_restore` (bestaande tabellen worden eerst verwijderd) en de MongoDB-databases met `mongorestore --drop`. De tijdstempel is het deel van de bestandsnaam na `postgres_` of `mongo_`.

## 10. Wat je niet moet doen

- **Geen `docker compose down -v`** en geen `docker volume rm`: dat verwijdert de databases. `make down` verwijdert alleen de containers.
- **Niet twee installaties op één Docker-host**: de containers hebben vaste namen (`wasstraat_postgres` enzovoort). Een tweede installatie, ook een uit de repository, botst daarmee.
- **`init-config.sh --force` niet op een bestaande installatie**: dan krijgen de `config/*.env` nieuwe wachtwoorden, terwijl de databases de oude kennen. Wil je een wachtwoord wijzigen, doe dat dan in de database én in het bestand.
- **`latest` niet als versie in `.env`**: dan bepaalt het moment van `docker compose pull` welke versie je draait.
- **Geen wijzigingen in de containers**: alles wat je in een container aanpast verdwijnt bij het bijwerken. Configuratie hoort in `.env`, `config/` en `wasstraat_config/`.
- **De `.env`-bestanden niet delen of in versiebeheer zetten**: ze bevatten de wachtwoorden.
- **De brondata niet aanpassen tijdens een verwerking**: de pipeline registreert per bestand een vingerafdruk; wijzigingen tijdens een run leveren een inconsistente registratie op.

## Veelvoorkomende problemen

**`denied` of `unauthorized` bij het ophalen van de images.** De images zijn publiek; controleer de versie in `.env` (bestaat de tag?) en de netwerktoegang tot `ghcr.io`. Een `docker login ghcr.io` is niet nodig.

**Een container start steeds opnieuw.** Bekijk `make logs S=<service>`. Bij Elasticsearch is de oorzaak meestal te weinig geheugen voor Docker; bij Airflow of Flask een PostgreSQL die nog niet klaar is (ze proberen het vanzelf opnieuw).

**`permission denied` in de logs van Airflow of Flask (Linux).** De mappen uit `.env` zijn niet schrijfbaar voor de containers: `chmod -R a+rwX` op de uitvoer- en backupmap.

**Load mislukt met `relation Def_... does not exist`.** De Flask App maakt de tabellen aan; controleer met `make ps` of `wasstraat_flask` draait en start de Load-stap opnieuw.

**Poort al in gebruik.** Pas de poort aan in `.env` en draai `make up` opnieuw.

Meer oplossingen staan in [Aan de slag](../aan-de-slag.md#veelvoorkomende-problemen); de commando's daar met `docker exec wasstraat_<service>` werken ook in deze installatie.

## Voor beheerders van de Wasstraat zelf

Het publiceren van nieuwe images (`make publish`, `make release`) en de inrichting van de registry staan beschreven in [Omgevingen & Docker Compose](omgevingen.md#publicatie-van-images).
