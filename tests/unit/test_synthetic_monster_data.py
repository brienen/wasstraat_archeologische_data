"""
Unit tests voor de synthetische monsterdata.

Test de data-integriteit en structuur van de monsterdatabase-data
ZONDER Java-dependency. De tests valideren de Python data-dicts,
niet de MDB-bestanden zelf.
"""
import pytest
import sys
import os
import types

# Voeg data/synthetic/generatie toe aan het pad zodat we de generator kunnen importeren
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "data", "synthetic", "generatie"))

# Mock msaccessdb zodat generate_synthetic_data kan importeren zonder Java
if "msaccessdb" not in sys.modules:
    sys.modules["msaccessdb"] = types.ModuleType("msaccessdb")

from generate_synthetic_data import (
    dataMonsterDatabase,
    KOLOMMEN_MONSTER_GEGEVENS,
    KOLOMMEN_MONSTER_WAARDERING,
    KOLOMMEN_MONSTER_BOTANIE,
    KOLOMMEN_MONSTER_SCHELP,
    KOLOMMEN_R_PLANT,
    KOLOMMEN_R_SCHELP,
    KOLOMMEN_R_DEEL,
    KOLOMMEN_R_STAAT,
)


# ============================================================
# Testdata ophalen
# ============================================================

@pytest.fixture(scope="module")
def monster_data():
    return dataMonsterDatabase()


# ============================================================
# Tests: Tabelstructuur
# ============================================================

@pytest.mark.unit
class TestMonsterGegevensStructuur:
    """Test de structuur van de monsterdatabase tabellen."""

    def test_verwachte_tabellen_aanwezig(self, monster_data):
        """Monsterdatabase moet alle verwachte tabellen bevatten."""
        verwacht = {
            "Monster_gegevens",
            "Monster_waardering",
            "Monster_botanie_determinatie",
            "Monster_schelp_determinatie",
            "R_PLANT",
            "R_SCHELP",
            "R_DEEL",
            "R_STAAT",
        }
        assert verwacht.issubset(set(monster_data.keys())), (
            f"Ontbrekende tabellen: {verwacht - set(monster_data.keys())}"
        )

    def test_monster_gegevens_aantal(self, monster_data):
        """Monster_gegevens moet 6 records bevatten (3x SY001, 2x SY002, 1x SYNTFOUT testgeval)."""
        _, records = monster_data["Monster_gegevens"]
        assert len(records) == 6

    def test_monster_waardering_aantal(self, monster_data):
        """Monster_waardering moet 5 records bevatten (1:1 met gegevens)."""
        _, records = monster_data["Monster_waardering"]
        assert len(records) == 5

    def test_botanie_determinatie_aantal(self, monster_data):
        """Monster_botanie_determinatie moet 8 records bevatten."""
        _, records = monster_data["Monster_botanie_determinatie"]
        assert len(records) == 8

    def test_schelp_determinatie_aantal(self, monster_data):
        """Monster_schelp_determinatie moet 4 records bevatten."""
        _, records = monster_data["Monster_schelp_determinatie"]
        assert len(records) == 4

    def test_r_plant_aantal(self, monster_data):
        """R_PLANT moet 5 plantensoorten bevatten."""
        _, records = monster_data["R_PLANT"]
        assert len(records) == 5

    def test_r_schelp_aantal(self, monster_data):
        """R_SCHELP moet 3 schelpsoorten bevatten."""
        _, records = monster_data["R_SCHELP"]
        assert len(records) == 3

    def test_r_deel_aantal(self, monster_data):
        """R_DEEL moet 4 deel-typen bevatten."""
        _, records = monster_data["R_DEEL"]
        assert len(records) == 4

    def test_r_staat_aantal(self, monster_data):
        """R_STAAT moet 4 staat-typen bevatten."""
        _, records = monster_data["R_STAAT"]
        assert len(records) == 4


# ============================================================
# Tests: Kolomaantallen
# ============================================================

