# Verbeterplan en Roadmap

De Wasstraat bevindt zich op een kruispunt: succesvol bewezen in Delft, maar met significante zwakheden die generalisatie belemmeren. Dit verbeterplan richt zich op stapsgewijze modernisering en voorbereiding voor bredere implementatie.

## Strategische Doelstellingen

1. **Ontkoppeling van Delft-specifieke logica**: Maken van het platform configurable voor verschillende gemeenten
2. **Stabilisering van architectuur**: Vereenvoudiging van technology stack en vermindering van single-point-of-failure
3. **Documentatie en training**: Mogelijkheden creëren voor andere organisaties om het platform in te zetten
4. **Ecosysteem-integratie**: Aansluiting op nationale infrastructuur (Archis, DANS, ARIADNE)
5. **Community-building**: Ondersteuning van open-source samenwerking en kennisdeling

## Fasering van het Verbeterplan

### Fase 1: Stabiliteit & Documentatie (Maanden 1-3)

**Kritieke prioriteiten:**

#### 1.1 Single-Developer Mitigatie
- Kennis-overdracht naar minimaal 2 andere ontwikkelaars
- Documentatie van kritieke systeem-componenten
- Oprichting van code-review proces
- Mentorship-program

**Impact**: Reduceert risico van continuïteit, maakt toekomstige ontwikkeling mogelijk.

#### 1.2 Baseline Documentatie
- Architecture Decision Records (ADR) voor alle major components
- Setup- en deployment-handleiding
- Data-model documentatie met voorbeelden
- API-referentie (ook al primitief)

**Impact**: Externe developers kunnen codebase begrijpen.

#### 1.3 Monitoring & Observability
- Logging-infrastructuur uitbreiden
- Performance monitoring implementeren
- Health check endpoints toevoegen
- Dashboard voor operationeel beheer

**Impact**: Operationeel beheer wordt mogelijk, problemen sneller detecteerbaar.

#### 1.4 Test Coverage Uitbreiden
- Unit tests voor kritieke business logic
- Integration tests voor ETL pipeline
- Data validation test-suites
- Load testing om performance baselines vast te leggen

**Impact**: Regressies voorkomen, veranderingen veiliger maken.

---

### Fase 2: Generalisering (Maanden 3-6)

**Kritieke prioriteiten:**

#### 2.1 Delft-Logica Extractie
- Inventory van hardcoded Delft-specifieke elementen
  - Veldnamen
  - Validatie-regels
  - Data-transformaties
  - Lokale systeem-koppelingen
- Verplaatsen naar configuratielaag
- Creëren van "Delft-profiel" als default configuratie

**Impact**: Codebase wordt generiek; Delft blijft werken via configuratie.

#### 2.2 Configuratie-Framework
- Oprichting van YAML/JSON configuration schema
- Ondersteuning voor:
  - Field mapping definities
  - Custom validation rules
  - Output-format profiles
  - Data-bron connectors
- Documentatie van configuratie-options
- Validation van configuratie-files

**Impact**: Gemeenten kunnen aanpassen zonder code-wijzigingen.

#### 2.3 Plugin/Extensibility Architecture
- Definiëren van plugin interfaces
- Implementatie van plugin loader
- Examples van custom plugins
- Plugin-versioning strategie

**Impact**: Third-party extensie mogelijk zonder Wasstraat-code-wijzigingen.

#### 2.4 Standaard API-Laag
- REST API ontwerp en implementatie
- OpenAPI/Swagger documentatie
- API versioning strategie
- Authentication/authorization framework

**Impact**: Externe systeem-integratie wordt standaard.

---

### Fase 3: Pilot-Implementaties (Maanden 6-9)

**Kritieke prioriteiten:**

#### 3.1 Selectie van Pilot-Gemeenten
- Criteria:
  - 1-2 gemeenten met verschillende omvang
  - Variatie in data-karakteristieken
  - Politieke steun voor langetermijn involvement
  - IT-capaciteit voor ondersteuning
- Negotiatie van pilot-agreements
- Logistiek (hardware, connectivity, support)

**Impact**: Real-world validation van genericiteit.

#### 3.2 Implementatie in Pilot-Gemeenten
- Deployment van Wasstraat in pilot-omgeving
- Configuratie-setup voor pilot-gemeente
- Data-migratie van lokale bronnen
- Training van data-beheerders
- Iteratieve feedback loop
- Bug-fixes en aanpassingen

**Impact**: Praktische ervaring, identificatie van universele vs. locale problemen.

#### 3.3 Onderwijl: Architectuur-Verbetering
- Cache-concurrency problemen oplossen (Fase 1 bevinding)
- Performance-optimalisatie voor grotere datasets
- NoSQL-Relational sync verbeteren
- Coördinaten-detectie standardiseren

**Impact**: Systeem stabiel voor meerdere omgevingen.

---

### Fase 4: GGM Integratie & Standaardisering (Maanden 9-12)

**Kritieke prioriteiten:**

#### 4.1 GGM-Alignment
- Mapping van archaeologische data-model naar GGM
- Identificatie van GGM-velden en relaties
- Common Ground principes implementeren
- Interoperabiliteit met andere GGM-compliant systemen

