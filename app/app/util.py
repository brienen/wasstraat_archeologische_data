import pymongo
import gridfs
import sys
import magic
import PIL
import io
from PIL import Image, ExifTags
import logging
import copy



logger = logging.getLogger()

def shrinkAndSaveImage(file, filename, size, fs): 
    try:
        image = Image.open(file)
        mime_type = 'image/jpeg'
        #image = shrinkImage(image, size)
        
        if hasattr(image, '_getexif'): # only present in JPEGs
            try:
                for orientation in ExifTags.TAGS.keys():
                    if ExifTags.TAGS[orientation]=='Orientation':
                        break

                e = image._getexif()       # returns None if no EXIF data
                if e is not None:
                    exif=dict(e.items())
                    if orientation in exif:
                        orientation = exif[orientation] 

                        if orientation == 3:   image = image.transpose(Image.ROTATE_180)
                        elif orientation == 6: image = image.transpose(Image.ROTATE_270)
                        elif orientation == 8: image = image.transpose(Image.ROTATE_90)
            except Exception as exif_err:
                logger.warning('Error while getting EXIF-information from image with message: ' + str(exif_err))

        image.thumbnail(size, Image.ANTIALIAS)
        width = str(size[0])
        height = str(size[1])
        
        b = io.BytesIO()
        image.save(b, "JPEG")
        b.seek(0)

        return fs.put(b, content_type=mime_type, height=height, width=width, filename=filename)

    except Exception as err:
        print(err)
        logger.error('Error while shrinking image with message: ' + str(err))




def removeFieldFromFieldset(fieldsets, field):
    fieldsets = copy.deepcopy(fieldsets)
    
    for fieldset in fieldsets:
        if 'fields' in fieldset[1]:
            lst = list(fieldset[1]['fields'])
            fieldset[1]['fields'] = list(filter(lambda a: a != field, lst))
        else:
            for column in fieldset[1]['columns']:
                lst = list(column['fields'])
                column['fields'] = list(filter(lambda a: a != field, lst))
                
    return fieldsets