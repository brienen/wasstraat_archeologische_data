"""
Unit tests voor de synthetische data generator.

Test de data-integriteit en structuur ZONDER Java-dependency.
De tests valideren de Python data-dicts, niet de MDB-bestanden zelf.
"""
import pytest
import sys
import os

# Voeg data/synthetic/generatie toe aan het pad zodat we de generator kunnen importeren
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "data", "synthetic", "generatie"))

# msaccessdb is een optionele Java-dependency; skip alle tests als die ontbreekt
msaccessdb = pytest.importorskip("msaccessdb", reason="msaccessdb (Java) niet beschikbaar")

from generate_synthetic_data import (
    getAlleScenarioData,
    dataKleinProject,
    dataGrootProject,
    dataProjectenlijst,
    dataMagazijnlijst,
    dataDigifotos,
    KOLOMMEN_VONDSTENLIJST,
    KOLOMMEN_SPOREN,
    KOLOMMEN_VULLINGEN,
    KOLOMMEN_AARDEWERK,
    KOLOMMEN_GLAS,
    KOLOMMEN_BEEN,
    KOLOMMEN_METAAL,
    KOLOMMEN_LEER,
    KOLOMMEN_STEEN,
    KOLOMMEN_KLEIPIJPEN,
    KOLOMMEN_MUNTEN,
    KOLOMMEN_TEKENINGEN,
    KOLOMMEN_DIAOPGRAVING,
    KOLOMMEN_OPGRAVINGEN,
    KOLOMMEN_MAGAZIJNLIJST,
    KOLOMMEN_DIGIFOTOS,
)


# ============================================================
# Testdata ophalen
# ============================================================

@pytest.fixture(scope="module")
def klein_project():
    return dataKleinProject()


@pytest.fixture(scope="module")
def groot_project():
    return dataGrootProject()


@pytest.fixture(scope="module")
def projectenlijst():
    return dataProjectenlijst()


@pytest.fixture(scope="module")
def magazijnlijst():
    return dataMagazijnlijst()


@pytest.fixture(scope="module")
def digifotos():
    return dataDigifotos()


# ============================================================
# Tests: Scenario SY001 (klein project)
# ============================================================

@pytest.mark.unit
class TestKleinProjectStructuur:
    """Test de structuur van het kleine project SY001."""

    def test_verwachte_tabellen_aanwezig(self, klein_project):
        """SY001 moet minimaal vondstenlijst, sporen en aardewerk bevatten."""
        verwacht = {"VONDSTENLIJST", "SPOREN", "VULLINGEN", "AARDEWERK 1", "GLAS"}
        assert verwacht.issubset(set(klein_project.keys()))

    def test_vondstenlijst_aantal(self, klein_project):
        """SY001 moet 4 vondsten bevatten."""
        _, records = klein_project["VONDSTENLIJST"]
        assert len(records) == 4

    def test_sporen_aantal(self, klein_project):
        """SY001 moet 3 sporen bevatten."""
        _, records = klein_project["SPOREN"]
        assert len(records) == 3

    def test_aardewerk_aantal(self, klein_project):
        """SY001 moet 3 aardewerk-artefacten bevatten."""
        _, records = klein_project["AARDEWERK 1"]
        assert len(records) == 3

    def test_glas_aantal(self, klein_project):
        """SY001 moet 2 glas-artefacten bevatten."""
        _, records = klein_project["GLAS"]
        assert len(records) == 2


@pytest.mark.unit
class TestKleinProjectKolomAantal:
    """Test dat het aantal waarden per record overeenkomt met het aantal kolommen."""

    @pytest.mark.parametrize("tabelnaam,kolom_def", [
        ("VONDSTENLIJST", KOLOMMEN_VONDSTENLIJST),
        ("SPOREN", KOLOMMEN_SPOREN),
        ("VULLINGEN", KOLOMMEN_VULLINGEN),
        ("AARDEWERK 1", KOLOMMEN_AARDEWERK),
        ("GLAS", KOLOMMEN_GLAS),
        ("TEKENINGEN", KOLOMMEN_TEKENINGEN),
        ("DIAOPGRAVING", KOLOMMEN_DIAOPGRAVING),
    ])
    def test_kolom_aantal_klopt(self, klein_project, tabelnaam, kolom_def):
        """Elk record moet evenveel waarden hebben als er kolommen gedefinieerd zijn."""
        kolommen, records = klein_project[tabelnaam]
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
# Tests: Scenario SY002 (groot project)
# ============================================================

