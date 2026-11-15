import shared.config as config
import pymongo
import pandas as pd

import wasstraat.verwerkingsrun as verwerkingsrun
import logging
logger = logging.getLogger("airflow.task")


def extractABR():
    df = pd.read_excel(config.FILE_ABREXCEL)
    df['table'] = 'ABR'
    df.dropna(subset=['uri'])
    df = df[df["uri"].str.contains('https')==True]
    df['concept'] = df['concept'].str.title()
    df['label'] = df['label'].str.title()

    logger.info(f'Found file {config.FILE_ABREXCEL} with ABR-info for processing...')
    try: 
        myclient = pymongo.MongoClient(config.MONGO_URI)
        filesdb = myclient[config.DB_STAGING]
        col = filesdb[config.COLL_STAGING_REFERENTIETABELLEN]

        #First drop collection to not get doubles
        col.drop()

        # Insert collection
        data_dict = df.to_dict("records")
        col.insert_many(data_dict)
     
    except Exception as err:
        msg = f"Onbekende fout bij het inlezen van ABR-Bestand: " + str(err)
        logger.error(msg)    
        raise Exception(msg) from err

    finally:
        myclient.close()


def extractAllRefs(incrementeel=False):
    """Lees de referentietabellen (ABR) in.

    Args:
        incrementeel: als True alleen inlezen als het ABR-bestand in de actieve
            verwerkingsrun nieuw of gewijzigd is
    """
    if incrementeel and not verwerkingsrun.isInDelta(config.FILE_ABREXCEL, 'referentietabellen'):
        logger.info(f"Incrementeel: ABR-bestand {config.FILE_ABREXCEL} is niet nieuw of gewijzigd — overslaan.")
        return
    extractABR()

