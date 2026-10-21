# Import the os module, for the os.walk function
import os
import pymongo
from pymongo import UpdateOne, WriteConcern, InsertOne
import re
import pandas as pd
import numpy as np
import copy
import wasstraat.meta as meta
import wasstraat.mongoUtils as mongoUtil
import wasstraat.util as util
import wasstraat.verwerkingsrun as verwerkingsrun
import wasstraat.delta_transform as delta_transform
 
# Import app code
# Absolute imports for Hydrogen (Jupyter Kernel) compatibility
import shared.config as config
import shared.const as const
import logging
logger = logging.getLogger("airflow.task")

## De artefacten van deze projecten worden niet gemerged (te veel foutieve merges).
## Wordt geladen uit correcties.yml bij eerste gebruik.
def _laadArtefactNietMergenProjecten():
    import yaml
    pad = getattr(config, 'AIRFLOW_CORRECTIES_CONFIG', None)
    if not pad or not os.path.isfile(pad):
        return []
    try:
        with open(pad, 'r') as f:
            correcties = yaml.safe_load(f) or {}
        if not isinstance(correcties, dict):
            logger.warning(f"Correctiebestand {pad} bevat geen dictionary — artefact_niet_mergen overgeslagen.")
            return []
        result = correcties.get('artefact_niet_mergen', {}).get('projectcodes', [])
        if not isinstance(result, list):
            logger.warning(f"artefact_niet_mergen.projectcodes is geen lijst (type={type(result).__name__}) — overgeslagen.")
            return []
        return result
    except Exception as e:
        logger.error(f"Fout bij laden artefact_niet_mergen uit {pad}: {e}")
        return []

ARTEFACT_NOT_MERGE_PROJECTS = _laadArtefactNietMergenProjecten()

## The Artefacts of these tables will not be merged (too many wrong merges)
ARTEFACT_NOT_MERGE_TABLES = ['ROMEINS AARDEWERK']

## Generic aggregation phase for getting rid of empty cells
regx = re.compile(const.ONBEKEND_PROJECT, re.IGNORECASE)
AGGR_PHASE_CLEAN_EMPTY = {'$replaceRoot': {'newRoot': {'$arrayToObject': {'$filter': {'input': {'$objectToArray': '$$ROOT'},
      'as': 'item',
      'cond': {'$and': [{'$ne': ['$$item.v', np.nan]},
        {'$ne': ['$$item.v', None]},
        {'$ne': ['$$item.v', np.nan]},
        {'$ne': ['$$item.v', const.ONBEKEND_PROJECT]},
        {'$ne': ['$$item.v', const.ONBEKEND_PROJECT.upper()]},
        {'$ne': ['$$item.v', '-']}]}}}}}}

## Aggregation pipeline to move records of a certain type
AGGREGATE_MOVE = [
    {'$match': { 'soort': "XXX" } },
    {'$addFields': {
        'wasstraat': [{'projectcd': '$brondata.projectcd', 'table': '$brondata.table'}], 
        'brondata': ['$brondata']}},
    { "$merge": { "into": { "db": config.DB_ANALYSE, "coll": config.COLL_ANALYSE_CLEAN }, "on": "_id",  "whenMatched": "replace", "whenNotMatched": "insert" } }
    ]

## Aggregation pipeline to merge records of a certain type and then to move them
AGGREGATE_MERGE = [{'$match': {'soort': 'XXX'}},
 {'$group': {
    'doc': {'$mergeObjects': '$$ROOT'},
    'brondata': {'$addToSet': '$$ROOT.brondata'},
    'wasstraat': {'$addToSet': {'projectcd': '$$ROOT.brondata.projectcd', 'table': '$$ROOT.brondata.table'}}}},
 {'$project': {'doc.brondata': 0}},
 {'$addFields': {'doc.brondata': '$brondata',
    'doc.wasstraat': '$wasstraat'}},
 {'$replaceRoot': {'newRoot': '$doc'}},
 {'$addFields': {'brondata_count': {'$size': '$brondata'}}},
 { "$merge": { "into": { "db": config.DB_ANALYSE, "coll": config.COLL_ANALYSE_CLEAN }, "on": "_id",  "whenMatched": "replace", "whenNotMatched": "insert" } }
]

