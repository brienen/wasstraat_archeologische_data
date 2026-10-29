# Foutbeleid en verwerkingsrapport

!!! note "Status"
    Gebouwd voor [issue 54](https://github.com/brienen/wasstraat_archeologische_data/issues/54) (fouten bij inlezen leiden niet altijd tot het afbreken van de hele run) en [issue 62](https://github.com/brienen/wasstraat_archeologische_data/issues/62) (verwerkingsrapport per run). Het run-document waarop beide steunen staat in [Incrementeel laden](incrementeel-laden.md#run-document).

## Doel

Tot issue 54 stopte een fout in een taak de hele DAG, terwijl een deel van de fouten (één onleesbare database, één beschadigde foto, een haperende Elasticsearch) de rest van de verwerking niet raakt. Andere fouten werden juist stil genegeerd: een mislukte `Drop_All_Databases` werd alleen gelogd, een onleesbare Access-database alleen in het log van `importMDB.sh` genoemd. En na een run was nergens in één overzicht te zien wat er verwerkt was, wat niet, en waarom.

Daarom:

- **Foutbeleid (issue 54):** per taak is vastgelegd of een fout *cruciaal* is (de run stopt) of een *waarschuwing* (de run gaat door, de fout wordt geteld en gemeld), met waar nodig een drempel. Alle waarschuwingen en fouten komen op één plek: de meldingen in het run-document. Ook de volledige cyclus en `DAG_Load_Only` hebben nu een run-document.
- **Verwerkingsrapport (issue 62):** aan het eind van elke run, ook na een fout, schrijft de taak `Verwerkingsrapport` een rapport als JSON (machineleesbaar) en Markdown (leesbaar), met een samenvatting in het Airflow-log en in het run-document.

## Foutbeleid

### Uitgangspunt

| Soort fout | Gedrag | Voorbeelden |
|------------|--------|-------------|
| **Cruciaal** | De taak faalt, `Markeer_Run_Mislukt` zet de run op `mislukt`, de DAG faalt. De registratie van bronbestanden wordt niet bijgewerkt, zodat een volgende run dezelfde bestanden opnieuw oppakt. | De data in PostgreSQL zou onvolledig of onjuist worden: een harmonisatie, transformatie of load die faalt, een vol mediavolume, een drempel die wordt overschreden, MongoDB of PostgreSQL onbereikbaar |
| **Waarschuwing** | De run gaat door. De fout komt als melding met niveau `waarschuwing` in het run-document en in het rapport. | Eén onleesbare database, tabel, afbeelding of record; een mislukte Elasticsearch-index; afgeleide velden die niet herberekend konden worden; een FK die niet gevalideerd kon worden |
| **Waarschuwing met drempel** | Onder de drempel een waarschuwing, erboven cruciaal: een reeks losse fouten wijst op een structureel probleem (mdbtools kapot, een fout in het gemeenteprofiel, een ontbrekende map). | Onleesbare Access-databases, mislukte afbeeldingen, records die Transform 2 niet kon verwerken |

De drempel is steeds het grootste van een vast aantal en een percentage van het totaal (`foutbeleid.bepaalDrempel`, dezelfde regel als bij de afbeeldingen): bij een kleine verzameling telt het vaste aantal, bij een grote het percentage.

### Beleid per stap

Legenda gedrag tot issue 54: **F** = taak faalt en DAG faalt; **S** = overgeslagen met alleen een regel in het log (taak slaagt); **T** = geteld en gerapporteerd.

| Stap / taak | Fout | Tot issue 54 | Nu |
|---|---|---|---|
| Volledige cyclus en `DAG_Load_Only` | geen run-document tijdens de run (de volledige cyclus maakte er pas bij de registratie een aan) | — | `Start_Run` aan het begin (soort `volledig` of `laden`), `Markeer_Run_Mislukt`, meldingen, rapport |
| `Start_Run` | er loopt al een run | F (alleen incrementeel) | F in alle drie de DAG's: twee runs tegelijk beschadigen elkaars staging en registratie |
| `Drop_All_Databases` | MongoDB-fout | **S**: de extractie las daarna bovenop de oude data in | F. De collectie `Verwerkingsruns` blijft staan (geschiedenis van runs en rapporten) |
| `Bepaal_Delta`, `Opruimen_Oude_Records` | elke fout | F | F |
| `Extract_Data_From_<map>` (`importMDB.sh`) | onleesbare Access-database | S (ERROR in het log, exit 0) | T met drempel: nieuwe taak `Controleer_Databases`, waarschuwing; boven `AIRFLOW_MAX_MISLUKTE_DATABASES` / `_PCT` cruciaal |
| idem | tabel die de export niet aankan (kopregel, kolommen, mongoimport) | S | T: waarschuwing, per tabel in het rapport |
| idem | database zonder één record | S (registratie met 0 records en een WARNING) | T: waarschuwing |
| idem | lijstbestand ontbreekt (incrementeel) | F | F |
| `Extract_Data_From_Fotos_*` | één bestand onleesbaar of beschadigd | T (status `mislukt` in `Filenames`) | T, ongewijzigd |
| idem | vol of alleen-lezen volume, geen schrijfrechten | F direct, zonder herhaling | F, ongewijzigd |
| `Controleer_Afbeeldingen` | mislukte afbeeldingen | T met drempel; tellingen alleen in het run-document van de incrementele cyclus | T met drempel; tellingen en melding nu ook in de volledige cyclus |
| `Extract_Referentietabellen`, `Extract_ExtraProjecten` | bestand onleesbaar | F | F: zonder ABR of projecten is de rest onbruikbaar |
| Transform 1 (harmonisatie) | aggregatie faalt | F | F |
| `ParseFotobestanden` | één bestand niet te parsen | S | ongewijzigd; het rapport telt de onherkende bestandsnamen (soort `Bestand`) |
| `Enhance_All_Attributes` (Transform 2) | één record faalt | T (`_processing_errors`), geen drempel | T met drempel (`AIRFLOW_MAX_VERWERKINGSFOUTEN` / `_PCT`), melding |
| idem | locatie buiten Nederland of onleesbare coördinaat | S (veld `error` in het document) | T: locatiefouten per soort in het rapport |
| `extract_Imagedata_From_FileNames` | één foto faalt | S | T (`_processing_errors`, fase `imagedata`) met drempel |
| `Set_Artefactnr_Unique` (Transform 3) | fout bij één project | S | T: waarschuwing |
| idem | fout buiten de projecten | **S**: de sleutels werden zonder de vlag `vondstkey_met_putnr` berekend | F |
| Overige taken van Transform 3, 4 en 5 | aggregatie- of PostgreSQL-fout | F | F |
| `LoadToDatabase_postgres` (`loadAll`) | laden of swap faalt | F | F |
| idem | FK niet hersteld (na de commit van de swap) | S (WARNING) | T: waarschuwing met de namen |
| idem | FK niet gevalideerd | S (WARNING) | T: waarschuwing |
| idem | sleutels niet stabiel (hernummerd) | S (WARNING) | T: waarschuwing |
| idem | afgeleide velden (FASE 4) | F, terwijl de swap al gecommit was | T: waarschuwing; de volgende load herstelt ze, `init.init()` van Flask blijft vangnet |
| `Load_Upsert` (`loadIncrementeel`) | upsert, verwijderen of FK-herstel faalt | F (rollback) | F (rollback) |
| idem | FK niet gevalideerd | T (`fk_niet_gevalideerd`) | T + melding |
| idem | afgeleide velden | F: de hele upsert werd teruggedraaid | T: waarschuwing; alleen de herberekening wordt teruggedraaid (`SAVEPOINT`) |
| `Index_<tabel>` (volledige cyclus, `DAG_Load_Only`) | Elasticsearch-fout | F: de hele DAG faalde, terwijl de load al goed was | waarschuwing: `Index_Klaar` (`all_done`), de registratie gaat door en de DAG slaagt |
| `Index_<tabel>` (incrementeel) | Elasticsearch-fout | run `afgerond`, DAG rood | waarschuwing, DAG slaagt |
| `Registreer_Bronbestanden`, `Registreer_Run`, `Rond_Run_Af` | PostgreSQL- of MongoDB-fout | F | F |
| `Verwerkingsrapport` | rapportmap niet schrijfbaar | — | terugval naar `AIRFLOW_LOGDIR/rapporten` met een waarschuwing; een sectie die niet op te bouwen is, staat als niet beschikbaar in het rapport; alleen een onverwachte fout laat de taak (en de DAG) falen, de status van de run blijft |

Herstel na een cruciale fout: zie de melding in het rapport en het log van de taak. Een mislukte incrementele run kan na herstel van de oorzaak gewoon opnieuw starten (de registratie is niet bijgewerkt); na een mislukte volledige cyclus de volledige cyclus opnieuw draaien. Een mislukte Elasticsearch-index herstel je met `DAG_Load_Only` of de volgende incrementele run.

### Opbouw van de DAG's

De volledige cyclus, de incrementele cyclus en `DAG_Load_Only` hebben dezelfde opbouw (`airflow_app/dags/tasks_verwerkingsrun.py`):

```
Start_Run → … verwerking … → registratie (Registreer_Bronbestanden, Registreer_Run of Rond_Run_Af)
bewaakte taken → Markeer_Run_Mislukt (one_failed)
alle andere taken → Verwerkingsrapport (all_done) → eindtaak (all_success)
```

- **Bewaking.** De cruciale taken (en taakgroepen) hangen aan `Markeer_Run_Mislukt` (`trigger_rule=one_failed`), de Index-taken niet. De melding van de run noemt de mislukte taken, bijvoorbeeld `Mislukte taak in Airflow-run manual__…: Extract_Group.Controleer_Afbeeldingen.`
- **Foutmelding per taak.** Elke taak heeft `foutbeleid.registreerTaakfout` als `on_failure_callback` (via `default_args`): de foutmelding van een mislukte taak komt in de meldingen van het run-document, met niveau `fout` bij een cruciale taak en `waarschuwing` bij een Index-taak. Heeft de taak zelf al een fout gemeld (zoals een overschreden drempel), dan volgt geen tweede melding.
- **Eindstatus.** De eindtaak (`End_ETL_full_cycle`, `End_ETL_incremental`, `End_cycle`) is de enige taak zonder stroomafwaartse taken en bepaalt de status van de DAG. Hij hangt via `all_success` aan de registratie en aan het rapport: hij faalt (upstream_failed) als een cruciale taak faalde of het rapport niet gemaakt kon worden, en slaagt als alleen een Index-taak faalde.
- **Rapport na alles.** `Verwerkingsrapport` hangt aan álle andere taken met `trigger_rule=all_done`, zodat het ook na een fout pas draait als de rest klaar is (ook bij `airflow dags test`, dat de taken na elkaar uitvoert).
- **Index-taken.** In de taakgroep `Load_To_Database_And_Inxdex_Group` wacht `Index_Klaar` (`all_done`) op alle Index-taken; `End_cycle` hangt aan `LoadToDatabase_postgres` en `Index_Klaar`. In de volledige cyclus hangt `Registreer_Bronbestanden` aan de groep en dus ook aan `Index_Klaar`: de registratie wacht tot de indexering klaar is, ongeacht de uitkomst (zoals `Registreer_Run` in de incrementele cyclus), zodat geen nieuwe run kan starten terwijl de indexering nog loopt.
- **Eén run tegelijk.** De drie DAG's hebben `max_active_runs=1` en `Start_Run` faalt als er al een run actief is.
- **Volgorde ongewijzigd.** Er zijn alleen taken bijgekomen (`Start_Run`, `Controleer_Databases`, `Index_Klaar`, `Rond_Run_Af`, `Markeer_Run_Mislukt`, `Verwerkingsrapport`); de verwerkingsvolgorde van de stappen is niet veranderd.

`foutbeleid.controleerBewaking(dag)` controleert deze regels voor een DAG; de integratietest `test_verwerkingsrapport.py` past hem toe op de DagBag.

### Controle van de Access-databases (`Controleer_Databases`)

`importMDB.sh` slaat een onleesbare database of een tabel die de export niet aankan over met een regel `ERROR`/`WARNING` in zijn log en eindigt met exit 0. De taak `Controleer_Databases` (in `Extract_Group`, na `Extract_ExtraProjecten`, vóór de transformatie) leest per MDB-categorie het log van deze run (`AIRFLOW_LOGDIR/<collectie>.log`, door `importMDB.sh` per run overschreven; een log van vóór de start van de run telt niet), telt per verwerkte database de staging-documenten en schrijft het resultaat in het run-document onder `tellingen.extractie`:

| Veld | Inhoud |
|------|--------|
| `databases`, `onleesbaar`, `leeg`, `tabellen_overgeslagen` | Aantallen over alle categorieën |
| `per_categorie` | Per categorie `log_gelezen`, `verwerkt`, `onleesbaar`, `tabellen_overgeslagen`, `leeg` |
| `onleesbare_databases`, `lege_databases`, `overgeslagen_tabellen` | Lijsten (hoogstens 200) met `bestand`, `categorie` en bij tabellen `tabel` en `reden` (`geen kopregel gelezen`, `kolommen toevoegen mislukt`, `mongoimport mislukt (exit n)`) |
| `niet_gevonden`, `overige_meldingen` | Paden uit het lijstbestand die niet bestaan en overige `ERROR`/`WARNING`-regels |
| `records` | Per verwerkte database het aantal staging-documenten |
| `drempel`, `max_aantal`, `max_pct`, `boven_drempel` | De drempel voor onleesbare databases |

Lege databases, overgeslagen tabellen en overige meldingen zijn waarschuwingen; onleesbare databases ook, tot de drempel. Meldingen van `mdb-prop` (alleen metainformatie) tellen niet.

### Meldingen in het run-document

`foutbeleid.meld(niveau, soort, melding, aantal, details)` schrijft een melding in de lijst `meldingen` van het run-document van de lopende run (begrensd op 500 meldingen van hoogstens 2.000 tekens). Een taak uit een DAG zonder eigen run (bijvoorbeeld `DAG_Transform_Only`) schrijft niets, ook niet in een run van een andere DAG die toevallig actief is (`verwerkingsrun.runVanTaak`). Soorten:

| Soort | Niveau | Bron |
|-------|--------|------|
| `taak_mislukt` | fout of waarschuwing (Index) | `registreerTaakfout` (on_failure_callback) |
| `database_onleesbaar` | waarschuwing, boven de drempel fout | `Controleer_Databases` |
| `database_leeg`, `tabel_overgeslagen`, `import_melding` | waarschuwing | `Controleer_Databases` |
| `afbeeldingen_mislukt` | waarschuwing, boven de drempel fout | `Controleer_Afbeeldingen` |
| `verwerkingsfouten` | waarschuwing, boven de drempel fout | `Enhance_All_Attributes`, `extract_Imagedata_From_FileNames` |
| `uniciteit_niet_bepaald` | waarschuwing | `Set_Artefactnr_Unique` |
| `sleutels_niet_stabiel`, `fk_niet_hersteld`, `fk_niet_gevalideerd`, `afgeleide_velden_mislukt` | waarschuwing | `LoadToDatabase_postgres`, `Load_Upsert` |
| `rapport` | waarschuwing | `Verwerkingsrapport` (terugval van de rapportmap) |

## Verwerkingsrapport

### Wanneer en waar

De taak `Verwerkingsrapport` draait aan het eind van elke run van `Extract_Transform_Load_Full_Cycle`, `Extract_Transform_Load_Incremental` en `DAG_Load_Only`, ook na een fout. Hij schrijft twee bestanden naar `AIRFLOW_OUTPUT_RAPPORTEN` (standaard `/output/rapporten`):

```
verwerkingsrapport_<run_id>_<soort>_<tijdstip>.json
verwerkingsrapport_<run_id>_<soort>_<tijdstip>.md
```

bijvoorbeeld `verwerkingsrapport_20261029T101500_volledig_20261029T102312.json` (run-id = start van de run, tijdstip = moment van het rapport, beide UTC). Mislukte `Start_Run` (er was al een run actief): `verwerkingsrapport_zonder-run_<dag_id>_<tijdstip>`. Het opnieuw draaien van de taak maakt een nieuw bestand; er wordt niets overschreven of opgeruimd.

| Omgeving | Map op de host |
|----------|----------------|
| Ontwikkelomgeving (`docker-compose.yml`) | `data/synthetic/output/rapporten` |
| Delftse omgeving (`docker-compose.delft.yml`) | `data/delft/output/rapporten` |
| Live installatie (`deploy/`) | `${WASSTRAAT_OUTPUT:-./data/output}/rapporten` (aangemaakt door `make init`) |
| Testomgevingen | `/tmp/rapporten_test` in de Airflow-container (gelezen met `docker exec`) |

De Airflow-image maakt `/output/rapporten` aan met de airflow-gebruiker als eigenaar. Is de map niet schrijfbaar (bijvoorbeeld een bind mount die Docker op Linux als root heeft aangemaakt, of een installatie zonder de nieuwe mount), dan schrijft de taak in `AIRFLOW_LOGDIR/rapporten` en komt er een waarschuwing in het run-document. De mappen `data/*/output/` staan in `.gitignore`.

Daarnaast:

- **Airflow-log:** een samenvatting (uitkomst, fouten, waarschuwingen, bronbestanden, objecten) met de eerste fouten en waarschuwingen en de paden van het rapport.
- **Run-document:** het veld `rapport` met `json`, `markdown`, `map_terugval`, `gemaakt_op` en `samenvatting` (zie hieronder), zodat de webapplicatie het rapport later kan tonen.

### Inhoud (JSON)

| Sectie | Inhoud |
|--------|--------|
| `rapport_versie`, `gemaakt_op` | Versie van de opbouw (1) en tijdstip (UTC) |
| `run` | `run_id`, `soort`, `status`, `melding`, `dag_id`, `airflow_run_id`, `gestart_op`, `beeindigd_op`, `duur_seconden`, `profiel` (`WASSTRAAT_GEMEENTE`) en `versie` (alleen als bekend, zie [Configuratie](#configuratie)) |
| `samenvatting` | `uitkomst`, `status`, `duur_seconden`, `fouten`, `waarschuwingen`, `gestopt_door`, bronbestanden per status, objecttotalen, `verwerkingsfouten`, `afbeeldingen_mislukt`, `databases_onleesbaar`, `secties_niet_beschikbaar` |
| `foutbeleid` | `uitkomst` (`geslaagd`, `geslaagd met waarschuwingen` of `mislukt`), `gestopt_door` (`taak`, `stap`, `melding` van de eerste mislukte cruciale taak), `fouten` en `waarschuwingen` (de meldingen, aangevuld met mislukte taken zonder melding), `mislukte_taken`, `niet_uitgevoerd` (taken die door een fout niet aan de beurt kwamen) en de `drempels` die golden |
| `bronbestanden` | `totalen` per categorie en status (`verwerkt`, `overgeslagen`, `mislukt`, `onverwerkt`, `verwijderd`, `ongewijzigd`), `bestanden` (per bestand `bestand`, `categorie`, `grootte`, `status`, `wijziging` (de delta: `nieuw`, `gewijzigd`, …), `records`, `reden` en eventueel `tabellen_overgeslagen`), `weggelaten`, `delta`, `paden_overgeslagen`, `registratie_uitgevoerd` en `van_toepassing` (niet bij `DAG_Load_Only`) |
| `objecttotalen` | Per tabel uit `LOAD_TABELLEN`: `totaal` (rijen in PostgreSQL na de run), `aangemaakt`, `bijgewerkt`, `samengevoegd`, `verwijderd` en `nieuwe_sleutels`; plus `totaal`, `artefactsoorten` en `load_uitgevoerd` |
| `kwaliteitsmeldingen` | `verwerkingsfouten` (per fase, soort en fouttype met voorbeelden), `afbeeldingen` (`tellingen.afbeeldingen`), `databases` (`tellingen.extractie`), `paden_overgeslagen`, `locatiefouten`, `onherkende_bestandsnamen`, `rijen_zonder_key`, `fk`, `gebruikersdata`, `sleutels` (hernummerd, nieuwe en verdwenen primary_keys per soort) en `afgeleide_velden` |
| `pipeline` | `start`, `eind`, `duur_seconden` van de Airflow-run, `stappen` (per stap `start`, `eind`, `duur_seconden`, `som_taakduur_seconden`, `taken`, `geslaagd`, `mislukt`, `niet_uitgevoerd`, `overgeslagen`) en `taken` (per taak `status`, `start`, `eind`, `duur_seconden`, `start_geschat`, `pogingen`, `stap`, `cruciaal`) |
| `fouten_in_rapport` | Secties die niet (volledig) opgebouwd konden worden, met de fout |

Herkomst van de gegevens:

- **Bronbestanden.** De registratie van deze run in `Def_Bronbestand` (`run_id`), bij een incrementele run aangevuld met de delta uit `Verwerkingsrun_Bestanden`; de onleesbare en lege databases en overgeslagen tabellen uit `tellingen.extractie`; mislukte, onverwerkte en overgeslagen afbeeldingen uit `Filenames` (bij een incrementele run alleen die van deze run en de openstaande); de paden die `paden_overslaan` in `correcties.yml` overslaat (`paden_overgeslagen` in het run-document). Stopte de run vóór de registratie, dan krijgen nieuwe en gewijzigde bestanden zonder andere status `onverwerkt`. De lijst noemt alle bestanden behalve ongewijzigde en verwerkte afbeeldingen zonder bijzonderheden (bij een incrementele run wel de nieuwe en gewijzigde), hoogstens 2.000 in de JSON en 200 in de Markdown; de totalen tellen alles.
- **Objecttotalen.** `aangemaakt`, `bijgewerkt` en `verwijderd` komen uit `tellingen.load`: bij de incrementele cyclus uit de upsert (`ingevoegd`, `bijgewerkt`, `verwijderd`), bij de volledige cyclus en `DAG_Load_Only` uit de vergelijking van de oude en de nieuwe tabel in `loadAll` (`telLaadRijen`: rijen met een nieuwe of verdwenen `primary_key`; `bijgewerkt` is daar niet bekend, want elke rij wordt opnieuw geschreven). `samengevoegd` is het aantal documenten in `Single_Store_Clean` dat uit meer dan één bronrecord is samengevoegd (`brondata_count > 1`; incrementeel alleen die van deze run). `nieuwe_sleutels` komt uit Transform 4 (`tellingen.transform.primary_keys`).
- **Kwaliteitsmeldingen.** `_processing_errors` met een tijdstempel na de start van de run; locatiefouten (veld `error`, gezet door `archutils.logError`) en onherkende bestandsnamen (soort `Bestand`, `fototype` N) in `Single_Store_Clean`; rijen zonder key in PostgreSQL (alleen na een load); de rest uit de tellingen van het run-document.
- **Pipeline.** De taakinstanties van de lopende DagRun (`dag_run.get_task_instances()`), zonder het rapport zelf en de eindtaak. De scheduler legt per taak start en einde vast; `airflow dags test` (de integratietests) legt alleen het einde vast. Daar lopen de taken na elkaar, dus wordt de start dan geschat als het einde van de taak die daarvóór eindigde (`start_geschat`). Om dezelfde reden bepaalt `verwerkingsrun.startVanAirflowRun` de start van een Airflow-run uit het vroegste tijdstip van zijn taken: `airflow dags test` geeft de DagRun de logische datum als start en bij elke aanroep dezelfde run_id.

### Voorbeeld (Markdown)

Ingekort (lege secties en rijen weggelaten), uit de synthetische testomgeving: de incrementele run met een onleesbare database (stap h2 van de integratietest):

```markdown
# Verwerkingsrapport 20261029T134248

Uitkomst: **geslaagd met waarschuwingen** (0 fout(en), 1 waarschuwing(en)).

| Gegeven | Waarde |
|---|---|
| Soort run | incrementeel |
| Status | afgerond |
| DAG | Extract_Transform_Load_Incremental |
| Gestart | 2026-10-29 13:42:48 UTC |
| Beëindigd | 2026-10-29 13:43:04 UTC |
| Doorlooptijd | 16,8 s |
| Profiel | delft |

## Foutbeleid

Geen fout heeft de run gestopt.

### Fouten

Geen.

### Waarschuwingen

| Stap | Taak | Soort | Aantal | Melding |
|---|---|---|---|---|
| extractie | Extract_Group.Controleer_Databases | database_onleesbaar | 1 | Onleesbare Access-databases (mogelijk corrupt; zie het log van de extractie): 1 van 1, binnen de drempel van 2. |

## Bronbestanden

### Totalen per categorie

| Categorie | overgeslagen | mislukt | ongewijzigd |
|---|---|---|---|
| afbeeldingen | 1 | 0 | 15 |
| projecten | 1 | 1 | 2 |
| … | | | |

### Bestanden

| Bestand | Categorie | Grootte | Status | Records | Reden |
|---|---|---|---|---|---|
| /input/projecten/SY003/C Database/kapot.mdb | projecten | 10600 | mislukt | 0 | onleesbaar (mdb-tables kan het bestand niet lezen; mogelijk corrupt) |
| /input/projecten/SY001/K Overig/werkmap/opgravingSY001.mdb | projecten | – | overgeslagen | – | paden_overslaan (correcties.yml) |

## Objecttotalen

| Tabel | Totaal | Aangemaakt | Bijgewerkt | Samengevoegd | Verwijderd |
|---|---|---|---|---|---|
| Def_Project | 2 | 0 | 0 | 0 | 0 |
| Def_Artefact | 27 | 0 | 0 | 0 | 0 |
| … | | | | | |
| **Totaal** | 4989 | 0 | 0 | 0 | 0 |

## Kwaliteitsmeldingen

### Access-databases

1 databases verwerkt: 1 onleesbaar, 0 zonder records, 0 tabel(len) overgeslagen (drempel onleesbaar 2).

| Bestand | Probleem |
|---|---|
| /input/projecten/SY003/C Database/kapot.mdb | onleesbaar |

## Pipeline

### Doorlooptijd per stap

| Stap | Start | Eind | Duur | Taken | Mislukt | Niet uitgevoerd |
|---|---|---|---|---|---|---|
| extractie | 2026-10-29 13:42:48 UTC | 2026-10-29 13:42:49 UTC | 1,2 s | 21 | 0 | 0 |
| transform4 | 2026-10-29 13:42:56 UTC | 2026-10-29 13:43:01 UTC | 5,2 s | 59 | 0 | 0 |
| load | 2026-10-29 13:43:01 UTC | 2026-10-29 13:43:03 UTC | 1,4 s | 1 | 0 | 0 |
| index | 2026-10-29 13:43:03 UTC | 2026-10-29 13:43:04 UTC | 1,5 s | 22 | 0 | 0 |
```

## Configuratie

| Omgevingsvariabele (Airflow) | Vorm | Standaard | Betekenis |
|------------------------------|------|-----------|-----------|
| `AIRFLOW_OUTPUT_RAPPORTEN` | pad | `/output/rapporten` | Map voor de verwerkingsrapporten (terugval: `AIRFLOW_LOGDIR/rapporten`) |
| `AIRFLOW_MAX_MISLUKTE_DATABASES` | geheel getal ≥ 0 | `2` | Vast aantal onleesbare Access-databases dat nog acceptabel is |
| `AIRFLOW_MAX_MISLUKTE_DATABASES_PCT` | getal ≥ 0 (decimaal mag) | `5` | Percentage van de verwerkte databases dat nog acceptabel is |
| `AIRFLOW_MAX_VERWERKINGSFOUTEN` | geheel getal ≥ 0 | `100` | Vast aantal records per taak van Transform 2 dat niet verwerkt hoeft te kunnen worden |
| `AIRFLOW_MAX_VERWERKINGSFOUTEN_PCT` | getal ≥ 0 (decimaal mag) | `1` | Percentage van de bekeken records dat nog acceptabel is |
| `WASSTRAAT_VERSION` | tekst | — | Versie in het rapport; `deploy/docker-compose.yml` geeft de versie uit `.env` mee |
| `WASSTRAAT_VERSIEBESTAND` | pad | `/opt/airflow/version.env` | Bestand met een regel `VERSION=` (bijvoorbeeld een gemounte `config/version.env`); alleen gelezen zonder `WASSTRAAT_VERSION`. Ontbreken beide, dan staat er geen versie in het rapport |

De drempels worden in `shared/config.py` gelezen (aantallen met `int()`, percentages met `float()`); een lege, ongeldige of negatieve waarde levert de standaard op. Met `0` en `0` is elke fout cruciaal. Ze staan, met `AIRFLOW_OUTPUT_RAPPORTEN`, in `config/airflow.env.example` en `deploy/config/airflow.env.example`. De drempels voor afbeeldingen (`AIRFLOW_MAX_MISLUKTE_AFBEELDINGEN` / `_PCT`) staan bij de [extractie](extractie.md#afbeeldingen-en-rapporten).

Voorbeeld (alleen afwijkingen van de standaard zijn nodig):

```
AIRFLOW_MAX_MISLUKTE_DATABASES=5
AIRFLOW_MAX_MISLUKTE_DATABASES_PCT=2.5
AIRFLOW_OUTPUT_RAPPORTEN=/output/rapporten
```

## Modules en taken

| Onderdeel | Inhoud |
|-----------|--------|
| `airflow_app/dags/wasstraat/foutbeleid.py` | Beleid per taak (`isCrucialeTaak`, `isWaarschuwingstaak`, `bepaalStap`), `bepaalDrempel`, `toetsDrempel`, `meld`, `schrijfTelling`, `registreerTaakfout` (on_failure_callback), `controleerBewaking`, `CrucialeFout` |
| `airflow_app/dags/wasstraat/controle_extractie.py` | `controleerDatabases` (taak `Controleer_Databases`), `leesImportLog`, `controleerAfbeeldingen` (taak `Controleer_Afbeeldingen`, om `image_import.controleerAfbeeldingen` heen) |
| `airflow_app/dags/wasstraat/verwerkingsrapport.py` | `maakVerwerkingsrapport` (taak `Verwerkingsrapport`), de lezers per bron, de opbouw per sectie (`bouwBronbestanden`, `bouwObjecttotalen`, `bouwKwaliteit`, `bepaalFoutbeleid`, `bouwPipeline`), `maakMarkdown`, `schrijfRapport`, `bepaalRapportmap`, `leesVersie` |
| `airflow_app/dags/tasks_verwerkingsrun.py` | `maakStartRun`, `maakMarkeerRunMislukt`, `maakRondRunAf`, `voegVerwerkingsrapportToe`, `getDefaultArgs` |
| `airflow_app/dags/wasstraat/verwerkingsrun.py` | Soort `laden`, aansluiten bij de lopende volledige cyclus (`startRun('volledig')` zonder Airflow-run), `zoekRunVanAirflowRun`, `runVanTaak`, `voegMeldingToe`, `rondRunAf`, `getMislukteTaken` |
| Overige wijzigingen | `mongoUtils.dropAll` (laat `Verwerkingsruns` staan, faalt bij een fout); `setAttributes_functions.toetsVerwerkingsfouten`; `references_functions.setAndVondstUniqueInProject`; in `loadToDatabase_functions`: `telLaadRijen`, `schrijfLoadTellingen`, `herberekenAfgeleideVeldenInSavepoint` en de meldingen; `tasks_extract` (`Controleer_Databases`); `tasks_load_to_database_and_index` (`Index_Klaar`) |

## Testen

- Unit tests: `tests/unit/test_foutbeleid.py` (beleid per taak, drempels en meldingen, de callback, `controleerBewaking` op nagebootste DAG's, het run-document van alle cycli, `dropAll`, Transform 2 en 3, de meldingen en tellingen van de laadstap), `tests/unit/test_controle_extractie.py` (het log van `importMDB.sh`, `Controleer_Databases` onder en boven de drempel, `Controleer_Afbeeldingen` in beide cycli) en `tests/unit/test_verwerkingsrapport.py` (opbouw per sectie, JSON-structuur, Markdown-koppen ook bij lege secties en zonder run-document, een sectie die faalt, schrijven met terugval, het veld `rapport` in het run-document, de lezers met nagebootste MongoDB en PostgreSQL). De gewijzigde verwachtingen van de afgeleide velden staan in `test_loadToDatabase.py` en `test_load_incrementeel.py`.
- Integratietests: `tests/integration/test_incremental_synthetic_data.py` controleert na elke run het rapport (secties, koppen, totalen per tabel gelijk aan PostgreSQL, aangemaakte rijen van SY003), het run-document van de volledige cyclus, het rapport van de bewust mislukte run (stap g: de stoppende taak en de onleesbare foto) en een onleesbare database als waarschuwing (stap h2, ook in de volledige cyclus daarna). `tests/integration/test_verwerkingsrapport.py` bevat de DagBag-test op trigger rules en bewaking, controleert dat elke beëindigde run een rapport heeft, `DAG_Load_Only` (totalen gelijk aan PostgreSQL, niets nieuw of verwijderd) en een bewust mislukte `Start_Run` (rapport zonder run-document, de andere run ongemoeid); in de Delftse suite het rapport na `DAG_Load_Only`.

## Vervolg

- **Weergave in de webapplicatie** (optie B uit issue 62): een pagina die de runs uit `Verwerkingsruns` toont met het veld `rapport` (samenvatting, link naar het Markdown-rapport). Het run-document bevat daarvoor al de paden en de samenvatting; de bestanden staan in de uitvoermap, die Flask nu niet mount.
- **Opschoonbeleid.** Rapporten en run-documenten blijven onbeperkt staan (per run enkele tientallen kB tot enkele MB bij grote volledige cycli).
- **Parsefouten van bestandsnamen.** `ParseFotobestanden` logt een fout per bestand nog alleen; het rapport telt wel de onherkende bestandsnamen.
