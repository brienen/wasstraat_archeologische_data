"""
Kantelen van bestanden in de mediamap (acties Kantelen Linksom en Kantelen Rechtsom, issue 34).

Een bestand heeft drie formaten in de mediamap (config.AIRFLOW_OUTPUT_MEDIA). Def_Bestand
bewaart de paden relatief aan die map: imageID (groot formaat, of de pdf zelf), imageMiddleID
(briefkaartformaat) en imageThumbID (thumbnail). Kantelen draait het grote formaat en maakt de
andere twee daaruit opnieuw met dezelfde functie als de extractie (image_util.putImageInGrid),
zodat ze dezelfde afmetingen en opmaak houden.
"""
import io
import logging
import os

from PIL import Image, ImageOps
from PyPDF2 import PdfReader, PdfWriter
import pdf2image

import shared.config as config
import shared.image_util as image_util


logger = logging.getLogger()

# Bestanden waarvan de voorbeelden een vast pictogram zijn; die vallen niet te kantelen
NIET_TE_KANTELEN = ('.doc', '.docx')


class KantelFout(Exception):
    """Het bestand kan niet gekanteld worden; de tekst is bedoeld voor de gebruiker."""


def mediaPad(pad):
    """
    Geef het volledige pad in de mediamap bij een pad uit Def_Bestand.

    Args:
        pad: Pad relatief aan de mediamap, zoals imageID (begint met '/').

    Returns:
        str: Pad onder config.AIRFLOW_OUTPUT_MEDIA.
    """
    return os.path.join(config.AIRFLOW_OUTPUT_MEDIA, pad.lstrip('/\\'))


def kantelPdf(bestandsnaam, degrees):
    """
    Kantel alle pagina's van een pdf en schrijf hem ter plekke terug.

    PyPDF2 draait met de klok mee en PIL tegen de klok in; met -degrees % 360 draait de pdf
    dezelfde kant op als een foto. De nieuwe inhoud wordt eerst in het geheugen opgebouwd en
    daarna over het bestaande bestand geschreven, zodat eigenaar en rechten gelijk blijven.

    Args:
        bestandsnaam: Volledig pad van de pdf in de mediamap.
        degrees: Aantal graden linksom (negatief is rechtsom), een veelvoud van 90.
    """
    reader = PdfReader(bestandsnaam)
    writer = PdfWriter()
    for page in reader.pages:
        page.rotate(-degrees % 360)
        writer.add_page(page)
    inhoud = io.BytesIO()
    writer.write(inhoud)
    with open(bestandsnaam, 'wb') as pdf_out:
        pdf_out.write(inhoud.getvalue())


def rotateBestand(bestand, degrees=90):
    """
    Kantel een bestand in de mediamap en maak het briefkaartformaat en de thumbnail opnieuw.

    Positieve graden draaien linksom (tegen de klok in), negatieve rechtsom, net als PIL. Van
    een foto of tekening wordt het grote formaat gekanteld (imageID, altijd een jpg, ook bij
    een tif- of png-bron); van een pdf worden alle pagina's gekanteld en komen de voorbeelden
    van de eerste pagina. Alle bestanden komen in de map van imageID, op dezelfde namen als bij
    de extractie, en worden ter plekke overschreven. Wijken de paden in het bestand daarvan af,
    dan worden ze bijgewerkt en moet het bestand worden opgeslagen.

    Args:
        bestand: Bestand (of subklasse) met imageID, imageMiddleID en imageThumbID.
        degrees: Aantal graden, een veelvoud van 90.

    Returns:
        bool: True als een van de paden in het bestand is veranderd.

    Raises:
        KantelFout: Het bestand heeft geen afbeelding, is een Word-document of ontbreekt in
            de mediamap.
        ValueError: degrees is geen veelvoud van 90.
    """
    if degrees % 90 != 0:
        raise ValueError(f'Kantelen kan alleen in veelvouden van 90 graden, niet {degrees}')
    if not bestand.imageID:
        raise KantelFout(f'{bestand.fileName}: geen afbeelding in de mediamap')
    groot = mediaPad(bestand.imageID)
    extensie = os.path.splitext(groot)[1].lower()
    if extensie in NIET_TE_KANTELEN:
        raise KantelFout(f'{bestand.fileName}: een Word-document kan niet gekanteld worden')
    if not os.path.isfile(groot):
        raise KantelFout(f'{bestand.fileName}: {bestand.imageID} ontbreekt in de mediamap')

    if extensie == '.pdf':
        kantelPdf(groot, degrees)
        image = pdf2image.convert_from_path(groot, first_page=1, last_page=1)[0]
        filetype = '.pdf'
    else:
        with Image.open(groot) as origineel:
            # Het grote formaat heeft geen EXIF-oriëntatie meer (de extractie past die toe);
            # mocht die er toch zijn, dan eerst toepassen zodat de foto niet verspringt
            image = ImageOps.exif_transpose(origineel).rotate(degrees, expand=True)
        filetype = '.jpg'

    directory = os.path.dirname(bestand.imageID)
    nieuw = image_util.putImageInGrid(image, groot, None, directory, '', filetype=filetype)
    oud = (bestand.imageThumbID, bestand.imageMiddleID, bestand.imageID)
    bestand.imageThumbID, bestand.imageMiddleID, bestand.imageID = nieuw
    logger.info(f'{bestand.imageID} {degrees} graden gekanteld')
    return tuple(nieuw) != oud
