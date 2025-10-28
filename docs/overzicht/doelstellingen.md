# Doelstellingen: Onze Ambities

## Kernvisie

Wasstraat streeft ernaar om archeologische data-integratie van een moeizame, handmatige bezigheid om te vormen naar een **generieke, configureerbare toolbox** die meerdere Nederlandse gemeenten kan bedienen.

## Strategische Doelen

### 1. Generieke en Configureerbare Aanpak

**Doel:** Het systeem moet werk voor diverse gemeenten, zonder dat de code voor elk geval opnieuw geschreven hoeft te worden.

**Implementatie:**

- **Metagegevens-gestuurde mapping**: Transformatieregels worden gespecificeerd als configuratie, niet gehard-coded
- **Plug-and-play connectors**: Nieuwe databronnen kunnen worden toegevoegd via configuratie
- **Crossviews-framework**: Generieken query-engine die over verschillende schemata werkt
- **Themaplaten**: Herbruikbare transformatiepatterns voor veelvoorkomende gegevenstypen

Dit maakt migratie naar andere gemeenten veel sneller en goedkoper.

### 2. Open Source en Openheid

**Doel:** Transparantie, herbruikbaarheid, en langterm duurzaamheid.

**Implementatie:**

- Uitgifte onder **EUPL-licentie** (open source, commercieel gebruik toegestaan)
- Volledige code en documentatie op **GitHub** gepubliceerd
- Community-driven ontwikkeling met bijdragen van andere gemeenten
- Geen vendor lock-in; gebruikers kunnen het systeem aanpassen

!!! quote "Publieke Waarde"
    Open source zorgt ervoor dat investeringen in data-harmonisatie geld oplevert voor de gehele publieke sector, niet slechts voor één organisatie.

### 3. Integratie met Gemeentelijk Gegevensmodel (GGM)

**Doel:** Aansluiting bij de standaard data-architectuur van gemeenten.

**Implementatie:**

- Mapping van archeologische entiteiten naar **GGM-concepten**
- Compatibiliteit met common data models
- Facilitering van data-uitwisseling met andere gemeentelijke informatiesystemen (gebouwen, kadaster, etc.)

Dit maakt het mogelijk om archeologische data naast andere basisregistraties te positioneren.

### 4. Ondersteuning van Meerdere Gemeenten

**Doel:** Schaalbare deployment naar Nederlandse gemeenten.

**Ambities:**

- Uitbreiding vanuit Delft naar minstens 5-10 andere gemeenten in eerste fase
- Harmonisatie van methodologieën tussen gemeenten
- Shared learnings en best practices

**Stichting Reuvens Innovatieproject:**

Dit ambitie wordt ondersteund via het innovatieproject van Stichting Reuvens, dat Wasstraat financiert als generieke oplossing voor Nederlandse erfgoeddata.

### 5. FAIR Data Principes

**Doel:** Geologische gegevens moeten aan het FAIR-stelsel voldoen.

**Implementatie:**

- **F (Findable)**: Metadata-indexering via nationale zoekdiensten
- **A (Accessible)**: Publieke interfaces en API's voor gegevenstoegang
- **I (Interoperable)**: Gebruik van standaard RDF, CIDOC CRM, URIs
- **R (Reusable)**: Duidelijke licenties, provenance-tracking, documentatie

!!! info "FAIR in Praktijk"
    Een onderzoeker aan de Universiteit van Amsterdam kan op dezelfde manier gegevens uit Delft, Utrecht en Amsterdam bevragen.

### 6. Aansluiting Nationale Standaarden

**Doel:** Integratie met landelijke erfgoed-infrastructuur.

**Standaarden en Registers:**

| Standaard | Doel |
|-----------|------|
| **ABR** (Archeologische Basisregistratie) | Nationale definitie van archeologische concepten |
| **Archis** | Landelijk informatiesysteem voor erfgoed |
| **CIDOC CRM** | Semantische beschrijving van culturele objecten |
| **DANS e-Depot** | Lange-termijn archivering van onderzoeksdata |

**Implementatie:**

- URIs die verwijzen naar ABR-thesaurus termen
- Export naar CIDOC CRM-RDF voor interoperabiliteit
- Mogelijkheid om datasets aan te leveren aan DANS voor archivering
- Aansluiting op Archis voor landelijk overzicht

### 7. Technische Innovatie

**Doel:** Demonstratie van geavanceerde data-engineering technieken.

**Technologische Highlights:**

- **SingleStore voor Polymorfische Data**: Flexibel gegevensmodel zonder performance-inlevering
- **Crossviews-Engine**: Queries over meerdere gegevensbronnen heen
- **Metagegevens-Gestuurde Transformaties**: Geen code nodig voor nieuwe schema's
- **Fuzzy Indexing**: Zoeken ondanks onnauwkeurigheid
- **Moderne DevOps**: Docker, Kubernetes, CI/CD pipelines

Dit toont aan dat erfgoeddata net zo geavanceerd beheerd kan worden als bedrijfskritieke data.

### 8. Gebruikerservaring

**Doel:** Archeologische data moet gemakkelijk toegankelijk zijn voor diverse gebruikersgroepen.

**Implementatie:**

- **Web Interface** (Vue/Vuetify): Intuïtieve zoekopdracht en browsen
- **GIS-Dashboards**: Kaart-gebaseerde verkenning
- **Data Warehouse Exports**: BI-gereedschap (Power BI, Tableau) support
- **API's**: Programmatische toegang voor onderzoekers
- **Rapporten**: Automatisch gegenereerde overzichten en analyses

!!! success "Inclusieve Benadering"
    Van niet-technische erfgoed-curators tot data scientists: iedereen vindt een interface die past.

## Succescriteria

De realisatie van Wasstraat is succesvol wanneer:

✓ **Generieke software** die zonder code-aanpassingen in ≥3 gemeenten is ingezet
✓ **Open source community** met bijdragen van organisaties buiten E-Space
✓ **FAIR-gevalideerde datasets** beschikbaar via nationale portals
✓ **Onderzoeksresultaten** gebaseerd op Wasstraat-data gepubliceerd in toonaangevende vakliteratuur
✓ **Kosteneffectiviteit** aangetoond: harmonisatie in minder tijd tegen lagere kosten
✓ **Duurzaamheid** gegarandeerd via Stichting Reuvens als host-organisatie

## Leeswijzer

- Voor context over waarom dit project nodig is, zie [Inleiding](inleiding.md)
- Voor de technische details hoe we deze problemen adresseren, zie [Probleemstelling](probleemstelling.md)
- Voor implementatie-documentatie, verwijzen we naar de technische handleidingen elders in deze documentatie