## Match phase aggregation specific for moving Artefacts: inverse of the merge phase. For alle artefacts that do not pass the merge match clause
INVERSE_MATCH_ARTEFACT = {
    "$match": {
        "$and": [
            {"soort": "Artefact"},
            {"brondata.table": {"$nin": ["ARTEFACT"]}},
            {
                "$or": [
                    {"subnr": {"$exists": False}},
                    {"brondata.ARTEFACT": {"$exists": True}},
                    {"brondata.table": {"$in": ARTEFACT_NOT_MERGE_TABLES}},
                    {"projectcd": {"$in": ARTEFACT_NOT_MERGE_PROJECTS}},
                    {"artefactsoort": {"$exists": False}},
                    {"artefactsoort": None},
                    {
                        "$expr": {
                            "$in": [
                                {"$toLower": {"$trim": {"input": "$artefactsoort"}}},
                                ["", "-", "onbekend"]
                            ]
                        }
                    },
                    # Records uit artefactsoort-specifieke tabellen (MUNT, HOUT,
                    # METAAL, etc.) hoeven niet gemerged te worden — direct moven.
                    {"brondata.table": {"$not": {"$regex": "^ARTEFACT"}}}
                ]
            }
        ]
    }
}

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


def moveSoort(soort, incrementeel=False):
    """Verplaats de documenten van een soort van Single_Store naar Single_Store_Clean.

    Args:
        soort: Move-soort
        incrementeel: als True alleen de documenten met delta_run van de actieve
            verwerkingsrun verplaatsen en, voor de soorten waarvan de sleutels van
            de vlag vondstkey_met_putnr afhangen, ook alle documenten van de
            geraakte projecten (delta_transform.getDeltaOfProjectFilter); elk
            verplaatst document krijgt delta_run (incrementeel laden)
    """
    if not soort in meta.getKeys(meta.MOVEANDMERGE_MOVE):
        msg = "Fout bij het aanroepen van de move aggregation. Onbekend soort:  " + soort
        logger.error(msg)    
        raise Exception(msg)

    aggr = getMoveAggregate(soort)
    run = None
    if incrementeel:
        run = verwerkingsrun.huidigeRun()
        aggr[0]['$match'].update(delta_transform.getDeltaOfProjectFilter(soort, run))
    try:
        #Aggregate Pipelin
        collection = getAnalyseCollection()
        if soort in const.BESTANDSOORTEN:
            aggr.insert(-1, {'$match': {'imageID': {'$exists': True}}})
            aggr.insert(-1, {'$addFields': {'soort': 'Bestand'}})
            aggr.insert(-1, {'$addFields': {'bestandsoort_XX': soort}})
        if run:
            aggr = delta_transform.voegDeltaRunToeVoorMerge(aggr, run['run_id'])

        logger.info("Calling aggregation: " + str(aggr))
        collection.aggregate(aggr, allowDiskUse=True)
        
    except Exception as err:
        msg = "Onbekende fout bij het aanroepen van een aggregation met melding: " + str(err)
        logger.error(msg)    
        raise Exception(msg) from err

    finally:
        collection.database.client.close()


