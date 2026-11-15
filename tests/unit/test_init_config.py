"""
Unit tests voor init-config.sh — het genereren van config/*.env.

Draait het script via subprocess in een tijdelijke kopie van de
projectmap, zodat de echte config/*.env bestanden onaangeroerd blijven.
"""
import glob
import os
import re
import shutil
import subprocess

import pytest


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
INIT_SCRIPT = os.path.join(PROJECT_ROOT, "init-config.sh")


def leesEnv(pad):
    """Lees een .env-bestand als dict (alleen regels met NAAM=waarde)."""
    waarden = {}
    with open(pad, encoding="utf-8") as f:
        for regel in f:
            match = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$", regel.strip())
            if match:
                waarden[match.group(1)] = match.group(2)
    return waarden


def draaiInitConfig(map_, *args):
    """Draai init-config.sh in de opgegeven map en geef het resultaat terug."""
    return subprocess.run(
        ["bash", os.path.join(map_, "init-config.sh"), *args],
        capture_output=True,
        text=True,
        timeout=60,
    )


@pytest.fixture
def projectkopie(tmp_path):
    """Tijdelijke map met init-config.sh en alle config/*.env.example bestanden."""
    shutil.copy(INIT_SCRIPT, tmp_path / "init-config.sh")
    (tmp_path / "config").mkdir()
    for example in glob.glob(os.path.join(PROJECT_ROOT, "config", "*.env.example")):
        shutil.copy(example, tmp_path / "config")
    return tmp_path


@pytest.mark.unit
class TestInitConfig:
    """Gegenereerde wachtwoorden in config/*.env."""

    def test_flask_admin_wachtwoord_gegenereerd(self, projectkopie):
        resultaat = draaiInitConfig(str(projectkopie))
        assert resultaat.returncode == 0, resultaat.stderr

        wachtwoord = leesEnv(projectkopie / "config" / "flask.env")["FLASK_ADMIN_PASSWORD"]
        assert re.fullmatch(r"[A-Za-z0-9]{24}", wachtwoord), wachtwoord
        assert f"Flask admin:           {wachtwoord}" in resultaat.stdout

    def test_geen_placeholders_over(self, projectkopie):
        resultaat = draaiInitConfig(str(projectkopie))
        assert resultaat.returncode == 0, resultaat.stderr

        for env in glob.glob(str(projectkopie / "config" / "*.env")):
            with open(env, encoding="utf-8") as f:
                inhoud = f.read()
            assert "_secret_42" not in inhoud, f"Placeholder over in {os.path.basename(env)}"
            assert "wijzig_deze_geheime_sleutel" not in inhoud, os.path.basename(env)

    def test_bestaand_flask_env_blijft_ongewijzigd(self, projectkopie):
        """Zonder --force krijgt een bestaande installatie geen nieuw wachtwoord."""
        draaiInitConfig(str(projectkopie))
        flask_env = projectkopie / "config" / "flask.env"
        voor = flask_env.read_text(encoding="utf-8")

        # Eén ander bestand ontbreekt, zodat het script wel iets doet
        (projectkopie / "config" / "redis.env").unlink()
        resultaat = draaiInitConfig(str(projectkopie))
        assert resultaat.returncode == 0, resultaat.stderr

        assert flask_env.read_text(encoding="utf-8") == voor
        assert (projectkopie / "config" / "redis.env").exists()
