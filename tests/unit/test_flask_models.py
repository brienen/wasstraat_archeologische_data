"""
Unit tests voor app/app/models.py

Test model-definities, enum-waarden en polymorphic inheritance.
Gebruikt geen database — alleen klasse-inspectie.
"""
import pytest
import sys
import os

_app_path = os.path.join(os.path.dirname(__file__), '..', '..', 'app', 'app')
if os.path.abspath(_app_path) not in sys.path:
    sys.path.insert(0, os.path.abspath(_app_path))
_app_root = os.path.join(os.path.dirname(__file__), '..', '..', 'app')
if os.path.abspath(_app_root) not in sys.path:
    sys.path.insert(0, os.path.abspath(_app_root))


class TestDiscrArtefactsoortEnum:
    """Test de artefactsoort enum waarden."""

    def test_all_expected_types_present(self):
        from models import DiscrArtefactsoortEnum
        expected = [
            'Aardewerk', 'Glas', 'Metaal', 'Hout', 'Steen', 'Leer',
            'Dierlijk_Bot', 'Menselijk_Bot', 'Kleipijp', 'Bouwaardewerk',
            'Munt', 'Schelp', 'Textiel', 'Onbekend'
        ]
        members = [e.name for e in DiscrArtefactsoortEnum]
        for name in expected:
            assert name in members, f"{name} ontbreekt in DiscrArtefactsoortEnum"

    def test_enum_values_are_strings(self):
        from models import DiscrArtefactsoortEnum
        for e in DiscrArtefactsoortEnum:
            assert isinstance(e.value, str)


class TestArtefactPolymorphism:
    """Test dat artefact-subtypes correct polymorphic identity hebben."""

    @pytest.mark.parametrize("model_name,expected_identity", [
        ("Aardewerk", "Aardewerk"),
        ("Glas", "Glas"),
        ("Metaal", "Metaal"),
        ("Hout", "Hout"),
        ("Steen", "Steen"),
        ("Leer", "Leer"),
        ("Dierlijk_Bot", "Dierlijk_Bot"),
        ("Menselijk_Bot", "Menselijk_Bot"),
        ("Kleipijp", "Kleipijp"),
        ("Bouwaardewerk", "Bouwaardewerk"),
        ("Munt", "Munt"),
        ("Schelp", "Schelp"),
        ("Textiel", "Textiel"),
    ])
    def test_artefact_subtype_identity(self, model_name, expected_identity):
        import models
        model_cls = getattr(models, model_name)
        identity = model_cls.__mapper_args__['polymorphic_identity']
        # Identity kan een enum zijn of een string
        if hasattr(identity, 'value'):
            assert identity.value == expected_identity
        else:
            assert identity == expected_identity


class TestBestandPolymorphism:
    """Test dat bestand-subtypes correct polymorphic identity hebben."""

    @pytest.mark.parametrize("model_name", [
        "Objectfoto", "Opgravingsfoto", "Overige_foto", "Sfeerfoto",
        "Veldtekening", "Overzichtstekening", "Objecttekening",
        "Archeologische_Rapportage", "Conserveringsrapport",
    ])
    def test_bestand_subtype_exists(self, model_name):
        import models
        model_cls = getattr(models, model_name)
        assert hasattr(model_cls, '__mapper_args__')
        assert 'polymorphic_identity' in model_cls.__mapper_args__


class TestCoreModels:
    """Test dat kernmodellen de verwachte kolommen hebben."""

    def test_project_has_location(self):
        import models
        assert hasattr(models.Project, 'location')

    def test_project_has_projectcd(self):
        import models
        assert hasattr(models.Project, 'projectcd')

    def test_artefact_has_primary_key(self):
        import models
        assert hasattr(models.Artefact, 'primary_key')

    def test_artefact_has_artefactsoort(self):
        import models
        assert hasattr(models.Artefact, 'artefactsoort')

    def test_vondst_has_vondstnr(self):
        import models
        assert hasattr(models.Vondst, 'vondstnr')

    def test_spoor_has_spoornr(self):
        import models
        assert hasattr(models.Spoor, 'spoornr')

    def test_put_has_putnr(self):
        import models
        assert hasattr(models.Put, 'putnr')

    def test_bestand_has_bestandsoort(self):
        import models
        assert hasattr(models.Bestand, 'bestandsoort')

    def test_abr_has_uri(self):
        import models
        assert hasattr(models.ABR, 'uri')

    def test_abr_has_parent_relationship(self):
        import models
        assert hasattr(models.ABR, 'parentID')


class TestModelImports:
    """Test dat alle modellen importeerbaar zijn."""

    @pytest.mark.parametrize("model_name", [
        "Project", "Put", "Vlak", "Spoor", "Vulling", "Vondst",
        "Artefact", "Bestand", "ABR", "Doos", "Stelling", "Vindplaats",
        "Standplaats", "Plaatsing", "Partij", "Bruikleen", "Monster",
    ])
    def test_model_importable(self, model_name):
        import models
        model_cls = getattr(models, model_name, None)
        assert model_cls is not None, f"Model {model_name} niet gevonden"
