#!/usr/bin/env python3
"""
Voeg de kolommen table, projectcd, bron, loadtime en mdbfile toe aan een CSV-export
van een Access-tabel (aangeroepen door importMDB.sh, na de encoding-conversie).

De kolomnamen komen achter de kopregel, de waarden achter elk datarecord. Een
record is een CSV-record, geen regel: een tekstveld met een regeleinde (een
memo-veld in Access) staat tussen aanhalingstekens en beslaat in de export meer
regels. De csv-module bepaalt waar een record eindigt, zodat de waarden achter
het hele record komen en niet midden in het tekstveld (issue 74; voorheen
voegde sed ze per regel toe).

De tekst van elk record blijft ongewijzigd: alleen de vijf waarden worden vóór
het regeleinde van het record gezet. De quoting van mdb-export (tekstvelden
tussen aanhalingstekens, getallen zonder) blijft daardoor behouden en de uitvoer
is voor records zonder regeleinde in een veld byte voor byte gelijk aan die van
de vroegere sed-opdrachten. De vijf waarden worden net als door csv.writer met
QUOTE_MINIMAL alleen tussen aanhalingstekens gezet als ze een komma, een
aanhalingsteken of een regeleinde bevatten.

Het bestand wordt regel voor regel gelezen en via een tijdelijk bestand in
dezelfde map vervangen, zodat ook tabellen met tienduizenden rijen niet in het
geheugen hoeven. Bytes die geen geldig UTF-8 zijn blijven ongewijzigd
(surrogateescape).

Gebruik:
    python3 csv_kolommen.py <csv-bestand> <table> <projectcd> <bron> <loadtime> <mdbfile>

Schrijft het aantal datarecords (zonder kopregel) naar stdout. Exitcode 0 bij
succes; bij een fout een melding op stderr, exitcode 1 en een ongewijzigd
CSV-bestand.
"""
import csv
import io
import os
import stat
import sys
import tempfile

KOLOMNAMEN = ["table", "projectcd", "bron", "loadtime", "mdbfile"]
CODERING = "utf-8"
FOUTEN = "surrogateescape"

# Memo-velden kunnen groter zijn dan de standaardgrens van de csv-module (128 KB)
csv.field_size_limit(2**31 - 1)


def maakAchtervoegsel(waarden):
    """Maak de tekst die achter een record komt: een komma plus de waarden als CSV-velden.

    Args:
        waarden: lijst met teksten

    Returns:
        Tekst zoals ",waarde1,waarde2", zonder regeleinde
    """
    uit = io.StringIO()
    csv.writer(uit, quoting=csv.QUOTE_MINIMAL, lineterminator="\n").writerow(waarden)
    return "," + uit.getvalue()[:-1]


def splitsRegeleinde(record):
    """Splits de tekst van een record in de inhoud en het afsluitende regeleinde.

    Args:
        record: tekst van een record, inclusief regeleinde ("\\r\\n", "\\n", "\\r" of geen
            bij de laatste regel van een bestand zonder afsluitend regeleinde)

    Returns:
        Tuple (inhoud, regeleinde)
    """
    if record.endswith("\r\n"):
        return record[:-2], "\r\n"
    if record.endswith(("\n", "\r")):
        return record[:-1], record[-1]
    return record, ""


def leesRecords(regels):
    """Geef per CSV-record de oorspronkelijke tekst, inclusief regeleinde(n).

    De csv-module leest de regels en bepaalt waar een record eindigt; een gequote
    veld met een regeleinde loopt door over meer regels. De regels die de lezer
    voor een record gebruikt worden samengevoegd tot de tekst van dat record.

    Args:
        regels: iterator over tekstregels inclusief regeleinde (een bestand geopend
            met newline="")

    Returns:
        Generator met de tekst per record

    Raises:
        csv.Error: als de CSV niet te lezen is
    """
    gelezen = []

    def bron():
        for regel in regels:
            gelezen.append(regel)
            yield regel

    for _ in csv.reader(bron()):
        record = "".join(gelezen)
        gelezen.clear()
        yield record
    if gelezen:
        # Restant zonder volledig record (komt bij geldige CSV niet voor); niet weggooien
        yield "".join(gelezen)


def voegKolommenToe(invoer, uitvoer, waarden):
    """Voeg de vijf kolommen toe aan een CSV-stroom.

    Args:
        invoer: tekststroom met de CSV (kopregel plus records), geopend met newline=""
        uitvoer: tekststroom voor het resultaat, geopend met newline=""
        waarden: de waarden voor table, projectcd, bron, loadtime en mdbfile

    Returns:
        Aantal datarecords (zonder kopregel)
    """
    if len(waarden) != len(KOLOMNAMEN):
        raise ValueError(f"Verwacht {len(KOLOMNAMEN)} waarden, gekregen: {len(waarden)}")
    kop_achtervoegsel = "," + ",".join(KOLOMNAMEN)
    achtervoegsel = maakAchtervoegsel(waarden)

    aantal = -1
    for record in leesRecords(invoer):
        inhoud, regeleinde = splitsRegeleinde(record)
        uitvoer.write(inhoud + (kop_achtervoegsel if aantal < 0 else achtervoegsel) + regeleinde)
        aantal += 1
    return max(aantal, 0)


def verwerkBestand(pad, waarden):
    """Voeg de vijf kolommen toe aan een CSV-bestand (vervangt het bestand).

    Een leeg bestand (geen kopregel) blijft leeg.

    Args:
        pad: pad naar het CSV-bestand
        waarden: de waarden voor table, projectcd, bron, loadtime en mdbfile

    Returns:
        Aantal datarecords (zonder kopregel)
    """
    if os.path.getsize(pad) == 0:
        return 0
    with open(pad, "r", encoding=CODERING, errors=FOUTEN, newline="") as invoer:
        fd, tijdelijk = tempfile.mkstemp(prefix=".kolommen_", suffix=".csv",
                                         dir=os.path.dirname(os.path.abspath(pad)))
        try:
            with os.fdopen(fd, "w", encoding=CODERING, errors=FOUTEN, newline="") as uitvoer:
                aantal = voegKolommenToe(invoer, uitvoer, waarden)
            # mkstemp maakt het bestand alleen leesbaar voor de eigenaar; neem de rechten over
            os.chmod(tijdelijk, stat.S_IMODE(os.stat(pad).st_mode))
        except BaseException:
            os.remove(tijdelijk)
            raise
    os.replace(tijdelijk, pad)
    return aantal


def main(argv):
    """Opdrachtregel: csv_kolommen.py <csv-bestand> <table> <projectcd> <bron> <loadtime> <mdbfile>."""
    if len(argv) != 1 + len(KOLOMNAMEN):
        sys.stderr.write("Gebruik: csv_kolommen.py <csv-bestand> <table> <projectcd> <bron> <loadtime> <mdbfile>\n")
        return 1
    pad, waarden = argv[0], argv[1:]
    try:
        aantal = verwerkBestand(pad, waarden)
    except (OSError, ValueError, csv.Error) as fout:
        sys.stderr.write(f"ERROR: kolommen toevoegen aan '{pad}' mislukt: {fout}\n")
        return 1
    print(aantal)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
