"""
Unit tests voor de formatters in app/app/baseviews.py

Test fotoFormatter, abrFormatter, schelpFormatter, highlightFormatter en flatten.
De functies worden direct uit het bronbestand geladen om circulaire
imports met de Flask app te voorkomen.
"""
import pytest
import sys
import os
import ast
from markupsafe import Markup

# Laad de formatter-functies rechtstreeks uit baseviews.py
_baseviews_path = os.path.join(
    os.path.dirname(__file__), '..', '..', 'app', 'app', 'baseviews.py'
)


def _load_functions():
    """Extraheer pure functies uit baseviews.py zonder de FAB-imports."""
    with open(os.path.abspath(_baseviews_path)) as f:
        source = f.read()

    ns = {"ast": ast, "Markup": Markup}

    # Extraheer functies individueel
    for func_name in ["fotoFormatter", "abrFormatter", "schelpFormatter",
                       "highlightFormatter", "flatten"]:
        start = source.index(f"def {func_name}")
        # Zoek het einde: volgende def of class op hetzelfde indent-level
        rest = source[start:]
        lines = rest.split('\n')
        func_lines = [lines[0]]
        for line in lines[1:]:
            if line and not line[0].isspace() and not line.strip() == '':
                break
            func_lines.append(line)
        func_source = '\n'.join(func_lines)
        exec(compile(func_source, _baseviews_path, "exec"), ns)

    return ns


_funcs = _load_functions()
fotoFormatter = _funcs["fotoFormatter"]
abrFormatter = _funcs["abrFormatter"]
schelpFormatter = _funcs["schelpFormatter"]
highlightFormatter = _funcs["highlightFormatter"]
flatten = _funcs["flatten"]


class MockFoto:
    """Simuleer een foto-object met imageMiddleID."""
    def __init__(self, image_id):
        self.imageMiddleID = image_id


class MockABR:
    """Simuleer een ABR-object met note en __str__."""
    def __init__(self, label, note=None):
        self._label = label
        self.note = note

    def __str__(self):
        return self._label


class MockSchelp:
    """Simuleer een schelp-object met milieu en __str__."""
    def __init__(self, name, milieu=None):
        self._name = name
        self.milieu = milieu

    def __str__(self):
        return self._name


class TestFotoFormatter:
    """Test de fotoFormatter() functie."""

    def test_empty_list(self):
        result = fotoFormatter([])
        assert "carousel" in result
        assert "carousel-inner" in result

    def test_single_foto(self):
        foto = MockFoto("/images/test.jpg")
        result = fotoFormatter([foto])
        assert "/archeomedia/images/test.jpg" in result
        assert "active" in result

    def test_multiple_fotos(self):
        fotos = [MockFoto("/img/a.jpg"), MockFoto("/img/b.jpg")]
        result = fotoFormatter(fotos)
        assert "/archeomedia/img/a.jpg" in result
        assert "/archeomedia/img/b.jpg" in result
        assert "data-slide-to=\"0\"" in result
        assert "data-slide-to=\"1\"" in result


class TestAbrFormatter:
    """Test de abrFormatter() functie."""

    def test_with_note(self):
        abr = MockABR("Aardewerk", note="Gebakken klei")
        result = abrFormatter(abr)
        assert "Aardewerk" in result
        assert "Gebakken klei" in result
        assert "tooltip" in result

    def test_without_note(self):
        abr = MockABR("Steen", note=None)
        result = abrFormatter(abr)
        assert "Steen" in result
        assert "Geen beschrijving" in result


class TestSchelpFormatter:
    """Test de schelpFormatter() functie."""

    def test_with_milieu(self):
        schelp = MockSchelp("Oester", milieu="Marien")
        result = schelpFormatter(schelp)
        assert "Oester" in result
        assert "Marien" in result
        assert "Milieu:" in result

    def test_without_milieu(self):
        schelp = MockSchelp("Mossel", milieu=None)
        result = schelpFormatter(schelp)
        assert "Mossel" in result
        assert "Geen milieu-informatie" in result


class TestHighlightFormatter:
    """Test de highlightFormatter() functie."""

    def test_none_returns_str(self):
        result = highlightFormatter(None)
        assert result == "None"

    def test_plain_string(self):
        result = highlightFormatter("test highlight")
        assert result == "test highlight"


class TestFlatten:
    """Test de flatten() functie."""

    def test_nested_lists(self):
        assert flatten([[1, 2], [3, 4]]) == [1, 2, 3, 4]

    def test_empty_sublists(self):
        assert flatten([[], [1], []]) == [1]

    def test_single_list(self):
        assert flatten([[1, 2, 3]]) == [1, 2, 3]

    def test_empty(self):
        assert flatten([]) == []
