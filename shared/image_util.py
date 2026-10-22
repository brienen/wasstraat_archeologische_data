"""Afbeeldingen, pdf's en Word-documenten omzetten naar drie formaten in de mediamap.

Gebruikt door de extractie (``adjustAndSaveFile``, via ``wasstraat/image_import.py``)
en door de webapplicatie (uploaden en kantelen, ``putImageInGrid``). Per bronbestand
komen er een groot formaat, een briefkaartformaat (``-med.jpg``) en een thumbnail
(``-sml.jpg``) in ``config.AIRFLOW_OUTPUT_MEDIA``.

- Een pdf krijgt de eerste pagina als voorbeeld; het groot formaat is de pdf zelf.
- Een Word-document krijgt een vast documenticoon als voorbeeld
  (``config.FILE_WORD_ICON``, standaard ``shared/afbeeldingen/document.png``);
  het groot formaat is het document zelf.
- Een afbeelding wordt eerst gedraaid volgens haar EXIF-oriëntatie en daarna
  omgezet naar een kleurmodus die een jpg kan bevatten (``zetOmVoorJpg``).
- Een afgekapt bestand (het einde ontbreekt) wordt met een waarschuwing toch
  geladen; een bestand dat niet te decoderen is, geeft een ``AfbeeldingFout``.
"""
# Import the os module, for the os.walk function
import os
import re
import pathlib
import shutil

import pdf2image
from PIL import ExifTags, Image, ImageFile, ImageOps

import shared.config as config

# Import app code
import logging
logger = logging.getLogger()

# Prevent error message when reading large files, see https://stackoverflow.com/questions/25705773/image-cropping-tool-python
Image.MAX_IMAGE_PIXELS = None

# Documenten die geen afbeelding zijn en het documenticoon als voorbeeld krijgen, met hun mime-type
DOCUMENT_MIME_TYPES = {
    '.doc': 'application/msword',
    '.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
}
MIME_JPG = 'image/jpeg'
MIME_PDF = 'application/pdf'

# Kleurmodi die als jpg opgeslagen kunnen worden zonder omzetting
JPG_MODI = ('RGB', 'L')
# Kleurmodi met een alfakanaal; die komen op een witte achtergrond
ALFA_MODI = ('RGBA', 'RGBa', 'LA', 'PA')
ACHTERGROND = (255, 255, 255)


class AfbeeldingFout(Exception):
    """Bekend probleem met één bronbestand, met een melding die de oorzaak noemt.

    Bijvoorbeeld een beschadigd bestand, een pdf zonder pagina's of een
    bestandsnaam zonder projectcode. Het bestand krijgt in ``Filenames`` de
    status mislukt; de extractie gaat door met het volgende bestand.
    """


def pasOrientatieToe(image):
    """Draai en spiegel een afbeelding volgens haar EXIF-oriëntatie.

    Camera's slaan een staande foto vaak liggend op met een EXIF-tag die zegt
    hoe hij gedraaid moet worden. De formaten in de mediamap bevatten geen EXIF
    meer, dus zonder deze stap zou zo'n foto op zijn kant staan.

    Args:
        image: PIL-afbeelding

    Returns:
        De gedraaide afbeelding, of dezelfde afbeelding als er niets te draaien is
    """
    try:
        orientatie = image.getexif().get(ExifTags.Base.Orientation, 1)
    except Exception as err:
        logger.warning(f"EXIF-gegevens niet leesbaar, oriëntatie niet toegepast: {err}")
        return image
    if orientatie in (2, 3, 4, 5, 6, 7, 8):
        return ImageOps.exif_transpose(image)
    return image


