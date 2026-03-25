# Incrementeel laden (delta-verwerking)

## Is your feature request related to a problem? Please describe.

De Wasstraat ondersteunt uitsluitend een volledige run waarbij alle databases worden leeggemaakt en opnieuw opgebouwd vanuit de bronbestanden. Bij ~1 TB aan data is dat voor het toevoegen van een handvol nieuwe opgravingen disproportioneel. Er is geen mogelijkheid om aanvullingen (nieuwe projecten, vondsten, foto's) toe te voegen aan een bestaande, draaiende database.

## Describe the solution you'd like

Een incrementeel laadmechanisme waarbij aangeboden bronbestanden als delta worden behandeld: alles wat wordt aangeboden wordt verwerkt en samengevoegd met de bestaande data. Dit geldt voor alle objecttypen (Project, Vondst, Artefact, Foto, etc.).

1. **Bestandsregistratie met hash** — Bij elke verwerking wordt een SHA-256 hash van het bronbestand opgeslagen (nieuwe tabel `Def_Bronbestand` met `bestandsnaam`, `sha256`, `verwerkingsdatum`, `status`, `aantal_records`). Bij een volgende aanbieding bepaalt de hash het scenario:
   - *Nieuw bestand* (onbekende naam) — Volledig verwerken en samenvoegen.
   - *Gewijzigd bestand* (zelfde naam, andere hash) — Oude records van dit bestand verwijderen, opnieuw verwerken.
   - *Ongewijzigd bestand* (zelfde hash) — Overslaan.
2. **Incrementele transformatie** — De transform-stappen (harmonize, enhance, keys, merge) draaien alleen op de aangeboden delta-data en voegen het resultaat samen met de bestaande analyse-collectie.
3. **Upsert in plaats van replace** — PostgreSQL-load via `INSERT ... ON CONFLICT ... DO UPDATE` in plaats van volledige tabelswap. Elasticsearch via incrementele bulk-upsert in plaats van volledige herindexering.
4. **Stabiele sleutels** — Composite keys en integer `primary_key` blijven stabiel tussen runs, zodat foreign keys en externe referenties niet breken.

## Describe alternatives you've considered

De kernvraag is welke datalaag de bron van waarheid is bij het samenvoegen van delta-data met bestaande data.

### A. MongoDB staging als bron van waarheid

Nieuwe bestanden importeren in de bestaande staging-collecties (zonder `dropAll`). Het `mdbfile`-veld en de bestandshash markeren welke documenten bij welk bronbestand horen. Bij een gewijzigd bestand: oude documenten met dat `mdbfile` verwijderen, nieuwe importeren. Alleen de nieuwe/gewijzigde documenten door de transformatie-pipeline sturen en via `$merge` samenvoegen met `COLL_ANALYSE_CLEAN`.

*Voordeel:* de staging-laag bevat altijd de volledige ruwe data en is herstelbaar.
*Nadeel:* de merge-stap (`$group`) werkt nu alleen op documenten binnen dezelfde aggregation pipeline — nieuwe records vinden hun bestaande duplicaten niet zonder aanpassing.

### B. PostgreSQL als bron van waarheid

De bestaande PostgreSQL-data als leidend beschouwen. Nieuwe brondata transformeren en via upsert direct in PostgreSQL laden. Bij een gewijzigd bestand: oude records (traceerbaar via `herkomst`-veld) verwijderen en vervangen.

*Voordeel:* simpelste model voor de load-fase; geen MongoDB-synchronisatieprobleem.
*Nadeel:* de volledige transformatielogica is nu in MongoDB-aggregaties geschreven; die moet deels herschreven worden of je accepteert dat MongoDB en PostgreSQL tijdelijk uit sync zijn.

### C. Hybride: MongoDB voor transformatie, PostgreSQL voor persistentie

MongoDB staging en analyse worden gebruikt als werkgeheugen voor de transformatie van de delta. Na transformatie worden de resultaten via upsert naar PostgreSQL geschreven. MongoDB wordt niet als langetermijnopslag behandeld en mag na succesvolle load worden opgeschoond.

*Voordeel:* bestaande transformatielogica blijft grotendeels intact; PostgreSQL is de single source of truth.
*Nadeel:* bij een gewijzigd bestand moet je de oude records uit `COLL_ANALYSE_CLEAN` pre-fetchen om de merge correct uit te voeren.

### Vergelijking

| Aspect | A (Mongo = waarheid) | B (PG = waarheid) | C (Hybride) |
|---|---|---|---|
| Bestandshash-registratie | In MongoDB | In PostgreSQL | In PostgreSQL |
| Bestaande transformatielogica | Grotendeels herbruikbaar | Herschrijven vereist | Grotendeels herbruikbaar |
| Merge/dedup bij delta | Aanpassing nodig | In SQL (nieuw) | Aanpassing nodig |
| Consistentie Mongo↔PG | Gegarandeerd | PG leidend, Mongo disposable | PG leidend, Mongo tijdelijk |
| Herstelbaarheid | Volledige rebuild vanuit staging | Rebuild vereist re-import | Rebuild vereist re-import |

**Aanbeveling:** optie C. PostgreSQL is de bron van waarheid (daar draait de applicatie op), MongoDB dient als werkgeheugen voor transformatie.

## Additional context

### Grootste technische uitdaging

De merge-stap (Transform5) is de kernblokkade. De huidige `$group`-aggregatie in MongoDB veronderstelt dat alle duplicaten van een entiteit in dezelfde pipeline zitten. Bij incrementeel laden moet de merge-stap:

- Bestaande records met dezelfde composite key ophalen uit `COLL_ANALYSE_CLEAN`
- Deze combineren met de nieuwe delta-records
- De `brondata`-array aanvullen (niet vervangen)
- Het samengevoegde resultaat terugschrijven

Dit vereist een aanpassing van `merge_functions.py`: van een enkelvoudige `$group`-aggregatie naar een twee-staps-proces (pre-fetch bestaand + merge met nieuw).

### Huidige pipeline (full-batch)

De huidige pipeline doorloopt deze stappen, elk met full-batch aannames:

1. `dropAll()` — dropt MongoDB staging, files en analyse databases
2. Extract — volledige MDB-import via `mongoimport --mode upsert` (maar met auto-generated `_id`)
3. Transform1-5 — MongoDB-aggregaties op complete collecties
4. Load — PostgreSQL tabelswap via temp-tabellen (`Def_*_new` → `Def_*`); `primary_key` wordt sequentieel opnieuw toegekend
5. Index — Elasticsearch volledige herindexering met alias-swap

### Voorbeeld bestandshash-registratie

```
Def_Bronbestand
├── id: 1
├── bestandsnaam: "opgravingDC036.mdb"
├── sha256: "a3f2b8c..."
├── verwerkingsdatum: "2026-03-14T10:30:00"
├── status: "verwerkt"
└── aantal_records: 1247
```

### Relatie met andere issues

Hangt samen met het profielensysteem (sleutelafleiding moet stabiel zijn tussen runs), het externaliseren van hard-coded Delft-logica (correctieregels moeten ook incrementeel toepasbaar zijn), en de Docker productie-deployment (containers moeten volumes mounten voor het aanbieden van nieuwe bronbestanden).
