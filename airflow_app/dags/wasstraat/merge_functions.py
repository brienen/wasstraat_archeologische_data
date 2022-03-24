# Import the os module, for the os.walk function
import pymongo
from pymongo import UpdateOne, WriteConcern, InsertOne
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

## The Artefacts of these projects will not be merged (too many wrong merges)
ARTEFACT_NOT_MERGE_PROJECTS = ['DC112']

## The Artefacts of these tables will not be merged (too many wrong merges)
ARTEFACT_NOT_MERGE_TABLES = ['ROMEINS AARDEWERK']

## Generic aggregation phase for getting rid of empty cells
AGGR_PHASE_CLEAN_EMPTY = {'$replaceRoot': {'newRoot': {'$arrayToObject': {'$filter': {'input': {'$objectToArray': '$$ROOT'},
      'as': 'item',
      'cond': {'$and': [{'$ne': ['$$item.v', np.nan]},
        {'$ne': ['$$item.v', None]},
        {'$ne': ['$$item.v', np.nan]},
        {'$ne': ['$$item.v', '-']}]}}}}}}

## Aggregation pipeline to move records of a certain type
AGGREGATE_MOVE = [
    {'$match': { 'soort': "XXX" } },
    {'$addFields': {'wasstraat.tables': ['$brondata.table'],
        'wasstraat.projects': ['$projectcd'], 
        'brondata': ['$brondata']}},
    { "$merge": { "into": { "db": config.DB_ANALYSE, "coll": config.COLL_ANALYSE_CLEAN }, "on": "_id",  "whenMatched": "replace", "whenNotMatched": "insert" } }
    ]

## Aggregation pipeline to merge records of a certain type and then to move them
AGGREGATE_MERGE = [{'$match': {'soort': 'XXX'}},
 {'$group': {
    'doc': {'$mergeObjects': '$$ROOT'},
    'brondata': {'$addToSet': '$$ROOT.brondata'},
    'tables': {'$addToSet': '$$ROOT.brondata.table'},
    'projects': {'$addToSet': '$$ROOT.brondata.project'}}},
 {'$project': {'doc.brondata': 0}},
 {'$addFields': {'doc.brondata': '$brondata',
    'doc.wasstraat.tables': '$tables',
    'doc.wasstraat.projects': '$projects'}},
 {'$replaceRoot': {'newRoot': '$doc'}},
 {'$addFields': {'brondata_count': {'$size': '$brondata'}}},
 { "$merge": { "into": { "db": config.DB_ANALYSE, "coll": config.COLL_ANALYSE_CLEAN }, "on": "_id",  "whenMatched": "replace", "whenNotMatched": "insert" } }
]

## Match phase aggregation specific for moving Artefacts: inverse of the merge phase. For alle artefacts that do not pass the merge match clause  
INVERSE_MATCH_ARTEFACT = {"$match": {'$and': [{'soort': 'Artefact'},
  {'brondata.table': {'$nin': ['ARTEFACT']}},
  {'$or': [{'subnr': {'$exists': False}},
    {'brondata.ARTEFACT': {'$exists': True}},
    {'brondata.table': {'$in': ARTEFACT_NOT_MERGE_TABLES}},
    {'projectcd': {'$in': ARTEFACT_NOT_MERGE_PROJECTS}}]}]}}

''' Factory method to retrieve move aggragtion pipeline for specific type
'''
def getMoveAggregate(soort):
    aggr = copy.deepcopy(AGGREGATE_MOVE)
    aggr.insert(1, AGGR_PHASE_CLEAN_EMPTY)
    if soort == 'Artefact':
        aggr.insert(1, INVERSE_MATCH_ARTEFACT)
        
    aggr[0]['$match']['soort'] = soort
    return aggr

''' Factory method to retrieve merge aggragtion pipeline for specific type
'''
def getMergeAggregate(soort, key='key'):
    aggr = copy.deepcopy(AGGREGATE_MERGE)
    aggr.insert(1, AGGR_PHASE_CLEAN_EMPTY)
    aggr[2]["$group"]["_id"] = {key: "$"+key}

    if soort == 'Artefact':
        aggr.insert(1, 
            {'$match': {'$and': [{'subnr': {'$exists': True}},
                {'brondata.ARTEFACT': {'$exists': False}},
                {'brondata.table': {'$nin': ARTEFACT_NOT_MERGE_TABLES}},
                {'projectcd': {'$nin': ARTEFACT_NOT_MERGE_PROJECTS}}]}})
        aggr[3]["$group"]["_id"]['artefactsoort'] = "$artefactsoort"
    aggr[0]['$match']['soort'] = soort

    return aggr
 


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

    aggr = getMoveAggregate(soort)
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

    key = 'key_subnr' if soort == 'Artefact' else 'key'
    aggr = getMergeAggregate(soort, key=key)
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


def mergeMissing(soort):
    logger.info(f"Start ind and merge missing for {soort}")
    if not soort in meta.getKeys(meta.GENERATE_MISSING_PIPELINES):
        msg = f"Fout bij het aanroepen van de merge aggregation voor merge missing. Onbekend soort: {soort}. Alleen deze zijn geldig: {meta.getKeys(meta.GENERATE_MISSING_PIPELINES)}"
        logger.error(msg)    
        raise Exception(msg)

    aggr_lst = meta.getGenerateMissingPipelines(soort)

    try:
        #Aggregate Pipelin
        collection = getAnalyseCollection()
        cleancollection = getAnalyseCleanCollection()

        for aggr in aggr_lst:
            logger.info("Calling aggregation: " + str(aggr))
            collection.aggregate(aggr)

            df_gen = pd.DataFrame(list(collection.aggregate(aggr)))            
            if not df_gen.empty and 'key' in df_gen.columns:
                df_orig = pd.DataFrame(list(cleancollection.find({'soort': soort})))

                df_all = df_gen.merge(df_orig, on=['key', 'soort'], how='left', indicator=True, suffixes=[None, "_orig"])
                df = df_all[df_all._merge == 'left_only'][df_gen.columns]
                if len(df) < 1:
                    logger.info(f"No missing records for type: {soort} nothing inserted in collection.")
                    return

                inserts=[ InsertOne(record) for record in [v.dropna().to_dict() for k,v in df.iterrows()]]  # 
                result = cleancollection.bulk_write(inserts)
            else:
                logger.warning(f"trying to insert empty dataframe of soort: {soort} into collection.")

    except Exception as err:
        msg = "Onbekende fout bij het aanroepen van een aggregation met melding: " + str(err)
        logger.error(msg)    
        raise Exception(msg) from err

    finally:
        collection.database.client.close()
        cleancollection.database.client.close()