def mergeSoort(soort, incrementeel=False):
    """Voeg de documenten van een soort met dezelfde sleutel samen in Single_Store_Clean.

    Args:
        soort: Merge-soort
        incrementeel: als True alleen de geraakte sleutels van de actieve
            verwerkingsrun opnieuw samenvoegen en daarna de samengevoegde
            documenten van verdwenen sleutels verwijderen (incrementeel laden)
    """
    if not soort in meta.getKeys(meta.MOVEANDMERGE_INHERITED) and not soort in meta.getKeys(meta.MOVEANDMERGE_MERGE):
        msg = "Fout bij het aanroepen van de merge aggregation voor inherit. Onbekend soort:  " + soort
        logger.error(msg)    
        raise Exception(msg)

    key = 'key_subnr' if soort == 'Artefact' else 'key'
    aggr = getMergeAggregate(soort, key=key)
    try:
        #Aggregate Pipelin
        collection = getAnalyseCollection()
        # Merge Tekening into photo's
        if soort in const.BESTANDSOORTEN:
            aggr.insert(-1, {'$match': {'imageID': {'$exists': True}}})
            aggr.insert(-1, {'$addFields': {'soort': 'Bestand'}})
            aggr.insert(-1, {'$addFields': {'bestandsoort_XX': soort}})

        if soort == 'Artefact':
            aggr.insert(-1, {
                '$set': {
                    'artefactsoort': {
                        '$let': {
                            'vars': {'val': {'$ifNull': ['$artefactsoort', '']}},
                            'in': {
                                '$cond': [
                                    { '$or': [
                                        { '$eq': ['$$val', ''] },
                                        { '$eq': [ { '$trim': { 'input': '$$val' } }, '' ] },
                                        { '$eq': [ { '$toLower': { '$trim': { 'input': '$$val' } } }, 'onbekend' ] },
                                        { '$eq': [ { '$trim': { 'input': '$$val' } }, '-' ] }
                                    ]},
                                    'Onbekend',
                                    { '$trim': { 'input': '$$val' } }
                                ]
                            }
                        }
                    }
                }
            })
        if incrementeel:
            mergeSoortDelta(soort, key, aggr, collection)
            return

        logger.info("Calling aggregation: " + str(aggr))
        collection.aggregate(aggr, allowDiskUse=True)
        
    except Exception as err:
        msg = "Onbekende fout bij het aanroepen van een aggregation met melding: " + str(err)
        logger.error(msg)    
        raise Exception(msg) from err

    finally:
        collection.database.client.close()


def mergeSoortDelta(soort, key, aggr, collection):
    """Voeg bij een incrementele run alleen de geraakte sleutels van een soort opnieuw samen.

    De geraakte sleutels zijn die van de delta-documenten plus verwijderde_keys
    uit het run-document; voor Vondst, Artefact en Monster ook alle sleutels van
    de geraakte projecten (delta_transform.bepaalGeraakteSleutels). De merge-pipeline krijgt een $match op die sleutels en
    $addFields delta_run; $merge vervangt het bestaande document met hetzelfde
    _id. Omdat een samengevoegd document het _id van het laatste brondocument in
    de groep krijgt, levert een gewijzigde groep een nieuw document op; daarom
    worden daarna de samengevoegde documenten met een geraakte sleutel die niet
    opnieuw zijn geschreven verwijderd (delta_transform.verwijderVerdwenenSleutels).

    Args:
        soort: Merge-soort
        key: sleutelveld ('key' of 'key_subnr')
        aggr: volledige merge-pipeline van de soort
        collection: Single_Store-collectie
    """
    run = verwerkingsrun.huidigeRun()
    run_id = run['run_id']
    cleancollection = collection.database[config.COLL_ANALYSE_CLEAN]
    sleutels = delta_transform.bepaalGeraakteSleutels(soort, collection, run, cleancollection)
    if not sleutels:
        logger.info(f"Incrementeel: geen geraakte sleutels voor {soort} — niets opnieuw samen te voegen.")
        delta_transform.werkTellingBij(f'merge.{soort}', {'sleutels': 0, 'verwijderd': 0})
        return

    logger.info(f"Incrementeel: {len(sleutels)} geraakte sleutels voor {soort} opnieuw samenvoegen.")
    for batch in delta_transform.inBatches(sleutels):
        collection.aggregate(delta_transform.maakDeltaMergePipeline(aggr, key, batch, run_id), allowDiskUse=True)

    verwijderd = delta_transform.verwijderVerdwenenSleutels(soort, cleancollection, sleutels, run_id)
    logger.info(f"Incrementeel: {verwijderd} samengevoegde documenten van {soort} met een verdwenen sleutel verwijderd.")
    delta_transform.werkTellingBij(f'merge.{soort}', {'sleutels': len(sleutels), 'verwijderd': verwijderd})


