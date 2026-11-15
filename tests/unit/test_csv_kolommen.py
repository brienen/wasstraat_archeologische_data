"""
Unit tests voor airflow_app/scripts/csv_kolommen.py en de aanroep ervan in importMDB.sh (issue 74).

importMDB.sh zet achter elk record van de CSV-export van een Access-tabel de
kolommen table, projectcd, bron, loadtime en mdbfile. Tot issue 74 deed sed dat
per regel. Een tekstveld (memo) met een regeleinde staat in de export tussen
aanhalingstekens en beslaat meer regels; sed zette de waarden dan ook midden in
dat veld. csv_kolommen.py bepaalt met de csv-module waar een record eindigt en
zet de waarden alleen aan het einde. De tekst van de records blijft ongewijzigd,
zodat de uitvoer voor records zonder regeleinde byte voor byte gelijk is aan die
van de vroegere sed-regels (die staan hieronder ter vergelijking).

De laatste klasse draait het hele importMDB.sh met nagebootste mdbtools en een
nagebootste mongoimport die de aangeboden CSV bewaart.
"""
import csv
import importlib.util
import io
import json
import os
import subprocess
import sys

import pytest

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(SCRIPT_DIR))
SCRIPTS = os.path.join(PROJECT_ROOT, "airflow_app", "scripts")
KOLOMMEN_SCRIPT = os.path.join(SCRIPTS, "csv_kolommen.py")
IMPORT_SCRIPT = os.path.join(SCRIPTS, "importMDB.sh")

_spec = importlib.util.spec_from_file_location("csv_kolommen", KOLOMMEN_SCRIPT)
csv_kolommen = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(csv_kolommen)

EXTRA_KOLOMMEN = ["table", "projectcd", "bron", "loadtime", "mdbfile"]
TIJDSTEMPEL = "2026-10-21T10:00:00+02:00"
MDBFILE_SY002 = "/opt/airflow/projectdata/projecten/SY002/C Database/opgravingSY002.mdb"
WAARDEN_SY002 = ["SPOREN", "SY002", "opgravingSY002", TIJDSTEMPEL, MDBFILE_SY002]
ACHTERVOEGSEL_SY002 = ",SPOREN,SY002,opgravingSY002," + TIJDSTEMPEL + "," + MDBFILE_SY002

# Kopregel zoals export_table_to_csv hem schrijft, rijen zoals mdb-export -H ze
# geeft: tekst tussen aanhalingstekens, getallen zonder, NULL als leeg veld.
VOORBEELD_CSV = (
    'ID,CODE,"FORMAAT IN MM, HORIZONTAAL",VORM\n'
    '1,"ala",22,"Rond"\n'
    '2,,18,"Ovaal, gebroken"\n'
)
VOORBEELD_KOP = ["ID", "CODE", "FORMAAT IN MM, HORIZONTAAL", "VORM"]
VOORBEELD_RIJEN = [["1", "ala", "22", "Rond"], ["2", "", "18", "Ovaal, gebroken"]]

# Een memo-veld met een regeleinde, zoals OPGRAVINGEN.KAARTBLAD in de Delftse projectenlijst
MEMO_CSV = (
    'ID,KAARTBLAD,CODE\n'
    '3,"37E\r\n\r\n37E",DC003\n'
    '4,"37E",DC004\n'
)

