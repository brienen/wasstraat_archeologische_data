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
