#!/usr/bin/env python3
"""
Genereer synthetische archeologische data als MDB-bestanden.

Produceert twee scenario's:
  - SY001: Klein project (Marktstraat 10, Voorburg)
  - SY002: Groot project (Kerkplein, Leiden)

Vereisten:
  - Java JRE (openjdk via brew of apt)
  - Python packages: msaccessdb, JPype1
  - Jackcess JAR + dependencies in data/synthetic/jars/

Gebruik:
  python data/synthetic/generate_synthetic_data.py
"""

import os
import sys
import msaccessdb

# JPype wordt pas geïmporteerd in startJvm() zodat tests zonder Java kunnen draaien
jpype = None
JClass = None


# ============================================================
# Paden
# ============================================================

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SYNTHETIC_DIR = os.path.dirname(SCRIPT_DIR)
JARS_DIR = os.path.join(SCRIPT_DIR, "jars")
OUTPUT_DIR = os.path.join(SYNTHETIC_DIR, "data")

JAR_FILES = [
    os.path.join(JARS_DIR, "jackcess-4.0.5.jar"),
    os.path.join(JARS_DIR, "commons-lang3-3.14.0.jar"),
    os.path.join(JARS_DIR, "commons-logging-1.3.0.jar"),
]


# ============================================================
# JVM en database-hulpfuncties (Jackcess via JPype)
# ============================================================

def startJvm():
    """Start de Java Virtual Machine met Jackcess op het classpath."""
    global jpype, JClass
    import jpype as _jpype
    import jpype.imports
    jpype = _jpype
    JClass = jpype.JClass

    if not jpype.isJVMStarted():
        classpath = ":".join(JAR_FILES)
        jpype.startJVM(classpath=[classpath])


def maakMdbBestand(pad):
    """Maak een leeg MDB-bestand aan.

    Args:
        pad: Volledig pad naar het MDB-bestand
    """
    os.makedirs(os.path.dirname(pad), exist_ok=True)
    if os.path.exists(pad):
        os.remove(pad)
    msaccessdb.create(pad)
    print(f"  Leeg MDB aangemaakt: {pad}")


# Mapping van SQL-types naar Jackcess DataType enum waarden
TYPE_MAP = {
    "VARCHAR": "TEXT",
    "INTEGER": "LONG",
    "DOUBLE": "DOUBLE",
    "COUNTER": "LONG",
}


def jackcessDataType(sql_type):
    """Vertaal een SQL-type string naar een Jackcess DataType enum waarde.

    Args:
        sql_type: SQL type string zoals 'VARCHAR(50)', 'INTEGER', 'DOUBLE'

    Returns:
        Jackcess DataType enum waarde
    """
    DataType = JClass("com.healthmarketscience.jackcess.DataType")
    base = sql_type.split("(")[0].upper()
    jtype = TYPE_MAP.get(base, "TEXT")
    return DataType.valueOf(jtype)


def openMdb(pad):
    """Open een MDB-bestand met Jackcess DatabaseBuilder.

    Args:
        pad: Volledig pad naar het MDB-bestand

    Returns:
        Jackcess Database object
    """
    File = JClass("java.io.File")
    DatabaseBuilder = JClass("com.healthmarketscience.jackcess.DatabaseBuilder")
    return DatabaseBuilder.open(File(pad))


def maakTabelJackcess(db, tabelnaam, kolommen):
    """Maak een tabel aan in de Jackcess database.

    Args:
        db: Jackcess Database object
        tabelnaam: Naam van de tabel
        kolommen: Lijst van (kolomnaam, type) tuples

    Returns:
        Jackcess Table object
    """
    TableBuilder = JClass("com.healthmarketscience.jackcess.TableBuilder")
    ColumnBuilder = JClass("com.healthmarketscience.jackcess.ColumnBuilder")

    tb = TableBuilder(tabelnaam)

    # ID kolom (autoincrement)
    col_id = ColumnBuilder("ID", jackcessDataType("COUNTER"))
    col_id.setAutoNumber(True)
    tb.addColumn(col_id)

    for naam, dtype in kolommen:
        col = ColumnBuilder(naam, jackcessDataType(dtype))
        tb.addColumn(col)

    return tb.toTable(db)


def voegRecordsIn(table, kolommen, records):
    """Voeg records in via Jackcess Table.addRow().

    Args:
        table: Jackcess Table object
        kolommen: Lijst van kolomnamen (zonder ID)
        records: Lijst van tuples met waarden
    """
    for record in records:
        # Bouw een rij-array: ID=None (autoincrement) + waarden
        row_values = [None]  # ID = autoincrement
        for val in record:
            if val is None:
                row_values.append(None)
            elif isinstance(val, int):
                row_values.append(jpype.JInt(val))
            elif isinstance(val, float):
                row_values.append(jpype.JDouble(val))
            else:
                row_values.append(str(val))
        table.addRow(*row_values)


# ============================================================
# Tabelstructuren (gebaseerd op echte MDB-structuur)
# ============================================================

KOLOMMEN_VONDSTENLIJST = [
    ("CODENAAM", "VARCHAR(20)"),
    ("PUTNO", "INTEGER"),
    ("VLAKNO", "INTEGER"),
    ("VONDSTNO", "INTEGER"),
    ("SPOORNO", "INTEGER"),
    ("LENGTE", "VARCHAR(20)"),
    ("BREEDTE", "VARCHAR(20)"),
    ("DIEPTE", "VARCHAR(20)"),
    ("PROFIEL", "VARCHAR(50)"),
    ("VONDSTOMSTH", "VARCHAR(100)"),
    ("INHOUD", "VARCHAR(200)"),
    ("VOORLOPIGEDATERING", "VARCHAR(50)"),
    ("DATUM", "VARCHAR(20)"),
    ("XCOORD", "DOUBLE"),
    ("YCOORD", "DOUBLE"),
]

KOLOMMEN_SPOREN = [
    ("CODENAAM", "VARCHAR(20)"),
    ("PUTNO", "INTEGER"),
    ("VLAKNO", "INTEGER"),
    ("SPOORNO", "INTEGER"),
    ("AARD", "VARCHAR(50)"),
    ("HB", "VARCHAR(20)"),
    ("LB", "VARCHAR(20)"),
    ("BB", "VARCHAR(20)"),
    ("HO", "VARCHAR(20)"),
    ("LO", "VARCHAR(20)"),
    ("BO", "VARCHAR(20)"),
    ("VORM", "VARCHAR(50)"),
    ("STEENFORMAAT", "VARCHAR(50)"),
    ("RICHTING SPOOR", "VARCHAR(50)"),
    ("JONGER DAN", "VARCHAR(50)"),
    ("OUDER DAN", "VARCHAR(50)"),
    ("GELIJKTIJDIG MET", "VARCHAR(50)"),
    ("IDENTIEK AAN", "VARCHAR(50)"),
    ("VERBANDEN (muur)", "VARCHAR(100)"),
    ("FOTONUMMER(S)", "VARCHAR(50)"),
    ("PROFIEL", "VARCHAR(50)"),
    ("BESCHRIJVING", "VARCHAR(255)"),
    ("INTERPRETATIE", "VARCHAR(200)"),
    ("PER", "VARCHAR(20)"),
    ("FASE", "VARCHAR(20)"),
    ("DAT", "VARCHAR(50)"),
    ("DATUM", "VARCHAR(20)"),
    ("DETERM", "VARCHAR(100)"),
]

KOLOMMEN_VULLINGEN = [
    ("CODENAAM", "VARCHAR(20)"),
    ("PUTNO", "INTEGER"),
    ("SPOORNO", "INTEGER"),
    ("VULLINGNO", "INTEGER"),
    ("GRONDSOORT", "VARCHAR(50)"),
    ("KLEUR", "VARCHAR(50)"),
    ("TEXTUUR", "VARCHAR(50)"),
    ("VONDSTNUMMERS", "VARCHAR(100)"),
]

KOLOMMEN_AARDEWERK = [
    ("CODENAAM", "VARCHAR(20)"),
    ("PUTNO", "INTEGER"),
    ("VONDSTNO", "INTEGER"),
    ("SUBNO", "INTEGER"),
    ("1b", "VARCHAR(50)"),      # baksel
    ("1c", "VARCHAR(50)"),      # subbaksel
    ("2", "VARCHAR(50)"),       # fragment
    ("3", "VARCHAR(50)"),       # vormtype/voorwerp
    ("3a", "VARCHAR(50)"),
    ("3b", "VARCHAR(50)"),
    ("DR", "INTEGER"),          # randdiameter
    ("DB", "INTEGER"),          # bodemdiameter
    (">D", "VARCHAR(10)"),
    ("H", "INTEGER"),           # hoogte
    ("4b", "VARCHAR(50)"),      # glazuur
    ("4b1", "VARCHAR(50)"),
    ("4b2", "VARCHAR(50)"),
    ("4c", "VARCHAR(50)"),
    ("4d", "VARCHAR(50)"),
    ("5a", "VARCHAR(50)"),      # versiering
    ("5a1", "VARCHAR(50)"),
    ("5b", "VARCHAR(50)"),
    ("5c", "VARCHAR(50)"),
    ("5d", "VARCHAR(50)"),
    ("5e", "VARCHAR(50)"),
    ("5f", "VARCHAR(50)"),
    ("6a", "VARCHAR(50)"),      # datering begin
    ("6b", "VARCHAR(50)"),      # datering eind
    ("6c", "VARCHAR(50)"),
    ("6d", "VARCHAR(50)"),
    ("7a", "VARCHAR(50)"),      # opmerking
    ("7b", "VARCHAR(50)"),
    ("8", "VARCHAR(50)"),       # doosno
    ("9", "VARCHAR(50)"),       # tekno
    ("10a", "VARCHAR(50)"),
    ("10b", "VARCHAR(50)"),
    ("10c", "VARCHAR(50)"),
    ("10d", "VARCHAR(50)"),
    ("11", "VARCHAR(50)"),
    ("12", "VARCHAR(50)"),
    ("13", "VARCHAR(50)"),
]

