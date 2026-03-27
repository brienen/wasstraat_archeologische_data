"""
Unit tests voor app/app/validators.py

Test de ABRCompare_Artefactsoort en ABRCompare_SUBArtefactsoort validators.
"""
import pytest
import sys
import os

_app_path = os.path.join(os.path.dirname(__file__), '..', '..', 'app', 'app')
if os.path.abspath(_app_path) not in sys.path:
    sys.path.insert(0, os.path.abspath(_app_path))

from wtforms.validators import ValidationError
import shared.const as const


class MockData:
    """Simuleer een form field .data object met een uri attribuut."""
    def __init__(self, uri):
        self.uri = uri


class MockLabel:
    """Simuleer een WTForms field label."""
    def __init__(self, text):
        self.text = text


class MockField:
    """Simuleer een WTForms field met .data en .label."""
    def __init__(self, data, label_text="test"):
        self.data = data
        self.label = MockLabel(label_text)

    def gettext(self, msg):
        return msg


class MockForm(dict):
    """Simuleer een WTForms form als dict van fields."""
    pass


def _make_form(abr_uri, artefactsoort_enum):
    """Helper: maak een mock form met ABR field en artefactsoort field."""
    field = MockField(MockData(abr_uri))
    artefactsoort_field = MockField(artefactsoort_enum)
    form = MockForm({"abr_materiaal": field, "artefactsoort": artefactsoort_field})
    return form, field, artefactsoort_field


class TestABRCompareArtefactsoort:
    """Test de ABRCompare_Artefactsoort validator."""

    @pytest.fixture(autouse=True)
    def setup(self):
        from validators import ABRCompare_Artefactsoort
        from models import DiscrArtefactsoortEnum
        self.validator = ABRCompare_Artefactsoort("artefactsoort")
        self.enum = DiscrArtefactsoortEnum

    def test_organisch_dierlijk_bot_valid(self):
        """Organisch materiaal + Dierlijk Bot is geldig."""
        form, field, _ = _make_form(const.ABR_URI_ORGANISCH, self.enum.Dierlijk_Bot)
        self.validator(form, field)  # mag geen exception geven

    def test_organisch_hout_valid(self):
        """Organisch materiaal + Hout is geldig."""
        form, field, _ = _make_form(const.ABR_URI_ORGANISCH, self.enum.Hout)
        self.validator(form, field)

    def test_organisch_glas_invalid(self):
        """Organisch materiaal + Glas is ongeldig."""
        form, field, _ = _make_form(const.ABR_URI_ORGANISCH, self.enum.Glas)
        with pytest.raises((ValidationError, KeyError)):
            self.validator(form, field)

    def test_keramiek_aardewerk_valid(self):
        """Keramiek + Aardewerk is geldig."""
        form, field, _ = _make_form(const.ABR_URI_KARAMIEK, self.enum.Aardewerk)
        self.validator(form, field)

    def test_keramiek_metaal_invalid(self):
        """Keramiek + Metaal is ongeldig."""
        form, field, _ = _make_form(const.ABR_URI_KARAMIEK, self.enum.Metaal)
        with pytest.raises((ValidationError, KeyError)):
            self.validator(form, field)

    def test_glas_glas_valid(self):
        """Glas + Glas is geldig."""
        form, field, _ = _make_form(const.ABR_URI_GLAS, self.enum.Glas)
        self.validator(form, field)

    def test_metaal_metaal_valid(self):
        """Metaal + Metaal is geldig."""
        form, field, _ = _make_form(const.ABR_URI_METAAL, self.enum.Metaal)
        self.validator(form, field)

    def test_metaal_munt_valid(self):
        """Metaal + Munt is geldig."""
        form, field, _ = _make_form(const.ABR_URI_METAAL, self.enum.Munt)
        self.validator(form, field)

    def test_steen_steen_valid(self):
        """Steen + Steen is geldig."""
        form, field, _ = _make_form(const.ABR_URI_STEEN, self.enum.Steen)
        self.validator(form, field)

    def test_onbekend_always_valid(self):
        """Onbekend artefactsoort is altijd geldig ongeacht materiaal."""
        form, field, _ = _make_form(const.ABR_URI_ORGANISCH, self.enum.Onbekend)
        self.validator(form, field)

    def test_steen_aardewerk_invalid(self):
        """Steen + Aardewerk is ongeldig."""
        form, field, _ = _make_form(const.ABR_URI_STEEN, self.enum.Aardewerk)
        with pytest.raises((ValidationError, KeyError)):
            self.validator(form, field)
