# Extractie

De extractie leest de brondata in, zonder iets aan de inhoud te veranderen: elke rij uit een Access-database wordt een document in een staging-collectie van MongoDB, elk Excel-bestand wordt ingelezen met pandas, en elke foto, tekening of elk rapport wordt omgezet naar drie formaten in de mediamap. Daarna tellen twee controletaken wat niet gelukt is. Alles gebeurt in de taakgroep `Extract_Group` (`airflow_app/dags/tasks_extract.py`), in de volledige cyclus, de incrementele cyclus (alleen voor de delta) en `Extract_only`.

## Bronnen en taken

| Taak | Invoer (pad in de container) | Staging-collectie | Hoe |
|------|-------------------------------|-------------------|-----|
| `Extract_Data_From_Projecten` | `AIRFLOW_INPUT_PROJECTEN` (`/input/projecten`) | `Staging_Projecten_Oud` | `importMDB.sh` |
| `Extract_Data_From_Projectenlijst` | `AIRFLOW_INPUT_PROJECTENLIJST` | `Staging_Projecten_Projectenlijst` | `importMDB.sh` |
| `Extract_Data_From_Magazijnlijst` | `AIRFLOW_INPUT_MAGAZIJNLIJST` | `Staging_Projecten_Magazijnlijst` | `importMDB.sh` |
| `Extract_Data_From_Fotolijst` | `AIRFLOW_INPUT_FOTOLIJST` | `Staging_Projecten_Fotolijst` | `importMDB.sh` |
| `Extract_Data_From_MonsterDB` | `AIRFLOW_INPUT_MONSTER` | `Staging_Projecten_Monster` | `importMDB.sh` |
| `Extract_Data_From_RapportaneDBs` | `AIRFLOW_INPUT_RAPPORTEN` | `Staging_Rapporten` | `importMDB.sh` |
| `Extract_Referentietabellen` | `FILE_ABREXCEL` (ABR-thesaurus) | `Staging_Referentietabellen` | pandas |
| `Extract_ExtraProjecten` | `FILE_EXTRA_PROJECTS` (optioneel) | `Staging_Projecten_Projectenlijst` | pandas |
| `GetAndStoreImageFilenames`, `Extract_Data_From_Fotos_0` t/m `_7` | `AIRFLOW_INPUT_IMAGES`, `AIRFLOW_INPUT_RAPPORTEN`, `FILE_IMPORT_FILES_EXCEL` | `Filenames`, `Plaatjes` en de mediamap | `image_import.py`, `shared/image_util.py` |
| `Controleer_Databases` | De logs van `importMDB.sh` | run-document | `controle_extractie.py` |
| `Controleer_Afbeeldingen` | `Filenames` | run-document | `controle_extractie.py` |

De paden, collectienamen en drempels zijn instelbaar; zie [Configuratie](configuratie.md). Bij de volledige cyclus zijn de staging-collecties vooraf geleegd door `Drop_All_Databases`.

## Access-databases (importMDB.sh)

`airflow_app/scripts/importMDB.sh <invoermap> <collectie> [lijstbestand]` verwerkt alle Access-databases onder een invoermap:

