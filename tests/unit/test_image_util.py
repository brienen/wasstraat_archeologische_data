"""
Unit tests voor shared/image_util.py (issue 82): kleurmodus, EXIF-oriëntatie, documenticoon,
afgekapte en beschadigde bestanden.

De echte image_util schrijft de drie formaten in een tijdelijke mediamap; de collectie
Plaatjes is nagebootst en pdf2image ook (net als in test_flask_foto_util.py). De Delftse
productiedata gaf op 2026-10-22 78 mislukte bestanden: 67 Word-documenten (icoon ontbrak),
6 psd's met alfakanaal ('cannot write mode RGBA as JPEG'), een 16-bits tif ('NoneType' object
has no attribute 'copy'), een afgekapte jpg, twee beschadigde LZW-tifs ('decoder error -2')
en de rapportenlijst zonder projectcode.
"""
import errno
import fnmatch
import importlib.util
import io
import os
import re
import shutil
import sys
import types

import pytest
from PIL import Image, ImageDraw, ImageFile


_project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
IMAGE_UTIL = os.path.join(_project_root, 'shared', 'image_util.py')
CONFIG = os.path.join(_project_root, 'shared', 'config.py')
ICOON = os.path.join(_project_root, 'shared', 'afbeeldingen', 'document.png')

PROJECTMAP = os.path.join('SY001', 'L Fotos')
ROOD = (255, 0, 0)
WIT = (255, 255, 255)

# Doel van 'COPY ./shared ...' in de Dockerfiles, met de werkmap van de Airflow-image (/opt/airflow)
SHARED_IN_IMAGE = {
    'airflow': '/opt/airflow/dags/shared',
    'flask': '/app/app/shared',
}


def laadModule(naam, pad):
    """Laad een Python-bestand als losse module, zonder het in sys.modules te registreren."""
    spec = importlib.util.spec_from_file_location(naam, pad)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class NepCollectie:
    """Nabootsing van de collectie Plaatjes: bewaart de ingevoegde documenten."""

    def __init__(self):
        self.documenten = []

    def insert_one(self, document):
        self.documenten.append(document)
        return types.SimpleNamespace(inserted_id=len(self.documenten))


class NepPdf2image:
    """Nabootsing van pdf2image; paginas is de lijst die convert_from_path teruggeeft."""

    def __init__(self):
        self.paginas = [Image.new('RGB', (600, 800), 'white')]
        self.fout = None
        self.aanroepen = []

    def convert_from_path(self, pad, **kwargs):
        self.aanroepen.append((pad, kwargs))
        if self.fout is not None:
            raise self.fout
        return list(self.paginas)


@pytest.fixture
def mappen(tmp_path, monkeypatch):
    """Tijdelijke invoer- en mediamap als AIRFLOW_INPUT_IMAGES en AIRFLOW_OUTPUT_MEDIA."""
    config = sys.modules['shared.config']
    invoer = tmp_path / 'invoer'
    media = tmp_path / 'media'
    (invoer / PROJECTMAP).mkdir(parents=True)
    media.mkdir()
    monkeypatch.setattr(config, 'AIRFLOW_INPUT_IMAGES', str(invoer), raising=False)
    monkeypatch.setattr(config, 'AIRFLOW_OUTPUT_MEDIA', str(media), raising=False)
    monkeypatch.setattr(config, 'IMAGE_SIZE_THUMB', (300, 200), raising=False)
    monkeypatch.setattr(config, 'IMAGE_SIZE_MIDDLE', (1500, 1000), raising=False)
    monkeypatch.setattr(config, 'IMAGE_SIZE_BIGGEST', (7000, 7000), raising=False)
    monkeypatch.setattr(config, 'FILE_WORD_ICON', ICOON, raising=False)
    return types.SimpleNamespace(invoer=invoer, media=media)


@pytest.fixture
def nepPdf():
    return NepPdf2image()