# De vroegere functie en sed-regels van importMDB.sh (tot issue 74), ter vergelijking.
# GNU sed (container) accepteert 'sed -i script', BSD sed (macOS) niet; beide
# accepteren 'sed -i.bak script'.
OUDE_ESCAPE_FUNCTIE = r'''escape_sed_csv_value() {
    local WAARDE="$1"
    case "$WAARDE" in
        *[,\"]*) WAARDE="\"$(printf '%s' "$WAARDE" | sed -e 's/"/""/g')\"" ;;
    esac
    printf '%s' "$WAARDE" | sed -e 's/[\/&]/\\&/g'
}'''
OUDE_SED_REGELS = [
    'SED_TABLE=$(escape_sed_csv_value "$TABLE")',
    'SED_PROJECT=$(escape_sed_csv_value "$PROJECT")',
    'SED_BRON=$(escape_sed_csv_value "opgraving$PROJECT")',
    'SED_LOADTIME=$(escape_sed_csv_value "$timestamp")',
    'SED_MDBFILE=$(escape_sed_csv_value "$mdbfile")',
    r'sed -i.bak "1!s/\$/,$SED_TABLE,$SED_PROJECT,$SED_BRON,$SED_LOADTIME,$SED_MDBFILE/" "$CSV"',
    r'sed -i.bak "1s/\$/,table,projectcd,bron,loadtime,mdbfile/" "$CSV"',
]


