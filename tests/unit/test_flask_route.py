"""
Unit tests voor de makeRelative() functie uit app/app/route.py

Importeert de functie direct uit het bronbestand om circulaire
imports met de Flask app te voorkomen.
"""
import pytest
import os


def _load_makeRelative():
    """Laad makeRelative() direct uit route.py zonder de hele app te importeren."""
    import importlib.util
    route_path = os.path.join(
        os.path.dirname(__file__), '..', '..', 'app', 'app', 'route.py'
    )
    # Lees alleen de functie-definitie, niet de module-level imports
    with open(os.path.abspath(route_path)) as f:
        source = f.read()

    # Extraheer de makeRelative functie
    ns = {"os": os}
    exec(compile(
        "import os\n" + source[source.index("def makeRelative"):source.index("\n\n\n", source.index("def makeRelative"))],
        route_path, "exec"
    ), ns)
    return ns["makeRelative"]


makeRelative = _load_makeRelative()


class TestMakeRelative:
    """Test de makeRelative() functie die leading separators verwijdert."""

    def test_with_leading_separator(self):
        assert makeRelative("/images/foto.jpg") == "images/foto.jpg"

    def test_without_leading_separator(self):
        assert makeRelative("images/foto.jpg") == "images/foto.jpg"

    def test_just_separator(self):
        assert makeRelative("/") == ""

    def test_empty_string(self):
        assert makeRelative("") == ""

    def test_nested_path(self):
        assert makeRelative("/output/archeomedia/fotos/123.jpg") == "output/archeomedia/fotos/123.jpg"
