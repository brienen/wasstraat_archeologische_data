# Import installed packages
from raven import Client
import pymongo
import config
import logging

logger = logging.getLogger("airflow.task")

def dropAll():
    try: 
        myclient = pymongo.MongoClient(str(config.MONGO_URI))

        logger.info("Deleting: " + str(config.DB_STAGING))
        myclient.drop_database(str(config.DB_STAGING))

        logger.info("Deleting: " + str(config.DB_FILES))
        myclient.drop_database(str(config.DB_FILES))

        logger.info("Deleting: " + str(config.DB_ANALYSE))
        myclient.drop_database(str(config.DB_ANALYSE))

    except Exception as err:
        msg = "Fout bij het verwijderen van alle databases met melding: " + str(err)
        logger.error(msg)    
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
        if collection == config.COLL_ANALYSE:
            col.create_index("key")
        elif collection == config.COLL_ANALYSE_CLEAN:
            col.create_index(["soort", "key"])

    except Exception as err:
        msg = f"Fout bij het verwijderen van collection {config.DB_ANALYSE} uit database {config.DB_ANALYSE} met melding: " + str(err)
        logger.error(msg)    
    finally:
        myclient.close()
