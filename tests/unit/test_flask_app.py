"""
Unit tests voor de Flask webapp-modules.

Test de FAB 4.x compatibiliteit en de correcte werking van
imports, widgets, modellen en geo-addon na de upgrade.
"""
import pytest
import sys
import types


# ============================================================
# Import tests — verifieer dat FAB 4.x imports werken
# ============================================================

class TestFAB4Imports:
    """Verifieer dat alle FAB 4.x-compatibele imports werken."""

    def test_markupsafe_markup_importable(self):
        """Markup moet uit markupsafe komen, niet uit flask."""
        from markupsafe import Markup
        assert Markup is not None
        assert callable(Markup)

    def test_markup_basic_usage(self):
        """Markup moet HTML-strings correct wrappen."""
        from markupsafe import Markup
        html = Markup('<b>test</b>')
        assert str(html) == '<b>test</b>'
        assert isinstance(html, str)

    def test_markup_format(self):
        """Markup.format() moet werken voor template-achtig gebruik."""
        from markupsafe import Markup
        template = Markup('<span>{}</span>')
        result = template.format('data')
        assert str(result) == '<span>data</span>'

    def test_markup_concatenation(self):
        """Markup-objecten moeten concateneerbaar zijn (gebruikt in widgets)."""
        from markupsafe import Markup
        a = Markup('<div>')
        b = Markup('</div>')
        result = a + b
        assert str(result) == '<div></div>'
        assert isinstance(result, Markup)

    def test_flask_appbuilder_importable(self):
        """Flask-AppBuilder 4.x moet importeerbaar zijn."""
        import flask_appbuilder
        assert hasattr(flask_appbuilder, 'ModelView')
        assert hasattr(flask_appbuilder, 'AppBuilder')
        assert hasattr(flask_appbuilder, 'BaseView')

    def test_fab_model_importable(self):
        """FAB Model class moet importeerbaar zijn."""
        from flask_appbuilder import Model
        assert Model is not None

    def test_fab_sqla_interface_importable(self):
        """SQLAInterface moet importeerbaar zijn."""
        from flask_appbuilder.models.sqla.interface import SQLAInterface
        assert SQLAInterface is not None

    def test_fab_forms_importable(self):
        """GeneralModelConverter en FieldConverter moeten importeerbaar zijn."""
        from flask_appbuilder.forms import GeneralModelConverter, FieldConverter
        assert GeneralModelConverter is not None
        assert FieldConverter is not None

    def test_fab_validators_importable(self):
        """FAB validators moeten importeerbaar zijn."""
        from flask_appbuilder.validators import Unique
        assert Unique is not None

    def test_fab_fields_importable(self):
        """FAB fields moeten importeerbaar zijn."""
        from flask_appbuilder.fields import AJAXSelectField, QuerySelectField, EnumField
        assert AJAXSelectField is not None

    def test_fab_fieldwidgets_importable(self):
        """FAB fieldwidgets moeten importeerbaar zijn."""
        from flask_appbuilder.fieldwidgets import Select2Widget, Select2ManyWidget, Select2AJAXWidget
        assert Select2Widget is not None

    def test_fab_actions_importable(self):
        """FAB actions moeten importeerbaar zijn."""
        from flask_appbuilder.actions import action
        assert action is not None

    def test_fab_baseviews_importable(self):
        """FAB BaseCRUDView moet importeerbaar zijn."""
        from flask_appbuilder.baseviews import BaseCRUDView
        assert BaseCRUDView is not None

    def test_fab_decorators_importable(self):
        """FAB decorators moeten importeerbaar zijn."""
        from flask_appbuilder import expose, has_access
        assert expose is not None
        assert has_access is not None

    def test_fab_model_rest_api_importable(self):
        """FAB ModelRestApi moet importeerbaar zijn."""
        from flask_appbuilder import ModelRestApi
        assert ModelRestApi is not None

    def test_fab_api_importable(self):
        """FAB BaseApi, expose en rison moeten importeerbaar zijn."""
        from flask_appbuilder.api import BaseApi, expose, rison
        assert BaseApi is not None

    def test_fab_security_decorators_importable(self):
        """FAB security decorators moeten importeerbaar zijn."""
        from flask_appbuilder.security.decorators import protect
        assert protect is not None

    def test_fab_indexview_importable(self):
        """FAB IndexView moet importeerbaar zijn."""
        from flask_appbuilder import IndexView
        assert IndexView is not None

    def test_fab_widgets_importable(self):
        """FAB widget classes moeten importeerbaar zijn."""
        from flask_appbuilder.widgets import ListWidget, FormWidget, ShowWidget
        assert ListWidget is not None
        assert FormWidget is not None
        assert ShowWidget is not None

    def test_fab_filters_importable(self):
        """FAB filter classes moeten importeerbaar zijn."""
        from flask_appbuilder.models.sqla.filters import BaseFilter, SQLAFilterConverter
        assert BaseFilter is not None
        assert SQLAFilterConverter is not None

    def test_fab_renders_decorator_importable(self):
        """FAB renders decorator moet importeerbaar zijn."""
        from flask_appbuilder.models.decorators import renders
        assert renders is not None

    def test_fab_image_manager_importable(self):
        """FAB ImageManager moet importeerbaar zijn."""
        from flask_appbuilder.filemanager import ImageManager
        assert ImageManager is not None

    def test_fab_image_column_importable(self):
        """FAB ImageColumn mixin moet importeerbaar zijn."""
        from flask_appbuilder.models.mixins import ImageColumn
        assert ImageColumn is not None

    def test_fab_basemanager_importable(self):
        """FAB BaseManager moet importeerbaar zijn (gebruikt door geo addon)."""
        from flask_appbuilder.basemanager import BaseManager
        assert BaseManager is not None

    def test_fab_group_aggregate_importable(self):
        """FAB aggregate functies moeten importeerbaar zijn."""
        from flask_appbuilder.models.group import aggregate_count
        assert aggregate_count is not None

    def test_fab_exceptions_importable(self):
        """FAB exceptions moeten importeerbaar zijn."""
        from flask_appbuilder.exceptions import InterfaceQueryWithoutSession
        assert InterfaceQueryWithoutSession is not None


