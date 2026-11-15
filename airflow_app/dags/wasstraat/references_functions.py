# Import the os module, for the os.walk function
import math
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
import wasstraat.foutbeleid as foutbeleid
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


# Fasen van een sleutelpipeline (meta.SET_KEYS_PIPELINES) waarvan setReferenceKeys de berekende
# velden kent; bij andere fasen schrijft hij het hele document terug (issue 88)
FASEN_MET_VELDEN = ('$addFields', '$set')
# Velden die setReferenceKeys ook schrijft als de pipeline er geen waarde voor geeft (dan None),
# zoals voorheen met util.safe_row_to_dict(keep_fields=['_id', 'key', 'soort'])
VELDEN_OOK_LEEG = ('key', 'soort')


def getPipelineVelden(pipeline):
    """Retourneer de velden die een sleutelpipeline berekent: de velden van zijn $addFields- en $set-fasen.

    Args:
        pipeline: sleutelpipeline uit meta.getReferenceKeysPipeline

    Returns:
        Lijst met veldnamen (in volgorde van voorkomen), of None als de pipeline
        andere fasen heeft dan $match, $addFields en $set: dan is niet vast te
        stellen welke velden hij verandert
    """
    velden = []
    for fase in pipeline:
        naam = next(iter(fase), None)
        if naam == '$match':
            continue
        if naam not in FASEN_MET_VELDEN:
            return None
        for veld in fase[naam]:
            if veld not in velden:
                velden.append(veld)
    return velden


def _waardeOpPad(doc, pad):
    """Waarde van een (geneste) veldnaam met punten, of None als het veld ontbreekt."""
    for deel in pad.split('.'):
        if not isinstance(doc, dict) or deel not in doc:
            return None
        doc = doc[deel]
    return doc


def maakSleutelUpdate(doc, velden):
    """Bouw de $set voor één uitkomst van een sleutelpipeline: alleen de gegeven velden.

    Een veld zonder waarde (None of NaN) wordt niet geschreven, behalve key en
    soort (VELDEN_OOK_LEEG): die worden None. Dat is hetzelfde als de
    terugschrijving van vóór issue 88 (safe_row_to_dict), maar dan alleen voor
    de velden die de pipeline berekent.

    Args:
        doc: document uit de aggregatie
        velden: veldnamen die geschreven mogen worden

    Returns:
        Dict voor $set (kan leeg zijn)
    """
    update = {}
    for veld in velden:
        if veld == '_id':
            continue
        waarde = _waardeOpPad(doc, veld)
        if waarde is None or (isinstance(waarde, float) and math.isnan(waarde)):
            if veld in VELDEN_OOK_LEEG:
                update[veld] = None
            continue
        update[veld] = waarde
    return update


