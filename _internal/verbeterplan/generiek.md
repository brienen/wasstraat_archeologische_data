# Generalisering: Van Delft naar Alle Gemeenten

Een van de grootste obstakels voor bredere adoptie van de Wasstraat is dat het platform sterk gekoppeld is aan de specifieke omgeving van Delft. Dit document beschrijft hoe we het platform generiek kunnen maken zodat het in willekeurige gemeenten kan worden ingezet.

## Huidige Delft-Specifieke Elementen

### In Code Ingebed
- **Veldnamen**: Verwijzingen naar "Delft" in variabelen, databases, scripts
- **Validatie-regels**: Gebaseerd op Delft-specifieke data-kwaliteitseisen
- **Data-transformaties**: Scripts voor conversie van Delft's erfgoed-registers
- **API-koppelingen**: Directe integratie met Delft's GIS en monument-registers
- **Geografische limieten**: Hard-coded search boundaries, coördinaten-systemen

### In Configuratie
- Veld-mappings voor Delft's data-formaten
- Validatie-profiles optimaliseerd voor Delft's situatie
- Archief-naamgeving conventions
- User interface strings in Nederlands met Delft-specifieke termen

### Operationeel
- Database setup voor Delft's specifieke volumes
- Caching-strategie op Delft-data gebaseerd
- Backup-procedures ingesteld op Delft-schedules
- Documentatie geschreven "hoe te Delft"

## Extractie-Plan: Delft-Logica naar Configuratie

### Stap 1: Inventory van Delft-Specifiek

**Codebase audit:**
```
find . -type f -name "*.py" | xargs grep -l "delft\|Delft" | sort
grep -r "amsterdam\|Den Haag\|Utrecht" docs/  # Check voor hardcoded gemeente-names
```

**Configuratie audit:**
- Alle YAML/JSON config files met Delft-verwijzingen inventariseren
- Data-scripts scannen op locale naamgeving
- API-calls naar Delft-systemen identificeren

**Typische bevindingen:**
```python
# VOOR - Delft ingebed
def validate_address(address_string):
    # Nur valideren als in Delft geometrie
    if not is_in_delft(address_string.coordinates):
        raise ValueError("Adres moet in Delft zijn")

# NA - Configurable
def validate_address(address_string, bounds_geometry=None):
    if bounds_geometry and not is_within_bounds(address_string.coordinates, bounds_geometry):
        raise ValueError(f"Adres moet binnen geselecteerde geometrie zijn")
```

### Stap 2: Extractie naar Parameters

Drie niveaus van configuratie-parameters:

#### Level 1: Environment/Infrastructure
```yaml
# config/municipality.yaml
municipality:
  name: "Delft"
  code: "0503"  # CBS gemeentecode
  bounds_geometry: "POLYGON((4.35 51.98, 4.40 51.98, ...))"
  coordinate_system: "EPSG:28992"  # RD (Rijksdriehoeksmeting)

database:
  postgres_host: "localhost"
  postgres_port: 5432
  mongodb_host: "localhost"
  mongodb_port: 27017
```

#### Level 2: Data Model & Schema
```yaml
# config/data_model.yaml
fields:
  address:
    type: "string"
    required: true
    validation:
      - type: "bounds_check"
        geometry: "${municipality.bounds_geometry}"
      - type: "address_format"
        pattern: "^[A-Za-z0-9 .,]$"

  date_found:
    type: "date"
    validation:
      - type: "date_range"
        min: "1800-01-01"
        max: "${current_date}"

  excavation_method:
    type: "enum"
    values: ["hand_dig", "machine_dig", "survey", "monitoring"]
    validation:
      - type: "required_if_field_exists"
        condition: "phase == 'excavation'"
```

