"""
Python wrapper voor de bash unit tests van importMDB.sh functies.

Draait tests/unit/test_importMDB_functions.sh via subprocess zodat
pytest (en run_tests.py) de bash-testen automatisch meeneemt.
"""
import os
import subprocess
import pytest

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(SCRIPT_DIR))
UNIT_BASH_SCRIPT = os.path.join(SCRIPT_DIR, "test_importMDB_functions.sh")
IMPORT_SCRIPT = os.path.join(PROJECT_ROOT, "airflow_app", "scripts", "importMDB.sh")


@pytest.mark.unit
class TestImportMDBBashFunctions:
    """Draait de bash unit tests voor importMDB.sh functies."""

    def test_bash_script_exists(self):
        assert os.path.isfile(UNIT_BASH_SCRIPT), (
            f"Bash test script niet gevonden: {UNIT_BASH_SCRIPT}"
        )

    def test_import_script_exists(self):
        assert os.path.isfile(IMPORT_SCRIPT), (
            f"importMDB.sh niet gevonden: {IMPORT_SCRIPT}"
        )

    def test_importMDB_unit_functions(self):
        """Draait test_importMDB_functions.sh en controleert exit code."""
        result = subprocess.run(
            ["bash", UNIT_BASH_SCRIPT],
            capture_output=True,
            text=True,
            timeout=60,
            cwd=PROJECT_ROOT,
        )
        # Print output voor debugging bij falen
        if result.returncode != 0:
            print("=== STDOUT ===")
            print(result.stdout)
            print("=== STDERR ===")
            print(result.stderr)
        assert result.returncode == 0, (
            f"Bash unit tests gefaald (exit {result.returncode}).\n"
            f"Output:\n{result.stdout}\n{result.stderr}"
        )

    def test_all_unit_tests_pass(self):
        """Controleert dat de output 'ALL ... TESTS PASSED' bevat."""
        result = subprocess.run(
            ["bash", UNIT_BASH_SCRIPT],
            capture_output=True,
            text=True,
            timeout=60,
            cwd=PROJECT_ROOT,
        )
        assert "ALL" in result.stdout and "PASSED" in result.stdout, (
            f"Niet alle tests geslaagd.\nOutput:\n{result.stdout}"
        )
