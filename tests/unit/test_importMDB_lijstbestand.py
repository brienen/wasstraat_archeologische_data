"""
Unit tests voor het optionele derde argument van importMDB.sh: een lijstbestand
met de te verwerken MDB/ACCDB-bestanden (incrementeel laden, issue 61).

Net als sectie D van test_importMDB_functions.sh draait het script direct met
dummy-omgevingsvariabelen. De bestanden zijn lege nep-MDB's: mdb-tables faalt
daarop (of ontbreekt), zodat er nooit iets naar MongoDB gaat. Gecontroleerd
wordt welke bestanden het script probeert te verwerken ("Processing ...").
"""
import os
import subprocess
import pytest

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(SCRIPT_DIR))
IMPORT_SCRIPT = os.path.join(PROJECT_ROOT, "airflow_app", "scripts", "importMDB.sh")


def draaiImportMDB(tmp_path, *args):
    """Draai importMDB.sh met de opgegeven argumenten en retourneer (exitcode, output)."""
    env = dict(os.environ,
               AIRFLOW_TEMPDIR=str(tmp_path), DB_STAGING='testdb', AIRFLOW_LOGDIR=str(tmp_path),
               MONGO_INITDB_ROOT_USERNAME='test', MONGO_INITDB_ROOT_PASSWORD='test',
               MONGO_SERVER='localhost', COLL_STAGING_METAINFO='metainfo')
    result = subprocess.run(["bash", IMPORT_SCRIPT] + [str(a) for a in args],
                            capture_output=True, text=True, timeout=60, env=env)
    return result.returncode, result.stdout


@pytest.fixture
def invoermap(tmp_path):
    """Invoermap met drie nep-MDB's, waarvan één in een map met een spatie."""
    invoer = tmp_path / "projecten"
    paden = {}
    for naam, rel in [('sy001', 'SY001/C Database/opgravingSY001.mdb'),
                      ('sy002', 'SY002/C Database/opgravingSY002.mdb'),
                      ('sy003', 'SY003/opgravingSY003.accdb')]:
        pad = invoer / rel
        pad.parent.mkdir(parents=True, exist_ok=True)
        pad.write_bytes(b'')
        paden[naam] = str(pad)
    return invoer, paden


def schrijfLijst(tmp_path, regels, einde='\n'):
    lijst = tmp_path / "delta_projecten.txt"
    lijst.write_text(einde.join(regels) + (einde if regels else ''), encoding='utf-8')
    return lijst


@pytest.mark.unit
class TestImportMDBLijstbestand:
    """Test importMDB.sh met en zonder lijstbestand."""

    def test_zonder_lijstbestand_alle_bestanden(self, tmp_path, invoermap):
        invoer, paden = invoermap
        exitcode, output = draaiImportMDB(tmp_path, invoer, 'test_collection')
        assert exitcode == 0
        assert "3 MDB/ACCDB-bestand(en) gevonden" in output
        for pad in paden.values():
            assert f"Processing {pad} file" in output

    def test_alleen_bestanden_uit_lijst(self, tmp_path, invoermap):
        invoer, paden = invoermap
        lijst = schrijfLijst(tmp_path, [paden['sy002']])
        exitcode, output = draaiImportMDB(tmp_path, invoer, 'test_collection', lijst)
        assert exitcode == 0
        assert "1 MDB/ACCDB-bestand(en) uit lijstbestand" in output
        assert f"Processing {paden['sy002']} file for project SY002" in output
        assert paden['sy001'] not in output
        assert paden['sy003'] not in output

    def test_lege_lijst_niets_doen_wel_rapport(self, tmp_path, invoermap):
        invoer, _ = invoermap
        lijst = schrijfLijst(tmp_path, [])
        exitcode, output = draaiImportMDB(tmp_path, invoer, 'test_collection', lijst)
        assert exitcode == 0
        assert "bevat geen bestanden, niets te verwerken" in output
        assert "Processing" not in output
        assert "ENCODING RAPPORT" in output
        assert "Totaal MDB-bestanden verwerkt:       0" in output

    def test_lege_lijst_bij_niet_bestaande_invoermap(self, tmp_path):
        lijst = schrijfLijst(tmp_path, [])
        exitcode, output = draaiImportMDB(tmp_path, tmp_path / "bestaat_niet", 'test_collection', lijst)
        assert exitcode == 0
        assert "ENCODING RAPPORT" in output

    def test_ontbrekend_lijstbestand_faalt(self, tmp_path, invoermap):
        invoer, _ = invoermap
        exitcode, output = draaiImportMDB(tmp_path, invoer, 'test_collection', tmp_path / "weg.txt")
        assert exitcode == 1
        assert "ERROR: Lijstbestand" in output

    def test_niet_bestaand_pad_in_lijst_wordt_overgeslagen(self, tmp_path, invoermap):
        invoer, paden = invoermap
        weg = str(invoer / "SY009" / "weg.mdb")
        lijst = schrijfLijst(tmp_path, [weg, paden['sy001']])
        exitcode, output = draaiImportMDB(tmp_path, invoer, 'test_collection', lijst)
        assert exitcode == 0
        assert f"WARNING: Bestand '{weg}' uit lijstbestand bestaat niet" in output
        assert f"Processing {paden['sy001']} file for project SY001" in output
        assert f"Processing {weg}" not in output

    def test_windows_regeleinden_en_lege_regels(self, tmp_path, invoermap):
        invoer, paden = invoermap
        lijst = schrijfLijst(tmp_path, [paden['sy001'], '', paden['sy003']], einde='\r\n')
        exitcode, output = draaiImportMDB(tmp_path, invoer, 'test_collection', lijst)
        assert exitcode == 0
        assert "2 MDB/ACCDB-bestand(en) uit lijstbestand" in output
        assert f"Processing {paden['sy003']} file for project SY003" in output

    def test_laatste_regel_zonder_regeleinde(self, tmp_path, invoermap):
        invoer, paden = invoermap
        lijst = tmp_path / "delta.txt"
        lijst.write_text(paden['sy002'], encoding='utf-8')
        exitcode, output = draaiImportMDB(tmp_path, invoer, 'test_collection', lijst)
        assert exitcode == 0
        assert f"Processing {paden['sy002']} file" in output

    def test_verkeerd_aantal_argumenten(self, tmp_path):
        exitcode, output = draaiImportMDB(tmp_path, 'a')
        assert exitcode == 1
        exitcode, output = draaiImportMDB(tmp_path, 'a', 'b', 'c', 'd')
        assert exitcode == 1