**Impact**: Data wordt bruikbaar in bredere gemeentelijke ecosysteem.

#### 4.2 CIDOC CRM / Linked Open Data
- Evaluatie van CIDOC CRM als semantic backbone
- RDF output-format
- Linked Open Data publicatie-mechanisme
- URI-naming strategie

**Impact**: Data wordt machine-readable en linked-data-compliant.

#### 4.3 Nationale Standaarden Formalisering
- Integratie met ABR-termen
- Koppeling met Archis-systeem
- DANS e-Depot compatibiliteit
- ARIADNE federation participation

**Impact**: Wasstraat wordt onderdeel van nationale erfgoed-infrastructuur.

---

### Fase 5: Community & Documentatie (Maanden 12+)

**Kritieke prioriteiten:**

#### 5.1 Open Source Community Building
- GitHub issues/discussions modereren
- Contribution guidelines publiceren
- Code of Conduct opstellen
- Reguliere community meetings
- Encouragement van external contributions

**Impact**: Sustainable long-term development, knowledge distribution.

#### 5.2 Uitgebreide Documentatie
- User-facing guides (implementatie per gemeente)
- Developer guides (extensie van Wasstraat)
- Data model reference
- Use case studies van Delft, pilots, en partners
- Troubleshooting guides
- Video tutorials

**Impact**: Adoptie vergemakkelijkt, support-burden gereduceerd.

#### 5.3 Training & Kennisoverdracht
- Training-modules voor:
  - Archaeologen (data-gebruik)
  - Data managers (beheer & operaties)
  - IT-teams (deployment & support)
  - Developers (extensie)
- Certification program
- Workshop-series
- Online community-forum

**Impact**: Organisaties kunnen zelfstandig werken met systeem.

#### 5.4 Lange-termijn Governance
- Oprichting van steering committee
- Contributions review proces
- Release planning
- Versioning strategie
- Long-term funding/sponsorship

**Impact**: Platform blijft evoluceren, niet afhankelijk van één organisatie.

---

## Risico-mitigatie Tijdlijn

| Risico | Fase | Maatregel |
|--------|------|-----------|
| Single-developer verlies | 1 | Kennis-overdracht, documentatie |
| Technische schuld accumulation | 1-2 | Test coverage, refactoring |
| Pilot-mislukking | 3 | Zorgvuldige selectie, gefaseerde aanpak |
| GGM misalignment | 4 | Vroege consultation, iteratieve design |
| Adoptie moeite | 5 | Training, documentatie, support |

---

## Success Criteria per Fase

### Fase 1: Stabiliteit & Documentatie
- Minimaal 2 developers operationeel
- Architecture documentation 80%+ compleet
- Test coverage ≥ 70%
- Monitoring dashboard operationeel

### Fase 2: Generalisering
- Zero hardcoded Delft-namen in code
- Configuration framework gelaunched
- Eerste pilot-pilot-versie draait
- API documentatie beschikbaar

### Fase 3: Pilot-Implementaties
- 2-3 gemeenten draaiend
- 90%+ feature parity met Delft
- Feedback-loop geïnstitutionaliseerd
- Performance-problemen opgelost

### Fase 4: GGM Integratie
- Archaeologische data in GGM-model gemapped
- CIDOC CRM-compatibiliteit gedemonstreerd
- Archis-koppeling werkend
- RDF-output beschikbaar

### Fase 5: Community & Documentatie
- 50+ externe users
- 10+ externe contributors
- Documentation 95%+ compleet
- Training-modules beschikbaar

---

## Resource-Vereisten

### Developers
- **Fase 1-2**: 1,5 FTE (bestaande + 0,5 junior)
- **Fase 3-4**: 1 FTE (focus shift naar stabilisering)
- **Fase 5**: 0,5 FTE (maintenance mode)

### Expertise Nodig
- Python/Django expert
- Database architect (MongoDB + PostgreSQL)
- Frontend developer (Vue)
- DevOps/Infrastructure engineer
- Documentation/UX writer

### Externe Partners
- Pilot-gemeenten (data, feedback, testing)
- Community members (contributions, feedback)
- Stichting Reuvens (projectleiding, visie)
- Universiteiten (research, validation)

---

## Budget Indicaties

De precieze kosten hangen af van organisatorische keuzes, maar indicatief:

- **Fase 1** (3 maanden): €40-60k (dev time + tooling)
- **Fase 2** (3 maanden): €50-70k (dev time + pilot prep)
- **Fase 3** (3 maanden): €60-80k (dev time + deployment, pilot support)
- **Fase 4** (3 maanden): €40-60k (expertise, standards alignment)
- **Fase 5** (ongoing): €30-50k/jaar (community management, docs, training)

**Totaal Jaar 1**: €220-330k
**Ongoing**: €30-50k/jaar

---

## Volgende Stappen

1. **Stakeholder alignment**: Commitment van Delft, Reuvens, pilots
2. **Team assembly**: Recruitment van dev team
3. **Sprint planning**: Gedetailleerde planning van Fase 1
4. **Infrastructure setup**: Development environment, CI/CD, monitoring
5. **Kick-off**: Project formeel van start

Target: Start Fase 1 within 4 weken.
