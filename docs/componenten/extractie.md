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

Daarna voegt `importMDB.sh` met twee `sed`-opdrachten de kolommen `table`, `projectcd`, `bron`, `loadtime` en `mdbfile` toe: de waarden achter elke datarij, de kolomnamen achter de kopregel. De tabelnaam, projectcode, tijdstempel en het pad stonden eerder letterlijk in de vervangingstekst van `sed`, waar `&` "de gevonden tekst" betekent en `\` een escape-teken is. De Delftse tabel `AARDEWERK 1&2 VOORWERP` (96 rijen in DB034) kreeg zo de waarde `AARDEWERK 12 VOORWERP`, de kopregel werd niet vervangen en de documenten kregen geen `table`, `projectcd`, `loadtime` of `mdbfile`; ze werden niet geharmoniseerd en de incrementele cyclus kon ze niet opruimen. Hetzelfde gold voor dezelfde tabel in de projectenlijst (`DELF-IT.mdb`, 96 rijen) en voor de rapportentabel `REEKS MENS & LANDSCHAP DELFTSE REGIO` (16 rijen); die tabellen worden niet geharmoniseerd, dus daar worden alleen de staging-velden goed. De functie `escape_sed_csv_value` maakt de waarden nu veilig voor `sed` (`\` → `\\`, `&` → `\&`, `/` → `\/`) en zet een waarde met een komma of aanhalingsteken tussen dubbele aanhalingstekens, met `"` → `""` (zoals `csv.writer` met `QUOTE_MINIMAL`), zodat een komma of aanhalingsteken in een tabelnaam of pad geen extra veld oplevert. Andere waarden blijven ongequote, zodat de CSV voor gewone tabelnamen en paden byte voor byte gelijk blijft. Altijd quoten kan niet: `sed` werkt per regel en zet de waarden ook achter elke regel binnen een tekstveld met een regeleinde (bijvoorbeeld in de tabel `OPGRAVINGEN` van de Delftse projectenlijst); een `"` daar maakt de CSV ongeldig en `mongoimport` weigert dan de hele tabel. De kopregel-`sed` gebruikt de waarden niet meer. `mongoimport` leest gequote en ongequote waarden hetzelfde in: `projectcd` en `loadtime` blijven tekst (een numerieke projectcode wordt net als voorheen een getal en door de harmonisatie naar tekst omgezet).

!!! warning "Tekstvelden met een regeleinde"
    Omdat `sed` per regel werkt, komen de toegevoegde waarden in een tekstveld met een regeleinde ook midden in dat veld terecht (bijvoorbeeld `"37E,OPGRAVINGEN,DELF,..."` gevolgd door de rest van het veld). Dat gedrag bestond al vóór deze wijziging en is ongewijzigd; het record zelf krijgt de juiste waarden aan het einde. Een tabelnaam of pad met een komma of aanhalingsteken in een tabel met zulke tekstvelden levert wel een ongeldige CSV op; dat komt in de huidige data niet voor.

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
