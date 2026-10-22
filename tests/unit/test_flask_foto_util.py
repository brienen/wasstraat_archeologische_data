"""
Unit tests voor het kantelen van bestanden (app/app/foto_util.py, issue 34).

foto_util draait het grote formaat in de mediamap en maakt het briefkaartformaat en de
thumbnail opnieuw met de echte image_util.putImageInGrid, in een tijdelijke mediamap. De
pdf-bibliotheken (PyPDF2, pdf2image) zijn hier nagebootst; de smoke tests in
tests/integration/test_flask_smoke.py kantelen een echte pdf in de Flask-container.
"""
import importlib.util
import os
import re
import sys
import types
from types import SimpleNamespace

import pytest
from PIL import Image


_project_root = os.path.join(os.path.dirname(__file__), '..', '..')
FOTO_UTIL = os.path.abspath(os.path.join(_project_root, 'app', 'app', 'foto_util.py'))
IMAGE_UTIL = os.path.abspath(os.path.join(_project_root, 'shared', 'image_util.py'))
VIEWS = os.path.abspath(os.path.join(_project_root, 'app', 'app', 'views.py'))

MAP = '/SY001/L Fotos'
ROOD = (255, 0, 0)


def laadModule(naam, pad):
    """Laad een Python-bestand als losse module, zonder het in sys.modules te registreren."""
    spec = importlib.util.spec_from_file_location(naam, pad)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class NepPagina:
    """Nabootsing van een PyPDF2-pagina die de gevraagde draaiingen bijhoudt."""

    def __init__(self):
        self.draaiingen = []

    def rotate(self, hoek):
        self.draaiingen.append(hoek)
        return self


class NepPdf:
    """Houdt bij wat de nagebootste pdf-bibliotheken te zien kregen."""

    def __init__(self):
        self.paginas = [NepPagina(), NepPagina()]
        self.gelezen = []
        self.geschreven = []
        self.conversies = []
        # Eerste pagina liggend, met een rood blok linksboven
        self.eerstePagina = Image.new('RGB', (600, 400), 'white')
        self.eerstePagina.paste(ROOD, (0, 0, 150, 100))


@pytest.fixture
def nepPdf():
    return NepPdf()


@pytest.fixture
def media(tmp_path, monkeypatch):
    """Tijdelijke mediamap als config.AIRFLOW_OUTPUT_MEDIA, met de formaten uit shared/config.py."""
    config = sys.modules['shared.config']
    monkeypatch.setattr(config, 'AIRFLOW_OUTPUT_MEDIA', str(tmp_path), raising=False)
    monkeypatch.setattr(config, 'IMAGE_SIZE_THUMB', (300, 200), raising=False)
    monkeypatch.setattr(config, 'IMAGE_SIZE_MIDDLE', (1500, 1000), raising=False)
    monkeypatch.setattr(config, 'IMAGE_SIZE_BIGGEST', (7000, 7000), raising=False)
    monkeypatch.setattr(config, 'IMAGE_SIZE_LZW', (15000, 15000), raising=False)
    return tmp_path


@pytest.fixture
def imageUtil(media, nepPdf, monkeypatch):
    """De echte shared/image_util.py, met nagebootste magic en pdf2image."""
    nepMagic = types.ModuleType('magic')
    nepPdf2image = types.ModuleType('pdf2image')

    def convertFromPath(pad, **kwargs):
        nepPdf.conversies.append((pad, kwargs))
        return [nepPdf.eerstePagina.copy()]

    nepPdf2image.convert_from_path = convertFromPath
    monkeypatch.setitem(sys.modules, 'magic', nepMagic)
    monkeypatch.setitem(sys.modules, 'pdf2image', nepPdf2image)
    module = laadModule('image_util_onder_test', IMAGE_UTIL)
    monkeypatch.setitem(sys.modules, 'shared.image_util', module)
    return module


@pytest.fixture
def fotoUtil(imageUtil, nepPdf, monkeypatch):
    """app/app/foto_util.py met de echte image_util en een nagebootste PyPDF2."""
    nepPyPDF2 = types.ModuleType('PyPDF2')

    class PdfReader:
        def __init__(self, pad):
            nepPdf.gelezen.append(pad)
            self.pages = nepPdf.paginas

    class PdfWriter:
        def __init__(self):
            self.paginas = []

        def add_page(self, pagina):
            self.paginas.append(pagina)

        def write(self, stroom):
            nepPdf.geschreven.append(len(self.paginas))
            stroom.write(b'%PDF-gekanteld')

    nepPyPDF2.PdfReader = PdfReader
    nepPyPDF2.PdfWriter = PdfWriter
    monkeypatch.setitem(sys.modules, 'PyPDF2', nepPyPDF2)
    return laadModule('foto_util_onder_test', FOTO_UTIL)


