# Import the os module, for the os.walk function
import pymongo
from pymongo import UpdateOne, WriteConcern
import re
import pandas as pd
import numpy as np
import roman
import wasstraat.meta as meta
import wasstraat.mongoUtils as mongoUtil
import wasstraat.util as util
import wasstraat.verwerkingsrun as verwerkingsrun
import wasstraat.delta_transform as delta_transform
import simplejson
 
# Import app code
# Absolute imports for Hydrogen (Jupyter Kernel) compatibility
import shared.config as config
import shared.const as const
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


def setReferenceKeys(pipeline, soort, col='analyse', incrementeel=False):   
    """Bereken de sleutels (key, key_project, ...) van een soort met de pipeline uit meta.py.

    Args:
        pipeline: pipeline uit meta.getReferenceKeysPipeline
        soort: soort
        col: 'analyse' (Single_Store) of 'analyseclean' (Single_Store_Clean)
        incrementeel: als True krijgt de eerste $match een filter op delta_run van
            de actieve verwerkingsrun (incrementeel laden); voor de soorten
            waarvan de sleutels van de vlag vondstkey_met_putnr afhangen ook op
            de geraakte projecten (delta_transform.getDeltaOfProjectFilter). De
            pipeline uit meta.py zelf blijft ongewijzigd
    """
    if incrementeel:
        pipeline = delta_transform.voegToeAanEersteMatch(
            pipeline, delta_transform.getDeltaOfProjectFilter(soort, verwerkingsrun.huidigeRun()))

    try:
        if (col == 'analyse'):
            collection = getAnalyseCollection()
        elif (col == 'analyseclean'):
            collection = getAnalyseCleanCollection()
        else:
            raise ValueError('Error: Herkent de collectie niet met naam ' + col)
        
        logger.info(f"Setting references voor soort {soort} with pipeline {pipeline}")
        df = pd.DataFrame(list(collection.aggregate(pipeline)))
        # Fix problem with dates
        if 'datum' in df.columns.values:
            df[['datum']] = df[['datum']].astype(object).where(df[['datum']].notnull(), None)
        
        if not df.empty:
            # Update soort documents 
            updates=[ UpdateOne({'_id':x['_id']}, {'$set':x}, upsert=True) for x in [util.safe_row_to_dict(v, keep_fields=['_id', 'key', 'soort']) for k,v in df.iterrows()]]
            result = collection.bulk_write(updates)
        else:
            logger.warning(f"trying to insert empty dataframe of soort: {soort} into collection {col}.")

    except Exception as err:
        msg = "Onbekende fout bij het aanroepen van een aggregation met melding: " + str(err)
        logger.error(msg)
        raise Exception(msg) from err

    finally:
        collection.database.client.close()


def setPrimaryKeys(soort, col='analyse', stabiel=False):   
    """Ken de integer-sleutels (ID, in PostgreSQL primary_key) toe aan de documenten van een soort.

    Args:
        soort: soort
        col: 'analyse' (Single_Store) of 'analyseclean' (Single_Store_Clean)
        stabiel: als True houden documenten hun ID, krijgen documenten zonder ID
            hun primary_key uit PostgreSQL terug en krijgen alleen nieuwe
            entiteiten een nieuw nummer (zie delta_transform.bepaalStabieleIds).
            Transform 4 doet dat in alle DAG's, ook in de volledige cyclus
            (issue 71). Zonder stabiel, of als de tabel nog niet bestaat en geen
            document een ID heeft, worden alle documenten opnieuw genummerd
            vanaf 0 in de volgorde van de collectie (documenten met een veld
            primary_key uit de bron houden dat nummer).
    """
    try:
        if (col == 'analyse'):
            collection = getAnalyseCollection()
        elif (col == 'analyseclean'):
            collection = getAnalyseCleanCollection()
        else:
            raise ValueError('Error: Herkent de collectie niet met naam ' + col)

        if stabiel and delta_transform.setStabielePrimaryKeys(soort, collection):
            return

        df = pd.DataFrame(list(collection.find({'soort': soort})))
        df.drop(['ID', 'index', 'level_0'], inplace=True, errors='ignore')
        if 'primary_key' in df.columns:
            df['ID'] = df['primary_key']
            df = df.drop(['primary_key'], axis=1)
        else:
            df.reset_index(inplace=True)
            df.index = df.index + 1
            df['ID'] = df['index']
        
        if not df.empty:
            # Update soort documents 
            updates=[ UpdateOne({'_id':x['_id']}, {'$set':x}, upsert=True) for x in [util.safe_row_to_dict(v, keep_fields=['_id', 'soort']) for k,v in df.iterrows()]]
            result = collection.bulk_write(updates)
        else:
            logger.warning(f"trying to insert empty dataframe of soort: {soort} into collection {col}.")
        
    except Exception as err:
        msg = "Onbekende fout bij het aanmaken van primary keys met melding: " + str(err)
        logger.error(msg)    
        raise Exception(msg) from err

    finally:
        collection.database.client.close()