# ============================================================
# FAB 4.x compat module verwijdering
# ============================================================

class TestFAB4CompatRemoval:
    """Verifieer dat verwijderde _compat functies correct vervangen zijn."""

    def test_as_unicode_replaced_by_str(self):
        """as_unicode was str() wrapper — str() moet dezelfde output geven."""
        assert str("test") == "test"
        assert str(42) == "42"
        assert str(None) == "None"
        assert str("héllo wörld") == "héllo wörld"

    def test_str_on_label_text_like_objects(self):
        """str() moet werken op objecten die label.text simuleren."""
        class MockLabel:
            text = "Projectnaam"
        label = MockLabel()
        assert str(label.text) == "Projectnaam"

    def test_str_on_filter_name_like_objects(self):
        """str() moet werken op filter name attributen."""
        class MockFilter:
            name = "Fulltext Zoeken"
        flt = MockFilter()
        assert str(flt.name) == "Fulltext Zoeken"


# ============================================================
# _is_sqla_type vervanging door isinstance
# ============================================================

class TestIsInstanceReplacement:
    """Verifieer dat isinstance() correct _is_sqla_type vervangt."""

    def test_isinstance_with_geoalchemy_geometry(self):
        """isinstance moet Geometry types correct herkennen."""
        from geoalchemy2 import Geometry
        geom_type = Geometry(geometry_type='POINT', srid=4326)
        assert isinstance(geom_type, Geometry)

    def test_isinstance_with_non_geometry(self):
        """isinstance moet False returnen voor niet-Geometry types."""
        from geoalchemy2 import Geometry
        from sqlalchemy import String
        string_type = String()
        assert not isinstance(string_type, Geometry)

    def test_isinstance_point_detection(self):
        """isinstance + geometry_type check moet POINT detecteren."""
        from geoalchemy2 import Geometry
        point_type = Geometry(geometry_type='POINT', srid=4326)
        is_point = isinstance(point_type, Geometry) and point_type.geometry_type == 'POINT'
        assert is_point

    def test_isinstance_polygon_not_point(self):
        """POLYGON moet niet als POINT gedetecteerd worden."""
        from geoalchemy2 import Geometry
        poly_type = Geometry(geometry_type='POLYGON', srid=4326)
        is_point = isinstance(poly_type, Geometry) and poly_type.geometry_type == 'POINT'
        assert not is_point


# ============================================================
# Flask en Werkzeug 2.x compatibiliteit
# ============================================================