@pytest.mark.unit
class TestMonsterKolomAantal:
    """Test dat het aantal waarden per record overeenkomt met het aantal kolommen."""

    @pytest.mark.parametrize("tabelnaam,kolom_def", [
        ("Monster_gegevens", KOLOMMEN_MONSTER_GEGEVENS),
        ("Monster_waardering", KOLOMMEN_MONSTER_WAARDERING),
        ("Monster_botanie_determinatie", KOLOMMEN_MONSTER_BOTANIE),
        ("Monster_schelp_determinatie", KOLOMMEN_MONSTER_SCHELP),
        ("R_PLANT", KOLOMMEN_R_PLANT),
        ("R_SCHELP", KOLOMMEN_R_SCHELP),
        ("R_DEEL", KOLOMMEN_R_DEEL),
        ("R_STAAT", KOLOMMEN_R_STAAT),
    ])
    def test_kolom_aantal_klopt(self, monster_data, tabelnaam, kolom_def):
        """Elk record moet evenveel waarden hebben als er kolommen gedefinieerd zijn."""
        kolommen, records = monster_data[tabelnaam]
        verwacht_aantal = len(kolom_def)
        assert len(kolommen) == verwacht_aantal, (
            f"Tabel {tabelnaam}: verwachtte {verwacht_aantal} kolomnamen, "
            f"maar kreeg {len(kolommen)}"
        )
        for i, record in enumerate(records):
            assert len(record) == verwacht_aantal, (
                f"Tabel {tabelnaam}, record {i}: verwachtte {verwacht_aantal} waarden, "
                f"maar kreeg {len(record)}"
            )


# ============================================================
# Tests: Referentiële integriteit
# ============================================================

@pytest.mark.unit
class TestMonsterReferentieleIntegriteit:
    """Test dat verwijzingen tussen monstertabellen kloppen."""

    def test_botanie_verwijst_naar_bestaande_monsters(self, monster_data):
        """Elke botanische determinatie moet verwijzen naar een bestaande monstercode."""
        _, gegevens = monster_data["Monster_gegevens"]
        monstercodes = {r[3] for r in gegevens}  # MONSTERCODE is kolom index 3
        _, botanie = monster_data["Monster_botanie_determinatie"]
        for record in botanie:
            monstercode = record[0]  # MONSTERCODE is kolom index 0
            assert monstercode in monstercodes, (
                f"Botanische determinatie verwijst naar monster '{monstercode}', "
                f"maar dat bestaat niet. Bestaande monstercodes: {monstercodes}"
            )

    def test_schelp_verwijst_naar_bestaande_monsters(self, monster_data):
        """Elke schelpdeterminatie moet verwijzen naar een bestaande monstercode."""
        _, gegevens = monster_data["Monster_gegevens"]
        monstercodes = {r[3] for r in gegevens}  # MONSTERCODE
        _, schelp = monster_data["Monster_schelp_determinatie"]
        for record in schelp:
            monstercode = record[0]  # MONSTERCODE
            assert monstercode in monstercodes, (
                f"Schelpdeterminatie verwijst naar monster '{monstercode}', "
                f"maar dat bestaat niet. Bestaande monstercodes: {monstercodes}"
            )

    def test_waardering_verwijst_naar_bestaande_monsters(self, monster_data):
        """Elke waardering moet verwijzen naar een bestaande monstercode."""
        _, gegevens = monster_data["Monster_gegevens"]
        monstercodes = {r[3] for r in gegevens}  # MONSTERCODE
        _, waardering = monster_data["Monster_waardering"]
        for record in waardering:
            monstercode = record[0]  # MONSTERCODE
            assert monstercode in monstercodes, (
                f"Waardering verwijst naar monster '{monstercode}', "
                f"maar dat bestaat niet."
            )

    def test_botanie_soort_verwijst_naar_r_plant(self, monster_data):
        """Elke botanische SOORT moet voorkomen in R_PLANT."""
        _, r_plant = monster_data["R_PLANT"]
        plant_codes = {r[0] for r in r_plant}  # SPEC is kolom index 0
        _, botanie = monster_data["Monster_botanie_determinatie"]
        for record in botanie:
            soort = record[1]  # SOORT is kolom index 1
            assert soort in plant_codes, (
                f"Botanische soort '{soort}' niet gevonden in R_PLANT. "
                f"Beschikbare soorten: {plant_codes}"
            )

    def test_botanie_deel_verwijst_naar_r_deel(self, monster_data):
        """Elk botanisch DEEL moet voorkomen in R_DEEL."""
        _, r_deel = monster_data["R_DEEL"]
        deel_codes = {r[0] for r in r_deel}  # DEEL is kolom index 0
        _, botanie = monster_data["Monster_botanie_determinatie"]
        for record in botanie:
            deel = record[2]  # DEEL is kolom index 2
            assert deel in deel_codes, (
                f"Deel '{deel}' niet gevonden in R_DEEL. "
                f"Beschikbare delen: {deel_codes}"
            )

    def test_botanie_staat_verwijst_naar_r_staat(self, monster_data):
        """Elke botanische STAAT moet voorkomen in R_STAAT."""
        _, r_staat = monster_data["R_STAAT"]
        staat_codes = {r[0] for r in r_staat}  # STAAT is kolom index 0
        _, botanie = monster_data["Monster_botanie_determinatie"]
        for record in botanie:
            staat = record[3]  # STAAT is kolom index 3
            assert staat in staat_codes, (
                f"Staat '{staat}' niet gevonden in R_STAAT. "
                f"Beschikbare staten: {staat_codes}"
            )

    def test_schelp_soort_verwijst_naar_r_schelp(self, monster_data):
        """Elke schelp-SOORT moet voorkomen in R_SCHELP (latijnse naam)."""
        _, r_schelp = monster_data["R_SCHELP"]
        schelp_namen = {r[1] for r in r_schelp}  # NAAM LATIJN is kolom index 1
        _, schelp = monster_data["Monster_schelp_determinatie"]
        for record in schelp:
            soort = record[1]  # SOORT is kolom index 1
            assert soort in schelp_namen, (
                f"Schelpsoort '{soort}' niet gevonden in R_SCHELP. "
                f"Beschikbare soorten: {schelp_namen}"
            )