def setReferences(soort, col='analyseclean', key='key', refkey=None):
    try:
        if (col == 'analyse'):
            collection = getAnalyseCollection()
        elif (col == 'analyseclean'):
            collection = getAnalyseCleanCollection()
        else:
            raise ValueError('Error: Herkent de collectie niet met naam ' + col)
        soort_lw = soort.lower()

        # Find all main entries for type soort
        soort_query = {'soort': soort}
        if soort in const.BESTANDSOORTEN:
            soort_query = {'soort': 'Bestand', 'bestandsoort_XX': soort}
        soort_query[key] = {"$exists": True}

        if key == 'key':
            df_soort = pd.DataFrame(list(collection.find(soort_query, projection={key:1, 'ID':1})))

            key = 'key_' + soort_lw
            df_soort = df_soort.rename(columns={'_id': soort_lw+'UUID', 'index':soort_lw+'ID', 'key': key})
        else:
            df_soort = pd.DataFrame(list(collection.find(soort_query, projection={key:1, 'ID':1})))
            df_soort = df_soort.rename(columns={'_id': soort_lw+'UUID', 'index':soort_lw+'ID'})


        if df_soort.size < 1:
            logger.warning("Er zjn geen documents gevonden van het type " +soort)
            return

        if not key in df_soort.columns:
            logger.warning("Kan geen referenties maken voor " +soort + ". Geen Key-veld aanwezig.")
            return

        # Find all references to type soort
        if refkey:
            df_ref = pd.DataFrame(list(collection.find({'key_'+refkey: {"$exists": True}, 'soort': {'$ne': soort}, (soort_lw if not refkey else refkey) + 'ID': {"$exists": False}}, projection={'key_'+refkey:1})))
            df_ref = df_ref.rename(columns={'key_'+refkey: key})
        else:
            df_ref = pd.DataFrame(list(collection.find({key: {"$exists": True}, 'soort': {'$ne': soort}, (soort_lw if not refkey else refkey) + 'ID': {"$exists": False}}, projection={key:1})))
        if df_ref.size < 1:
            logger.warning("Er zjn geen referentie met key_"+soort_lw+" gevonden naar documents van het type " +soort )
            return
            
        # Merge dataframes to connect ID's en UUID's to referencing docs
        df_merge = pd.merge(df_ref, df_soort, how='inner', on=key).rename(columns={'ID': (soort_lw if not refkey else refkey) + 'ID'})
        if key == 'key_foto3':
            df2 = df_merge.groupby(['_id']).size().reset_index(name='counts')
            df2 = df2[df2.counts == 1]
            df_merge = pd.merge(df2, df_merge, how='inner', on='_id')

        if df_merge.size < 1:
            logger.warning("Er zjn geen referentie met "+key+" gevonden naar documents van het type " +soort )
            return

        # Update soort documents 
        updates=[ UpdateOne({'_id':x['_id']}, {'$set':x}) for x in [util.safe_row_to_dict(v, keep_fields=['_id']) for k,v in df_merge.iterrows()]]
        result = collection.bulk_write(updates)

        return result.bulk_api_result
        
    except Exception as err:
        msg = "Onbekende fout bij het aanroepen van een aggregation met melding: " + str(err)
        logger.error(msg)   
        raise Exception(msg) from err
 
    finally:
        collection.database.client.close()


# returns all project where the same vondstnr is used in multiple putten
aggr_vondstnr_not_unique = [ #{"$match" : {"soort" : "Vondst"}},
        {"$group" : {"_id" : {"projectcd" : "$projectcd","vondstnr" : "$vondstnr"}, "putnrs" : {"$addToSet" : "$putnr"}}},
        {"$replaceRoot" : {"newRoot" : {"_id" : 0,"projectcd" : "$_id.projectcd","aantal_put" : {"$size" : "$putnrs"}}}},
        {"$match" : {"aantal_put" : {"$gt" : 1.0}}},
        {"$group" : {"_id" : "$projectcd"}},
        {"$replaceRoot" : {"newRoot" : {"projectcd" : "$_id"}}}]

