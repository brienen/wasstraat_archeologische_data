import os

import shared.config as config
import pymongo
import pandas as pd

import logging
logger = logging.getLogger("airflow.task")


def extractExtraProjects():
    if not os.path.isfile(config.FILE_EXTRA_PROJECTS):
        logger.info(f"Bestand {config.FILE_EXTRA_PROJECTS} niet gevonden — overslaan.")
        return

    df = pd.read_excel(config.FILE_EXTRA_PROJECTS)

    logger.info(f'Found file {config.FILE_EXTRA_PROJECTS} with extra projects processing...')
    try: 
        myclient = pymongo.MongoClient(config.MONGO_URI)
        filesdb = myclient[config.DB_STAGING]
        col = filesdb[config.COLL_STAGING_PROJECTENLIJST]

        # Insert collection
        data_dict = df.to_dict("records")
        col.insert_many(data_dict)
     
    except Exception as err:
        msg = f"Onbekende fout bij het inlezen van projectenbestand {config.FILE_EXTRA_PROJECTS} with message: " + str(err)
        logger.error(msg)    
        raise Exception(msg) from err

    finally:
        myclient.close()


