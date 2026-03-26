# Synthetische Voorbeelddata

Fictieve maar realistische archeologische data voor de Wasstraat, als vervanging van echte opgravingsdata.

## Scenario's

### SY001 — Klein project (Marktstraat 10, Voorburg)
- 2 putten, 3 sporen, 4 vondsten, 5 artefacten (aardewerk + glas)
- Datering: 1600-1750

### SY002 — Groot project (Kerkplein, Leiden)
- 4 putten, 8 sporen, 12 vondsten, 20 artefacten (8 materiaalsoorten)
- Datering: 1200-1800

## Structuur

```
data/synthetic/
  data/                                             # Gegenereerde MDB-bestanden
    projecten/SY001/C Database/opgravingSY001.mdb    # Klein project
    projecten/SY002/C Database/opgravingSY002.mdb    # Groot project
    delfit/DELF-IT.mdb                               # Projectenlijst
    magazijnlijst/MAGAZIJN.mdb                       # Depotdata
    digifotos/Digifotos.mdb                          # Fotocatalogus
  generatie/                                         # Alles voor (her)generatie
    generate_synthetic_data.py                       # Generator-script
    requirements-synthetic.txt                       # Python dependencies
    jars/                                            # Jackcess JARs
```

## Opnieuw genereren

Vereisten:
- Java JRE (`brew install openjdk` op macOS)
- Python packages: `pip install -r generatie/requirements-synthetic.txt`
- Jackcess JARs in `generatie/jars/` (al aanwezig in de repo)

```bash
make synthetic
```

## Gebruik met de Wasstraat

Mount de synthetische data als input-volumes in Docker Compose:

```yaml
volumes:
  - ./data/synthetic/data/projecten:/input/projecten
  - ./data/synthetic/data/delfit:/input/delfit
  - ./data/synthetic/data/magazijnlijst:/input/magazijnlijst
  - ./data/synthetic/data/digifotos:/input/digifotos
```
