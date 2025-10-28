# Bredere Beschikbaarheid: Stichting Reuvens Initiatief

Dit document beschrijft de visie op het breder beschikbaar maken van de Wasstraat voor alle Nederlandse gemeenten en andere erfgoeorganisaties onder coördinatie van Stichting Reuvens.

## Context: Stichting Reuvens

Stichting Reuvens is het Nederlandse wetenschappelijk instituut voor erfgoed-informatica en -beheer:

- **Missie**: Bevordering van duurzame en open toegang tot archeologische en erfgoedinformatie
- **Rol**: Facilitator van kennisuitwisseling en standaardisering
- **Netwerk**: Verbinding tussen gemeenten, universiteiten, erfgoedbeheerders, en DANS
- **Mandaat**: Vertrouwen van erfgoed-sector doordat onafhankelijk en wetenschappelijk

### Stichting Reuvens & Wasstraat

Stichting Reuvens speelt drie rollen in dit project:

1. **Projectcoördinator**: Overarching governance en stakeholder management
2. **Kennisinstituut**: Research, standaarden, best practices
3. **Neutrale partij**: Vertrouwen van alle deelnemers (gemeenten, onderzoekers, archivering)

## Visie: Landelijke Archaeologische Data Infrastructure

### Doel

Alle Nederlandse gemeenten kunnen hun archeologische data beheren en delen via één uniform platform dat:

- Operationeel is (niet "idealistisch")
- Open source is (transparantie, hergebruik)
- Decentraal beheerd is (geen centrale bottleneck)
- Aangesloten op nationale standaarden (ABR, Archis, DANS, ARIADNE)
- Gepubliceerd als open data (CC-BY)
- Ondersteund via training en community

### Scope in Fase 1-2

Focus op Nederland, met potentiële uitbreiding naar:
- Andere Nederlandse erfgoebeheerders (monumentenregisters, musea)
- Internationale partners (ARIADNE, CIDOC CRM community)
- Linked data ecosysteem (DBpedia, Wikidata)

## Projectstructuur: 5 Work Packages

Het transformatieproject is gestructureerd in 5 parallelle Work Packages:

### WP1: Decoupling Delft-Specific Logic
**Doel**: Uit-engineered Wasstraat van gemeente-specifieke code
**Verantwoordelijke**: Lead Developer + Junior Dev
**Duur**: Maanden 1-6
**Output**: Generic Wasstraat codebase

#### Deliverables
1. **Code audit**: Volledige inventory van Delft-specifieke elementen
2. **Refactored core**: 100% Delft-logic verplaatst naar config/plugins
3. **Test suite**: Tests voor minstens 3 configuratie-varianten
4. **Documentatie**: Architecture Decision Records (ADRs)

#### Key Activities
```
Month 1-2: Audit & planning
- Analyze codebase for hardcoded Delft references
- Create refactoring roadmap
- Set up test infrastructure

Month 3-4: Refactoring wave 1
- Extract data model specifics
- Move validation rules to config
- Extract API integrations

Month 5-6: Refactoring wave 2 & testing
- Extract UI/display logic
- Extract operational specifics
- Integration testing with pilot configs
```

### WP2: Generic Configuration Layer
**Doel**: Creatie van configuration-driven architecture
**Verantwoordelijke**: Architecture Lead + Dev
**Duur**: Maanden 2-6
**Output**: Configuration framework, documentation, examples

#### Deliverables
1. **YAML Schema**: Comprehensive configuration specification
2. **Config loader**: Robust implementation with validation
3. **Plugin framework**: Standard interfaces for extensions
4. **Starter templates**: Configuration templates voor 5 common scenarios
5. **Migration tool**: Script voor conversie van old configs naar new

#### Key Activities
```
Month 2-3: Framework design
- Design configuration schema
- Identify extension points
- Design plugin interfaces

Month 4-5: Implementation
- Implement config loader
- Implement plugin system
- Comprehensive validation

Month 6: Documentation & examples
- Write configuration guide
- Create example configs (Delft, Amsterdam, Groningen, etc.)
- Create plugin development guide
```