def draaiOudeSed(pad, tabel, project, timestamp, mdbfile):
    """Draai de vroegere sed-regels van importMDB.sh op een CSV-bestand (IFS op een komma, zoals in het script)."""
    script = (
        OUDE_ESCAPE_FUNCTIE + "\n"
        'TABLE="$1"; PROJECT="$2"; timestamp="$3"; mdbfile="$4"; CSV="$5"\n'
        'IFS=","\n'
        + "\n".join(OUDE_SED_REGELS) + "\n"
    )
    result = subprocess.run(["bash", "-c", script, "bash", tabel, project, timestamp, mdbfile, str(pad)],
                            capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr


def schrijf(pad, tekst):
    with open(pad, "w", encoding="utf-8", newline="") as f:
        f.write(tekst)
    return pad


def lees(pad):
    with open(pad, encoding="utf-8", newline="") as f:
        return f.read()


def leesCsv(pad):
    with open(pad, encoding="utf-8", newline="") as f:
        return list(csv.reader(f))


def verwerkTekst(tekst, waarden=WAARDEN_SY002):
    """Draai voegKolommenToe op een tekst; retourneer (uitvoer, aantal)."""
    uit = io.StringIO(newline="")
    aantal = csv_kolommen.voegKolommenToe(io.StringIO(tekst, newline=""), uit, waarden)
    return uit.getvalue(), aantal


@pytest.mark.unit
class TestMaakAchtervoegsel:
    """De toegevoegde waarden worden gequote zoals csv.writer met QUOTE_MINIMAL."""

    @pytest.mark.parametrize("waarde,verwacht", [
        ("MUNTEN EN PENNINGEN", "MUNTEN EN PENNINGEN"),
        ("AARDEWERK 1&2 VOORWERP", "AARDEWERK 1&2 VOORWERP"),
        ("A\\B/C", "A\\B/C"),
        ("A, B", '"A, B"'),
        ('NAAM "KORT"', '"NAAM ""KORT"""'),
        (TIJDSTEMPEL, TIJDSTEMPEL),
        (MDBFILE_SY002, MDBFILE_SY002),
    ])
    def test_een_waarde(self, waarde, verwacht):
        assert csv_kolommen.maakAchtervoegsel([waarde, "x"]) == f",{verwacht},x"

    def test_lege_waarde_blijft_leeg(self):
        assert csv_kolommen.maakAchtervoegsel(["T", "", "opgraving", TIJDSTEMPEL, "/p.mdb"]) == \
            f",T,,opgraving,{TIJDSTEMPEL},/p.mdb"


@pytest.mark.unit
class TestVoegKolommenToe:
    """voegKolommenToe zet de vijf kolommen achter de kopregel en achter elk record."""

    def test_gewone_rijen(self):
        uit, aantal = verwerkTekst(VOORBEELD_CSV)
        assert aantal == 2
        assert uit == (
            'ID,CODE,"FORMAAT IN MM, HORIZONTAAL",VORM,table,projectcd,bron,loadtime,mdbfile\n'
            '1,"ala",22,"Rond"' + ACHTERVOEGSEL_SY002 + '\n'
            '2,,18,"Ovaal, gebroken"' + ACHTERVOEGSEL_SY002 + '\n'
        )
        kop, *rijen = list(csv.reader(io.StringIO(uit, newline="")))
        assert kop == VOORBEELD_KOP + EXTRA_KOLOMMEN
        assert rijen == [r + WAARDEN_SY002 for r in VOORBEELD_RIJEN]

    @pytest.mark.parametrize("regeleinde", ["\n", "\r\n", "\r"])
    def test_rij_met_regeleinde_in_gequote_cel(self, regeleinde):
        memo = f"Gemetselde beerput{regeleinde}Binnenwerk met tonvormige bodem"
        tekst = f'ID,SPOORNO,BESCHRIJVING,AARD\n1,4,"{memo}","Beerput"\n2,5,"Kuil","Kuil"\n'
        uit, aantal = verwerkTekst(tekst)
        assert aantal == 2
        kop, *rijen = list(csv.reader(io.StringIO(uit, newline="")))
        assert kop == ["ID", "SPOORNO", "BESCHRIJVING", "AARD"] + EXTRA_KOLOMMEN
        assert rijen[0] == ["1", "4", memo, "Beerput"] + WAARDEN_SY002
        assert rijen[1] == ["2", "5", "Kuil", "Kuil"] + WAARDEN_SY002
        # De waarden staan alleen aan het einde van het record, niet in het tekstveld
        assert uit.count(MDBFILE_SY002) == 2
        assert f'1,4,"{memo}","Beerput"{ACHTERVOEGSEL_SY002}\n' in uit

    def test_meerdere_regeleinden_en_lege_regels_in_cel(self):
        """Zoals OPGRAVINGEN.KAARTBLAD in de Delftse projectenlijst: '37E' plus lege regels."""
        uit, aantal = verwerkTekst(MEMO_CSV)
        assert aantal == 2
        kop, *rijen = list(csv.reader(io.StringIO(uit, newline="")))
        assert rijen[0] == ["3", "37E\r\n\r\n37E", "DC003"] + WAARDEN_SY002
        assert rijen[1] == ["4", "37E", "DC004"] + WAARDEN_SY002
        assert {len(r) for r in rijen} == {len(kop)}

    def test_lege_velden(self):
        """Lege velden (NULL in Access) blijven leeg, ook als laatste veld en in een rij met alleen lege velden."""
        tekst = 'ID,A,B,C\n1,,,\n,,,\n2,"",,"x"\n'
        uit, aantal = verwerkTekst(tekst)
        assert aantal == 3
        assert uit.splitlines()[1] == "1,,," + ACHTERVOEGSEL_SY002
        assert uit.splitlines()[2] == ",,," + ACHTERVOEGSEL_SY002
        assert uit.splitlines()[3] == '2,"",,"x"' + ACHTERVOEGSEL_SY002
        rijen = list(csv.reader(io.StringIO(uit, newline="")))[1:]
        assert rijen[0] == ["1", "", "", ""] + WAARDEN_SY002
        assert rijen[1] == ["", "", "", ""] + WAARDEN_SY002

    def test_cel_met_komma_en_aanhalingstekens(self):
        tekst = 'ID,VORM,OPMERKING\n1,"Ovaal, ""gebroken""","zegt ""ja"", of\n""nee"""\n'
        uit, aantal = verwerkTekst(tekst)
        assert aantal == 1
        _, rij = list(csv.reader(io.StringIO(uit, newline="")))
        assert rij == ["1", 'Ovaal, "gebroken"', 'zegt "ja", of\n"nee"'] + WAARDEN_SY002

    def test_lege_tabel_alleen_kopregel(self):
        uit, aantal = verwerkTekst('ID,"A, B"\n')
        assert aantal == 0
        assert uit == 'ID,"A, B",table,projectcd,bron,loadtime,mdbfile\n'

    def test_lege_invoer(self):
        assert verwerkTekst("") == ("", 0)

    def test_laatste_regel_zonder_regeleinde(self):
        uit, aantal = verwerkTekst('ID,A\n1,"x"\n2,"y"')
        assert aantal == 2
        assert uit == f'ID,A,table,projectcd,bron,loadtime,mdbfile\n1,"x"{ACHTERVOEGSEL_SY002}\n2,"y"{ACHTERVOEGSEL_SY002}'

    def test_windows_regeleinden_blijven_behouden(self):
        uit, aantal = verwerkTekst('ID,A\r\n1,"x"\r\n')
        assert aantal == 1
        assert uit == f'ID,A,table,projectcd,bron,loadtime,mdbfile\r\n1,"x"{ACHTERVOEGSEL_SY002}\r\n'

    @pytest.mark.parametrize("tabel", [
        "AARDEWERK 1&2 VOORWERP",
        "TABEL\\MET\\BACKSLASH",
        "TABEL/MET/SLASH",
        "TABEL, MET KOMMA",
        'TABEL "MET" AANHALINGSTEKEN',
        "TABEL \\1 & \\& ,/\" ALLES",
    ])
    def test_bijzondere_tabelnaam(self, tabel):
        waarden = [tabel, "DB034", "opgravingDB034", TIJDSTEMPEL, MDBFILE_SY002]
        uit, _ = verwerkTekst(VOORBEELD_CSV + '3,"memo\nmet regeleinde",1,"x"\n', waarden)
        kop, *rijen = list(csv.reader(io.StringIO(uit, newline="")))
        assert kop == VOORBEELD_KOP + EXTRA_KOLOMMEN
        assert len(rijen) == 3
        for rij in rijen:
            assert len(rij) == len(kop)
            assert rij[-5:] == waarden
        assert rijen[2][1] == "memo\nmet regeleinde"

    def test_bijzondere_tekens_in_pad(self):
        mdbfile = '/opt/airflow/projectdata/projecten/DB034_Koningsveld & co, "IV"/C Data\\base/opgravingDB34.mdb'
        waarden = ["AARDEWERK 1", "DB034", "opgravingDB034", TIJDSTEMPEL, mdbfile]
        uit, _ = verwerkTekst(MEMO_CSV, waarden)
        kop, *rijen = list(csv.reader(io.StringIO(uit, newline="")))
        for rij in rijen:
            assert len(rij) == len(kop)
            assert rij[kop.index("mdbfile")] == mdbfile
            assert rij[kop.index("table")] == "AARDEWERK 1"

    def test_verkeerd_aantal_waarden(self):
        with pytest.raises(ValueError):
            verwerkTekst(VOORBEELD_CSV, ["T", "P"])


@pytest.mark.unit
class TestVergelijkingMetOudeSed:
    """Zonder regeleinde in een veld is de uitvoer gelijk aan die van de vroegere sed-regels."""

    @pytest.mark.parametrize("tabel,mdbfile", [
        ("MUNTEN EN PENNINGEN", MDBFILE_SY002),
        ("AARDEWERK 1&2 VOORWERP", MDBFILE_SY002),
        ("TABEL, MET KOMMA", MDBFILE_SY002),
        ('TABEL "MET" AANHALINGSTEKEN', MDBFILE_SY002),
        ("AARDEWERK 1", '/opt/airflow/projecten/DB034 & co, "IV"/C Data\\base/opgravingDB34.mdb'),
    ])
    def test_bytegelijk_zonder_regeleinde_in_veld(self, tmp_path, tabel, mdbfile):
        oud = schrijf(tmp_path / "oud.csv", VOORBEELD_CSV)
        nieuw = schrijf(tmp_path / "nieuw.csv", VOORBEELD_CSV)
        draaiOudeSed(oud, tabel, "SY002", TIJDSTEMPEL, mdbfile)
        csv_kolommen.verwerkBestand(str(nieuw), [tabel, "SY002", "opgravingSY002", TIJDSTEMPEL, mdbfile])
        assert nieuw.read_bytes() == oud.read_bytes()

    def test_ter_vergelijking_oude_sed_zette_waarden_in_het_tekstveld(self, tmp_path):
        """Issue 74: sed zette de waarden ook achter de regels binnen het tekstveld."""
        oud = schrijf(tmp_path / "oud.csv", MEMO_CSV)
        nieuw = schrijf(tmp_path / "nieuw.csv", MEMO_CSV)
        draaiOudeSed(oud, "OPGRAVINGEN", "DELF", TIJDSTEMPEL, "/input/projectenlijst/DELF-IT.mdb")
        waarden = ["OPGRAVINGEN", "DELF", "opgravingDELF", TIJDSTEMPEL, "/input/projectenlijst/DELF-IT.mdb"]
        csv_kolommen.verwerkBestand(str(nieuw), waarden)

        kaartblad_oud = leesCsv(oud)[1][1]
        assert kaartblad_oud.startswith("37E\r,OPGRAVINGEN,DELF,opgravingDELF,")
        assert kaartblad_oud.count("/input/projectenlijst/DELF-IT.mdb") == 2
        assert leesCsv(nieuw)[1] == ["3", "37E\r\n\r\n37E", "DC003"] + waarden
        # De records zonder regeleinde zijn in beide gelijk
        assert lees(oud).splitlines()[-1] == lees(nieuw).splitlines()[-1]


@pytest.mark.unit
class TestVerwerkBestand:
    """verwerkBestand vervangt het CSV-bestand en telt de datarecords."""

    def test_bestand_wordt_vervangen(self, tmp_path):
        pad = schrijf(tmp_path / "opgravingSY002.SPOREN.csv", MEMO_CSV)
        assert csv_kolommen.verwerkBestand(str(pad), WAARDEN_SY002) == 2
        kop, *rijen = leesCsv(pad)
        assert kop == ["ID", "KAARTBLAD", "CODE"] + EXTRA_KOLOMMEN
        assert len(rijen) == 2
        # Geen tijdelijke bestanden achtergebleven
        assert os.listdir(tmp_path) == ["opgravingSY002.SPOREN.csv"]

    def test_rechten_blijven_gelijk(self, tmp_path):
        pad = schrijf(tmp_path / "t.csv", MEMO_CSV)
        pad.chmod(0o644)
        csv_kolommen.verwerkBestand(str(pad), WAARDEN_SY002)
        assert pad.stat().st_mode & 0o777 == 0o644

    def test_leeg_bestand_blijft_leeg(self, tmp_path):
        pad = schrijf(tmp_path / "leeg.csv", "")
        assert csv_kolommen.verwerkBestand(str(pad), WAARDEN_SY002) == 0
        assert pad.read_bytes() == b""

    def test_niet_utf8_bytes_blijven_ongewijzigd(self, tmp_path):
        """Bytes die geen geldig UTF-8 zijn (encoding-conversie mislukt) gaan niet verloren."""
        pad = tmp_path / "cp1252.csv"
        pad.write_bytes('ID,NAAM\n1,"Café\r\nterras"\n'.encode("cp1252"))
        assert csv_kolommen.verwerkBestand(str(pad), WAARDEN_SY002) == 1
        assert pad.read_bytes() == (
            'ID,NAAM,table,projectcd,bron,loadtime,mdbfile\n1,"Café\r\nterras"'.encode("cp1252")
            + ACHTERVOEGSEL_SY002.encode("utf-8") + b"\n")

    def test_grote_tabel_met_memo_velden(self, tmp_path):
        """Tienduizenden rijen (zoals Monster_botanie_determinatie in Delft) worden regel voor regel verwerkt."""
        pad = tmp_path / "groot.csv"
        with open(pad, "w", encoding="utf-8", newline="") as f:
            f.write("ID,SOORT,OPMERKING\n")
            for i in range(30000):
                opmerking = f'"regel 1\r\nregel {i}"' if i % 100 == 0 else f'"opmerking {i}"'
                f.write(f'{i},"Soort {i}",{opmerking}\n')
        assert csv_kolommen.verwerkBestand(str(pad), WAARDEN_SY002) == 30000
        rijen = leesCsv(pad)
        assert len(rijen) == 30001
        assert {len(r) for r in rijen} == {8}
        assert rijen[1][2] == "regel 1\r\nregel 0"
        assert rijen[-1][-5:] == WAARDEN_SY002

    def test_opdrachtregel(self, tmp_path):
        pad = schrijf(tmp_path / "t.csv", MEMO_CSV)
        result = subprocess.run([sys.executable, KOLOMMEN_SCRIPT, str(pad)] + WAARDEN_SY002,
                                capture_output=True, text=True, timeout=60)
        assert result.returncode == 0, result.stderr
        assert result.stdout == "2\n"
        assert leesCsv(pad)[1][-1] == MDBFILE_SY002

    def test_opdrachtregel_fout_laat_bestand_ongewijzigd(self, tmp_path):
        pad = schrijf(tmp_path / "t.csv", MEMO_CSV)
        result = subprocess.run([sys.executable, KOLOMMEN_SCRIPT, str(pad), "T", "P"],
                                capture_output=True, text=True, timeout=60)
        assert result.returncode == 1
        assert result.stdout == ""
        assert lees(pad) == MEMO_CSV
        result = subprocess.run([sys.executable, KOLOMMEN_SCRIPT, str(tmp_path / "weg.csv")] + WAARDEN_SY002,
                                capture_output=True, text=True, timeout=60)
        assert result.returncode == 1
        assert "ERROR" in result.stderr


# ============================================================
# importMDB.sh als geheel, met nagebootste mdbtools en mongoimport
# ============================================================

# Nagebootste database: tabellen met kolommen en rijen (tekst wordt gequote, zoals mdb-export)
NEP_DATABASE = {
    "SPOREN": {
        "kolommen": ["ID", "CODENAAM", "SPOORNO", "BESCHRIJVING"],
        "rijen": [
            [1, "SY002", 3, "Bakstenen muur, kruisverband"],
            [2, "SY002", 4, "Gemetselde beerput, vierkant\r\nBinnenwerk met tonvormige bodem"],
            [3, "SY002", 5, None],
        ],
    },
    "LEEG": {"kolommen": ["ID", "A"], "rijen": []},
}

NEP_MDBTOOLS = r'''#!/usr/bin/env python3
import json, os, sys

naam = os.path.basename(sys.argv[0])
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
uit = sys.stdout.buffer
if naam == "mdb-tables":
    uit.write((scheiding.join(tabellen) + scheiding + "\n").encode("utf-8"))
    sys.exit(0)
if naam == "mdb-prop":
    sys.exit(1)
tabel = tabellen[posities[1]]

def veld(waarde):
    if waarde is None:
        return ""
    if isinstance(waarde, str) and quote:
        return '"' + waarde.replace('"', '""') + '"'
    return str(waarde)

if kop:
    uit.write((scheiding.join(tabel["kolommen"]) + "\n").encode("utf-8"))
for rij in tabel["rijen"]:
    uit.write((scheiding.join(veld(w) for w in rij) + "\n").encode("utf-8"))
'''

# Bewaart elk aangeboden bestand als <collectie>.<n> in $NEP_MONGO_UIT
NEP_MONGOIMPORT = r'''#!/usr/bin/env python3
import os, shutil, sys

args = sys.argv[1:]
bestand = args[args.index("--file") + 1]
collectie = args[args.index("--collection") + 1]
uit = os.environ["NEP_MONGO_UIT"]
n = len(os.listdir(uit))
shutil.copy(bestand, os.path.join(uit, f"{collectie}.{n}"))
'''


@pytest.fixture
def nepOmgeving(tmp_path):
    """Invoermap met een nep-MDB van SY002, nagebootste mdbtools/mongoimport en een vaste datum."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for naam in ["mdb-tables", "mdb-export", "mdb-prop"]:
        (bin_dir / naam).write_text(NEP_MDBTOOLS, encoding="utf-8")
    (bin_dir / "mongoimport").write_text(NEP_MONGOIMPORT, encoding="utf-8")
    (bin_dir / "date").write_text(f"#!/bin/sh\necho {TIJDSTEMPEL}\n", encoding="utf-8")
    for bestand in bin_dir.iterdir():
        bestand.chmod(0o755)

    invoer = tmp_path / "projecten"
    mdb = invoer / "SY002" / "C Database" / "opgravingSY002.mdb"
    mdb.parent.mkdir(parents=True)
    mdb.write_text(json.dumps(NEP_DATABASE), encoding="utf-8")
    for naam in ["tmp", "logs", "mongo"]:
        (tmp_path / naam).mkdir()
    env = dict(os.environ,
               PATH=f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}",
               AIRFLOW_TEMPDIR=str(tmp_path / "tmp"), AIRFLOW_LOGDIR=str(tmp_path / "logs"),
               DB_STAGING="testdb", MONGO_INITDB_ROOT_USERNAME="test", MONGO_INITDB_ROOT_PASSWORD="test",
               MONGO_SERVER="localhost", COLL_STAGING_METAINFO="metainfo",
               NEP_MONGO_UIT=str(tmp_path / "mongo"))
    return invoer, mdb, env, tmp_path / "mongo"


@pytest.mark.unit
class TestImportMDBMetCsvKolommen:
    """importMDB.sh gebruikt csv_kolommen.py; mongoimport krijgt de waarden aan het einde van elk record."""

    def test_script_gebruikt_csv_kolommen_en_geen_sed_meer(self):
        with open(IMPORT_SCRIPT, encoding="utf-8") as f:
            inhoud = f.read()
        assert 'python3 "$SCRIPT_DIR/csv_kolommen.py" "$CSV" "$TABLE" "$PROJECT" "opgraving$PROJECT" ' \
               '"$timestamp" "$mdbfile"' in inhoud
        assert "escape_sed_csv_value" not in inhoud
        assert "sed -i" not in inhoud
        assert "wc -l" not in inhoud

    def test_csv_kolommen_staat_naast_importMDB(self):
        assert os.path.isfile(KOLOMMEN_SCRIPT)
        assert os.path.dirname(KOLOMMEN_SCRIPT) == os.path.dirname(IMPORT_SCRIPT)

    def test_volledige_import(self, nepOmgeving):
        invoer, mdb, env, mongo = nepOmgeving
        result = subprocess.run(["bash", IMPORT_SCRIPT, str(invoer), "Staging_Projecten_Oud"],
                                capture_output=True, text=True, timeout=120, env=env)
        assert result.returncode == 0, result.stdout + result.stderr
        assert "ERROR" not in result.stdout, result.stdout

        aangeboden = sorted(os.listdir(mongo))
        csv_bestanden = [b for b in aangeboden if b.startswith("Staging_Projecten_Oud.")]
        # Alleen SPOREN gaat naar mongoimport; de lege tabel wordt overgeslagen
        assert len(csv_bestanden) == 1, aangeboden
        kop, *rijen = leesCsv(mongo / csv_bestanden[0])
        assert kop == ["ID", "CODENAAM", "SPOORNO", "BESCHRIJVING"] + EXTRA_KOLOMMEN
        waarden = ["SPOREN", "SY002", "opgravingSY002", TIJDSTEMPEL, str(mdb)]
        assert rijen == [
            ["1", "SY002", "3", "Bakstenen muur, kruisverband"] + waarden,
            ["2", "SY002", "4", "Gemetselde beerput, vierkant\r\nBinnenwerk met tonvormige bodem"] + waarden,
            ["3", "SY002", "5", ""] + waarden,
        ]
        # LENGTE (en de teller in de metainfo) telt records, geen regels
        assert "is: 3" in result.stdout
        meta = [b for b in aangeboden if b.startswith("metainfo.")]
        assert len(meta) == 1
        with open(mongo / meta[0], encoding="utf-8") as f:
            metainfo = json.load(f)
        assert metainfo["table"] == "SPOREN"
        assert metainfo["teller"] == "3"