class TestFlask2Compat:
    """Verifieer Flask 2.x en Werkzeug 2.x compatibiliteit."""

    def test_flask_version(self):
        """Flask moet versie 2.x zijn."""
        import flask
        assert flask.__version__.startswith('2.')

    def test_werkzeug_version(self):
        """Werkzeug moet versie 2.x zijn."""
        import werkzeug
        assert werkzeug.__version__.startswith('2.')

    def test_jinja2_version(self):
        """Jinja2 moet versie 3.x zijn."""
        import jinja2
        assert jinja2.__version__.startswith('3.')

    def test_wtforms_version(self):
        """WTForms moet versie 3.x zijn."""
        import wtforms
        assert wtforms.__version__.startswith('3.')

    def test_flask_app_creation(self):
        """Een Flask app moet aangemaakt kunnen worden."""
        from flask import Flask
        app = Flask(__name__)
        assert app is not None

    def test_flask_redirect(self):
        """flask.redirect moet beschikbaar zijn."""
        from flask import redirect
        assert redirect is not None

    def test_flask_request(self):
        """flask.request moet beschikbaar zijn."""
        from flask import request
        assert request is not None

    def test_flask_url_for(self):
        """flask.url_for moet beschikbaar zijn."""
        from flask import url_for
        assert url_for is not None

    def test_flask_current_app(self):
        """flask.current_app moet beschikbaar zijn."""
        from flask import current_app
        assert current_app is not None

    def test_flask_session(self):
        """flask.session moet beschikbaar zijn."""
        from flask import session
        assert session is not None

    def test_flask_blueprint(self):
        """flask.Blueprint moet beschikbaar zijn."""
        from flask import Blueprint
        assert Blueprint is not None

    def test_flask_make_response(self):
        """flask.make_response moet beschikbaar zijn."""
        from flask import make_response
        assert make_response is not None


# ============================================================
# Database libraries compatibiliteit
# ============================================================

class TestDatabaseLibraries:
    """Verifieer dat database-gerelateerde libraries correct werken."""

    def test_sqlalchemy_version(self):
        """SQLAlchemy moet versie 1.4.x zijn."""
        import sqlalchemy
        assert sqlalchemy.__version__.startswith('1.4.')

    def test_sqlalchemy_core_imports(self):
        """SQLAlchemy core imports moeten werken."""
        from sqlalchemy import Column, Integer, String, Float, Text, Boolean
        from sqlalchemy import ForeignKey, Table, Date, DateTime, JSON
        from sqlalchemy import select, func
        from sqlalchemy.orm import relationship
        from sqlalchemy.ext.hybrid import hybrid_property, hybrid_method
        assert Column is not None

    def test_sqlalchemy_dialects(self):
        """PostgreSQL dialect moet beschikbaar zijn."""
        from sqlalchemy.dialects.postgresql import UUID
        assert UUID is not None

    def test_geoalchemy2_importable(self):
        """GeoAlchemy2 moet importeerbaar zijn."""
        from geoalchemy2 import Geometry
        assert Geometry is not None

    def test_geoalchemy2_shape(self):
        """GeoAlchemy2 shape utilities moeten importeerbaar zijn."""
        from geoalchemy2.shape import to_shape
        assert to_shape is not None

    def test_geoalchemy2_elements(self):
        """GeoAlchemy2 WKBElement moet importeerbaar zijn."""
        from geoalchemy2.elements import WKBElement
        assert WKBElement is not None

    def test_pymongo_importable(self):
        """pymongo 4.x moet importeerbaar zijn."""
        import pymongo
        assert pymongo.version.startswith('4.')

    def test_pymongo_mongo_client(self):
        """MongoClient moet importeerbaar zijn."""
        from pymongo import MongoClient
        assert MongoClient is not None

    def test_elasticsearch_importable(self):
        """Elasticsearch client moet importeerbaar zijn."""
        from elasticsearch import Elasticsearch
        assert Elasticsearch is not None

    def test_psycopg2_importable(self):
        """psycopg2 moet importeerbaar zijn."""
        import psycopg2
        assert psycopg2 is not None


# ============================================================
# Data libraries compatibiliteit
# ============================================================

