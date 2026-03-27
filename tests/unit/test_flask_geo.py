"""
Unit tests voor de fab_addon_geoalchemy module.

Test PointField, LatLonWidget en GeoSQLAInterface.
"""
import pytest
import sys
import os

_app_path = os.path.join(os.path.dirname(__file__), '..', '..', 'app')
if os.path.abspath(_app_path) not in sys.path:
    sys.path.insert(0, os.path.abspath(_app_path))
_app_app_path = os.path.join(_app_path, 'app')
if os.path.abspath(_app_app_path) not in sys.path:
    sys.path.insert(0, os.path.abspath(_app_app_path))


class TestPointFieldGetPoint:
    """Test PointField._getpoint() — genereert WKT POINT strings."""

    @pytest.fixture
    def point_field(self):
        """Maak een gebonden PointField via een dummy WTForms form."""
        from wtforms import Form
        from fab_addon_geoalchemy.fields import PointField

        class DummyForm(Form):
            location = PointField(srid=4326)

        form = DummyForm()
        return form.location

    @pytest.fixture
    def point_field_rd(self):
        """PointField met Rijksdriehoek SRID."""
        from wtforms import Form
        from fab_addon_geoalchemy.fields import PointField

        class DummyForm(Form):
            location = PointField(srid=28992)

        form = DummyForm()
        return form.location

    def test_valid_coordinates(self, point_field):
        result = point_field._getpoint(52.0067, 4.3556)
        assert result == "SRID=4326;POINT(4.3556 52.0067)"

    def test_none_lat(self, point_field):
        result = point_field._getpoint(None, 4.3556)
        assert result is None

    def test_none_lon(self, point_field):
        result = point_field._getpoint(52.0, None)
        assert result is None

    def test_empty_string_lat(self, point_field):
        result = point_field._getpoint('', 4.3556)
        assert result is None

    def test_empty_string_lon(self, point_field):
        result = point_field._getpoint(52.0, '')
        assert result is None

    def test_custom_srid(self, point_field_rd):
        result = point_field_rd._getpoint(437428, 92565)
        assert "SRID=28992" in result
        assert "POINT(92565 437428)" in result

    def test_zero_coordinates(self, point_field):
        result = point_field._getpoint(0, 0)
        assert result == "SRID=4326;POINT(0 0)"


class TestLatLonWidgetGetROMap:
    """Test LatLonWidget.getROMap() — genereert read-only kaart HTML."""

    def test_with_none_value(self):
        from fab_addon_geoalchemy.widgets import LatLonWidget
        result = LatLonWidget.getROMap(None, "location")
        assert "null" in str(result)
        assert "Latitude" in str(result)
        assert "Longitude" in str(result)

    def test_returns_markup(self):
        from fab_addon_geoalchemy.widgets import LatLonWidget
        from markupsafe import Markup
        result = LatLonWidget.getROMap(None, "location")
        assert isinstance(result, Markup)

    def test_contains_leaflet_map_div(self):
        from fab_addon_geoalchemy.widgets import LatLonWidget
        result = LatLonWidget.getROMap(None, "location")
        assert "leaflet_map" in str(result)
        assert "createROPointMap" in str(result)


class TestGeoSQLAInterfaceIsPoint:
    """Test dat is_point isinstance gebruikt i.p.v. _is_sqla_type."""

    def test_source_uses_isinstance(self):
        """Verifieer dat de source code isinstance gebruikt."""
        import inspect
        from fab_addon_geoalchemy.models import GeoSQLAInterface
        source = inspect.getsource(GeoSQLAInterface.is_point)
        assert 'isinstance' in source
        assert '_is_sqla_type' not in source


class TestGeometryFieldInheritance:
    """Test de GeometryField class hierarchy."""

    def test_point_field_extends_geometry_field(self):
        from fab_addon_geoalchemy.fields import GeometryField, PointField
        assert issubclass(PointField, GeometryField)

    def test_geometry_field_extends_wtforms_field(self):
        from fab_addon_geoalchemy.fields import GeometryField
        from wtforms.fields import Field
        assert issubclass(GeometryField, Field)