KOLOMMEN_GLAS = [
    ("CODENAAM", "VARCHAR(20)"),
    ("PUTNO", "INTEGER"),
    ("VONDSTNO", "INTEGER"),
    ("SUBNO", "INTEGER"),
    ("1b", "VARCHAR(50)"),      # glassoort
    ("1c", "VARCHAR(50)"),
    ("2", "VARCHAR(50)"),       # fragment
    ("3", "VARCHAR(50)"),       # voorwerp
    ("DR", "INTEGER"),
    ("DB", "INTEGER"),
    (">D", "VARCHAR(10)"),
    ("H", "INTEGER"),
    ("OPMERKING", "VARCHAR(200)"),
    ("4b", "VARCHAR(50)"),
    ("4c", "VARCHAR(50)"),
    ("4d", "VARCHAR(50)"),
    ("5a", "VARCHAR(50)"),
    ("5b", "VARCHAR(50)"),
    ("5c", "VARCHAR(50)"),
    ("5d", "VARCHAR(50)"),
    ("6a", "VARCHAR(50)"),
    ("6b", "VARCHAR(50)"),
    ("6c", "VARCHAR(50)"),
    ("6d", "VARCHAR(50)"),
    ("7a", "VARCHAR(50)"),
    ("7b", "VARCHAR(50)"),
    ("8", "VARCHAR(50)"),
    ("9", "VARCHAR(50)"),
    ("10a", "VARCHAR(50)"),
    ("10b", "VARCHAR(50)"),
    ("10c", "VARCHAR(50)"),
    ("11", "VARCHAR(50)"),
    ("12", "VARCHAR(50)"),
    ("13", "VARCHAR(50)"),
]

KOLOMMEN_BEEN = [
    ("CODENAAM", "VARCHAR(20)"),
    ("PUTNO", "INTEGER"),
    ("VLAKNO", "INTEGER"),
    ("VONDSTNO", "INTEGER"),
    ("SUBNO", "INTEGER"),
    ("VOORWERP", "VARCHAR(100)"),
    ("FUNCTIE", "VARCHAR(50)"),
    ("MATERIAAL", "VARCHAR(50)"),
    ("AFMETINGEN", "VARCHAR(50)"),
    ("OPMERKING", "VARCHAR(200)"),
    ("PERCENTAGE", "VARCHAR(20)"),
    ("BEWERKING", "VARCHAR(50)"),
    ("TEKNO", "VARCHAR(20)"),
    ("FOTONO", "VARCHAR(20)"),
    ("DOOSNO", "VARCHAR(20)"),
    ("BIBLIOGRAFIE", "VARCHAR(200)"),
    ("GECONSERVEERD", "VARCHAR(10)"),
]

KOLOMMEN_METAAL = [
    ("CODENAAM", "VARCHAR(20)"),
    ("PUTNO", "INTEGER"),
    ("VONDSTNO", "INTEGER"),
    ("SUBNO", "INTEGER"),
    ("3", "VARCHAR(50)"),       # voorwerp
    ("4a", "VARCHAR(50)"),
    ("4b", "VARCHAR(50)"),
    ("4c", "VARCHAR(50)"),
    ("5a", "VARCHAR(50)"),      # materiaal
    ("5b", "VARCHAR(50)"),
    ("5c", "VARCHAR(50)"),
    ("5d", "VARCHAR(50)"),
    ("5e", "VARCHAR(50)"),
    ("6d", "VARCHAR(50)"),
    ("7a", "VARCHAR(50)"),
    ("7b", "VARCHAR(50)"),
    ("7c", "VARCHAR(50)"),
    ("9", "VARCHAR(50)"),
    ("10a", "VARCHAR(50)"),
    ("10b", "VARCHAR(50)"),
    ("10c", "VARCHAR(50)"),
    ("10d", "VARCHAR(50)"),
    ("11", "VARCHAR(50)"),
    ("12", "VARCHAR(50)"),
    ("13", "VARCHAR(50)"),
    ("14", "VARCHAR(50)"),
]

KOLOMMEN_LEER = [
    ("CODENAAM", "VARCHAR(20)"),
    ("PUTNO", "INTEGER"),
    ("VONDSTNO", "INTEGER"),
    ("SUBNO", "INTEGER"),
    ("1b", "VARCHAR(50)"),
    ("1c", "VARCHAR(50)"),
    ("2", "VARCHAR(50)"),
    ("3", "VARCHAR(50)"),
    ("4a", "VARCHAR(50)"),
    ("4b", "VARCHAR(50)"),
    ("4c", "VARCHAR(50)"),
    ("4d", "VARCHAR(50)"),
    ("4e", "VARCHAR(50)"),
    ("4f", "VARCHAR(50)"),
    ("5a", "VARCHAR(50)"),
    ("5b", "VARCHAR(50)"),
    ("5c", "VARCHAR(50)"),
    ("5d", "VARCHAR(50)"),
    ("6a", "VARCHAR(50)"),
    ("6b", "VARCHAR(50)"),
    ("6c", "VARCHAR(50)"),
    ("6d", "VARCHAR(50)"),
    ("6e", "VARCHAR(50)"),
    ("6f", "VARCHAR(50)"),
    ("7a", "VARCHAR(50)"),
    ("7b", "VARCHAR(50)"),
    ("8", "VARCHAR(50)"),
    ("9", "VARCHAR(50)"),
    ("10a", "VARCHAR(50)"),
    ("10b", "VARCHAR(50)"),
    ("10c", "VARCHAR(50)"),
    ("11", "VARCHAR(50)"),
    ("12", "VARCHAR(50)"),
    ("13", "VARCHAR(50)"),
    ("14", "VARCHAR(50)"),
]

KOLOMMEN_HOUT = [
    ("CODENAAM", "VARCHAR(20)"),
    ("PUTNO", "INTEGER"),
    ("VONDSTNO", "INTEGER"),
    ("SUBNO", "INTEGER"),
    ("1b", "VARCHAR(50)"),
    ("1c", "VARCHAR(50)"),
    ("2", "VARCHAR(50)"),
    ("3", "VARCHAR(50)"),
    ("JSB", "VARCHAR(20)"),
    ("DENDRO", "VARCHAR(20)"),
    ("C14", "VARCHAR(20)"),
    ("4a", "VARCHAR(50)"),
    ("D-BOOM", "VARCHAR(50)"),
    ("STC", "VARCHAR(20)"),
    ("PUNTV", "VARCHAR(20)"),
    ("PUNTL", "VARCHAR(20)"),
    ("4b", "VARCHAR(50)"),
    ("4c", "VARCHAR(50)"),
    ("DET_W", "VARCHAR(50)"),
    ("5a", "VARCHAR(50)"),
    ("5b", "VARCHAR(50)"),
    ("5b1", "VARCHAR(50)"),
    ("5c", "VARCHAR(50)"),
    ("5d", "VARCHAR(50)"),
    ("6d", "VARCHAR(50)"),
    ("7a", "VARCHAR(50)"),
    ("7b", "VARCHAR(50)"),
    ("8", "VARCHAR(50)"),
    ("9", "VARCHAR(50)"),
    ("10a", "VARCHAR(50)"),
    ("10a1", "VARCHAR(50)"),
    ("10b", "VARCHAR(50)"),
    ("10c", "VARCHAR(50)"),
    ("10d", "VARCHAR(50)"),
    ("11", "VARCHAR(50)"),
    ("12", "VARCHAR(50)"),
    ("13", "VARCHAR(50)"),
    ("14", "VARCHAR(50)"),
]

KOLOMMEN_STEEN = [
    ("CODENAAM", "VARCHAR(20)"),
    ("PUTNO", "INTEGER"),
    ("VONDSTNO", "INTEGER"),
    ("SUBNO", "INTEGER"),
    ("1b", "VARCHAR(50)"),
    ("1c", "VARCHAR(50)"),
    ("3", "VARCHAR(50)"),
    ("DIKTE", "VARCHAR(20)"),
    ("LENGTE", "VARCHAR(20)"),
    ("DIAMETER", "VARCHAR(20)"),
    ("4b", "VARCHAR(50)"),
    ("4c", "VARCHAR(50)"),
    ("4d", "VARCHAR(50)"),
    ("5a", "VARCHAR(50)"),
    ("5a1", "VARCHAR(50)"),
    ("5b", "VARCHAR(50)"),
    ("5c", "VARCHAR(50)"),
    ("5d", "VARCHAR(50)"),
    ("6d", "VARCHAR(50)"),
    ("7a", "VARCHAR(50)"),
    ("7b", "VARCHAR(50)"),
    ("8", "VARCHAR(50)"),
    ("9", "VARCHAR(50)"),
    ("10a", "VARCHAR(50)"),
    ("10b", "VARCHAR(50)"),
    ("10c", "VARCHAR(50)"),
    ("10d", "VARCHAR(50)"),
    ("11", "VARCHAR(50)"),
    ("12", "VARCHAR(50)"),
    ("13", "VARCHAR(50)"),
]

KOLOMMEN_KLEIPIJPEN = [
    ("CODENAAM", "VARCHAR(20)"),
    ("PUTNO", "INTEGER"),
    ("VONDSTNO", "INTEGER"),
    ("SUBNO", "INTEGER"),
    ("1b", "VARCHAR(50)"),
    ("1c", "VARCHAR(50)"),
    ("2", "VARCHAR(50)"),
    ("3", "VARCHAR(50)"),
    ("3a", "VARCHAR(50)"),
    ("4a", "VARCHAR(50)"),
    ("4b", "VARCHAR(50)"),
    ("4c", "VARCHAR(50)"),
    ("4d", "VARCHAR(50)"),
    ("5a", "VARCHAR(50)"),
    ("5b", "VARCHAR(50)"),
    ("5c", "VARCHAR(50)"),
    ("5d", "VARCHAR(50)"),
    ("6a", "VARCHAR(50)"),
    ("6b", "VARCHAR(50)"),
    ("6c", "VARCHAR(50)"),
    ("6d", "VARCHAR(50)"),
    ("7a", "VARCHAR(50)"),
    ("7b", "VARCHAR(50)"),
    ("8", "VARCHAR(50)"),
    ("9", "VARCHAR(50)"),
    ("10a", "VARCHAR(50)"),
    ("10b", "VARCHAR(50)"),
    ("10c", "VARCHAR(50)"),
    ("11", "VARCHAR(50)"),
    ("12", "VARCHAR(50)"),
    ("13", "VARCHAR(50)"),
]

