"""
Python wrapper voor de bash integratietests van importMDB.sh.

Draait de volgende bash testscripts via subprocess zodat
pytest (en run_tests.py) ze automatisch meeneemt:
  - test_importMDB_pipeline.sh (metainfo + CSV + encoding pipeline)
  - test_bash_encoding.sh (encoding conversie functie)
"""
import os
import subprocess
import pytest

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(SCRIPT_DIR))
PIPELINE_SCRIPT = os.path.join(SCRIPT_DIR, "test_importMDB_pipeline.sh")
ENCODING_SCRIPT = os.path.join(SCRIPT_DIR, "test_bash_encoding.sh")
IMPORT_SCRIPT = os.path.join(PROJECT_ROOT, "airflow_app", "scripts", "importMDB.sh")


@pytest.mark.integration
class TestImportMDBPipeline:
    """Draait de bash integratietests voor de importMDB pipeline."""

    def test_pipeline_script_exists(self):
        assert os.path.isfile(PIPELINE_SCRIPT), (
            f"Bash test script niet gevonden: {PIPELINE_SCRIPT}"
        )

    def test_importMDB_pipeline_integration(self):
        """Draait test_importMDB_pipeline.sh en controleert exit code."""
        result = subprocess.run(
            ["bash", PIPELINE_SCRIPT],
            capture_output=True,
            text=True,
            timeout=120,
            cwd=PROJECT_ROOT,
        )
        if result.returncode != 0:
            print("=== STDOUT ===")
            print(result.stdout)
            print("=== STDERR ===")
            print(result.stderr)
        assert result.returncode == 0, (
            f"Pipeline integratietests gefaald (exit {result.returncode}).\n"
            f"Output:\n{result.stdout}\n{result.stderr}"
        )

    def test_pipeline_all_pass(self):
        """Controleert dat de output 'ALL ... TESTS PASSED' bevat."""
        result = subprocess.run(
            ["bash", PIPELINE_SCRIPT],
            capture_output=True,
            text=True,
            timeout=120,
            cwd=PROJECT_ROOT,
        )
        assert "ALL" in result.stdout and "PASSED" in result.stdout, (
            f"Niet alle pipeline tests geslaagd.\nOutput:\n{result.stdout}"
        )


@pytest.mark.integration
class TestBashEncoding:
    """Draait de bestaande bash encoding-tests."""

    def test_encoding_script_exists(self):
        assert os.path.isfile(ENCODING_SCRIPT), (
            f"Bash test script niet gevonden: {ENCODING_SCRIPT}"
        )

    def test_bash_encoding_integration(self):
        """Draait test_bash_encoding.sh en controleert exit code."""
        result = subprocess.run(
            ["bash", ENCODING_SCRIPT],
            capture_output=True,
            text=True,
            timeout=120,
            cwd=PROJECT_ROOT,
        )
        if result.returncode != 0:
            print("=== STDOUT ===")
            print(result.stdout)
            print("=== STDERR ===")
            print(result.stderr)
        assert result.returncode == 0, (
            f"Bash encoding tests gefaald (exit {result.returncode}).\n"
            f"Output:\n{result.stdout}\n{result.stderr}"
        )
