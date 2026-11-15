# Import installed packages
import pymongo
import shared.config as config
import wasstraat.verwerkingsrun as verwerkingsrun
import logging

logger = logging.getLogger("airflow.task")

# Collecties in de staging-database die de volledige cyclus laat staan: de run-documenten
# (issue 54), zodat de run die de cyclus zelf heeft gestart en de geschiedenis van runs en
# verwerkingsrapporten bewaard blijven
BEWAARDE_STAGING_COLLECTIES = [verwerkingsrun.COLL_VERWERKINGSRUNS]


def dropAll():
    """Taak Drop_All_Databases: leeg de staging-, bestanden- en analysedatabase van MongoDB.

    De run-documenten (BEWAARDE_STAGING_COLLECTIES) blijven staan. Een fout is
    cruciaal (issue 54): zonder lege databases zou de extractie bovenop de oude
    gegevens inlezen en ontstaan dubbele records.

    Raises:
        Exception: als het legen mislukt
    """
    myclient = pymongo.MongoClient(str(config.MONGO_URI))
    try:
        stagingdb = myclient[str(config.DB_STAGING)]
        for naam in stagingdb.list_collection_names():
            if naam in BEWAARDE_STAGING_COLLECTIES or naam.startswith('system.'):
                continue
            logger.info(f"Deleting: {config.DB_STAGING}.{naam}")
            stagingdb.drop_collection(naam)

        logger.info("Deleting: " + str(config.DB_FILES))
        myclient.drop_database(str(config.DB_FILES))

        logger.info("Deleting: " + str(config.DB_ANALYSE))
        myclient.drop_database(str(config.DB_ANALYSE))

    except Exception as err:
        msg = "Fout bij het verwijderen van alle databases met melding: " + str(err)
        logger.error(msg)
        raise Exception(msg) from err
    finally:
        myclient.close()

def dropAnalyse():
    try: 
        myclient = pymongo.MongoClient(str(config.MONGO_URI))

        logger.info("Deleting: " + str(config.DB_ANALYSE))
        myclient.drop_database(str(config.DB_ANALYSE))

    except Exception as err:
        msg = "Fout bij het verwijderen van alle databases met melding: " + str(err)
        logger.error(msg)    
    finally:
        myclient.close()

def dropStaging():
    try: 
        myclient = pymongo.MongoClient(str(config.MONGO_URI))

        logger.info("Deleting: " + str(config.DB_STAGING))
        myclient.drop_database(str(config.DB_STAGING))

    except Exception as err:
        msg = "Fout bij het verwijderen van database STAGING met melding: " + str(err)
        logger.error(msg)    
    finally:
        myclient.close()

def dropFileStore():
    try: 
        myclient = pymongo.MongoClient(str(config.MONGO_URI))

        logger.info("Deleting: " + str(config.DB_FILES))
        myclient.drop_database(str(config.DB_FILES))

    except Exception as err:
        msg = "Fout bij het verwijderen van database DB_FILES met melding: " + str(err)
        logger.error(msg)    
    finally:
        myclient.close()



def dropProjectsStore():
    try: 
        myclient = pymongo.MongoClient(str(config.MONGO_URI))
        db = myclient[config.DB_STAGING]
        col = db[config.COLL_STAGING_OUD]

        logger.info("Deleting: " + str(config.COLL_STAGING_OUD))
        col.drop()

    except Exception as err:
        msg = f"Fout bij het verwijderen van collection {config.COLL_STAGING_OUD} uit database {config.DB_STAGING} met melding: " + str(err)
        logger.error(msg)    
    finally:
        myclient.close()



def dropSingleStore():
    try: 
        myclient = pymongo.MongoClient(str(config.MONGO_URI))
        db = myclient[config.DB_ANALYSE]
        col = db[config.COLL_ANALYSE]

        logger.info("Deleting: " + str(config.DB_ANALYSE))
        col.drop()

    except Exception as err:
        msg = f"Fout bij het verwijderen van collection {config.DB_ANALYSE} uit database {config.DB_ANALYSE} met melding: " + str(err)
        logger.error(msg)    
    finally:
        myclient.close()


def dropSingleStoreClean():
    try: # config.COLL_ANALYSE_DOOS en config.COLL_ANALYSE_CLEAN
        myclient = pymongo.MongoClient(str(config.MONGO_URI))
        db = myclient[config.DB_ANALYSE]

        logger.info("Deleting: " + str(config.COLL_ANALYSE_CLEAN))
        col = db[config.COLL_ANALYSE_CLEAN]
        col.drop()

        logger.info("Deleting: " + str(config.COLL_ANALYSE_DOOS))
        col = db[config.COLL_ANALYSE_DOOS]
        col.drop()

    except Exception as err:
        msg = f"Fout bij het verwijderen van collection {config.DB_ANALYSE} of {config.COLL_ANALYSE_CLEAN} uit database {config.DB_ANALYSE} met melding: " + str(err)
        logger.error(msg)    
    finally:
        myclient.close()


def setIndexes(collection):
    if not collection in [config.COLL_ANALYSE, config.COLL_ANALYSE_CLEAN]:
        msg = f"Fout bij het indexeren van collection {collection}: onbekende collectie. Gebruik {config.COLL_ANALYSE} of {config.COLL_ANALYSE_CLEAN}."
        logger.error(msg)    
        raise Exception(msg)

    try: 
        myclient = pymongo.MongoClient(str(config.MONGO_URI))
        db = myclient[config.DB_ANALYSE]
        col = db[collection]

        logger.info(f"Setting indexes for collection {collection}.")
        col.create_index([("soort", pymongo.ASCENDING), ("key", pymongo.ASCENDING)], name='idx_soort_key')

    except Exception as err:
        msg = f"Fout bij het verwijderen van collection {config.DB_ANALYSE} uit database {config.DB_ANALYSE} met melding: " + str(err)
        logger.error(msg)    
    finally:
        myclient.close()
