# Zoeken en indexering

De webapplicatie zoekt met Elasticsearch 8.17 in de tekst van de tabellen in PostgreSQL. De pipeline bouwt de zoekindex op na het laden; de webapplicatie werkt hem bij als gebruikers iets wijzigen. De code staat in `shared/fulltext.py` (indexeren), `app/app/search.py` en `app/app/filters.py` (zoeken).

## Wat er in de index staat

- **Eén index per `Def_`-tabel.** De webapplicatie zoekt via een alias met de tabelnaam in kleine letters, bijvoorbeeld `def_artefact`. Achter de alias staat een index met een tijdstempel (`def_artefact_1761733500`), zodat een nieuwe index kan worden opgebouwd terwijl de oude in gebruik is.
- **Eén document per rij**, met de `primary_key` als document-id.
- **De tekstkolommen** (`text`, `varchar` en enum) van de tabel, als tekst. De kolommen uit `SKIP_FULLTEXT` in `shared/const.py` (`_id`, `herkomst`, `key`, `brondata`, `vindplaats`) blijven buiten de index. Getallen en datums worden niet geïndexeerd.
- **Geen eigen mapping**: Elasticsearch gebruikt zijn standaardanalyse.

Niet geïndexeerd worden `Def_Bronbestand` (administratie van de pipeline, `PIPELINE_TABELLEN`) en de koppeltabellen zonder `primary_key` (`Def_artefact_abr`, `Def_artefact_conservering`).

## Indexering door de pipeline

| Functie | Gebruikt door | Werking |
|---------|---------------|---------|
| `indexTable(table)` | Volledige cyclus en `DAG_Load_Only` (taken `Index_<tabel>`, voor alle `Def_`-tabellen behalve de bovengenoemde), en de webapplicatie bij het opstarten | Bouwt een nieuwe index `<alias>_<tijdstempel>` met alle rijen en zet de alias daarna in één keer om; de oude index wordt verwijderd. Mislukt het vullen, dan wordt de nieuwe index weggegooid en blijft de oude in gebruik |
| `indexTableIncrementeel(table)` | Incrementele cyclus (taken `Index_<tabel>` na `Load_Upsert`, alleen voor `LOAD_TABELLEN`) | Indexeert alle rijen van de tabel opnieuw in de bestaande index achter de alias (een document met dezelfde id wordt overschreven) en verwijdert daarna de documenten waarvan de id niet meer als `primary_key` in de tabel staat. Bestaat de alias nog niet, of wijst hij naar meer dan één index, dan volgt een volledige indexering met `indexTable` |

Omdat de `primary_key`s stabiel zijn, blijven de document-id's in de index gelijk tussen cycli. De Index-taken staan buiten de bewaking van de run: mislukt de indexering, dan klopt PostgreSQL al, is de mislukte taak een waarschuwing in het run-document en het verwerkingsrapport, en slaagt de DAG. Herstel: draai de mislukte Index-taak opnieuw (taak wissen in Airflow) of `DAG_Load_Only`; de volgende incrementele run indexeert ook weer alle rijen. Zie [Foutbeleid en verwerkingsrapport](verwerkingsrapport.md).

## Indexering door de webapplicatie

- **Bij het opstarten** (`app/app/init.py`, `initIfNotInit`): bestaat de index `def_artefact` niet, dan indexeert de webapplicatie alle tabellen (`indexAll`). Een nieuwe installatie is zo doorzoekbaar zodra Flask voor het eerst start na een load.
- **Bij wijzigingen**: maakt, wijzigt of verwijdert een gebruiker een rij in de webapplicatie, dan werkt de webapplicatie het document in de index bij (`search.add_to_index` en `search.remove_from_index`, aangeroepen vanuit `interface.py`) en leegt ze de cache van de zoekresultaten.

## Zoeken in de webapplicatie

Op de lijstpagina's staat het filter **Fulltext Zoeken** (`FulltextFilter` in `filters.py`). Het zoekt in alle tekstkolommen van de tabel, of in één kolom als je het filter op die kolom zet. De zoekopdracht gaat als `query_string` naar Elasticsearch, dus de syntaxis van Lucene werkt:

| Voorbeeld | Betekenis |
|-----------|-----------|
| `kogelpot` | Het woord, in elk tekstveld |
| `kogel*` | Woorden die met `kogel` beginnen |
| `kogelpot~` | Ook woorden die er één of twee letters van verschillen |
| `"rood aardewerk"` | De woorden achter elkaar |
| `baksel:rood AND vorm:kom` | In bepaalde velden, met `AND`, `OR` en `NOT` |

De webapplicatie haalt hoogstens 1.000 treffers op, voegt ze via de `primary_key` samen met de rijen uit PostgreSQL en sorteert op relevantie; de gevonden woorden worden gemarkeerd. In de lijst van één artefactsoort (zoals Aardewerk) zoekt hij alleen artefacten van die soort, in de lijst van één bestandsoort alleen bestanden van die soort. De resultaten worden in Redis gecachet (`CACHE_DEFAULT_TIMEOUT`, standaard 300 seconden) en bij een wijziging in de index geleegd.

## Configuratie

| Instelling | Waar | Standaard |
|------------|------|-----------|
| Adres van Elasticsearch | `ES_HOST` (Airflow en Flask) | `http://elasticsearch:9200` |
| Geheugen | `ES_JAVA_OPTS` in het compose-bestand; in de live installatie `WASSTRAAT_ES_GEHEUGEN` | 512 MB |
| Beveiliging | `xpack.security.enabled=false`, single-node | uit; in de live installatie zonder hostpoort |
| Kolommen buiten de index | `SKIP_FULLTEXT` in `shared/const.py` | zie boven |

Zie [Configuratie](configuratie.md).

## Controleren

In de ontwikkelomgeving heeft Elasticsearch hostpoort 9200:

```bash
curl -s "http://localhost:9200/_cat/aliases?v"            # alias per tabel
curl -s "http://localhost:9200/_cat/indices?v"            # indexen en aantallen
curl -s "http://localhost:9200/def_artefact/_count"       # aantal artefacten in de index
```

In de live installatie en de testomgevingen heeft Elasticsearch geen hostpoort; gebruik daar `docker exec`:

```bash
docker exec wasstraat_elasticsearch curl -s "http://localhost:9200/_cat/indices?v"
```

Het aantal documenten per index hoort gelijk te zijn aan het aantal rijen in de tabel; de integratietests controleren dat na elke run.

## Testen

- `tests/unit/test_load_incrementeel.py`: `indexTableIncrementeel` met een nagebootste Elasticsearch.
- `tests/unit/test_load_volledig.py`: `indexTable` slaat koppeltabellen zonder `primary_key` over.
- `tests/unit/test_flask_search.py`: het zoeken in de webapplicatie zonder Elasticsearch-verbinding.
- `tests/unit/test_elasticsearch_testomgeving.py`: beide testomgevingen hebben een eigen Elasticsearch zonder hostpoort.
- `tests/integration/test_incremental_synthetic_data.py` en `test_full_pipeline_delft_data.py`: na elke run zijn de aantallen en id's in Elasticsearch gelijk aan PostgreSQL.
