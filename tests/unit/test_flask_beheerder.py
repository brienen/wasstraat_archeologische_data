"""
Unit tests voor app/app/beheerder.py — het aanmaken van de Flask-beheerder.

Gebruikt een nep-security manager in plaats van Flask-AppBuilder, zodat er
geen database nodig is.
"""
import importlib.util
import os
import re
from types import SimpleNamespace

import pytest
from werkzeug.security import generate_password_hash


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
BEHEERDER_PAD = os.path.join(PROJECT_ROOT, "app", "app", "beheerder.py")
FLASK_ENV_EXAMPLE = os.path.join(PROJECT_ROOT, "config", "flask.env.example")

_spec = importlib.util.spec_from_file_location("beheerder", BEHEERDER_PAD)
beheerder = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(beheerder)


class NepSecurityManager:
    """Minimale vervanger van appbuilder.sm voor find_user/find_role/add_user."""

    def __init__(self, bestaand_wachtwoord=None, aanmaken_lukt=True):
        self.gebruiker = None
        if bestaand_wachtwoord is not None:
            self.gebruiker = SimpleNamespace(
                username="admin",
                password=generate_password_hash(bestaand_wachtwoord),
            )
        self.aanmaken_lukt = aanmaken_lukt
        self.toegevoegd = []

    def find_user(self, username=None):
        if self.gebruiker and self.gebruiker.username == username:
            return self.gebruiker
        return None

    def find_role(self, naam):
        return f"rol:{naam}"

    def add_user(self, **kwargs):
        self.toegevoegd.append(kwargs)
        return SimpleNamespace(**kwargs) if self.aanmaken_lukt else False


@pytest.mark.unit
class TestBepaalWachtwoord:
    """Wachtwoordkeuze voor een nieuwe beheerder."""

    def test_wachtwoord_uit_omgeving(self, capsys):
        assert beheerder.bepaalWachtwoord({"FLASK_ADMIN_PASSWORD": "Geheim123"}) == "Geheim123"
        assert "WAARSCHUWING" not in capsys.readouterr().out

    @pytest.mark.parametrize("omgeving", [
        {},
        {"FLASK_ADMIN_PASSWORD": ""},
        {"FLASK_ADMIN_PASSWORD": "   "},
    ])
    def test_ontbrekend_valt_terug_op_admin_met_waarschuwing(self, omgeving, capsys):
        assert beheerder.bepaalWachtwoord(omgeving) == "admin"
        uitvoer = capsys.readouterr().out
        assert "WAARSCHUWING" in uitvoer
        assert "FLASK_ADMIN_PASSWORD" in uitvoer

    def test_placeholder_geeft_waarschuwing(self, capsys):
        omgeving = {"FLASK_ADMIN_PASSWORD": beheerder.PLACEHOLDER_WACHTWOORD}
        assert beheerder.bepaalWachtwoord(omgeving) == beheerder.PLACEHOLDER_WACHTWOORD
        assert "WAARSCHUWING" in capsys.readouterr().out

    def test_placeholder_gelijk_aan_flask_env_example(self):
        """init-config.sh vervangt de placeholder uit flask.env.example; die moet gelijk zijn."""
        with open(FLASK_ENV_EXAMPLE, encoding="utf-8") as f:
            inhoud = f.read()
        match = re.search(r"^FLASK_ADMIN_PASSWORD=(.*)$", inhoud, re.MULTILINE)
        assert match, "FLASK_ADMIN_PASSWORD ontbreekt in config/flask.env.example"
        assert match.group(1).strip() == beheerder.PLACEHOLDER_WACHTWOORD


@pytest.mark.unit
class TestMaakBeheerder:
    """Aanmaken van de beheerder en gedrag bij een bestaande beheerder."""

    def test_maakt_beheerder_met_wachtwoord_uit_omgeving(self):
        sm = NepSecurityManager()
        assert beheerder.maakBeheerder(sm, {"FLASK_ADMIN_PASSWORD": "Geheim123"}) is True
        assert len(sm.toegevoegd) == 1
        assert sm.toegevoegd[0]["username"] == "admin"
        assert sm.toegevoegd[0]["password"] == "Geheim123"
        assert sm.toegevoegd[0]["role"] == "rol:Admin"

    def test_zonder_variabele_oud_gedrag_met_waarschuwing(self, capsys):
        sm = NepSecurityManager()
        assert beheerder.maakBeheerder(sm, {}) is True
        assert sm.toegevoegd[0]["password"] == "admin"
        assert "WAARSCHUWING" in capsys.readouterr().out

    def test_bestaande_beheerder_wordt_niet_gewijzigd(self, capsys):
        sm = NepSecurityManager(bestaand_wachtwoord="OudWachtwoord")
        assert beheerder.maakBeheerder(sm, {"FLASK_ADMIN_PASSWORD": "NieuwWachtwoord"}) is False
        assert sm.toegevoegd == []
        assert "bestaat al" in capsys.readouterr().out

    def test_afwijkend_wachtwoord_bestaande_beheerder_staat_in_log(self, capsys):
        sm = NepSecurityManager(bestaand_wachtwoord="OudWachtwoord")
        beheerder.maakBeheerder(sm, {"FLASK_ADMIN_PASSWORD": "NieuwWachtwoord"})
        assert "wijkt af" in capsys.readouterr().out

    def test_gelijk_wachtwoord_bestaande_beheerder_geen_melding(self, capsys):
        sm = NepSecurityManager(bestaand_wachtwoord="Geheim123")
        beheerder.maakBeheerder(sm, {"FLASK_ADMIN_PASSWORD": "Geheim123"})
        assert "wijkt af" not in capsys.readouterr().out

    def test_bestaande_beheerder_zonder_variabele_geen_waarschuwing(self, capsys):
        """Oude installatie met bestaande beheerder: geen terugval en geen melding."""
        sm = NepSecurityManager(bestaand_wachtwoord="admin")
        assert beheerder.maakBeheerder(sm, {}) is False
        uitvoer = capsys.readouterr().out
        assert "WAARSCHUWING" not in uitvoer
        assert "wijkt af" not in uitvoer

    def test_mislukt_aanmaken_geeft_fout(self, capsys):
        sm = NepSecurityManager(aanmaken_lukt=False)
        assert beheerder.maakBeheerder(sm, {"FLASK_ADMIN_PASSWORD": "Geheim123"}) is False
        assert "FOUT" in capsys.readouterr().out