# ============================================================
# Tests: Projectverwijzingen en monstercodes
# ============================================================

@pytest.mark.unit
class TestMonsterProjectVerwijzingen:
    """Test dat monsters correct verwijzen naar synthetische projecten."""

    def test_monstercodes_bevatten_projectprefix(self, monster_data):
        """Elke monstercode moet het projectcode-prefix bevatten."""
        _, gegevens = monster_data["Monster_gegevens"]
        for record in gegevens:
            project = record[0]   # PROJECT is kolom index 0
            monstercode = record[3]  # MONSTERCODE is kolom index 3
            assert monstercode.startswith(project), (
                f"Monstercode '{monstercode}' begint niet met project '{project}'"
            )

    def test_projectcodes_zijn_sy_prefix(self, monster_data):
        """Alle projectcodes moeten SY-prefix hebben (synthetische data)."""
        _, gegevens = monster_data["Monster_gegevens"]
        for record in gegevens:
            project = record[0]  # PROJECT
            assert project.startswith("SY"), (
                f"Projectcode '{project}' heeft geen SY-prefix"
            )

    def test_beide_projecten_vertegenwoordigd(self, monster_data):
        """Monsters moeten van zowel SY001 als SY002 komen."""
        _, gegevens = monster_data["Monster_gegevens"]
        projecten = {r[0] for r in gegevens}
        assert "SY001" in projecten, "Geen monsters voor SY001"
        assert "SY002" in projecten, "Geen monsters voor SY002"

    def test_monstercodes_uniek(self, monster_data):
        """Alle monstercodes moeten uniek zijn."""
        _, gegevens = monster_data["Monster_gegevens"]
        monstercodes = [r[3] for r in gegevens]
        assert len(monstercodes) == len(set(monstercodes)), (
            f"Dubbele monstercodes gevonden: "
            f"{[mc for mc in monstercodes if monstercodes.count(mc) > 1]}"
        )

    def test_monsters_hebben_geldige_doosno(self, monster_data):
        """Elk monster moet een geldig doosnummer hebben (> 0)."""
        _, gegevens = monster_data["Monster_gegevens"]
        for record in gegevens:
            doosno = record[7]  # DOOSNO is kolom index 7
            assert doosno is not None and doosno > 0, (
                f"Monster '{record[3]}' heeft ongeldig doosnr: {doosno}"
            )
