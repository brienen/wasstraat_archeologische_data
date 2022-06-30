# Import the os module, for the os.walk function
import os
import shared.config as config
import pymongo
from pymongo import WriteConcern, InsertOne
import gridfs

# Import app code
import shared.image_util as image_util
import logging

logger = logging.getLogger("airflow.task")


def getImageNamesFromDir(dir):
    return [os.path.join(dp, f) for dp, dn, filenames in os.walk(dir) for f in filenames if os.path.splitext(f)[1].lower() in config.IMAGE_EXTENSIONS] 


def importImages(index, of):   
    try: 
        myclient = pymongo.MongoClient(config.MONGO_URI)
        filesdb = myclient[config.DB_FILES]
        fs = gridfs.GridFS(filesdb)
        stagingdb = myclient[config.DB_STAGING]
        col = filesdb[config.COLL_FILENAMES]

        count = col.count_documents({})
        blocksize = int(count/of)
        import_from = index*blocksize -1
        import_to = (index+1)*blocksize
        
        logger.info(f"Importing images from index {str(import_from)} " + f" to index {str(import_to)}" if index<of-1 else "")
        aggr = {'iter': {'$gt': import_from, '$lt': import_to}} if index<of-1 else {'iter': {'$gt': index*blocksize -1}}

        files = col.find(aggr)
        fileList = [file['filename'] for file in files]

        for filedirname in fileList:     
            logger.info('Processing and loading image file: %s' % filedirname)

            # If file is Tif look if there is a jpg-version already. if so skip
            filename, file_extension = os.path.splitext(filedirname)
            if 'tif' in file_extension:
                result = col.find_one({'filename': {"$regex": filename + ".jpg"}})
                if result:
                    continue 

            try:
                result = image_util.adjustAndSaveFile(filedirname, fs, stagingdb[config.COLL_PLAATJES])
                if not result:
                    logger.warning('Could nog load file with name: %s' % filedirname)
            except Exception as err:
                msg = f"Onbekende fout bij het laden van image: {filedirname} met melding {str(err)}" 
                logger.error(msg)    
            
    except Exception as err:
        msg = "Onbekende fout bij het laden van images: " + str(err)
        logger.error(msg)    
        raise Exception(msg) from err

    finally:
        myclient.close()




def getAndStoreImageFilenames():
    lst_filenames = []
    for dir in config.IMAGE_INPUTDIRS:
        lst_filenames += getImageNamesFromDir(dir)
    lst_filenames = list(set(lst_filenames))

    logger.info(f'Found {len(lst_filenames)} unique image files for processing...')

    try: 
        myclient = pymongo.MongoClient(config.MONGO_URI)
        filesdb = myclient[config.DB_FILES]
        col = filesdb[config.COLL_FILENAMES]

        #First drop collection to not get doubles
        col.drop()

        inserts=[ InsertOne({'iter': i, 'filename': v}) for i,v in enumerate(lst_filenames) ]
        result = col.bulk_write(inserts)
        col.create_index([ ("iter", 1) ])
        col.create_index([ ("filename", 1) ])
     
    except Exception as err:
        msg = "Onbekende fout bij het opslaan van de filenames: " + str(err)
        logger.error(msg)    
        raise Exception(msg) from err

    finally:
        myclient.close()