def setReferenceKeys(pipeline, soort, col='analyse', incrementeel=False):
    """Bereken de sleutels (key, key_project, ...) van een soort met de pipeline uit meta.py.

    Schrijft per document alleen de velden die de pipeline berekent (de
    $addFields- en $set-fasen, getPipelineVelden), niet het hele document
    (issue 88). De Set_ReferenceKeys-taken van Transform 3 draaien parallel.
    Tot issue 88 schreef elke taak de documenten volledig terug zoals hij ze
    had gelezen, en de lege pipeline van Fotokoppel las en schreef zo de hele
    collectie: de key (en bij stellingen de soort) die een andere taak
    intussen had berekend, werd dan met de oude waarde (None) overschreven.
    Welke documenten dat trof hing af van de timing; in de volledige cyclus
    van 29 oktober 2026 op de productie-installatie onder meer alle sporen,
    vullingen, stellingen en tekeningen en de meeste standplaatsen. Een lege
    pipeline berekent niets en doet nu niets.

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
    if not pipeline:
        logger.info(f"Soort {soort} heeft geen sleutelpipeline in meta.py: er zijn geen sleutels te berekenen.")
        return
    if '$match' not in pipeline[0]:
        logger.warning(f"De sleutelpipeline van {soort} begint niet met $match; alleen de documenten van soort "
                       f"{soort} worden bewerkt.")
        pipeline = [{'$match': {'soort': soort}}] + list(pipeline)
    if incrementeel:
        pipeline = delta_transform.voegToeAanEersteMatch(
            pipeline, delta_transform.getDeltaOfProjectFilter(soort, verwerkingsrun.huidigeRun()))
    velden = getPipelineVelden(pipeline)
    if velden is None:
        logger.warning(f"De sleutelpipeline van {soort} heeft andere fasen dan $match, $addFields en $set; de "
                       f"documenten worden volledig teruggeschreven.")

    collection = None
    try:
        if (col == 'analyse'):
            collection = getAnalyseCollection()
        elif (col == 'analyseclean'):
            collection = getAnalyseCleanCollection()
        else:
            raise ValueError('Error: Herkent de collectie niet met naam ' + col)

        logger.info(f"Sleutels berekenen voor soort {soort} met pipeline {pipeline}")
        # Eerst alle uitkomsten lezen, dan schrijven: de pipeline kan een geïndexeerd veld (soort) wijzigen
        updates = []
        for doc in collection.aggregate(pipeline, allowDiskUse=True):
            update = maakSleutelUpdate(doc, velden if velden is not None else list(doc))
            if update:
                updates.append(UpdateOne({'_id': doc['_id']}, {'$set': update}))

        if updates:
            for batch in delta_transform.inBatches(updates):
                collection.bulk_write(batch, ordered=False)
            logger.info(f"Sleutels van {len(updates)} documenten van soort {soort} geschreven "
                        f"(velden: {velden if velden is not None else 'alle'}).")
        else:
            logger.warning(f"Geen documenten van soort {soort} gevonden in collectie {col} om sleutels voor te berekenen.")

    except Exception as err:
        msg = "Onbekende fout bij het aanroepen van een aggregation met melding: " + str(err)
        logger.error(msg)
        raise Exception(msg) from err

    finally:
        if collection is not None:
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

    Een fout bij één project is een waarschuwing (issue 54): de vlag
    artefactnrs_unique blijft voor dat project leeg, de fout wordt geteld en
    gemeld in het run-document. Een fout buiten de afzonderlijke projecten
    laat de taak falen; tot issue 54 werd ook die alleen gelogd, waarna de
    sleutels zonder de vlag vondstkey_met_putnr werden berekend.

    Args:
        col: 'analyse' (Single_Store) of 'analyseclean' (Single_Store_Clean)
        incrementeel: als True alleen de geraakte projecten van de actieve
            verwerkingsrun bekijken (incrementeel laden)

    Raises:
        Exception: bij een fout buiten de afzonderlijke projecten
    """
    collection = None
    mislukte_projecten = []
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
                if 'subnr' not in df_art.columns:
                    # Geen enkel artefact met een subnr: niets te bepalen (de vlag blijft leeg, zoals voorheen)
                    logger.info(f"Project {proj}: geen artefacten met een subnr; uniciteit niet bepaald.")
                    continue
                unique = df_art['subnr'].is_unique
                
                project = collection.find_one({ 'soort': "Project", 'projectcd': proj })
                project['artefactnrs_unique'] = unique
                collection.replace_one({'_id': project['_id']}, project)

            except Exception as exp2:
                logger.error(f'Error while determining whether artefactnrs are unique for project {proj} with message: {str(exp2)} ')
                mislukte_projecten.append({'projectcd': proj, 'fout': f"{type(exp2).__name__}: {exp2}"[:500]})


        # Zonder treffers had pd.DataFrame([]) geen kolom projectcd (KeyError); dat werd tot issue 54
        # als 'Severe error' gelogd en genegeerd, en nu zou de taak erop falen
        lst_vondst_in_multi_putten = [r['projectcd'] for r in collection.aggregate(aggr_vondstnr)
                                      if r.get('projectcd') is not None]
        if len(lst_vondst_in_multi_putten) > 0:
            try:
                collection.update_many({'vondstnr': {"$exists": {"$Bool": 1}}, 'projectcd': {"$exists": {"$Bool": 1}}, 'projectcd': {'$in': lst_vondst_in_multi_putten}}, {'$set': {'vondstkey_met_putnr': True}})

            except Exception as exp2:
                msg = f'Error while setting whether vondstnrs are unique for projects {lst_vondst_in_multi_putten} with message: {str(exp2)} '
                logger.error(msg)
                raise Exception(msg) from exp2
    except Exception as exp1:
        msg = f'Severe error while determining whether artefactnr and vondstnr are unique with message: {str(exp1)} '
        logger.error(msg)
        raise Exception(msg) from exp1
    finally:
        if collection is not None:
            collection.database.client.close()

    if mislukte_projecten:
        msg = (f"Bij {len(mislukte_projecten)} project(en) kon niet bepaald worden of de artefactnummers uniek zijn: "
               f"{[p['projectcd'] for p in mislukte_projecten[:10]]}.")
        logger.warning(msg)
        foutbeleid.meld(foutbeleid.NIVEAU_WAARSCHUWING, foutbeleid.SOORT_UNICITEIT_NIET_BEPAALD, msg,
                        aantal=len(mislukte_projecten), details=mislukte_projecten[:10])

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


