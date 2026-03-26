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
JARS_DIR = os.path.join(SCRIPT_DIR, "jars")
OUTPUT_DIR = os.path.join(SCRIPT_DIR, "output")

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
        (code, 1, 1, 1, 1, "", "", "", "", "Aanleg vlak", "Aardewerk", "1600-1700", "15-03-2024", 80120.5, 451230.8),
        (code, 1, 1, 2, 2, "", "", "", "", "Coupe spoor 2", "Glas, aardewerk", "17e eeuw", "16-03-2024", 80121.0, 451231.2),
        (code, 2, 1, 3, 3, "", "", "", "", "Aanleg vlak", "Bot", "1650-1750", "18-03-2024", 80125.3, 451228.5),
        (code, 2, 1, 4, 3, "", "", "", "", "Uitschaven spoor 3", "Aardewerk, metaal", "1600-1700", "18-03-2024", 80125.8, 451228.9),
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
        (code, 1, 1, 1, 1, "", "", "", "", "Aanleg vlak 1", "Aardewerk", "1200-1400", "01-06-2024", 92050.2, 464120.5),
        (code, 1, 1, 2, 1, "", "", "", "", "Coupe spoor 1", "Aardewerk, bot", "1300-1400", "02-06-2024", 92050.5, 464120.8),
        (code, 1, 2, 3, 3, "", "", "", "", "Aanleg vlak 2", "Metaal", "1400-1600", "03-06-2024", 92051.0, 464121.0),
        (code, 2, 1, 4, 4, "", "", "", "", "Aanleg vlak 1", "Aardewerk, glas", "1500-1700", "05-06-2024", 92055.3, 464118.5),
        (code, 2, 1, 5, 4, "", "", "", "", "Coupe spoor 4", "Aardewerk", "1600-1700", "06-06-2024", 92055.8, 464118.9),
        (code, 2, 2, 6, 5, "", "", "", "", "Aanleg vlak 2", "Kleipijp, glas", "1650-1750", "07-06-2024", 92056.0, 464119.2),
        (code, 3, 1, 7, 6, "", "", "", "", "Aanleg vlak 1", "Bot, aardewerk", "1300-1500", "10-06-2024", 92060.1, 464115.3),
        (code, 3, 1, 8, 6, "", "", "", "", "Uitschaven spoor 6", "Leer, hout", "1400-1500", "10-06-2024", 92060.5, 464115.7),
        (code, 3, 2, 9, 7, "", "", "", "", "Aanleg vlak 2", "Aardewerk", "1200-1350", "11-06-2024", 92060.8, 464116.0),
        (code, 4, 1, 10, 8, "", "", "", "", "Aanleg vlak 1", "Steen, metaal", "1500-1700", "14-06-2024", 92065.2, 464112.8),
        (code, 4, 1, 11, 8, "", "", "", "", "Coupe spoor 8", "Munt, aardewerk", "1600-1700", "15-06-2024", 92065.5, 464113.1),
        (code, 4, 3, 12, 8, "", "", "", "", "Aanleg vlak 3", "Aardewerk", "1500-1650", "16-06-2024", 92065.8, 464113.4),
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
        ("SY001", "Marktstraat 10", "Opgraving Marktstraat 10, Voorburg", "SY001",
         "37EN2", 80120.5, 451230.8, "VBG A 1234", 2024, "Voorburg",
         "Ja", "Ja", "Ja", "Ja", "Ja", "Ja", "Ja", "", "", "", "", "", "", "",
         "Nieuwe Tijd, nederzetting, afvalkuil, muur",
         "Ja", "1600", "1750", "Synthegraven B.V."),
        ("SY002", "Kerkplein", "Opgraving Kerkplein, Leiden", "SY002",
         "30GN1", 92050.2, 464120.5, "LDN B 5678", 2024, "Leiden",
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


def genereerAlles():
    """Genereer alle synthetische MDB-bestanden."""
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

    # SY001 - Klein project
    print("\n[1/5] SY001 — Klein project (Marktstraat 10, Voorburg)")
    pad_sy001 = os.path.join(OUTPUT_DIR, "projecten", "SY001", "C Database", "opgravingSY001.mdb")
    schrijfMdb(pad_sy001, dataKleinProject(), project_tabel_defs)

    # SY002 - Groot project
    print("\n[2/5] SY002 — Groot project (Kerkplein, Leiden)")
    pad_sy002 = os.path.join(OUTPUT_DIR, "projecten", "SY002", "C Database", "opgravingSY002.mdb")
    schrijfMdb(pad_sy002, dataGrootProject(), project_tabel_defs)

    # DELF-IT projectenlijst
    print("\n[3/5] DELF-IT — Projectenlijst")
    pad_delfit = os.path.join(OUTPUT_DIR, "delfit", "DELF-IT.mdb")
    schrijfMdb(pad_delfit, dataProjectenlijst(), {"OPGRAVINGEN": KOLOMMEN_OPGRAVINGEN})

    # Magazijnlijst
    print("\n[4/5] Magazijnlijst — Depot")
    pad_magazijn = os.path.join(OUTPUT_DIR, "magazijnlijst", "MAGAZIJN.mdb")
    schrijfMdb(pad_magazijn, dataMagazijnlijst(), {"magazijnlijst": KOLOMMEN_MAGAZIJNLIJST})

    # Digifotos
    print("\n[5/5] Digifotos — Fotocatalogus")
    pad_fotos = os.path.join(OUTPUT_DIR, "digifotos", "Digifotos.mdb")
    schrijfMdb(pad_fotos, dataDigifotos(), {"Fotos": KOLOMMEN_DIGIFOTOS})

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
    }


if __name__ == "__main__":
    # Controleer of JARs aanwezig zijn
    for jar in JAR_FILES:
        if not os.path.exists(jar):
            print(f"FOUT: JAR-bestand niet gevonden: {jar}")
            print("Download eerst de Jackcess JARs. Zie README.md.")
            sys.exit(1)

    genereerAlles()
