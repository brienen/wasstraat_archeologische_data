# Import the os module, for the os.walk function
import config
import pymongo
import gridfs

# Import app code
import shared.image_util as image_util
import logging

logger = logging.getLogger("airflow.task")


def importImages(fileList, mongo_uri, db_files, db_staging):   
    try: 
        myclient = pymongo.MongoClient(mongo_uri)
        filesdb = myclient[db_files]
        fs = gridfs.GridFS(filesdb)
        stagingdb = myclient[db_staging]

        for filedirname in fileList:     
            logger.info('Processing and loading image file: %s' % filedirname)

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
