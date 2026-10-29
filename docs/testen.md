# Testen

De Wasstraat heeft een testsuite met twee niveaus: unit tests voor individuele functies en integratietests die de volledige verwerkingspipeline testen met echte databases in Docker.

## Quickstart

```bash
make install          # eenmalig: maakt .venv aan met alle dependencies
make test             # draai unit tests
make integration      # integratietests met synthetische voorbeelddata
make integration-delft # integratietests met Delftse data (indien aanwezig)
make test-all         # unit + integratietests
```

Typ `make help` voor alle beschikbare targets.

## Structuur

```
Makefile                                      # Alle commando's (make help)
requirements-test.txt                         # Python test-dependencies
pytest.ini                                    # Markers en standaardopties
docker-compose.test.yml                       # Testomgeving met synthetische data (SY001, SY002)
docker-compose.delft-test.yml                 # Testomgeving met Delftse testdata (DB034)
tests/
├── conftest.py                               # Mocks voor shared.config, roman, etc.
├── run_tests.py                              # Fallback runner (zonder venv/pytest)
├── unit/                                     # Unit tests, zie de tabel hieronder
│   └── nep_mongo.py                          # In-memory nabootsing van pymongo (hulpmodule, geen tests)
└── integration/
    ├── fixtures/delft_golden_snapshot.json   # Referentie-uitkomst van de Delftse testdata
    ├── snapshot_mongodb.py                   # Hulpmiddel om een referentie-uitkomst vast te leggen
    ├── test_full_pipeline.py                 # Pipeline met directe MongoDB-seeding
    ├── test_full_pipeline_synthetic_data.py  # Volledige pipeline via Airflow (synthetische data)
    ├── test_full_pipeline_delft_data.py      # Volledige pipeline via Airflow (Delftse data)
    ├── test_harmonize_pipeline.py            # Harmonisatie met echte MongoDB
    ├── test_importMDB_bash.py                # MDB-import en encoding in Docker
    ├── test_incremental_synthetic_data.py    # Volledige en incrementele cyclus (synthetische data + SY003)
    ├── test_verwerkingsrapport.py            # Foutbeleid en verwerkingsrapport in de echte DAG's
    └── test_flask_smoke.py                   # Webapplicatie via Apache
```

## Vereisten

Bij `make install` wordt automatisch een `.venv` aangemaakt met Python 3.11 (of 3.12/3.10 als fallback) en worden alle dependencies uit `requirements-test.txt` geïnstalleerd. Je hoeft zelf geen venv aan te maken.

De integratietests hebben daarnaast Docker nodig.

## Unit tests

```bash
make test       # uitgebreide output
make test-quick # korte output
```

Of handmatig:

```bash
source .venv/bin/activate
python -m pytest tests/unit/ -v
python -m pytest tests/unit/test_archutils.py -v   # één module
```

### Fallback zonder venv

Als je geen venv wilt of kunt gebruiken en de basispackages (pandas, numpy, openpyxl) al beschikbaar zijn:

```bash
python3 tests/run_tests.py
```

## Integratietests

### Standaard: synthetische data

```bash
make integration
```

Dit target gebruikt de **synthetische voorbeelddata** uit `data/synthetic/data/`. De tests controleren dat de volledige ETL-pipeline (Extract → Transform → Load) correct werkt met de meegeleverde fictieve opgravingsprojecten SY001 en SY002.

Het target:

1. Maakt de `.venv` aan als die nog niet bestaat
2. Start MongoDB 7.0, PostgreSQL 18 met PostGIS, Elasticsearch 8.17, Redis, Airflow, Flask en Apache in Docker (MongoDB, PostgreSQL en het mediavolume in tmpfs voor snelheid)
3. Mount de synthetische data als input-volumes
4. Triggert de Airflow DAGs (Extract, Transform, Load en indexering) en valideert de resultaten
5. Controleert verwachte aantallen per entiteitstype (sporen, vondsten, artefacten) in MongoDB en PostgreSQL
6. Draait de volledige en daarna de incrementele cyclus (`test_incremental_synthetic_data.py`, zie hieronder)
7. Draait de Flask smoke tests via Apache tegen de geladen database, inclusief de media uit het gedeelde mediavolume
8. Ruimt de containers en volumes op

### Elasticsearch in de testomgeving

