"""
Unit tests voor app/app/util.py

Test de pure utility-functies: isEmpty, create_named_tuple, removeFieldFromFieldset.
"""
import pytest


class TestIsEmpty:
    """Test de isEmpty() functie."""

    def test_none_is_empty(self):
        from util import isEmpty
        assert isEmpty(None) is True

    def test_empty_string_is_empty(self):
        from util import isEmpty
        assert isEmpty("") is True

    def test_nonempty_string_is_not_empty(self):
        from util import isEmpty
        assert isEmpty("abc") is False

    def test_zero_is_empty(self):
        from util import isEmpty
        assert isEmpty(0) is True

    def test_whitespace_is_not_empty(self):
        """Spatie is technisch een string met lengte > 0."""
        from util import isEmpty
        assert isEmpty(" ") is False

    def test_false_is_empty(self):
        from util import isEmpty
        assert isEmpty(False) is True


class TestCreateNamedTuple:
    """Test de create_named_tuple() functie."""

    def test_with_values(self):
        from util import create_named_tuple
        nt = create_named_tuple("a", "b", "c")
        assert nt.a == "a"
        assert nt.b == "b"
        assert nt.c == "c"

    def test_single_value(self):
        from util import create_named_tuple
        nt = create_named_tuple("test")
        assert nt.test == "test"

    def test_returns_tuple(self):
        from util import create_named_tuple
        nt = create_named_tuple("x", "y")
        assert isinstance(nt, tuple)


class TestRemoveFieldFromFieldset:
    """Test de removeFieldFromFieldset() functie."""

    def test_remove_existing_field(self):
        from util import removeFieldFromFieldset
        fieldsets = [
            ("Sectie1", {"fields": ["naam", "code", "type"]})
        ]
        result = removeFieldFromFieldset(fieldsets, "code")
        assert "code" not in result[0][1]["fields"]
        assert "naam" in result[0][1]["fields"]

    def test_remove_nonexistent_field(self):
        from util import removeFieldFromFieldset
        fieldsets = [
            ("Sectie1", {"fields": ["naam", "code"]})
        ]
        result = removeFieldFromFieldset(fieldsets, "onbekend")
        assert result[0][1]["fields"] == ["naam", "code"]

    def test_does_not_mutate_original(self):
        from util import removeFieldFromFieldset
        fieldsets = [
            ("Sectie1", {"fields": ["naam", "code"]})
        ]
        removeFieldFromFieldset(fieldsets, "code")
        assert "code" in fieldsets[0][1]["fields"]

    def test_multiple_fieldsets(self):
        from util import removeFieldFromFieldset
        fieldsets = [
            ("Sectie1", {"fields": ["naam", "code"]}),
            ("Sectie2", {"fields": ["code", "type"]})
        ]
        result = removeFieldFromFieldset(fieldsets, "code")
        assert "code" not in result[0][1]["fields"]
        assert "code" not in result[1][1]["fields"]

    def test_columns_layout(self):
        """Test met columns-gebaseerde fieldset layout."""
        from util import removeFieldFromFieldset
        fieldsets = [
            ("Sectie1", {"columns": [
                {"fields": ["naam", "code"]},
                {"fields": ["type", "code"]}
            ]})
        ]
        result = removeFieldFromFieldset(fieldsets, "code")
        assert "code" not in result[0][1]["columns"][0]["fields"]
        assert "code" not in result[0][1]["columns"][1]["fields"]
