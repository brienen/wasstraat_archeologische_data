"""
Unit tests voor export_table_to_csv in importMDB.sh: de kopregel van de CSV-export,
en voor de sed-regels die de kolommen table, projectcd, bron, loadtime en mdbfile
toevoegen (met escape_sed_csv_value).

mdb-export (1.0.0) zet kolomnamen in de kopregel niet tussen aanhalingstekens.
Een kolomnaam met een komma (bijv. "FORMAAT IN MM, HORIZONTAAL" in tabel
MUNTEN EN PENNINGEN) telde daardoor als twee velden, zodat mongoimport
(--headerline) alle waarden verschoof en de velden die importMDB.sh achteraan
toevoegt (table, projectcd, bron, loadtime, mdbfile) onder verkeerde namen
terechtkwamen. export_table_to_csv schrijft de kopregel zelf, correct gequote.

De toegevoegde waarden stonden letterlijk in de vervangingstekst van sed. Een &
betekent daar "de gevonden tekst" en een backslash is een escape-teken: de
Delftse tabel "AARDEWERK 1&2 VOORWERP" werd "AARDEWERK 12 VOORWERP", de kopregel
werd niet vervangen en de 96 documenten kregen geen table, projectcd, loadtime
of mdbfile.
escape_sed_csv_value maakt de waarden veilig voor sed en zet een waarde met een
komma of aanhalingsteken tussen dubbele aanhalingstekens (andere waarden blijven
ongequote, zodat de uitvoer voor gewone tabellen byte voor byte gelijk blijft;
ook binnen een tekstveld met een regeleinde, waar sed de waarden eveneens
achter zet).

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
import re
import shutil
import subprocess
import pytest

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(SCRIPT_DIR))
IMPORT_SCRIPT = os.path.join(PROJECT_ROOT, "airflow_app", "scripts", "importMDB.sh")
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


def extraheerSedRegels():
    """Haal de regels uit importMDB.sh die de extra kolommen toevoegen.

    Dat zijn de vijf toewijzingen SED_...=$(escape_sed_csv_value ...) en de twee
    sed-regels (datarijen en kopregel). De functie escape_sed_csv_value zelf haalt
    draaiSedRegels op met extraheerFunctie.

    GNU sed (in de container) accepteert 'sed -i script'; BSD sed (macOS) vat het
    script dan op als backup-extensie. Beide accepteren 'sed -i.bak script', dus
    alleen de -i-optie wordt aangepast.
    """
    with open(IMPORT_SCRIPT, encoding="utf-8") as f:
        inhoud = f.readlines()
    toewijzingen = [r.strip() for r in inhoud if re.match(r'\s*SED_[A-Z]+=\$\(escape_sed_csv_value ', r)]
    sed_regels = [r.strip() for r in inhoud if re.match(r'\s*sed -i ', r)]
    assert len(toewijzingen) == 5, f"Verwacht 5 SED_-toewijzingen in importMDB.sh, gevonden: {toewijzingen}"
    assert len(sed_regels) == 2, f"Verwacht 2 sed-regels in importMDB.sh, gevonden: {sed_regels}"
    return toewijzingen + [r.replace("sed -i ", "sed -i.bak ", 1) for r in sed_regels]


def draaiSedRegels(csv_bestand, tabel, project, timestamp, mdbfile, regels=None):
    """Draai de sed-regels van importMDB.sh (of de opgegeven regels) op een CSV-bestand.

    Net als in importMDB.sh staat IFS op een komma. Retourneert het
    subprocess-resultaat.
    """
    if regels is None:
        regels = extraheerSedRegels()
    script = (
        f'{extraheerFunctie("escape_sed_csv_value")}\n'
        'TABLE="$1"; PROJECT="$2"; timestamp="$3"; mdbfile="$4"; CSV="$5"\n'
        'IFS=","\n'
        + "\n".join(regels) + "\n"
    )
    return subprocess.run(["bash", "-c", script, "bash", tabel, project, timestamp, mdbfile, str(csv_bestand)],
                          capture_output=True, text=True, timeout=60)


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

    def test_sed_regels_voegen_kolommen_toe_na_gequote_laatste_kolom(self, tmp_path, nepMdb):
        """De sed-regels van importMDB.sh werken ook als de laatste kolomnaam gequote is."""
        bin_dir, database = nepMdb
        uit = tmp_path / "opgravingSY002.KOMMA_LAATST.csv"
        assert draaiExport(bin_dir, database, "KOMMA_LAATST", uit) == 0

        mdbfile = "/input/projecten/SY002/C Database/opgravingSY002.mdb"
        script = (
            f'{extraheerFunctie("escape_sed_csv_value")}\n'
            'TABLE="$1"; PROJECT="$2"; timestamp="$3"; mdbfile="$4"; CSV="$5"\n'
            'IFS=","\n'
            + "\n".join(extraheerSedRegels()) + "\n"
            + f'{extraheerFunctie("fix_duplicate_csv_headers")}\n'
            'fix_duplicate_csv_headers "$CSV"\n'
        )
        result = subprocess.run(
            ["bash", "-c", script, "bash", "KOMMA_LAATST", "SY002", "2026-10-21T10:00:00+02:00", mdbfile, str(uit)],
            capture_output=True, text=True, timeout=60)
        assert result.returncode == 0, result.stderr
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


# De sed-regels van importMDB.sh vóór de fix (letterlijke waarden in de
# vervangingstekst), ter vergelijking; -i.bak voor BSD sed.
OUDE_SED_REGELS = [
    r'''sed -i.bak s/$/,"$TABLE","$PROJECT",opgraving"$PROJECT","$timestamp","${mdbfile//\//\\/}"/ "$CSV"''',
    r'''sed -i.bak 1s/,"$TABLE","$PROJECT",opgraving"$PROJECT","$timestamp","${mdbfile//\//\\/}"/,table,projectcd,bron,loadtime,mdbfile/ "$CSV"''',
]

TIJDSTEMPEL = "2026-10-21T10:00:00+02:00"
MDBFILE_SY002 = "/opt/airflow/projectdata/projecten/SY002/C Database/opgravingSY002.mdb"
EXTRA_KOLOMMEN = ["table", "projectcd", "bron", "loadtime", "mdbfile"]

# Kopregel en rijen zoals export_table_to_csv ze schrijft (rijen van mdb-export -H)
VOORBEELD_CSV = (
    'ID,CODE,"FORMAAT IN MM, HORIZONTAAL",VORM\n'
    '1,"ala",22,"Rond"\n'
    '2,,18,"Ovaal, gebroken"\n'
)
VOORBEELD_RIJEN = [["1", "ala", "22", "Rond"], ["2", "", "18", "Ovaal, gebroken"]]


def schrijfVoorbeeldCsv(tmp_path, naam="opgraving.csv"):
    pad = tmp_path / naam
    with open(pad, "w", encoding="utf-8", newline="") as f:
        f.write(VOORBEELD_CSV)
    return pad


def draaiEscape(waarde):
    """Draai escape_sed_csv_value uit importMDB.sh op één waarde."""
    script = f'{extraheerFunctie("escape_sed_csv_value")}\nIFS=","\nescape_sed_csv_value "$1"\n'
    result = subprocess.run(["bash", "-c", script, "bash", waarde],
                            capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr
    return result.stdout


@pytest.mark.unit
class TestEscapeSedCsvValue:
    """escape_sed_csv_value maakt een waarde veilig voor de sed-vervanging en de CSV."""

    @pytest.mark.parametrize("waarde,verwacht", [
        ("MUNTEN EN PENNINGEN", "MUNTEN EN PENNINGEN"),
        ("AARDEWERK 1&2 VOORWERP", r"AARDEWERK 1\&2 VOORWERP"),
        ("A\\B", r"A\\B"),
        ("A/B", r"A\/B"),
        ('NAAM "KORT"', '"NAAM ""KORT"""'),
        ("A, B", '"A, B"'),
        ("TABEL \\1", r"TABEL \\1"),
        ('&\\/"', r'"\&\\\/"""'),
        ("/opt/airflow/C Database/x.mdb", r"\/opt\/airflow\/C Database\/x.mdb"),
        ("2026-10-21T10:00:00+02:00", "2026-10-21T10:00:00+02:00"),
        ("", ""),
    ])
    def test_escape(self, waarde, verwacht):
        assert draaiEscape(waarde) == verwacht

    def test_functie_bestaat_en_wordt_gebruikt(self):
        with open(IMPORT_SCRIPT, encoding="utf-8") as f:
            inhoud = f.read()
        assert "escape_sed_csv_value()" in inhoud
        for variabele in ['"$TABLE"', '"$PROJECT"', '"opgraving$PROJECT"', '"$timestamp"', '"$mdbfile"']:
            assert f"$(escape_sed_csv_value {variabele})" in inhoud
        # De oude regel met de letterlijke waarden in de vervangingstekst staat er niet meer
        assert '${mdbfile//\\//\\\\/}' not in inhoud


