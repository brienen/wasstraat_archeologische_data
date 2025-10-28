# Technologie Stack

## Overzicht

Het Wasstraat-systeem maakt gebruik van een moderne, schaalbare technologiestapel geoptimaliseerd voor data-intensieve werkstromen in de digitale archeologie. Deze pagina catalogueert alle kerncomponenten georganiseerd op functioneel domein.

## Backend & Extractie/Transformatie

### Algemeen Doel

| Component | Versie | Rol | Licentie |
|-----------|--------|-----|----------|
| **Python** | 3.9+ | Scriptingtaal voor extractie/transformatie | MIT |
| **Pandas** | 2.x | Data wrangling & dataframe-manipulatie | BSD |
| **RDFLib** | 6.x | RDF-processing en semantic modeling | BSD |
| **SQLAlchemy** | 2.x | Object-relationeel mapping (ORM) | MIT |
| **Alembic** | 1.x | Database schema versioning & migraties | MIT |
| **Jinja2** | 3.x | Template-engine voor dynamische queries | BSD |

## Web Framework & API's

| Component | Versie | Rol | Licentie |
|-----------|--------|-----|----------|
| **Django** | 4.2+ | Backend web framework | BSD |
| **Django REST Framework** | 3.14+ | API framework & serializers | BSD |
| **Celery** | 5.3+ | Asynchrone taakuitvoering | BSD |
| **Vue.js** | 3.x | Frontend JavaScript framework | MIT |
| **Vuetify** | 3.x | Vue component library (Material Design) | MIT |

## Databases

### NoSQL & Semi-Structured

| Component | Rol | Schaal | Licentie |
|-----------|-----|-------|----------|
| **MongoDB** | Opslag ruwgegevens, semi-gestructureerde data | Miljarden documenten | SSPL |
| **SingleStore** | Kolom-georiënteerde analytic store, crossviews | Real-time analytics | Proprietary |

### Relationeel (Primair)

| Component | Versie | Rol | Licentie |
|-----------|--------|-----|----------|
| **PostgreSQL** | 13+ | Voorkeur relationele database | PostgreSQL License (permissief) |
| **PostGIS** | 3.x | Geografische dataruguitbreiding | GPL/BSD dual |

### Relationeel (Legacy)

| Component | Versie | Rol | Licentie |
|-----------|--------|-----|----------|
| **Oracle Database** | 12c+ | Enterprise relationele database | Proprietary |

### Analytics & Data Warehouse

| Component | Rol | Licentie |
|-----------|-----|----------|
| **Snowflake** | Cloud data warehouse voor reporting | Proprietary |

## Processing & Orchestratie

### Workflow Management

| Component | Versie | Rol | Licentie |
|-----------|--------|-----|----------|
| **Apache Airflow** | 2.5+ | DAG-gebaseerde workflow orchestratie | Apache 2.0 |
| **Luigi** | 3.x | Task dependency management | Apache 2.0 |
| **Celery** | 5.3+ | Distributed task queue | BSD |

### Distributed Computing

| Component | Versie | Rol | Licentie |
|-----------|--------|-----|----------|
| **Apache Spark** | 3.x | Distributed ETL & data processing | Apache 2.0 |

## Infrastructure & Deployment

### Containerization & Orchestration

| Component | Versie | Rol | Licentie |
|-----------|--------|-----|----------|
| **Docker** | 20.10+ | Container verpakking & isolatie | Apache 2.0 |
| **Kubernetes** | 1.24+ | Container orchestratie & deployment | Apache 2.0 |

### Logging & Monitoring

| Component | Rol | Licentie |
|-----------|-----|----------|
| **Docker Logs** | Container log aggregatie | Apache 2.0 |
| **Kubernetes Logs** | Cluster-level logging | Apache 2.0 |
| **Custom Monitoring** | Application-level metrics | In-house |

## Analyse & Visualisatie

### Interactive Dashboards

| Component | Versie | Rol | Licentie |
|-----------|--------|-----|----------|
| **RShiny** | 1.7+ | Interactive R dashboard framework | GPL/Proprietary dual |
| **Jupyter Notebook** | 6.x | Interactive Python notebook environment | BSD |

