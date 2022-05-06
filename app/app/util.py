import pymongo
import gridfs
import sys
import magic
import PIL
import io
from PIL import Image, ExifTags
import logging
import copy
from app.models import Foto
from gridfs import GridFS
from gridfs.errors import NoFile
from bson.objectid import ObjectId
import config



logger = logging.getLogger()


def shrinkAndSaveImage(filename, size, fs, postcard=False): 
    try:
        image = Image.open(filename, 'r')
        mime_type = magic.from_file(filename, mime=True)
        
        if hasattr(image, '_getexif'): # only present in JPEGs
            for orientation in ExifTags.TAGS.keys(): 
                if ExifTags.TAGS[orientation]=='Orientation':
                    break 
            e = image._getexif()       # returns None if no EXIF data
            if e is not None:
                exif=dict(e.items())
                orientation = exif[orientation] 

                if orientation == 3:   image = image.transpose(Image.ROTATE_180)
                elif orientation == 6: image = image.transpose(Image.ROTATE_270)
                elif orientation == 8: image = image.transpose(Image.ROTATE_90)

        image.thumbnail(size, Image.ANTIALIAS)

        # if size of picture does not fit paste it on a blank picture
        if postcard:
            img_w, img_h = image.size

            mode = image.mode
            if len(mode) == 1:  # L, 1
                new_background = (255)
            if len(mode) == 3:  # RGB
                new_background = (255, 255, 255)
            if len(mode) == 4:  # RGBA, CMYK
                new_background = (255, 255, 255, 255)
            background = Image.new(mode, size, new_background)

            bg_w, bg_h = background.size
            offset = ((bg_w - img_w) // 2, (bg_h - img_h) // 2)
            background.paste(image, offset)
            image = background

        width = str(size[0])
        height = str(size[1])
        
        b = io.BytesIO()
        image.save(b, "JPEG")
        b.seek(0)

        return fs.put(b, content_type=mime_type, height=height, width=width, filename=filename)

    except Exception as err:
        print(err)
        logger.warning('Error while reszing image with message: ' + str(err))



def putImage(fs, image, filename, content_type, size=None, postcard=False):
    if size:
        image.thumbnail(size, Image.BICUBIC)

    # if size of picture does not fit paste it on a blank picture
    if postcard:
        img_w, img_h = image.size

        mode = image.mode
        if len(mode) == 1:  # L, 1
            new_background = (255)
        if len(mode) == 3:  # RGB
            new_background = (255, 255, 255)
        if len(mode) == 4:  # RGBA, CMYK
            new_background = (255, 255, 255, 255)
        background = Image.new(mode, size, new_background)

        bg_w, bg_h = background.size
        offset = ((bg_w - img_w) // 2, (bg_h - img_h) // 2)
        background.paste(image, offset)
        image = background
        

    b = io.BytesIO()
    image.save(b, "JPEG")
    b.seek(0)

    return fs.put(b, content_type=content_type, height=image.height, width=image.width, filename=filename)


def rotateImage(foto: Foto, degrees=90):
    myclient = pymongo.MongoClient(str(config.MONGO_URI))
    filesdb = myclient[str(config.DB_FILES)]
    fs = gridfs.GridFS(filesdb)


    try:
        uuid_old = foto.imageUUID
        uuid_middle_old = foto.imageMiddleUUID       
        uuid_thumb_old = foto.imageThumbUUID       

        file_object = fs.get(ObjectId(foto.imageUUID))
        image = Image.open(io.BytesIO(file_object.read()))
        image = image.rotate(degrees, expand = 1) 
        foto.imageUUID = str(putImage(fs, image, file_object.name, file_object.content_type))
        foto.imageMiddleUUID = str(putImage(fs, image, file_object.name, file_object.content_type, size=config.IMAGE_MIDDLE_SIZE))
        foto.imageThumbUUID = str(putImage(fs, image, file_object.name, file_object.content_type, size=config.IMAGE_THUMB_SIZE, postcard=True))

        fs.delete(ObjectId(uuid_old))
        fs.delete(ObjectId(uuid_middle_old))
        fs.delete(ObjectId(uuid_thumb_old))

    except Exception as err:
        print(err)
        logger.warning('Error while rotating image with message: ' + str(err))

    return foto





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