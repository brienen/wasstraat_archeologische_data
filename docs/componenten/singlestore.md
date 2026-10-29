# MongoDB en Single_Store

MongoDB is het werkgeheugen van de pipeline. Alle brondata komt eerst ongewijzigd in MongoDB, wordt daar geharmoniseerd, aangevuld, van sleutels voorzien en samengevoegd, en gaat pas aan het eind naar PostgreSQL. MongoDB past daarbij omdat elke bron andere kolommen heeft: een document hoeft geen vast schema te volgen, en alle soorten (vondsten, sporen, artefacten van elk materiaal, foto's) kunnen in één collectie staan.

`Single_Store` en `Single_Store_Clean` zijn de twee centrale collecties: geen apart product, maar gewone MongoDB-collecties in de database `Arch_Analyse`.

## Databases en collecties

De namen zijn instelbaar in `config/mongo.env` (zie [Configuratie](configuratie.md#24-databases-postgresenv-mongoenv-redisenv)); hieronder staan de standaardnamen.

| Database | Collectie | Inhoud | Geschreven door |
|----------|-----------|--------|-----------------|
| `Arch_Staging` | `Staging_Projecten_Oud` | Alle rijen uit de opgravingsdatabases, één document per rij | `Extract_Data_From_Projecten` |
| | `Staging_Projecten_Projectenlijst`, `_Magazijnlijst`, `_Fotolijst`, `_Monster` | De centrale lijsten (projectenlijst plus de extra projecten uit Excel, magazijnlijst, fotocatalogus, monsterdatabase) | `Extract_Data_From_<map>`, `Extract_ExtraProjecten` |
| | `Staging_Rapporten` | Rijen uit de rapportendatabases | `Extract_Data_From_RapportaneDBs` |
| | `Staging_Referentietabellen` | De ABR-thesaurus | `Extract_Referentietabellen` |
| | `Kolominformatie` | Per geïmporteerde tabel de kolommen en het aantal records | `importMDB.sh` |
| | `Plaatjes` | Per verwerkt bestand de metadata en de paden van de drie formaten in de mediamap | `Extract_Data_From_Fotos_*` |
| | `Verwerkingsruns` | Het run-document van elke run (status, meldingen, tellingen, rapport) | De taken van de cycli; blijft staan bij `Drop_All_Databases` |
| | `Verwerkingsrun_Bestanden` | De vingerafdrukken per bestand per incrementele run | `Bepaal_Delta` |
| `Arch_Files` | `Filenames` | De te verwerken afbeeldingen en rapporten, met hun status (verwerkt, overgeslagen, mislukt) | `GetAndStoreImageFilenames`, `Extract_Data_From_Fotos_*` |
| `Arch_Analyse` | `Single_Store` | Alle geharmoniseerde documenten | Transform 1, aangevuld door Transform 2 en 3 |
| | `Single_Store_Clean` | De verplaatste en samengevoegde documenten met sleutels en verwijzingen; de bron van de laadstap | Transform 5 en 4 |
| | `_processing_errors` | Documenten die Transform 2 niet kon verwerken, met de fout | `Enhance_All_Attributes`, `extract_Imagedata_From_FileNames` |

De afbeeldingen zelf staan niet in MongoDB maar als bestanden in de mediamap (`AIRFLOW_OUTPUT_MEDIA`); `Plaatjes` en `Def_Bestand` bevatten de paden.

## Documenten in de staging

`importMDB.sh` exporteert elke tabel naar CSV en laadt die met `mongoimport`. Elk document is één rij met de kolomnamen uit Access als veldnamen, plus vijf velden:

| Veld | Inhoud |
|------|--------|
| `table` | Naam van de Access-tabel; de harmonisatie-Excel herkent tabellen hierop |
| `projectcd` | Projectcode: het begin van de eerste map onder de invoermap, zolang het uit hoofdletters en cijfers bestaat (`DB008_Leeuwenstein` → `DB008`) |
| `bron` | `opgraving<projectcd>` |
| `loadtime` | Tijdstip van het inlezen |
| `mdbfile` | Pad van het bronbestand in de container |

Lege velden worden weggelaten. Waarden worden ingelezen zoals ze er staan; correcties op de staging gebeuren alleen met `brondata_correcties` uit `correcties.yml`.

## Documenten in Single_Store

Transform 1 maakt van elk staging-document een document in `Single_Store`, met hetzelfde `_id`:

```json
{
  "_id": "…",
  "soort": "Artefact",
  "artefactsoort": "Aardewerk",
  "projectcd": "DB034",
  "putnr": "10",
  "vondstnr": "460",
  "subnr": "1",
  "baksel": "…",
  "abr_materiaal": "https://data.cultureelerfgoed.nl/term/id/abr/…",
  "brondata": { "table": "AARDEWERK 1", "mdbfile": "/input/projecten/…/opgravingDB34.mdb", "PUT": 10, "VONDST": 460, "…": "…" }
}
```

| Veld | Komt van |
|------|----------|
| `soort`, `artefactsoort`, `abr_materiaal`, `abr_submateriaal` en de geharmoniseerde velden | Transform 1, volgens de harmonisatie-Excel of een vaste pipeline in `meta.py` |
| `brondata` | Het volledige staging-document |
| Opgeschoonde waarden (getallen, ja/nee, datums), dateringen als jaartallen (`vondstdatering_vanaf`, `_tot`, ...), `latitude`, `longitude`, `coor_wgs` | Transform 2 |
| `error` | Transform 2, bij een locatie buiten Nederland of een onleesbare coördinaat |
| `key`, `key_<soort>` (zoals `key_vondst`, `key_put`), bij artefacten `key_subnr`; de vlag `vondstkey_met_putnr` | Transform 3 |
| `delta_run` | Alleen in de incrementele cyclus: het run-id van de run die het document (opnieuw) harmoniseerde |

Foto's, tekeningen en rapporten komen niet uit de staging-collecties maar uit `Plaatjes` en de fotocatalogus: `ParseFotobestanden` leidt hun soort en nummers af uit de bestandsnaam (gemeenteprofiel en `rapportcode_prefixen`).

## Documenten in Single_Store_Clean

Transform 5 zet de documenten over naar `Single_Store_Clean`, per soort op een van drie manieren:

| Manier | Taken | Resultaat |
|--------|-------|-----------|
| Verplaatsen | `Move_<soort>` | Eén op één, met hetzelfde `_id` |
| Samenvoegen | `Merge_<soort>` (Vondst, Artefact, Monster, Tekening, Rapport), `MergeFotoinfo` | Documenten met dezelfde sleutel worden één document: de velden van alle bronrijen samen, alle bronrijen in `brondata` (een lijst) en hun aantal in `brondata_count`. Het `_id` is dat van de laatste bronrij |
| Aanmaken | `Generate_Missing_<soort>` (Put, Vlak, Spoor, Vondst, Doos) | Een document voor elke put, elk vlak, spoor, vondst of doos die alleen als nummer in andere documenten voorkomt; `brondata.table` is dan `generated_<soort>` |

Daarna geeft Transform 4 elk document een integer-sleutel `ID` (in PostgreSQL `primary_key`, stabiel tussen cycli) en de verwijzingen `<soort>ID` naar de documenten waarnaar het verwijst. De laadstap neemt van elk document alleen de velden mee die als kolom in de `Def_`-tabel bestaan.

Beide collecties hebben een index op `soort` en `key` (taken `Set_Index_SingleStore` en `Set_Index_SingleStoreClean`).

## Levensduur

| Cyclus | MongoDB |
|--------|---------|
| Volledige cyclus | `Drop_All_Databases` leegt alle drie de databases, behalve `Verwerkingsruns`; alles wordt opnieuw opgebouwd |
| Incrementele cyclus | Niets wordt geleegd. Records van gewijzigde en verwijderde bronbestanden worden opgeruimd (`Opruimen_Oude_Records`), de nieuwe worden toegevoegd en alleen de geraakte sleutels worden opnieuw samengevoegd. `Single_Store` is daardoor altijd volledig. Zie [Incrementeel laden](incrementeel-laden.md) |
| `DAG_Load_Only` | Leest alleen `Single_Store_Clean` |

`make backup` dumpt de drie databases met `mongodump`; een volledige cyclus kan ze ook altijd opnieuw maken uit de brondata.

## Zelf bekijken

```bash
docker exec -it wasstraat_mongo mongosh --username root --password <wachtwoord> --authenticationDatabase admin
```

Het wachtwoord staat in `config/mongo.env` (`MONGO_INITDB_ROOT_PASSWORD`).

```javascript
use Arch_Analyse
// Aantal documenten per soort
db.Single_Store_Clean.aggregate([{ $group: { _id: "$soort", n: { $sum: 1 } } }, { $sort: { _id: 1 } }])
// Een vondst op sleutel, met zijn bronrijen
db.Single_Store_Clean.findOne({ soort: "Vondst", key: "PDB034P10V460" })
// Documenten met een locatiefout
db.Single_Store.find({ error: { $exists: true } }, { projectcd: 1, error: 1 })
// Records die Transform 2 niet kon verwerken
db._processing_errors.find().limit(5)

use Arch_Staging
// De laatste runs
db.Verwerkingsruns.find({}, { run_id: 1, soort: 1, status: 1, melding: 1 }).sort({ gestart_op: -1 }).limit(5)
```