KOLOMMEN_MUNTEN = [
    ("CODENAAM", "VARCHAR(20)"),
    ("PUTNO", "INTEGER"),
    ("VONDSTNO", "INTEGER"),
    ("SUBNO", "INTEGER"),
    ("MAI", "INTEGER"),
    ("VOORWERP", "VARCHAR(100)"),
    ("RUBRIEK", "VARCHAR(50)"),
    ("LAND", "VARCHAR(50)"),
    ("STAAT", "VARCHAR(50)"),
    ("AUTORITEIT", "VARCHAR(100)"),
    ("MUNTSOORT", "VARCHAR(50)"),
    ("EENHEID / WAARDE", "VARCHAR(50)"),
    ("JAARTAL / DATUM / PERIODE", "VARCHAR(50)"),
    ("DATUM BEGIN", "VARCHAR(20)"),
    ("DATUM EIND", "VARCHAR(20)"),
    ("MATERIAAL", "VARCHAR(50)"),
    ("GEWICHT IN G", "DOUBLE"),
    ("FORMAAT IN MM, HORIZONTAAL", "DOUBLE"),
    ("FORMAAT IN MM, VERTIKAAL", "DOUBLE"),
    ("VORM", "VARCHAR(50)"),
    ("CONDITIE", "VARCHAR(50)"),
    ("OPMERKINGEN", "VARCHAR(255)"),
]

KOLOMMEN_TEKENINGEN = [
    ("CODE", "VARCHAR(20)"),
    ("CODENAAM", "VARCHAR(20)"),
    ("PERIODE", "VARCHAR(50)"),
    ("TEKNO", "INTEGER"),
    ("PUTNO", "INTEGER"),
    ("VLAKNO", "INTEGER"),
    ("PROFIEL", "VARCHAR(50)"),
    ("DETAILS", "VARCHAR(200)"),
    ("SCHAAL", "VARCHAR(20)"),
    ("SOORT", "VARCHAR(50)"),
    ("OMSCHRIJVING", "VARCHAR(200)"),
    ("TEKENAAR", "VARCHAR(50)"),
    ("GEINKT", "VARCHAR(10)"),
    ("DATUM", "VARCHAR(20)"),
    ("MICROFILM", "VARCHAR(20)"),
]

KOLOMMEN_DIAVOORWERP = [
    ("DIANO", "INTEGER"),
    ("PAD", "VARCHAR(200)"),
    ("CODENAAM", "VARCHAR(20)"),
    ("PUTNO", "INTEGER"),
    ("VONDSTNO", "INTEGER"),
    ("SUBNO", "INTEGER"),
    ("OMSCHRIJVING", "VARCHAR(200)"),
    ("DATUM", "VARCHAR(20)"),
    ("FOTOGRAAF", "VARCHAR(50)"),
]

KOLOMMEN_DIAOPGRAVING = [
    ("CODENAAM", "VARCHAR(20)"),
    ("DIANO", "INTEGER"),
    ("PAD", "VARCHAR(200)"),
    ("PUTNO", "INTEGER"),
    ("VLAKNO", "INTEGER"),
    ("SPOORNO", "INTEGER"),
    ("VONDSTNO", "INTEGER"),
    ("OMSCHRIJVING", "VARCHAR(200)"),
    ("PROFIEL", "VARCHAR(50)"),
    ("TEKNO", "INTEGER"),
    ("RICHTING NAAR", "VARCHAR(50)"),
    ("DATUM", "VARCHAR(20)"),
    ("FOTOGRAAF", "VARCHAR(50)"),
]

# DELF-IT OPGRAVINGEN tabel
KOLOMMEN_OPGRAVINGEN = [
    ("CODE", "VARCHAR(20)"),
    ("TOPONIEM", "VARCHAR(100)"),
    ("OPGRAVING", "VARCHAR(200)"),
    ("CODENAAM", "VARCHAR(20)"),
    ("KAARTBLAD", "VARCHAR(20)"),
    ("XCOORD", "DOUBLE"),
    ("YCOORD", "DOUBLE"),
    ("KADASTRAAL", "VARCHAR(100)"),
    ("JAAR", "INTEGER"),
    ("LOKATIE", "VARCHAR(200)"),
    ("VONDSTENLIJST", "VARCHAR(10)"),
    ("SPOREN", "VARCHAR(10)"),
    ("DIAOPGRAVING", "VARCHAR(10)"),
    ("DIAVOORWERP", "VARCHAR(10)"),
    ("TEKENINGEN", "VARCHAR(10)"),
    ("AARDEWERK 1", "VARCHAR(10)"),
    ("GLAS", "VARCHAR(10)"),
    ("BEEN", "VARCHAR(10)"),
    ("METAAL", "VARCHAR(10)"),
    ("MUNTEN EN PENNINGEN", "VARCHAR(10)"),
    ("STEEN", "VARCHAR(10)"),
    ("LEER", "VARCHAR(10)"),
    ("HOUT", "VARCHAR(10)"),
    ("KLEIPIJPEN", "VARCHAR(10)"),
    ("TREFWOORDEN", "VARCHAR(255)"),
    ("NT", "VARCHAR(10)"),
    ("VROEGSTE DATUM", "VARCHAR(20)"),
    ("LAATSTE DATUM", "VARCHAR(20)"),
    ("UITVOERDER", "VARCHAR(100)"),
]

# Magazijnlijst tabel
KOLOMMEN_MAGAZIJNLIJST = [
    ("CODE", "VARCHAR(20)"),
    ("PROJECT", "VARCHAR(200)"),
    ("STELLING", "VARCHAR(20)"),
    ("VAKNO", "VARCHAR(20)"),
    ("VOLGLETTER", "VARCHAR(10)"),
    ("INHOUD", "VARCHAR(200)"),
    ("DOOSNO", "VARCHAR(20)"),
    ("UIT", "VARCHAR(100)"),
]

# ============================================================
# Monsterdatabase tabelstructuren (gebaseerd op MONSTERS.accdb)
# ============================================================

KOLOMMEN_MONSTER_GEGEVENS = [
    ("PROJECT", "VARCHAR(20)"),
    ("PUTNO", "INTEGER"),
    ("VONDSTNO", "INTEGER"),
    ("MONSTERCODE", "VARCHAR(50)"),
    ("DET", "VARCHAR(50)"),
    ("DATUM_DET", "VARCHAR(30)"),
    ("SPOORNO", "INTEGER"),
    ("DOOSNO", "INTEGER"),
    ("VONDSTOMST", "VARCHAR(100)"),
    ("GRONDSOORT", "VARCHAR(50)"),
    ("GEZEEFD_VOL", "DOUBLE"),
    ("ZEEFMAAT", "DOUBLE"),
    ("REST_VOL", "DOUBLE"),
    ("DATUM_ZEVEN", "VARCHAR(30)"),
    ("OPMERKINGEN", "VARCHAR(255)"),
    ("KARAKTERISERING", "VARCHAR(255)"),
    ("R analysewaardig ZO", "VARCHAR(10)"),
    ("R analysewaardig BO", "VARCHAR(10)"),
    ("R concentratie ZO", "VARCHAR(10)"),
    ("R concentratie BO", "VARCHAR(10)"),
    ("R conservering ZO", "VARCHAR(10)"),
    ("R conservering BO", "VARCHAR(10)"),
    ("R diversiteit ZO", "VARCHAR(10)"),
    ("R diversiteit BO", "VARCHAR(10)"),
]

KOLOMMEN_MONSTER_WAARDERING = [
    ("MONSTERCODE", "VARCHAR(50)"),
    ("B stengel onverkoold", "INTEGER"),
    ("B zaden-cultuur onverkoold", "INTEGER"),
    ("B zaden-kaf onverkoold", "INTEGER"),
    ("B zaden-wild onverkoold", "INTEGER"),
    ("B zaden-cultuur mineraaliseerd", "INTEGER"),
    ("C aardewerk", "INTEGER"),
    ("C fabsteen", "INTEGER"),
    ("C glas", "INTEGER"),
    ("C leer", "INTEGER"),
    ("C mortel", "INTEGER"),
    ("C natsteen", "INTEGER"),
    ("C steenkool", "INTEGER"),
    ("C textiel", "INTEGER"),
    ("C leisteen", "INTEGER"),
    ("C overig", "INTEGER"),
    ("D hout", "INTEGER"),
    ("D houtskool", "INTEGER"),
    ("Z amfibiebot O", "INTEGER"),
    ("Z bot-groot O", "INTEGER"),
    ("Z bot-klein O", "INTEGER"),
    ("Z eierschaal/vel O", "INTEGER"),
    ("Z insekten O", "INTEGER"),
    ("Z visgraat/bot O", "INTEGER"),
    ("Z viswervel O", "INTEGER"),
    ("Z visschub O", "INTEGER"),
    ("Z vliegepop O", "INTEGER"),
    ("Z watervlo-ei O", "INTEGER"),
    ("Z wormei O", "INTEGER"),
    ("Z anders", "VARCHAR(200)"),
    ("S molzoet/land", "INTEGER"),
    ("S mollusk zout", "INTEGER"),
    ("S mossel", "INTEGER"),
    ("B wortel onverkoold", "INTEGER"),
    ("B stengel verkoold", "INTEGER"),
    ("B wortel verkoold", "INTEGER"),
    ("B zaden-cultuur verkoold", "INTEGER"),
    ("B zaden-kaf verkoold", "INTEGER"),
    ("B zaden-wild verkoold", "INTEGER"),
    ("B stengel mineraaliseerd", "INTEGER"),
    ("B wortel mineraaliseerd", "INTEGER"),
    ("B zaden-kaf mineraaliseerd", "INTEGER"),
    ("B zaden-wild mineraaliseerd", "INTEGER"),
    ("B stengel recent", "INTEGER"),
    ("B wortel recent", "INTEGER"),
    ("B zaden-cultuur recent", "INTEGER"),
    ("B zaden-kaf recent", "INTEGER"),
    ("B zaden-wild recent", "INTEGER"),
    ("C bewerkt hout", "INTEGER"),
    ("C fosfaat", "INTEGER"),
    ("C huttenleem", "INTEGER"),
    ("C metaal", "INTEGER"),
    ("C ovenslakken", "INTEGER"),
    ("C turf", "INTEGER"),
    ("C antraciet", "INTEGER"),
    ("C kleipijp", "INTEGER"),
    ("C lakzegel", "INTEGER"),
    ("D C14", "INTEGER"),
    ("D tak/knop", "INTEGER"),
    ("D te determ", "INTEGER"),
    ("Z amfibiebot V", "INTEGER"),
    ("Z bot-groot V", "INTEGER"),
    ("Z bot-klein V", "INTEGER"),
    ("Z eierschaal/vel V", "INTEGER"),
    ("Z insekten V", "INTEGER"),
    ("Z visgraat/bot V", "INTEGER"),
    ("Z viswervel V", "INTEGER"),
    ("Z visschub V", "INTEGER"),
    ("Z vliegepop V", "INTEGER"),
    ("Z vogelbot O", "INTEGER"),
    ("Z vogelbot V", "INTEGER"),
    ("Z watervlo-ei V", "INTEGER"),
    ("Z wormei V", "INTEGER"),
    ("S kokkel", "INTEGER"),
    ("S oester", "INTEGER"),
]

