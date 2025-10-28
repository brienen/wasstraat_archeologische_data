# Architectuurpatronen in Wasstraat

De Wasstraat implementeert een aantal klassieke software-architectuurpatronen. Het volgende geeft een overzicht van hoe elk patroon wordt gebruikt en welke trade-offs hieraan verbonden zijn.

## ETL Pipeline Pattern

### Beschrijving
Het systeem volgt klassiek Extract-Transform-Load model: data komt uit diverse bronnen, wordt getransformeerd en geladen in centrale opslag.

### Implementatie in Wasstraat
- **Extract**: Format-specifieke extractoren lezen XML, JSON, CSV, etc.
- **Transform**: Regelmotor past transformatieregels toe, valideert tegen schema's
- **Load**: Data wordt opgeslagen in SingleStore (MongoDB/PostgreSQL hybrid)

### Voordelen
- Duidelijke scheiding van concerns
- Hergebruik van individuele stappen
- Eenvoudig debuggen van fouten (in welke fase treedt het op?)
- Mogelijk incrementele processing

### Trade-offs
- Performance-overhead door stap-sequentialisatie
- Staging area-vereisten (temp storage)
- Complexiteit in foutafhandeling en rollback
- Moeilijk real-time streaming te integreren

---

## Mediator Pattern

### Beschrijving
Een centrale component coördineert interactie tussen meerdere systemen zonder directe koppeling.

### Implementatie in Wasstraat
**SingleStore** functioneert als centrale mediator:
- Diverse databronnen (XML files, Delft GIS, monument registers) koppelen op SingleStore
- Applicaties (Fasttext search, Crossviews, API) queuren SingleStore
- SingleStore synchronized tussen MongoDB (document storage) en PostgreSQL (relational queries)

### Voordelen
- Losse koppeling tussen bronnen en consumenten
- Centralisatie van data-governance
- Eenvoudig nieuwe bronnen toe te voegen
- Één place of truth voor metadata

### Trade-offs
- SingleStore zelf wordt een kritieke bottleneck
- Complexe synchronisatieproblemen (NoSQL-relational mismatch)
- Performance-overhead van indirection layer
- Monitoring wordt complex (waar loopt het fout?)

---

## Observer Pattern

### Beschrijving
Componenten registreren zich voor events en worden genotificeerd wanneer bepaalde acties plaatsvinden.

### Implementatie in Wasstraat
- Transformatie-stappen "observeren" valideringsresultaten
- Logging- en monitoring-systemen observeren data-flow events
- Cache-invalidatie wordt getriggerd door data-updates
- Audit logs registreren alle wijzigingen

### Voordelen
- Losse koppeling tussen event-bron en listeners
- Eenvoudig nieuwe monitoring toe te voegen
- Audit trail gegarandeerd
- Asynchrone verwerking mogelijk

### Trade-offs
- Moeilijkheid in debugging (impliciete kontrol flow)
- Order-afhankelijkheid tussen observers
- Memory overhead voor observer-registratie
- Event-verlies als systeem crasht

---

## Strategy Pattern

### Beschrijving
Verschillende algoritmen kunnen gekozen worden runtime, bepaald door een context-parameter.

### Implementatie in Wasstraat
- **Per gegevenstype**: Verschillende transformatie-strategieën voor XML vs. CSV vs. JSON
- **Per validatie-regel**: Verschillende validators voor verschillende veldtypen
- **Per export-format**: Verschillende serializers (JSON, RDF, GeoJSON)

Voorbeeld: Bij inlezen XML volgt strategy X, bij JSON volgt strategy Y.

### Voordelen
- Pluggable, uitbreidbaar ontwerp
- Runtime keuze van implementatie
- Testbaar (elke strategy apart)
- Eenvoudig nieuwe varianten toe te voegen

### Trade-offs
- Overhead van strategy-selectie
- Kan tot code-duplication leiden (boilerplate)
- Moeilijker voor gebruikers om "juiste" strategy te kiezen
- Inconsistentie mogelijk als strategies niet goed gecoördineerd zijn

---

## Repository Pattern

### Beschrijving
Een centrale repository bevat alle metadata en schema's, waarvan koppelingen naar deze centrale autoriteit worden gebruikt.

### Implementatie in Wasstraat
- **Metaschema repository**: Centrale plaats waar data-modellen (Delft-specifiek, ABR, CIDOC CRM) zijn opgeslagen
- **Transformatie-regels**: Centraal repository van alle transformatie-logica
- **Validatie-schemas**: Centraal beheerde validatie-definiëring

### Voordelen
- Eenduidelheid van definities
- Versionering van schema's mogelijk
- Audit trail van wijzigingen
- Hergebruik across projects

### Trade-offs
- Centralisatie kan bottleneck worden
- Wijzigingen in repository beïnvloeden alles
- Versie-compatibiliteit lastig
- Performance bij regelmatige metadata-lookups

---

## Adapter Pattern

### Beschrijving
Adapters converteren interfaccen van incompatibele klasses.

