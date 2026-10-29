# Extractie

## Overzicht

De extractielaag vormt de ingangspoort van het Wasstraat Archeologische Data systeem. Dit onderdeel leest en verwerkt diverse bronformaten en maakt de data beschikbaar voor verdere verwerking in het systeem.

## Ondersteunde Bronformaten

De extractielaag kan gegevens inlezen uit een breed scala aan bronnen:

- **Excel-bestanden** (.xls, .xlsx)
- **Word-documenten** (.doc, .docx)
- **Access-databases** (.mdb, .accdb)
- **CSV-bestanden** (diverse scheidingstekens)
- **XML-bestanden**
- **Gescande documenten** (afbeeldingen, foto's)

## Kernfunctionaliteiten

### Zeichenkodering en Diacrieten

De extractielaag behandelt automatisch diverse tekencoderingsschema's (UTF-8, Latin-1, Windows-1252, etc.) en beheerst correct diakritische tekens (accenten, umlautsem, etc.). Dit is essentieel voor het verwerken van Nederlands-talige bronnen.

!!! tip "Tekenherkenning"
    Het systeem detecteert automatisch de tekencodering van bronbestanden en voert indien nodig conversies uit.

### Kopregel van Access-tabellen

`mdb-export` (mdbtools 1.0) zet de kolomnamen in de kopregel van de CSV-export niet tussen aanhalingstekens. Een kolomnaam met een komma, zoals `FORMAAT IN MM, HORIZONTAAL` in de tabel `MUNTEN EN PENNINGEN`, telde daardoor als twee velden: de kopregel had meer velden dan de rijen, `mongoimport --headerline` verschoof alle waarden en de velden die `importMDB.sh` achteraan toevoegt (`table`, `projectcd`, `bron`, `loadtime`, `mdbfile`) kwamen onder verkeerde namen terecht, zodat de tabel niet werd geharmoniseerd en de documenten niet herleidbaar waren tot hun bestand. `importMDB.sh` schrijft de kopregel daarom zelf (functie `export_table_to_csv`): de kolomnamen worden tab-gescheiden uit `mdb-export -d $'\t' -Q` gelezen en met Python's `csv.writer` waar nodig gequote; de data volgt daaronder via `mdb-export -H` (zonder kopregel).

### Extra kolommen per record

Na de encoding-conversie voegt `importMDB.sh` aan de CSV-export de kolommen `table`, `projectcd`, `bron`, `loadtime` en `mdbfile` toe: de kolomnamen achter de kopregel, de waarden achter elk datarecord. Dat doet het Python-script `airflow_app/scripts/csv_kolommen.py`, dat naast `importMDB.sh` staat (in de Airflow-image via de `COPY` van `airflow_app/scripts`, in de ontwikkel- en testomgevingen via de mount van die map).

**Record, geen regel.** Een tekstveld met een regeleinde (een memo-veld in Access, bijvoorbeeld `KAARTBLAD` in de tabel `OPGRAVINGEN` van de Delftse projectenlijst) staat in de export tussen aanhalingstekens en beslaat meer regels. `csv_kolommen.py` leest de export met de `csv`-module, die bepaalt waar een record eindigt, en zet de waarden alleen aan het einde van het record. Tot issue 74 deed `importMDB.sh` dit met `sed`, per regel: de waarden kwamen dan ook achter elke regel binnen het tekstveld terecht (bijvoorbeeld `"37E,OPGRAVINGEN,DELF,..."` gevolgd door de rest van het veld). Het aantal velden per record klopte nog, dus de tellingen waren gelijk, maar de inhoud van die tekstvelden was vervuild. In de Delftse testdata ging het om 42 records in 11 tabellen van de projectenlijst, de monsterdatabase en de rapportenlijsten (DAN en DAR); de opgravingsdatabase van DB034 heeft zulke velden niet.

**De rest blijft gelijk.** De tekst van elk record blijft ongewijzigd: alleen de vijf waarden komen vóór het regeleinde van het record. De quoting van `mdb-export` (tekstvelden tussen aanhalingstekens, getallen zonder, lege velden voor NULL) blijft behouden en voor records zonder regeleinde in een veld is de CSV byte voor byte gelijk aan die van de vroegere `sed`-opdrachten. De vijf waarden worden, zoals `csv.writer` met `QUOTE_MINIMAL`, alleen tussen aanhalingstekens gezet als ze een komma, een aanhalingsteken of een regeleinde bevatten (met `"` → `""`). Bijzondere tekens in een tabelnaam of pad, zoals `&` en `\`, hebben geen speciale betekenis meer; met `sed` stonden de waarden in de vervangingstekst, waar `&` "de gevonden tekst" betekent, waardoor de Delftse tabel `AARDEWERK 1&2 VOORWERP` tot 21 oktober 2026 de waarde `AARDEWERK 12 VOORWERP` kreeg en de rijen geen `table`, `projectcd`, `loadtime` of `mdbfile` (net als dezelfde tabel in de projectenlijst en de rapportentabel `REEKS MENS & LANDSCHAP DELFTSE REGIO`).

**mongoimport.** `mongoimport --type csv` leest een gequote veld met regeleinden als één veld in. Een CR LF (het regeleinde van Access) binnen het veld wordt daarbij een LF; een losse CR blijft staan. Gequote en ongequote waarden worden hetzelfde ingelezen: `"123"` en `123` worden beide het getal 123, een leeg veld (ook `""`) wordt weggelaten (`--ignoreBlanks`). `projectcd` en `loadtime` blijven dus tekst, een numerieke projectcode wordt een getal en door de harmonisatie naar tekst omgezet.

**Tellen en fouten.** Het script schrijft het aantal datarecords naar stdout; `importMDB.sh` gebruikt dat als lengte van de tabel (een tabel zonder records wordt overgeslagen) en als `teller` in de metainfo (`Kolominformatie`). Voorheen was dat het aantal regels min één, dus te hoog bij tekstvelden met een regeleinde. Het bestand wordt regel voor regel gelezen en via een tijdelijk bestand in dezelfde map vervangen, zodat ook tabellen met tienduizenden rijen niet in het geheugen hoeven; bytes die geen geldig UTF-8 zijn blijven ongewijzigd. Mislukt het toevoegen, dan blijft het CSV-bestand ongewijzigd, meldt `importMDB.sh` een `ERROR` (ook in het encoding-foutenlog) en slaat het de tabel over.

Tests: `tests/unit/test_csv_kolommen.py` (het script, de vergelijking met de vroegere `sed`-regels en `importMDB.sh` als geheel met nagebootste mdbtools en mongoimport). De synthetische data heeft een memo-veld met een regeleinde (de beschrijving van spoor 4 van SY002); de integratietests controleren in de staging dat dat veld het regeleinde bevat en dat de extra kolommen in geen enkel ander veld staan, in de Delftse test ook het aantal records met een regeleinde per tabel.

### Afbeeldingen en rapporten

Foto's, tekeningen en rapporten worden in de taakgroep `Extract_Group` verwerkt (`airflow_app/dags/wasstraat/image_import.py`). `GetAndStoreImageFilenames` zet alle te verwerken bestanden in de collectie `Filenames` (database `Arch_Files`) met `processed: False`; daarna verdelen acht parallelle taken `Extract_Data_From_Fotos_0` t/m `_7` de bestanden in blokken. Per bestand maakt `shared/image_util.adjustAndSaveFile` drie formaten in de uitvoermap (`AIRFLOW_OUTPUT_MEDIA`) en een document in `Plaatjes`.

**Formaten per bestandstype.** Een foto of tekening krijgt een groot formaat (`<naam>.jpg`, hoogstens 7000 × 7000 pixels), een briefkaartformaat (`<naam>-med.jpg`, 1500 × 1000, gecentreerd op wit) en een thumbnail (`<naam>-sml.jpg`, 300 × 200). Bij een pdf is het groot formaat de pdf zelf en tonen de andere twee de eerste pagina (alleen die pagina wordt omgezet). Bij een Word-document (`.doc`, `.docx`) is het groot formaat het document zelf en tonen de andere twee een vast documenticoon (issue 82):

| Onderdeel | Gedrag |
|-----------|--------|
| Documenticoon | `shared/afbeeldingen/document.png`, een neutraal icoon (een pagina met de tekst DOC, getekend met Pillow, geen merklogo). Het hoort bij de code en zit daarom in beide images: `/opt/airflow/dags/shared/afbeeldingen/` (Airflow) en `/app/app/shared/afbeeldingen/` (Flask, voor uploads). `FILE_WORD_ICON` in `shared/config.py` wijst er standaard naar; de gelijknamige omgevingsvariabele overschrijft het pad. Tot issue 82 stond de standaard op `/input/fotolijst/microsoft-word-logo.jpg` in de brondata, waar het bestand niet stond: alle Word-documenten mislukten. |
| EXIF-oriëntatie | Een foto die volgens zijn EXIF-gegevens gedraaid of gespiegeld moet worden, wordt eerst rechtgezet; de formaten in de mediamap bevatten geen EXIF meer. Tot issue 82 ging die informatie verloren en stonden zulke foto's op hun kant. |
| Kleurmodus | Een jpg kan alleen RGB of grijswaarden (L) bevatten. Alles daarbuiten wordt omgezet, op basis van de kleurmodus en niet van de extensie: een alfakanaal (RGBA, LA, of een palet met een transparante kleur, zoals in png, gif en psd) komt op een witte achtergrond; zwart-wit (1) wordt grijswaarden, zodat het verkleinen vloeiend gaat; 16-bits grijswaarden (I;16) worden geschaald naar 8 bits; overige modi (palet, CMYK, ...) worden RGB. Tot issue 82 werd alleen `.png` (in kleine letters) omgezet en gaven psd's met een alfakanaal `cannot write mode RGBA as JPEG`. |
| Afgekapte bestanden | Ontbreekt het einde van een afbeelding (`image file is truncated`), dan wordt ze toch geladen: het ontbrekende deel blijft grijs en het log van de import-taak krijgt een waarschuwing met de bestandsnaam. Een beschadigd voorbeeld is bruikbaarder dan geen voorbeeld, en het bronbestand blijft ongewijzigd; vervang het als er een goede versie is. |
| Beschadigde bestanden | Een afbeelding die niet te decoderen is (zoals `decoder error -2` bij een LZW-tif waarvan een strip niet goed eindigt), een bestand dat geen afbeelding is en een pdf die niet te lezen is of geen pagina oplevert, krijgen de status mislukt met een melding die het bestand en de oorzaak noemt (`AfbeeldingFout` in `shared/image_util.py`). |
| Geen projectcode | Een bestand waarvan het pad niet met een projectmap begint en waarvan de naam geen DAN of DAR bevat, blijft mislukt (`geen projectcode en geen rapportnummer`), zoals de Delftse `rapporten/DAR/Lijst met Delftse Archeologische Rapporten.doc`. |

**Status per bestand.** Na de import heeft elk document in `Filenames` precies één status (issue 70):

| Status | Velden | Betekenis |
|--------|--------|-----------|
| verwerkt | `processed: true`, `verwerkt_op` | Opgeslagen in de uitvoermap en in `Plaatjes` |
| overgeslagen | `processed: true`, `verwerkt_op`, `overgeslagen: <reden>` | Bewust niet verwerkt. Redenen: `jpg-versie aanwezig` (een tif of pdf waarvan dezelfde naam als `.jpg` bestaat) en `sfeerfoto of niet-ondersteund bestandstype` (`adjustAndSaveFile` sloeg het bestand over, bijvoorbeeld een sfeerfoto met mensen) |
| mislukt | `processed: false`, `fout`, `fout_op` | De foutmelding (afgekapt op 2.000 tekens) en het tijdstip (UTC) van de laatste poging |
| onverwerkt | `processed: false`, geen `fout` | Nog niet aan de beurt geweest; hoort na de import-taken niet voor te komen |

Een mislukt bestand blijft op `processed: false` staan en wordt daarom opnieuw geprobeerd door een herhaling van de taak, door de DAG `Redo_Images` en door elke volgende incrementele run; lukt het dan wel, dan verdwijnen `fout` en `fout_op`. Vóór issue 70 bleven mislukte én overgeslagen tif- en pdf-bestanden zonder onderscheid op `processed: false` staan en meldde niets dat er bestanden ontbraken.

**Harde fouten.** Een fout bij één bestand (onleesbaar of beschadigd bestand, geen projectcode in de naam) stopt de taak niet. Een fout waarbij elk volgend bestand ook zou mislukken wel: een vol volume (`ENOSPC`, `No space left on device`), een bereikt schijfquotum (`EDQUOT`), een alleen-lezen volume (`EROFS`) of geen schrijfrechten op de uitvoermap (een `PermissionError` op een pad onder `AIRFLOW_OUTPUT_MEDIA`; geen leesrechten op een bronbestand blijft een fout van dat ene bestand). Het bestand krijgt dan de status mislukt en de taak faalt direct, zonder herhalingen (`AirflowFailException`), met een melding die de uitvoermap noemt. De herkenning (`vindOnherstelbareOorzaak`) doorzoekt de hele keten van oorzaken, omdat `image_util` de oorspronkelijke fout in een nieuwe exception verpakt.

**Controle na de import.** De taak `Controleer_Afbeeldingen` draait na alle import-taken en vóór het einde van `Extract_Group`, dus vóór de transformatie. Ze telt de bestanden per status, logt het resultaat met de eerste tien foutmeldingen, en laat de DAG falen als het aantal mislukte plus onverwerkte bestanden groter is dan de drempel:

```
drempel = max(AIRFLOW_MAX_MISLUKTE_AFBEELDINGEN, AIRFLOW_MAX_MISLUKTE_AFBEELDINGEN_PCT % van het aantal bestanden)
```

Onder de drempel volgt een waarschuwing (`WARNING`) met de lijst. De taak zit in alle DAG's die afbeeldingen importeren: `Extract_Transform_Load_Full_Cycle`, `Extract_only` en `Extract_Transform_Load_Incremental` (via `Extract_Group.Controleer_Afbeeldingen`) en `Redo_Images` (`Controleer_Afbeeldingen`). In de incrementele cyclus tellen alleen de bestanden die in deze run verwerkt of overgeslagen zijn plus de bestanden die nog openstaan, en komen de tellingen ook in het run-document (`tellingen.afbeeldingen`, zie [Incrementeel laden](incrementeel-laden.md#run-document)); een mislukte controle zet de run via `Markeer_Run_Mislukt` op `mislukt`.

| Omgevingsvariabele (Airflow) | Standaard | Betekenis |
|------------------------------|-----------|-----------|
| `AIRFLOW_MAX_MISLUKTE_AFBEELDINGEN` | `10` | Vast aantal mislukte bestanden dat nog acceptabel is |
| `AIRFLOW_MAX_MISLUKTE_AFBEELDINGEN_PCT` | `1` | Percentage van het aantal bestanden dat nog acceptabel is (decimaal mag, bijv. `0.5`) |

Beide staan in `config/airflow.env.example` (en `deploy/config/airflow.env.example`); een lege, ongeldige of negatieve waarde levert de standaard op. Met `0` en `0` is elke mislukte afbeelding een fout. Het vaste aantal beschermt kleine verzamelingen (de Delftse testdata: 541 bestanden, drempel 10), het percentage grote: bij ~100.000 foto's is de drempel 1.000, zodat een handvol beschadigde bestanden de cyclus niet stillegt, terwijl een structureel probleem (een ontbrekende map, een vol volume halverwege) wel opvalt.

**Na een mislukte controle.** Bekijk de mislukte bestanden in het log van `Controleer_Afbeeldingen` of in MongoDB (`db.Filenames.find({processed: false})` in `Arch_Files`). Herstel de oorzaak en draai `Redo_Images` (verwerkt alleen de openstaande bestanden) en daarna de transformatie en de load, of draai de cyclus opnieuw. Zijn de bestanden bekend en acceptabel, verhoog dan de drempel. Haal je in de incrementele cyclus een mislukt nieuw bestand weg voordat een run geslaagd is, dan ruimt de volgende run de openstaande entry in `Filenames` op (`voegImageFilenamesToe`).

### Paden overslaan (issue 84)

In de brondata staan soms kopieën van databases en afbeeldingen die niet als aparte bron mogen tellen. De extractie leest elke Access-database onder een invoermap in (`importMDB.sh`: `**/*.mdb` en `**/*.accdb`), dus zonder filter geeft zo'n kopie dubbele artefacten, sporen en vondsten. Het bekendste geval is de werkmap van Joris in DC024 (`DC024_Stadskantoor/K Overig/werkmap joris`): vijf Access-databases (`opgravingDC24.mdb`, `opgravingDC241.mdb`, `raapimport.accdb`, `test.mdb` en `C Database/DC24_STADSKANTOOR.mdb`), kopieën en tussenversies van de opgravingsdatabase in `C Database`. Op de productie-installatie leverden ze op 22 oktober 2026 17.128 rijen in de staging, 7.404 documenten in `Single_Store` en 6.663 artefacten die alleen uit deze kopieën kwamen (een vijfde van alle Delftse artefacten).

De sectie `paden_overslaan` in `correcties.yml` (zie [Transformatie: datacorrecties](transformatie.md#datacorrecties-yaml)) is een lijst met patronen van bestanden en mappen die de extractie overslaat:

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

**Delft.** `data/delft/wasstraat_config/correcties.yml` slaat de werkmap van Joris over (de vijf databases; de overige 251 bestanden in die map, waaronder 4 jpg's, 2 tif's en 2 pdf's, vielen al buiten de selectie van afbeeldingen en rapporten). Een simulatie op de productie-installatie (alleen lezen, samen met [issue 83](transformatie.md#10-verplaatsen-en-samenvoegen-van-artefacten-issue-83)) geeft bij de eerstvolgende volledige cyclus 22.551 artefacten in plaats van 32.527: 6.663 artefacten uit de werkmap en 3.313 losse exemplaren uit merge-groepen vervallen, geen enkel artefact krijgt een nieuw nummer. Andere soorten met rijen die alleen uit de werkmap kwamen: 272 sporen, 148 fotobeschrijvingen, 12 putten, 12 vlakken en 1 vulling; 143 bestanden (tekeningen) waren samengevoegd met rijen uit de werkmap en houden hun nummer via map en bestandsnaam (alle 143 uniek in `Def_Bestand`). Eén vondst krijgt eenmalig een nieuw nummer: het samengevoegde document van alle vondstrijen zonder key, dat bronrijen uit de werkmap verliest en daardoor een andere hulpsleutel krijgt. Niet in de werkmap maar mogelijk ook kopieën: `B Arcview/opgravingDC24.mdb` (met onder meer `BOT`, `GLAS` en `KLEIPIJPEN`, die in de hoofddatabase ontbreken), `B Arcview/Database1.accdb` en `F Vondstmateriaal/Aardewerk/Aardewerk.accdb` (elk de tabel `Determinaties` met 880 rijen) in DC024, en `HHD2.mdb` en `dc79a1.mdb` naast `opgravingDC97.mdb` in `DC097_Ipse/C Database` (hun artefacten worden samengevoegd, zie issue 83). Of die ook overgeslagen moeten worden, is een vraag voor de opdrachtgever. De Delftse testdata (`data/test`) heeft geen werkmap: `paden_overslaan: []`.

**Synthetische data.** `data/synthetic/data/projecten/SY001/K Overig/werkmap/` bevat een kopie van de database van SY001 en van foto `SY001_G001.jpg` (ook gemaakt door de generator, `WERKMAP_KOPIEEN`), en `data/synthetic/wasstraat_config/correcties.yml` slaat de map over (`SY001/K Overig/werkmap`). De integratietest controleert dat de staging, `Filenames` en `Plaatjes` niets uit de werkmap bevatten, dat beide bestanden als overgeslagen in het log van `Extract_only` staan en dat de registratie ze overslaat (`test_01d`, `test_01e`). Unit tests: `tests/unit/test_paden_overslaan.py` (patronen, foutieve waarden, het script, `importMDB.sh` met nep-MDB's, de registratie, de afbeeldingen en de configuraties in de repo) en `tests/unit/test_correcties_yml.py` (klasse `TestPadenOverslaan`).

### Formaatdetectie

Op basis van bestandsextensies en bestandsinhoud detecteert het systeem automatisch welke parser moet worden gebruikt. Dit maakt handmatige configuratie overbodig in veel gevallen.

### Import-Modi

#### Eenmalige Imports
Geschikt voor enkelvoudige databronnen die eenmalig moeten worden ingelezen.

```python
from extractie import Extractor

extractor = Extractor()
data = extractor.extract_once('bron_data.xlsx')
```

#### Periodieke Imports
Voor bronnen die regelmatig worden bijgewerkt, ondersteunt de extractielaag geplande imports:

- Dagelijkse synchronisatie
- Wekelijkse updates
- Maandelijkse integratieprocessen

!!! info "Planning"
    Periodieke imports kunnen worden geconfigureerd via het configuratiemodule van Wasstraat Archeologische Data.

## Architectuur

```
┌─────────────────────────────────┐
│     Diverse Bronformaten        │
│  (Excel, Word, Access, CSV etc) │
└────────────┬────────────────────┘
             │
             ▼
┌─────────────────────────────────┐
│   Formaatdetectie & Parsing     │
│  (Python-gebaseerde Parser)     │
└────────────┬────────────────────┘
             │
             ▼
┌─────────────────────────────────┐
│ Tekencodering Normalisatie      │
│  (UTF-8, Diakritische tekens)   │
└────────────┬────────────────────┘
             │
             ▼
┌─────────────────────────────────┐
│   Geïntegreerde Datasets        │
└─────────────────────────────────┘
```

## Verwerkingsflow

1. **Brondetectie**: Identificatie van het brontype en bestandsindeling
2. **Parsing**: Omzetting van het bronformat naar interne representatie
3. **Normalisatie**: Harmonisering van tekencodering en diakritische tekens
4. **Validatie**: Eerste controle op structuur en integriteit
5. **Opslag**: Doorgifte naar de SingleStore laag

## Best Practices

!!! warning "Gegevenskwaliteit"
    Zorg ervoor dat bronbestanden consistent zijn geformatteerd. Inconsistenties kunnen tot gevolg hebben dat de extractie minder accuraat verloopt.

- Controleer bronbestanden op typografische fouten voordat deze worden ingeladen
- Vermijd speciale karakters in kolomnamen waar mogelijk
- Zorg voor consistente datuumnotaties (aanbevolen: ISO 8601 formaat: YYYY-MM-DD)

## Foutafhandeling

De extractielaag implementeert robuuste foutafhandeling:

- **Encoding-fouten**: Automatische fallback naar alternatieve coderingsschema's
- **Parsing-fouten**: Gedetailleerde foutmeldingen met regelreferenties
- **Structuurfouten**: Waarschuwingen voor onverwachte bestandsstructuren
- **Kopieën van databases en afbeeldingen**: bestanden en mappen uit `paden_overslaan` in `correcties.yml` worden overgeslagen, met een logregel per bestand (zie [Paden overslaan](#paden-overslaan-issue-84))
- **Afbeeldingen en rapporten**: status per bestand in `Filenames`, een harde fout bij een vol of niet-schrijfbaar mediavolume en een drempel op het aantal mislukte bestanden (taak `Controleer_Afbeeldingen`, zie [Afbeeldingen en rapporten](#afbeeldingen-en-rapporten))

!!! error "Kritieke Fouten"
    Bij kritieke fouten wordt het importproces gestopt en ontvangt de beheerder een gedetailleerde foutrapport.