@pytest.fixture
def imageUtil(mappen, nepPdf, monkeypatch):
    """De echte shared/image_util.py met een nagebootste pdf2image."""
    module = types.ModuleType('pdf2image')
    module.convert_from_path = nepPdf.convert_from_path
    monkeypatch.setitem(sys.modules, 'pdf2image', module)
    return laadModule('image_util_onder_test', IMAGE_UTIL)


def bronpad(mappen, naam):
    return str(mappen.invoer / PROJECTMAP / naam)


def maakRgbaPng(pad):
    """RGBA-png: linkerhelft rood en dekkend, rechterhelft volledig transparant (met zwarte pixels)."""
    image = Image.new('RGBA', (400, 200), (0, 0, 0, 0))
    image.paste((255, 0, 0, 255), (0, 0, 200, 200))
    image.save(pad, 'PNG')


def maakPaletGif(pad):
    """Palet-gif met een transparante kleur (index 0) in de rechterhelft en rood in de linkerhelft."""
    image = Image.new('P', (400, 200), 0)
    image.putpalette([0, 0, 0, 255, 0, 0] + [0, 0, 0] * 254)
    image.paste(1, (0, 0, 200, 200))
    image.save(pad, 'GIF', transparency=0)


def maakJpg(pad, grootte=(400, 200), orientatie=None, ruis=False):
    """Jpg met een rood blok linksboven, eventueel met EXIF-oriëntatie of met ruis (groter bestand)."""
    if ruis:
        image = Image.effect_noise(grootte, 80).convert('RGB')
    else:
        image = Image.new('RGB', grootte, 'white')
        image.paste(ROOD, (0, 0, grootte[0] // 4, grootte[1] // 4))
    kwargs = {}
    if orientatie is not None:
        exif = Image.Exif()
        exif[0x0112] = orientatie
        kwargs['exif'] = exif
    image.save(pad, 'JPEG', **kwargs)


def maakBeschadigdeLzwTif(pad):
    """Zwart-wit LZW-tif waarvan de strip niet met de EOI-code eindigt, zoals twee Delftse veldtekeningen."""
    image = Image.new('1', (400, 300), 1)
    teken = ImageDraw.Draw(image)
    for i in range(0, 400, 7):
        teken.line([(i, 0), (399 - i, 299)], fill=0)
    buffer = io.BytesIO()
    image.save(buffer, 'TIFF', compression='tiff_lzw')
    data = bytearray(buffer.getvalue())
    tif = Image.open(io.BytesIO(bytes(data)))
    begin, lengte = tif.tag_v2[273][0], tif.tag_v2[279][0]
    for k in range(begin + lengte - 4, begin + lengte):
        data[k] = 0
    with open(pad, 'wb') as f:
        f.write(bytes(data))


def openUitMedia(mappen, pad):
    with Image.open(os.path.join(str(mappen.media), pad.lstrip('/'))) as image:
        image.load()
        return image


def pixel(mappen, pad, xy):
    return openUitMedia(mappen, pad).convert('RGB').getpixel(xy)


def bijna(kleur, verwacht, marge=8):
    """Kleur gelijk aan verwacht op jpg-compressie na."""
    return all(abs(a - b) <= marge for a, b in zip(kleur, verwacht))


def ketenVan(err):
    """Alle exceptions in de keten van oorzaken (__cause__ en __context__)."""
    keten = []
    while err is not None and err not in keten:
        keten.append(err)
        err = err.__cause__ if err.__cause__ is not None else err.__context__
    return keten


# ============================================================
# Kleurmodus
# ============================================================

class TestZetOmVoorJpg:
    """zetOmVoorJpg levert altijd RGB of L, ongeacht de kleurmodus van de bron."""

    @pytest.mark.parametrize('modus', ['RGB', 'L'])
    def test_rgb_en_l_ongewijzigd(self, imageUtil, modus):
        image = Image.new(modus, (10, 10))
        assert imageUtil.zetOmVoorJpg(image) is image

    def test_rgba_op_witte_achtergrond(self, imageUtil):
        image = Image.new('RGBA', (4, 2), (0, 0, 0, 0))
        image.putpixel((0, 0), (255, 0, 0, 255))
        image.putpixel((1, 0), (0, 0, 255, 128))
        omgezet = imageUtil.zetOmVoorJpg(image)
        assert omgezet.mode == 'RGB'
        assert omgezet.getpixel((0, 0)) == ROOD
        assert omgezet.getpixel((3, 1)) == WIT, "Een transparante pixel hoort wit te worden, niet zwart"
        r, g, b = omgezet.getpixel((1, 0))
        assert 120 <= r <= 135 and 120 <= g <= 135 and b == 255, "Half doorzichtig blauw wordt lichtblauw"

    def test_la_op_witte_achtergrond(self, imageUtil):
        image = Image.new('LA', (2, 1), (0, 0))
        image.putpixel((0, 0), (0, 255))
        omgezet = imageUtil.zetOmVoorJpg(image)
        assert omgezet.mode == 'RGB'
        assert omgezet.getpixel((0, 0)) == (0, 0, 0)
        assert omgezet.getpixel((1, 0)) == WIT

    def test_palet_met_transparantie_op_wit(self, imageUtil):
        image = Image.new('P', (2, 1), 0)
        image.putpalette([0, 0, 0, 255, 0, 0] + [0, 0, 0] * 254)
        image.putpixel((0, 0), 1)
        image.info['transparency'] = 0
        omgezet = imageUtil.zetOmVoorJpg(image)
        assert omgezet.mode == 'RGB'
        assert omgezet.getpixel((0, 0)) == ROOD
        assert omgezet.getpixel((1, 0)) == WIT

    @pytest.mark.parametrize('modus', ['P', 'CMYK', 'YCbCr', 'RGBX'])
    def test_overige_modi_worden_rgb(self, imageUtil, modus):
        assert imageUtil.zetOmVoorJpg(Image.new(modus, (4, 4))).mode == 'RGB'

    def test_zwart_wit_wordt_grijswaarden(self, imageUtil):
        image = Image.new('1', (4, 4), 1)
        image.putpixel((0, 0), 0)
        omgezet = imageUtil.zetOmVoorJpg(image)
        assert omgezet.mode == 'L'
        assert omgezet.getpixel((0, 0)) == 0 and omgezet.getpixel((1, 1)) == 255

    @pytest.mark.parametrize('modus', ['I;16', 'I;16B'])
    def test_16_bits_geschaald_naar_8_bits(self, imageUtil, modus):
        """Zoals de Delftse tekening kvtekeningpotter2d2.tif (waarden 4112-65535): niet alles wit."""
        image = Image.new(modus, (3, 1), 0)
        image.putpixel((1, 0), 32768)
        image.putpixel((2, 0), 65535)
        omgezet = imageUtil.zetOmVoorJpg(image)
        assert omgezet.mode == 'L'
        assert [omgezet.getpixel((x, 0)) for x in range(3)] == [0, 128, 255]

    def test_32_bits_geschaald_op_eigen_bereik(self, imageUtil):
        image = Image.new('I', (2, 1), -100)
        image.putpixel((1, 0), 100000)
        omgezet = imageUtil.zetOmVoorJpg(image)
        assert omgezet.mode == 'L'
        assert omgezet.getpixel((0, 0)) == 0 and omgezet.getpixel((1, 0)) == 255

    def test_32_bits_constant_buiten_bereik(self, imageUtil):
        omgezet = imageUtil.zetOmVoorJpg(Image.new('I', (2, 2), 1000))
        assert omgezet.mode == 'L' and omgezet.getextrema() == (255, 255)

    def test_float_binnen_bereik(self, imageUtil):
        omgezet = imageUtil.zetOmVoorJpg(Image.new('F', (2, 2), 100.0))
        assert omgezet.mode == 'L' and omgezet.getextrema() == (100, 100)


class TestPasOrientatieToe:
    """De EXIF-oriëntatie van een foto wordt toegepast; de formaten in de mediamap hebben geen EXIF."""

    def test_staande_foto_wordt_gedraaid(self, imageUtil, tmp_path):
        pad = str(tmp_path / 'staand.jpg')
        maakJpg(pad, grootte=(400, 200), orientatie=6)
        with Image.open(pad) as image:
            assert imageUtil.pasOrientatieToe(image).size == (200, 400)

    def test_zonder_exif_dezelfde_afbeelding(self, imageUtil):
        image = Image.new('RGB', (40, 20))
        assert imageUtil.pasOrientatieToe(image) is image


# ============================================================
# putImageInGrid
# ============================================================

class TestPutImageInGrid:

    def test_rgba_afbeelding_wordt_opgeslagen(self, imageUtil, mappen):
        """Tot issue 82 gaf dit 'cannot write mode RGBA as JPEG' voor alles behalve .png."""
        image = Image.new('RGBA', (400, 200), (0, 0, 0, 0))
        image.paste((255, 0, 0, 255), (0, 0, 200, 200))
        sml, med, groot = imageUtil.putImageInGrid(image, '/bron/profiel.psd', None, '/SY001/L Fotos', 'SY001')
        assert groot == '/SY001/L Fotos/profiel.jpg'
        assert openUitMedia(mappen, groot).mode == 'RGB'
        assert bijna(pixel(mappen, groot, (300, 100)), WIT)

    def test_zestien_bits_geeft_geen_nonetype_fout(self, imageUtil, mappen):
        """Tot issue 82: "'NoneType' object has no attribute 'copy'" (briefkaart op I;16 mislukte stil)."""
        image = Image.new('I;16', (300, 200), 40000)
        sml, med, groot = imageUtil.putImageInGrid(image, '/bron/tekening.tif', None, '/SY001', 'SY001')
        for pad in (sml, med, groot):
            assert openUitMedia(mappen, pad).mode == 'L'
        assert abs(pixel(mappen, groot, (10, 10))[0] - 156) <= 2

    def test_geen_afbeelding_geeft_duidelijke_fout(self, imageUtil, mappen):
        with pytest.raises(imageUtil.AfbeeldingFout, match='geen afbeelding om op te slaan'):
            imageUtil.putImageInGrid(None, '/bron/leeg.jpg', None, '/SY001', 'SY001')

    def test_afbeelding_van_de_aanroeper_blijft_ongewijzigd(self, imageUtil, mappen):
        image = Image.new('RGB', (2000, 1000), 'white')
        imageUtil.putImageInGrid(image, '/bron/groot.jpg', None, '/SY001', 'SY001')
        assert image.size == (2000, 1000)


# ============================================================
# adjustAndSaveFile
# ============================================================

class TestAdjustAndSaveFile:

    def verwerk(self, imageUtil, mappen, naam):
        collectie = NepCollectie()
        resultaat = imageUtil.adjustAndSaveFile(bronpad(mappen, naam), None, collectie)
        assert resultaat == 1
        document = collectie.documenten[0]
        for veld in ('imageThumbID', 'imageMiddleID', 'imageID'):
            assert os.path.isfile(os.path.join(str(mappen.media), document[veld].lstrip('/'))), veld
        return document

    def test_rgba_png(self, imageUtil, mappen):
        maakRgbaPng(bronpad(mappen, 'SY001_G003.png'))
        document = self.verwerk(imageUtil, mappen, 'SY001_G003.png')
        assert document['projectcd'] == 'SY001'
        assert document['fileType'] == '.png'
        assert document['mime_type'] == 'image/jpeg'
        assert document['imageID'] == '/SY001/L Fotos/SY001_G003.jpg'
        assert bijna(pixel(mappen, document['imageID'], (100, 100)), ROOD)
        assert bijna(pixel(mappen, document['imageID'], (300, 100)), WIT)

    def test_palet_gif(self, imageUtil, mappen):
        maakPaletGif(bronpad(mappen, 'SY001_G004.gif'))
        document = self.verwerk(imageUtil, mappen, 'SY001_G004.gif')
        assert document['fileType'] == '.gif'
        assert bijna(pixel(mappen, document['imageID'], (100, 100)), ROOD)
        assert bijna(pixel(mappen, document['imageID'], (300, 100)), WIT)

    def test_hoofdletter_extensie(self, imageUtil, mappen):
        """Een .PNG met alfakanaal ging vroeger mis: de omzetting keek naar '.png' in kleine letters."""
        maakRgbaPng(bronpad(mappen, 'SY001_G005.PNG'))
        document = self.verwerk(imageUtil, mappen, 'SY001_G005.PNG')
        assert document['fileType'] == '.png'
        assert document['imageID'] == '/SY001/L Fotos/SY001_G005.jpg'
        assert bijna(pixel(mappen, document['imageID'], (300, 100)), WIT)

    def test_exif_orientatie_toegepast(self, imageUtil, mappen):
        maakJpg(bronpad(mappen, 'SY001_G006.jpg'), grootte=(400, 200), orientatie=6)
        document = self.verwerk(imageUtil, mappen, 'SY001_G006.jpg')
        assert openUitMedia(mappen, document['imageID']).size == (200, 400)

    @pytest.mark.parametrize('naam,mime_type', [
        ('Dagrapport SY001.docx', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'),
        ('Dagrapport SY001.doc', 'application/msword'),
    ])
    def test_word_document_met_icoon(self, imageUtil, mappen, naam, mime_type):
        """Tot issue 82 zocht de extractie het icoon in de invoermap van de fotolijst."""
        inhoud = b'PK\x03\x04 geen echt document'
        with open(bronpad(mappen, naam), 'wb') as f:
            f.write(inhoud)
        document = self.verwerk(imageUtil, mappen, naam)
        assert document['mime_type'] == mime_type
        assert document['fileType'] == os.path.splitext(naam)[1]
        # Het grote formaat is het document zelf, de andere twee tonen het icoon
        assert document['imageID'] == '/SY001/L Fotos/' + naam
        with open(os.path.join(str(mappen.media), document['imageID'].lstrip('/')), 'rb') as f:
            assert f.read() == inhoud
        thumb = openUitMedia(mappen, document['imageThumbID'])
        assert thumb.mode == 'RGB' and thumb.size == (300, 200)

    def test_ontbrekend_icoon_geeft_duidelijke_fout(self, imageUtil, mappen, monkeypatch):
        monkeypatch.setattr(sys.modules['shared.config'], 'FILE_WORD_ICON', '/bestaat/niet/icoon.png')
        with open(bronpad(mappen, 'notitie.docx'), 'wb') as f:
            f.write(b'PK')
        with pytest.raises(imageUtil.AfbeeldingFout, match='FILE_WORD_ICON'):
            imageUtil.adjustAndSaveFile(bronpad(mappen, 'notitie.docx'), None, NepCollectie())

    def test_afgekapte_jpg_met_waarschuwing(self, imageUtil, mappen, caplog):
        """Zoals DC97_G0021_04.jpg (89 bytes te kort): verwerkt, met een waarschuwing in het log."""
        pad = bronpad(mappen, 'SY001_G007.jpg')
        maakJpg(pad, grootte=(400, 300), ruis=True)
        with open(pad, 'rb') as f:
            data = f.read()
        with open(pad, 'wb') as f:
            f.write(data[:-2000])
        with caplog.at_level('WARNING'):
            document = self.verwerk(imageUtil, mappen, 'SY001_G007.jpg')
        assert openUitMedia(mappen, document['imageID']).size == (400, 300)
        assert any('afgekapt' in r.getMessage() and 'SY001_G007.jpg' in r.getMessage() for r in caplog.records)
        # De instelling voor afgekapte bestanden geldt alleen voor dit ene bestand
        assert ImageFile.LOAD_TRUNCATED_IMAGES is False

    def test_beschadigde_lzw_tif_blijft_mislukt(self, imageUtil, mappen):
        """Zoals DB034_B018_LZW.tif: 'decoder error -2', met een melding die zegt wat er aan de hand is."""
        pad = bronpad(mappen, 'SY001_B002_LZW.tif')
        maakBeschadigdeLzwTif(pad)
        with pytest.raises(imageUtil.AfbeeldingFout) as fout:
            imageUtil.adjustAndSaveFile(pad, None, NepCollectie())
        melding = str(fout.value)
        assert 'SY001_B002_LZW.tif' in melding
        assert 'beschadigd' in melding and 'decoder error -2' in melding
        assert not os.listdir(str(mappen.media)), "Van een beschadigd bestand mag niets in de mediamap komen"

    def test_geen_afbeelding(self, imageUtil, mappen):
        pad = bronpad(mappen, 'SY001_G008.jpg')
        with open(pad, 'wb') as f:
            f.write(b'dit is geen jpg')
        with pytest.raises(imageUtil.AfbeeldingFout, match='kan niet als afbeelding geopend worden'):
            imageUtil.adjustAndSaveFile(pad, None, NepCollectie())

    def test_pdf_eerste_pagina(self, imageUtil, mappen, nepPdf):
        with open(bronpad(mappen, 'SY001_rapport.pdf'), 'wb') as f:
            f.write(b'%PDF-1.4')
        document = self.verwerk(imageUtil, mappen, 'SY001_rapport.pdf')
        assert document['mime_type'] == 'application/pdf'
        assert document['imageID'] == '/SY001/L Fotos/SY001_rapport.pdf'
        # Alleen de eerste pagina wordt omgezet
        assert nepPdf.aanroepen[0][1] == {'first_page': 1, 'last_page': 1}

    def test_pdf_zonder_paginas(self, imageUtil, mappen, nepPdf):
        """Een pdf zonder pagina gaf 'list index out of range'; nu een duidelijke melding."""
        nepPdf.paginas = []
        with open(bronpad(mappen, 'SY001_leeg.pdf'), 'wb') as f:
            f.write(b'%PDF-1.4')
        with pytest.raises(imageUtil.AfbeeldingFout, match="geen pagina"):
            imageUtil.adjustAndSaveFile(bronpad(mappen, 'SY001_leeg.pdf'), None, NepCollectie())

    def test_pdf_pagina_none(self, imageUtil, mappen, nepPdf):
        nepPdf.paginas = [None]
        with open(bronpad(mappen, 'SY001_none.pdf'), 'wb') as f:
            f.write(b'%PDF-1.4')
        with pytest.raises(imageUtil.AfbeeldingFout, match="geen pagina"):
            imageUtil.adjustAndSaveFile(bronpad(mappen, 'SY001_none.pdf'), None, NepCollectie())

    def test_onleesbare_pdf(self, imageUtil, mappen, nepPdf):
        nepPdf.fout = RuntimeError('Unable to get page count.')
        with open(bronpad(mappen, 'SY001_kapot.pdf'), 'wb') as f:
            f.write(b'geen pdf')
        with pytest.raises(imageUtil.AfbeeldingFout, match='de pdf kan niet gelezen worden.*Unable to get page count'):
            imageUtil.adjustAndSaveFile(bronpad(mappen, 'SY001_kapot.pdf'), None, NepCollectie())

    def test_rapportenlijst_zonder_projectcode_blijft_mislukt(self, imageUtil, mappen, tmp_path):
        """Zoals rapporten/DAR/Lijst met Delftse Archeologische Rapporten.doc (vraag voor de opdrachtgever)."""
        map_ = tmp_path / 'rapporten' / 'DAR'
        map_.mkdir(parents=True)
        pad = str(map_ / 'Lijst met Delftse Archeologische Rapporten.doc')
        with open(pad, 'wb') as f:
            f.write(b'doc')
        with pytest.raises(imageUtil.AfbeeldingFout, match='geen projectcode en geen rapportnummer'):
            imageUtil.adjustAndSaveFile(pad, None, NepCollectie())

    def test_vol_volume_blijft_herkenbaar_in_de_keten(self, imageUtil, mappen, monkeypatch):
        """image_import.vindOnherstelbareOorzaak zoekt de OSError in de keten van oorzaken (issue 70)."""
        maakJpg(bronpad(mappen, 'SY001_G009.jpg'))

        def volVolume(self, pad, *args, **kwargs):
            raise OSError(errno.ENOSPC, 'No space left on device', pad)

        monkeypatch.setattr(Image.Image, 'save', volVolume)
        with pytest.raises(Exception) as fout:
            imageUtil.adjustAndSaveFile(bronpad(mappen, 'SY001_G009.jpg'), None, NepCollectie())
        assert any(isinstance(e, OSError) and e.errno == errno.ENOSPC for e in ketenVan(fout.value))

    def test_sfeerfoto_en_onbekend_type_overgeslagen(self, imageUtil, mappen):
        maakJpg(bronpad(mappen, 'Sfeerfoto_SY001.jpg'))
        with open(bronpad(mappen, 'SY001_lijst.xlsx'), 'wb') as f:
            f.write(b'xlsx')
        collectie = NepCollectie()
        assert imageUtil.adjustAndSaveFile(bronpad(mappen, 'Sfeerfoto_SY001.jpg'), None, collectie) is None
        assert imageUtil.adjustAndSaveFile(bronpad(mappen, 'SY001_lijst.xlsx'), None, collectie) is None
        assert collectie.documenten == []


# ============================================================
# Documenticoon in de repository en in de images
# ============================================================

def laadConfig(monkeypatch, pad, naam='config_onder_test'):
    """Laad een shared/config.py met de minimale omgeving en zonder FILE_WORD_ICON."""
    for variabele in ('POSTGRES_DB', 'POSTGRES_USER', 'POSTGRES_PASSWORD'):
        monkeypatch.setenv(variabele, 'test')
    monkeypatch.delenv('FILE_WORD_ICON', raising=False)
    return laadModule(naam, pad)


def uitgeslotenDoorDockerignore(pad):
    """Geeft True als een pad (relatief aan de repository) door .dockerignore buiten de buildcontext valt.

    Benadering van de regels van Docker: een patroon geldt voor het pad en elke bovenliggende map,
    '**/' mag op elke diepte beginnen en een regel met '!' maakt een uitsluiting ongedaan.
    """
    with open(os.path.join(_project_root, '.dockerignore'), encoding='utf-8') as f:
        regels = [r.strip() for r in f if r.strip() and not r.strip().startswith('#')]
    delen = pad.split('/')
    kandidaten = ['/'.join(delen[:i]) for i in range(1, len(delen) + 1)]
    uitgesloten = False
    for regel in regels:
        uitzondering = regel.startswith('!')
        patroon = regel.lstrip('!').strip('/')
        for kandidaat in kandidaten:
            stukken = kandidaat.split('/')
            if patroon.startswith('**/'):
                past = any(fnmatch.fnmatch('/'.join(stukken[j:]), patroon[3:]) for j in range(len(stukken)))
            else:
                past = fnmatch.fnmatch(kandidaat, patroon)
            if past:
                uitgesloten = not uitzondering
    return uitgesloten


class TestDocumenticoon:
    """Het documenticoon hoort bij de code (shared/afbeeldingen) en zit in beide images."""

    def test_icoon_bestaat_en_is_een_kleine_afbeelding(self):
        assert os.path.isfile(ICOON)
        assert os.path.getsize(ICOON) < 100_000
        with Image.open(ICOON) as image:
            image.load()
            assert image.format == 'PNG'
            assert image.size[0] >= 300 and image.size[1] >= 200

    def test_standaard_wijst_naar_het_icoon_in_shared(self, monkeypatch):
        config = laadConfig(monkeypatch, CONFIG)
        assert os.path.normpath(config.FILE_WORD_ICON) == os.path.normpath(ICOON)
        assert os.path.isfile(config.FILE_WORD_ICON)

    def test_omgevingsvariabele_overschrijft(self, monkeypatch):
        for variabele in ('POSTGRES_DB', 'POSTGRES_USER', 'POSTGRES_PASSWORD'):
            monkeypatch.setenv(variabele, 'test')
        monkeypatch.setenv('FILE_WORD_ICON', '/eigen/icoon.png')
        config = laadModule('config_met_eigen_icoon', CONFIG)
        assert config.FILE_WORD_ICON == '/eigen/icoon.png'

    @pytest.mark.parametrize('service,doel', sorted(SHARED_IN_IMAGE.items()))
    def test_icoon_klopt_in_de_image(self, monkeypatch, tmp_path, service, doel):
        """De Dockerfile kopieert shared/ in zijn geheel; config.py vindt het icoon daar naast zich."""
        with open(os.path.join(_project_root, 'services', service, 'Dockerfile'), encoding='utf-8') as f:
            dockerfile = f.read()
        if service == 'airflow':
            assert re.search(r'^COPY .*\./shared \./dags/shared$', dockerfile, re.M)
        else:
            assert re.search(r'^COPY \./shared /app/app/shared$', dockerfile, re.M)
        assert not uitgeslotenDoorDockerignore('shared/afbeeldingen/document.png')

        # Bootst de map in de image na: <doel>/config.py en <doel>/afbeeldingen/document.png
        map_in_image = tmp_path / doel.lstrip('/')
        (map_in_image / 'afbeeldingen').mkdir(parents=True)
        shutil.copy(CONFIG, map_in_image / 'config.py')
        shutil.copy(ICOON, map_in_image / 'afbeeldingen' / 'document.png')
        config = laadConfig(monkeypatch, str(map_in_image / 'config.py'), naam=f'config_{service}')
        assert config.FILE_WORD_ICON == os.path.join(str(map_in_image), 'afbeeldingen', 'document.png')
        assert os.path.isfile(config.FILE_WORD_ICON)

    def test_airflow_test_mount_shared(self):
        """In de testomgevingen mount airflow-test ./shared over de map uit de image heen."""
        for compose in ('docker-compose.test.yml', 'docker-compose.delft-test.yml'):
            with open(os.path.join(_project_root, compose), encoding='utf-8') as f:
                assert './shared:/opt/airflow/dags/shared' in f.read(), compose

    def test_geen_icoon_meer_in_de_invoermap(self):
        """Geen configuratiesjabloon of compose-bestand wijst nog naar het oude Word-logo in de fotolijst."""
        bestanden = [os.path.join('config', n) for n in os.listdir(os.path.join(_project_root, 'config'))
                     if n.endswith('.env.example')]
        bestanden += [os.path.join('deploy', 'config', n)
                      for n in os.listdir(os.path.join(_project_root, 'deploy', 'config'))]
        bestanden += [n for n in os.listdir(_project_root) if n.startswith('docker-compose')]
        bestanden += [os.path.join('deploy', 'docker-compose.yml')]
        for bestand in bestanden:
            with open(os.path.join(_project_root, bestand), encoding='utf-8') as f:
                inhoud = f.read()
            assert 'microsoft-word-logo' not in inhoud, bestand