KOLOMMEN_MONSTER_BOTANIE = [
    ("MONSTERCODE", "VARCHAR(50)"),
    ("SOORT", "VARCHAR(20)"),
    ("DEEL", "VARCHAR(10)"),
    ("STAAT", "VARCHAR(5)"),
    ("DET", "VARCHAR(50)"),
    ("AANTAL", "INTEGER"),
]

KOLOMMEN_MONSTER_SCHELP = [
    ("MONSTERCODE", "VARCHAR(50)"),
    ("SOORT", "VARCHAR(100)"),
    ("AANTAL", "INTEGER"),
]

KOLOMMEN_R_PLANT = [
    ("SPEC", "VARCHAR(20)"),
    ("OUDE NAAM", "VARCHAR(50)"),
    ("WETENSCHAPPELIJKE NAAM", "VARCHAR(100)"),
    ("NEDERLANDSE NAAM", "VARCHAR(100)"),
]

KOLOMMEN_R_SCHELP = [
    ("CODENAAM", "VARCHAR(20)"),
    ("NAAM LATIJN", "VARCHAR(100)"),
    ("NAAM NEDERLANDS", "VARCHAR(100)"),
    ("MILIEU", "VARCHAR(200)"),
]

KOLOMMEN_R_DEEL = [
    ("DEEL", "VARCHAR(10)"),
    ("OMSCHRIJVING", "VARCHAR(50)"),
    ("UITLEG", "VARCHAR(200)"),
]

KOLOMMEN_R_STAAT = [
    ("STAAT", "VARCHAR(5)"),
    ("OMSCHRIJVING", "VARCHAR(50)"),
    ("STAAT_ID", "INTEGER"),
]

# Digifotos tabel
KOLOMMEN_DIGIFOTOS = [
    ("FOTONR", "INTEGER"),
    ("PROJECTCD", "VARCHAR(20)"),
    ("PUTNO", "INTEGER"),
    ("VLAKNR", "INTEGER"),
    ("SPOORNR", "INTEGER"),
    ("VONDSTNR", "INTEGER"),
    ("OMSCHRIJVING", "VARCHAR(200)"),
    ("BESTANDSNAAM", "VARCHAR(200)"),
    ("FOTOSOORT", "VARCHAR(50)"),
]


# ============================================================
# Scenario SY001 — Klein project (Marktstraat 10, Voorburg)
# ============================================================

def dataKleinProject():
    """Genereer data voor scenario SY001: een klein opgravingsproject.

    Returns:
        Dict met tabelnaam -> (kolommen, records) per tabel
    """
    code = "SY001"

    tabellen = {}

    # Vondstenlijst: 4 vondsten
    kol = [k[0] for k in KOLOMMEN_VONDSTENLIJST]
    tabellen["VONDSTENLIJST"] = (kol, [
        (code, 1, 1, 1, 1, "", "", "", "", "Aanleg vlak", "Aardewerk", "1600-1700", "15-03-2024", 84450.0, 447750.0),
        (code, 1, 1, 2, 2, "", "", "", "", "Coupe spoor 2", "Glas, aardewerk", "17e eeuw", "16-03-2024", 84450.5, 447750.4),
        (code, 2, 1, 3, 3, "", "", "", "", "Aanleg vlak", "Bot", "1650-1750", "18-03-2024", 84455.0, 447747.0),
        (code, 2, 1, 4, 3, "", "", "", "", "Uitschaven spoor 3", "Aardewerk, metaal", "1600-1700", "18-03-2024", 84455.5, 447747.4),
    ])

    # Sporen: 3 sporen
    kol = [k[0] for k in KOLOMMEN_SPOREN]
    tabellen["SPOREN"] = (kol, [
        (code, 1, 1, 1, "Kuil", "DGr", "", "", "", "", "", "Ovaal", "", "", "", "", "", "", "", "", "", "Donkergrijze kuil met houtskoolbrokjes", "Afvalkuil", "", "", "1600-1700", "15-03-2024", ""),
        (code, 1, 1, 2, "Muur", "", "", "", "", "", "", "Lineair", "22x10x5", "NO-ZW", "", "", "", "", "", "", "", "Bakstenen muur, 1 steen breed", "Funderingsmuur", "", "", "17e-18e eeuw", "15-03-2024", ""),
        (code, 2, 1, 3, "Greppel", "LBr", "", "", "", "", "", "Lineair", "", "N-Z", "", "", "", "", "", "", "", "Lichtbruine greppel met puinbijmenging", "Perceelsgreppel", "", "", "1650-1750", "18-03-2024", ""),
    ])

    # Vullingen: 2 vullingen
    kol = [k[0] for k in KOLOMMEN_VULLINGEN]
    tabellen["VULLINGEN"] = (kol, [
        (code, 1, 1, 1, "Klei", "Donkergrijs", "Zandig", "1, 2"),
        (code, 2, 3, 1, "Zand", "Lichtbruin", "Kleiig", "3, 4"),
    ])

    # Aardewerk: 3 stuks
    kol = [k[0] for k in KOLOMMEN_AARDEWERK]
    tabellen["AARDEWERK 1"] = (kol, [
        (code, 1, 1, 1, "Roodbakkend", "", "Rand", "Grape", "", "", 18, None, "", None, "Loodglazuur", "", "", "", "", "", "", "", "", "", "", "", "1550", "1700", "", "", "", "", "D001", "", "", "", "", "", "", "", ""),
        (code, 1, 1, 2, "Witbakkend Delft", "", "Wand", "Bord", "", "", None, None, "", None, "Tinglazuur", "", "", "", "Blauw schildering", "", "", "", "", "", "", "", "1625", "1700", "", "", "", "", "D001", "", "", "", "", "", "", "", ""),
        (code, 2, 4, 1, "Steengoed", "Westerwald", "Bodem", "Kan", "", "", None, 8, "", None, "Zoutglazuur", "", "", "", "Kobaltblauwe versiering", "", "", "", "", "", "", "", "1650", "1750", "", "", "", "", "D002", "", "", "", "", "", "", "", ""),
    ])

    # Glas: 2 stuks
    kol = [k[0] for k in KOLOMMEN_GLAS]
    tabellen["GLAS"] = (kol, [
        (code, 1, 2, 1, "Groen glas", "", "Compleet", "Fles", None, None, "", None, "Wijnfles, donkergroen", "", "", "", "", "", "", "", "1650", "1750", "", "", "", "", "D001", "", "", "", "", "", "", ""),
        (code, 1, 2, 2, "Kleurloos glas", "", "Rand", "Roemer", 8, None, "", None, "Dunwandig drinkglas", "", "", "", "", "", "", "", "1600", "1700", "", "", "", "", "D001", "", "", "", "", "", "", ""),
    ])

    # Tekeningen: 2 tekeningen
    kol = [k[0] for k in KOLOMMEN_TEKENINGEN]
    tabellen["TEKENINGEN"] = (kol, [
        (code, code, "", 1, 1, 1, "", "", "1:20", "Vlaktekening", "Overzicht vlak 1 put 1", "J. de Vries", "Ja", "15-03-2024", ""),
        (code, code, "", 2, 2, 1, "", "", "1:20", "Vlaktekening", "Overzicht vlak 1 put 2", "J. de Vries", "Ja", "18-03-2024", ""),
    ])

    # Diaopgraving (opgravingsfoto's): 3 foto's
    kol = [k[0] for k in KOLOMMEN_DIAOPGRAVING]
    tabellen["DIAOPGRAVING"] = (kol, [
        (code, 1, "", 1, 1, None, None, "Overzicht vlak 1 put 1", "", None, "N", "15-03-2024", "M. Bakker"),
        (code, 2, "", 1, 1, 1, None, "Detail spoor 1", "", None, "NO", "15-03-2024", "M. Bakker"),
        (code, 3, "", 2, 1, 3, None, "Coupe spoor 3", "", None, "W", "18-03-2024", "M. Bakker"),
    ])

    return tabellen


# ============================================================
# Scenario SY002 — Groot project (Kerkplein, Leiden)
# ============================================================