1. **Selectie.** Alle bestanden `**/*.mdb` en `**/*.accdb` onder de invoermap (recursief, hoofdlettergevoelige extensie, zonder verborgen bestanden en mappen), of in de incrementele cyclus alleen de bestanden uit het lijstbestand van `Bepaal_Delta`. Bestanden onder een patroon uit `paden_overslaan` vallen af (zie [Paden overslaan](#paden-overslaan)).
2. **Projectcode.** Het begin van de eerste map onder de invoermap, zolang het uit hoofdletters en cijfers bestaat: `DB008_Leeuwenstein/C Database/DB008.mdb` hoort bij `DB008`. Staat het bestand direct in de invoermap, dan telt het begin van de bestandsnaam (`MONSTERS.mdb` geeft `MONSTERS`). Begint de map anders, zoals `werkmap/`, dan blijft de projectcode leeg en meldt het log `INFO: Geen projectcode af te leiden uit ...`. De code wordt per bestand opnieuw bepaald; tot issue 87 kreeg zo'n bestand de projectcode van het vorige bestand.
3. **Leesbaarheid.** `mdb-tables` moet het bestand kunnen lezen; anders logt het script een `ERROR` en slaat het de database over.
4. **Export per tabel.** Elke tabel gaat met `mdb-export` naar CSV. mdbtools leest de tekst als Windows-1252 (`MDB_JET3_CHARSET=CP1252`) en schrijft UTF-8; is de export toch geen geldige UTF-8, dan zet het script hem om vanuit de gedetecteerde codering, anders vanuit Windows-1252 of ISO-8859-1. Mislukte omzettingen staan in `AIRFLOW_LOGDIR/<collectie>_encoding_errors.log`.
5. **Extra kolommen** `table`, `projectcd`, `bron`, `loadtime` en `mdbfile` achter elk record (zie hieronder).
6. **Inlezen** met `mongoimport` in de staging-collectie; de kolominformatie per tabel komt in `Kolominformatie`.

Het log van het script staat in `AIRFLOW_LOGDIR/<collectie>.log` (per run overschreven) en in het log van de Airflow-taak. Een onleesbare database of een tabel die niet te exporteren is, laat het script niet falen; die telt de taak `Controleer_Databases` daarna.

### Kopregel van Access-tabellen

`mdb-export` (mdbtools 1.0) zet de kolomnamen in de kopregel van de CSV-export niet tussen aanhalingstekens. Een kolomnaam met een komma, zoals `FORMAAT IN MM, HORIZONTAAL` in de tabel `MUNTEN EN PENNINGEN`, telde daardoor als twee velden: de kopregel had meer velden dan de rijen, `mongoimport --headerline` verschoof alle waarden en de velden die `importMDB.sh` achteraan toevoegt (`table`, `projectcd`, `bron`, `loadtime`, `mdbfile`) kwamen onder verkeerde namen terecht, zodat de tabel niet werd geharmoniseerd en de documenten niet herleidbaar waren tot hun bestand. `importMDB.sh` schrijft de kopregel daarom zelf (functie `export_table_to_csv`): de kolomnamen worden tab-gescheiden uit `mdb-export -d $'\t' -Q` gelezen en met Python's `csv.writer` waar nodig gequote; de data volgt daaronder via `mdb-export -H` (zonder kopregel).

### Extra kolommen per record

Na de encoding-conversie voegt `importMDB.sh` aan de CSV-export de kolommen `table`, `projectcd`, `bron`, `loadtime` en `mdbfile` toe: de kolomnamen achter de kopregel, de waarden achter elk datarecord. Dat doet het Python-script `airflow_app/scripts/csv_kolommen.py`, dat naast `importMDB.sh` staat (in de Airflow-image via de `COPY` van `airflow_app/scripts`, in de ontwikkel- en testomgevingen via de mount van die map).

**Record, geen regel.** Een tekstveld met een regeleinde (een memo-veld in Access, bijvoorbeeld `KAARTBLAD` in de tabel `OPGRAVINGEN` van de Delftse projectenlijst) staat in de export tussen aanhalingstekens en beslaat meer regels. `csv_kolommen.py` leest de export met de `csv`-module, die bepaalt waar een record eindigt, en zet de waarden alleen aan het einde van het record. Tot oktober 2026 deed `importMDB.sh` dit met `sed`, per regel: de waarden kwamen dan ook achter elke regel binnen het tekstveld terecht (bijvoorbeeld `"37E,OPGRAVINGEN,DELF,..."` gevolgd door de rest van het veld). Het aantal velden per record klopte nog, dus de tellingen waren gelijk, maar de inhoud van die tekstvelden was vervuild. In de Delftse testdata ging het om 42 records in 11 tabellen van de projectenlijst, de monsterdatabase en de rapportenlijsten (DAN en DAR); de opgravingsdatabase van DB034 heeft zulke velden niet.

**De rest blijft gelijk.** De tekst van elk record blijft ongewijzigd: alleen de vijf waarden komen vóór het regeleinde van het record. De quoting van `mdb-export` (tekstvelden tussen aanhalingstekens, getallen zonder, lege velden voor NULL) blijft behouden en voor records zonder regeleinde in een veld is de CSV byte voor byte gelijk aan die van de vroegere `sed`-opdrachten. De vijf waarden worden, zoals `csv.writer` met `QUOTE_MINIMAL`, alleen tussen aanhalingstekens gezet als ze een komma, een aanhalingsteken of een regeleinde bevatten (met `"` → `""`). Bijzondere tekens in een tabelnaam of pad, zoals `&` en `\`, hebben geen speciale betekenis meer; met `sed` stonden de waarden in de vervangingstekst, waar `&` "de gevonden tekst" betekent, waardoor de Delftse tabel `AARDEWERK 1&2 VOORWERP` tot 21 oktober 2026 de waarde `AARDEWERK 12 VOORWERP` kreeg en de rijen geen `table`, `projectcd`, `loadtime` of `mdbfile` (net als dezelfde tabel in de projectenlijst en de rapportentabel `REEKS MENS & LANDSCHAP DELFTSE REGIO`).

**mongoimport.** `mongoimport --type csv` leest een gequote veld met regeleinden als één veld in. Een CR LF (het regeleinde van Access) binnen het veld wordt daarbij een LF; een losse CR blijft staan. Gequote en ongequote waarden worden hetzelfde ingelezen: `"123"` en `123` worden beide het getal 123, een leeg veld (ook `""`) wordt weggelaten (`--ignoreBlanks`). `projectcd` en `loadtime` blijven dus tekst, een numerieke projectcode wordt een getal en door de harmonisatie naar tekst omgezet.

**Tellen en fouten.** Het script schrijft het aantal datarecords naar stdout; `importMDB.sh` gebruikt dat als lengte van de tabel (een tabel zonder records wordt overgeslagen) en als `teller` in de metainfo (`Kolominformatie`). Voorheen was dat het aantal regels min één, dus te hoog bij tekstvelden met een regeleinde. Het bestand wordt regel voor regel gelezen en via een tijdelijk bestand in dezelfde map vervangen, zodat ook tabellen met tienduizenden rijen niet in het geheugen hoeven; bytes die geen geldig UTF-8 zijn blijven ongewijzigd. Mislukt het toevoegen, dan blijft het CSV-bestand ongewijzigd, meldt `importMDB.sh` een `ERROR` (ook in het encoding-foutenlog) en slaat het de tabel over.

Tests: `tests/unit/test_csv_kolommen.py` (het script, de vergelijking met de vroegere `sed`-regels en `importMDB.sh` als geheel met nagebootste mdbtools en mongoimport). De synthetische data heeft een memo-veld met een regeleinde (de beschrijving van spoor 4 van SY002); de integratietests controleren in de staging dat dat veld het regeleinde bevat en dat de extra kolommen in geen enkel ander veld staan, in de Delftse test ook het aantal records met een regeleinde per tabel.

### Controle van de Access-databases

De taak `Controleer_Databases` draait na alle MDB-taken en `Extract_ExtraProjecten`, en vóór de transformatie. Ze leest per categorie het log van `importMDB.sh` van deze run, telt per verwerkte database de staging-documenten en schrijft het resultaat in het run-document onder `tellingen.extractie`: onleesbare databases, databases zonder records, overgeslagen tabellen (met de reden: geen kopregel, kolommen toevoegen mislukt, `mongoimport` mislukt) en overige meldingen. Dat zijn waarschuwingen in het run-document en het verwerkingsrapport. Voor onleesbare databases geldt een drempel:

```
drempel = max(AIRFLOW_MAX_MISLUKTE_DATABASES, AIRFLOW_MAX_MISLUKTE_DATABASES_PCT % van de verwerkte databases)
```

met als standaard 2 databases en 5 procent. Daarboven faalt de taak en zet `Markeer_Run_Mislukt` de run op `mislukt`. De velden van `tellingen.extractie` staan in [Foutbeleid en verwerkingsrapport](verwerkingsrapport.md#controle-van-de-access-databases-controleer_databases).

## Excel-bestanden

| Bestand | Inhoud | Gebruik |
|---------|--------|---------|
| `FILE_ABREXCEL` (standaard `/input/referentietabellen/abr_versie_01122018.xlsx`) | Export van de ABR-thesaurus | Wordt de tabel `Def_ABR`; artefacten verwijzen ernaar |
| `FILE_EXTRA_PROJECTS` (standaard `/input/projectenlijst/Extra_projecten_tabel_OPGRAVINGEN.xlsx`) | Projecten die niet in de projectenlijst staan, in dezelfde kolommen als de tabel `OPGRAVINGEN` | Komen bij de projectenlijst in de staging; ontbreekt het bestand, dan slaat de taak het over |
| `FILE_IMPORT_FILES_EXCEL` (standaard `/input/referentietabellen/Alle Bestanden Archeologisch Depot.xlsx`) | Bestandenlijst van het depot (kolommen `Dir`, `Bestand`, `wel/niet`) | Extra afbeeldingen en rapporten die de extractie meeneemt (zie hieronder) |

Een onleesbaar ABR-bestand of een fout bij het inlezen van de extra projecten is cruciaal: zonder die gegevens is de rest van de verwerking onbruikbaar.

## Afbeeldingen en rapporten

Foto's, tekeningen en rapporten worden in de taakgroep `Extract_Group` verwerkt (`airflow_app/dags/wasstraat/image_import.py`). `GetAndStoreImageFilenames` zet alle te verwerken bestanden in de collectie `Filenames` (database `Arch_Files`) met `processed: False`; daarna verdelen acht parallelle taken `Extract_Data_From_Fotos_0` t/m `_7` de bestanden in blokken. Per bestand maakt `shared/image_util.adjustAndSaveFile` drie formaten in de uitvoermap (`AIRFLOW_OUTPUT_MEDIA`) en een document in `Plaatjes`.

**Selectie.** De extractie neemt uit de map met afbeeldingen (`AIRFLOW_INPUT_IMAGES`, in alle compose-bestanden de projectmap) en de map met rapporten (`AIRFLOW_INPUT_RAPPORTEN`) de bestanden met de extensie `.jpg`, `.jpeg`, `.gif`, `.png`, `.tif`, `.psd`, `.pdf`, `.jp2`, `.doc` of `.docx` waarvan het pad `velddocument`, `fotos` of `tekening` bevat (hoofdletterongevoelig) of een prefix uit `rapportcode_prefixen` in `correcties.yml` (hoofdlettergevoelig, zoals `DAR` en `DAN`). Daarbij komen de bestanden uit de bestandenlijst (`FILE_IMPORT_FILES_EXCEL`, rijen met `wel/niet` = 1) die in de map staan maar niet al geselecteerd zijn. Bestanden onder `paden_overslaan` vallen af. Zie [Configuratie: rapportcode_prefixen](configuratie.md#34-rapportcode_prefixen).

**Formaten per bestandstype.** Een foto of tekening krijgt een groot formaat (`<naam>.jpg`, hoogstens 7000 × 7000 pixels), een briefkaartformaat (`<naam>-med.jpg`, 1500 × 1000, gecentreerd op wit) en een thumbnail (`<naam>-sml.jpg`, 300 × 200). Bij een pdf is het groot formaat de pdf zelf en tonen de andere twee de eerste pagina (alleen die pagina wordt omgezet). Bij een Word-document (`.doc`, `.docx`) is het groot formaat het document zelf en tonen de andere twee een vast documenticoon:

| Onderdeel | Gedrag |
|-----------|--------|
| Documenticoon | `shared/afbeeldingen/document.png`, een neutraal icoon (een pagina met de tekst DOC, getekend met Pillow, geen merklogo). Het hoort bij de code en zit daarom in beide images: `/opt/airflow/dags/shared/afbeeldingen/` (Airflow) en `/app/app/shared/afbeeldingen/` (Flask, voor uploads). `FILE_WORD_ICON` in `shared/config.py` wijst er standaard naar; de gelijknamige omgevingsvariabele overschrijft het pad. Tot oktober 2026 stond de standaard op `/input/fotolijst/microsoft-word-logo.jpg` in de brondata, waar het bestand niet stond: alle Word-documenten mislukten. |
| EXIF-oriëntatie | Een foto die volgens zijn EXIF-gegevens gedraaid of gespiegeld moet worden, wordt eerst rechtgezet; de formaten in de mediamap bevatten geen EXIF meer. Tot oktober 2026 ging die informatie verloren en stonden zulke foto's op hun kant. |
| Kleurmodus | Een jpg kan alleen RGB of grijswaarden (L) bevatten. Alles daarbuiten wordt omgezet, op basis van de kleurmodus en niet van de extensie: een alfakanaal (RGBA, LA, of een palet met een transparante kleur, zoals in png, gif en psd) komt op een witte achtergrond; zwart-wit (1) wordt grijswaarden, zodat het verkleinen vloeiend gaat; 16-bits grijswaarden (I;16) worden geschaald naar 8 bits; overige modi (palet, CMYK, ...) worden RGB. Tot oktober 2026 werd alleen `.png` (in kleine letters) omgezet en gaven psd's met een alfakanaal `cannot write mode RGBA as JPEG`. |
| Afgekapte bestanden | Ontbreekt het einde van een afbeelding (`image file is truncated`), dan wordt ze toch geladen: het ontbrekende deel blijft grijs en het log van de import-taak krijgt een waarschuwing met de bestandsnaam. Een beschadigd voorbeeld is bruikbaarder dan geen voorbeeld, en het bronbestand blijft ongewijzigd; vervang het als er een goede versie is. |
| Beschadigde bestanden | Een afbeelding die niet te decoderen is (zoals `decoder error -2` bij een LZW-tif waarvan een strip niet goed eindigt), een bestand dat geen afbeelding is en een pdf die niet te lezen is of geen pagina oplevert, krijgen de status mislukt met een melding die het bestand en de oorzaak noemt (`AfbeeldingFout` in `shared/image_util.py`). |
| Geen projectcode | Een bestand waarvan het pad niet met een projectmap begint en waarvan de naam geen DAN of DAR bevat, blijft mislukt (`geen projectcode en geen rapportnummer`), zoals de Delftse `rapporten/DAR/Lijst met Delftse Archeologische Rapporten.doc`. |

**Status per bestand.** Na de import heeft elk document in `Filenames` precies één status:

| Status | Velden | Betekenis |
|--------|--------|-----------|
| verwerkt | `processed: true`, `verwerkt_op` | Opgeslagen in de uitvoermap en in `Plaatjes` |
| overgeslagen | `processed: true`, `verwerkt_op`, `overgeslagen: <reden>` | Bewust niet verwerkt. Redenen: `jpg-versie aanwezig` (een tif of pdf waarvan dezelfde naam als `.jpg` bestaat) en `sfeerfoto of niet-ondersteund bestandstype` (`adjustAndSaveFile` sloeg het bestand over, bijvoorbeeld een sfeerfoto met mensen) |
| mislukt | `processed: false`, `fout`, `fout_op` | De foutmelding (afgekapt op 2.000 tekens) en het tijdstip (UTC) van de laatste poging |
| onverwerkt | `processed: false`, geen `fout` | Nog niet aan de beurt geweest; hoort na de import-taken niet voor te komen |

Een mislukt bestand blijft op `processed: false` staan en wordt daarom opnieuw geprobeerd door een herhaling van de taak, door de DAG `Redo_Images` en door elke volgende incrementele run; lukt het dan wel, dan verdwijnen `fout` en `fout_op`. Tot oktober 2026 bleven mislukte én overgeslagen tif- en pdf-bestanden zonder onderscheid op `processed: false` staan en meldde niets dat er bestanden ontbraken.

**Harde fouten.** Een fout bij één bestand (onleesbaar of beschadigd bestand, geen projectcode in de naam) stopt de taak niet. Een fout waarbij elk volgend bestand ook zou mislukken wel: een vol volume (`ENOSPC`, `No space left on device`), een bereikt schijfquotum (`EDQUOT`), een alleen-lezen volume (`EROFS`) of geen schrijfrechten op de uitvoermap (een `PermissionError` op een pad onder `AIRFLOW_OUTPUT_MEDIA`; geen leesrechten op een bronbestand blijft een fout van dat ene bestand). Het bestand krijgt dan de status mislukt en de taak faalt direct, zonder herhalingen (`AirflowFailException`), met een melding die de uitvoermap noemt. De herkenning (`vindOnherstelbareOorzaak`) doorzoekt de hele keten van oorzaken, omdat `image_util` de oorspronkelijke fout in een nieuwe exception verpakt.

**Controle na de import.** De taak `Controleer_Afbeeldingen` draait na alle import-taken en vóór het einde van `Extract_Group`, dus vóór de transformatie. Ze telt de bestanden per status, logt het resultaat met de eerste tien foutmeldingen, en laat de DAG falen als het aantal mislukte plus onverwerkte bestanden groter is dan de drempel:

```
drempel = max(AIRFLOW_MAX_MISLUKTE_AFBEELDINGEN, AIRFLOW_MAX_MISLUKTE_AFBEELDINGEN_PCT % van het aantal bestanden)
```

Onder de drempel volgt een waarschuwing (`WARNING`) met de lijst. De taak zit in alle DAG's die afbeeldingen importeren: `Extract_Transform_Load_Full_Cycle`, `Extract_only` en `Extract_Transform_Load_Incremental` (via `Extract_Group.Controleer_Afbeeldingen`) en `Redo_Images` (`Controleer_Afbeeldingen`). In de volledige cyclus telt de controle alle bestanden in `Filenames`, in de incrementele cyclus alleen de bestanden die in deze run verwerkt of overgeslagen zijn plus de bestanden die nog openstaan. In beide cycli komen de tellingen in het run-document (`tellingen.afbeeldingen`, zie [Incrementeel laden](incrementeel-laden.md#run-document)) en worden mislukte of onverwerkte bestanden een melding: een waarschuwing onder de drempel, een fout erboven. Een mislukte controle zet de run via `Markeer_Run_Mislukt` op `mislukt`. `Extract_only` en `Redo_Images` hebben geen run-document; daar staat het resultaat alleen in het log.

| Omgevingsvariabele (Airflow) | Standaard | Betekenis |
|------------------------------|-----------|-----------|
| `AIRFLOW_MAX_MISLUKTE_AFBEELDINGEN` | `10` | Vast aantal mislukte bestanden dat nog acceptabel is |
| `AIRFLOW_MAX_MISLUKTE_AFBEELDINGEN_PCT` | `1` | Percentage van het aantal bestanden dat nog acceptabel is (decimaal mag, bijv. `0.5`) |

Beide staan in `config/airflow.env.example` (en `deploy/config/airflow.env.example`) en worden, net als de andere drempels, in `shared/config.py` ingelezen; een lege, ongeldige of negatieve waarde levert de standaard op. Met `0` en `0` is elke mislukte afbeelding een fout. Het vaste aantal beschermt kleine verzamelingen (de Delftse testdata: 541 bestanden, drempel 10), het percentage grote: bij ~100.000 foto's is de drempel 1.000, zodat een handvol beschadigde bestanden de cyclus niet stillegt, terwijl een structureel probleem (een ontbrekende map, een vol volume halverwege) wel opvalt.

**Na een mislukte controle.** Bekijk de mislukte bestanden in het log van `Controleer_Afbeeldingen` of in MongoDB (`db.Filenames.find({processed: false})` in `Arch_Files`). Herstel de oorzaak en draai `Redo_Images` (verwerkt alleen de openstaande bestanden) en daarna de transformatie en de load, of draai de cyclus opnieuw. Zijn de bestanden bekend en acceptabel, verhoog dan de drempel. Haal je in de incrementele cyclus een mislukt nieuw bestand weg voordat een run geslaagd is, dan ruimt de volgende run de openstaande entry in `Filenames` op (`voegImageFilenamesToe`).

## Paden overslaan

In de brondata staan soms kopieën van databases en afbeeldingen die niet als aparte bron mogen tellen. De extractie leest elke Access-database onder een invoermap in (`importMDB.sh`: `**/*.mdb` en `**/*.accdb`), dus zonder filter geeft zo'n kopie dubbele artefacten, sporen en vondsten. Het bekendste geval is de werkmap van Joris in DC024 (`DC024_Stadskantoor/K Overig/werkmap joris`): vijf Access-databases (`opgravingDC24.mdb`, `opgravingDC241.mdb`, `raapimport.accdb`, `test.mdb` en `C Database/DC24_STADSKANTOOR.mdb`), kopieën en tussenversies van de opgravingsdatabase in `C Database`. Op de productie-installatie leverden ze op 22 oktober 2026 17.128 rijen in de staging, 7.404 documenten in `Single_Store` en 6.663 artefacten die alleen uit deze kopieën kwamen (een vijfde van alle Delftse artefacten).

De sectie `paden_overslaan` in `correcties.yml` (zie [Configuratie: paden_overslaan](configuratie.md#35-paden_overslaan)) is een lijst met patronen van bestanden en mappen die de extractie overslaat:

```yaml
paden_overslaan:
  - "DC024_Stadskantoor/K Overig/werkmap joris"   # één map, met alles daaronder
  - "**/werkmap*"                                 # elke map die met werkmap begint, op elk niveau
  - "DC097_Ipse/C Database/HHD2.mdb"              # één bestand
```

| Onderdeel | Regel |
|-----------|-------|
| Vorm | Glob-patroon. `/` scheidt mappen (een `\` geldt ook als `/`); `*` staat voor een willekeurig deel van één naam, niet over een `/` heen; `?` voor één teken; `[abc]` en `[!abc]` voor een teken uit (of buiten) een reeks; `**` als hele naam voor nul of meer mappen |
| Waartegen | Het pad relatief aan de invoermap van het bestand: de projectmap (`AIRFLOW_INPUT_PROJECTEN`) voor de opgravingsdatabases, de map met afbeeldingen (`AIRFLOW_INPUT_IMAGES`), de map met rapporten, de monsterdatabase enzovoort. In de standaardopzet (Delft, synthetische data, `deploy/`) is de map met afbeeldingen dezelfde als de projectmap, zodat één patroon zowel de databases als de afbeeldingen in een projectmap dekt. Een `/` aan het begin of eind wordt genegeerd |
| Mappen | Een patroon dat een map aanwijst, geldt voor alles daaronder. Het patroon moet de hele naam van de map dekken: `DC024_Stadskantoor/K Overig/werkmap` slaat `werkmap joris` niet over, `DC024_Stadskantoor/K Overig/werkmap*` wel |
| Hoofdletters | Ongevoelig: `dc024_stadskantoor/k overig/WERKMAP JORIS` werkt ook |
| Fouten | Een sectie die geen lijst is, levert een foutmelding in het log op en er wordt niets overgeslagen; een element dat geen (niet-lege) tekst is of geen geldig patroon (zoals `[]`), wordt met een waarschuwing weggelaten. De rest van `correcties.yml` blijft werken |
| Standaard | Geen sectie of een lege lijst (`paden_overslaan: []`): er wordt niets overgeslagen |

**Waar het geldt.** Eén instelling dekt alle brontypen, met dezelfde functie (`airflow_app/dags/wasstraat/paden_overslaan.py`, `filterPaden`):

- **Access-databases** in de zes MDB-mappen: `importMDB.sh` geeft de gevonden bestanden (en in de incrementele cyclus de bestanden uit het lijstbestand) aan het script `airflow_app/scripts/paden_overslaan.py`, dat ze in Python filtert en de rest teruggeeft. Het script leest `correcties.yml` zelf (`AIRFLOW_CORRECTIES_CONFIG`). Gaat het filteren mis, dan stopt `importMDB.sh` met een `ERROR`: zonder filter zouden de kopieën stil worden ingelezen.
- **Registratie van bronbestanden** (incrementele cyclus en de taak `Registreer_Bronbestanden` van de volledige cyclus): `bronbestanden.zoekMdbBestanden` en `zoekAfbeeldingen` gebruiken dezelfde selectie als de extractie. Een overgeslagen bestand wordt niet geregistreerd. Een bestand dat al geregistreerd was en door een nieuw patroon buiten de selectie valt, geldt in de volgende incrementele run als verwijderd: `Opruimen_Oude_Records` haalt zijn rijen weg. Haal je een patroon weg, dan gelden de bestanden als nieuw.
- **Afbeeldingen en rapporten**: `image_import.getImageFilenames` (via `getImageNamesFromDir` voor de map met afbeeldingen en de map met rapporten, en `getImageNamesFromExcelAndDir` voor de bestandenlijst). Een overgeslagen bestand komt niet in `Filenames` en dus niet in `Plaatjes` of de mediamap. De bestandenlijst brengt een overgeslagen bestand niet terug. De filterpatronen voor rapporten (`rapportcode_prefixen`) werken zoals voorheen; `paden_overslaan` komt daar bovenop.

**Log en run-document.** Per overgeslagen bestand komt er een regel in het log van de taak (`Overgeslagen volgens paden_overslaan (patroon '...'): <pad>`), gevolgd door een telling per invoermap (`5 van 9 Access-databases in /input/projecten overgeslagen volgens paden_overslaan.`). Bij `importMDB.sh` staan die regels in het log van de taak `Extract_Data_From_<map>` (en in `AIRFLOW_LOGDIR/<collectie>.log`), bij de afbeeldingen in dat van `GetAndStoreImageFilenames`. De registratie schrijft de overgeslagen paden ook in het run-document (`Bepaal_Delta` in de incrementele cyclus, `Registreer_Bronbestanden` aan het eind van de volledige cyclus): `paden_overgeslagen` met per categorie de gesorteerde paden (hoogstens 1.000 per categorie) en `tellingen.paden_overgeslagen` met de aantallen per categorie en het totaal, bijvoorbeeld `{"projecten": 5, "totaal": 5}`. Het verwerkingsrapport kan ze daar lezen.

**Delft.** `data/delft/wasstraat_config/correcties.yml` slaat de werkmap van Joris over (de vijf databases; de overige 251 bestanden in die map, waaronder 4 jpg's, 2 tif's en 2 pdf's, vielen al buiten de selectie van afbeeldingen en rapporten). Een simulatie op de productie-installatie (alleen lezen, samen met de wijziging in het [samenvoegen van artefacten](transformatie.md#verplaatsen-en-samenvoegen-van-artefacten)) geeft bij de eerstvolgende volledige cyclus 22.551 artefacten in plaats van 32.527: 6.663 artefacten uit de werkmap en 3.313 losse exemplaren uit merge-groepen vervallen, geen enkel artefact krijgt een nieuw nummer. Andere soorten met rijen die alleen uit de werkmap kwamen: 272 sporen, 148 fotobeschrijvingen, 12 putten, 12 vlakken en 1 vulling; 143 bestanden (tekeningen) waren samengevoegd met rijen uit de werkmap en houden hun nummer via map en bestandsnaam (alle 143 uniek in `Def_Bestand`). Eén vondst krijgt eenmalig een nieuw nummer: het samengevoegde document van alle vondstrijen zonder key, dat bronrijen uit de werkmap verliest en daardoor een andere hulpsleutel krijgt. Niet in de werkmap maar mogelijk ook kopieën waren `B Arcview/opgravingDC24.mdb` (met onder meer `BOT`, `GLAS` en `KLEIPIJPEN`, die in de hoofddatabase ontbreken), `B Arcview/Database1.accdb` en `F Vondstmateriaal/Aardewerk/Aardewerk.accdb` (elk de tabel `Determinaties` met 880 rijen) in DC024, en `HHD2.mdb` en `dc79a1.mdb` naast `opgravingDC97.mdb` in `DC097_Ipse/C Database`. Besluit van de opdrachtgever (issue 86): de drie bestanden van DC024 zijn aanvullende bronnen en worden geladen; `HHD2.mdb` en `dc79a1.mdb` zijn tussenversies van `opgravingDC97.mdb` en staan in `paden_overslaan`. Daarmee vervallen bij de eerstvolgende volledige cyclus 115 artefacten, 182 sporen en 196 vullingen die alleen uit de tussenversies kwamen; de 533 artefacten en 351 vondsten die uit alle drie de bestanden waren samengevoegd, houden hun nummer via hun key. Let op: in `opgravingDC97.mdb` mist de tabel `AARDEWERK 1` de kolom `SUBNO` (108 rijen, in de tussenversies 114 met subnummer); die rijen worden zonder subnummer geladen. De Delftse testdata (`data/test`) heeft geen werkmap: `paden_overslaan: []`.

**Synthetische data.** `data/synthetic/data/projecten/SY001/K Overig/werkmap/` bevat een kopie van de database van SY001 en van foto `SY001_G001.jpg` (ook gemaakt door de generator, `WERKMAP_KOPIEEN`), en `data/synthetic/wasstraat_config/correcties.yml` slaat de map over (`SY001/K Overig/werkmap`). De integratietest controleert dat de staging, `Filenames` en `Plaatjes` niets uit de werkmap bevatten, dat beide bestanden als overgeslagen in het log van `Extract_only` staan en dat de registratie ze overslaat (`test_01d`, `test_01e`). Unit tests: `tests/unit/test_paden_overslaan.py` (patronen, foutieve waarden, het script, `importMDB.sh` met nep-MDB's, de registratie, de afbeeldingen en de configuraties in de repo) en `tests/unit/test_correcties_yml.py` (klasse `TestPadenOverslaan`).

## Samenvatting van de foutafhandeling

| Fout | Gevolg |
|------|--------|
| Onleesbare Access-database | Overgeslagen; waarschuwing via `Controleer_Databases`, boven de drempel stopt de run |
| Tabel die niet te exporteren is, database zonder records | Overgeslagen; waarschuwing |
| Tekst die geen UTF-8 is | Omgezet; mislukte omzettingen in het encoding-log |
| Bestand onder `paden_overslaan` | Overgeslagen met een logregel; in het run-document en het rapport |
| Onleesbare of beschadigde afbeelding, geen projectcode in de naam | Status `mislukt` in `Filenames`; waarschuwing via `Controleer_Afbeeldingen`, boven de drempel stopt de run |
| Vol of alleen-lezen mediavolume, geen schrijfrechten | De import-taak faalt direct, zonder herhalingen |
| ABR-bestand onleesbaar, fout in de extra projecten | De taak faalt, de run stopt |

Het volledige foutbeleid staat in [Foutbeleid en verwerkingsrapport](verwerkingsrapport.md).
