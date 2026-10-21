# Voorbeelddata

De repository bevat **synthetische voorbeelddata** in `data/synthetic/data/` — fictieve maar realistische archeologische data waarmee je de volledige Wasstraat-pipeline kunt testen zonder eigen brondata. De echte Delftse opgravingsdata is niet opgenomen in de repository.

## Twee voorbeeldprojecten

| Project | Beschrijving | Putten | Vlakken | Sporen | Vondsten | Artefacten | Datering |
|---------|-------------|--------|---------|--------|----------|------------|----------|
| **SY001** | Klein project (Marktstraat 10, Voorburg) | 2 | 2 | 3 | 4 | 5 (aardewerk, glas) | 1600-1750 |
| **SY002** | Groot project (Kerkplein, Leiden) | 4 | 8 | 8 | 12 | 20 (8 materiaalsoorten) | 1200-1800 |

De aantallen zijn wat na een volledige run in PostgreSQL staat; in totaal zijn dat 25 artefacten (ook in `Single_Store_Clean`). De projectdatabases hebben geen PUT- of VLAK-tabel: de pipeline leidt putten en vlakken af uit de put- en vlaknummers van sporen, vondsten, tekeningen en foto's (zie [Transformatie](../componenten/transformatie.md#7-ontbrekende-entiteiten-aanvullen)).

SY002 bevat een breed scala aan materiaalsoorten: aardewerk, glas, been, metaal, leer, steen, kleipijp en munten. De munt en een aardewerkscherf uit vondst 11 hebben hetzelfde artefactnummer, maar worden niet samengevoegd: de munt komt uit een artefactsoort-specifieke tabel (`MUNTEN EN PENNINGEN`) en wordt direct verplaatst, zodat 20 bronregels 20 artefacten opleveren. Beide projecten bevatten ook depot- en fotometadata.

Daarnaast bevat de synthetische data een **monsterdatabase** met 6 grondmonsters (3× SY001, 2× SY002 en 1 met de foute projectcode `SYNTFOUT`, die `correcties.yml` naar SY001 vertaalt), 8 botanische determinaties, 4 schelpdeterminaties en bijbehorende referentietabellen (plantensoorten, schelpsoorten, deeltypen, conserveringstoestanden).

## Bestandsstructuur

De synthetische data volgt exact dezelfde directorystructuur als echte opgravingsdata:

```
data/synthetic/data/
├── projecten/
│   ├── SY001/
│   │   ├── C Database/opgravingSY001.mdb    # Projectdatabase
│   │   └── L Fotos/                         # Foto's
│   └── SY002/
│       ├── C Database/opgravingSY002.mdb
│       └── L Fotos/                         # Project- en sfeerfoto's (G/F), tekening (B)
│           └── H (Objectfoto's)/            # Objectfoto's per materiaal, bijv.
│               ├── Aardewerk/SY002_P2_H4_1_1.jpg    # put 2, vondst 4, subnr 1 → artefact
│               └── Munt/SY002_P4_H11_1_1.jpg
├── projectenlijst/projectenlijst.mdb         # Projectenlijst
├── magazijnlijst/MAGAZIJN.mdb               # Depotdata
├── fotolijst/Digifotos.mdb                  # Fotocatalogus
└── monsterdatabase/MONSTERS.mdb             # Monsterdata (botanie + schelpen)
```

## Gebruik bij testen

De synthetische data wordt automatisch gebruikt bij de standaard integratietests:

```bash
make integration        # Test pipeline met synthetische data
```

De `docker-compose.test.yml` mount de synthetische data als input-volumes voor de Airflow-container.

## Eigen data klaarzetten

Gemeenten die hun eigen opgravingsdata willen verwerken, kunnen hun bestanden organiseren conform dezelfde structuur als de voorbeelddata:

| Directory | Inhoud | Verwachte tabellen/bestanden | Verplicht? |
|-----------|--------|------------------------------|-----------|
| `projecten/` | Per opgraving een subdirectory met projectdatabase en foto's | `.mdb` met VONDSTENLIJST, SPOREN, VULLINGEN, artefacttabellen | Ja |
| `projectenlijst/` | Projectoverzicht | `.mdb` met tabel `OPGRAVINGEN` (CODE, XCOORD, YCOORD, JAAR) | Ja |
| `magazijnlijst/` | Depotadministratie | `.mdb` met tabel `magazijnlijst` (CODE, STELLING, DOOSNO) | Aanbevolen |
| `fotolijst/` | Fotocatalogus | `.mdb` met tabel `Fotos` (FOTONR, PROJECTCD, BESTANDSNAAM) | Aanbevolen |
| `monsterdatabase/` | Monsters en determinaties | `.mdb` met Monster_gegevens, Monster_waardering, etc. | Optioneel |
| `referentietabellen/` | ABR-codes en standaardtabellen | `abr_versie_*.xlsx` | Ja |
| `rapporten/` | Rapportbestanden | `.mdb` / `.pdf` | Optioneel |

De Wasstraat doorzoekt elke directory **recursief** op `.mdb` en `.accdb` bestanden. In `projecten/` moet je per opgraving een subdirectory aanmaken — de directorynaam bepaalt de projectcode.

Plaats de bestanden in `data/<omgeving>/data/` en configureer optioneel een `correcties.yml` in `data/<omgeving>/wasstraat_config/` voor projectcode-correcties. Zie [Aan de slag](../aan-de-slag.md) voor gedetailleerde instructies.

## Data opnieuw genereren

De synthetische data kan opnieuw gegenereerd worden met het generatorscript in `data/synthetic/generatie/`:

```bash
make synthetic
```

Vereisten voor regeneratie:

- Java JRE (voor Jackcess MDB-schrijver): `brew install openjdk` op macOS, of een OpenJDK 21 in `/usr/lib/jvm/java-21-openjdk` op Linux
- Python packages uit `data/synthetic/generatie/requirements-synthetic.txt` (installeert `make synthetic` zelf in de `.venv`)
- Jackcess JARs (al aanwezig in `data/synthetic/generatie/jars/`)