def mergeMissing(soort, incrementeel=False):
    """Genereer ontbrekende entiteiten (Put, Vlak, Spoor, Vondst, Doos) in Single_Store_Clean.

    Args:
        soort: soort met een generate-missing-pipeline in meta.py
        incrementeel: als True eerst de gegenereerde documenten van de geraakte
            projecten van de actieve verwerkingsrun verwijderen en dan alleen voor
            die projecten opnieuw genereren (incrementeel laden)
    """
    logger.info(f"Start ind and merge missing for {soort}")
    if not soort in meta.getKeys(meta.MOVEANDMERGE_GENERATE_MISSING_PIPELINES):
        msg = f"Fout bij het aanroepen van de merge aggregation voor merge missing. Onbekend soort: {soort}. Alleen deze zijn geldig: {meta.getKeys(meta.MOVEANDMERGE_GENERATE_MISSING_PIPELINES)}"
        logger.error(msg)    
        raise Exception(msg)

    aggr_lst = meta.getGenerateMissingPipelines(soort)

    delta_run = None
    if incrementeel:
        run = verwerkingsrun.huidigeRun()
        projecten = delta_transform.getGeraakteProjecten(run)
        if not projecten:
            logger.info(f"Incrementeel: geen geraakte projecten — geen ontbrekende {soort}-records opnieuw gegenereerd.")
            delta_transform.werkTellingBij(f'gegenereerd.{soort}', {'verwijderd': 0, 'toegevoegd': 0})
            return
        delta_run = run['run_id']
        aggr_lst = [delta_transform.maakProjectMatchPipeline(aggr, projecten) for aggr in aggr_lst]

    try:
        #Aggregate Pipelin
        collection = getAnalyseCollection()
        cleancollection = getAnalyseCleanCollection()

        if incrementeel:
            verwijderd = delta_transform.verwijderGegenereerdeDocumenten(soort, cleancollection, projecten)
            logger.info(f"Incrementeel: {verwijderd} gegenereerde {soort}-records van de projecten {projecten} verwijderd.")
            delta_transform.werkTellingBij(f'gegenereerd.{soort}', {'verwijderd': verwijderd, 'toegevoegd': 0})

        for aggr in aggr_lst:
            logger.info("Calling aggregation: " + str(aggr))
            collection.aggregate(aggr, allowDiskUse=True)

            df_gen = pd.DataFrame(list(collection.aggregate(aggr)))            
            if not df_gen.empty and 'key' in df_gen.columns:
                if incrementeel:
                    # Alleen de records met een van de gegenereerde keys zijn nodig voor de vergelijking
                    df_orig = pd.DataFrame(list(cleancollection.find({'soort': soort, 'key': {'$in': list(df_gen['key'].dropna().unique())}})))
                else:
                    df_orig = pd.DataFrame(list(cleancollection.find({'soort': soort})))

                if df_orig.empty or 'key' not in df_orig.columns:
                    # Nog geen enkel record van deze soort (bijv. geen PUT-tabel in de brondata): alles ontbreekt
                    df = df_gen
                else:
                    df_all = df_gen.merge(df_orig, on=['key', 'soort'], how='left', indicator=True, suffixes=[None, "_orig"])
                    df = df_all[df_all._merge == 'left_only'][df_gen.columns]
                if len(df) < 1:
                    logger.info(f"No missing records for type: {soort} nothing inserted in collection.")
                    return

                records = [util.safe_row_to_dict(v, keep_fields=['_id', 'key', 'soort']) for k,v in df.iterrows()]
                if delta_run:
                    for record in records:
                        record[delta_transform.VELD_DELTA_RUN] = delta_run
                inserts=[ InsertOne(record) for record in records]
                result = cleancollection.bulk_write(inserts)
                if delta_run:
                    delta_transform.werkTellingBij(f'gegenereerd.{soort}.toegevoegd', len(inserts))
            else:
                logger.warning(f"trying to insert empty dataframe of soort: {soort} into collection.")

    except Exception as err:
        msg = "Onbekende fout bij het aanroepen van een aggregation met melding: " + str(err)
        logger.error(msg)    
        raise Exception(msg) from err

    finally:
        collection.database.client.close()
        cleancollection.database.client.close()


