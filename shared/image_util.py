# Import the os module, for the os.walk function
import os
import config
import io
 
import magic
from PIL import Image, ExifTags

# Import app code
import logging
logger = logging.getLogger()




def adjustImage(image: Image, size, postcard=False): 
    try:
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

        image.thumbnail(size)

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

        return image

    except Exception as err:
        logger.warning('Error while adjusting image with message: ' + str(err))



def adjustAndSaveFile(fullfilename, fs, collection):
    try:
        filename, file_extension = os.path.splitext(fullfilename)
        dir, filename = os.path.split(fullfilename)
        if file_extension.lower() not in config.IMAGE_EXTENSIONS:
            return None

        # First read image and make 3 versions with different sizes. And put them in a list 
        image = Image.open(fullfilename, 'r')
        mime_type = magic.from_file(fullfilename, mime=True)

        lst_images = []
        image_dict_big = {
            'image': adjustImage(image, config.IMAGE_SIZE_BIGGEST),
            'size': config.IMAGE_SIZE_BIGGEST
        }
        lst_images.append(image_dict_big)
        image_dict_med = {
            'image': adjustImage(image, config.IMAGE_SIZE_MIDDLE, postcard=True),
            'size': config.IMAGE_SIZE_MIDDLE
        }
        lst_images.append(image_dict_med)
        img_sml = image_dict_med['image'].copy()
        img_sml.thumbnail(config.IMAGE_SIZE_THUMB)
        image_dict_sml = {
            'image': img_sml,
            'size': config.IMAGE_SIZE_THUMB
        }
        lst_images.append(image_dict_sml)

        # Loop over all versions and store them in the filestore
        for img in lst_images:
            width = str(img['size'][0])
            height = str(img['size'][1])
        
            b = io.BytesIO()
            img['image'].save(b, "JPEG")
            b.seek(0)

            img['uuid'] = fs.put(b, content_type=mime_type, height=height, width=width, filename=filename)

        # Insert a record with metadata
        return collection.insert_one({
            'fileName': filename, 'imageUUID': str(image_dict_big['uuid']), 'imageMiddleUUID': str(image_dict_med['uuid']), 'imageThumbUUID': str(image_dict_sml['uuid']),
            'fileType': file_extension.lower(), 'directory': dir, 'mime_type': mime_type 
            }).inserted_id  

    except Exception as err:
        msg = "Onbekende fout bij het bewaren van image, met tekst: " + str(err)
        logger.error(msg)    
        raise Exception(msg) from err
