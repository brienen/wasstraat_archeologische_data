"""
Unit tests voor de projectcode per bestand in importMDB.sh (issue 87).

importMDB.sh leidt de projectcode af uit het begin van de eerste map onder de
invoermap (hoofdletters en cijfers, bijv. 'SY001' uit 'SY001/C Database/...').
Tot issue 87 werd PROJECT niet per bestand teruggezet: begon een map niet met
hoofdletters of cijfers (bijv. 'werkmap'), dan kreeg dat bestand de projectcode
van het vorige bestand. Nu blijft de projectcode dan leeg, met een INFO-regel.

Net als test_importMDB_lijstbestand.py draait het script direct met
dummy-omgevingsvariabelen en lege nep-MDB's: mdb-tables faalt daarop (of
ontbreekt), zodat er nooit iets naar MongoDB gaat. Gecontroleerd wordt de regel
"Processing ... file for project ...", die Controleer_Databases ook leest. De
volgorde ligt vast via een lijstbestand (derde argument).
"""
import os
import re
import subprocess
import sys
import types

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


def maakMdb(invoer, relatief):
    """Maak een lege nep-MDB onder de invoermap en retourneer het volledige pad."""
    pad = invoer / relatief
    pad.parent.mkdir(parents=True, exist_ok=True)
    pad.write_bytes(b'')
    return str(pad)


def projectcodes(output):
    """Projectcode per verwerkt bestand uit de regels 'Processing <pad> file for project <code> ...'."""
    return {m.group(1): m.group(2) for m in
            re.finditer(r"^Processing (.+) file for project (\S*) \.\.\.$", output, re.M)}


@pytest.mark.unit
class TestProjectcodePerBestand:

    def test_map_zonder_projectcode_erft_niet_van_vorig_bestand(self, tmp_path):
        invoer = tmp_path / "projecten"
        sy001 = maakMdb(invoer, 'SY001/C Database/opgravingSY001.mdb')
        werkmap = maakMdb(invoer, 'werkmap/kopie.mdb')
        sy002 = maakMdb(invoer, 'SY002/opgravingSY002.mdb')
        lijst = tmp_path / "lijst.txt"
        lijst.write_text("\n".join([sy001, werkmap, sy002]) + "\n", encoding='utf-8')

        exitcode, output = draaiImportMDB(tmp_path, invoer, 'test_collection', lijst)

        assert exitcode == 0, output
        assert projectcodes(output) == {sy001: 'SY001', werkmap: '', sy002: 'SY002'}
        assert (f"INFO: Geen projectcode af te leiden uit 'werkmap' (begint niet met hoofdletters of cijfers); "
                f"projectcd blijft leeg voor {werkmap}") in output
        # Alleen het bestand zonder projectcode krijgt de INFO-regel
        assert output.count("INFO: Geen projectcode af te leiden") == 1

    def test_projectcode_uit_bestandsnaam_direct_in_invoermap(self, tmp_path):
        """Lijsten zoals MONSTERS.mdb staan direct in de invoermap: de code komt uit de bestandsnaam."""
        invoer = tmp_path / "monsterdatabase"
        monsters = maakMdb(invoer, 'MONSTERS.mdb')
        klein = maakMdb(invoer, 'residu.mdb')
        lijst = tmp_path / "lijst.txt"
        lijst.write_text("\n".join([monsters, klein]) + "\n", encoding='utf-8')

        exitcode, output = draaiImportMDB(tmp_path, invoer, 'test_collection', lijst)

        assert exitcode == 0, output
        assert projectcodes(output) == {monsters: 'MONSTERS', klein: ''}

    def test_regel_blijft_leesbaar_voor_controleer_databases(self, tmp_path):
        """De Processing-regel met een lege projectcode telt nog als verwerkt (controle_extractie.RE_VERWERKT)."""
        # Zoals in test_controle_extractie.py: image_import (via controle_extractie) vereist anders PIL e.d.
        if "shared.image_util" not in sys.modules:
            sys.modules["shared.image_util"] = types.ModuleType("shared.image_util")
        import wasstraat.controle_extractie as controle
        invoer = tmp_path / "projecten"
        werkmap = maakMdb(invoer, 'werkmap/kopie.mdb')
        _, output = draaiImportMDB(tmp_path, invoer, 'test_collection')
        regels = [r for r in output.splitlines() if r.startswith("Processing ")]
        assert regels and controle.RE_VERWERKT.match(regels[0]).group(1) == werkmap
