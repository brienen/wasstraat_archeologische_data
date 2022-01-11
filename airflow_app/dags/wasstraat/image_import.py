# Import the os module, for the os.walk function
import os
import config
import io
 
import pymongo
import gridfs
import magic
from PIL import Image, ExifTags

# Import app code
import wasstraat.mongoUtils as mongoUtil
import logging

logger = logging.getLogger("airflow.task")



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



def importImages(rootDir, mongo_uri, db_files, db_staging):   
    try: 
        myclient = pymongo.MongoClient(mongo_uri)
        filesdb = myclient[db_files]
        fs = gridfs.GridFS(filesdb)
        stagingdb = myclient[db_staging]


        # Set the directory you want to start from
        valid_images = [".jpg",".gif",".png",".tga"]
        for leesdir, subdirList, fileList in os.walk(rootDir):
            logger.info('Scanning directory: %s' % leesdir)
            for fname in fileList:     
                filedirname = os.path.join(leesdir,fname)
                logger.info('Processing and loading image file: %s' % filedirname)

                filename, file_extension = os.path.splitext(filedirname)
                if file_extension.lower() not in valid_images:
                    continue
                
                mime_type = magic.from_file(filedirname, mime=True)

                imageUUID = shrinkAndSaveImage(filedirname, config.IMAGE_SIZE_ORIGINAL, fs)
                imageMiddleUUID = shrinkAndSaveImage(filedirname, config.IMAGE_MIDDLE_SIZE, fs)
                imageThumbUUID = shrinkAndSaveImage(filedirname, config.IMAGE_THUMB_SIZE, fs, postcard=True)

                stagingdb[config.COLL_PLAATJES].insert_one({
                    'fileName': fname, 'imageUUID': str(imageUUID), 'imageMiddleUUID': str(imageMiddleUUID), 'imageThumbUUID': str(imageThumbUUID),
                    'fileType': file_extension.lower(), 'directory': leesdir, 'mime_type': mime_type 
                    })  

    except Exception as err:
        msg = "Onbekende fout bij het laden van images: " + str(err)
        logger.error(msg)    

    finally:
        myclient.close()
