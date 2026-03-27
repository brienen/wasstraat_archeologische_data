# Synthetische Voorbeelddata

Fictieve maar realistische archeologische data voor de Wasstraat. Deze data dient als werkend voorbeeld van de bestandsstructuur die het platform verwacht. De echte Delftse opgravingsdata is niet opgenomen in de repository.

Gemeenten die hun eigen data willen verwerken, kunnen deze voorbeeldstructuur als referentie gebruiken om hun bronbestanden op dezelfde manier te organiseren.

## Scenario's

### SY001 — Klein project (Marktstraat 10, Voorburg)
- 2 putten, 3 sporen, 4 vondsten, 5 artefacten (aardewerk + glas)
- 2 vullingen, 7 tekeningen, 3 foto's
- Datering: 1600-1750

### SY002 — Groot project (Kerkplein, Leiden)
- 4 putten, 8 sporen, 12 vondsten, 20 artefacten (8 materiaalsoorten)
- 4 vullingen, 10 foto's
- Materiaalsoorten: aardewerk, glas, been, metaal, leer, steen, kleipijp, munten
- Datering: 1200-1800

## Structuur

```
data/synthetic/
  data/                                             # Gegenereerde MDB-bestanden
    projecten/SY001/C Database/opgravingSY001.mdb    # Klein project
    projecten/SY001/L Fotos/                         # Foto's bij SY001
    projecten/SY002/C Database/opgravingSY002.mdb    # Groot project
    projecten/SY002/L Fotos/                         # Foto's bij SY002
    delfit/DELF-IT.mdb                               # Projectenlijst
    magazijnlijst/MAGAZIJN.mdb                       # Depotdata
    digifotos/Digifotos.mdb                          # Fotocatalogus
  generatie/                                         # Alles voor (her)generatie
    generate_synthetic_data.py                       # Generator-script
    requirements-synthetic.txt                       # Python dependencies
    jars/                                            # Jackcess JARs (voor MDB-generatie)
```

## Gebruik met de Wasstraat

De synthetische data wordt automatisch gebruikt bij integratietests:

```bash
make integration      # Test de volledige pipeline met synthetische data
```

De `docker-compose.test.yml` mount de synthetische data als input-volumes:

```yaml
volumes:
  - ./data/synthetic/data/projecten:/input/projecten
  - ./data/synthetic/data/delfit:/input/delfit
  - ./data/synthetic/data/magazijnlijst:/input/magazijnlijst
  - ./data/synthetic/data/digifotos:/input/digifotos
```

Om de synthetische data met de volledige Wasstraat-applicatie te gebruiken, pas je dezelfde volume-mappings toe in je eigen docker-compose override.

## Opnieuw genereren

Vereisten:
- Java JRE (`brew install openjdk` op macOS)
- Python packages: `pip install -r generatie/requirements-synthetic.txt`
- Jackcess JARs in `generatie/jars/` (al aanwezig in de repo)

```bash
make synthetic
```

## Eigen data klaarzetten

Wil je als gemeente je eigen data verwerken? Organiseer je bestanden conform dezelfde structuur:

```
data/input/basefiles/projectdatabase/
├── digidepot/           # Per project een subdirectory met .mdb
│   ├── PROJECT001/
│   │   └── C Database/PROJECT001.mdb
│   └── PROJECT002/
│       └── C Database/PROJECT002.mdb
├── Delf-IT/             # Centrale administratiedatabase
├── magazijnlijst/       # Depot- en magazijnadministratie
├── digifotos/           # Digitale fotolijst
└── referentietabellen/  # ABR-codes en standaardtabellen
```

Zie de [handleiding Aan de slag](https://brienen.github.io/wasstraat_archeologische_data/aan-de-slag/) voor gedetailleerde instructies.
