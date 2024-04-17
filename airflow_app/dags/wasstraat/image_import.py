# Import the os module, for the os.walk function
import os
import re
import shared.config as config
import pymongo
from pymongo import InsertOne
import gridfs
import random
import pandas as pd

# Import app code
import shared.image_util as image_util
import logging

logger = logging.getLogger("airflow.task")


def getImageNamesFromDir(dir):
    lst = [os.path.join(dp, f) for dp, dn, filenames in os.walk(dir) for f in filenames if os.path.splitext(f)[1].lower() in config.IMAGE_EXTENSIONS] 
    lst = [file for file in lst if ("velddocument" in file.lower() or "fotos" in file.lower() or "tekening" in file.lower() or "DAN" in file or "DAR" in file)]
    lst = list(set(lst))
    return lst 


def getImageNamesFromExcelAndDir(dir):
    # get list from excel
    df = pd.read_excel(config.FILE_IMPORT_FILES_EXCEL)
    df = df[df['wel/niet'] == 1]
    df['fulldir'] = df['Dir'] + '/' + df['Bestand']
    excel_lst = df['fulldir'].tolist()
    
    # get files from dir
    dir_lst = [os.path.join(dp, f) for dp, dn, filenames in os.walk(dir) for f in filenames if os.path.splitext(f)[1].lower() in config.IMAGE_EXTENSIONS] 
    
    return list(set(excel_lst).intersection(set(dir_lst)).difference(set(getImageNamesFromDir(dir))))


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
        aggr = {'iter': {'$gt': import_from, '$lt': import_to}, 'processed': False} if index<of-1 else {'iter': {'$gt': index*blocksize -1}, 'processed': False}

        files = col.find(aggr)
        for file in files:  
            filedirname = file['filename']   
            logger.info('Processing and loading image file: %s' % filedirname)

            # If file is Tif or pdf look if there is a jpg-version already. if so skip
            filename, file_extension = os.path.splitext(filedirname)
            if 'tif' in file_extension or 'pdf' in file_extension:
                regex = re.compile(re.escape(filename + ".jpg"))
                result = col.find_one({'filename': regex })
                if result:
                    continue 

            try:
                result = image_util.adjustAndSaveFile(filedirname, fs, stagingdb[config.COLL_PLAATJES])
                if not result:
                    logger.warning('Could nog load file with name: %s' % filedirname)
                col.update_one({'_id': file['_id']}, {'$set': {'processed': True}})
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
    lst_filenames = getImageNamesFromDir(config.AIRFLOW_INPUT_IMAGES) + getImageNamesFromDir(config.AIRFLOW_INPUT_RAPPORTEN) + getImageNamesFromExcelAndDir(config.AIRFLOW_INPUT_IMAGES)
    random.shuffle(lst_filenames) # Shuffle to make sure not all big files are at the end
    logger.info(f'Found {len(lst_filenames)} unique image files for processing...')

    try: 
        myclient = pymongo.MongoClient(config.MONGO_URI)
        filesdb = myclient[config.DB_FILES]
        col = filesdb[config.COLL_FILENAMES]

        #First drop collection to not get doubles
        col.drop()

        inserts=[ InsertOne({'iter': i, 'filename': v, 'processed': False}) for i,v in enumerate(lst_filenames) ]
        result = col.bulk_write(inserts)
        col.create_index([ ("iter", 1) ])
        col.create_index([ ("filename", 1) ])
     
    except Exception as err:
        msg = "Onbekende fout bij het opslaan van de filenames: " + str(err)
        logger.error(msg)    
        raise Exception(msg) from err

    finally:
        myclient.close()