### Visualisatie Libraries

| Component | Rol | Licentie |
|-----------|-----|----------|
| **ggplot2** (R) | Grammar of graphics visualisatie | GPL |
| **Matplotlib/Seaborn** (Python) | Statistical data visualization | BSD |
| **Leaflet/Mapbox** | Interactive web maps | ISC/Proprietary dual |

## Semantic Tools & Standards

### Semantic Modeling

| Component | Rol | Licentie |
|-----------|-----|----------|
| **CIDOC CRM Ontology** | Cultural heritage data model | CIDOC standard (open) |
| **CRMarchaeo** | Archaeological extension to CRM | Community standard (open) |
| **CRMsci** | Scientific observation extension | Community standard (open) |
| **CRMgeo** | Geospatial extension to CRM | Community standard (open) |

### Thesaurus & Authority Files

| Component | Rol | Licentie |
|-----------|-----|----------|
| **ABR (Archeologisch Basisregister)** | Dutch archaeology thesaurus | Public use |
| **Gemeentelijk Gegevensmodel (GGM)** | Municipal data standards | Dutch open data |

## Data Exchange Formats

| Format | Use Case | Support |
|--------|----------|---------|
| **JSON** | REST API's, document storage | Native |
| **XML** | Legacy systems, schema definition | Via parsers |
| **RDF/Turtle** | Linked Open Data, semantic export | Via RDFLib |
| **CSV/TSV** | Tabular data, spreadsheet interchange | Pandas native |
| **GeoJSON** | Geographic feature exchange | PostGIS native |
| **WMS/WFS** | OGC geographic web services | GIS standard |

## Development Tools

| Component | Rol | Licentie |
|-----------|-----|----------|
| **Git** | Version control | GPL |
| **GitHub/GitLab** | Code repository hosting | Proprietary/AGPL |
| **pytest** | Python unit testing | MIT |
| **Black** | Python code formatting | MIT |
| **PostgreSQL pgAdmin** | Database administration UI | PostgreSQL License |

## Architecture Patterns

### Clean Architecture Principles
- Separation of concerns (extraction, transformation, output)
- Dependency inversion (ORM abstracts database)
- Data immutability (original data preserved)
- Polymorph awareness (flexible data structures)

### Scalability Patterns
- Horizontal scaling via Kubernetes
- Distributed processing via Apache Spark
- Asynchronous task execution via Celery
- Read replicas for reporting via Snowflake

### Reliability Patterns
- Database transactions (ACID in PostgreSQL/Oracle)
- Retry logic in Airflow/Luigi
- Health checks in Kubernetes
- Audit logging at every transformation step

## Integration Points

### External Systems

```
┌─────────────────────┐
│   External Data     │
│ Repositories (ABR,  │
│  GeoNames, etc.)    │
└──────────┬──────────┘
           │
      [RDFLib HTTP]
           ↓
┌─────────────────────┐
│  Wasstraat Core     │
│   Data Pipeline     │
└──────────┬──────────┘
           │
      [REST API]
           ↓
┌──────────────────────────┐
│  Output Systems:         │
│  - Website               │
│  - GIS (PostGIS/WMS)     │
│  - Data Warehouse        │
│  - Reporting (Snowflake) │
└──────────────────────────┘
```

## Performance Characteristics

| Component | Throughput | Latency | Notes |
|-----------|-----------|---------|-------|
| **MongoDB Ingestion** | 10k+ docs/sec | <100ms | Horizontal scaling via sharding |
| **PostgreSQL Queries** | 1k+ complex queries/sec | 10-100ms | Query optimization critical |
| **Spark ETL** | 1GB/min on modest cluster | 1-5 min per job | Distributed processing |
| **Celery Tasks** | 100+ concurrent tasks | <1s per task | Worker pool configurable |
| **Web API** | 1000+ req/sec | 10-50ms | Django + caching |

## Version Management

Alle components worden gemonitord op updates:
- Security patches: Onmiddellijk kritiek
- Minor updates: Quarterly review
- Major updates: Annual planning
- Python package versions: requirements.txt + pipenv locks
- Database versions: Alembic migration strategy