@pytest.mark.unit
class TestGrootProjectStructuur:
    """Test de structuur van het grote project SY002."""

    def test_verwachte_tabellen_aanwezig(self, groot_project):
        """SY002 moet alle artefacttabellen bevatten."""
        verwacht = {
            "VONDSTENLIJST", "SPOREN", "VULLINGEN",
            "AARDEWERK 1", "GLAS", "BEEN", "METAAL",
            "LEER", "STEEN", "KLEIPIJPEN", "MUNTEN EN PENNINGEN",
        }
        assert verwacht.issubset(set(groot_project.keys()))

    def test_vondstenlijst_aantal(self, groot_project):
        """SY002 moet 12 vondsten bevatten."""
        _, records = groot_project["VONDSTENLIJST"]
        assert len(records) == 12

    def test_sporen_aantal(self, groot_project):
        """SY002 moet 8 sporen bevatten."""
        _, records = groot_project["SPOREN"]
        assert len(records) == 8

    def test_meer_artefacttypen_dan_sy001(self, groot_project, klein_project):
        """SY002 moet meer artefacttypen bevatten dan SY001."""
        assert len(groot_project) > len(klein_project)


@pytest.mark.unit
class TestGrootProjectKolomAantal:
    """Test kolomaantallen voor alle tabellen in SY002."""

    @pytest.mark.parametrize("tabelnaam,kolom_def", [
        ("VONDSTENLIJST", KOLOMMEN_VONDSTENLIJST),
        ("SPOREN", KOLOMMEN_SPOREN),
        ("VULLINGEN", KOLOMMEN_VULLINGEN),
        ("AARDEWERK 1", KOLOMMEN_AARDEWERK),
        ("GLAS", KOLOMMEN_GLAS),
        ("BEEN", KOLOMMEN_BEEN),
        ("METAAL", KOLOMMEN_METAAL),
        ("LEER", KOLOMMEN_LEER),
        ("STEEN", KOLOMMEN_STEEN),
        ("KLEIPIJPEN", KOLOMMEN_KLEIPIJPEN),
        ("MUNTEN EN PENNINGEN", KOLOMMEN_MUNTEN),
        ("TEKENINGEN", KOLOMMEN_TEKENINGEN),
        ("DIAOPGRAVING", KOLOMMEN_DIAOPGRAVING),
    ])
    def test_kolom_aantal_klopt(self, groot_project, tabelnaam, kolom_def):
        """Elk record moet evenveel waarden hebben als er kolommen gedefinieerd zijn."""
        kolommen, records = groot_project[tabelnaam]
        verwacht_aantal = len(kolom_def)
        assert len(kolommen) == verwacht_aantal
        for i, record in enumerate(records):
            assert len(record) == verwacht_aantal, (
                f"Tabel {tabelnaam}, record {i}: verwachtte {verwacht_aantal} waarden, "
                f"maar kreeg {len(record)}"
            )


# ============================================================
# Tests: Referentiële integriteit
# ============================================================

