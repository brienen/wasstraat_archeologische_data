# Import the os module, for the os.walk function
import pymongo
from pymongo import UpdateOne
import re
import pandas as pd
import numpy as np
import roman
import wasstraat.meta as meta
import wasstraat.mongoUtils as mongoUtil
 
# Import app code
# Absolute imports for Hydrogen (Jupyter Kernel) compatibility
import config
import logging
logger = logging.getLogger("airflow.task")

def getAnalyseCollection():   
    myclient = pymongo.MongoClient(str(config.MONGO_URI))
    analyseDb = myclient[str(config.DB_ANALYSE)]
    return analyseDb[config.COLL_ANALYSE]

def getAnalyseCleanCollection():   
    myclient = pymongo.MongoClient(str(config.MONGO_URI))
    analyseDb = myclient[str(config.DB_ANALYSE)]
    return analyseDb[config.COLL_ANALYSE_CLEAN]

def getAnalyseDoosCollection():   
    myclient = pymongo.MongoClient(str(config.MONGO_URI))
    analyseDb = myclient[str(config.DB_ANALYSE)]
    return analyseDb[config.COLL_ANALYSE_DOOS]

def createIndex(collection, index_name, uniqueValue=False):
    if index_name + '_1'not in collection.index_information():
        collection.create_index(index_name, unique=uniqueValue)


def setReferenceKeys(pipeline, soort, col='analyse'):   
    try:
        # First remove all dozen from Clean Collection
        collectionClean = getAnalyseCleanCollection()
        collectionClean.delete_many({"soort": soort})

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
            collectionClean.insert_many(df.to_dict('records'))
        else:
            logger.warning(f"trying to insert empty dataframe of soort: {soort} into collection {col}.")
        
    except Exception as err:
        msg = "Onbekende fout bij het aanroepen van een aggregation met melding: " + str(err)
        logger.error(msg)    
        raise Exception(msg) from err

    finally:
        collection.database.client.close()
        collectionClean.database.client.close()


def setReferences(soort):
    try:
        col = getAnalyseCleanCollection()
        soort_lw = soort.lower()
        
        # Find all main entries for type soort
        df_soort = pd.DataFrame(list(col.find({'soort': soort}, projection={'key':1}))).reset_index()
        df_soort = df_soort.rename(columns={'_id': soort_lw+'UUID', 'index':soort_lw+'ID', 'key':'key_'+soort_lw})
        if df_soort.size < 1:
            logger.warning("Er zjn geen documents gevonden van het type " +soort)
            return
        
        # Find all references to type soort
        df_ref = pd.DataFrame(list(col.find({"key_"+soort_lw: {"$exists": True}}, projection={'key_'+soort_lw:1})))
        if df_ref.size < 1:
            logger.warning("Er zjn geen referentie met key_"+soort_lw+" gevonden naar documents van het type " +soort )
            return
            
        # Merge dataframes to connect ID's en UUID's to referencing docs
        df_merge = pd.merge(df_ref, df_soort, how='left', on='key_'+soort_lw)
        
        # Update soort documents 
        updates=[ UpdateOne({'_id':x['_id']}, {'$set':x}) for x in df_merge.to_dict('records')]
        result = col.bulk_write(updates)

        return result
        
    except Exception as err:
        msg = "Onbekende fout bij het aanroepen van een aggregation met melding: " + str(err)
        logger.error(msg)   
        raise Exception(msg) from err
 
    finally:
        col.database.client.close()



def setArtefactnrUnique():
    try:        
        col = getAnalyseCollection()
        lst_project = list(col.find({'soort': 'artefact'}).distinct('projectcd'))

        for proj in lst_project:
            try:
                df_art = pd.DataFrame(list(col.find({'soort': 'artefact', 'projectcd': proj}, projection={'artefactnr':1}))).dropna()
                unique = df_art['artefactnr'].is_unique
                
                project = col.find_one({ 'soort': "project", 'projectcd': proj })
                project['artefactnrs_unique'] = unique
                col.replace_one({'_id': project['_id']}, project)

            except expression as exp2:
                logger.error(f'Error while determining whether artefactnr are unique for project {proj} with message: {str(exp2)} ')
    except expression as exp1:
        logger.error(f'Severe rrror while determining whether artefactnr are unique with message: {str(exp1)} ')






    # Doos is a combination of doosnr, magazijnlijst and artefacts
def setReferenceKeysDozen():   
    #Find Doos in magazijnlijst
    try:
        # First remove all dozen from Clean Collection
        collectionClean = getAnalyseCleanCollection()
        collectionClean.delete_many({"soort": "Doos"})

        # First all Dozen in a separate collection
        collection = getAnalyseCollection()
        # Find and merge doos from artefacts
        collection.aggregate(meta.getReferenceKeysPipelines('Doos')[0])
        createIndex(collection.database[config.COLL_ANALYSE_DOOS], 'key', uniqueValue=True)

        collection.aggregate(meta.getReferenceKeysPipelines('Doos')[1])

        # Find and merge doos from Doos
        collection.aggregate(meta.getReferenceKeysPipelines('Doos')[2])

        doosCollection = getAnalyseDoosCollection()
        for doc in doosCollection.find({'stelling': {'$exists': True}}):
            doc['key_stelling'] = 'S' + str(doc['stelling'])
            doosCollection.update_one({'_id': doc['_id']}, {'$set': doc})

        # Set Primary key and read data from dooscollection
        setReferenceKeys([{ '$match': {'soort': "Doos"}}], 'Doos', 'doos')

    except Exception as err:
        msg = "Onbekende fout bij het aanroepen van een aggregation met melding: " + str(err)
        logger.error(msg)    
    finally:
        collection.database.client.close()



def setAllReferences():
    setReferences('Project')
    setReferences('Put')
    setReferences('Vondst')
    setReferences('Spoor')
    setReferences('Vlak')
    setReferences('Doos')
    setReferences('Stelling')
    setReferences('Artefact')
    setReferences('Project_type')