def zetOmVoorJpg(image):
    """Zet een afbeelding om naar een kleurmodus die als jpg opgeslagen kan worden (RGB of L).

    De omzetting hangt af van de kleurmodus, niet van de extensie van het bestand:

    - RGB en L blijven ongewijzigd;
    - een alfakanaal (RGBA, LA, PA) of transparantie (een palet met een
      transparante kleur) komt op een witte achtergrond, als RGB;
    - zwart-wit (1) wordt L, zodat het verkleinen vloeiend gaat (een
      zwart-witafbeelding kan alleen met 'nearest' verkleind worden, waarbij
      dunne lijnen wegvallen);
    - 16-bits grijswaarden (I;16) worden L, geschaald van 0-65535 naar 0-255;
      32-bits (I, F) worden L, geschaald van het eigen bereik naar 0-255;
    - alle andere modi (P, CMYK, YCbCr, LAB, ...) worden RGB.

    Args:
        image: PIL-afbeelding

    Returns:
        Afbeelding in modus RGB of L
    """
    modus = image.mode
    if modus in JPG_MODI:
        return image
    if modus == '1':
        return image.convert('L')
    if modus.startswith('I;16'):
        return image.convert('I').point(lambda v: v * (1 / 256)).convert('L')
    if modus in ('I', 'F'):
        laag, hoog = image.getextrema()
        if laag >= 0 and hoog <= 255:
            return image.convert('L')
        if hoog == laag:
            return Image.new('L', image.size, 255 if hoog > 255 else 0)
        schaal = 255 / (hoog - laag)
        return image.point(lambda v: v * schaal - laag * schaal).convert('L')
    if modus in ALFA_MODI or 'transparency' in image.info:
        rgba = image.convert('RGBA')
        achtergrond = Image.new('RGB', rgba.size, ACHTERGROND)
        achtergrond.paste(rgba, mask=rgba.getchannel('A'))
        return achtergrond
    return image.convert('RGB')


def _isAfgekapt(err):
    """Geeft True als een leesfout van Pillow betekent dat het einde van het bestand ontbreekt."""
    return isinstance(err, OSError) and 'truncated' in str(err)


def openAfbeelding(fullfilename):
    """Open een afbeelding en lees de pixels in.

    Een afgekapt bestand (het einde ontbreekt, bijvoorbeeld na een onderbroken
    kopie) wordt toch geladen, met een waarschuwing in het log: het ontbrekende
    deel blijft grijs, wat beter is dan geen voorbeeld. Een bestand dat niet te
    decoderen is (zoals 'decoder error -2' bij een beschadigde LZW-tif) of geen
    afbeelding is, geeft een AfbeeldingFout.

    Args:
        fullfilename: pad van het bronbestand

    Returns:
        De geladen PIL-afbeelding

    Raises:
        AfbeeldingFout: als het bestand geen leesbare afbeelding is
    """
    try:
        image = Image.open(fullfilename)
    except Exception as err:
        raise AfbeeldingFout(f"{fullfilename} kan niet als afbeelding geopend worden: {err}") from err

    try:
        image.load()
        return image
    except MemoryError:
        image.close()
        raise
    except Exception as err:
        image.close()
        if not _isAfgekapt(err):
            raise AfbeeldingFout(f"{fullfilename} is beschadigd en kan niet gedecodeerd worden ({err}); "
                                 f"vervang het bronbestand door een onbeschadigde versie") from err
        melding = str(err)

    logger.warning(f"{fullfilename} is afgekapt ({melding}); het bestand wordt toch verwerkt, "
                   f"het ontbrekende deel van de afbeelding blijft grijs. Vervang het bronbestand als dat kan.")
    vorige = ImageFile.LOAD_TRUNCATED_IMAGES
    ImageFile.LOAD_TRUNCATED_IMAGES = True
    try:
        image = Image.open(fullfilename)
        image.load()
        return image
    except Exception as err:
        raise AfbeeldingFout(f"{fullfilename} is afgekapt en ook zo niet te lezen: {err}") from err
    finally:
        ImageFile.LOAD_TRUNCATED_IMAGES = vorige


def eerstePaginaVanPdf(fullfilename):
    """Zet de eerste pagina van een pdf om naar een afbeelding.

    Args:
        fullfilename: pad van de pdf

    Returns:
        PIL-afbeelding van de eerste pagina

    Raises:
        AfbeeldingFout: als de pdf niet te lezen is of geen pagina oplevert
    """
    try:
        paginas = pdf2image.convert_from_path(fullfilename, first_page=1, last_page=1)
    except Exception as err:
        raise AfbeeldingFout(f"{fullfilename}: de pdf kan niet gelezen worden ({err})") from err
    if not paginas or paginas[0] is None:
        raise AfbeeldingFout(f"{fullfilename}: de pdf heeft geen pagina die als afbeelding omgezet kan worden")
    return paginas[0]