def setAndVondstUniqueInProject(col='analyse', incrementeel=False):
    """Bepaal per project of artefactnummers uniek zijn en of vondstnummers in meerdere putten voorkomen.

    Args:
        col: 'analyse' (Single_Store) of 'analyseclean' (Single_Store_Clean)
        incrementeel: als True alleen de geraakte projecten van de actieve
            verwerkingsrun bekijken (incrementeel laden)
    """
    try:        
        if (col == 'analyse'):
            collection = getAnalyseCollection()
        elif (col == 'analyseclean'):
            collection = getAnalyseCleanCollection()
        else:
            raise ValueError('Error: Herkent de collectie niet met naam ' + col)

        artefact_filter = {'soort': 'Artefact'}
        aggr_vondstnr = aggr_vondstnr_not_unique
        if incrementeel:
            projecten = delta_transform.getGeraakteProjecten(analyseCol=collection)
            if not projecten:
                logger.info("Incrementeel: geen geraakte projecten — uniciteit van artefact- en vondstnummers niet opnieuw bepaald.")
                return
            artefact_filter['projectcd'] = {'$in': projecten}
            aggr_vondstnr = delta_transform.maakProjectMatchPipeline(aggr_vondstnr_not_unique, projecten)
            # De vlag opnieuw bepalen: eerst weghalen bij alle documenten van de geraakte
            # projecten, ook die uit bronbestanden buiten de delta; hieronder komt hij terug
            # bij de projecten die hem nog nodig hebben
            result = collection.update_many(
                {'projectcd': {'$in': projecten}, delta_transform.VELD_VONDSTKEY_VLAG: {'$exists': True}},
                {'$unset': {delta_transform.VELD_VONDSTKEY_VLAG: ''}})
            logger.info(f"Incrementeel: vlag {delta_transform.VELD_VONDSTKEY_VLAG} weggehaald bij {result.modified_count} documenten van de projecten {projecten}.")

        lst_project = list(collection.find(artefact_filter).distinct('projectcd'))
        for proj in lst_project:
            try:
                df_art = pd.DataFrame(list(collection.find({'soort': 'Artefact', 'projectcd': proj}, projection={'subnr':1}))).dropna()
                unique = df_art['subnr'].is_unique
                
                project = collection.find_one({ 'soort': "Project", 'projectcd': proj })
                project['artefactnrs_unique'] = unique
                collection.replace_one({'_id': project['_id']}, project)

            except Exception as exp2:
                logger.error(f'Error while determining whether artefactnrs are unique for project {proj} with message: {str(exp2)} ')


        lst_vondst_in_multi_putten = list(pd.DataFrame(list(collection.aggregate(aggr_vondstnr)))['projectcd'])
        if len(lst_vondst_in_multi_putten) > 0:
            try:
                collection.update_many({'vondstnr': {"$exists": {"$Bool": 1}}, 'projectcd': {"$exists": {"$Bool": 1}}, 'projectcd': {'$in': lst_vondst_in_multi_putten}}, {'$set': {'vondstkey_met_putnr': True}})

            except Exception as exp2:
                logger.error(f'Error while setting whether vondstnrs are unique for project {proj} with message: {str(exp2)} ')
    except Exception as exp1:
        logger.error(f'Severe error while determining whether artefactnr and vondstnr are unique with message: {str(exp1)} ')
    finally:
        collection.database.client.close()

def test(aggr):
    collection = getAnalyseCollection()
    return list(pd.DataFrame(list(collection.aggregate(aggr)))['projectcd'])



def mergeRAAPArtefacts(col='analyse', incrementeel=False):   
    """Neem aantal, gewicht en materiaal over uit de ARTEFACT-tabellen van RAAP-databases.

    Args:
        col: 'analyse' (Single_Store) of 'analyseclean' (Single_Store_Clean)
        incrementeel: als True alleen de geraakte projecten van de actieve
            verwerkingsrun bewerken (incrementeel laden)
    """
    try:
        if (col == 'analyse'):
            collection = getAnalyseCollection()
        elif (col == 'analyseclean'):
            collection = getAnalyseCleanCollection()
        else:
            raise ValueError('Error: Herkent de collectie niet met naam ' + col)
        
        raap_match = {'brondata.table': "ARTEFACT"}
        if incrementeel:
            projecten = delta_transform.getGeraakteProjecten(analyseCol=collection)
            if not projecten:
                logger.info("Incrementeel: geen geraakte projecten — RAAP-artefacten niet opnieuw samengevoegd.")
                return
            raap_match['projectcd'] = {'$in': projecten}

        logger.info(f"Merging ARTEFACT-tables for RAAP-databases")
        df = pd.DataFrame(list(collection.aggregate([{"$match" : raap_match}, {"$addFields": {'vondstnr': "$brondata.VONDST"}}])))
        
        if not df.empty:
            # Update soort documents 
            updates = []
            for i, row in df.iterrows():
                updates.append(pymongo.UpdateMany({'projectcd': row['projectcd'], 'artefactnr': row['artefactnr']}, 
                    {'$set': {'aantal': row['aantal'], 
                            'gewicht': row['gewicht'], 
                            'materiaalcode': row['materiaalcode'], 
                            'materiaalspecifiek': row['materiaalspecifiek'],
                            'vondstnr': row['vondstnr']}}))
    
            result = collection.bulk_write(updates)
        else:
            logger.warning(f"trying to merge RAAP-artefact records, but no ARTEFACTS present.")
        
    except Exception as err:
        msg = "Onbekende fout Merging ARTEFACT-tables for RAAP-database met melding: " + str(err)
        logger.error(msg)    
        raise Exception(msg) from err

    finally:
        collection.database.client.close()


