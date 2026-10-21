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
- **Afbeeldingen en rapporten**: status per bestand in `Filenames`, een harde fout bij een vol of niet-schrijfbaar mediavolume en een drempel op het aantal mislukte bestanden (taak `Controleer_Afbeeldingen`, zie [Afbeeldingen en rapporten](#afbeeldingen-en-rapporten))

!!! error "Kritieke Fouten"
    Bij kritieke fouten wordt het importproces gestopt en ontvangt de beheerder een gedetailleerde foutrapport.