#### Configuration Example: Amsterdam
```yaml
# deployment/amsterdam.yaml
municipality:
  name: "Amsterdam"
  code: "0363"
  language: "nl"

geography:
  coordinate_system: "EPSG:28992"
  bounds:
    north: 52.4232
    south: 52.2481
    east: 5.0305
    west: 4.7673

data_sources:
  - name: "legacy_xml"
    type: "file_directory"
    path: "/data/amsterdam/opgraving_*.xml"
    parser: "xml_generic"

  - name: "ams_gis"
    type: "wfs"
    endpoint: "https://gis.amsterdam.nl/wfs"
    feature_type: "archeologie:sites"

  - name: "monuments_register"
    type: "rest_api"
    endpoint: "https://monuments.amsterdam.nl/api/v2"
    refresh_interval: "weekly"

validation_rules:
  - rule: "address_required"
    enabled: true

  - rule: "dutch_date_format"
    enabled: true

  - rule: "amsterdam_museum_notification"
    enabled: true
    # Amsterdam-specific: notify museum if high-value artifacts

field_mappings:
  excavation_name:
    - source: "xml_path://opgraving/naam"
    - source: "wfs_property:site_name"
    - source: "api_field:title"

output_formats:
  - format: "json_ld"
    enabled: true
  - format: "geojson"
    enabled: true
  - format: "archis_compatible"
    enabled: true
```

### WP3: Pilot Implementations (2-3 Municipalities)
**Doel**: Validation van genericiteit in real-world scenario's
**Verantwoordelijke**: Community Coordinator + Pilots Leads
**Duur**: Maanden 4-9
**Output**: Operational Wasstraat instances, lessons learned, feedback

#### Pilot Selection Criteria
- Diverse gemeente-sizes (1x middelgroot, 1x groot)
- Diverse data-characteristics (urban vs. rural, active vs. historical)
- Political commitment for 2+ years
- IT capacity for local support
- Geographic diversity (south, north, east, west)

#### Candidate Municipalities
1. **Amsterdam** (863k inhabitants, complex urban archaeology, rich data)
2. **Groningen** (230k inhabitants, university presence, historical depth)
3. **Maastricht** (121k inhabitants, Mediterranean archaeology, EU perspective)

#### Pilot Workflow
```
Month 4: Kickoff & setup
- Sign MOU with pilot municipalities
- Establish local teams
- Procure hardware/hosting
- Data inventory & assessment

Month 5-6: Implementation
- Deploy Wasstraat instance
- Configure for municipality
- Data migration & validation
- User training
- Go-live

Month 7-8: Operation & refinement
- Monitor system health
- User feedback collection
- Bug fixes & optimizations
- Data quality improvement

Month 9: Evaluation & documentation
- Lessons learned workshop
- Document success stories
- Identify generalizable patterns
- Plan Phase 2 roll-out
```

#### Success Metrics per Pilot
| Metric | Target |
|--------|--------|
| Data imported | >80% of archaeological records |
| System availability | >99% uptime |
| Query performance | <2s for typical queries |
| User satisfaction | >4/5 rating |
| Data quality | >90% compliance to rules |
| Support tickets | <10 per month |

### WP4: GGM Positioning & National Standards
**Doel**: Integratie met Gemeentelijk Gegevensmodel en nationale standaarden
**Verantwoordelijke**: Data Architect + Standards Coordinator
**Duur**: Maanden 6-12
**Output**: GGM specification, API, RDF/CIDOC CRM mappings, Archis integration

#### Deliverables
1. **GGM Archaeological Profile**: Formal specification
2. **CIDOC CRM Mappings**: Complete RDF/OWL
3. **Archis Integration**: API bindings, sync workflows
4. **FAIR Principles**: Data management plan
5. **DANS e-Depot Integration**: Long-term archival setup

#### Key Activities
```
Month 6-7: Standards audit
- Analyze current GGM adoption
- Review CIDOC CRM compatibility
- Assess Archis integration feasibility
- Research FAIR principles application

Month 8-9: Implementation
- Design GGM archaeological profile
- Implement RDF output
- Create Archis API bindings
- Implement FAIR metadata

Month 10-12: Integration & rollout
- Test with pilot instances
- Integrate with DANS e-Depot
- Community feedback
- Document for adoption
```

### WP5: Documentation, Training & Community
**Doel**: Ensure sustainability through knowledge transfer and community building
**Verantwoordelijke**: Community Manager + Technical Writer
**Duur**: Maanden 1-12 (ongoing)
**Output**: Documentation, training materials, community infrastructure

#### Deliverables
1. **User Documentation**
   - Installation guides for each municipality
   - Data management procedures
   - Troubleshooting guides
   - FAQ

2. **Developer Documentation**
   - Architecture guide
   - API documentation (OpenAPI spec)
   - Plugin development guide
   - Contributing guidelines

3. **Training Materials**
   - Video tutorials (5-10 min each)
   - Slide decks for workshops
   - Hands-on exercises
   - Certification program

