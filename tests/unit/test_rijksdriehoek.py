"""
Unit tests voor wasstraat/rijksdriehoek.py

Test de conversie tussen Rijksdriehoek (RD) en WGS84 coördinaten
met bekende referentiepunten uit het bestand zelf.
"""
import pytest
from wasstraat.rijksdriehoek import rd_to_wgs, wgs_to_rd


# Referentiewaarden (uit het bronbestand)
REFERENCE_POINTS = [
    # (rd_x, rd_y, wgs_lat, wgs_lon, plaatsnaam)
    (121687, 487484, 52.37422, 4.89801, "Amsterdam"),
    (92565, 437428, 51.92183, 4.47959, "Rotterdam"),
    (176331, 317462, 50.84660, 5.69006, "Maastricht"),
]

# Delft — nuttig voor de Wasstraat
DELFT_RD = (83500, 449600)
DELFT_WGS_APPROX = (52.03, 4.345)  # bij benadering


class TestRdToWgs:
    """Test RD → WGS84 conversie."""

    @pytest.mark.parametrize("rd_x,rd_y,expected_lat,expected_lon,naam", REFERENCE_POINTS)
    def test_known_cities(self, rd_x, rd_y, expected_lat, expected_lon, naam):
        lat, lon = rd_to_wgs(rd_x, rd_y)
        assert abs(lat - expected_lat) < 0.001, f"{naam}: latitude afwijking te groot"
        assert abs(lon - expected_lon) < 0.001, f"{naam}: longitude afwijking te groot"

    def test_delft_approximate(self):
        lat, lon = rd_to_wgs(*DELFT_RD)
        assert abs(lat - DELFT_WGS_APPROX[0]) < 0.02
        assert abs(lon - DELFT_WGS_APPROX[1]) < 0.02

    def test_tuple_input(self):
        """Functie accepteert ook een tuple als eerste argument."""
        lat, lon = rd_to_wgs((121687, 487484), None)
        assert abs(lat - 52.37422) < 0.001

    def test_returns_list(self):
        result = rd_to_wgs(121687, 487484)
        assert isinstance(result, list)
        assert len(result) == 2


class TestWgsToRd:
    """Test WGS84 → RD conversie."""

    @pytest.mark.parametrize("rd_x,rd_y,wgs_lat,wgs_lon,naam", REFERENCE_POINTS)
    def test_known_cities(self, rd_x, rd_y, wgs_lat, wgs_lon, naam):
        x, y = wgs_to_rd(wgs_lat, wgs_lon)
        assert abs(x - rd_x) < 2, f"{naam}: X afwijking te groot"
        assert abs(y - rd_y) < 2, f"{naam}: Y afwijking te groot"


class TestRoundTrip:
    """Test dat RD → WGS → RD nauwkeurig terugkeert."""

    @pytest.mark.parametrize("rd_x,rd_y,_lat,_lon,naam", REFERENCE_POINTS)
    def test_roundtrip(self, rd_x, rd_y, _lat, _lon, naam):
        lat, lon = rd_to_wgs(rd_x, rd_y)
        x, y = wgs_to_rd(lat, lon)
        assert abs(x - rd_x) < 0.01, f"{naam}: roundtrip X afwijking"
        assert abs(y - rd_y) < 0.01, f"{naam}: roundtrip Y afwijking"