def maakFoto(media, imageUtil, naam='foto', grootte=(400, 200), mode='RGB'):
    """Maak de drie formaten van een liggende foto met een rood blok linksboven, zoals de extractie.

    Returns:
        SimpleNamespace: Bestand met fileName, imageID, imageMiddleID en imageThumbID.
    """
    image = Image.new(mode, grootte, 'white')
    image.paste(ROOD if mode == 'RGB' else 0, (0, 0, grootte[0] // 4, grootte[1] // 4))
    bron = os.path.join(str(media), 'bron', f'{naam}.tif')
    sml, med, groot = imageUtil.putImageInGrid(image, bron, None, MAP, 'SY001')
    return SimpleNamespace(fileName=f'{naam}.tif', imageID=groot, imageMiddleID=med, imageThumbID=sml)


def open_(media, pad):
    """Open een bestand uit de mediamap als RGB-afbeelding."""
    with Image.open(os.path.join(str(media), pad.lstrip('/'))) as image:
        return image.convert('RGB')


def isRood(pixel):
    return pixel[0] > 200 and pixel[1] < 80 and pixel[2] < 80


def inhoud(image):
    """Omhullende van alles wat niet wit is (de briefkaart en thumbnail hebben een witte rand)."""
    return image.convert('L').point(lambda waarde: 255 if waarde < 245 else 0).getbbox()


def staand(kader):
    links, boven, rechts, onder = kader
    return (onder - boven) > (rechts - links)


class TestKantelenFoto:
    """Een foto (of tekening) draait in alle drie de formaten."""

    def test_linksom_kantelt_groot_formaat(self, fotoUtil, imageUtil, media):
        bestand = maakFoto(media, imageUtil)
        fotoUtil.rotateBestand(bestand, 90)
        groot = open_(media, bestand.imageID)
        assert groot.size == (200, 400)
        # Linksom: het blok linksboven komt linksonder
        assert isRood(groot.getpixel((10, 390)))
        assert not isRood(groot.getpixel((10, 10)))

    def test_rechtsom_kantelt_groot_formaat(self, fotoUtil, imageUtil, media):
        bestand = maakFoto(media, imageUtil)
        fotoUtil.rotateBestand(bestand, -90)
        groot = open_(media, bestand.imageID)
        assert groot.size == (200, 400)
        # Rechtsom: het blok linksboven komt rechtsboven
        assert isRood(groot.getpixel((190, 10)))
        assert not isRood(groot.getpixel((10, 390)))

    def test_briefkaart_en_thumbnail_opnieuw_gemaakt(self, fotoUtil, imageUtil, media):
        bestand = maakFoto(media, imageUtil)
        assert not staand(inhoud(open_(media, bestand.imageMiddleID)))
        assert not staand(inhoud(open_(media, bestand.imageThumbID)))
        fotoUtil.rotateBestand(bestand, 90)
        middel = open_(media, bestand.imageMiddleID)
        thumb = open_(media, bestand.imageThumbID)
        # De formaten zelf blijven gelijk (witte rand), de inhoud staat nu rechtop
        assert middel.size == (1500, 1000) and thumb.size == (300, 200)
        assert staand(inhoud(middel))
        assert staand(inhoud(thumb))

    def test_vier_keer_linksom_is_weer_het_origineel(self, fotoUtil, imageUtil, media):
        bestand = maakFoto(media, imageUtil)
        for _ in range(4):
            fotoUtil.rotateBestand(bestand, 90)
        groot = open_(media, bestand.imageID)
        assert groot.size == (400, 200)
        assert isRood(groot.getpixel((10, 10)))

    def test_grijswaardentekening(self, fotoUtil, imageUtil, media):
        """Een tekening uit een lzw-tif is als grijswaarden-jpg opgeslagen en blijft dat."""
        bestand = maakFoto(media, imageUtil, naam='tekening', mode='L')
        fotoUtil.rotateBestand(bestand, -90)
        with Image.open(os.path.join(str(media), bestand.imageID.lstrip('/'))) as groot:
            assert groot.size == (200, 400)
            assert groot.mode == 'L'

    def test_bestanden_ter_plekke_overschreven(self, fotoUtil, imageUtil, media):
        """Zelfde inode: eigenaar en rechten blijven die van de extractie (airflow)."""
        bestand = maakFoto(media, imageUtil)
        paden = [os.path.join(str(media), p.lstrip('/'))
                 for p in (bestand.imageID, bestand.imageMiddleID, bestand.imageThumbID)]
        inodes = [os.stat(pad).st_ino for pad in paden]
        assert fotoUtil.rotateBestand(bestand, 90) is False
        assert [os.stat(pad).st_ino for pad in paden] == inodes

    def test_paden_bijgewerkt_als_ze_afwijken(self, fotoUtil, imageUtil, media):
        """Wijzen de voorbeelden in Def_Bestand elders heen, dan komen ze naast imageID en wordt dat gemeld."""
        bestand = maakFoto(media, imageUtil)
        bestand.imageMiddleID = '/elders/foto-oud-med.jpg'
        bestand.imageThumbID = None
        assert fotoUtil.rotateBestand(bestand, 90) is True
        assert bestand.imageMiddleID == f'{MAP}/foto-med.jpg'
        assert bestand.imageThumbID == f'{MAP}/foto-sml.jpg'
        assert staand(inhoud(open_(media, bestand.imageThumbID)))


class TestKantelenPdf:
    """Van een pdf draaien alle pagina's; de voorbeelden komen van de eerste pagina."""

    def maakPdf(self, media, imageUtil, nepPdf):
        pad = os.path.join(str(media), 'rapportage', 'DAR001.pdf')
        os.makedirs(os.path.dirname(pad))
        with open(pad, 'wb') as pdf:
            pdf.write(b'%PDF-origineel')
        sml, med, groot = imageUtil.putImageInGrid(nepPdf.eerstePagina, pad, None, '/rapportage', '',
                                                   filetype='.pdf')
        return SimpleNamespace(fileName='DAR001.pdf', imageID=groot, imageMiddleID=med, imageThumbID=sml), pad

    @pytest.mark.parametrize('graden,pdfHoek', [(90, 270), (-90, 90)])
    def test_alle_paginas_dezelfde_kant_op(self, fotoUtil, imageUtil, media, nepPdf, graden, pdfHoek):
        """PyPDF2 draait met de klok mee: linksom is 270, rechtsom 90."""
        bestand, pad = self.maakPdf(media, imageUtil, nepPdf)
        fotoUtil.rotateBestand(bestand, graden)
        assert [pagina.draaiingen for pagina in nepPdf.paginas] == [[pdfHoek], [pdfHoek]]
        assert nepPdf.geschreven == [2]
        with open(pad, 'rb') as pdf:
            assert pdf.read() == b'%PDF-gekanteld'

    def test_voorbeelden_van_eerste_pagina_opnieuw_gemaakt(self, fotoUtil, imageUtil, media, nepPdf):
        """Dit ging mis: putImageInGrid kreeg 'pdf=True' en de fout werd stil ingeslikt."""
        bestand, pad = self.maakPdf(media, imageUtil, nepPdf)
        nepPdf.conversies.clear()
        # De nagebootste conversie levert na het kantelen een staande eerste pagina
        nepPdf.eerstePagina = nepPdf.eerstePagina.rotate(90, expand=True)
        assert fotoUtil.rotateBestand(bestand, 90) is False
        assert nepPdf.conversies == [(pad, {'first_page': 1, 'last_page': 1})]
        assert bestand.imageID == '/rapportage/DAR001.pdf'
        assert staand(inhoud(open_(media, bestand.imageMiddleID)))
        assert staand(inhoud(open_(media, bestand.imageThumbID)))


class TestNietTeKantelen:
    """Wat niet gekanteld kan worden, geeft een KantelFout met een melding voor de gebruiker."""

    @pytest.mark.parametrize('extensie', ['.doc', '.docx', '.DOCX'])
    def test_word_document(self, fotoUtil, extensie):
        bestand = SimpleNamespace(fileName=f'notitie{extensie}', imageID=f'/DAN/notitie{extensie}',
                                  imageMiddleID=None, imageThumbID=None)
        with pytest.raises(fotoUtil.KantelFout, match='Word-document'):
            fotoUtil.rotateBestand(bestand, 90)

    def test_ontbreekt_in_mediamap(self, fotoUtil):
        bestand = SimpleNamespace(fileName='weg.jpg', imageID='/SY001/weg.jpg',
                                  imageMiddleID='/SY001/weg-med.jpg', imageThumbID='/SY001/weg-sml.jpg')
        with pytest.raises(fotoUtil.KantelFout, match='ontbreekt in de mediamap'):
            fotoUtil.rotateBestand(bestand, 90)

    def test_zonder_afbeelding(self, fotoUtil):
        bestand = SimpleNamespace(fileName='leeg.jpg', imageID=None, imageMiddleID=None, imageThumbID=None)
        with pytest.raises(fotoUtil.KantelFout, match='geen afbeelding'):
            fotoUtil.rotateBestand(bestand, 90)

    def test_alleen_veelvouden_van_90(self, fotoUtil, imageUtil, media):
        bestand = maakFoto(media, imageUtil)
        with pytest.raises(ValueError):
            fotoUtil.rotateBestand(bestand, 45)


class TestKantelActies:
    """De acties in app/app/views.py (broncontrole; de werking zelf zit in de smoke tests)."""

    def acties(self):
        with open(VIEWS, encoding='utf-8') as bron:
            return dict(re.findall(r'@action\("(\d\w*kantelen)", "[^"]*", "([^"]*)"', bron.read()))

    def test_beide_acties_aanwezig(self):
        assert set(self.acties()) == {'5linkskantelen', '6rechtskantelen'}

    def test_bevestigingstekst_zonder_apostrof(self):
        """Flask-AppBuilder 3.x zette de tekst van de knoppen op de detailpagina in een
        onclick-attribuut; een apostrof (zoals in "foto's") brak daar de JavaScript af en de knop
        deed niets."""
        for naam, tekst in self.acties().items():
            assert "'" not in tekst, f'{naam}: {tekst}'
