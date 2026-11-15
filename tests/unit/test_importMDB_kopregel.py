"""
Unit tests voor export_table_to_csv in importMDB.sh: de kopregel van de CSV-export.

mdb-export (1.0.0) zet kolomnamen in de kopregel niet tussen aanhalingstekens.
Een kolomnaam met een komma (bijv. "FORMAAT IN MM, HORIZONTAAL" in tabel
MUNTEN EN PENNINGEN) telde daardoor als twee velden, zodat mongoimport
(--headerline) alle waarden verschoof en de velden die importMDB.sh achteraan
toevoegt (table, projectcd, bron, loadtime, mdbfile) onder verkeerde namen
terechtkwamen. export_table_to_csv schrijft de kopregel zelf, correct gequote.

Het toevoegen van die vijf kolommen (vroeger met sed en escape_sed_csv_value,
sinds issue 74 met csv_kolommen.py) wordt getest in test_csv_kolommen.py; één
test hier controleert de combinatie met een gequote laatste kolomnaam.

Net als test_importMDB_bash.py draaien deze tests bash via subprocess. De
functie wordt uit importMDB.sh gehaald; mdb-export wordt nagebootst met een
klein script dat het gedrag van mdb-export 1.0.0 volgt (kopregel ongequote,
opties -d, -Q en -H). Eén test gebruikt de echte mdb-export en de synthetische
data, als die beschikbaar zijn.
"""
import csv
import io
import json
import os
import shutil
import subprocess
import pytest

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(SCRIPT_DIR))
IMPORT_SCRIPT = os.path.join(PROJECT_ROOT, "airflow_app", "scripts", "importMDB.sh")
KOLOMMEN_SCRIPT = os.path.join(PROJECT_ROOT, "airflow_app", "scripts", "csv_kolommen.py")
SY002_MDB = os.path.join(PROJECT_ROOT, "data", "synthetic", "data", "projecten", "SY002",
                         "C Database", "opgravingSY002.mdb")

KOLOMMEN = ["ID", "CODENAAM", "PUTNO", "GEWICHT IN G", "FORMAAT IN MM, HORIZONTAAL",
            "FORMAAT IN MM, VERTIKAAL", "VORM"]
RIJEN = [
    [1, "SY002", 4, 2.5, 22, 22, "Rond"],
    [2, "SY002", 4, 3.1, 18, 19, "Ovaal, gebroken"],
]

# Tabellen van de nagebootste database (kolommen zoals mdb-export ze kent)
TABELLEN = {
    "MUNTEN EN PENNINGEN": {"kolommen": KOLOMMEN, "rijen": RIJEN},
    "LEEG": {"kolommen": ["ID", "A, B"], "rijen": []},
    "KOMMA_LAATST": {"kolommen": ["ID", "A, B"], "rijen": [[7, 12]]},
    "QUOTE": {"kolommen": ["ID", 'NAAM "KORT"'], "rijen": [[1, "x"]]},
    "CP1252": {"kolommen": ["ID", "DIAMETER \u00f8, MM"], "rijen": [[1, 5]], "codering": "cp1252"},
}

# Nabootsing van mdb-export 1.0.0: kopregel ongequote, tekstvelden tussen
# aanhalingstekens (tenzij -Q), -d scheidingsteken, -H zonder kopregel.
NEP_MDB_EXPORT = r'''#!/usr/bin/env python3
import json, sys

args = sys.argv[1:]
scheiding, quote, kop = ",", True, True
posities = []
i = 0
while i < len(args):
    if args[i] == "-d":
        scheiding = args[i + 1]
        i += 2
        continue
    if args[i] == "-Q":
        quote = False
    elif args[i] == "-H":
        kop = False
    else:
        posities.append(args[i])
    i += 1
with open(posities[0], encoding="utf-8") as f:
    tabellen = json.load(f)
if posities[1] not in tabellen:
    sys.stderr.write("Error: Table %s does not exist in this database.\n" % posities[1])
    sys.exit(1)
tabel = tabellen[posities[1]]

def veld(waarde):
    if isinstance(waarde, str) and quote:
        return '"' + waarde.replace('"', '""') + '"'
    return str(waarde)

uit = sys.stdout.buffer
if kop:
    regel = scheiding.join(tabel["kolommen"])
    uit.write(regel.encode(tabel.get("codering", "utf-8"), "surrogateescape") + b"\n")
for rij in tabel["rijen"]:
    uit.write(scheiding.join(veld(w) for w in rij).encode("utf-8") + b"\n")
'''