4. **Community Infrastructure**
   - GitHub repository & discussions
   - Community forum / Slack
   - Regular webinars (monthly)
   - Annual conference

5. **Academic Publications**
   - Journal articles on architecture & lessons learned
   - Conference presentations (ARIADNE, DHN, etc.)
   - White papers on standards integration

#### Community Building Activities
```
Month 1: Setup
- GitHub org + repository
- Community guidelines & code of conduct
- Discussion forum
- Newsletter signup

Month 3: Launch
- First webinar (system overview)
- Community guidelines published
- First issue resolved from external contributor

Month 6: Growth
- Monthly webinars
- 50+ GitHub stars
- 10+ active forum members
- 1-2 external code contributions

Month 12: Maturity
- 100+ GitHub stars
- 50+ forum members
- 20+ external contributors
- Annual conference

Year 2: Sustainable
- Self-sustaining community
- Regular local meetups
- User group chapters per region
- Academic partnerships
```

## FAIR Data Principles Implementation

Wasstraat must align with FAIR (Findable, Accessible, Interoperable, Reusable):

### Findable
- Persistent identifiers (PIDs) for datasets
- Rich metadata (Dublin Core, CIDOC CRM)
- Registration in data registries (CKAN, DataCite)
- Indexing in search engines

### Accessible
- Open APIs (REST, SPARQL)
- No unjustified restrictions
- Clear authentication/authorization
- Data in standard formats (JSON-LD, RDF, GeoJSON)

### Interoperable
- Use standard vocabularies (ABR, CIDOC CRM)
- Standard formats (ISO 8601, OGC standards)
- GGM compliance
- Archis compatibility

### Reusable
- Clear data licenses (CC-BY)
- Detailed documentation
- Training & support
- Long-term preservation (DANS)

## National Infrastructure Connections

### Archis Integration
```
Wasstraat         Archis (centraal archeologisch register)
    │                    │
    └────────────────────┘
         (sync API)

Scenario: Wasstraat uploads new excavations → Archis ingests → UNESCO/international visibility
```

### DANS e-Depot (Long-term Archival)
```
Wasstraat      DANS e-Depot (25+ year preservation)
    │                │
    └────────────────┘
     (periodic upload)

Scenario: Every 2 years, Wasstraat submits dataset → DANS preserves with DOI
```

### ARIADNE Federation
```
Wasstraat         ARIADNE Portal (European archaeology)
    │                    │
    └────────────────────┘
         (RDF/CIDOC CRM)

Scenario: Dutch archaeology discoverable at European level
```

### National GGM Federation
```
Wasstraat (GGM API)
    ├── Delft GGM
    ├── Amsterdam GGM
    ├── Groningen GGM
    └── ...other municipalities

Scenario: Citizens can find archaeology through common interface
```

## Risk Management

### Risk Register

| Risk | Description | Impact | Probability | Mitigation |
|------|-------------|--------|-------------|-----------|
| **Naming Variations** | Different municipalities use different terms for same concept | High | High | ABR standardization, vocabulary server, mapping tool |
| **IT Structure Alignment** | Municipal IT doesn't support generalized deployment | Medium | Medium | Early engagement, technical assessment, support resources |
| **Pilot Capacity** | Limited capacity for parallel implementations | High | Medium | Phased approach, vendor support for deployment, templating |
| **Standardization Premature** | National standards not ready when needed | Medium | Low | Modular design allows future updates without code changes |
| **GGM Adoption** | Municipalities not adopting GGM | Medium | Medium | Position Wasstraat as GGM enabler, early implementation |
| **Data Quality** | Inconsistent quality across municipalities | High | High | Clear quality guidelines, automated validation, incentives |
| **Community Engagement** | Lack of external contributors | Medium | Low | Professional community management, clear contribution path |
| **Funding Sustainability** | Project funding ends | High | Medium | Seek structural funding, demonstrate ROI, build sustainability |

### Mitigation Details

#### Naming Variations (Highest Priority)
The archaeological domain has centuries of inconsistent terminology:

