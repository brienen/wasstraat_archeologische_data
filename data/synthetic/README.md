# Synthetische Voorbeelddata

Fictieve maar realistische archeologische data voor de Wasstraat, als vervanging van echte opgravingsdata.

## Scenario's

### SY001 — Klein project (Marktstraat 10, Voorburg)
- 2 putten, 3 sporen, 4 vondsten, 5 artefacten (aardewerk + glas)
- Datering: 1600-1750

### SY002 — Groot project (Kerkplein, Leiden)
- 4 putten, 8 sporen, 12 vondsten, 20 artefacten (8 materiaalsoorten)
- Datering: 1200-1800

## Bestanden

```
output/
  projecten/SY001/C Database/opgravingSY001.mdb   # Klein project
  projecten/SY002/C Database/opgravingSY002.mdb   # Groot project
  delfit/DELF-IT.mdb                               # Projectenlijst
  magazijnlijst/MAGAZIJN.mdb                       # Depotdata
  digifotos/Digifotos.mdb                          # Fotocatalogus
```

## Opnieuw genereren

Vereisten:
- Java JRE (`brew install openjdk` op macOS)
- Python packages: `pip install -r requirements-synthetic.txt`
- Jackcess JARs in `jars/` (al aanwezig in de repo)

```bash
make synthetic
```

## Gebruik met de Wasstraat

Mount de synthetische data als input-volumes in Docker Compose:

```yaml
volumes:
  - ./data/synthetic/output/projecten:/input/projecten
  - ./data/synthetic/output/delfit:/input/delfit
  - ./data/synthetic/output/magazijnlijst:/input/magazijnlijst
  - ./data/synthetic/output/digifotos:/input/digifotos
```
