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

!!! error "Kritieke Fouten"
    Bij kritieke fouten wordt het importproces gestopt en ontvangt de beheerder een gedetailleerde foutrapport.