```python
# Solution: Semantic layer with ABR
class TermMapping:
    """Map local terms to standard ABR terms"""

    def __init__(self, config: Config):
        self.abr_uri_map = {
            "delft_keramiek": "https://abr.erfgeo.nl/themas/pottery",
            "amsterdam_aardewerk": "https://abr.erfgeo.nl/themas/pottery",
            "groningen_klei": "https://abr.erfgeo.nl/themas/pottery",
        }
        self.inverse_map = {v: k for k, v in self.abr_uri_map.items()}

    def normalize_term(self, local_term: str) -> str:
        """Get ABR URI for any local term"""
        return self.abr_uri_map.get(local_term, None)

    def get_local_terms(self, abr_uri: str) -> List[str]:
        """Get all local variants of standard term"""
        return [k for k, v in self.abr_uri_map.items() if v == abr_uri]
```

#### Municipal IT Structure
```yaml
# Technical assessment template for municipalities
assessment:
  infrastructure:
    - has_linux_hosting: required
    - postgresql_supported: required
    - docker_capacity: required
    - api_infrastructure: required
    - available_disk_space: "≥500GB recommended"

  staffing:
    - data_manager_availability: "0.5 FTE minimum"
    - it_support_capacity: "0.25 FTE minimum"
    - training_time_budget: "40 hours in Year 1"

  governance:
    - data_governance_framework: required
    - budget_approval_time: "3 months typical"
    - legal_review: required
```

#### Pilot Capacity Mitigation
```
Year 1:  1-2 pilots (intensive support)
Year 2:  3-5 pilots (templated, self-service)
Year 3:  10+ deployments (fully documented, plugin ecosystem)
```

## Success Criteria (Overall)

### End of Year 1
- ✓ 3 operational Wasstraat instances (Delft + 2 pilots)
- ✓ 100+ municipalities aware of project
- ✓ Open source release with 5K+ GitHub stars
- ✓ 50+ community members
- ✓ Integration with Archis demonstrated
- ✓ GGM profile published
- ✓ Training delivered to 150+ people

### End of Year 2
- ✓ 10+ municipalities operational
- ✓ 1000+ GitHub stars
- ✓ 500+ community members
- ✓ Academic publications in top-tier journals
- ✓ Linked data federation demonstrating European cooperation
- ✓ Sustainable funding model established

### Long-term (3-5 years)
- ✓ 40+ municipalities operational
- ✓ National standard for Dutch archaeology
- ✓ Self-sustaining community & governance
- ✓ Integration with international FAIR infrastructure
- ✓ Washout as reference implementation globally

## Timeline Overview

```
Q1 2024     Q2 2024     Q3 2024     Q4 2024     Q1 2025     Q2 2025
├────┤      ├────┤      ├────┤      ├────┤      ├────┤      ├────┤
WP1: Decoupling ─────────────────────────►
WP2: Configuration ──────────────────────►
WP3: Pilots          Kickoff ─────────────────►
WP4: Standards                    ───────────────────────►
WP5: Community ─────────────────────────────────────►

Month 1: Setup & discovery
Month 3: First deliverables
Month 6: Pilots live, open source release
Month 9: GGM integration, evaluation
Month 12: Community established, Year 2 planning
```

## Governance Structure

### Steering Committee
**Members**: Delft mayor, Stichting Reuvens director, pilot municipality representatives, Ministry representative, DANS director
**Frequency**: Quarterly
**Role**: Strategic direction, resource allocation, stakeholder alignment

### Technical Board
**Members**: Lead architect, WP leads, community representatives, university partners
**Frequency**: Monthly
**Role**: Technical decisions, architecture evolution, quality assurance

### Community Council
**Members**: External contributors, municipality data managers, user representatives
**Frequency**: Quarterly
**Role**: User needs, feature prioritization, feedback

### Operational Team
**Members**: Project manager, devops, community manager
**Frequency**: Weekly
**Role**: Day-to-day coordination, issue tracking, communication

## Budget & Funding

### Total Project Cost (3 years)

| Category | Year 1 | Year 2 | Year 3 |
|----------|--------|--------|--------|
| Personnel | €300k | €250k | €150k |
| Infrastructure | €50k | €50k | €30k |
| Training/Events | €30k | €40k | €30k |
| Overhead | €70k | €60k | €40k |
| **Total** | **€450k** | **€400k** | **€250k** |

### Funding Sources
- Ministry of Education/Culture
- Stichting Reuvens core funding
- Participating municipalities (cost-share)
- European Horizon grants (ARIADNE, etc.)
- Academic institutional support

## Conclusion

Wasstraat can evolve from a Delft-specific system into the Dutch national standard for archaeological data management. This requires disciplined execution across five coordinated work packages, strong community engagement, and alignment with national and European infrastructure.

The initiative is not just about technology—it's about building sustainable infrastructure for Dutch cultural heritage that benefits archaeologists, municipalities, citizens, and the international research community.