### Implementatie in Wasstraat
- **Format-adapters**: Elk inkomend format (XML, JSON, CSV) heeft eigen adapter
- **Database-adapters**: OneSQL adapter voor MongoDB, ander voor PostgreSQL
- **Legacy-adapters**: Adapters voor oude Delft-systemen
- **Standard-adapters**: Adapters voor ABR, Archis API's

### Voordelen
- Compatibiliteit met meerdere externe systemen
- Centralisatie van conversie-logica
- Eenvoudig nieuwe formaten toe te voegen
- Bestaande code hoeft niet aangepast

### Trade-offs
- Adapter-laag zelf kan fouten introduceren
- Performance-overhead door conversies
- Dual maintenance (original + adapter code)
- Risico op data-verlies bij conversie

---

## Cache-Aside Pattern

### Beschrijving
Applicatie vraagt data op, controleert cache, en vult cache bij miss.

### Implementatie in Wasstraat
- Validatieresultaten worden gecached
- Frequente queries (Fulltext search) gebruiken cache voor snelle responses
- Transform-stappen cachen intermediate results

Flow:
1. Request voor validatie-resultaat
2. Check cache
3. Bij miss: bereken resultaat, sla op in cache
4. Terugkeren resultaat

### Voordelen
- Snellere herhaalde requests
- Flexibel invalidatie-beleid
- Kan eenvoudig ingekapseld
- Laag overhead bij cache-hit

### Trade-offs
- Stale data risico (inconsistentie)
- Cache-invalidatie is lastig
- Multi-threading synchronisatie nodig
- Meer geheugen nodig

---

## Configuration-Driven Processing

### Beschrijving
Gedrag wordt bepaald door configuratieparameters, niet hardcoded.

### Implementatie in Wasstraat
- Transformatie-regels zijn opgeslagen in JSON/YAML configuratie
- Validatie-regels kunnen per project worden ingesteld
- Field mappings zijn configurable
- Output-formaten kunnen geconfigureerd worden

### Voordelen
- Eenvoudig aanpassen voor nieuwe use-cases
- Geen code-wijzigingen nodig
- Non-technische gebruikers kunnen aanpassen
- Audit trail van configuratie-wijzigingen

### Trade-offs
- Complexe configuratie-structuren lastig uit te leggen
- Validatie van configuratie-syntaxis nodig
- Performance overhead van configuratie-parsing
- Debugging van "wat doet deze configuratie?" lastig

---

## Polyglot Persistence

### Beschrijving
Verschillende datastore-types worden gebruikt voor verschillende doeleinden.

### Implementatie in Wasstraat
- **MongoDB**: Opslag van ruwe, semi-gestructureerde XML/JSON documenten
- **PostgreSQL**: Gestructureerde, gerelateerde data voor queries
- **Fulltext index**: Geoptimaliseerd voor text search
- Mogelijk **Oracle**: Legacy Delft-systeem compatibiliteit

### Voordelen
- Elk systeem optimaal voor zijn use-case
- Heterogene data-modellen kunnen coëxisteren
- Flexibiliteit in data-design
- Performance optimalisering per store-type

### Trade-offs
- Synchronisatie-complexiteit (NoSQL ≠ Relational)
- Transactie-semantiek lastig (geen ACID across stores)
- Operationele complexiteit (meerdere systemen onderhouden)
- Data-migration tussen stores lastig
- Query-planning wordt complex

---

## Event-Driven Processing

### Beschrijving
Systeem reageert op events (data-aankomst, transformatie-voltooiing, etc.) met asynchrone verwerking.

### Implementatie in Wasstraat
- Transformatie-engine (Airflow/Celery) verwerkt jobs event-driven
- Data-import triggert validatie-jobs
- Validatie-fouten triggeren alert-events
- Cache-invalidatie gebeurt via events

### Voordelen
- Asynchrone, non-blocking verwerking
- Scalability door queue-based architecture
- Retry-logica eenvoudig implementeren
- Parallelle verwerking van meerdere events

### Trade-offs
- Eventual consistency i.p.v. immediate
- Moeilijkheid in error handling (gedistribueerde transacties)
- Debugging van asynchrone flows lastig
- Verstaan van event-flow vereist mentaal model

---

## Samenvatting van Pattern-Interacties

| Pattern | Primair Voordeel | Primair Risico |
|---------|-------------------|-----------------|
| ETL Pipeline | Modulair, debugbaar | Sequential bottleneck |
| Mediator | Losse koppeling | Single point of failure |
| Observer | Extensible monitoring | Implicit control flow |
| Strategy | Runtime flexibiliteit | Overhead, inconsistentie |
| Repository | Eenheidsmateriaal | Centraal bottleneck |
| Adapter | Format-flexibiliteit | Conversie-fouten |
| Cache-Aside | Performance | Stale data, sync-problemen |
| Config-Driven | Flexibiliteit | Complexe configuration |
| Polyglot Persistence | Optimale per-tool | Sync-complexiteit |
| Event-Driven | Schaalbare async | Debugging-moeilijkheid |

Deze patronen interacteren: het Mediator Pattern (SingleStore) combineert met Polyglot Persistence (MongoDB + PostgreSQL), terwijl Event-Driven Processing via de Observer Pattern operationalisatie mogelijk maakt.