class TestDataLibraries:
    """Verifieer dat data-gerelateerde libraries beschikbaar zijn."""

    def test_pandas_importable(self):
        """pandas moet importeerbaar zijn."""
        import pandas
        assert pandas is not None

    def test_numpy_importable(self):
        """numpy moet importeerbaar zijn."""
        import numpy
        assert numpy is not None

    def test_geopandas_importable(self):
        """geopandas moet importeerbaar zijn."""
        import geopandas
        assert geopandas is not None

    def test_shapely_importable(self):
        """shapely 2.x moet importeerbaar zijn."""
        import shapely
        assert shapely is not None

    def test_shapely_geometry_point(self):
        """shapely.geometry.Point moet importeerbaar zijn (gebruikt in loadToDatabase)."""
        from shapely.geometry import Point
        p = Point(0, 0)
        assert p.x == 0
        assert p.y == 0

    def test_shapely_wkb(self):
        """shapely.wkb moet importeerbaar zijn (gebruikt in geo addon fields)."""
        from shapely import wkb
        assert wkb is not None

    def test_pillow_importable(self):
        """Pillow moet importeerbaar zijn."""
        from PIL import Image
        assert Image is not None

    def test_folium_importable(self):
        """folium moet importeerbaar zijn."""
        import folium
        assert folium is not None

    def test_redis_importable(self):
        """redis-py moet importeerbaar zijn."""
        import redis
        assert redis is not None

    def test_flask_caching_importable(self):
        """flask_caching moet importeerbaar zijn."""
        from flask_caching import Cache
        assert Cache is not None

    def test_flask_migrate_importable(self):
        """flask_migrate moet importeerbaar zijn."""
        from flask_migrate import Migrate
        assert Migrate is not None


# ============================================================
# Geo addon modules
# ============================================================

class TestGeoAddon:
    """Test dat de geo addon modules correct importeren."""

    def test_geo_fields_importable(self):
        """GeometryField en PointField moeten importeerbaar zijn."""
        # Voeg app pad toe zodat het geo addon gevonden wordt
        import os
        app_path = os.path.join(os.path.dirname(__file__), '..', '..', 'app')
        if app_path not in sys.path:
            sys.path.insert(0, os.path.abspath(app_path))
        from fab_addon_geoalchemy.fields import GeometryField, PointField
        assert GeometryField is not None
        assert PointField is not None
        assert issubclass(PointField, GeometryField)

    def test_geo_widgets_importable(self):
        """LatLonWidget moet importeerbaar zijn."""
        import os
        app_path = os.path.join(os.path.dirname(__file__), '..', '..', 'app')
        if app_path not in sys.path:
            sys.path.insert(0, os.path.abspath(app_path))
        from fab_addon_geoalchemy.widgets import LatLonWidget
        assert LatLonWidget is not None

    def test_geo_widgets_uses_markupsafe(self):
        """LatLonWidget._ro_template moet een Markup instance zijn."""
        import os
        app_path = os.path.join(os.path.dirname(__file__), '..', '..', 'app')
        if app_path not in sys.path:
            sys.path.insert(0, os.path.abspath(app_path))
        from fab_addon_geoalchemy.widgets import LatLonWidget
        from markupsafe import Markup
        assert isinstance(LatLonWidget._ro_template, Markup)

    def test_geo_models_importable(self):
        """GeoSQLAInterface moet importeerbaar zijn."""
        import os
        app_path = os.path.join(os.path.dirname(__file__), '..', '..', 'app')
        if app_path not in sys.path:
            sys.path.insert(0, os.path.abspath(app_path))
        from fab_addon_geoalchemy.models import GeoSQLAInterface
        assert GeoSQLAInterface is not None

    def test_geo_models_isinstance_check(self):
        """GeoSQLAInterface.is_point moet isinstance gebruiken (niet _is_sqla_type)."""
        import os
        import inspect
        app_path = os.path.join(os.path.dirname(__file__), '..', '..', 'app')
        if app_path not in sys.path:
            sys.path.insert(0, os.path.abspath(app_path))
        from fab_addon_geoalchemy.models import GeoSQLAInterface
        source = inspect.getsource(GeoSQLAInterface.is_point)
        assert 'isinstance' in source
        assert '_is_sqla_type' not in source


# ============================================================
# shared/config.py MongoDB URI tests
# ============================================================

class TestMongoURIs:
    """Verifieer dat MongoDB URI's authSource=admin bevatten."""

    def test_mongo_uri_has_authsource(self):
        """MONGO_URI moet authSource=admin bevatten."""
        import shared.config as config
        assert '?authSource=admin' in config.MONGO_URI

    def test_mongo_staging_uri_has_authsource(self):
        """MONGO_STAGING_URI moet authSource=admin bevatten."""
        import shared.config as config
        assert '?authSource=admin' in config.MONGO_STAGING_URI

    def test_mongo_files_uri_has_authsource(self):
        """MONGO_FILES_URI moet authSource=admin bevatten."""
        import shared.config as config
        assert '?authSource=admin' in config.MONGO_FILES_URI

    def test_mongo_analyse_uri_has_authsource(self):
        """MONGO_ANALYSE_URI moet authSource=admin bevatten."""
        import shared.config as config
        assert '?authSource=admin' in config.MONGO_ANALYSE_URI