Beide testomgevingen hebben een eigen Elasticsearch (`elasticsearch-test`; container `wasstraat_elasticsearch_test` in `docker-compose.test.yml` en `wasstraat_elasticsearch_delft_test` in `docker-compose.delft-test.yml`; image `docker.elastic.co/elasticsearch/elasticsearch:8.17.0`, zonder beveiliging, single-node, 512 MB heap). Airflow en Flask bereiken die via `ES_HOST=http://elasticsearch:9200`. Airflow start pas als Elasticsearch gezond is (healthcheck met `depends_on: condition: service_healthy`). De Index_*-taken van de volledige cyclus, van `DAG_Load_Only` en van de incrementele cyclus slagen daardoor ook in de testomgeving; `test_full_pipeline_synthetic_data.py` en `test_full_pipeline_delft_data.py` eisen dat `DAG_Load_Only` volledig slaagt, en de Delftse test vergelijkt daarna per geïndexeerde tabel het aantal documenten in Elasticsearch met het aantal rijen in PostgreSQL.

De container heeft bewust geen hostpoort: poort 9200 op de host is van de echte installatie. Tests benaderen Elasticsearch via `docker exec wasstraat_elasticsearch_test curl -s http://localhost:9200/...` (Delft: `wasstraat_elasticsearch_delft_test`).

### Apache in de testomgeving

Net als in de echte installatie is Apache de voordeur: `apache-test` (container `wasstraat_apache_test`, gebouwd uit `services/apache/Dockerfile`) luistert op hostpoort 5061, serveert `/archeomedia` en stuurt al het overige door naar `flask-test`, dat geen hostpoort heeft (netwerkalias `flask`, zoals `httpd.conf` verwacht). De media die `airflow-test` schrijft (`AIRFLOW_OUTPUT_MEDIA=/tmp/archeomedia_test`) staan in het volume `archeomedia-test`, een tmpfs-volume met de uid van de airflow-gebruiker, dat `apache-test` alleen-lezen mount onder `htdocs/archeomedia`.