@pytest.mark.unit
class TestSedKolommenToevoegen:
    """De sed-regels voegen table, projectcd, bron, loadtime en mdbfile correct toe."""

    @pytest.mark.parametrize("tabel", [
        "AARDEWERK 1&2 VOORWERP",
        "TABEL\\MET\\BACKSLASH",
        "TABEL/MET/SLASH",
        "TABEL, MET KOMMA",
        'TABEL "MET" AANHALINGSTEKEN',
        "TABEL \\1 & \\& ,/\" ALLES",
    ])
    def test_bijzondere_tabelnaam(self, tmp_path, tabel):
        uit = schrijfVoorbeeldCsv(tmp_path)
        result = draaiSedRegels(uit, tabel, "DB034", TIJDSTEMPEL, MDBFILE_SY002)
        assert result.returncode == 0, result.stderr
        kop, *rijen = leesCsv(uit)
        assert kop == ["ID", "CODE", "FORMAAT IN MM, HORIZONTAAL", "VORM"] + EXTRA_KOLOMMEN
        assert len(rijen) == len(VOORBEELD_RIJEN)
        for rij, origineel in zip(rijen, VOORBEELD_RIJEN):
            assert len(rij) == len(kop)
            assert rij == origineel + [tabel, "DB034", "opgravingDB034", TIJDSTEMPEL, MDBFILE_SY002]
            assert rij[kop.index("table")] == tabel

    def test_kopregel_bytegelijk_bij_bijzondere_tabelnaam(self, tmp_path):
        """De kopregel krijgt alleen de kolomnamen, ongeacht de tabelnaam."""
        uit = schrijfVoorbeeldCsv(tmp_path)
        result = draaiSedRegels(uit, "AARDEWERK 1&2 VOORWERP", "DB034", TIJDSTEMPEL, MDBFILE_SY002)
        assert result.returncode == 0, result.stderr
        with open(uit, encoding="utf-8", newline="") as f:
            assert f.readline() == 'ID,CODE,"FORMAAT IN MM, HORIZONTAAL",VORM,table,projectcd,bron,loadtime,mdbfile\n'

    def test_bijzondere_tekens_in_pad(self, tmp_path):
        mdbfile = '/opt/airflow/projectdata/projecten/DB034_Koningsveld & co, "IV"/C Data\\base/opgravingDB34.mdb'
        uit = schrijfVoorbeeldCsv(tmp_path)
        result = draaiSedRegels(uit, "AARDEWERK 1", "DB034", TIJDSTEMPEL, mdbfile)
        assert result.returncode == 0, result.stderr
        kop, *rijen = leesCsv(uit)
        for rij in rijen:
            assert len(rij) == len(kop)
            assert rij[kop.index("mdbfile")] == mdbfile
            assert rij[kop.index("table")] == "AARDEWERK 1"

    def test_gewone_tabel_zelfde_uitvoer_als_voorheen(self, tmp_path):
        """Een gewone tabel: de CSV is byte voor byte gelijk aan die van de oude sed-regels."""
        oud = schrijfVoorbeeldCsv(tmp_path, "oud.csv")
        nieuw = schrijfVoorbeeldCsv(tmp_path, "nieuw.csv")
        args = ("MUNTEN EN PENNINGEN", "SY002", TIJDSTEMPEL, MDBFILE_SY002)
        assert draaiSedRegels(oud, *args, regels=OUDE_SED_REGELS).returncode == 0
        assert draaiSedRegels(nieuw, *args).returncode == 0

        assert nieuw.read_bytes() == oud.read_bytes()
        with open(nieuw, encoding="utf-8", newline="") as f:
            nieuwe_regels = f.readlines()
        assert nieuwe_regels[1] == (
            '1,"ala",22,"Rond",MUNTEN EN PENNINGEN,SY002,opgravingSY002,'
            f'{TIJDSTEMPEL},{MDBFILE_SY002}\n'
        )

    def test_tekstveld_met_regeleinde_blijft_leesbaar(self, tmp_path):
        """Een record over meer regels (tekstveld met regeleinde) blijft een geldige CSV.

        sed werkt per regel en zet de waarden ook achter de regel binnen het
        tekstveld (zoals voorheen). Zonder aanhalingstekens in de toegevoegde
        waarden blijft de CSV geldig en byte voor byte gelijk aan voorheen; met
        aanhalingstekens weigerde mongoimport de tabel ("extraneous \" in field"),
        zoals bij OPGRAVINGEN in de Delftse projectenlijst.
        """
        inhoud = 'ID,KAARTBLAD,CODE\n3,"37E\nregel 2",DC003\n4,"37E",DC004\n'
        oud = tmp_path / "oud.csv"
        nieuw = tmp_path / "nieuw.csv"
        oud.write_text(inhoud, encoding="utf-8")
        nieuw.write_text(inhoud, encoding="utf-8")
        args = ("AARDEWERK 1&2 VOORWERP", "DELF", TIJDSTEMPEL, "/input/projectenlijst/DELF-IT.mdb")
        assert draaiSedRegels(nieuw, *args).returncode == 0
        kop, *rijen = leesCsv(nieuw)
        assert len(rijen) == 2
        assert {len(r) for r in rijen} == {len(kop)}
        assert [r[0] for r in rijen] == ["3", "4"]
        assert rijen[1][kop.index("table")] == "AARDEWERK 1&2 VOORWERP"
        assert rijen[0][kop.index("mdbfile")] == "/input/projectenlijst/DELF-IT.mdb"
        # Voor een tabelnaam zonder & is de uitvoer gelijk aan die van de oude sed-regels
        args = ("OPGRAVINGEN", "DELF", TIJDSTEMPEL, "/input/projectenlijst/DELF-IT.mdb")
        oud.write_text(inhoud, encoding="utf-8")
        nieuw.write_text(inhoud, encoding="utf-8")
        assert draaiSedRegels(oud, *args, regels=OUDE_SED_REGELS).returncode == 0
        assert draaiSedRegels(nieuw, *args).returncode == 0
        assert nieuw.read_bytes() == oud.read_bytes()

    def test_ter_vergelijking_oude_sed_regels_breken_op_ampersand(self, tmp_path):
        """De oude sed-regels: & wordt weggelaten en de kopregel wordt niet vervangen."""
        uit = schrijfVoorbeeldCsv(tmp_path)
        result = draaiSedRegels(uit, "AARDEWERK 1&2 VOORWERP", "DB034", TIJDSTEMPEL, MDBFILE_SY002,
                                regels=OUDE_SED_REGELS)
        assert result.returncode == 0, result.stderr
        kop, rij, _ = leesCsv(uit)
        assert "table" not in kop
        assert "AARDEWERK 12 VOORWERP" in kop
        assert rij[4] == "AARDEWERK 12 VOORWERP"