#### Level 3: Transformatie Regels & Integraties
```yaml
# config/transformations.yaml
input_formats:
  - name: "delft_legacy_xml"
    file_pattern: "*.xml"
    parser: "xml_delft_parser"  # Or generic XML parser
    field_mappings:
      - source: "//opgraving/naam"
        target: "excavation_name"
      - source: "//opgraving/datum_start"
        target: "date_start"
        transformation: "parse_dutch_date"

external_systems:
  - name: "delft_gis"
    type: "wfs"  # Web Feature Service (OGC standard)
    endpoint: "${municipality.gis_endpoint}"
    feature_type: "archeologie:excavation_areas"
    fields_to_sync:
      - "location_geometry"
      - "site_code"
```

### Stap 3: Plugin Architecture voor Gemeente-Specifieke Logica

Veel gemeenten hebben unieke requirements. Dit kan via plugins:

```python
# plugins/delft/delft_custom_validator.py
from wasstraat.plugin_interface import ValidationPlugin

class DelftCustomValidator(ValidationPlugin):
    """Delft-specifieke validatieregels"""

    def validate(self, record, context):
        # Delft requirement: alle opgravingen moeten gemetaald zijn
        if record.get("status") == "completed":
            if not record.get("excavation_cost"):
                self.add_error("excavation_cost", "Delft vereist kostenregistratie")

        # Delft requirement: bepaalde straats-combinaties zijn niet geldig
        if record.get("street") and record.get("neighborhood"):
            valid_combos = context.config.get("delft.street_neighborhood_combos")
            if (record["street"], record["neighborhood"]) not in valid_combos:
                self.add_error("neighborhood", "Ongeldig combinatie straat/buurt in Delft")

        return self.errors

# Registreren in config
validation_plugins:
  - name: "delft_custom"
    module: "plugins.delft.delft_custom_validator"
    class: "DelftCustomValidator"
    enabled: true
```

## Generieke Data-Model Ontwerp

### Kernprincipe: Polymorf + Configurable

De Wasstraat moet kunnen omgaan met verschillende data-modellen zonder ze te standardiseren. In plaats daarvan:

1. **Generieke core**: Universele concepten (locatie, datum, actor, etc.)
2. **Extensible properties**: Gemeente-specifieke extra velden via key-value pairs
3. **Transformatie-regels**: Mapping van lokaal model naar generieke core

```yaml
# Universal archaeological record structure
record:
  id: string  # Unique identifier
  source_system: string  # Where did this come from?

  # Core universele velden
  excavation_name: string
  location:
    geometry: WKT
    coordinate_system: EPSG_code
    description: string

  dates:
    start: ISO8601
    end: ISO8601
    uncertainty: "estimated|precise"

  responsible_parties:
    - role: "excavator|project_lead|recording_official"
      name: string
      organization: string

  # Extensible gemeente-specifieke velden
  local_fields:
    delft_cost: float
    delft_site_category: enum
    amsterdam_preservation_status: string
    # ... enz

  # Metadata
  metadata:
    created: ISO8601
    modified: ISO8601
    source: string
    rights: string
```

### Multi-Gemeente Scenario

```yaml
# deployment/delft.yaml
extends: "config/base.yaml"
municipality:
  name: "Delft"
  code: "0503"

# deployment/amsterdam.yaml
extends: "config/base.yaml"
municipality:
  name: "Amsterdam"
  code: "0363"
  # Amsterdam-specifieke overrides
  coordinate_system: "EPSG:28992"  # Samen RD
  bounds_geometry: "POLYGON((4.77 52.24, 5.03 52.42, ...))"

# deployment/groningen.yaml
extends: "config/base.yaml"
municipality:
  name: "Groningen"
  code: "0014"
  coordinate_system: "EPSG:28992"
  bounds_geometry: "POLYGON((6.50 53.19, 6.60 53.22, ...))"
```

## Configuration-Driven Processing Framework

### Configuratie-Engine

