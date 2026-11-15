import os

import shared.config as config
import pymongo
import pandas as pd

import wasstraat.verwerkingsrun as verwerkingsrun
import logging
logger = logging.getLogger("airflow.task")


def extractExtraProjects(incrementeel=False):
    """Lees het bestand met extra projecten in de projectenlijst-collectie.

    Elk document krijgt het veld mdbfile met het pad van het bestand, zodat de
    incrementele cyclus de documenten kan verwijderen als het bestand wijzigt.

    Args:
        incrementeel: als True alleen inlezen als het bestand in de actieve
            verwerkingsrun nieuw of gewijzigd is
    """
    if not os.path.isfile(config.FILE_EXTRA_PROJECTS):
        logger.info(f"Bestand {config.FILE_EXTRA_PROJECTS} niet gevonden — overslaan.")
        return

    if incrementeel and not verwerkingsrun.isInDelta(config.FILE_EXTRA_PROJECTS, 'extra_projecten'):
        logger.info(f"Incrementeel: bestand {config.FILE_EXTRA_PROJECTS} is niet nieuw of gewijzigd — overslaan.")
        return

    df = pd.read_excel(config.FILE_EXTRA_PROJECTS)
    df['mdbfile'] = config.FILE_EXTRA_PROJECTS

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