De Flask smoke tests (`tests/integration/test_flask_smoke.py`, marker `flask_smoke`) lopen daardoor via Apache. Naast de kaart, het inloggen en de statische bestanden controleren ze dat een media-URL uit `Def_Bestand` via Apache 200 geeft (alle drie formaten van alle foto's), dat paden met spaties en diakritische tekens werken, dat redirects de `Host`-header van de browser en `X-Forwarded-Proto` van een TLS-proxy volgen, en dat `/archeomedia/` niet te bladeren is. Klasse `TestVerdwenenUitBrondata` maakt met SQL een bruikleen en een conserveringsproject aan waarvan het artefact uit de brondata is verdwenen (lege verwijzing met markering) en vraagt als beheerder de lijst en het detail van de bruiklenen en het detail van het conserveringsproject op: HTTP 200 en de markering in de pagina. Klasse `TestProjectZonderLocatie` maakt via de formulieren (inloggen, CSRF-token) projecten aan zonder locatie, maakt bij bewerken een locatie leeg en controleert in PostgreSQL dat `location` leeg is; Flask-AppBuilder stuurt na opslaan ook bij een databasefout door, dus de redirect alleen zegt niets. Klasse `TestFotoKantelen` maakt in de Flask-container een liggende foto en een liggende pdf met hun voorbeelden, kantelt ze via de knop op de detailpagina en via de selectie in de lijst, en meet via Apache de afmetingen en de stand van de inhoud van alle drie de formaten (en `/Rotate` in de pdf). Daarvoor koppelt `docker-compose.test.yml` het mediavolume ook schrijfbaar in `flask-test` op `/output/archeomedia`; zonder dat volume slaan die tests over. `make test-flask` start de omgeving zonder pipeline; de mediatests slaan dan over. De Delftse testomgeving (`docker-compose.delft-test.yml`) heeft dezelfde opzet op hostpoort 5062, maar met een gewoon schijfvolume (`archeomedia-delft-test`) op `/output/archeomedia` in plaats van tmpfs: de Delftse testdata bevat circa 5 GB aan rapporten die de extractie integraal naar de mediamap kopieert, en in een vol tmpfs mislukt de verwerking van de overige bestanden stil (ze blijven op `processed: False` staan). De Airflow-image maakt `/output/archeomedia` aan met de airflow-gebruiker als eigenaar, zodat een leeg named volume die rechten overneemt. Heb je een test-image van vóór deze wijziging, bouw hem dan opnieuw met `docker compose -p wasstraat-delft-test -f docker-compose.delft-test.yml build airflow-test`. De unit tests in `tests/unit/test_apache_voordeur.py` bewaken de Apache-configuratie en de compose-bestanden.

### Incrementele cyclus

`tests/integration/test_incremental_synthetic_data.py` (markers `integration` en `load`, draait in `make integration` na de andere tests) begint zelf met de volledige cyclus, controleert daarna de incrementele cyclus in negen runs (c tot en met h2) en draait tot slot opnieuw de volledige cyclus (i). Na elke run controleert de test ook het run-document en het verwerkingsrapport (zie [Incrementeel laden](componenten/incrementeel-laden.md#testen)):

| Stap | Wijziging | Wat wordt gecontroleerd |
|------|-----------|-------------------------|
| a | Volledige cyclus | Aantallen per `Def_`-tabel, `key` → `primary_key` van `Def_Project`, `Def_Put`, `Def_Vondst`, `Def_Artefact`, `Def_Bestand` en de aantallen per Elasticsearch-index (gelijk aan de tabellen) worden vastgelegd |
| b | Een partij en een bruikleen toegevoegd (SQL) | Gebruikersdata die naar een artefact en het project SY002 verwijst |
| c | Geen | Run afgerond, alle bronbestanden ongewijzigd, niets ingevoegd, bijgewerkt of verwijderd, aantallen en sleutels gelijk, bruikleen aanwezig, Elasticsearch gelijk; elke rij van elke tabel heeft dezelfde `primary_key` |
| c2 | De registratie van `opgravingSY002.mdb` krijgt een andere vingerafdruk (SQL), zodat de database ongewijzigd opnieuw wordt verwerkt | Alle documenten van SY002 hebben een nieuw `_id`; Transform 4 deelt geen nieuw nummer uit (artefacten zonder subnr en de dubbele key `PSY002P1V1A2|Aardewerk` via de hulpsleutel), niets ingevoegd of verwijderd, elke rij van elke tabel heeft dezelfde `primary_key`, key en hulpsleutel, de bruikleen blijft gekoppeld |
| d | Project SY003 als kopie van SY002 (`opgravingSY003.mdb`, foto's `SY003_*`); daarna een tweede bruikleen (SQL) voor een artefact van SY003 dat in stap e verdwijnt | SY003 heeft evenveel rijen als SY002, nieuwe `primary_key`s boven het oude maximum, SY001/SY002 ongewijzigd, bruikleen en zijn artefact ongewijzigd, Elasticsearch gelijk aan de tabellen |
| e | Database van SY003 vervangen door die van SY001, één foto verwijderd | SY003 volgt SY001 (4 vondsten, plus de put en vondst die Transform 5 aanmaakt voor de objectfoto `SY003_P4_H11_1_1.jpg`), geen rij meer voor de verwijderde foto, geen achtergebleven rijen, verdwenen id's ook uit Elasticsearch; de bruikleen van het verdwenen artefact bestaat nog met `artefactID` leeg, de key in `artefact_verdwenen_key` en een tijdstip binnen de run in `artefact_verdwenen_op`, de bruikleen uit stap b is ongemoeid en geen enkele FK is `NOT VALID` (`pg_constraint.convalidated`) |
| e2 | Database van SY003 weer die van SY002 | Het artefact keert terug met dezelfde key (nieuwe `primary_key`); de bruikleen is er weer aan gekoppeld en de markering is leeg (`tellingen.gebruikersdata`: één teruggekoppeld), FK's geldig |
| f | SY003 verwijderd | Geen SY003-rijen meer in PostgreSQL en Elasticsearch, `Def_Bronbestand` op `verwijderd`, alle sleutels en aantallen gelijk aan stap a; de bruikleen van het SY003-artefact is weer losgekoppeld en bestaat nog, FK's geldig |
| g | Een onleesbare foto in SY003, met drempel 0 voor mislukte afbeeldingen | `Extract_Group.Controleer_Afbeeldingen` faalt direct (zonder herhaling), `Markeer_Run_Mislukt` zet de run op `mislukt`, PostgreSQL is ongewijzigd; het rapport noemt de taak die de run stopte en de foto |
| h | De foto weer weggehaald | De run slaagt, de openstaande entry in `Filenames` is opgeruimd, alles gelijk aan stap a |
| h2 | Een onleesbare Access-database in SY003 (`kapot.mdb`) | `Extract_Group.Controleer_Databases` meldt een waarschuwing binnen de drempel, de run slaagt, het rapport noemt de database als mislukt met de reden, PostgreSQL gelijk aan stap a |
| i | Opnieuw de volledige cyclus (met de onleesbare database uit h2, dus met een waarschuwing), na een conserveringsproject met een regel en een extra ABR-materiaal (SQL) voor het artefact van de bruikleen | De inhoud van alle gebruikerstabellen is ongewijzigd (ook de losgekoppelde bruikleen van SY003), de bruikleen hangt aan hetzelfde artefact; aantallen, sleutels, Elasticsearch-aantallen en afgeleide velden gelijk aan stap a; geen melding van hernummerde sleutels, geen FK `NOT VALID`, elke sequence boven het maximum; elke rij van elke tabel uit `LOAD_TABELLEN` heeft dezelfde `primary_key` als na stap a |

De fixture `sy003_opruimen` verwijdert `data/synthetic/data/projecten/SY003` vóór en na de test, ook als die faalt, en ruimt achteraf de testgebruikersdata op (partij, bruiklenen, conserveringsproject en het extra ABR-materiaal). De test duurt ongeveer drie minuten. Los draaien (met een draaiende testomgeving):

```bash
python -m pytest tests/integration/test_incremental_synthetic_data.py -v -s
```

!!! warning "Images worden niet opnieuw gebouwd"
    `make integration` start de test-containers met de images die al op je machine staan. Wijzigingen in een Dockerfile, in `requirements.txt` of `constraints.txt`, of in `shared/` (die in de Flask-image wordt gekopieerd) zie je pas na een nieuwe build. De Flask- en Airflow-pakketten blijven bij een nieuwe build op de vastgelegde versies (zie [Pakketversies bijwerken](#pakketversies-bijwerken)). Bouw de images daarom opnieuw na zulke wijzigingen, en zonder cache als je een schone installatie wilt nabootsen:
    ```bash
    docker compose -p wasstraat-test -f docker-compose.test.yml build --no-cache --pull
    ```

### Delft-specifiek: echte data

```bash
make integration-delft
```

Dit target test met de echte Delftse opgravingsdata en controleert op Delft-specifieke aantallen. De Delftse data is niet opgenomen in de repository — deze tests worden automatisch overgeslagen als de data niet aanwezig is in `data/test/`.

Daarnaast legt `tests/integration/fixtures/delft_golden_snapshot.json` een referentie-uitkomst vast: de aantallen per soort in `Single_Store` en `Single_Store_Clean`, de artefactsoorten en voorbeeldsleutels. Geen test leest dat bestand automatisch. Raakt een wijziging de Delftse uitkomst, vergelijk de nieuwe uitkomst dan met de referentie, verklaar elk verschil en leg de referentie opnieuw vast, met de verklaring in het veld `beschrijving`. Voor een vergelijking van de aantallen per collectie in MongoDB is er `tests/integration/snapshot_mongodb.py` (`save` en `compare`).

### Handmatig

```bash
docker compose -p wasstraat-test -f docker-compose.test.yml up -d

source .venv/bin/activate
MONGO_TEST_URI="mongodb://testroot:testpass@localhost:27117/" \
python -m pytest tests/integration/ -v -m integration

docker compose -p wasstraat-test -f docker-compose.test.yml down -v
```

## Pakketversies bijwerken

De Flask-, de Jupyter- en de Airflow-image installeren hun Python-pakketten met vaste versies uit `services/flask/constraints.txt`, `services/jupyter/constraints.txt` en `services/airflow/constraints.txt`. Een verse build levert zo dezelfde versies op als de build waarmee de tests geslaagd zijn. De `requirements.txt` van Flask en Airflow bevatten alleen de directe pakketten, met ruime grenzen; bij Jupyter staan ze in de pip-opdracht van de Dockerfile.

- **Flask** bouwt op `python:3.11-slim-bookworm`. Daarom staan in `constraints.txt` alle pakketten, ook de afgeleide pakketten die pip zelf meeneemt.
- **Jupyter en Airflow** bouwen voort op een basisimage die haar eigen versies vastlegt: Jupyter op een digest, Airflow via de constraints waarmee `apache/airflow:2.10.5-python3.11` is gebouwd. In hun `constraints.txt` staat alleen wat pip bovenop de basisimage installeert of wijzigt: de directe pakketten en hun afgeleide pakketten. Pakketten die de basisimage al vastlegt staan er niet nog eens in, zodat de twee nooit botsen.
- **Airflow** gaat nog een stap verder: de build legt eerst de versies van de basisimage vast (`pip list --format=freeze`) en geeft die als extra constraints aan pip. Pip mag dus alleen pakketten toevoegen, nooit Airflow of een van zijn pakketten bij- of terugwerken, en `pip check` moet slagen. Vraagt `services/airflow/requirements.txt` een versie die de basisimage niet heeft, dan stopt de build; verruim dan de grens in `requirements.txt` (zo staat `opentelemetry-api` op `>=1.27`, de versie van de basisimage).

De Flask- en de Airflow-build controleren de versies: wijken de geïnstalleerde versies af van `constraints.txt`, dan stopt de build met de melding dat je `make constraints` moet draaien. Dat gebeurt bijvoorbeeld als je een pakket aan `requirements.txt` toevoegt of een grens verandert.

Zo werk je de versies bij:

```bash
make constraints
git diff services/*/constraints.txt
docker compose -p wasstraat-test -f docker-compose.test.yml build --no-cache --pull
make test-all
```

`make constraints` bouwt de drie images zonder cache en zonder vaste versies, zodat pip de nieuwste versies binnen de grenzen kiest, en schrijft die versies weg. Werk je maar één image bij, gebruik dan `bash scripts/leg_pakketversies_vast.sh flask` (of `jupyter` of `airflow`). Het script bouwt eigen images (`wasstraat-pakketversies-*`), verwijdert ze na afloop en laat draaiende containers ongemoeid.

Commit de nieuwe constraints-bestanden alleen als `make test-all` slaagt. Faalt een test door een nieuwere versie, zet dan een bovengrens in `requirements.txt` (bij Jupyter in de Dockerfile) en draai `make constraints` opnieuw. De Jupyter-image valt buiten de tests; open na het bijwerken een paar notebooks om te controleren of ze nog werken.

De basisimage van Jupyter staat vast op een digest in `services/jupyter/Dockerfile`. De Flask-image gebruikt `python:3.11-slim-bookworm` zonder digest, zodat beveiligingsupdates van Python en Debian wel binnenkomen. Ook `apache/airflow:2.10.5-python3.11` staat niet op een digest; de Python-pakketten van die tag liggen vast via de constraints van Airflow 2.10.5. De `apt-get`-opdrachten in de Dockerfiles proberen een mislukte download drie keer opnieuw (`-o Acquire::Retries=3`), zodat een verse build niet stukloopt op een tijdelijke netwerkfout.

## Wat wordt getest?

### Unit tests

Alle bestanden staan in `tests/unit/`.

| Bestand | Wat wordt getest |
|---------|------------------|
| **Extractie** | |
| `test_importMDB_bash.py`, `test_importMDB_functions.sh` | De bash-functies van `importMDB.sh` |
| `test_importMDB_kopregel.py` | `importMDB.sh`: de kopregel van de CSV-export (zelf gequote, ook bij komma's in kolomnamen) |
| `test_importMDB_lijstbestand.py` | `importMDB.sh` met een lijstbestand (incrementele cyclus) |
| `test_csv_kolommen.py` | `airflow_app/scripts/csv_kolommen.py` en de aanroep in `importMDB.sh`: `table`, `projectcd`, `bron`, `loadtime` en `mdbfile` achter elk record, ook bij een tekstveld met een regeleinde; bijzondere tekens (`&`, `\`) in tabelnamen en paden; byte voor byte gelijk aan de vroegere `sed`-regels zolang er geen regeleinde in een veld staat |
| `test_encoding.py` | UTF-8-conversie, herkenning van Windows-1252, dubbele CSV-kopregels |
| `test_paden_overslaan.py` | `paden_overslaan`: patronen, foutieve waarden, het script voor `importMDB.sh` (met nep-MDB's), de registratie, de afbeeldingen en de configuraties in de repository |
| `test_image_import.py` | De status per bestand in `Filenames` (verwerkt, overgeslagen, mislukt), de harde fout bij een vol volume of een niet-schrijfbare uitvoermap, tellingen en drempel, het opruimen van openstaande entries |
| `test_image_util.py` | `shared/image_util.py`: kleurmodus, EXIF-oriëntatie, documenticoon, afgekapte en beschadigde bestanden |
| `test_controle_extractie.py` | Het log van `importMDB.sh` lezen, `Controleer_Databases` onder en boven de drempel, `Controleer_Afbeeldingen` in beide cycli |
| `test_foto_parsing.py` | Bestandsnamen van objectfoto's, tekeningen (A–E, P, T, LZW), projectfoto's (F/G), DAN/DAR-rapporten, artefactsoort uit het pad |
| **Transformatie** | |
| `test_harmonizer.py` | `$ifNull`-ketens, tabelpatronen, `loadHarmonizer` (Excel naar DataFrame), opbouw van de pipeline, overerving, `getHarmonizeAggr` wijzigt de gecachete pipeline niet |
| `test_correcties_yml.py` | `correcties.yml` laden en toepassen, inclusief foutscenario's en `paden_overslaan` |
| `test_profielen.py` | Gemeenteprofielen: keuze, cache, `ConventieProfiel`, `DelftProfiel`, `VoorbeeldProfiel` |
| `test_archutils.py` | `convertToInt`, `convertToBool`, `fixDatering` (eeuw-kwartnotatie, Romeinse cijfers, LMEb, RT, gecombineerde dateringen) |
| `test_rijksdriehoek.py` | Rijksdriehoek naar WGS84 en terug, met referentiepunten |
| `test_fix_monster_projectcds.py` | Projectcodes van de monsterdatabase |
| `test_fixes_1_to_4.py`, `test_fix_5_nonetype_foto.py`, `test_fix_6_coordinaatvalidatie.py`, `test_fix_7_kolomselectie.py`, `test_fix_8_dropna.py` | Eerdere reparaties: robuustheid bij ontbrekende of ongeldige data, coördinaatvalidatie, kolomselectie in `mergeFotoinfo`, `dropna` |
| `test_meta_project.py`, `test_meta_generate_missing.py` | De Project-configuratie en de pipelines voor ontbrekende putten, vlakken, sporen, vondsten en dozen in `meta.py` |
| `test_merge_artefacten.py` | Verplaatsen en samenvoegen van artefacten: elke bronrij in precies één document |
| `test_delta_transform.py` | Delta-varianten van de transformaties en stabiele sleutels (ook de samengestelde sleutel van artefacten) |
| `test_bronsleutel.py` | De hulpsleutel uit de bronrij en het toekennen van stabiele `primary_key`s daarop |
| **Laden en zoeken** | |
| `test_loadToDatabase.py` | De helpers van de laadstap (typen, enums, FK-mechaniek, afgeleide velden als FASE 4) |
| `test_load_projectie.py` | De veldselectie van de load (`leesDocumenten`) |
| `test_load_volledig.py` | `loadAll` met gebruikersdata en de atomic swap op een nagebootste PostgreSQL; `indexTable` slaat koppeltabellen over |
| `test_load_incrementeel.py` | `loadIncrementeel` (upsert, verwijderen, FK's, sequence, schemamigratie en verwijzingen van gebruikersdata) en `indexTableIncrementeel` |
| `test_afgeleide_velden.py` | `herberekenAfgeleideVelden`: SQL, randgevallen op SQLite en gelijkheid met `init.init()` van de webapplicatie |
| **Run, foutbeleid en rapport** | |
| `test_verwerkingsrun.py`, `test_bronbestanden.py`, `test_opruimen.py` | Run-document, registratie en delta van bronbestanden, opruimen van oude records |
| `test_foutbeleid.py` | Beleid per taak, drempels en meldingen, de `on_failure_callback`, `controleerBewaking` op nagebootste DAG's, het run-document van alle cycli, `dropAll`, Transform 2 en 3, meldingen van de laadstap |
| `test_verwerkingsrapport.py` | Opbouw per sectie, JSON-structuur, Markdown-koppen, terugval van de rapportmap, de lezers met nagebootste MongoDB en PostgreSQL |
| **Webapplicatie** | |
| `test_flask_app.py`, `test_flask_models.py`, `test_flask_formatters.py`, `test_flask_geo.py`, `test_flask_route.py`, `test_flask_util.py`, `test_flask_validators.py`, `test_flask_search.py` | Modules van de webapplicatie: imports en modellen (ook tegen `gebruikersdata.VERWIJZINGEN`), formatters, de geo-uitbreiding, routes, hulpfuncties, validators en het zoeken zonder Elasticsearch |
| `test_flask_beheerder.py` | Aanmaken van de beheerder met `FLASK_ADMIN_PASSWORD` |
| `test_flask_foto_util.py` | Kantelen van foto's en pdf's |
| **Installatie, configuratie en images** | |
| `test_init_config.py` | `init-config.sh` in een tijdelijke kopie: gegenereerde wachtwoorden, bestaande bestanden blijven staan |
| `test_config_cache.py` | De cache-instellingen uit `shared/config.py` zijn getallen |
| `test_wachtwoord_maskeren.py` | `maskeerWachtwoord` en dat de logs geen wachtwoorden tonen |
| `test_apache_voordeur.py` | De Apache-configuratie, de compose-bestanden, de Makefile en `ProxyFix` |
| `test_deploy.py` | De live installatie in `deploy/`: kopieën gelijk aan het origineel, alleen images, alleen-lezen mounts, `PGDATA`, poorten, `make publish` |
| `test_elasticsearch_testomgeving.py` | Een eigen Elasticsearch zonder hostpoort in beide testomgevingen |
| `test_pakketversies.py` | Vastgelegde pakketversies en robuuste builds (`constraints.txt`, `pip check`, apt-retries, `make constraints`) |
| `test_jupyter_image.py` | De pakketten van de Jupyter-image |
| `test_synthetic_data.py`, `test_synthetic_monster_data.py` | Structuur van de synthetische Access-databases en monsterdata |

### Integratietests

| Test | Wat wordt getest |
|------|-----------------|
| `test_full_pipeline.py` | Volledige harmonisatie-pipeline met directe MongoDB-seeding: harmonisatie, attributen, sleutels, verplaatsen en samenvoegen, verwijzingen |
| `test_full_pipeline_synthetic_data.py` | Volledige ETL via Airflow met de synthetische data: verwachte aantallen per soort, objectfoto's gekoppeld aan hun artefact en vondst, unieke sleutels, de werkmap die `paden_overslaan` overslaat, een memo-veld met een regeleinde, `DAG_Load_Only` volledig geslaagd |
| `test_full_pipeline_delft_data.py` | Dezelfde pipeline met de Delftse testdata (DB034) en Delft-specifieke verwachte aantallen; Elasticsearch per tabel gelijk aan PostgreSQL |
| `test_harmonize_pipeline.py` | Individuele harmonisatie-pipelines |
| `test_importMDB_bash.py` | Het importscript in Docker: encoding-conversie, CSV, `mongoimport` |
| `test_incremental_synthetic_data.py` | Volledige cyclus, negen incrementele runs en opnieuw de volledige cyclus (zie [Incrementele cyclus](#incrementele-cyclus)): PostgreSQL, Elasticsearch, registratie, gebruikersdata, run-document en verwerkingsrapport |
| `test_verwerkingsrapport.py` | De trigger rules en de bewaking in de echte DAG's (DagBag), een rapport voor elke beëindigde run, `DAG_Load_Only` en een bewust mislukte `Start_Run` |
| `test_flask_smoke.py` | De webapplicatie via Apache: kaart, inloggen, media, redirects achter een proxy, bruiklenen van verdwenen artefacten, projecten zonder locatie, foto's kantelen |

## Nieuwe tests toevoegen

1. Maak een nieuw bestand aan in `tests/unit/` of `tests/integration/`
2. Gebruik `pytest.mark.unit` of `pytest.mark.integration` als marker
3. Gebruik `pytest.mark.delft` voor tests die Delftse data vereisen
4. De `conftest.py` mockt automatisch `shared.config` en laadt de echte `shared.const` en `shared.logutils`
5. Voor integratietests: gebruik de `mongo_client`, `staging_db` en `analyse_db` fixtures

## Opruimen

```bash
make clean          # verwijder .venv en caches
make clean-test-db  # stop test-database containers
```
