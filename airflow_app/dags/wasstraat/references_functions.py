# Import the os module, for the os.walk function
import pymongo
from pymongo import UpdateOne, WriteConcern
import re
import pandas as pd
import numpy as np
import roman
import wasstraat.meta as meta
import wasstraat.mongoUtils as mongoUtil
import simplejson
 
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

def createIndex(collection, index_name, uniqueValue=False):
    if index_name + '_1'not in collection.index_information():
        collection.create_index(index_name, unique=uniqueValue)


def setReferenceKeys(pipeline, soort, col='analyse'):   
    try:
        if (col == 'analyse'):
            collection = getAnalyseCollection()
        elif (col == 'analyseclean'):
            collection = getAnalyseCleanCollection()
        else:
            raise ValueError('Error: Herkent de collectie niet met naam ' + col)

        df = pd.DataFrame(list(collection.aggregate(pipeline)))
        # Fix problem with dates
        if 'datum' in df.columns.values:
            df[['datum']] = df[['datum']].astype(object).where(df[['datum']].notnull(), None)
        
        if not df.empty:
            # Update soort documents 
            updates=[ UpdateOne({'_id':x['_id']}, {'$set':x}, upsert=True) for x in [v.dropna().to_dict() for k,v in df.iterrows()]]  # 
            result = collection.bulk_write(updates)
        else:
            logger.warning(f"trying to insert empty dataframe of soort: {soort} into collection {col}.")
        
    except Exception as err:
        msg = "Onbekende fout bij het aanroepen van een aggregation met melding: " + str(err)
        logger.error(msg)    
        raise Exception(msg) from err

    finally:
        collection.database.client.close()


def setPrimaryKeys(soort, col='analyse'):   
    try:
        if (col == 'analyse'):
            collection = getAnalyseCollection()
        elif (col == 'analyseclean'):
            collection = getAnalyseCleanCollection()
        else:
            raise ValueError('Error: Herkent de collectie niet met naam ' + col)

        df = pd.DataFrame(list(collection.find({'soort': soort})))
        df.drop(['ID', 'index', 'level_0'], inplace=True, errors='ignore')
        df.reset_index(inplace=True)
        df['ID'] = df['index']
        
        if not df.empty:
            # Update soort documents 
            #updates=[ UpdateOne({'_id':x['_id']}, {'$set':x}, upsert=True) for x in df.to_dict('records')]  # v.dropna().to_dict() for k,v in df.iterrows()
            updates=[ UpdateOne({'_id':x['_id']}, {'$set':x}, upsert=True) for x in [v.dropna().to_dict() for k,v in df.iterrows()]]  # 
            result = collection.bulk_write(updates)
        else:
            logger.warning(f"trying to insert empty dataframe of soort: {soort} into collection {col}.")
        
    except Exception as err:
        msg = "Onbekende fout bij het aanmaken van primary keys met melding: " + str(err)
        logger.error(msg)    
        raise Exception(msg) from err

    finally:
        collection.database.client.close()



def setReferences(soort, col='analyse', key='key'):
    try:
        if (col == 'analyse'):
            collection = getAnalyseCollection()
        elif (col == 'analyseclean'):
            collection = getAnalyseCleanCollection()
        else:
            raise ValueError('Error: Herkent de collectie niet met naam ' + col)

        soort_lw = soort.lower()
        
        # Find all main entries for type soort
        df_soort = pd.DataFrame(list(collection.find({'soort': soort}, projection={key:1, 'ID':1})))
        df_soort = df_soort.rename(columns={'_id': soort_lw+'UUID', 'index':soort_lw+'ID', key:'key_'+soort_lw})
        if df_soort.size < 1:
            logger.warning("Er zjn geen documents gevonden van het type " +soort)
            return

        if not 'key_'+soort_lw in df_soort.columns:
            logger.warning("Kan geen referenties maken voor " +soort + ". Geen Key-veld aanwezig.")
            return

        # Find all references to type soort
        df_ref = pd.DataFrame(list(collection.find({"key_"+soort_lw: {"$exists": True}}, projection={'key_'+soort_lw:1})))
        if df_ref.size < 1:
            logger.warning("Er zjn geen referentie met key_"+soort_lw+" gevonden naar documents van het type " +soort )
            return
            
        # Merge dataframes to connect ID's en UUID's to referencing docs
        df_merge = pd.merge(df_ref, df_soort, how='left', on='key_'+soort_lw).rename(columns={'ID': soort_lw + 'ID'})
        
        # Update soort documents 
        updates=[ UpdateOne({'_id':x['_id']}, {'$set':x}) for x in [v.dropna().to_dict() for k,v in df_merge.iterrows()]] # 
        result = collection.bulk_write(updates)

        return result.bulk_api_result
        
    except Exception as err:
        msg = "Onbekende fout bij het aanroepen van een aggregation met melding: " + str(err)
        logger.error(msg)   
        raise Exception(msg) from err
 
    finally:
        collection.database.client.close()



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

            except Exception as exp2:
                logger.error(f'Error while determining whether artefactnr are unique for project {proj} with message: {str(exp2)} ')
    except Exception as exp1:
        logger.error(f'Severe rrror while determining whether artefactnr are unique with message: {str(exp1)} ')




