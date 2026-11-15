# Validatie en kwaliteitscontroles

De Wasstraat heeft geen aparte validatielaag met inhoudelijke regels; zo'n laag is een [ambitie](../toekomstvisie.md#validatie-met-regels). Wel controleert de pipeline op verschillende plaatsen of de brondata te verwerken is, telt ze wat niet lukt en legt ze dat vast in het run-document en het verwerkingsrapport. Deze pagina zet die controles op een rij; het beleid (wanneer een fout de run stopt) staat in [Foutbeleid en verwerkingsrapport](verwerkingsrapport.md).

## Overzicht

| Stap | Controle | Gevolg | Zichtbaar in |
|------|----------|--------|--------------|
| Extractie | Is de Access-database leesbaar (`mdb-tables`)? | Onleesbaar: overgeslagen | Log van `importMDB.sh`; `Controleer_Databases` |
| Extractie | Heeft een tabel een kopregel, lukt het toevoegen van de kolommen en `mongoimport`? | Tabel overgeslagen | idem |
| Extractie | Is de export geldige UTF-8? | Omzetting vanuit de gedetecteerde codering, anders Windows-1252 en ISO-8859-1 | `<collectie>_encoding_errors.log` in `AIRFLOW_LOGDIR` |
| Extractie | Valt een bestand onder `paden_overslaan`? | Overgeslagen, met een logregel | Log, run-document (`paden_overgeslagen`), rapport |
| Extractie | Is elke afbeelding en elk rapport te verwerken? | Status `mislukt` met de oorzaak; bij een vol of alleen-lezen mediavolume stopt de taak direct | `Filenames`, `Controleer_Afbeeldingen` |
| Na de extractie | Aantal onleesbare databases en mislukte afbeeldingen | Waarschuwing; boven de drempel stopt de run | Run-document (`tellingen.extractie`, `tellingen.afbeeldingen`), rapport |
| Transform 1 | Bestaat elke soort uit `meta.py` in de harmonisatie-Excel? | Nee: de taak `Harmonize_<soort>` faalt | Log |
| Transform 1 | Is een bestandsnaam van een foto, tekening of rapport te herkennen? | Nee: soort `Bestand`, fototype `N` | Rapport (`onherkende_bestandsnamen`) |
| Transform 2 | Kan elk document worden opgeschoond? | Nee: het document blijft ongewijzigd en komt in `_processing_errors`; boven de drempel stopt de run | `_processing_errors`, rapport (`verwerkingsfouten`) |
| Transform 2 | Liggen de Rijksdriehoek-coördinaten in Nederland (x tussen 10.000 en 280.000, y tussen 300.000 en 625.000) en zijn ze te lezen? | Nee: de locatie wordt weggelaten en het document krijgt een veld `error` | `Single_Store`, rapport (`locatiefouten`) |
| Transform 1 en 2 | Is het gemeenteprofiel (`WASSTRAAT_GEMEENTE`) bekend? | Nee: `ParseFotobestanden` faalt; in Transform 2 faalt elk document en stopt de drempel op verwerkingsfouten de run | Log, `_processing_errors` |
| Transform 3 | Komt een vondstnummer in een project in meer putten voor? | Ja: het putnummer komt in de sleutel van de vondst (`vondstkey_met_putnr`) | Sleutels |
| Transform 4 | Behoudt elke rij zijn `primary_key`? | Hernummerde rijen geven een waarschuwing | Run-document (`sleutels_niet_stabiel`), rapport |
| Laden | Past elke waarde in de kolom? | Tekst wordt afgekapt op de lengte van de kolom, getallen en datums omgezet, een lege enumwaarde wordt `Onbekend` | – |
| Laden | Kloppen de foreign keys na het laden? | Ze worden hersteld als `NOT VALID` en daarna gevalideerd. Lukt het herstel niet, dan is dat in de volledige cyclus een waarschuwing en in de incrementele cyclus een rollback en een fout; lukt het valideren niet, dan is dat een waarschuwing | Run-document, rapport (`fk`) |
| Laden | Verwijst gebruikersdata naar een verdwenen rij? | Losgekoppeld met een markering of verwijderd | Rapport (`gebruikersdata`) |
| Laden | Rijen zonder `key` in PostgreSQL | Geteld | Rapport (`rijen_zonder_key`) |

## Coördinaten

Projecten (en vindplaatsen) hebben Rijksdriehoek-coördinaten in de brondata. Transform 2 controleert of ze binnen de grenzen van Nederland vallen en rekent ze om naar WGS84 (`wasstraat/rijksdriehoek.py`) voor de kaart. Een project met een lege, onleesbare of buitenlandse coördinaat houdt geen locatie en staat niet op de kaart; het document krijgt een veld `error` met type `Afwijkende locatie` of `Ongeldige coordinaat`. In de webapplicatie kun je een project ook zonder locatie aanmaken.

## Records die niet te verwerken zijn

Faalt het opschonen van één document in Transform 2 (bijvoorbeeld een onverwachte waarde in een veld), dan blijft het document zoals het was en komt het met de fout en de fase in de collectie `_processing_errors` (database `Arch_Analyse`). De rest van de run gaat door. Per taak geldt de drempel `AIRFLOW_MAX_VERWERKINGSFOUTEN` (standaard 100) of `AIRFLOW_MAX_VERWERKINGSFOUTEN_PCT` (standaard 1 procent van de bekeken documenten), welke het grootst is; daarboven stopt de run. Het verwerkingsrapport telt de fouten per fase, soort en fouttype, met voorbeelden.

## Controles in de webapplicatie

De webapplicatie controleert invoer in de formulieren van Flask-AppBuilder: verplichte velden, typen en de keuzelijsten van enums. Bij een artefact controleert `ABRCompare_Artefactsoort` (`app/app/validators.py`) of het gekozen ABR-materiaal past bij de artefactsoort. Wijzigingen in de webapplicatie aan tabellen van de pipeline gaan bij de volgende cyclus verloren; alleen de gebruikerstabellen blijven staan (zie [Gegevensmodel](../architectuur/gegevensmodel.md#gebruikerstabellen)).

## Controles op de uitkomst

De integratietests leggen de uitkomst van de pipeline vast en vergelijken elke run daarmee:

- met de synthetische data: verwachte aantallen per soort, unieke sleutels, gekoppelde foto's, de werking van `correcties.yml`, stabiele `primary_key`s over de cycli heen, Elasticsearch gelijk aan PostgreSQL;
- met de Delftse testdata: Delft-specifieke verwachte aantallen in de test, en een referentie-uitkomst (`tests/integration/fixtures/delft_golden_snapshot.json`) met tellingen per soort en voorbeeldsleutels. `tests/integration/test_delft_referentie.py` vergelijkt elke run daarmee en noemt elk verschil; een verandering moet per verschil worden verklaard voordat de referentie opnieuw wordt vastgelegd (`tests/integration/snapshot_mongodb.py referentie`, zie [Testen](../testen.md#delft-specifiek-echte-data)).

Zie [Testen](../testen.md).