```python
# wasstraat/config/loader.py
class ConfigLoader:
    def load_configuration(self, config_file: str) -> Config:
        """Laad configuratie met validatie"""
        config_dict = yaml.load(config_file)

        # Inheritance handling
        if "extends" in config_dict:
            base_config = self.load_configuration(config_dict["extends"])
            config_dict = self.merge_configs(base_config, config_dict)

        # Validatie van config-schema
        self.validate_against_schema(config_dict)

        return Config(config_dict)

class Config:
    def get(self, path: str, default=None):
        """Access config met dot-notation"""
        # municipality.bounds_geometry → delft_config.municipality.bounds_geometry
        parts = path.split(".")
        value = self.config_dict
        for part in parts:
            value = value.get(part, {})
        return value if value else default

    def get_all_plugins(self) -> List[Plugin]:
        """Laad alle ingeschakelde plugins"""
        plugins = []
        for plugin_config in self.get("validation_plugins", []):
            if plugin_config.get("enabled", True):
                plugin_class = self._import_class(plugin_config["module"], plugin_config["class"])
                plugins.append(plugin_class(plugin_config))
        return plugins
```

### Extensibility Hooks

```python
# wasstraat/plugins/plugin_interface.py
class ValidationPlugin(ABC):
    @abstractmethod
    def validate(self, record: dict, context: ExecutionContext) -> List[ValidationError]:
        pass

class TransformationPlugin(ABC):
    @abstractmethod
    def transform(self, input_record: dict, config: dict) -> dict:
        pass

class InputFormatPlugin(ABC):
    @abstractmethod
    def parse(self, input_file: BinaryIO, config: dict) -> Generator[dict]:
        pass

class OutputFormatPlugin(ABC):
    @abstractmethod
    def serialize(self, record: dict, config: dict) -> str:
        pass
```

## Migratie-Plan: Delft naar Generiek

### Fase 1: Inventory & Refactor
1. Audit van alle Delft-specifieke code
2. Refactoring: Delft-logica naar parameters
3. Creatie van Delft-profiel-config
4. Verificatie: Delft werkt nog steeds met nieuwe setup

### Fase 2: Plugin-Framework
1. Implementatie van plugin-interfaces
2. Conversie van bestaande Delft-code naar plugins
3. Testing van plugin-loading
4. Documentatie van plugin-development

### Fase 3: Configuratie-Engine
1. YAML/JSON schema ontwerp
2. Config-loader implementatie
3. Config-validatie
4. Testen met Delft + mock gemeente

### Fase 4: Generieke Tests & Documentatie
1. Test-suites voor elk configuratie-scenario
2. Implementation guides voor nieuwe gemeenten
3. Template-configuratie files
4. Troubleshooting guides

## Handleiding: Instelling voor Nieuwe Gemeente

Voor een nieuwe gemeente (bijv. Utrecht):

```bash
# 1. Clone generieke config
cp -r deployment/template deployment/utrecht

# 2. Edit configuratie
edit deployment/utrecht/municipality.yaml
# Zet:
#   - Gemeente naam en code
#   - Geographic bounds
#   - Data-sources en API endpoints
#   - Veld-mappings voor lokale data

# 3. Data-import testen
wasstraat import \
  --config deployment/utrecht/municipality.yaml \
  --source data/utrechts_opgravingen.xml

# 4. Validatie en QA
wasstraat validate \
  --config deployment/utrecht/municipality.yaml

# 5. Custom validators/transformers toevoegen
# Create deployment/utrecht/plugins/custom_validator.py
# Register in deployment/utrecht/validation_plugins

# 6. UI branding (optioneel)
edit deployment/utrecht/ui_config.yaml
# Zet: gemeente-logo's, taal, kleursschema

# 7. Launch
wasstraat serve --config deployment/utrecht/municipality.yaml
```

## Success Criteria voor Generalisering

- **Code-niveau**: Geen verwijzing naar "Delft" in src/, allen in config/
- **Configuratie-niveau**: Município-specifieke logica is in YAML/JSON, niet hardcoded
- **Plugin-niveau**: Gemeente-unieke validatie is in plugins, niet in core
- **Test-niveau**: Tests draaien voor minstens 3 verschillende configuraties
- **Operationeel**: Nieuwe gemeente kan in deployment zonder code-wijzigingen

Dit framework maakt Wasstraat werkelijk generiek en ready voor nationale uitrol.
