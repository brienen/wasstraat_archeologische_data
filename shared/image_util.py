# Import the os module, for the os.walk function
import os
import re
import shared.config as config
import io
 
import magic
from PIL import Image, ExifTags, ImageOps

# Import app code
import logging
logger = logging.getLogger()

# Prevent error message when reading large files, see https://stackoverflow.com/questions/25705773/image-cropping-tool-python 
Image.MAX_IMAGE_PIXELS = None


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

        # If image is sfeerfoto then ignore to not add pictures of people
        if 'Sfeerfoto' in fullfilename:
            return None

        # Get projectcd
        projectcd = fullfilename.replace(config.AIRFLOW_INPUT_IMAGES + '/','')
        projectcd = re.search('^([A-Z0-9]+).*', projectcd).group(1)

        # First read image and make 3 versions with different sizes. And put them in a list 
        image = Image.open(fullfilename, 'r')
        mime_type = magic.from_file(fullfilename, mime=True)

        image_dict_sml, image_dict_med, image_dict_big = putImageInGrid(image, fullfilename, fs, dir, projectcd)    

        # Insert a record with metadata
        return collection.insert_one({
            'fileName': filename, 'fullFileName': fullfilename, 'imageUUID': str(image_dict_big), 'imageMiddleUUID': str(image_dict_med), 'imageThumbUUID': str(image_dict_sml),
            'fileType': file_extension.lower(), 'directory': dir, 'mime_type': 'image/jpeg', 'projectcd': projectcd 
            }).inserted_id  

    except Exception as err:
        msg = "Onbekende fout bij het bewaren van image, met tekst: " + str(err)
        logger.error(msg)    
        raise Exception(msg) from err



def putImageInGrid(image: Image, fullfilename, fs, dir, projectcd):
    try:
        filename, file_extension = os.path.splitext(fullfilename)

        # Grayscale images need special attention for not distoring
        lzw = False
        if 'lzw' in filename.lower() and 'tif' in file_extension.lower():
            image = ImageOps.grayscale(image)
            lzw = True

        lst_images = []
        image_dict_big = image.copy()
        image_dict_big = {
            #'image': adjustImage(image_dict_big, config.IMAGE_SIZE_BIGGEST if not lzw else config.IMAGE_SIZE_LZW) # grayscale images can have more pixels
            'image': adjustImage(image_dict_big, config.IMAGE_SIZE_BIGGEST) # grayscale images can have more pixels
        }
        lst_images.append(image_dict_big)
        image_dict_med = image.copy()
        image_dict_med = {
            'image': adjustImage(image_dict_med, config.IMAGE_SIZE_MIDDLE, postcard=True)
        }
        lst_images.append(image_dict_med)
        img_sml = image_dict_med['image'].copy()
        img_sml.thumbnail(config.IMAGE_SIZE_THUMB)
        image_dict_sml = {
            'image': img_sml
        }
        lst_images.append(image_dict_sml)

        # Loop over all versions and store them in the filestore
        for img in lst_images:
            width = str(img['image'].size[0])
            height = str(img['image'].size[1])
        
            b = io.BytesIO()
            img['image'].save(b, "JPEG")
            b.seek(0)

            img['uuid'] = fs.put(b, content_type='image/jpeg', height=int(height), width=int(width), filename=filename, dir=dir, fullfilename=fullfilename, projectcd=projectcd)

        return image_dict_sml['uuid'], image_dict_med['uuid'], image_dict_big['uuid']

    except Exception as err:
        msg = f"Onbekende fout bij het in grid plaatsen van image {fullfilename}, met tekst: {str(err)}" 
        logger.error(msg)    
        raise Exception(msg) from err