'''
Convenience methodes to retrieve table and project data from bson (non json) fields for pandas. 
mergeFotoInfo uses these values 
'''
regexTable = re.compile(r'\'table\': \'(.*?)\'') # regex to replace Object
regexProject = re.compile(r'\'projectcd\': \'(.*?)\'') # regex to replace Object
def getTable(brondata):  
    try:
        return regexTable.search(str(brondata)).group(1)
    except:
        return None

def getProject(brondata):    
    try:
        return regexProject.search(str(brondata)).group(1)
    except:
        return None



def mergeFotoinfo(incrementeel=False):
    """Voeg de foto's samen met hun koppelingen (fotolijst) en beschrijvingen in Single_Store_Clean.

    Args:
        incrementeel: als True alleen de foto's met delta_run, in een geraakt
            project of in een gewijzigde fotolijst van de actieve verwerkingsrun
            opnieuw samenvoegen (incrementeel laden)
    """
    logger.info(f"Starting with photo merging")
    try:
        #Aggregate Pipeline
        collection = getAnalyseCollection()
        cleancollection = getAnalyseCleanCollection()

        foto_filter = {"soort": "Foto"}
        delta_run = None
        if incrementeel:
            run = verwerkingsrun.huidigeRun()
            foto_filter = delta_transform.getFotoDeltaFilter(collection, run)
            if foto_filter is None:
                logger.info("Incrementeel: geen geraakte foto's — overslaan.")
                return
            delta_run = run['run_id']

        # get all Photo records
        df_foto = pd.DataFrame(list(collection.find(foto_filter)))

        if df_foto.empty:
            logger.info("Geen Foto-records gevonden in Single_Store — overslaan.")
            return

        # get all Photo descr records
        df_fotobeschr = pd.DataFrame(list(collection.find({"soort": "Fotobeschrijving"})))
        if not df_fotobeschr.empty and 'pad' in df_fotobeschr.columns:
            df_fotobeschr["abcd-nr"] = df_fotobeschr.apply(lambda x: x["pad"].split('\\')[-1].lower() if x["pad"] and type(x["pad"]) == str else '', axis=1)
        else:
            df_fotobeschr = pd.DataFrame()

        df_fotokoppel = pd.DataFrame(list(collection.find({"soort": "Fotokoppel"})))
        if not df_fotokoppel.empty and 'abcd-nr' in df_fotokoppel.columns:
            df_fotokoppel["abcd-nr"] = df_fotokoppel.apply(lambda x: x["abcd-nr"].lower() if x["abcd-nr"] and type(x["abcd-nr"]) == str else '', axis=1)
        else:
            df_fotokoppel = pd.DataFrame()

        # Als er geen koppeldata is, foto's direct als Bestand overnemen
        if df_fotokoppel.empty and df_fotobeschr.empty:
            logger.info("Geen Fotokoppel- of Fotobeschrijving-records — foto's worden direct overgenomen.")
            df_foto['soort'] = 'Bestand'
            df_foto['bestandsoort_XX'] = 'Foto'
            if 'brondata' in df_foto.columns:
                df_foto['brondata'] = df_foto['brondata'].apply(lambda x: [x])
            else:
                df_foto['brondata'] = df_foto.apply(lambda x: [{}], axis=1)
            df_foto['wasstraat'] = df_foto.apply(lambda x: [{'projectcd': x.get('projectcd'), 'table': getTable(x.get('brondata', [{}])[0])}], axis=1)
            desired_columns = ['_id', 'fileName', 'imageID', 'imageMiddleID', 'imageThumbID',
                'fileType', 'directory', 'mime_type', 'fototype', 'soort', 'projectcd',
                'key', 'key_project', 'key_project_type', 'brondata', 'wasstraat', 'bestandsoort_XX']
            available_columns = [c for c in desired_columns if c in df_foto.columns]
            df_merge = df_foto[available_columns]
        else:
            # Merge dataframes to get a complete Photo-dataframe
            if not df_fotokoppel.empty:
                df_merge = df_foto.merge(df_fotokoppel, how="left", right_on="bestandsnaam", left_on="fileName", suffixes=("", "_koppel"))
            else:
                df_merge = df_foto.copy()
                df_merge['abcd-nr'] = ''

            if not df_fotobeschr.empty:
                df_merge = df_merge.merge(df_fotobeschr, how="left", on=["abcd-nr", "projectcd"], suffixes=("", "_beschr"))

            df_merge['soort'] = 'Bestand'
            df_merge['bestandsoort_XX'] = 'Foto'
            df_merge['brondata'] = df_merge.apply(lambda x: [x['brondata'], x.get('brondata_beschr')], axis=1)
            df_merge['wasstraat'] = df_merge.apply(lambda x: [{'projectcd': x['projectcd'], 'table': getTable(elem)} for elem in x['brondata'] if getTable(elem)], axis=1)
            if 'materiaal' in df_merge.columns and 'materiaalgroep' in df_merge.columns:
                df_merge['materiaal'] = df_merge.apply(lambda x: util.firstValue(x['materiaal'], x['materiaalgroep']), axis=1)
            elif 'materiaalgroep' in df_merge.columns:
                df_merge['materiaal'] = df_merge['materiaalgroep']
            desired_columns = ['_id', 'fileName', 'imageID', 'imageMiddleID', 'imageThumbID',
                'fileType', 'directory', 'mime_type', 'fototype', 'soort', 'projectcd',
                'materiaal', 'putnr', 'vondstnr', 'fotonr', 'vondstkey_met_putnr',
                'key', 'key_project', 'key_project_type', 'key_vondst',
                'key_artefact', 'subnr', 'brondata', 'key_foto1', 'key_foto2', 'key_foto3',
                'pad', 'spoornr', 'profiel', 'omschrijving', 'vlaknr', 'richting', 'wasstraat', 'bestandsoort', 'bestandsoort_XX']
            available_columns = [c for c in desired_columns if c in df_merge.columns]
            df_merge = df_merge[available_columns]


        records = [util.safe_row_to_dict(v, keep_fields=['_id', 'soort']) for k,v in df_merge.iterrows()]
        if delta_run:
            for record in records:
                record[delta_transform.VELD_DELTA_RUN] = delta_run
        updates= [ pymongo.ReplaceOne({"_id": record['_id']}, record, upsert=True) for record in records]
        if len(updates) > 0:
            logger.info(f"Upserting {len(updates)} photo records.")
            result = cleancollection.bulk_write(updates)
        else:
            logger.warning("Could not merge photo data due to empty dataset")

    except Exception as err:
        msg = "Onbekende fout bij het mergen van foto-informatie met melding: " + str(err)
        logger.error(msg)    
        raise Exception(msg) from err

    finally:
        collection.database.client.close()
        cleancollection.database.client.close()