@pytest.mark.unit
class TestReferentieleIntegriteit:
    """Test dat vondsten verwijzen naar bestaande sporen, etc."""

    def test_vondsten_verwijzen_naar_bestaande_sporen_sy001(self, klein_project):
        """Elke vondst in SY001 moet verwijzen naar een bestaand spoornummer."""
        _, sporen = klein_project["SPOREN"]
        spoor_nrs = {r[3] for r in sporen}  # SPOORNO is kolom index 3
        _, vondsten = klein_project["VONDSTENLIJST"]
        for vondst in vondsten:
            spoornr = vondst[4]  # SPOORNO is kolom index 4
            assert spoornr in spoor_nrs, (
                f"Vondst verwijst naar spoor {spoornr}, "
                f"maar dat bestaat niet. Bestaande sporen: {spoor_nrs}"
            )

    def test_vondsten_verwijzen_naar_bestaande_sporen_sy002(self, groot_project):
        """Elke vondst in SY002 moet verwijzen naar een bestaand spoornummer."""
        _, sporen = groot_project["SPOREN"]
        spoor_nrs = {r[3] for r in sporen}  # SPOORNO
        _, vondsten = groot_project["VONDSTENLIJST"]
        for vondst in vondsten:
            spoornr = vondst[4]  # SPOORNO
            assert spoornr in spoor_nrs

    def test_aardewerk_verwijst_naar_bestaande_vondsten(self, groot_project):
        """Elk aardewerk-record moet verwijzen naar een bestaand vondstnummer."""
        _, vondsten = groot_project["VONDSTENLIJST"]
        vondst_nrs = {r[3] for r in vondsten}  # VONDSTNO
        _, aardewerk = groot_project["AARDEWERK 1"]
        for aw in aardewerk:
            vondstno = aw[2]  # VONDSTNO
            assert vondstno in vondst_nrs


# ============================================================
# Tests: Projectcodes en coördinaten
# ============================================================

@pytest.mark.unit
class TestProjectcodesEnLocatie:
    """Test dat projectcodes correct zijn en locaties niet in Delft liggen."""

    def test_projectcodes_sy_prefix(self):
        """Alle projectcodes moeten SY-prefix hebben."""
        data = getAlleScenarioData()
        sy001 = data["SY001"]
        _, vondsten = sy001["VONDSTENLIJST"]
        for v in vondsten:
            assert v[0].startswith("SY"), f"Projectcode {v[0]} heeft geen SY-prefix"

    def test_coordinaten_in_delft(self, projectenlijst):
        """Coördinaten moeten in Delft liggen (rond 84500, 447500)."""
        _, records = projectenlijst["OPGRAVINGEN"]
        for record in records:
            x = record[5]  # XCOORD
            y = record[6]  # YCOORD
            # Delft ligt rond X=84000-85000, Y=447000-448000
            assert 83000 <= x <= 86000, (
                f"X-coördinaat {x} ligt niet in Delft (verwacht 83000-86000)"
            )
            assert 446000 <= y <= 449000, (
                f"Y-coördinaat {y} ligt niet in Delft (verwacht 446000-449000)"
            )

    def test_twee_projecten_in_projectenlijst(self, projectenlijst):
        """De projectenlijst moet precies 2 projecten bevatten."""
        _, records = projectenlijst["OPGRAVINGEN"]
        assert len(records) == 2


# ============================================================
# Tests: Magazijnlijst en Digifotos
# ============================================================

@pytest.mark.unit
class TestMagazijnlijst:
    """Test de magazijnlijst data."""

    def test_magazijn_records_aanwezig(self, magazijnlijst):
        """De magazijnlijst moet records bevatten."""
        _, records = magazijnlijst["magazijnlijst"]
        assert len(records) >= 2

    def test_magazijn_kolom_aantal(self, magazijnlijst):
        """Magazijnlijst records moeten het juiste aantal kolommen hebben."""
        kolommen, records = magazijnlijst["magazijnlijst"]
        verwacht = len(KOLOMMEN_MAGAZIJNLIJST)
        assert len(kolommen) == verwacht
        for record in records:
            assert len(record) == verwacht


@pytest.mark.unit
class TestDigifotos:
    """Test de digitale fotocatalogus data."""

    def test_digifotos_records_aanwezig(self, digifotos):
        """De fotocatalogus moet records bevatten."""
        _, records = digifotos["Fotos"]
        assert len(records) >= 3

    def test_fotos_bevatten_beide_projecten(self, digifotos):
        """Foto's moeten verwijzen naar zowel SY001 als SY002."""
        _, records = digifotos["Fotos"]
        projectcodes = {r[1] for r in records}  # PROJECTCD
        assert "SY001" in projectcodes
        assert "SY002" in projectcodes

    def test_digifotos_kolom_aantal(self, digifotos):
        """Digifotos records moeten het juiste aantal kolommen hebben."""
        kolommen, records = digifotos["Fotos"]
        verwacht = len(KOLOMMEN_DIGIFOTOS)
        assert len(kolommen) == verwacht
        for record in records:
            assert len(record) == verwacht
