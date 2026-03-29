# Synthetische Voorbeelddata

Fictieve maar realistische archeologische data voor de Wasstraat. Deze data dient als werkend voorbeeld van de bestandsstructuur die het platform verwacht. De echte Delftse opgravingsdata is niet opgenomen in de repository.

Gemeenten die hun eigen data willen verwerken, kunnen deze voorbeeldstructuur als referentie gebruiken om hun bronbestanden op dezelfde manier te organiseren.

## Scenario's

### SY001 — Klein project (Marktstraat 10, Voorburg)
- 2 putten, 3 sporen, 4 vondsten, 5 artefacten (aardewerk + glas)
- 2 vullingen, 7 tekeningen, 3 foto's
- 3 monsters (2 met botanische determinaties, 1 zoölogisch)
- 1 monster met opzettelijk foute projectcode (SYNTFOUT) — test voor correctiemechanisme
- Datering: 1600-1750

### SY002 — Groot project (Kerkplein, Leiden)
- 4 putten, 8 sporen, 12 vondsten, 20 artefacten (8 materiaalsoorten)
- 4 vullingen, 10 foto's
- 2 monsters (uit beerput en greppel, met botanische en schelpdeterminaties)
- Materiaalsoorten: aardewerk, glas, been, metaal, leer, steen, kleipijp, munten
- Datering: 1200-1800

## Structuur

```
data/synthetic/
├── data/                                              # Gegenereerde bronbestanden
│   ├── projecten/                                     # Opgravingsdatabases + foto's
│   │   ├── SY001/
│   │   │   ├── C Database/opgravingSY001.mdb          #   Projectdatabase (putten, sporen, vondsten, artefacten)
│   │   │   └── L Fotos/                               #   Foto's (sfeer-, opgravinqs- en objectfoto's)
│   │   └── SY002/
│   │       ├── C Database/opgravingSY002.mdb
│   │       └── L Fotos/
│   ├── projectenlijst/                                # Projectoverzicht
│   │   └── projectenlijst.mdb                         #   Tabel OPGRAVINGEN: projectcode, locatie, jaar
│   ├── magazijnlijst/                                 # Depotadministratie
│   │   └── MAGAZIJN.mdb                               #   Tabel magazijnlijst: stellingen, dozen, inhoud
│   ├── fotolijst/                                     # Fotocatalogus
│   │   └── Digifotos.mdb                              #   Tabel Fotos: fotonr, projectcode, bestandsnaam
│   ├── monsterdatabase/                               # Monsters en determinaties
│   │   └── MONSTERS.mdb                               #   Monster_gegevens, Monster_waardering, botanie, schelp
│   ├── referentietabellen/                            # Standaardtabellen
│   │   ├── abr_versie_01122018.xlsx                   #   ABR-thesaurus (perioden, materialen)
│   │   └── Alle Bestanden Archeologisch Depot.xlsx    #   Depotinventarisatie
│   └── rapporten/                                     # Rapporten (leeg in synthetische data)
├── wasstraat_config/                                  # Pipeline-configuratie
│   ├── Wasstraat_Config_HarmonizeV3.xlsx              #   Harmonisatie-mapping (veldnamen per objecttype)
│   └── correcties.yml                                 #   Datacorrecties (projectcodes, rapportprefixen)
├── generatie/                                         # Alles voor (her)generatie
│   ├── generate_synthetic_data.py                     #   Generator-script
│   ├── requirements-synthetic.txt                     #   Python dependencies
│   └── jars/                                          #   Jackcess JARs (voor MDB-generatie)
├── output/                                            # Verwerkte output (gegenereerd door pipeline)
│   └── archeomedia/                                   #   Verwerkte mediabestanden
└── backup/                                            # Backups (gegenereerd door make backup)
```

### Wat zit in elk MDB-bestand?

| Directory | MDB-bestand | Tabellen | Beschrijving |
|-----------|-------------|----------|-------------|
| `projecten/` | `opgravingSY0xx.mdb` | VONDSTENLIJST, SPOREN, VULLINGEN, AARDEWERK 1, GLAS, METAAL, BEEN, LEER, HOUT, STEEN, KLEIPIJPEN, TEKENINGEN, DIAOPGRAVING | Eén database per opgraving, met alle vondsten, sporen en artefacten |
| `projectenlijst/` | `projectenlijst.mdb` | OPGRAVINGEN | Overzicht van alle projecten: code, locatie (RD), jaar, trefwoorden |
| `magazijnlijst/` | `MAGAZIJN.mdb` | magazijnlijst | Depotadministratie: stellingen, vakken, dozen, inhoud |
| `fotolijst/` | `Digifotos.mdb` | Fotos | Fotocatalogus: koppeling fotonummer ↔ project, put, vondst |
| `monsterdatabase/` | `MONSTERS.mdb` | Monster_gegevens, Monster_waardering, Monster_botanie_determinatie, Monster_schelp_determinatie, R_PLANT, R_SCHELP, R_DEEL, R_STAAT | Grondmonsters met botanische en zoölogische determinaties |
| `referentietabellen/` | *(xlsx)* | — | ABR-thesaurus en depotinventarisatie (geen MDB maar Excel) |

## Gebruik met de Wasstraat

De synthetische data wordt automatisch gebruikt bij integratietests:

```bash
make integration      # Test de volledige pipeline met synthetische data
```

De `docker-compose.test.yml` mount de synthetische data als input-volumes:

```yaml
volumes:
  - ./data/synthetic/data/projecten:/input/projecten
  - ./data/synthetic/data/projectenlijst:/input/projectenlijst
  - ./data/synthetic/data/magazijnlijst:/input/magazijnlijst
  - ./data/synthetic/data/fotolijst:/input/fotolijst
  - ./data/synthetic/data/monsterdatabase:/input/monsterdatabase
  - ./data/synthetic/data/referentietabellen:/input/referentietabellen
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

## Correcties (correcties.yml)

Het bestand `wasstraat_config/correcties.yml` bevat gemeente-specifieke datacorrecties. De synthetische data bevat een testgeval: een monster met projectcode `SYNTFOUT` dat via de correcties naar `SY001` vertaald wordt.

Twee soorten correcties:

- **`projectcode_correcties`** — fix `projectcd` na harmonisatie (eenvoudig: patroon → projectcode)
- **`brondata_correcties`** — fix raw velden in staging vóór harmonisatie (nodig als brondata niet matcht met de projectenlijst)

Zie `data/delft/wasstraat_config/correcties.yml` voor een volledig Delft-voorbeeld.

## Eigen data klaarzetten

Wil je als gemeente je eigen data verwerken? Organiseer je bestanden conform dezelfde structuur:

```
data/delft/data/
├── projecten/           # Per project een subdirectory met .mdb
│   ├── PROJECT001/
│   │   └── C Database/PROJECT001.mdb
│   └── PROJECT002/
│       └── C Database/PROJECT002.mdb
├── projectenlijst/      # Centrale administratiedatabase
├── magazijnlijst/       # Depot- en magazijnadministratie
├── fotolijst/           # Digitale fotolijst
└── referentietabellen/  # ABR-codes en standaardtabellen
```

Zie de [handleiding Aan de slag](https://brienen.github.io/wasstraat_archeologische_data/aan-de-slag/) voor gedetailleerde instructies.
