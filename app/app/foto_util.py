import PIL
import io
import os
from PIL import Image, ExifTags
import logging
import copy
from models import Bestand
import shared.config as config
import shared.image_util as image_util

from PyPDF2 import PdfReader, PdfWriter
import pdf2image



logger = logging.getLogger()


def rotateBestand(bestand: Bestand, degrees=90):
    try:
        fullfilename = os.path.join(config.AIRFLOW_OUTPUT_MEDIA, bestand.imageID.lstrip('/\\'))
        if fullfilename.lower().endswith('pdf'): 
            reader = PdfReader(fullfilename)
            writer = PdfWriter()
            for page in reader.pages:
                page.rotate(180 + degrees)
                writer.add_page(page)
            with open(fullfilename, "wb") as pdf_out:
                writer.write(pdf_out)

            images = pdf2image.convert_from_path(fullfilename)
            image = images[0]
            image_util.putImageInGrid(image, fullfilename, None, bestand.directory, '', pdf=True)
        else:
            image = Image.open(fullfilename)
            image = image.rotate(degrees, expand = 1) 
            image_util.putImageInGrid(image, fullfilename, None, bestand.directory, '')

    except Exception as err:
        print(err)
        logger.warning('Error while rotating image with message: ' + str(err))

    return bestand
