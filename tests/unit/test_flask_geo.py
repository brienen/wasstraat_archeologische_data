"""
Unit tests voor de fab_addon_geoalchemy module.

Test PointField, LatLonWidget en GeoSQLAInterface.
"""
import os
import sys
from types import SimpleNamespace

import pytest

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


class TestPointFieldFormulier:
    """Issue 27: een project zonder locatie aanmaken, of de locatie bij bewerken leegmaken.

    Het formulier van Flask-AppBuilder krijgt voor de kolom location een PointField met de
    validator Optional (de kolom mag leeg zijn), zie GeoModelConverter in
    fab_addon_geoalchemy/views.py.
    """

    def maakFormulier(self, formdata=None, obj=None):
        from werkzeug.datastructures import MultiDict
        from wtforms import Form, validators
        from fab_addon_geoalchemy.fields import PointField

        class ProjectFormulier(Form):
            location = PointField(srid=4326, validators=[validators.Optional()])

        return ProjectFormulier(MultiDict(formdata) if formdata is not None else None, obj=obj)

    def test_lege_coordinaten_geven_geen_locatie(self):
        form = self.maakFormulier({'location_lat': '', 'location_lon': ''})
        assert form.validate(), form.errors
        assert form.location.data is None

    def test_zonder_locatievelden_geen_locatie(self):
        form = self.maakFormulier({'projectcd': 'ZZ027'})
        assert form.validate(), form.errors
        assert form.location.data is None

    def test_alleen_breedtegraad_geeft_geen_locatie(self):
        form = self.maakFormulier({'location_lat': '52.0116', 'location_lon': ''})
        assert form.validate(), form.errors
        assert form.location.data is None

    def test_coordinaten_geven_ewkt(self):
        form = self.maakFormulier({'location_lat': '52.0116', 'location_lon': '4.3571'})
        assert form.validate(), form.errors
        assert form.location.data == 'SRID=4326;POINT(4.3571 52.0116)'

    def test_leeg_formulier_toont_lege_invoervelden(self):
        html = str(self.maakFormulier()['location']())
        assert 'name="location_lat"' in html and 'name="location_lon"' in html
        assert 'value=' not in html

    def test_bewerken_toont_bestaande_locatie(self):
        from geoalchemy2.shape import from_shape
        from shapely.geometry import Point
        project = SimpleNamespace(location=from_shape(Point(4.3571, 52.0116), srid=4326))
        form = self.maakFormulier(obj=project)
        assert (form.location.lat, form.location.lon) == (52.0116, 4.3571)
        assert 'value="52.0116"' in str(form.location())

    def test_bewerken_locatie_leegmaken(self):
        from geoalchemy2.shape import from_shape
        from shapely.geometry import Point
        project = SimpleNamespace(location=from_shape(Point(4.3571, 52.0116), srid=4326))
        form = self.maakFormulier({'location_lat': '', 'location_lon': ''}, obj=project)
        assert form.validate(), form.errors
        form.populate_obj(project)
        assert project.location is None

    def test_bewerken_project_zonder_locatie(self):
        project = SimpleNamespace(location=None)
        form = self.maakFormulier(obj=project)
        assert form.location.data is None
        assert 'value=' not in str(form.location())


class TestProjectLocatieKolom:
    """Issue 27: de oorzaak van de fout was een standaardwaarde op Project.location.

    Tot maart 2026 (commit b48f1c3) had de kolom default=(52.00667, 4.35556). SQLAlchemy laat
    een kolom die None is weg uit de INSERT als er een standaardwaarde is, dus een project
    zonder locatie kreeg de tuple als waarde. Die kwam in ST_GeomFromEWKT terecht
    ('function st_geomfromewkt(record) does not exist') en het opslaan mislukte.
    """

    def test_locatie_optioneel_zonder_standaardwaarde(self):
        from models import Project
        kolom = Project.__table__.c.location
        assert kolom.nullable
        assert kolom.default is None
        assert kolom.server_default is None

    def test_locatie_is_punt_in_wgs84(self):
        from models import Project
        kolom = Project.__table__.c.location
        assert kolom.type.geometry_type == 'POINT'
        assert kolom.type.srid == 4326