def extraheerFunctie(naam):
    """Haal een bash-functie (tekst) uit importMDB.sh, zoals test_importMDB_functions.sh."""
    with open(IMPORT_SCRIPT, encoding="utf-8") as f:
        inhoud = f.read()
    start = inhoud.index(naam + "()")
    diepte = 0
    for i, teken in enumerate(inhoud[start:]):
        if teken == "{":
            diepte += 1
        elif teken == "}":
            diepte -= 1
            if diepte == 0:
                return inhoud[start:start + i + 1]
    raise ValueError(f"Functie {naam} niet volledig gevonden in importMDB.sh")


@pytest.fixture
def nepMdb(tmp_path):
    """Map met een nagebootste mdb-export en een 'database' (json) met tabellen."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    mdb_export = bin_dir / "mdb-export"
    mdb_export.write_text(NEP_MDB_EXPORT, encoding="utf-8")
    mdb_export.chmod(0o755)
    database = tmp_path / "opgraving.mdb"
    database.write_text(json.dumps(TABELLEN), encoding="utf-8")
    return bin_dir, database


def draaiExport(bin_dir, database, tabel, csv_bestand):
    """Draai export_table_to_csv met de nagebootste mdb-export; retourneer de exitcode."""
    script = (
        f'{extraheerFunctie("export_table_to_csv")}\n'
        'IFS=","\n'
        'export_table_to_csv "$1" "$2" "$3"\n'
    )
    env = dict(os.environ, PATH=f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}")
    result = subprocess.run(["bash", "-c", script, "bash", str(database), tabel, str(csv_bestand)],
                            capture_output=True, text=True, timeout=60, env=env)
    return result.returncode


def leesCsv(pad):
    with open(pad, encoding="utf-8", newline="") as f:
        return list(csv.reader(f))


@pytest.mark.unit
class TestExportTableToCsv:
    """export_table_to_csv schrijft een correct gequote kopregel boven de data van mdb-export -H."""

    def test_functie_bestaat_en_wordt_gebruikt(self):
        with open(IMPORT_SCRIPT, encoding="utf-8") as f:
            inhoud = f.read()
        assert "export_table_to_csv()" in inhoud
        assert 'export_table_to_csv "$mdbfile" "$TABLE" "$CSV"' in inhoud
        # De oude export (ongequote kopregel) staat er niet meer
        assert 'mdb-export "$mdbfile" "$TABLE" > "$CSV"' not in inhoud

    def test_kolomnaam_met_komma_blijft_een_veld(self, tmp_path, nepMdb):
        bin_dir, database = nepMdb
        uit = tmp_path / "munten.csv"
        assert draaiExport(bin_dir, database, "MUNTEN EN PENNINGEN", uit) == 0
        kop = leesCsv(uit)[0]
        assert kop == KOLOMMEN
        assert "FORMAAT IN MM, HORIZONTAAL" in kop
        assert " HORIZONTAAL" not in kop
        with open(uit, encoding="utf-8") as f:
            assert '"FORMAAT IN MM, HORIZONTAAL","FORMAAT IN MM, VERTIKAAL"' in f.readline()

    def test_veldtelling_kop_gelijk_aan_rijen(self, tmp_path, nepMdb):
        bin_dir, database = nepMdb
        uit = tmp_path / "munten.csv"
        assert draaiExport(bin_dir, database, "MUNTEN EN PENNINGEN", uit) == 0
        regels = leesCsv(uit)
        assert len(regels) == 1 + len(RIJEN)
        assert {len(r) for r in regels} == {len(KOLOMMEN)}
        assert regels[2][-1] == "Ovaal, gebroken"

    def test_ter_vergelijking_ongequote_kopregel_telt_meer_velden(self, tmp_path, nepMdb):
        """De oude aanroep (mdb-export zonder opties) geeft een kopregel met te veel velden."""
        bin_dir, database = nepMdb
        env = dict(os.environ, PATH=f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}")
        uitvoer = subprocess.run(["mdb-export", str(database), "MUNTEN EN PENNINGEN"],
                                 capture_output=True, text=True, timeout=60, env=env).stdout
        regels = list(csv.reader(io.StringIO(uitvoer)))
        assert len(regels[0]) == len(KOLOMMEN) + 2
        assert len(regels[1]) == len(KOLOMMEN)

    def test_aanhalingsteken_in_kolomnaam(self, tmp_path, nepMdb):
        bin_dir, database = nepMdb
        uit = tmp_path / "quote.csv"
        assert draaiExport(bin_dir, database, "QUOTE", uit) == 0
        regels = leesCsv(uit)
        assert regels[0] == ["ID", 'NAAM "KORT"']
        assert len(regels[0]) == len(regels[1])

    def test_lege_tabel_alleen_kopregel(self, tmp_path, nepMdb):
        """Een lege tabel geeft één regel; importMDB.sh slaat hem over (LENGTE 0)."""
        bin_dir, database = nepMdb
        uit = tmp_path / "leeg.csv"
        assert draaiExport(bin_dir, database, "LEEG", uit) == 0
        with open(uit, encoding="utf-8") as f:
            assert f.read() == 'ID,"A, B"\n'

    def test_geen_kopregel_geeft_fout_en_leeg_bestand(self, tmp_path, nepMdb):
        bin_dir, database = nepMdb
        uit = tmp_path / "ontbreekt.csv"
        assert draaiExport(bin_dir, database, "BESTAAT_NIET", uit) == 1
        assert uit.exists() and uit.stat().st_size == 0

    def test_niet_utf8_kopregel_blijft_bytegelijk(self, tmp_path, nepMdb):
        """Een kopregel in CP1252 blijft ongewijzigd; convert_to_utf8 converteert later het hele bestand."""
        bin_dir, database = nepMdb
        uit = tmp_path / "cp1252.csv"
        assert draaiExport(bin_dir, database, "CP1252", uit) == 0
        with open(uit, "rb") as f:
            assert f.readline() == 'ID,"DIAMETER ø, MM"\n'.encode("cp1252")

    def test_kolommen_toevoegen_na_gequote_laatste_kolom(self, tmp_path, nepMdb):
        """csv_kolommen.py werkt ook als de laatste kolomnaam van de kopregel gequote is."""
        bin_dir, database = nepMdb
        uit = tmp_path / "opgravingSY002.KOMMA_LAATST.csv"
        assert draaiExport(bin_dir, database, "KOMMA_LAATST", uit) == 0

        mdbfile = "/input/projecten/SY002/C Database/opgravingSY002.mdb"
        script = (
            'LENGTE=$(python3 "$6" "$5" "$1" "$2" "opgraving$2" "$3" "$4") || exit 1\n'
            'echo "$LENGTE"\n'
            f'{extraheerFunctie("fix_duplicate_csv_headers")}\n'
            'fix_duplicate_csv_headers "$5"\n'
        )
        result = subprocess.run(
            ["bash", "-c", script, "bash", "KOMMA_LAATST", "SY002", "2026-10-21T10:00:00+02:00", mdbfile, str(uit),
             KOLOMMEN_SCRIPT],
            capture_output=True, text=True, timeout=60)
        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == "1"
        kop, rij = leesCsv(uit)
        assert kop == ["ID", "A, B", "table", "projectcd", "bron", "loadtime", "mdbfile"]
        assert rij == ["7", "12", "KOMMA_LAATST", "SY002", "opgravingSY002", "2026-10-21T10:00:00+02:00", mdbfile]

    @pytest.mark.skipif(shutil.which("mdb-export") is None or not os.path.isfile(SY002_MDB),
                        reason="mdb-export of synthetische data (SY002) niet beschikbaar")
    def test_echte_mdb_export_synthetisch_sy002(self, tmp_path):
        """Met de echte mdb-export: MUNTEN EN PENNINGEN van SY002 heeft evenveel kop- als rijvelden."""
        uit = tmp_path / "munten.csv"
        script = (
            f'{extraheerFunctie("export_table_to_csv")}\n'
            'export_table_to_csv "$1" "$2" "$3"\n'
        )
        result = subprocess.run(["bash", "-c", script, "bash", SY002_MDB, "MUNTEN EN PENNINGEN", str(uit)],
                                capture_output=True, text=True, timeout=60)
        assert result.returncode == 0, result.stderr
        regels = leesCsv(uit)
        assert len(regels) == 2
        assert "FORMAAT IN MM, HORIZONTAAL" in regels[0]
        assert "FORMAAT IN MM, VERTIKAAL" in regels[0]
        assert len(regels[0]) == len(regels[1]) == 23