def openDocumentIcoon():
    """Open het documenticoon dat als voorbeeld van een Word-document dient (config.FILE_WORD_ICON).

    Returns:
        De geladen PIL-afbeelding

    Raises:
        AfbeeldingFout: als het icoon ontbreekt of onleesbaar is
    """
    pad = config.FILE_WORD_ICON
    if not os.path.isfile(pad):
        raise AfbeeldingFout(f"Het documenticoon {pad} (FILE_WORD_ICON) ontbreekt; het hoort bij de code "
                             f"(shared/afbeeldingen/document.png). Laat FILE_WORD_ICON leeg of wijs een bestaand bestand aan.")
    return openAfbeelding(pad)


def adjustImage(image: Image, size, postcard=False):
    """Verklein een afbeelding tot binnen size, met postcard=True gecentreerd op een wit vlak van precies size.

    Vergroot nooit. De afbeelding staat al in modus RGB of L (zetOmVoorJpg) en
    is al gedraaid volgens haar EXIF-oriëntatie (pasOrientatieToe). Fouten worden
    niet ingeslikt: tot issue 82 gaf een fout hier None terug, wat pas later als
    "'NoneType' object has no attribute 'copy'" zichtbaar werd.

    Args:
        image: PIL-afbeelding (wordt aangepast)
        size: (breedte, hoogte)
        postcard: True voor een vlak van precies size met een witte rand

    Returns:
        De verkleinde afbeelding
    """
    image.thumbnail(size)

    # if size of picture does not fit paste it on a blank picture
    if postcard:
        img_w, img_h = image.size
        background = Image.new(image.mode, size, 'white')
        bg_w, bg_h = background.size
        offset = ((bg_w - img_w) // 2, (bg_h - img_h) // 2)
        background.paste(image, offset)
        image = background

    return image



def adjustAndSaveFile(fullfilename, fs, collection):
    """Maak de drie formaten van één bronbestand en leg het vast in de collectie Plaatjes.

    Args:
        fullfilename: pad van het bronbestand
        fs: GridFS (niet meer gebruikt; de formaten staan in de mediamap)
        collection: de collectie Plaatjes

    Returns:
        Het _id van het nieuwe document, of None als het bestand bewust is
        overgeslagen (niet-ondersteund bestandstype of sfeerfoto)

    Raises:
        AfbeeldingFout: bij een bekend probleem met dit bestand (beschadigd,
            pdf zonder pagina's, geen projectcode of rapportnummer in de naam)
        Exception: bij een onbekende fout, met de oorspronkelijke fout als oorzaak
    """
    try:
        filename, file_extension = os.path.splitext(fullfilename)
        dir, filename = os.path.split(fullfilename)
        if config.AIRFLOW_INPUT_IMAGES in dir:
            dir = re.sub('^' + config.AIRFLOW_INPUT_IMAGES, '', dir)

        if file_extension.lower() not in config.IMAGE_EXTENSIONS:
            return None

        # If image is sfeerfoto then ignore to not add pictures of people
        if 'Sfeerfoto' in fullfilename:
            return None

        # Get projectcd
        rapportnr = None
        projectcd = fullfilename.replace(config.AIRFLOW_INPUT_IMAGES + '/','')
        projectcd_srch = re.search('^([A-Z0-9]+).*', projectcd)
        if projectcd_srch:
            projectcd = re.search('^([A-Z0-9]+).*', projectcd).group(1)
        elif 'DAR' in filename or "DAN" in filename:
            projectcd = None
            dir = '/rapportage'
            rapportnr, file_extension = os.path.splitext(filename)
        else:
            raise AfbeeldingFout(f"{fullfilename}: geen projectcode en geen rapportnummer. Het pad begint niet met "
                                 f"een projectmap en de bestandsnaam bevat geen DAN of DAR; het bestand wordt niet verwerkt.")


        # First read image and make 3 versions with different sizes. And put them in a list
        extensie = file_extension.lower()
        if extensie == '.pdf':
            image = eerstePaginaVanPdf(fullfilename)
            filetype, mime_type = '.pdf', MIME_PDF
        elif extensie in DOCUMENT_MIME_TYPES:
            image = openDocumentIcoon()
            filetype, mime_type = extensie, DOCUMENT_MIME_TYPES[extensie]
        else:
            image = openAfbeelding(fullfilename)
            filetype, mime_type = '.jpg', MIME_JPG
        image_dict_sml, image_dict_med, image_dict_big = putImageInGrid(image, fullfilename, fs, dir, projectcd, filetype=filetype)

        # Insert a record with metadata
        if projectcd:
            return collection.insert_one({
                'fileName': filename, 'fullFileName': fullfilename, 'imageID': str(image_dict_big), 'imageMiddleID': str(image_dict_med), 'imageThumbID': str(image_dict_sml),
                'fileType': file_extension.lower(), 'directory': dir, 'mime_type': mime_type, 'projectcd': projectcd
                }).inserted_id
        else:
            return collection.insert_one({
                'fileName': filename, 'fullFileName': fullfilename, 'imageID': str(image_dict_big), 'imageMiddleID': str(image_dict_med), 'imageThumbID': str(image_dict_sml),
                'fileType': file_extension.lower(), 'directory': dir, 'mime_type': mime_type, 'rapportnr': rapportnr
                }).inserted_id

    except AfbeeldingFout as err:
        logger.error(str(err))
        raise

    except Exception as err:
        msg = f"Onbekende fout bij het bewaren van {fullfilename}, met tekst: {err}"
        logger.error(msg)
        raise Exception(msg) from err



def putImageInGrid(image: Image, fullfilename, fs, dir, projectcd, filetype='.jpg'):
    """Sla de drie formaten van een afbeelding op in de mediamap.

    De afbeelding wordt eerst gedraaid volgens haar EXIF-oriëntatie en omgezet
    naar RGB of L (zetOmVoorJpg), ongeacht de extensie van het bronbestand.

    Args:
        image: PIL-afbeelding (voor een pdf de eerste pagina, voor een Word-document het icoon)
        fullfilename: pad van het bronbestand
        fs: niet meer gebruikt
        dir: map onder de mediamap
        projectcd: niet meer gebruikt
        filetype: '.jpg' om het groot formaat als jpg te maken; '.pdf', '.doc' of
            '.docx' om het bronbestand zelf als groot formaat te kopiëren

    Returns:
        Tuple (thumbnail, briefkaartformaat, groot formaat): paden relatief aan de mediamap
    """
    try:
        if image is None:
            raise AfbeeldingFout(f"{fullfilename}: geen afbeelding om op te slaan")

        basename = os.path.basename(fullfilename)
        basename_noext, file_extension = os.path.splitext(basename)

        image = pasOrientatieToe(image)
        # Grayscale images need special attention for not distoring
        if 'lzw' in basename.lower() and 'tif' in file_extension.lower():
            image = ImageOps.grayscale(image)
        image = zetOmVoorJpg(image)

        img_med = adjustImage(image.copy(), config.IMAGE_SIZE_MIDDLE, postcard=True)
        img_sml = img_med.copy()
        img_sml.thumbnail(config.IMAGE_SIZE_THUMB)

        #Set dir and Create dir if not exists before saving file
        if config.AIRFLOW_INPUT_IMAGES in dir:
            dir = re.sub('^' + config.AIRFLOW_INPUT_IMAGES, '', dir)
        pathlib.Path(os.path.join(config.AIRFLOW_OUTPUT_MEDIA, dir.lstrip('/\\'))).mkdir(parents=True, exist_ok=True)

        # Loop over all versions and store them in the filestore
        file_id_sml = os.path.join(dir, basename_noext + '-sml.jpg')
        img_sml.save(os.path.join(config.AIRFLOW_OUTPUT_MEDIA, file_id_sml.lstrip('/\\')))

        file_id_med = os.path.join(dir, basename_noext + '-med.jpg')
        img_med.save(os.path.join(config.AIRFLOW_OUTPUT_MEDIA, file_id_med.lstrip('/\\')))

        if filetype != '.jpg':
            file_id = os.path.join(dir, basename_noext + filetype)
            filename_to = os.path.join(config.AIRFLOW_OUTPUT_MEDIA, file_id.lstrip('/\\'))
            if not fullfilename == filename_to:
                shutil.copy(fullfilename, filename_to)
        else:
            file_id = os.path.join(dir, basename_noext + '.jpg')
            #'image': adjustImage(image_dict_big, config.IMAGE_SIZE_BIGGEST if not lzw else config.IMAGE_SIZE_LZW) # grayscale images can have more pixels
            img_big = adjustImage(image.copy(), config.IMAGE_SIZE_BIGGEST)
            img_big.save(os.path.join(config.AIRFLOW_OUTPUT_MEDIA, file_id.lstrip('/\\')))

        return file_id_sml, file_id_med, file_id

    except AfbeeldingFout:
        raise

    except Exception as err:
        msg = f"Onbekende fout bij het in grid plaatsen van image {fullfilename}, met tekst: {str(err)}"
        logger.error(msg)
        raise Exception(msg) from err