def dataGrootProject():
    """Genereer data voor scenario SY002: een groter opgravingsproject.

    Returns:
        Dict met tabelnaam -> (kolommen, records) per tabel
    """
    code = "SY002"

    tabellen = {}

    # Vondstenlijst: 12 vondsten
    kol = [k[0] for k in KOLOMMEN_VONDSTENLIJST]
    tabellen["VONDSTENLIJST"] = (kol, [
        (code, 1, 1, 1, 1, "", "", "", "", "Aanleg vlak 1", "Aardewerk", "1200-1400", "01-06-2024", 84850.0, 447250.0),
        (code, 1, 1, 2, 1, "", "", "", "", "Coupe spoor 1", "Aardewerk, bot", "1300-1400", "02-06-2024", 84850.3, 447250.3),
        (code, 1, 2, 3, 3, "", "", "", "", "Aanleg vlak 2", "Metaal", "1400-1600", "03-06-2024", 84851.0, 447251.0),
        (code, 2, 1, 4, 4, "", "", "", "", "Aanleg vlak 1", "Aardewerk, glas", "1500-1700", "05-06-2024", 84855.0, 447248.0),
        (code, 2, 1, 5, 4, "", "", "", "", "Coupe spoor 4", "Aardewerk", "1600-1700", "06-06-2024", 84855.5, 447248.4),
        (code, 2, 2, 6, 5, "", "", "", "", "Aanleg vlak 2", "Kleipijp, glas", "1650-1750", "07-06-2024", 84856.0, 447249.0),
        (code, 3, 1, 7, 6, "", "", "", "", "Aanleg vlak 1", "Bot, aardewerk", "1300-1500", "10-06-2024", 84860.0, 447245.0),
        (code, 3, 1, 8, 6, "", "", "", "", "Uitschaven spoor 6", "Leer, hout", "1400-1500", "10-06-2024", 84860.5, 447245.5),
        (code, 3, 2, 9, 7, "", "", "", "", "Aanleg vlak 2", "Aardewerk", "1200-1350", "11-06-2024", 84860.8, 447246.0),
        (code, 4, 1, 10, 8, "", "", "", "", "Aanleg vlak 1", "Steen, metaal", "1500-1700", "14-06-2024", 84865.0, 447242.0),
        (code, 4, 1, 11, 8, "", "", "", "", "Coupe spoor 8", "Munt, aardewerk", "1600-1700", "15-06-2024", 84865.3, 447242.3),
        (code, 4, 3, 12, 8, "", "", "", "", "Aanleg vlak 3", "Aardewerk", "1500-1650", "16-06-2024", 84865.8, 447242.8),
    ])

    # Sporen: 8 sporen
    kol = [k[0] for k in KOLOMMEN_SPOREN]
    tabellen["SPOREN"] = (kol, [
        (code, 1, 1, 1, "Kuil", "DGr", "", "", "", "", "", "Ovaal", "", "", "", "", "", "", "", "", "", "Donkergrijze kuil met hk-inclusies", "Afvalkuil", "", "", "1200-1400", "01-06-2024", ""),
        (code, 1, 1, 2, "Laag", "LBr", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "Ophogingslaag met puin", "Ophogingslaag", "", "", "1400-1600", "01-06-2024", ""),
        (code, 1, 2, 3, "Muur", "", "", "", "", "", "", "Lineair", "24x11x5", "O-W", "", "", "", "", "S4", "", "", "Bakstenen muur, kruisverband", "Buitenmuur", "", "", "1400-1600", "03-06-2024", ""),
        (code, 2, 1, 4, "Beerput", "DGr-Zw", "", "", "", "", "", "Vierkant", "24x11x5", "", "", "", "", "", "", "", "", "Gemetselde beerput, vierkant", "Beerput", "", "", "1500-1700", "05-06-2024", ""),
        (code, 2, 2, 5, "Kuil", "Br", "", "", "", "", "", "Rond", "", "", "S4", "", "", "", "", "", "", "Bruine kuil naast beerput", "Afvalkuil", "", "", "1650-1750", "07-06-2024", ""),
        (code, 3, 1, 6, "Greppel", "LGr", "", "", "", "", "", "Lineair", "", "N-Z", "", "", "", "", "", "", "", "Ondiepe greppel", "Perceelsgreppel", "", "", "1300-1500", "10-06-2024", ""),
        (code, 3, 2, 7, "Kuil", "DGr-Br", "", "", "", "", "", "Ovaal", "", "", "", "S6", "", "", "", "", "", "Grote kuil onder greppel", "Extractiekuil", "", "", "1200-1350", "11-06-2024", ""),
        (code, 4, 1, 8, "Waterput", "DGr", "", "", "", "", "", "Rond", "", "", "", "", "", "", "", "", "", "Gemetselde waterput", "Waterput", "", "", "1500-1700", "14-06-2024", ""),
    ])

    # Vullingen: 4 vullingen
    kol = [k[0] for k in KOLOMMEN_VULLINGEN]
    tabellen["VULLINGEN"] = (kol, [
        (code, 1, 1, 1, "Klei", "Donkergrijs", "Zandig", "1, 2"),
        (code, 2, 4, 1, "Veen", "Zwart", "Humeus", "4, 5"),
        (code, 2, 4, 2, "Klei", "Grijs", "Zandig", ""),
        (code, 3, 6, 1, "Zand", "Lichtgrijs", "Fijn", "7, 8"),
    ])

    # Aardewerk: 8 stuks
    kol = [k[0] for k in KOLOMMEN_AARDEWERK]
    tabellen["AARDEWERK 1"] = (kol, [
        (code, 1, 1, 1, "Grijsbakkend", "", "Rand", "Kogelpot", "", "", 16, None, "", None, "", "", "", "", "", "", "", "", "", "", "", "", "1200", "1350", "", "", "", "", "D003", "", "", "", "", "", "", "", ""),
        (code, 1, 1, 2, "Grijsbakkend", "", "Wand", "Kogelpot", "", "", None, None, "", None, "", "", "", "", "", "", "", "", "", "", "", "", "1200", "1400", "", "", "", "", "D003", "", "", "", "", "", "", "", ""),
        (code, 1, 2, 1, "Roodbakkend", "", "Rand", "Kookpot", "", "", 20, None, "", None, "Loodglazuur", "", "", "", "", "", "", "", "", "", "", "", "1300", "1400", "", "", "", "", "D003", "", "", "", "", "", "", "", ""),
        (code, 2, 4, 1, "Roodbakkend", "", "Compleet", "Grape", "", "", 14, 10, "", 15, "Loodglazuur", "", "", "", "", "", "", "", "", "", "", "", "1500", "1650", "", "", "", "", "D004", "", "", "", "", "", "", "", ""),
        (code, 2, 5, 1, "Witbakkend Delft", "", "Rand", "Bord", "", "", None, None, "", None, "Tinglazuur", "", "", "", "Blauw chinoiserie", "", "", "", "", "", "", "", "1650", "1750", "", "", "", "", "D004", "", "", "", "", "", "", "", ""),
        (code, 3, 7, 1, "Proto-steengoed", "", "Wand", "Kan", "", "", None, None, "", None, "", "", "", "", "", "", "", "", "", "", "", "", "1200", "1300", "", "", "", "", "D005", "", "", "", "", "", "", "", ""),
        (code, 3, 9, 1, "Grijsbakkend", "", "Bodem", "Kogelpot", "", "", None, 12, "", None, "", "", "", "", "", "", "", "", "", "", "", "", "1200", "1350", "", "", "", "", "D005", "", "", "", "", "", "", "", ""),
        (code, 4, 11, 1, "Roodbakkend", "", "Oor", "Kan", "", "", None, None, "", None, "Loodglazuur", "", "", "", "", "", "", "", "", "", "", "", "1550", "1700", "", "", "", "", "D006", "", "", "", "", "", "", "", ""),
    ])

    # Glas: 3 stuks
    kol = [k[0] for k in KOLOMMEN_GLAS]
    tabellen["GLAS"] = (kol, [
        (code, 2, 4, 1, "Groen glas", "", "Rand", "Fles", None, None, "", None, "Wijnfles fragment", "", "", "", "", "", "", "", "1600", "1750", "", "", "", "", "D004", "", "", "", "", "", "", ""),
        (code, 2, 6, 1, "Kleurloos glas", "", "Compleet", "Kelkglas", 6, None, "", 12, "Dunwandig drinkglas", "", "", "", "", "", "", "", "1650", "1750", "", "", "", "", "D004", "", "", "", "", "", "", ""),
        (code, 2, 6, 2, "Groen glas", "", "Bodem", "Roemer", None, 5, "", None, "Cilindrische roemer", "", "", "", "", "", "", "", "1625", "1700", "", "", "", "", "D004", "", "", "", "", "", "", ""),
    ])

    # Been/Bot: 2 stuks
    kol = [k[0] for k in KOLOMMEN_BEEN]
    tabellen["BEEN"] = (kol, [
        (code, 3, 1, 7, 1, "Metatarsus", "Voedsel", "Rund", "12 cm", "Haksporen aanwezig", "", "", "", "", "D005", "", ""),
        (code, 1, 1, 2, 1, "Rib", "Voedsel", "Varken", "8 cm", "", "", "", "", "", "D003", "", ""),
    ])

    # Metaal: 2 stuks
    kol = [k[0] for k in KOLOMMEN_METAAL]
    tabellen["METAAL"] = (kol, [
        (code, 1, 3, 1, "Gesp", "", "", "", "Koper", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", ""),
        (code, 4, 10, 1, "Spijker", "", "", "", "IJzer", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", ""),
    ])

    # Leer: 1 stuk
    kol = [k[0] for k in KOLOMMEN_LEER]
    tabellen["LEER"] = (kol, [
        (code, 3, 8, 1, "Rundleer", "", "Zool", "Schoen", "", "", "", "", "", "", "", "", "", "", "1400", "1500", "", "", "", "", "", "", "D005", "", "", "", "", "", "", "", ""),
    ])

    # Steen: 1 stuk
    kol = [k[0] for k in KOLOMMEN_STEEN]
    tabellen["STEEN"] = (kol, [
        (code, 4, 10, 1, "Natuursteen", "Graniet", "Maalsteen", "3 cm", "25 cm", "30 cm", "", "", "", "", "", "", "", "", "", "", "", "D006", "", "", "", "", "", "", "", ""),
    ])

    # Kleipijpen: 2 stuks
    kol = [k[0] for k in KOLOMMEN_KLEIPIJPEN]
    tabellen["KLEIPIJPEN"] = (kol, [
        (code, 2, 6, 1, "Goudse pijp", "", "Kop", "Pijpekop", "", "WS-gekroond", "", "", "", "", "", "", "", "1660", "1720", "", "", "", "", "D004", "", "", "", "", "", "", ""),
        (code, 2, 6, 2, "Goudse pijp", "", "Steel", "Pijpesteel", "", "", "", "", "", "", "", "", "", "1650", "1750", "", "", "", "", "D004", "", "", "", "", "", "", ""),
    ])

    # Munten: 1 stuk
    kol = [k[0] for k in KOLOMMEN_MUNTEN]
    tabellen["MUNTEN EN PENNINGEN"] = (kol, [
        (code, 4, 11, 1, 1, "Munt", "Gebruiksmunt", "Republiek der Zeven Verenigde Nederlanden", "Holland", "Staten van Holland", "Duit", "1 duit", "1649", "1649", "1649", "Koper", 2.5, 22.0, 22.0, "Rond", "Matig", "Slecht leesbaar maar jaartal herkenbaar"),
    ])

    # Tekeningen: 5 tekeningen
    kol = [k[0] for k in KOLOMMEN_TEKENINGEN]
    tabellen["TEKENINGEN"] = (kol, [
        (code, code, "", 1, 1, 1, "", "", "1:20", "Vlaktekening", "Vlak 1 put 1", "P. Jansen", "Ja", "01-06-2024", ""),
        (code, code, "", 2, 1, 2, "", "", "1:20", "Vlaktekening", "Vlak 2 put 1", "P. Jansen", "Ja", "03-06-2024", ""),
        (code, code, "", 3, 2, 1, "", "", "1:20", "Vlaktekening", "Vlak 1 put 2", "P. Jansen", "Ja", "05-06-2024", ""),
        (code, code, "", 4, 3, 1, "", "", "1:20", "Vlaktekening", "Vlak 1 put 3", "P. Jansen", "Nee", "10-06-2024", ""),
        (code, code, "", 5, 4, 1, "", "Coupe S8", "1:10", "Coupetekening", "Coupe waterput spoor 8", "P. Jansen", "Ja", "15-06-2024", ""),
    ])

    # Diaopgraving: 10 foto's
    kol = [k[0] for k in KOLOMMEN_DIAOPGRAVING]
    tabellen["DIAOPGRAVING"] = (kol, [
        (code, 1, "", 1, 1, None, None, "Overzicht vlak 1 put 1", "", None, "N", "01-06-2024", "K. Smit"),
        (code, 2, "", 1, 2, 3, None, "Detail muur spoor 3", "", None, "O", "03-06-2024", "K. Smit"),
        (code, 3, "", 2, 1, 4, None, "Beerput spoor 4 vlak 1", "", None, "Z", "05-06-2024", "K. Smit"),
        (code, 4, "", 2, 2, 5, None, "Kuil spoor 5 vlak 2", "", None, "W", "07-06-2024", "K. Smit"),
        (code, 5, "", 3, 1, None, None, "Overzicht vlak 1 put 3", "", None, "N", "10-06-2024", "K. Smit"),
        (code, 6, "", 3, 1, 6, None, "Greppel spoor 6", "", None, "O", "10-06-2024", "K. Smit"),
        (code, 7, "", 3, 2, 7, None, "Kuil spoor 7 vlak 2", "", None, "Z", "11-06-2024", "K. Smit"),
        (code, 8, "", 4, 1, None, None, "Overzicht vlak 1 put 4", "", None, "N", "14-06-2024", "K. Smit"),
        (code, 9, "", 4, 1, 8, None, "Waterput spoor 8", "", None, "W", "14-06-2024", "K. Smit"),
        (code, 10, "", 4, 1, 8, None, "Coupe waterput spoor 8", "", None, "O", "15-06-2024", "K. Smit"),
    ])

    return tabellen


# ============================================================
# DELF-IT (projectenlijst) data
# ============================================================

def dataProjectenlijst():
    """Genereer de projectenlijst (DELF-IT equivalent).

    Returns:
        Dict met tabelnaam -> (kolommen, records)
    """
    kol = [k[0] for k in KOLOMMEN_OPGRAVINGEN]
    tabellen = {}
    tabellen["OPGRAVINGEN"] = (kol, [
        ("SY001", "Marktstraat 10", "Opgraving Marktstraat 10, Delft", "SY001",
         "37EN2", 84450.0, 447750.0, "DFT A 1234", 2024, "Delft",
         "Ja", "Ja", "Ja", "Ja", "Ja", "Ja", "Ja", "", "", "", "", "", "", "",
         "Nieuwe Tijd, nederzetting, afvalkuil, muur",
         "Ja", "1600", "1750", "Synthegraven B.V."),
        ("SY002", "Kerkplein", "Opgraving Kerkplein, Delft", "SY002",
         "37EN2", 84850.0, 447250.0, "DFT B 5678", 2024, "Delft",
         "Ja", "Ja", "Ja", "Ja", "Ja", "Ja", "Ja", "Ja", "Ja", "Ja", "Ja", "Ja", "Ja", "Ja",
         "Middeleeuwen, Nieuwe Tijd, beerput, waterput, muur, greppel",
         "Ja", "1200", "1800", "Synthegraven B.V."),
    ])
    return tabellen


# ============================================================
# Magazijnlijst data
# ============================================================

def dataMagazijnlijst():
    """Genereer magazijnlijst (depot) data.

    Returns:
        Dict met tabelnaam -> (kolommen, records)
    """
    kol = [k[0] for k in KOLOMMEN_MAGAZIJNLIJST]
    tabellen = {}
    tabellen["magazijnlijst"] = (kol, [
        ("SY001", "Opgraving Marktstraat, Voorburg", "A01", "01", "a", "Aardewerk", "D001", ""),
        ("SY001", "Opgraving Marktstraat, Voorburg", "A01", "01", "b", "Glas", "D002", ""),
        ("SY002", "Opgraving Kerkplein, Leiden", "B03", "02", "a", "Aardewerk middeleeuws", "D003", ""),
        ("SY002", "Opgraving Kerkplein, Leiden", "B03", "02", "b", "Aardewerk post-middeleeuws", "D004", ""),
        ("SY002", "Opgraving Kerkplein, Leiden", "B03", "03", "a", "Bot, leer, hout", "D005", ""),
        ("SY002", "Opgraving Kerkplein, Leiden", "B03", "03", "b", "Steen, metaal, munt", "D006", ""),
        ("SY002", "Opgraving Kerkplein, Leiden", "B04", "01", "a", "Kleipijpen, glas", "D007", ""),
        ("SY002", "Opgraving Kerkplein, Leiden", "B04", "01", "b", "Monsters", "D008", ""),
    ])
    return tabellen


# ============================================================
# Digifotos data
# ============================================================

def dataDigifotos():
    """Genereer digitale fotocatalogus data.

    Returns:
        Dict met tabelnaam -> (kolommen, records)
    """
    kol = [k[0] for k in KOLOMMEN_DIGIFOTOS]
    tabellen = {}
    tabellen["Fotos"] = (kol, [
        # SY001 foto's
        (1, "SY001", 1, 1, None, None, "Overzicht vlak 1 put 1", "SY001_P1_V1_001.jpg", "Opgravingsfoto"),
        (2, "SY001", 1, 1, 1, None, "Detail spoor 1", "SY001_P1_S1_002.jpg", "Opgravingsfoto"),
        (3, "SY001", 2, 1, 3, None, "Coupe spoor 3", "SY001_P2_S3_003.jpg", "Opgravingsfoto"),
        # SY002 foto's
        (4, "SY002", 1, 1, None, None, "Overzicht vlak 1 put 1", "SY002_P1_V1_001.jpg", "Opgravingsfoto"),
        (5, "SY002", 1, 2, 3, None, "Detail muur spoor 3", "SY002_P1_S3_002.jpg", "Opgravingsfoto"),
        (6, "SY002", 2, 1, 4, None, "Beerput spoor 4", "SY002_P2_S4_003.jpg", "Opgravingsfoto"),
        (7, "SY002", 2, 2, 5, None, "Kuil spoor 5", "SY002_P2_S5_004.jpg", "Opgravingsfoto"),
        (8, "SY002", 3, 1, None, None, "Overzicht vlak 1 put 3", "SY002_P3_V1_005.jpg", "Opgravingsfoto"),
        (9, "SY002", 3, 1, 6, None, "Greppel spoor 6", "SY002_P3_S6_006.jpg", "Opgravingsfoto"),
        (10, "SY002", 4, 1, 8, None, "Waterput spoor 8", "SY002_P4_S8_007.jpg", "Opgravingsfoto"),
        (11, "SY002", 4, 1, 8, None, "Coupe waterput spoor 8", "SY002_P4_S8_008.jpg", "Opgravingsfoto"),
        (12, "SY002", None, None, None, 4, "Grape roodbakkend", "SY002_AW_V4_001.jpg", "Voorwerpfoto"),
        (13, "SY002", None, None, None, 11, "Duit 1649", "SY002_MU_V11_001.jpg", "Voorwerpfoto"),
    ])
    return tabellen


# ============================================================
# Monsterdatabase data
# ============================================================

def _maakWaarderingRecord(monstercode, waarden_dict):
    """Bouw een Monster_waardering record met correcte kolomaantallen.

    Args:
        monstercode: De monstercode (string)
        waarden_dict: Dict met kolomnaam -> waarde voor niet-lege kolommen

    Returns:
        Tuple met 75 waarden (MONSTERCODE + 74 telkolommen)
    """
    record = [monstercode]
    for naam, _ in KOLOMMEN_MONSTER_WAARDERING[1:]:  # skip MONSTERCODE
        record.append(waarden_dict.get(naam, None))
    # Z anders is een string, default ""
    idx_anders = [k[0] for k in KOLOMMEN_MONSTER_WAARDERING].index("Z anders")
    if record[idx_anders] is None:
        record[idx_anders] = ""
    return tuple(record)


def _maakWaarderingRecords():
    """Genereer alle 5 Monster_waardering records.

    Returns:
        Lijst van 5 tuples met correcte kolomaantallen
    """
    return [
        # SY001_p1_v1: veel botanisch, weinig zoologisch
        _maakWaarderingRecord("SY001_p1_v1", {
            "B stengel onverkoold": 5, "B zaden-cultuur onverkoold": 25,
            "B zaden-kaf onverkoold": 5, "B zaden-wild onverkoold": 25,
            "C aardewerk": 5, "D houtskool": 5,
            "Z bot-groot O": 5, "Z bot-klein O": 5, "Z visgraat/bot O": 5,
            "S molzoet/land": 10,
        }),
        # SY001_p1_v2: gemengd
        _maakWaarderingRecord("SY001_p1_v2", {
            "B zaden-cultuur onverkoold": 5, "B zaden-wild onverkoold": 5,
            "C aardewerk": 25, "C glas": 5, "D hout": 5, "C metaal": 5,
        }),
        # SY001_p2_v3: veel zoologisch
        _maakWaarderingRecord("SY001_p2_v3", {
            "Z bot-groot O": 25, "Z bot-klein O": 25,
            "Z visgraat/bot O": 5, "Z viswervel O": 5,
            "Z anders": "muis kiezen", "S molzoet/land": 5,
        }),
        # SY002_p2_v4: rijk monster, alles aanwezig
        _maakWaarderingRecord("SY002_p2_v4", {
            "B stengel onverkoold": 5, "B zaden-cultuur onverkoold": 50,
            "B zaden-kaf onverkoold": 25, "B zaden-wild onverkoold": 50,
            "B zaden-cultuur mineraaliseerd": 5, "C aardewerk": 5,
            "D hout": 5, "D houtskool": 5,
            "Z bot-groot O": 25, "Z bot-klein O": 5,
            "Z eierschaal/vel O": 5, "Z visgraat/bot O": 25, "Z viswervel O": 5,
            "S molzoet/land": 25, "S mollusk zout": 5,
            "B wortel onverkoold": 5, "B stengel verkoold": 5,
            "B zaden-cultuur verkoold": 5, "B zaden-wild verkoold": 5,
            "Z vogelbot O": 5, "S kokkel": 5, "S oester": 5,
        }),
        # SY002_p3_v7: gemiddeld
        _maakWaarderingRecord("SY002_p3_v7", {
            "B zaden-cultuur onverkoold": 5, "B zaden-wild onverkoold": 25,
            "Z bot-groot O": 5, "Z bot-klein O": 5, "S molzoet/land": 5,
        }),
    ]


def dataMonsterDatabase():
    """Genereer monsterdatabase-data voor synthetische projecten SY001 en SY002.

    Bevat Monster_gegevens, Monster_waardering, Monster_botanie_determinatie,
    Monster_schelp_determinatie en referentietabellen (R_PLANT, R_SCHELP,
    R_DEEL, R_STAAT).

    Returns:
        Dict met tabelnaam -> (kolommen, records) per tabel
    """
    tabellen = {}

    # ---- Monster_gegevens: 5 monsters (3x SY001, 2x SY002) ----
    kol = [k[0] for k in KOLOMMEN_MONSTER_GEGEVENS]
    tabellen["Monster_gegevens"] = (kol, [
        # SY001 monsters — verwijzen naar putten en vondsten van SY001
        ("SY001", 1, 1, "SY001_p1_v1", "S. Syntheticus", "03/15/24 00:00:00",
         1, 101, "monster uit kuil", "grondmonster", 0.5, 0.5, 0.3,
         "03/20/24 00:00:00", None, "Wv:onkruid, cultuur",
         "+", "+/-", "+", "+/-", "+", "+/-", "+/-", "+"),
        ("SY001", 1, 2, "SY001_p1_v2", "S. Syntheticus", "03/16/24 00:00:00",
         2, 101, "monster uit muur", "zeef residu", 0.3, 0.5, 0.2,
         "03/21/24 00:00:00", "zeef residu", "A:",
         "+/-", "+", "+/-", "+", "+/-", "+", "+/-", "+"),
        ("SY001", 2, 3, "SY001_p2_v3", "S. Syntheticus", "03/18/24 00:00:00",
         3, 102, "monster uit greppel", "beenmonster", 0.8, 0.5, 0.6,
         "03/22/24 00:00:00", None, "B:",
         "-", "+/-", "-", "+", "-", "+/-", "-", "+/-"),
        # SY002 monsters — verwijzen naar putten en vondsten van SY002
        ("SY002", 2, 4, "SY002_p2_v4", "P. Plantkundige", "06/05/24 00:00:00",
         4, 201, "monster uit beerput", "grondmonster", 1.0, 0.5, 0.8,
         "06/10/24 00:00:00", "rijk monster", "Wv:cultuur, onkruid, bomen",
         "+", "+", "+", "+", "+", "+", "+", "+"),
        ("SY002", 3, 7, "SY002_p3_v7", "P. Plantkundige", "06/10/24 00:00:00",
         6, 202, "monster uit greppel", "grondmonster", 0.5, 0.5, 0.3,
         "06/15/24 00:00:00", None, "B:",
         "+/-", "+/-", "+/-", "+/-", "+/-", "+/-", "+/-", "+/-"),
    ])

    # ---- Monster_waardering: 5 records (1:1 met Monster_gegevens) ----
    # Vereenvoudigd: alleen de meest relevante telkolommen gevuld, rest = None
    kol = [k[0] for k in KOLOMMEN_MONSTER_WAARDERING]
    nul = None  # afkorting voor leesbaarheid
    tabellen["Monster_waardering"] = (kol, [
        # Gebruik een hulpfunctie om records op te bouwen met correcte kolomaantallen
        # De kolommen zijn (75 totaal):
        #   MONSTERCODE(1), B-onverk(4)+B-miner(1)=5, C-1e(10), D-1e(2),
        #   Z-O(11), Z-anders(1), S-1e(3),
        #   B-onverk2(2)+B-verk(5)+B-miner2(3)=10, B-recent(5), C-2e(9), D-2e(3),
        #   Z-V(9)+Z-vogel(2)+Z-rest(2)=13, S-2e(2)
        *_maakWaarderingRecords(),
    ])

    # ---- Monster_botanie_determinatie: 8 records ----
    kol = [k[0] for k in KOLOMMEN_MONSTER_BOTANIE]
    tabellen["Monster_botanie_determinatie"] = (kol, [
        # SY001_p1_v1: 3 botanische determinaties
        ("SY001_p1_v1", "CAREX-SP", "SEE", "o", None, 50),
        ("SY001_p1_v1", "BRASSICA", "SEE", "o", None, 25),
        ("SY001_p1_v1", "SAMBUC/N", "SEE", "v", None, 10),
        # SY001_p1_v2: 1 determinatie
        ("SY001_p1_v2", "CAREX-SP", "SEE", "o", None, 15),
        # SY002_p2_v4: 3 determinaties (rijk monster)
        ("SY002_p2_v4", "CEREALI", "SEE", "o", None, 100),
        ("SY002_p2_v4", "SAMBUC/N", "BAS", "o", None, 5),
        ("SY002_p2_v4", "QUERCUS", "HOT", "v", None, 3),
        # SY002_p3_v7: 1 determinatie
        ("SY002_p3_v7", "BRASSICA", "SEE", "m", None, 20),
    ])

    # ---- Monster_schelp_determinatie: 4 records ----
    kol = [k[0] for k in KOLOMMEN_MONSTER_SCHELP]
    tabellen["Monster_schelp_determinatie"] = (kol, [
        # SY001_p1_v1: 2 schelpdeterminaties
        ("SY001_p1_v1", "Planorbis corneus", 10),
        ("SY001_p1_v1", "Radix ovata", 5),
        # SY002_p2_v4: 2 schelpdeterminaties
        ("SY002_p2_v4", "Planorbis corneus", 25),
        ("SY002_p2_v4", "Ostracoda", 15),
    ])

    # ---- R_PLANT: 5 plantensoorten ----
    kol = [k[0] for k in KOLOMMEN_R_PLANT]
    tabellen["R_PLANT"] = (kol, [
        ("CAREX-SP", None, "Carex spec.", "Zegge"),
        ("BRASSICA", None, "Brassica spec.", "Kool"),
        ("SAMBUC/N", None, "Sambucus nigra", "Gewone vlier"),
        ("CEREALI", None, "Cerealia indet.", "Graan"),
        ("QUERCUS", None, "Quercus spec.", "Eik"),
    ])

    # ---- R_SCHELP: 3 schelpsoorten ----
    kol = [k[0] for k in KOLOMMEN_R_SCHELP]
    tabellen["R_SCHELP"] = (kol, [
        ("PLANORCO", "Planorbis corneus", "Grote posthoren",
         "stilstaand zoet water met rijke vegetatie."),
        ("RADIXOVA", "Radix ovata", "Ovale poelslak",
         "stilstaand tot langzaam stromend zoet water."),
        ("OSTRACOD", "Ostracoda", "Mosselkreeftje",
         "diverse aquatische milieus."),
    ])

    # ---- R_DEEL: 4 deel-typen ----
    kol = [k[0] for k in KOLOMMEN_R_DEEL]
    tabellen["R_DEEL"] = (kol, [
        ("SEE", "zaad", "zaad of vrucht"),
        ("BAS", "bast", "levend deel van de schors van houtige gewassen"),
        ("HOT", "hout", "houtfragment"),
        ("BDS", "knop", "van houtige gewassen"),
    ])

    # ---- R_STAAT: 4 staat-typen ----
    kol = [k[0] for k in KOLOMMEN_R_STAAT]
    tabellen["R_STAAT"] = (kol, [
        ("o", "onverkoold", 1),
        ("v", "verkoold", 2),
        ("m", "gemineraliseerd", 3),
        ("r", "recent of subrecent", 4),
    ])

    return tabellen


# ============================================================
# MDB-bestanden aanmaken
# ============================================================

def schrijfMdb(pad, tabellen_data, tabel_definities):
    """Schrijf een MDB-bestand met tabellen en data.

    Args:
        pad: Pad naar het MDB-bestand
        tabellen_data: Dict met tabelnaam -> (kolommen, records)
        tabel_definities: Dict met tabelnaam -> kolom_definities (lijst van (naam, type) tuples)
    """
    maakMdbBestand(pad)
    db = openMdb(pad)

    try:
        for tabelnaam, (kolommen, records) in tabellen_data.items():
            if tabelnaam not in tabel_definities:
                print(f"  WAARSCHUWING: geen definitie voor tabel {tabelnaam}")
                continue

            print(f"  Tabel [{tabelnaam}]: {len(records)} records")
            table = maakTabelJackcess(db, tabelnaam, tabel_definities[tabelnaam])
            voegRecordsIn(table, kolommen, records)
    finally:
        db.close()


# Minimale geldige JPEG (1x1 pixel, rood)
MINIMAL_JPEG = bytes([
    0xFF, 0xD8, 0xFF, 0xE0, 0x00, 0x10, 0x4A, 0x46, 0x49, 0x46, 0x00, 0x01,
    0x01, 0x00, 0x00, 0x01, 0x00, 0x01, 0x00, 0x00, 0xFF, 0xDB, 0x00, 0x43,
    0x00, 0x08, 0x06, 0x06, 0x07, 0x06, 0x05, 0x08, 0x07, 0x07, 0x07, 0x09,
    0x09, 0x08, 0x0A, 0x0C, 0x14, 0x0D, 0x0C, 0x0B, 0x0B, 0x0C, 0x19, 0x12,
    0x13, 0x0F, 0x14, 0x1D, 0x1A, 0x1F, 0x1E, 0x1D, 0x1A, 0x1C, 0x1C, 0x20,
    0x24, 0x2E, 0x27, 0x20, 0x22, 0x2C, 0x23, 0x1C, 0x1C, 0x28, 0x37, 0x29,
    0x2C, 0x30, 0x31, 0x34, 0x34, 0x34, 0x1F, 0x27, 0x39, 0x3D, 0x38, 0x32,
    0x3C, 0x2E, 0x33, 0x34, 0x32, 0xFF, 0xC0, 0x00, 0x0B, 0x08, 0x00, 0x01,
    0x00, 0x01, 0x01, 0x01, 0x11, 0x00, 0xFF, 0xC4, 0x00, 0x1F, 0x00, 0x00,
    0x01, 0x05, 0x01, 0x01, 0x01, 0x01, 0x01, 0x01, 0x00, 0x00, 0x00, 0x00,
    0x00, 0x00, 0x00, 0x00, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08,
    0x09, 0x0A, 0x0B, 0xFF, 0xC4, 0x00, 0xB5, 0x10, 0x00, 0x02, 0x01, 0x03,
    0x03, 0x02, 0x04, 0x03, 0x05, 0x05, 0x04, 0x04, 0x00, 0x00, 0x01, 0x7D,
    0x01, 0x02, 0x03, 0x00, 0x04, 0x11, 0x05, 0x12, 0x21, 0x31, 0x41, 0x06,
    0x13, 0x51, 0x61, 0x07, 0x22, 0x71, 0x14, 0x32, 0x81, 0x91, 0xA1, 0x08,
    0x23, 0x42, 0xB1, 0xC1, 0x15, 0x52, 0xD1, 0xF0, 0x24, 0x33, 0x62, 0x72,
    0x82, 0x09, 0x0A, 0x16, 0x17, 0x18, 0x19, 0x1A, 0x25, 0x26, 0x27, 0x28,
    0x29, 0x2A, 0x34, 0x35, 0x36, 0x37, 0x38, 0x39, 0x3A, 0x43, 0x44, 0x45,
    0x46, 0x47, 0x48, 0x49, 0x4A, 0x53, 0x54, 0x55, 0x56, 0x57, 0x58, 0x59,
    0x5A, 0x63, 0x64, 0x65, 0x66, 0x67, 0x68, 0x69, 0x6A, 0x73, 0x74, 0x75,
    0x76, 0x77, 0x78, 0x79, 0x7A, 0x83, 0x84, 0x85, 0x86, 0x87, 0x88, 0x89,
    0x8A, 0x92, 0x93, 0x94, 0x95, 0x96, 0x97, 0x98, 0x99, 0x9A, 0xA2, 0xA3,
    0xA4, 0xA5, 0xA6, 0xA7, 0xA8, 0xA9, 0xAA, 0xB2, 0xB3, 0xB4, 0xB5, 0xB6,
    0xB7, 0xB8, 0xB9, 0xBA, 0xC2, 0xC3, 0xC4, 0xC5, 0xC6, 0xC7, 0xC8, 0xC9,
    0xCA, 0xD2, 0xD3, 0xD4, 0xD5, 0xD6, 0xD7, 0xD8, 0xD9, 0xDA, 0xE1, 0xE2,
    0xE3, 0xE4, 0xE5, 0xE6, 0xE7, 0xE8, 0xE9, 0xEA, 0xF1, 0xF2, 0xF3, 0xF4,
    0xF5, 0xF6, 0xF7, 0xF8, 0xF9, 0xFA, 0xFF, 0xDA, 0x00, 0x08, 0x01, 0x01,
    0x00, 0x00, 0x3F, 0x00, 0x7B, 0x94, 0x11, 0x00, 0x00, 0x00, 0x00, 0x00,
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0xFF, 0xD9,
])


def genereerFotos():
    """Genereer synthetische fotobestanden (minimale JPEG's) voor SY001 en SY002.

    Plaatst 1x1 pixel JPEG's in de directorystructuur die importMDB.sh
    en getImageNamesFromDir verwachten: <project>/L Fotos/<bestandsnaam>.jpg
    """
    fotos = {
        "SY001": [
            "SY001_G001.jpg",  # Opgravingsfoto (G-type)
            "SY001_F001.jpg",  # Sfeerfoto (F-type)
            "SY001_G002.jpg",  # Opgravingsfoto 2
        ],
        "SY002": [
            "SY002_G001.jpg",
            "SY002_G002.jpg",
            "SY002_G003.jpg",
            "SY002_G004.jpg",
            "SY002_G005.jpg",
            "SY002_F001.jpg",
            "SY002_F002.jpg",
            "SY002_H4_1.jpg",   # Objectfoto vondst 4 (H-type)
            "SY002_H11_1.jpg",  # Objectfoto vondst 11 (munt)
            "SY002_B001.tif",   # Tekening (B-type, als .tif)
        ],
    }

    count = 0
    for project, bestanden in fotos.items():
        fotos_dir = os.path.join(OUTPUT_DIR, "projecten", project, "L Fotos")
        os.makedirs(fotos_dir, exist_ok=True)
        for bestand in bestanden:
            pad = os.path.join(fotos_dir, bestand)
            with open(pad, "wb") as f:
                f.write(MINIMAL_JPEG)
            count += 1

    print(f"  {count} synthetische fotobestanden aangemaakt")


def genereerAlles():
    """Genereer alle synthetische MDB-bestanden en fotobestanden."""
    print("=" * 60)
    print("Synthetische data generatie")
    print("=" * 60)

    startJvm()

    # Tabel definities verzamelen
    project_tabel_defs = {
        "VONDSTENLIJST": KOLOMMEN_VONDSTENLIJST,
        "SPOREN": KOLOMMEN_SPOREN,
        "VULLINGEN": KOLOMMEN_VULLINGEN,
        "AARDEWERK 1": KOLOMMEN_AARDEWERK,
        "GLAS": KOLOMMEN_GLAS,
        "BEEN": KOLOMMEN_BEEN,
        "METAAL": KOLOMMEN_METAAL,
        "LEER": KOLOMMEN_LEER,
        "HOUT": KOLOMMEN_HOUT,
        "STEEN": KOLOMMEN_STEEN,
        "KLEIPIJPEN": KOLOMMEN_KLEIPIJPEN,
        "MUNTEN EN PENNINGEN": KOLOMMEN_MUNTEN,
        "TEKENINGEN": KOLOMMEN_TEKENINGEN,
        "DIAVOORWERP": KOLOMMEN_DIAVOORWERP,
        "DIAOPGRAVING": KOLOMMEN_DIAOPGRAVING,
    }

    # Monsterdatabase tabel definities
    monster_tabel_defs = {
        "Monster_gegevens": KOLOMMEN_MONSTER_GEGEVENS,
        "Monster_waardering": KOLOMMEN_MONSTER_WAARDERING,
        "Monster_botanie_determinatie": KOLOMMEN_MONSTER_BOTANIE,
        "Monster_schelp_determinatie": KOLOMMEN_MONSTER_SCHELP,
        "R_PLANT": KOLOMMEN_R_PLANT,
        "R_SCHELP": KOLOMMEN_R_SCHELP,
        "R_DEEL": KOLOMMEN_R_DEEL,
        "R_STAAT": KOLOMMEN_R_STAAT,
    }

    # SY001 - Klein project
    print("\n[1/7] SY001 — Klein project (Marktstraat 10, Voorburg)")
    pad_sy001 = os.path.join(OUTPUT_DIR, "projecten", "SY001", "C Database", "opgravingSY001.mdb")
    schrijfMdb(pad_sy001, dataKleinProject(), project_tabel_defs)

    # SY002 - Groot project
    print("\n[2/7] SY002 — Groot project (Kerkplein, Leiden)")
    pad_sy002 = os.path.join(OUTPUT_DIR, "projecten", "SY002", "C Database", "opgravingSY002.mdb")
    schrijfMdb(pad_sy002, dataGrootProject(), project_tabel_defs)

    # Projectenlijst
    print("\n[3/7] Projectenlijst")
    pad_delfit = os.path.join(OUTPUT_DIR, "projectenlijst", "projectenlijst.mdb")
    schrijfMdb(pad_delfit, dataProjectenlijst(), {"OPGRAVINGEN": KOLOMMEN_OPGRAVINGEN})

    # Magazijnlijst
    print("\n[4/7] Magazijnlijst — Depot")
    pad_magazijn = os.path.join(OUTPUT_DIR, "magazijnlijst", "MAGAZIJN.mdb")
    schrijfMdb(pad_magazijn, dataMagazijnlijst(), {"magazijnlijst": KOLOMMEN_MAGAZIJNLIJST})

    # Fotolijst
    print("\n[5/7] Fotolijst — Fotocatalogus")
    pad_fotos = os.path.join(OUTPUT_DIR, "fotolijst", "Digifotos.mdb")
    schrijfMdb(pad_fotos, dataDigifotos(), {"Fotos": KOLOMMEN_DIGIFOTOS})

    # Monsterdatabase
    print("\n[6/7] Monsterdatabase — Monsters, botanie, schelpen")
    pad_monster = os.path.join(OUTPUT_DIR, "monsterdatabase", "MONSTERS.mdb")
    schrijfMdb(pad_monster, dataMonsterDatabase(), monster_tabel_defs)

    # Foto's
    print("\n[7/7] Synthetische fotobestanden")
    genereerFotos()

    print("\n" + "=" * 60)
    print("Klaar! Bestanden gegenereerd in:")
    print(f"  {OUTPUT_DIR}")
    print("=" * 60)


# ============================================================
# Hulpfuncties voor tests (zonder Java-dependency)
# ============================================================

def getAlleScenarioData():
    """Geeft alle scenariodata als dict terug, bruikbaar voor unit tests.

    Returns:
        Dict met scenario-naam -> tabellen_data
    """
    return {
        "SY001": dataKleinProject(),
        "SY002": dataGrootProject(),
        "projectenlijst": dataProjectenlijst(),
        "magazijnlijst": dataMagazijnlijst(),
        "digifotos": dataDigifotos(),
        "monsterdatabase": dataMonsterDatabase(),
    }


if __name__ == "__main__":
    # Controleer of JARs aanwezig zijn
    for jar in JAR_FILES:
        if not os.path.exists(jar):
            print(f"FOUT: JAR-bestand niet gevonden: {jar}")
            print("Download eerst de Jackcess JARs. Zie README.md.")
            sys.exit(1)

    genereerAlles()
