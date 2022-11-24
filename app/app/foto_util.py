import PIL
import io
import os
from PIL import Image, ExifTags
import logging
import copy
from models import Foto
import shared.config as config
import shared.image_util as image_util

logger = logging.getLogger()


def rotateImage(foto: Foto, degrees=90):
    try:
        image = Image.open(os.path.join(config.AIRFLOW_OUTPUT_MEDIA, foto.imageUUID.lstrip('/\\')))
        image = image.rotate(degrees, expand = 1) 
        image_util.putImageInGrid(image, foto.fileName, None, foto.directory, '')

    except Exception as err:
        print(err)
        logger.warning('Error while rotating image with message: ' + str(err))

    return foto
