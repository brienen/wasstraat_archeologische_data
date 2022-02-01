# Import the os module, for the os.walk function
import pymongo
from pymongo import UpdateOne, WriteConcern
import re
import pandas as pd
import numpy as np
import copy
import wasstraat.meta as meta
import wasstraat.mongoUtils as mongoUtil
 
# Import app code
# Absolute imports for Hydrogen (Jupyter Kernel) compatibility
import config
import logging
logger = logging.getLogger("airflow.task")

AGGREGATE_MOVE = [
    { '$match': { 'soort': "XXX" } },
    { "$merge": { "into": { "db": config.DB_ANALYSE, "coll": config.COLL_ANALYSE_CLEAN }, "on": "_id",  "whenMatched": "replace", "whenNotMatched": "insert" } }
    ]


def getAnalyseCollection():   
    myclient = pymongo.MongoClient(str(config.MONGO_URI))
    analyseDb = myclient[str(config.DB_ANALYSE)]
    return analyseDb[config.COLL_ANALYSE]

def getAnalyseCleanCollection():   
    myclient = pymongo.MongoClient(str(config.MONGO_URI))
    analyseDb = myclient[str(config.DB_ANALYSE)]
    return analyseDb[config.COLL_ANALYSE_CLEAN]


def moveSoort(soort):
    if not soort in meta.getKeys(meta.MOVE_FASE):
        msg = "Fout bij het aanroepen van de move aggregation. Onbekend soort:  " + soort
        logger.error(msg)    
        raise Exception(msg)

    aggr = copy.deepcopy(AGGREGATE_MOVE)
    aggr[0]['$match']['soort'] = soort

    try:
        #Aggregate Pipelin
        collection = getAnalyseCollection()
        logger.info("Calling aggregation: " + str(aggr))
        collection.aggregate(aggr)
        
    except Exception as err:
        msg = "Onbekende fout bij het aanroepen van een aggregation met melding: " + str(err)
        logger.error(msg)    
        raise Exception(msg) from err

    finally:
        collection.database.client.close()




def setReferenceKeys(pipeline, soort, col='analyse'):   
    try:
        #Aggregate Pipelin
        if (col == 'analyse'):
            collection = getAnalyseCollection()
        elif (col == 'doos'):
            collection = getAnalyseDoosCollection()
        else:
            raise ValueError('Error: Herkent de collectie niet met naam ' + col)

        df = pd.DataFrame(list(collection.aggregate(pipeline))).reset_index().rename(columns={'index': 'ID'})
        # Fix problem with dates
        if 'datum' in df.columns.values:
            df[['datum']] = df[['datum']].astype(object).where(df[['datum']].notnull(), None)
        
        if not df.empty:
            #collectionClean.with_options(write_concern=WriteConcern(w=0)).insert_many(df.to_dict('records'))

            # Update soort documents 
            updates=[ UpdateOne({'_id':x['_id']}, {'$set':x}, upsert=True) for x in df.to_dict('records')]
            result = collection.bulk_write(updates)
        else:
            logger.warning(f"trying to insert empty dataframe of soort: {soort} into collection {col}.")
        
    except Exception as err:
        msg = "Onbekende fout bij het aanroepen van een aggregation met melding: " + str(err)
        logger.error(msg)    
        raise Exception(msg) from err

    finally:
        collection.database.client.close()

