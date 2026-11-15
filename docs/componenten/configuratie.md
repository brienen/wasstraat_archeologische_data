# Configuratie

Deze pagina is het naslagwerk voor alles wat je aan de Wasstraat kunt instellen zonder de code te wijzigen: de omgevingsvariabelen van de services, de datacorrecties in `correcties.yml`, de harmonisatie-Excel, het gemeenteprofiel, de instellingen van de live installatie in `deploy/`, de vastgelegde pakketversies en het versienummer. Per onderdeel staat waar het staat, wie het leest, wat de standaard is en wat een wijziging vraagt.

De stap-voor-stap-handleidingen verwijzen hierheen: [Aan de slag](../aan-de-slag.md) voor de ontwikkelomgeving en [Installatie met images](../deployment/installatie-met-images.md) voor de live installatie.

## 1. Overzicht van de configuratielagen

| Laag | Ontwikkelomgeving (repository) | Live installatie (`deploy/`) | Gelezen door |
|------|-------------------------------|------------------------------|--------------|
| [Omgevingsvariabelen van de services](#2-omgevingsvariabelen) | `config/*.env`, gemaakt door `init-config.sh` uit `config/*.env.example` | `deploy/config/*.env`, gemaakt door `make init` | De containers, bij het aanmaken van de container |
| [Instellingen in de compose-bestanden](#26-instellingen-in-de-compose-bestanden) | `environment:`-blokken, mounts en poorten in `docker-compose*.yml` | `deploy/.env` (`WASSTRAAT_*`) | Docker Compose |
| [`correcties.yml`](#3-correctiesyml) | `data/<omgeving>/wasstraat_config/correcties.yml` | `deploy/wasstraat_config/correcties.yml` | De pipeline, bij elke taak opnieuw |
| [Harmonisatie-Excel](#4-harmonisatie-excel) | `data/<omgeving>/wasstraat_config/Wasstraat_Config_HarmonizeV3.xlsx` | `deploy/wasstraat_config/Wasstraat_Config_HarmonizeV3.xlsx` | Transform 1, bij elke taak opnieuw |
| [Gemeenteprofiel](#5-gemeenteprofiel) | Code in `airflow_app/dags/wasstraat/profielen/`, gekozen met `WASSTRAAT_GEMEENTE` | `WASSTRAAT_GEMEENTE` in `deploy/.env` | `Start_Run`, Transform 1 en 2 |
| [Versienummer](#8-versienummer-en-releases) | `config/version.env` (uit `config/version.env.example`) | `WASSTRAAT_VERSION` in `deploy/.env` | `make publish`, `make release`, het verwerkingsrapport |
| [Pakketversies](#7-pakketversies) | `services/*/requirements.txt` en `services/*/constraints.txt` | Vast in de gepubliceerde images | De build van de images |

De standaardwaarden van alle omgevingsvariabelen staan in `shared/config.py`; die code is leidend als deze pagina en de code verschillen.

### Wat een wijziging vraagt

| Je wijzigt | Nodig daarna |
|------------|--------------|
| Een waarde in `config/*.env` of `deploy/.env` | De container opnieuw aanmaken: `make app` of `make delft` in de ontwikkelomgeving, `make up` in de live installatie. Docker Compose ziet de gewijzigde configuratie en vervangt alleen de betrokken containers. `make start` en `make restart` lezen de bestanden niet opnieuw. |
| Een wachtwoord van PostgreSQL, MongoDB of een beheerder | Meer dan het bestand: de databases en beheerders worden bij de eerste start aangemaakt en lezen het wachtwoord daarna niet meer. Zie [Wachtwoorden wijzigen](#wachtwoorden-wijzigen). |
| `correcties.yml` of de harmonisatie-Excel | Geen herstart: elke taak leest de bestanden opnieuw. Draai de **volledige cyclus**, zodat de wijziging voor alle data geldt; de incrementele cyclus past haar alleen toe op nieuwe en gewijzigde bronbestanden. |
| `WASSTRAAT_GEMEENTE` | De Airflow-container opnieuw aanmaken en daarna de **volledige cyclus**. |
| Een drempel (`AIRFLOW_MAX_*`) of `AIRFLOW_OUTPUT_RAPPORTEN` | De Airflow-container opnieuw aanmaken; geldt vanaf de volgende run. |
| Een pad of mount (invoer, uitvoer, configuratie) | De betrokken containers opnieuw aanmaken; na een andere invoermap de **volledige cyclus**. |
| `requirements.txt` of een Dockerfile | `make constraints`, de images opnieuw bouwen en `make test-all` (zie [Pakketversies](#7-pakketversies)). |
| Het versienummer | `make release` (zie [Versienummer en releases](#8-versienummer-en-releases)). |

!!! info "Nieuwe variabelen in een bestaande installatie"
    `init-config.sh` maakt alleen ontbrekende `config/*.env`-bestanden aan; een bestaand bestand wordt nooit bijgewerkt. Komt er in een nieuwe versie een variabele bij in een `.env.example` (zoals de drempels van oktober 2026), dan geldt in een bestaande installatie de standaardwaarde uit `shared/config.py`. Wil je afwijken, neem de regel dan over uit het sjabloon in je eigen `.env`-bestand.

!!! info "Opgeruimde variabelen (issue 87)"
    Uit de sjablonen zijn variabelen verdwenen die niemand las: `AIRFLOW_INPUTDIR`, `AIRFLOW_VAR_TEMPDIR` en `_AIRFLOW_WWW_USER_USERNAME`/`_PASSWORD` uit `airflow.env` (de Airflow-image start met een eigen entrypoint, `scripts/airflow/init.sh`, dat `SECURITY__ADMIN_*` gebruikt), `MONGO_MINPOOLSIZE`, `COLL_STAGING_NIEUW` en de `COLL_ANALYSE_*`-variabelen behalve `COLL_ANALYSE_DOOS` uit `mongo.env`, en het hele sjabloon `elasticsearch.env`. Staan ze nog in je eigen `config/*.env`, dan doen ze niets; je mag ze laten staan of weghalen. `AIRFLOW__WEBSERVER_BASE_URL` (met één underscore tussen sectie en sleutel) heet nu `AIRFLOW__WEBSERVER__BASE_URL`; Airflow las de oude naam niet en gebruikte dus al zijn standaard `http://localhost:8080`. `tests/unit/test_config.py` eist dat elke variabele in de sjablonen van Airflow, MongoDB en Flask ook gelezen wordt.

## 2. Omgevingsvariabelen

### 2.1 Hoe de bestanden ontstaan

De sjablonen `config/*.env.example` staan in de repository; de echte `config/*.env`-bestanden niet (`.gitignore`: `*.env`). Bij `make app`, `make delft`, `make dev` en `make build` roept de Makefile `init-config.sh` aan. Dat script:

1. maakt voor elk sjabloon zonder bijbehorend `.env`-bestand een kopie;
2. vervangt daarin de plaatshouders door unieke wachtwoorden van 24 letters en cijfers (zie de tabel hieronder);
3. toont de gegenereerde wachtwoorden één keer in de terminal.

Bestaande bestanden blijven ongemoeid. `./init-config.sh --force` overschrijft alle bestanden met nieuwe wachtwoorden; doe dat niet bij een installatie met data, want de databases kennen dan de oude wachtwoorden nog. De live installatie heeft een kopie van het script en van zes sjablonen (`deploy/init-config.sh`, `deploy/config/*.env.example`); `make init` roept het daar aan. `tests/unit/test_deploy.py` bewaakt dat de kopieën gelijk zijn aan het origineel.

| Gegenereerd geheim | Plaatshouder in het sjabloon | Komt in |
|--------------------|------------------------------|---------|
| Wachtwoord van de PostgreSQL-gebruiker van Airflow | `airflow_secret_42` | `postgres.env` (`POSTGRES_PASSWORD`) en `airflow_db.env` (`DB__PASSWORD`) |
| Wachtwoord van de PostgreSQL-gebruiker van Flask | `flask_secret_42` | `postgres.env` (`FLASK_PGPASSWORD`) |
| Wachtwoord van de MongoDB-beheerder | `mongo_secret_42` | `mongo.env` (`MONGO_INITDB_ROOT_PASSWORD`) |
| Wachtwoord van Redis | `redis_secret_42` | `redis.env` (`CACHE_REDIS_PASSWORD`) |
| Geheime sleutel van Flask | `wijzig_deze_geheime_sleutel` | `flask.env` (`SECRET_KEY`) |
| Wachtwoord van de Flask-beheerder `admin` | `flask_admin_secret_42` | `flask.env` (`FLASK_ADMIN_PASSWORD`) |
| Wachtwoord van de Airflow-beheerder | `admin` | `airflow.env` (`SECURITY__ADMIN_PASSWORD`) |
| Token van Jupyter Lab | `jupyter_secret_42` | `jupyter.env` (`JUPYTER_PASSWORD`, alleen ontwikkelomgeving) |

`version.env` bevat geen geheimen.

### 2.2 Welke service welk bestand leest

| Service | Ontwikkelomgeving (`docker-compose.yml`, `docker-compose.delft.yml`) | Live installatie (`deploy/docker-compose.yml`) |
|---------|------------------------------|------------------------------|
| `airflow` | `airflow.env`, `airflow_db.env`, `mongo.env`, `postgres.env` | idem, plus `WASSTRAAT_GEMEENTE` en `WASSTRAAT_VERSION` uit `deploy/.env` |
| `flask` | `flask.env`, `postgres.env`, `mongo.env`, `redis.env` | idem |
| `postgres` | `postgres.env`, `flask.env` | `postgres.env` |
| `mongo` | `mongo.env` | `mongo.env` |
| `redis` | `redis.env` | `redis.env` |
| `jupyter` | `jupyter.env`, `airflow.env`, `airflow_db.env`, `mongo.env`, `postgres.env` | geen Jupyter |
| `elasticsearch`, `apache` | geen (instellingen staan in het compose-bestand) | idem |

Twee gevolgen:

- Flask leest `airflow.env` niet. Instellingen die Airflow en Flask allebei gebruiken (`AIRFLOW_OUTPUT_MEDIA`, `FILE_WORD_ICON`, `ES_HOST`) hebben in Flask daarom altijd hun standaardwaarde; houd de mounts in lijn met die standaard.
- Een variabele in een `environment:`-blok van het compose-bestand gaat vóór dezelfde variabele in een `env_file`. `WASSTRAAT_GEMEENTE` zet je daarom in `docker-compose.delft.yml` (of `deploy/.env`), niet in `config/airflow.env`.

Omgevingsvariabelen zijn altijd tekst. `shared/config.py` zet getallen om (`int()` voor aantallen en poorten, `float()` voor percentages); een lege, ongeldige of negatieve drempel levert de standaardwaarde op, met een waarschuwing in het log.

### 2.3 Airflow (`airflow.env`, `airflow_db.env`)

`airflow.env`:

| Variabele | Betekenis | Standaard in de code | Sjabloon | Geheim |
|-----------|-----------|----------------------|----------|--------|
| `AIRFLOW__CORE__EXECUTOR` | Executor van Airflow | Airflow: `SequentialExecutor` | `LocalExecutor` | – |
| `AIRFLOW__CORE__LOAD_EXAMPLES` | Voorbeeld-DAG's van Airflow tonen | Airflow: `True` | `False` | – |
| `AIRFLOW__WEBSERVER__WEB_SERVER_HOST` | Adres waarop de webinterface luistert | Airflow: `0.0.0.0` | `0.0.0.0` | – |
| `AIRFLOW__WEBSERVER__BASE_URL` | Adres waaronder de webinterface van Airflow bereikbaar is; Airflow gebruikt het voor de links in logs en meldingen. Airflow staat niet achter Apache, dus dit is de hostpoort van Airflow; pas het aan als Airflow via een andere naam of poort bereikbaar is (live installatie: `WASSTRAAT_PORT_AIRFLOW`) | Airflow: `http://localhost:8080` | `http://localhost:8080` | – |
| `AIRFLOW__SCHEDULER__MIN_FILE_PROCESS_INTERVAL` | Seconden tussen het opnieuw inlezen van de DAG-bestanden | Airflow: `30` | `60` | – |
| `SECURITY__ADMIN_USERNAME`, `_FIRSTNAME`, `_LASTNAME`, `_EMAIL` | Gegevens van de Airflow-beheerder, alleen gebruikt bij de eerste start (`scripts/airflow/init.sh`) | – | `admin`, `Admin`, `Administrators`, `admin@example.com` | – |
| `SECURITY__ADMIN_PASSWORD` | Wachtwoord van de Airflow-beheerder, alleen bij de eerste start | – | gegenereerd | ja |
| `AIRFLOW_TEMPDIR` | Werkmap van de extractie (CSV-exports, lijstbestanden `delta_<categorie>.txt` van de incrementele cyclus); de Airflow-image maakt de map aan | `/opt/airflow/tmp` | `/opt/airflow/tmp` | – |
| `AIRFLOW_LOGDIR` | Map voor de logs van `importMDB.sh` (`<collectie>.log`, gelezen door `Controleer_Databases`) en terugvalmap van de verwerkingsrapporten | `/opt/airflow/logs` | `/opt/airflow/logs` | – |
| `AIRFLOW_WASSTRAAT_CONFIG` | Pad van de [harmonisatie-Excel](#4-harmonisatie-excel) | `/opt/airflow/config/Wasstraat_Config_HarmonizeV3.xlsx` | `/opt/airflow/config/Wasstraat_Config_HarmonizeV3.xlsx` | – |
| `AIRFLOW_MAX_MISLUKTE_AFBEELDINGEN` | Drempel (aantal) voor mislukte en onverwerkte afbeeldingen en rapporten (taak `Controleer_Afbeeldingen`) | `10` | `10` | – |
| `AIRFLOW_MAX_MISLUKTE_AFBEELDINGEN_PCT` | Drempel (procent van het aantal bestanden) voor dezelfde controle | `1` | `1` | – |
| `AIRFLOW_MAX_MISLUKTE_DATABASES` | Drempel (aantal) voor onleesbare Access-databases (taak `Controleer_Databases`) | `2` | `2` | – |
| `AIRFLOW_MAX_MISLUKTE_DATABASES_PCT` | Drempel (procent van de verwerkte databases) | `5` | `5` | – |
| `AIRFLOW_MAX_VERWERKINGSFOUTEN` | Drempel (aantal) voor records die Transform 2 niet kon verwerken, per taak | `100` | `100` | – |
| `AIRFLOW_MAX_VERWERKINGSFOUTEN_PCT` | Drempel (procent van de bekeken records) | `1` | `1` | – |
| `AIRFLOW_OUTPUT_RAPPORTEN` | Map voor de [verwerkingsrapporten](verwerkingsrapport.md) (JSON en Markdown); niet schrijfbaar: `AIRFLOW_LOGDIR/rapporten` | `/output/rapporten` | `/output/rapporten` | – |

`importMDB.sh` leest `AIRFLOW_TEMPDIR` en `AIRFLOW_LOGDIR` zelf uit de omgeving, met dezelfde standaardwaarden als `shared/config.py`.

Alle drempels, ook die voor de afbeeldingen, leest `shared/config.py` in (`int()` voor het aantal, `float()` voor het percentage); de taken gebruiken die waarden. Voor alle drempels geldt: de toegestane hoeveelheid fouten is het grootste van het aantal en het percentage van het totaal. Het vaste aantal beschermt kleine verzamelingen, het percentage grote. Met `0` en `0` is elke fout cruciaal. Een decimaal percentage mag (`0.5` of `0,5`). Het foutbeleid staat in [Foutbeleid en verwerkingsrapport](verwerkingsrapport.md#foutbeleid).

Variabelen die niet in het sjabloon staan, maar die je in `airflow.env` kunt toevoegen om van de standaard af te wijken:

| Variabele | Betekenis | Standaard in de code |
|-----------|-----------|----------------------|
| `AIRFLOW_INPUT_PROJECTEN` | Map met de opgravingsdatabases (per project een map) | `/input/projecten` |
| `AIRFLOW_INPUT_IMAGES` | Map met foto's en tekeningen; in alle compose-bestanden dezelfde map als de projecten | `/input/images` |
| `AIRFLOW_INPUT_PROJECTENLIJST` | Map met de projectenlijst | `/input/projectenlijst` |
| `AIRFLOW_INPUT_MAGAZIJNLIJST` | Map met de magazijnlijst | `/input/magazijnlijst` |
| `AIRFLOW_INPUT_FOTOLIJST` | Map met de fotocatalogus | `/input/fotolijst` |
| `AIRFLOW_INPUT_MONSTER` | Map met de monsterdatabase | `/input/monsterdatabase` |
| `AIRFLOW_INPUT_RAPPORTEN` | Map met rapporten en rapportendatabases | `/input/rapporten` |
| `FILE_ABREXCEL` | Excel-export van de ABR-thesaurus | `/input/referentietabellen/abr_versie_01122018.xlsx` |
| `FILE_EXTRA_PROJECTS` | Excel met projecten die niet in de projectenlijst staan (optioneel; ontbreekt het, dan slaat de extractie het over) | `/input/projectenlijst/Extra_projecten_tabel_OPGRAVINGEN.xlsx` |
| `FILE_IMPORT_FILES_EXCEL` | Excel met de bestandenlijst van het depot (kolommen `Dir`, `Bestand`, `wel/niet`): extra bestanden die de extractie meeneemt | `/input/referentietabellen/Alle Bestanden Archeologisch Depot.xlsx` |
| `AIRFLOW_OUTPUT_MEDIA` | Uitvoermap voor de verwerkte foto's, tekeningen en rapporten in drie formaten | `/output/archeomedia` |
| `AIRFLOW_CORRECTIES_CONFIG` | Pad van [`correcties.yml`](#3-correctiesyml) | `/opt/airflow/config/correcties.yml` |
| `FILE_WORD_ICON` | Voorbeeldafbeelding (documenticoon) voor Word-documenten | `shared/afbeeldingen/document.png` naast `shared/config.py` |
| `ES_HOST` | Adres van Elasticsearch | `http://elasticsearch:9200` |
| `WASSTRAAT_GEMEENTE` | [Gemeenteprofiel](#5-gemeenteprofiel): `delft` of `voorbeeld` | `delft` |
| `WASSTRAAT_VERSION` | Versie in het verwerkingsrapport; `make app`, `make delft`, `make dev` en de live installatie zetten hem (zie [Versienummer en releases](#8-versienummer-en-releases)) | geen |
| `WASSTRAAT_VERSIEBESTAND` | Bestand met een regel `VERSION=`, gelezen als `WASSTRAAT_VERSION` ontbreekt | `/opt/airflow/version.env` |

De paden zijn paden in de container. Wijzig je een pad, pas dan ook de mount in het compose-bestand aan (zie [Paden en mounts](#27-paden-en-mounts)).

`airflow_db.env`, de metadatabase van Airflow in PostgreSQL:

| Variabele | Betekenis | Sjabloon | Geheim |
|-----------|-----------|----------|--------|
| `DB__HOST`, `DB__PORT` | Server van de metadatabase; `init.sh` wacht tot die bereikbaar is | `wasstraat_postgres`, `5432` | – |
| `DB__USERNAME`, `DB__NAME` | Gebruiker en database; gelijk aan `POSTGRES_USER` en `POSTGRES_DB` in `postgres.env` | `airflow`, `airflow` | – |
| `DB__PASSWORD` | Wachtwoord; gelijk aan `POSTGRES_PASSWORD` | gegenereerd | ja |
| `PGPASSWORD` | Wachtwoord voor `psql` in `init.sh` | `${DB__PASSWORD}` | ja |
| `AIRFLOW__DATABASE__SQL_ALCHEMY_CONN` | Verbinding van Airflow met zijn metadatabase | opgebouwd uit de `DB__`-variabelen | ja |

### 2.4 Databases (`postgres.env`, `mongo.env`, `redis.env`)

`postgres.env` wordt gelezen door PostgreSQL (image `kartoza/postgis`), Airflow, Flask en Jupyter:

| Variabele | Betekenis | Standaard in de code | Sjabloon | Geheim |
|-----------|-----------|----------------------|----------|--------|
| `POSTGRES_USER`, `POSTGRES_DB` | Superuser en database van PostgreSQL, ook gebruikt voor de metadatabase van Airflow | geen; ontbreekt er een, dan meldt `shared/config.py` een fout | `airflow`, `airflow` | – |
| `POSTGRES_PASSWORD` | Wachtwoord van die gebruiker | geen; vereist | gegenereerd | ja |
| `POSTGRES_PASS` | Hetzelfde wachtwoord onder de naam die de PostGIS-image verwacht | – | `${POSTGRES_PASSWORD}` | ja |
| `PASSWORD_AUTHENTICATION` | Authenticatiemethode van de PostGIS-image | – | `md5` | – |
| `FLASK_PGUSER`, `FLASK_PGDATABASE` | Gebruiker en database van de webapplicatie; daarin staan de `Def_`-tabellen. `scripts/postgres/00_init.sql` maakt ze bij de eerste start aan, met PostGIS | geen | `flask`, `flask` | – |
| `FLASK_PGPASSWORD` | Wachtwoord van die gebruiker | geen | gegenereerd | ja |

`PGDATA` staat niet in dit bestand maar vast in de compose-bestanden op `/data/postgres`, het pad van het volume. Wijzig die twee alleen samen (zie [Omgevingen](../deployment/omgevingen.md#persistente-volumes)). De host van de webdatabase is in `shared/config.py` vast `postgres`, de servicenaam.

!!! info "Als een van de drie POSTGRES_-variabelen ontbreekt"
    `shared/config.py` leest `POSTGRES_DB`, `POSTGRES_USER` en `POSTGRES_PASSWORD` elk los in. Ontbreekt er een, dan staat er een foutmelding in het log die de ontbrekende variabelen noemt; de overige instellingen (MongoDB, collecties, paden) worden gewoon ingelezen. Tot issue 87 sloeg één ontbrekende variabele alle instellingen daarna over. Zet ze toch altijd: de PostgreSQL-container maakt er bij de eerste start de gebruiker en de database van Airflow mee aan.

`mongo.env` wordt gelezen door MongoDB, Airflow, Flask en Jupyter:

| Variabele | Betekenis | Standaard in de code | Sjabloon | Geheim |
|-----------|-----------|----------------------|----------|--------|
| `MONGO_SERVER` | Host van MongoDB | geen | `mongo` | – |
| `MONGO_INITDB_ROOT_USERNAME` | Beheerder van MongoDB, aangemaakt bij de eerste start van het volume | geen | `root` | – |
| `MONGO_INITDB_ROOT_PASSWORD` | Wachtwoord van die beheerder | geen | gegenereerd | ja |
| `DB_STAGING` | Database met de ruwe brondata (ook de ABR-thesaurus), `Plaatjes` en de run-documenten (`Verwerkingsruns`, `Verwerkingsrun_Bestanden`) | geen | `Arch_Staging` | – |
| `DB_FILES` | Database met de lijst van te verwerken afbeeldingen en rapporten (`Filenames`) | geen | `Arch_Files` | – |
| `DB_ANALYSE` | Database met `Single_Store`, `Single_Store_Clean` en de records die Transform 2 niet kon verwerken (`_processing_errors`) | geen | `Arch_Analyse` | – |
| `COLL_ANALYSE`, `COLL_ANALYSE_CLEAN` | Collecties van de geharmoniseerde en de samengevoegde data | geen | `Single_Store`, `Single_Store_Clean` | – |
| `COLL_PLAATJES`, `COLL_FILENAMES` | Verwerkte afbeeldingen en de lijst met te verwerken bestanden | geen | `Plaatjes`, `Filenames` | – |
| `COLL_STAGING_OUD` | Staging van de opgravingsdatabases | geen | `Staging_Projecten_Oud` | – |
| `COLL_STAGING_PROJECTENLIJST`, `_MAGAZIJNLIJST`, `_FOTOLIJST`, `_MONSTER` | Staging van de centrale lijsten | geen | `Staging_Projecten_Projectenlijst`, `_Magazijnlijst`, `_Fotolijst`, `_Monster` | – |
| `COLL_STAGING_RAPPORTEN` | Staging van de rapportendatabases. Tot issue 87 noemde het sjabloon `Staging_Projecten_Rapporten`; een installatie met die regel in `mongo.env` werkt gewoon (wijzig je de naam, draai dan de volledige cyclus) | `Staging_Rapporten` | `Staging_Rapporten` | – |
| `COLL_STAGING_REFERENTIETABELLEN` | Staging van de ABR-thesaurus | `Staging_Referentietabellen` | `Staging_Referentietabellen` | – |
| `COLL_STAGING_METAINFO` | Kolominformatie per geïmporteerde tabel (`importMDB.sh`) | geen | `Kolominformatie` | – |
| `COLL_STAGING_NIEUW` | Oude staging-collectie; geen taak schrijft erin, alleen de notebooks in `notebooks/` lezen hem nog | `Staging_Projecten_Nieuw` | niet in het sjabloon | – |
| `COLL_ANALYSE_DOOS` | Oude collectie in `DB_ANALYSE`; `Drop_SingleStoreClean` ruimt hem op als hij nog bestaat | `Def_Doos` | `Def_Doos` | – |

De namen van databases en collecties zijn interne afspraken tussen de taken. Laat ze staan; een andere naam vraagt een volledige cyclus en raakt ook de backup (`make backup` dumpt de drie databases bij naam).

`redis.env` wordt gelezen door Redis en Flask:

| Variabele | Betekenis | Standaard in de code | Sjabloon | Geheim |
|-----------|-----------|----------------------|----------|--------|
| `CACHE_REDIS_HOST` | Host van Redis | geen | `redis` | – |
| `CACHE_REDIS_PASSWORD` | Wachtwoord waarmee Flask inlogt | geen | gegenereerd | ja |
| `REDIS_PASSWORD` | Wachtwoord van de Redis-server (`redis-server --requirepass`) | geen | `${CACHE_REDIS_PASSWORD}` | ja |
| `CACHE_REDIS_PORT`, `CACHE_REDIS_DB` | Poort en databasenummer | `6379`, `0` | `6379`, `0` | – |
| `CACHE_DEFAULT_TIMEOUT` | Seconden dat Flask pagina's en zoekresultaten cachet (onder meer de kaart op de startpagina) | `300` | `300` | – |
| `CACHE_KEY_PREFIX` | Voorvoegsel van de cachesleutels | leeg | niet in het sjabloon | – |

### 2.5 Webapplicatie en analyse (`flask.env`, `jupyter.env`)

`flask.env`:

| Variabele | Betekenis | Standaard in de code | Sjabloon | Geheim |
|-----------|-----------|----------------------|----------|--------|
| `SECRET_KEY` | Sleutel waarmee Flask sessies en CSRF-tokens ondertekent | geen | gegenereerd | ja |
| `FLASK_ADMIN_PASSWORD` | Wachtwoord van de beheerder `admin`, alleen gebruikt als die nog niet bestaat (`app/app/beheerder.py`). Ontbreekt de variabele, dan krijgt een nieuwe beheerder het wachtwoord `admin` en staat er een waarschuwing in het log | `admin` met waarschuwing | gegenereerd | ja |
| `MAIL_SERVER`, `MAIL_USERNAME`, `MAIL_PASSWORD`, `MAIL_DEFAULT_SENDER` | Mailserver van Flask-AppBuilder (bijvoorbeeld voor het herstellen van wachtwoorden); optioneel | geen | voorbeeldwaarden | `MAIL_PASSWORD` |
| `MAIL_USE_TLS` | TLS voor de mailserver: `True` of `False` (ook `1`/`0`, `ja`/`nee`, `yes`/`no`, `on`/`off`; hoofdletters en aanhalingstekens maken niet uit). Leeg of weggelaten: `True`; een ongeldige waarde geeft `True` met een waarschuwing in het log | `True` | `True` | – |
| `DEBUG_TB_PROFILER_ENABLED` | Profiler van de debugwerkbalk, alleen bij precies `True` | `False` | `True` | – |

`jupyter.env` (alleen ontwikkelomgeving): `JUPYTER_PASSWORD`, het token waarmee je inlogt op Jupyter Lab (gegenereerd). De Jupyter-container leest daarnaast `airflow.env`, `airflow_db.env`, `mongo.env` en `postgres.env`, zodat notebooks de pipelinecode kunnen gebruiken.

Elasticsearch heeft geen eigen `.env`-bestand. Airflow en Flask gebruiken de standaard `ES_HOST=http://elasticsearch:9200`, de servicenaam in alle compose-bestanden; wil je een andere host, zet `ES_HOST` dan in `airflow.env` én `flask.env`. Elasticsearch zelf krijgt zijn instellingen in het compose-bestand (single-node, zonder beveiliging, 512 MB geheugen). Tot issue 87 was er een sjabloon `elasticsearch.env.example` dat geen service inlas; een achtergebleven `config/elasticsearch.env` mag je verwijderen.

### 2.6 Instellingen in de compose-bestanden

Sommige instellingen staan niet in `config/`, maar direct in een compose-bestand:

| Instelling | Waar | Waarde |
|------------|------|--------|
| `WASSTRAAT_GEMEENTE` | `docker-compose.delft.yml` (Airflow); `deploy/docker-compose.yml` via `deploy/.env` | `delft`; in `docker-compose.yml` niet gezet, dus de standaard `delft` |
| `WASSTRAAT_VERSION` | `deploy/docker-compose.yml` via `deploy/.env`; `docker-compose.yml` en `docker-compose.delft.yml` (Airflow) via de Makefile | de versie van de images; in de ontwikkelomgeving de versie uit `config/version.env` (anders `config/version.env.example`), meegegeven door `make app`, `make delft` en `make dev` |
| `PGDATA` | alle compose-bestanden (PostgreSQL) | `/data/postgres` |
| Elasticsearch | alle compose-bestanden | `discovery.type=single-node`, `xpack.security.enabled=false`, heap 512 MB (live installatie: `WASSTRAAT_ES_GEHEUGEN`) |
| Debuggen | `docker-compose.develop.yml` (`make dev`) | Airflow: `DEBUGPY=1`, `DEBUG_TARGET=scheduler` (of `webserver`), poort 5678 (`DEBUG_PORT`), één parserproces en geen parallelle taken; Flask: `FLASK_DEBUG=1`, hostpoort 5051 |

De live installatie heeft alle instellbare waarden in `deploy/.env` (sjabloon `deploy/.env.example`):

| Variabele | Betekenis | Standaard |
|-----------|-----------|-----------|
| `WASSTRAAT_VERSION` | Versie (tag) van de images op `ghcr.io/brienen`; verplicht, de compose stopt zonder | de laatste release in het sjabloon (gelijk aan `config/version.env.example`) |
| `WASSTRAAT_REGISTRY` | Registry van de eigen images, alleen wijzigen bij een eigen kopie | `ghcr.io/brienen` |
| `WASSTRAAT_GEMEENTE` | Gemeenteprofiel van de pipeline | `delft` |
| `WASSTRAAT_INPUT` | Map met de brondata (alleen-lezen gekoppeld) | `./data/input` |
| `WASSTRAAT_OUTPUT` | Map voor de verwerkte media (`archeomedia/`) en de verwerkingsrapporten (`rapporten/`) | `./data/output` |
| `WASSTRAAT_BACKUP` | Map voor `make backup` | `./data/backup` |
| `WASSTRAAT_CONFIG` | Map met de harmonisatie-Excel en `correcties.yml` (alleen-lezen gekoppeld) | `./wasstraat_config` |
| `WASSTRAAT_PORT_AIRFLOW` | Hostpoort van Airflow | `8080` |
| `WASSTRAAT_PORT_APACHE` | Hostpoort van de webapplicatie (Apache als voordeur) | `5052` |
| `WASSTRAAT_BIND` | Netwerkadres van Airflow en Apache: `0.0.0.0` (alle netwerkkaarten) of `127.0.0.1` (alleen deze machine) | `0.0.0.0` |
| `WASSTRAAT_PORT_POSTGRES`, `WASSTRAAT_PORT_MONGO` | Hostpoorten van de databases | `5432`, `27017` |
| `WASSTRAAT_BIND_DB` | Netwerkadres van de databases | `127.0.0.1` |
| `WASSTRAAT_ES_GEHEUGEN` | Java-heap van Elasticsearch | `512m` |

Mappen in `deploy/.env` zijn relatief aan de map `deploy/` of absoluut. Zie [Installatie met images](../deployment/installatie-met-images.md#3-configureren).

### 2.7 Paden en mounts

De pipeline werkt met vaste paden in de container; de compose-bestanden koppelen daar mappen van de host aan.

| Pad in de container | Variabele | Ontwikkelomgeving (`make app` / `make delft`) | Live installatie | Testomgevingen |
|---------------------|-----------|-----------------------------------------------|------------------|----------------|
| `/input/projecten` | `AIRFLOW_INPUT_PROJECTEN` | `data/<omgeving>/data/projecten` | `${WASSTRAAT_INPUT}/projecten` (alleen-lezen) | `data/synthetic/data/projecten` (schrijfbaar, voor het testproject SY003), `data/test/data/projecten` |
| `/input/images` | `AIRFLOW_INPUT_IMAGES` | dezelfde map als `projecten` | idem | `AIRFLOW_INPUT_IMAGES=/input/projecten` |
| `/input/rapporten` | `AIRFLOW_INPUT_RAPPORTEN` | `data/<omgeving>/data/rapporten` (in de synthetische data leeg) | `${WASSTRAAT_INPUT}/rapporten` | `data/synthetic/data/rapporten` (leeg), `data/test/data/rapporten` |
| `/input/projectenlijst`, `/input/magazijnlijst`, `/input/fotolijst`, `/input/monsterdatabase`, `/input/referentietabellen` | `AIRFLOW_INPUT_*`, `FILE_*` | `data/<omgeving>/data/<map>` | `${WASSTRAAT_INPUT}/<map>` | `data/synthetic/data/<map>`, `data/test/data/<map>` |
| `/output/archeomedia` | `AIRFLOW_OUTPUT_MEDIA` | `data/<omgeving>/output/archeomedia` (ook in Flask, schrijfbaar voor het kantelen) | `${WASSTRAAT_OUTPUT}/archeomedia` | synthetisch: `/tmp/archeomedia_test` (tmpfs-volume); Delft: schijfvolume op `/output/archeomedia` |
| `/output/rapporten` | `AIRFLOW_OUTPUT_RAPPORTEN` | `data/<omgeving>/output/rapporten` | `${WASSTRAAT_OUTPUT}/rapporten` | `/tmp/rapporten_test` in de container |
| `/opt/airflow/config` | `AIRFLOW_WASSTRAAT_CONFIG`, `AIRFLOW_CORRECTIES_CONFIG` | `data/<omgeving>/wasstraat_config` | `${WASSTRAAT_CONFIG}` (alleen-lezen) | `data/synthetic/wasstraat_config`, `data/test/wasstraat_config` |
| `/usr/local/apache2/htdocs` (Apache) | – | `data/<omgeving>/output` (alleen-lezen) | `${WASSTRAAT_OUTPUT}` (alleen-lezen) | het mediavolume onder `htdocs/archeomedia` |
| `/backup` (PostgreSQL, MongoDB) | – | `data/<omgeving>/backup/postgres`, `.../mongo` | `${WASSTRAAT_BACKUP}/postgres`, `.../mongo` | – |

`<omgeving>` is `synthetic` bij `make app` en `delft` bij `make delft`. Alleen `/output/archeomedia` wordt door Apache gepubliceerd (onder `/archeomedia`); alle andere verzoeken gaan door naar Flask, dus de rapporten in `output/rapporten` zijn niet via de browser te zien. Een eigen omgevingsnaam maak je door `docker-compose.delft.yml` te kopiëren en de paden aan te passen.

### 2.8 Poorten

| Service | Ontwikkelomgeving | Live installatie | Test (synthetisch) | Test (Delft) |
|---------|-------------------|------------------|--------------------|--------------|
| Apache (webapplicatie en media) | 5052 | `WASSTRAAT_PORT_APACHE` (5052) | 5061 | 5062 |
| Airflow | 8080 | `WASSTRAAT_PORT_AIRFLOW` (8080) | 8081 | 8082 |
| PostgreSQL | 5432 | `WASSTRAAT_PORT_POSTGRES` (5432, alleen lokaal) | geen | geen |
| MongoDB | 27017 | `WASSTRAAT_PORT_MONGO` (27017, alleen lokaal) | 27117 | 27118 |
| Elasticsearch | 9200 en 9300 | geen | geen | geen |
| Redis | 6379 | geen | geen | geen |
| Jupyter Lab | 8888 | geen | geen | geen |
| Flask | alleen `make dev`: 5051 | geen | geen | geen |
| debugpy (Airflow) | alleen `make dev`: 5678 | geen | geen | geen |

Flask heeft geen hostpoort: Apache is de voordeur en stuurt alles behalve `/archeomedia` door naar `flask:5051`. De twee testomgevingen hebben elk eigen hostpoorten en kunnen dus tegelijk draaien, ook naast een installatie; `tests/unit/test_testomgevingen_poorten.py` bewaakt dat. De integratietests vinden MongoDB via `MONGO_TEST_URI` (standaard poort 27117, in de Delftse tests 27118; `make integration-delft` zet hem op 27118).

### Wachtwoorden wijzigen

De databases en beheerders worden bij de eerste start aangemaakt met de wachtwoorden uit `config/`; daarna leest niemand die wachtwoorden opnieuw om ze in te stellen. Een gewijzigd wachtwoord in het bestand alleen breekt dus de verbinding. Wijzig daarom beide kanten:

| Wachtwoord | In de database of applicatie | In de bestanden |
|------------|------------------------------|-----------------|
| PostgreSQL, Airflow-gebruiker | `ALTER USER airflow WITH PASSWORD '...';` | `postgres.env` (`POSTGRES_PASSWORD`) en `airflow_db.env` (`DB__PASSWORD`) |
| PostgreSQL, Flask-gebruiker | `ALTER USER flask WITH PASSWORD '...';` | `postgres.env` (`FLASK_PGPASSWORD`) |
| MongoDB | `db.changeUserPassword('root', '...')` in de database `admin` | `mongo.env` |
| Redis | Geen data: alleen het bestand | `redis.env` |
| Airflow-beheerder | In de webinterface van Airflow (Your Profile) of met `airflow users reset-password` | Niet nodig; `SECURITY__ADMIN_PASSWORD` geldt alleen bij de eerste start |
| Flask-beheerder | In het gebruikersmenu van de webapplicatie | Niet nodig; `FLASK_ADMIN_PASSWORD` geldt alleen bij het aanmaken |

Maak de containers daarna opnieuw aan (`make app`, `make delft` of `make up`).

## 3. correcties.yml

`correcties.yml` bevat gemeente-specifieke datacorrecties en uitzonderingen die de pipeline toepast zonder dat de code verandert. Het bestand staat naast de harmonisatie-Excel:

| Omgeving | Bestand |
|----------|---------|
| Ontwikkelomgeving, synthetische data | `data/synthetic/wasstraat_config/correcties.yml` (met testgevallen voor elke sectie) |
| Ontwikkelomgeving, eigen data | `data/delft/wasstraat_config/correcties.yml` (de Delftse correcties) |
| Delftse testomgeving | `data/test/wasstraat_config/correcties.yml` |
| Live installatie | `deploy/wasstraat_config/correcties.yml` (sjabloon met lege lijsten en voorbeelden als commentaar) |

In de container is het pad `AIRFLOW_CORRECTIES_CONFIG` (standaard `/opt/airflow/config/correcties.yml`).

**Inlezen en fouten.** De pipeline leest het bestand met `harmonize_functions.laadCorrecties()`, één keer per taak (het resultaat wordt binnen de taak gecachet). `artefact_niet_mergen` en de filterpatronen van de afbeeldingen lezen het bestand zelf in, met dezelfde regels, en `importMDB.sh` leest `paden_overslaan` via het script `airflow_app/scripts/paden_overslaan.py`. Voor het hele bestand geldt:

- ontbreekt het bestand, dan zijn er geen correcties (logregel `Geen correctiebestand gevonden`);
- ongeldige YAML of een bestand dat geen YAML-dictionary is: een foutmelding in het log en geen enkele correctie;
- een sectie die ontbreekt of leeg is (`[]`), doet niets;
- een ongeldige regel binnen een sectie wordt met een melding overgeslagen; de andere regels en secties werken gewoon.

Een fout in `correcties.yml` stopt de pipeline dus nooit, met één uitzondering: kan `importMDB.sh` de lijst met over te slane databases niet bepalen, dan stopt het met een `ERROR`, omdat de kopieën anders stil zouden worden ingelezen.

| Sectie | Toegepast in | Vorm | Standaard |
|--------|--------------|------|-----------|
| [`brondata_correcties`](#31-brondata_correcties) | Transform 1, taak `FixProjectNames`, vóór de harmonisatie | lijst van regels met `collectie`, `zoek_veld`, `patroon`, `waarde` (en optioneel `doel_veld`) | geen correcties |
| [`projectcode_correcties`](#32-projectcode_correcties) | Transform 2, taak `Enhance_All_Attributes`, op `Single_Store` | lijst van regels met `patroon` en `projectcode` | geen correcties |
| [`artefact_niet_mergen`](#33-artefact_niet_mergen) | Transform 5, samenvoegen van artefacten | dictionary met de lijst `projectcodes` | alle projecten worden samengevoegd |
| [`rapportcode_prefixen`](#34-rapportcode_prefixen) | Extractie (selectie van bestanden) en Transform 1 (`ParseFotobestanden`) | lijst van regels met `prefix` en `type` | geen rapportherkenning op naam |
| [`paden_overslaan`](#35-paden_overslaan) | Extractie en registratie van bronbestanden | lijst van glob-patronen | niets overgeslagen |
| [`harmonisatie_voorrang`](#36-harmonisatie_voorrang) | Transform 1, taken `Harmonize_<soort>` | dictionary van tabelnaam naar soort (of leeg) | de voorrangsregel, met een waarschuwing |

### 3.1 brondata_correcties

Corrigeert ruwe velden in de staging, vóór de harmonisatie. Nodig als een bron een afwijkende waarde heeft die later niet meer goed te koppelen is, zoals een projectcode die niet in de projectenlijst staat, of een database die in de verkeerde projectmap staat.

```yaml
brondata_correcties:
  # De monsterdatabase gebruikt een oude code voor DC039
  - collectie: COLL_STAGING_MONSTER
    zoek_veld: PROJECT
    patroon: "SCHE"
    waarde: "DC039"
  # Alle rijen uit de databases in deze map horen bij DC027
  - collectie: COLL_STAGING_OUD
    zoek_veld: mdbfile
    doel_veld: project
    patroon: "DC027_Voorstraat"
    waarde: "DC027"
```

| Sleutel | Verplicht | Betekenis |
|---------|-----------|-----------|
| `collectie` | ja | De naam van een collectieconstante uit `shared/config.py` voor een collectie in de staging-database, zoals `COLL_STAGING_OUD` (opgravingsdatabases), `COLL_STAGING_PROJECTENLIJST`, `COLL_STAGING_MAGAZIJNLIJST`, `COLL_STAGING_FOTOLIJST`, `COLL_STAGING_MONSTER`, `COLL_STAGING_RAPPORTEN` of `COLL_PLAATJES`. Een onbekende naam geeft een waarschuwing en de regel wordt overgeslagen |
| `zoek_veld` | nee | Het veld waarop het patroon wordt toegepast: een kolomnaam uit de Access-tabel (zoals ze in de staging staat) of een van de velden die `importMDB.sh` toevoegt (`table`, `projectcd`, `mdbfile`, `bron`, `loadtime`). Zonder `zoek_veld` geldt `veld` (oude schrijfwijze, nog in de synthetische data) en anders `projectcd` |
| `doel_veld` | nee | Het veld dat de nieuwe waarde krijgt; standaard het `zoek_veld` |
| `patroon` | ja | Reguliere expressie (MongoDB `$regex`, hoofdlettergevoelig, niet verankerd: `"SCHE"` treft ook `SCHE2`; gebruik `^` en `$` voor een exacte waarde) |
| `waarde` | ja | De nieuwe waarde, altijd als tekst opgeslagen |

Elke regel wordt uitgevoerd als `update_many` op de hele collectie; het log van `FixProjectNames` noemt per regel het aantal gewijzigde documenten (`Brondata fix: ...`). Een regel zonder `collectie`, `patroon` of `waarde` geeft een foutmelding en wordt overgeslagen. Daarna zet de taak altijd numerieke projectcodes in `Staging_Projecten_Oud` en `Plaatjes` om naar tekst; dat hoort niet bij `correcties.yml`.

### 3.2 projectcode_correcties

Corrigeert het veld `projectcd` van alle geharmoniseerde documenten in `Single_Store`, na de harmonisatie en vóór de identificatie door het gemeenteprofiel. Gebruik dit voor afkortingen en oude codes die in meer bronnen voorkomen.

```yaml
projectcode_correcties:
  - patroon: "DC 16"       # reguliere expressie op projectcd
    projectcode: "DC016"   # nieuwe waarde
  - patroon: "^MONSTERS$"
    projectcode: "Onbekend"
```

| Sleutel | Verplicht | Betekenis |
|---------|-----------|-----------|
| `patroon` | ja | Reguliere expressie op `projectcd` (hoofdlettergevoelig, niet verankerd) |
| `projectcode` | ja | De nieuwe projectcode (als tekst) |

De regels worden in volgorde uitgevoerd, in beide cycli op de hele collectie. Het log van `Enhance_All_Attributes` noemt per regel het aantal gewijzigde documenten (`Projectcode fix: ...`); een onvolledige regel geeft een foutmelding en wordt overgeslagen. Het gemeenteprofiel normaliseert de code daarna nog (in Delft `dc16` → `DC016`, zie [Gemeenteprofielen](gemeenteprofielen.md#projectcode-normalisatie)); een correctie is dus alleen nodig voor codes die het profiel niet kan herleiden.

### 3.3 artefact_niet_mergen

Transform 5 voegt artefacten met dezelfde `key_subnr` (project, put, vondst en subnummer) en artefactsoort samen tot één artefact; de andere artefacten worden één op één verplaatst. Voor projecten in `artefact_niet_mergen` gebeurt dat samenvoegen niet: elke bronrij wordt een eigen artefact. Gebruik dit voor projecten waarin hetzelfde subnummer voor verschillende voorwerpen is gebruikt.

```yaml
artefact_niet_mergen:
  projectcodes: ["DC112"]
```

De projectcodes worden vergeleken met `projectcd` na Transform 2, dus in de genormaliseerde vorm (`DC112`, niet `dc112`). Is `artefact_niet_mergen` geen dictionary of `projectcodes` geen lijst, dan volgt een waarschuwing en geldt de sectie als leeg. De werking en de vaste uitzonderingen (de tabellen `ROMEINS AARDEWERK` en `ARTEFACT`) staan in [Transformatie: verplaatsen en samenvoegen van artefacten](transformatie.md#verplaatsen-en-samenvoegen-van-artefacten).

### 3.4 rapportcode_prefixen

Rapportnummers zoals `DAR045` (Delftse Archeologische Rapporten) en `DAN007` (Delftse Archeologische Notities) beginnen met een vaste letterreeks. Deze sectie legt die reeksen vast:

```yaml
rapportcode_prefixen:
  - prefix: "DAR"
    type: "archeologische_rapportage"
  - prefix: "DAN"
    type: "archeologische_notitie"
```

| Sleutel | Betekenis |
|---------|-----------|
| `prefix` | Letterreeks waarmee de bestandsnaam van een rapport begint, hoofdlettergevoelig |
| `type` | `archeologische_rapportage` (bestandsoort Archeologische Rapportage) of `archeologische_notitie` (Archeologische Notitie); hoofdletters en spaties eromheen maken niet uit. Een andere waarde is een fout (zie hieronder) |

De sectie werkt op twee plaatsen:

1. **Selectie van bestanden bij de extractie.** Uit de map met afbeeldingen en de map met rapporten neemt de extractie alleen bestanden met een ondersteunde extensie (`.jpg`, `.jpeg`, `.gif`, `.png`, `.tif`, `.psd`, `.pdf`, `.jp2`, `.doc`, `.docx`) waarvan het pad `velddocument`, `fotos` of `tekening` bevat (hoofdletterongevoelig) of een van de prefixen (hoofdlettergevoelig). Zonder prefixen worden rapporten buiten zulke mappen dus niet verwerkt.
2. **Herkenning in `ParseFotobestanden`.** Begint de bestandsnaam met een prefix gevolgd door twee of drie cijfers (spaties ertussen mogen), dan wordt het bestand een Rapport met rapportnummer `<prefix><nummer met drie cijfers>` (bijvoorbeeld `DAR 45.pdf` → `DAR045`) en key `R<rapportnummer>`.

Een regel zonder `prefix` of `type` wordt bij de herkenning genegeerd; een regel zonder `prefix` geeft bij de selectie een waarschuwing.

De herkenning controleert de sectie aan het begin van `ParseFotobestanden` (`harmonize_functions.leesRapportcodePrefixen`, toegestane waarden in `RAPPORT_TYPES`). Een regel met een onbekend `type`, zonder `type` of zonder `prefix` geeft een foutmelding in het log en een waarschuwing `configuratie_ongeldig` in het [verwerkingsrapport](verwerkingsrapport.md), en wordt overgeslagen: bestanden met dat prefix worden geen rapport (maar bijvoorbeeld een `Bestand`). De run gaat door. Tot issue 87 werd elk ander type stil een notitie. Bij de selectie telt alleen `prefix`; zo'n bestand wordt dus wel ingelezen.

### 3.5 paden_overslaan

Een lijst met bestanden en mappen die de extractie overslaat, zoals kopieën van databases en afbeeldingen in een werkmap. Zonder deze sectie leest de extractie elke Access-database onder een invoermap in, en geeft zo'n kopie dubbele artefacten, sporen en vondsten.

```yaml
paden_overslaan:
  - "DC024_Stadskantoor/K Overig/werkmap joris"   # één map, met alles daaronder
  - "**/werkmap*"                                 # elke map die met werkmap begint, op elk niveau
  - "DC097_Ipse/C Database/HHD2.mdb"              # één bestand
```

| Onderdeel | Regel |
|-----------|-------|
| Vorm | Glob-patroon. `/` scheidt mappen; een `\` telt ook als `/`. `*` staat voor een willekeurig deel van één naam (niet over een `/` heen), `?` voor één teken, `[abc]` en `[!abc]` voor een teken uit (of buiten) een reeks, `**` als hele naam voor nul of meer mappen |
| Waartegen | Het hele pad relatief aan de invoermap van het bestand: de projectmap (`AIRFLOW_INPUT_PROJECTEN`) voor de opgravingsdatabases, de mappen van de projectenlijst, magazijnlijst, fotolijst, monsterdatabase en rapporten voor hun databases, en de map met afbeeldingen (`AIRFLOW_INPUT_IMAGES`) en de map met rapporten voor de afbeeldingen en rapporten. In alle compose-bestanden is de map met afbeeldingen dezelfde als de projectmap, zodat één patroon zowel de databases als de afbeeldingen van een project dekt. Een `/` of `./` aan het begin en een `/` aan het eind worden genegeerd |
| Hele namen | Het patroon begint bij de invoermap en moet hele namen dekken: `DC024_Stadskantoor/K Overig/werkmap` slaat `werkmap joris` niet over, `DC024_Stadskantoor/K Overig/werkmap*` wel; `werkmap joris` alleen treft niets, `**/werkmap joris` wel |
| Mappen | Een patroon dat een map aanwijst, geldt voor alles daaronder |
| Hoofdletters | Ongevoelig |
| Fouten | Is de sectie geen lijst, dan volgt een foutmelding en wordt er niets overgeslagen. Een element dat geen niet-lege tekst of geen geldig patroon is (zoals `[]`), wordt met een waarschuwing weggelaten |
| Standaard | Geen sectie of een lege lijst: niets overgeslagen |

**Waar het geldt.** Eén instelling dekt alle brontypen, met dezelfde functie (`wasstraat/paden_overslaan.py`):

- de Access-databases in de zes MDB-mappen (`importMDB.sh`, in de incrementele cyclus ook de bestanden uit het lijstbestand);
- de registratie van bronbestanden (`Bepaal_Delta` in de incrementele cyclus, `Registreer_Bronbestanden` aan het eind van de volledige cyclus): een overgeslagen bestand wordt niet geregistreerd;
- de afbeeldingen en rapporten (`GetAndStoreImageFilenames`), ook als de bestandenlijst (`FILE_IMPORT_FILES_EXCEL`) ze noemt.

**Zichtbaarheid.** Elk overgeslagen bestand krijgt een regel in het log van de taak (`Overgeslagen volgens paden_overslaan (patroon '...'): <pad>`), gevolgd door een telling per invoermap. Het run-document krijgt `paden_overgeslagen` (per categorie de paden, hoogstens 1.000) en `tellingen.paden_overgeslagen`; het [verwerkingsrapport](verwerkingsrapport.md) noemt ze als bestanden met status `overgeslagen` en reden `paden_overslaan (correcties.yml)`.

**Wijzigen.** Een nieuw patroon werkt ook in de incrementele cyclus: een al geregistreerd bestand dat erbuiten valt, geldt daar als verwijderd en zijn rijen worden opgeruimd; haal je een patroon weg, dan gelden de bestanden als nieuw. Na een grotere wijziging is de volledige cyclus de veilige weg. Meer achtergrond en de Delftse aantallen staan in [Extractie: paden overslaan](extractie.md#paden-overslaan).

**Delft: tussenversies van een database (issue 86).** Naast de werkmap van Joris slaat de Delftse configuratie twee losse bestanden over, tussenversies van `opgravingDC97.mdb` in DC097:

```yaml
paden_overslaan:
  - "DC024_Stadskantoor/K Overig/werkmap joris"
  - "DC097_Ipse/C Database/HHD2.mdb"
  - "DC097_Ipse/C Database/dc79a1.mdb"
```

Het pad begint bij de projectmap (niet bij `projecten/`). Samengevoegde artefacten en vondsten van DC097 verliezen zo twee van hun drie bronrijen; ze houden hun nummer via hun key, die niet verandert. Rijen die alleen in de tussenversies stonden (115 artefacten, 182 sporen, 196 vullingen) vervallen bij de eerstvolgende volledige cyclus.

### 3.6 harmonisatie_voorrang

Bepaalt welke soort een Access-tabel harmoniseert als de patronen van meer dan één soort in de [harmonisatie-Excel](#4-harmonisatie-excel) hem selecteren, en welke tabellen door geen enkele soort worden geharmoniseerd. Zonder deze keuze schreven de parallelle taken `Harmonize_<soort>` hetzelfde document om beurten weg en won de taak die het laatst klaar was, per run anders (issue 89: `AW1DeterminatiesJohan` werd de ene keer aardewerk met baksel, decoratie en ABR-materiaal, de andere keer een kaal artefact).

```yaml
harmonisatie_voorrang:
  AW1DeterminatiesJohan: Aardewerk   # door Aardewerk ("AW1.*"), niet door Artefact ("Determinaties")
  "CODES BAKSEL":                    # codetabel: door geen enkele soort
```

| Onderdeel | Regel |
|-----------|-------|
| Sleutel | De naam van de Access-tabel (veld `table` in de staging), precies en hoofdlettergevoelig. Zet een naam met een spatie, dubbele punt of alleen cijfers tussen aanhalingstekens |
| Waarde | De naam van een soort uit `meta.py` die de tabel selecteert, zoals `Aardewerk` of `Artefact`. Leeg (niets, `~`, `null` of `""`): door geen enkele soort, ook als maar één soort de tabel selecteert |
| Zonder instelling | De voorrangsregel: een specifieke artefactsoort (`Aardewerk`, `Glas`, `Metaal`, …) gaat vóór de algemene `Artefact`; verder de volgorde van de soorten in `wasstraat_model` in `meta.py` (`Put`, `Vlak`, `Spoor`, `Vulling`, `Stelling`, de artefactsoorten, `Artefact`, `Monster`, …). Elke tabel die meer dan één soort selecteert geeft dan een waarschuwing |
| Fouten | Is de sectie geen dictionary, dan geldt geen enkele instelling (foutmelding in het log). Een regel met een tabelnaam die geen tekst is of een waarde die geen tekst is (zoals een lijst) wordt met een foutmelding overgeslagen. Een soort die de tabel niet selecteert (of niet bestaat) wordt genegeerd: dan kiest de voorrangsregel, met een waarschuwing die de genegeerde instelling noemt |
| Standaard | Geen sectie of een lege sectie (`{}`): de voorrangsregel |

**Hoe het werkt.** Elke taak `Harmonize_<soort>` bepaalt bij de start met `distinct('table', ...)` op zijn staging-collectie welke tabellen de pipelines van de soorten op die collectie selecteren (de `$match`-fasen uit de Excel of `meta.py`), kiest per tabel die meer pipelines selecteren één soort en slaat in zijn eigen pipeline de tabellen over die een andere soort (of geen enkele) krijgen (`{$match: {table: {$nin: [...]}}}` vooraan). Alle taken komen zo tot hetzelfde besluit, onafhankelijk van de volgorde waarin ze draaien; in de incrementele cyclus geldt hetzelfde. Alleen pipelines die het `_id` van het staging-document schrijven kunnen elkaar overschrijven en doen mee: standplaatsen, plaatsingen en dozen maken uit één rij van de magazijnlijst elk een eigen document en tellen niet mee. De code staat in `wasstraat/harmonisatie_voorrang.py`.

**Zichtbaarheid.** Een tabel die meer soorten selecteren zonder instelling geeft een waarschuwing `tabel_dubbel_geselecteerd` in het run-document, met de tabel, de collectie, de kandidaten en de gekozen soort; de run gaat door. Alle besluiten, ook die uit deze sectie, staan in het [verwerkingsrapport](verwerkingsrapport.md) onder Kwaliteitsmeldingen ("Harmonisatie: tabellen bij meer dan één soort") en in het log van de taak van de gekozen soort (bij geen enkele soort: van de eerste kandidaat). Een instelling voor een tabel die geen enkele pipeline selecteert heeft geen effect en wordt niet gemeld.

**Delft.** In de Delftse staging selecteren twee pipelines dezelfde tabel bij alleen `AW1DeterminatiesJohan` (802 rijen uit `opgravingDB34.mdb`): `Aardewerk` via `AW1.*` en `Artefact` via `Determinaties`; `data/delft/wasstraat_config/correcties.yml` kiest `Aardewerk`. De codetabel `METAAL OPPERVLAK` staat in de projectenlijst, waar alleen de vaste pipelines van projecten (`OPGRAVINGEN`) en vindplaatsen (`VINDPLAATSEN`) draaien; geen enkele soort selecteert hem. De synthetische data en de Delftse testdata hebben geen dubbel geselecteerde tabellen.

**Delft: codetabellen (issue 75).** De tabellen `AARDEWERK 1&2 VOORWERP` (kolommen `CODE` en `VOORWERP`, 96 rijen) en `AARDEWERK 1 BAKSEL` (`CODE` en `BAKSEL`, 46 rijen) uit `opgravingDB34.mdb` zijn lijsten met codes, geen artefacten. Alleen `Aardewerk` selecteert ze (via `.*AARDEWERK.*`); een lege waarde sluit ze toch uit. Ze blijven als referentiedata in de staging:

```yaml
harmonisatie_voorrang:
  AW1DeterminatiesJohan: Aardewerk
  "AARDEWERK 1&2 VOORWERP":
  "AARDEWERK 1 BAKSEL":
```

De Delftse testdata (`data/test/wasstraat_config/correcties.yml`) sluit dezelfde twee tabellen uit. Andere tabellen die een artefactsoort selecteert en die alleen codes of omschrijvingen bevatten (in Delft `GLAS FUNCTIE`, `GLAS GLASSOORT` en `GLAS VOORWERP` uit `DC024_Stadskantoor/B Arcview/opgravingDC24.mdb`), worden nog als artefact geharmoniseerd.

**Wijzigen.** Een andere keuze verandert de soort (en bij artefacten de artefactsoort en de velden) van de documenten uit die tabel: draai daarna de volledige cyclus. Rijen die zo een andere artefactsoort krijgen, houden hun nummer in PostgreSQL (zie [Incrementeel laden](incrementeel-laden.md#andere-artefactsoort-door-de-harmonisatie-issue-89)).

### 3.7 Volledig voorbeeld

```yaml
# correcties.yml van een gemeente; alle secties zijn optioneel

brondata_correcties:            # Transform 1, op de ruwe staging
  - collectie: COLL_STAGING_MONSTER
    zoek_veld: PROJECT
    patroon: "^OUDECODE$"
    waarde: "AB001"

projectcode_correcties:         # Transform 2, op projectcd in Single_Store
  - patroon: "^AB 1$"
    projectcode: "AB001"

artefact_niet_mergen:           # Transform 5: elke bronrij een eigen artefact
  projectcodes: ["AB012"]

rapportcode_prefixen:           # extractie en ParseFotobestanden
  - prefix: "ABR"
    type: "archeologische_rapportage"

paden_overslaan:                # extractie en registratie
  - "AB001_Voorbeeldproject/K Overig/werkmap"
  - "**/oude kopie*"

harmonisatie_voorrang:          # Transform 1: welke soort een dubbel geselecteerde tabel harmoniseert
  ABDeterminaties: Aardewerk
  "AARDEWERK BAKSEL":           # codetabel: door geen enkele soort
```

Controleer na een run of de correcties werkten: de logs van `FixProjectNames` en `Enhance_All_Attributes` noemen per regel het aantal gewijzigde documenten, en het verwerkingsrapport noemt de overgeslagen paden en de voorrang bij de harmonisatie. `tests/unit/test_correcties_yml.py`, `tests/unit/test_paden_overslaan.py` en `tests/unit/test_harmonisatie_voorrang.py` toetsen het inlezen, de werking en de foutgevallen.

## 4. Harmonisatie-Excel

De harmonisatie-Excel vertaalt de tabel- en kolomnamen van de Access-databases naar het datamodel van de Wasstraat. Het is het belangrijkste configuratiebestand voor een nieuwe gemeente.

| Omgeving | Bestand |
|----------|---------|
| Ontwikkelomgeving | `data/synthetic/wasstraat_config/Wasstraat_Config_HarmonizeV3.xlsx` en `data/delft/wasstraat_config/Wasstraat_Config_HarmonizeV3.xlsx` |
| Delftse testomgeving | `data/test/wasstraat_config/Wasstraat_Config_HarmonizeV3.xlsx` (de andere Excel-bestanden in die map worden niet gebruikt) |
| Live installatie | `deploy/wasstraat_config/Wasstraat_Config_HarmonizeV3.xlsx` |

Op dit moment zijn de vier bestanden gelijk: de Delftse configuratie, die ook op de synthetische data past. In de container is het pad `AIRFLOW_WASSTRAAT_CONFIG`; die variabele heeft geen standaardwaarde en staat in `config/airflow.env.example`.

### Structuur

**Tabblad `Objecten`.** Eén rij per objecttype:

| Kolom | Betekenis | Voorbeeld |
|-------|-----------|-----------|
| `Object` | Naam van het objecttype; moet overeenkomen met een soort in `wasstraat/meta.py` | `Vondst`, `Aardewerk` |
| `Tabellen` | Lijst (in Python-notatie) met reguliere expressies op de naam van de Access-tabel | `["^VONDSTENLIJST", "^VONDST$", "^VELDVONDST"]` |
| `Overerven` | Objecttype waarvan de attributen eerst worden overgenomen | `Artefact` bij alle artefactsoorten |
| `ABR-materiaal`, `ABR-submateriaal` | URI's uit de ABR-thesaurus; worden de velden `abr_materiaal` en `abr_submateriaal` van elk artefact van die soort, en bepalen sinds issue 86 omgekeerd de artefactsoort van een artefact zonder soort met een ABR-materiaalcode (zie [Transformatie](transformatie.md)) | `https://data.cultureelerfgoed.nl/term/id/abr/...` |

De rij `Ignore` bevat patronen voor tabellen die nooit worden geharmoniseerd, bijvoorbeeld `.*backup.*`, `.*kopie.*`, `.*tijdelijk.*`, `^Soorten` en `^Ref_`.

**Attribuuttabbladen.** Per objecttype een tabblad met dezelfde naam, met de kolommen:

| Kolom | Betekenis | Voorbeeld |
|-------|-----------|-----------|
| `Attribute` | Veldnaam in het datamodel | `putnr` |
| `Kolommen` | Lijst met kolomnamen in de Access-tabellen, in volgorde van voorkeur: de eerste kolom met een waarde wint. Een waarde zonder `[...]` is een vaste waarde | `["PUT", "PUTNO"]` |

Andere kolommen (zoals `Opmerkingen` of een volgnummer) worden genegeerd.

### Hoe de pipeline hem leest

Transform 1 maakt per objecttype een taak `Harmonize_<soort>` (de soorten uit `meta.py`). Die leest de Excel met pandas (`harmonizer.loadHarmonizer`) en bouwt er een MongoDB-aggregatie van:

1. documenten uit de staging-collectie van de soort waarvan het veld `table` (de naam van de Access-tabel) **niet** op een patroon uit `Ignore` lijkt;
2. en **wel** op een patroon uit `Tabellen`. De patronen zijn hoofdletterongevoelig en niet verankerd: `VLAK` treft ook `VLAKKEN` en `SPOOR_VLAK`; gebruik `^` en `$` om dat te beperken. Selecteren de patronen van meer soorten dezelfde tabel, dan harmoniseert alleen de soort met voorrang hem (zie [harmonisatie_voorrang](#36-harmonisatie_voorrang));
3. het hele brondocument gaat naar het veld `brondata`, met hetzelfde `_id`;
4. de attributen van het `Overerven`-type en daarna die van het eigen tabblad worden gezet, elk als de eerste niet-lege kolom uit de lijst (`$ifNull`-keten);
5. `soort` wordt de naam van het object; artefactsoorten krijgen `soort: Artefact` en `artefactsoort: <object>`, plus de ABR-velden;
6. het resultaat wordt in `Single_Store` geschreven.

De taak leest de Excel elke keer opnieuw; een wijziging vraagt dus geen herstart, wel een **volledige cyclus** om alle data opnieuw te harmoniseren. Ontbreekt een soort uit `meta.py` in het tabblad `Objecten`, dan faalt zijn `Harmonize_`-taak met de melding dat het object niet in de Excel staat.

### Wat de Excel niet regelt

- **Vaste bronnen.** Projecten, vindplaatsen en het depot hebben een vaste pipeline in `meta.py` en vaste tabelnamen: `OPGRAVINGEN` (projecten) en `VINDPLAATSEN` in de projectenlijst, en `magazijnlijst`, `doosnr` en `stellingen` in de magazijnlijst. Foto's, tekeningen en rapporten komen uit de bestandsnamen (gemeenteprofiel en `rapportcode_prefixen`) en uit de fotocatalogus (`Fotokoppel`, `Fotobeschrijving`).
- **Nieuwe objecttypen.** Een nieuwe rij in `Objecten` zonder soort in `meta.py` wordt genegeerd. Een nieuwe artefactsoort vraagt een codewijziging: een constante in `shared/const.py`, de lijst `lst_artefactsoort` in `meta.py`, de enum `DiscrArtefactsoortEnum` en een subklasse in `app/app/models.py`, en een tabblad in de Excel.
- **Waarden.** De Excel kiest velden, geen waarden. Opschonen en omzetten van waarden (datums, nummers, coördinaten) gebeurt in Transform 2 en het gemeenteprofiel; foute waarden in de brondata corrigeer je met [`correcties.yml`](#3-correctiesyml).

Een stappenplan voor het aanpassen aan je eigen databases staat in [Aan de slag, stap 5](../aan-de-slag.md#5-wasstraat_config_harmonizev3-configureren).

## 5. Gemeenteprofiel

Het gemeenteprofiel bevat de gemeente-specifieke logica die niet als configuratie te vangen is: het normaliseren van projectcodes, tekeningcodes en rapportnummers, en het lezen van bestandsnamen van foto's en tekeningen. De keuze gebeurt met `WASSTRAAT_GEMEENTE`:

| Waarde | Profiel |
|--------|---------|
| `delft` (standaard, ook als de variabele leeg is) | `DelftProfiel`: Delftse projectcodes (`DC016`), tekeningcodes (`B002`), rapportnummers (`DAR045`) en bestandsnamen (`DC001_P3_H456_789_002.jpg`) |
| `voorbeeld` | `VoorbeeldProfiel`: neemt de velden ongewijzigd over (de conventie) en herkent geen bestandsnamen |

Hoofdletters en spaties maken niet uit. Een onbekende waarde laat `Start_Run` van elke DAG direct falen (cruciale fout, melding `profiel_onbekend` met de bekende profielen; issue 87), en ook de losse DAG's voor Transform 1 en 2. Zet de variabele in `docker-compose.delft.yml` (ontwikkelomgeving) of `deploy/.env` (live installatie), maak de Airflow-container opnieuw aan en draai de volledige cyclus. Een eigen profiel is een codewijziging; zie [Gemeenteprofielen](gemeenteprofielen.md).

## 6. Live installatie

De live installatie in `deploy/` draait op de gepubliceerde images en heeft drie plekken voor configuratie:

| Plek | Inhoud | Aangemaakt door |
|------|--------|-----------------|
| `deploy/.env` | Versie, gemeenteprofiel, mappen, poorten, geheugen van Elasticsearch ([tabel](#26-instellingen-in-de-compose-bestanden)) | `make init`, uit `.env.example` |
| `deploy/config/*.env` | Wachtwoorden en instellingen van de services, zoals in de ontwikkelomgeving (zonder Jupyter) | `make init`, via `init-config.sh` |
| `deploy/wasstraat_config/` | Harmonisatie-Excel en `correcties.yml` (sjabloon zonder correcties) | in de map meegeleverd |

Verschillen met de ontwikkelomgeving: de brondata en `wasstraat_config/` zijn alleen-lezen gekoppeld, er zijn geen volumes naar broncode, Elasticsearch en Redis hebben geen hostpoort en de databases luisteren standaard alleen op `127.0.0.1`. De versie staat in `WASSTRAAT_VERSION` en komt ook in het verwerkingsrapport. Zie [Installatie met images](../deployment/installatie-met-images.md) voor de stappen.

## 7. Pakketversies

De Python-pakketten van de Airflow-, Flask- en Jupyter-image liggen vast, zodat een nieuwe build dezelfde, geteste versies oplevert:

| Bestand | Inhoud |
|---------|--------|
| `services/airflow/requirements.txt`, `services/flask/requirements.txt` | De directe pakketten met ruime grenzen (bij Jupyter staan ze in de Dockerfile) |
| `services/airflow/constraints.txt`, `services/flask/constraints.txt`, `services/jupyter/constraints.txt` | De exacte versies, gegenereerd; niet met de hand bijwerken |

De build stopt als de geïnstalleerde versies afwijken van `constraints.txt`. De Airflow-build houdt bovendien alle pakketten van de basisimage `apache/airflow:2.10.5-python3.11` op hun versie; pip mag alleen toevoegen. Bijwerken:

```bash
make constraints                       # alle drie; of: bash scripts/leg_pakketversies_vast.sh flask
git diff services/*/constraints.txt
docker compose -p wasstraat-test -f docker-compose.test.yml build --no-cache --pull
make test-all
```

Zie [Testen: pakketversies bijwerken](../testen.md#pakketversies-bijwerken) voor de achtergrond.

## 8. Versienummer en releases

| Bestand | Inhoud | In de repository |
|---------|--------|------------------|
| `config/version.env.example` | `VERSION=<versie>`, de standaard | ja |
| `config/version.env` | Lokale kopie, gemaakt door `init-config.sh` | nee (`*.env`) |
| `deploy/.env.example` | `WASSTRAAT_VERSION=<versie>`, de standaard voor nieuwe installaties | ja |

`make publish` gebruikt de versie uit `config/version.env` (anders uit het sjabloon) als tag van de images; `VERSION=x.y.z` op de commandoregel gaat voor. `make release VERSION=1.2.3 MSG="..."` schrijft de versie in de drie bestanden, staget alleen `config/version.env.example` en `deploy/.env.example`, commit, maakt een geannoteerde tag, pusht de huidige branch en de tag, en publiceert de images. `tests/unit/test_deploy.py` eist dat `deploy/.env.example` en `config/version.env.example` dezelfde versie noemen.

Het verwerkingsrapport vermeldt de versie als die in de Airflow-container bekend is: eerst `WASSTRAAT_VERSION`, anders de regel `VERSION=` uit `WASSTRAAT_VERSIEBESTAND` (standaard `/opt/airflow/version.env`). In de live installatie zet `deploy/docker-compose.yml` `WASSTRAAT_VERSION` uit `deploy/.env`. In de ontwikkelomgeving geven `make app`, `make delft` en `make dev` de versie uit `config/version.env` (anders `config/version.env.example`, dezelfde regel als `make publish`) als `WASSTRAAT_VERSION` mee; `docker-compose.yml` en `docker-compose.delft.yml` zetten die in de Airflow-container. Start je de ontwikkelomgeving met `docker compose up` zonder de Makefile, dan is `WASSTRAAT_VERSION` leeg en ontbreekt de versie in het rapport (tenzij je hem zelf meegeeft: `WASSTRAAT_VERSION=1.2.1 docker compose up -d`). De testomgevingen zetten geen versie. Publiceren en releases staan in [Omgevingen: publicatie van images](../deployment/omgevingen.md#publicatie-van-images).

## 9. Veelvoorkomende configuratietaken

| Taak | Waar en hoe |
|------|-------------|
| Eigen brondata verwerken (ontwikkelomgeving) | Bestanden in `data/delft/data/`, configuratie in `data/delft/wasstraat_config/`, starten met `make delft` |
| Brondata op een andere schijf (live installatie) | `WASSTRAAT_INPUT` in `deploy/.env`, daarna `make up` |
| Andere poort voor de webapplicatie | `WASSTRAAT_PORT_APACHE` in `deploy/.env`; in de ontwikkelomgeving de poort van `apache` in het compose-bestand |
| Alleen lokaal bereikbaar, achter een reverse proxy | `WASSTRAAT_BIND=127.0.0.1` in `deploy/.env` |
| Meer geheugen voor Elasticsearch | `WASSTRAAT_ES_GEHEUGEN=2g` in `deploy/.env` |
| Een werkmap met kopieën overslaan | `paden_overslaan` in `correcties.yml`, daarna de volledige of de incrementele cyclus |
| Een tabel die de patronen van twee soorten selecteren aan één soort toewijzen, of een codetabel niet harmoniseren | `harmonisatie_voorrang` in `correcties.yml` (de waarschuwing `tabel_dubbel_geselecteerd` noemt tabel en kandidaten), daarna de volledige cyclus |
| Een verkeerde projectcode corrigeren | `brondata_correcties` (één bron) of `projectcode_correcties` (alle bronnen), daarna de volledige cyclus |
| Een kolomnaam van een eigen database herkennen | Kolomnaam toevoegen aan de lijst `Kolommen` in de harmonisatie-Excel, daarna de volledige cyclus |
| Meer mislukte foto's toestaan | `AIRFLOW_MAX_MISLUKTE_AFBEELDINGEN` en `_PCT` in `config/airflow.env`, Airflow-container opnieuw aanmaken |
| Elke onleesbare database als fout behandelen | `AIRFLOW_MAX_MISLUKTE_DATABASES=0` en `AIRFLOW_MAX_MISLUKTE_DATABASES_PCT=0` |
| Rapporten naar een andere map | `AIRFLOW_OUTPUT_RAPPORTEN` in `config/airflow.env` en een mount naar dat pad |
| Ander gemeenteprofiel | `WASSTRAAT_GEMEENTE`, Airflow-container opnieuw aanmaken, volledige cyclus |
| Airflow via een andere naam of poort (links in logs en meldingen) | `AIRFLOW__WEBSERVER__BASE_URL` in `config/airflow.env`, Airflow-container opnieuw aanmaken |
| Mail zonder TLS | `MAIL_USE_TLS=False` in `config/flask.env`, Flask-container opnieuw aanmaken |
