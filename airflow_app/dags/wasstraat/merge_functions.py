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
AGGREGATE_MERGE = [
        {"$match" : {"soort" : {"$in" : ["XXX"]}}},
        {"$lookup" : { 
                "from" : "Single_Store", 
                "let" : {"key" : "$key"}, 
                "pipeline" : [{"$match" : {"$expr" : {"$and" : [
                                    {"$eq" : ["$soort","Artefact"]},
                                    {"$eq" : ["$key","$$key"]}]}}}],
                "as" : "results"}},
        {"$addFields" : {"artefactsoort" : "$soort"}},
        {"$addFields" : { 
                "results" : { 
                    "$map" : { 
                        "input" : "$results", 
                        "as" : "res", 
                        "in" : { 
                            "$arrayToObject" : { 
                                "$filter" : { 
                                    "input" : { 
                                        "$objectToArray" : "$$res"
                                    }, 
                                    "as" : "item", 
                                    "cond" : { 
                                        "$and" : [
                                            { 
                                                "$ne" : [
                                                    "$$item.v", 
                                                    np.NaN
                                                ]
                                            }, 
                                            { 
                                                "$ne" : [
                                                    "$$item.v", 
                                                    None
                                                ]
                                            }
                                        ]
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }, 
        {"$replaceRoot" : {"newRoot" : {"$mergeObjects" : ["$$ROOT", {"$arrayElemAt" : ["$results", 0]}]}}},
        {"$project" : {"results" : 0}}
    ,{ "$merge": { "into": { "db": config.DB_ANALYSE, "coll": config.COLL_ANALYSE_CLEAN }, "on": "_id",  "whenMatched": "replace", "whenNotMatched": "insert" } }
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


def mergeSoort(soort):
    if not soort in meta.getKeys(meta.MOVE_FASE):
        msg = "Fout bij het aanroepen van de merge aggregation voor inherit. Onbekend soort:  " + soort
        logger.error(msg)    
        raise Exception(msg)

    aggr = copy.deepcopy(AGGREGATE_MERGE)
    aggr[0]['$match']['soort']["$in"] = meta.getKeys(meta.MERGE_INHERITED_FASE)

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


