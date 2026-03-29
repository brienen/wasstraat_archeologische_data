
# Import the os module, for the os.walk function
import pymongo
import json
import re
import os
import yaml
import pandas as pd
import numpy as np
import wasstraat.harmonizer as harmonizer

# Import app code
# Absolute imports for Hydrogen (Jupyter Kernel) compatibility
import shared.config as config
import shared.const as const
import wasstraat.mongoUtils as mongoUtil
from wasstraat.profielen import get_profiel

import logging
logger = logging.getLogger("airflow.task")


_correcties_cache = None

def laadCorrecties():
    """Laad het correctiebestand (YAML) en cache het resultaat.

    Returns:
        dict met correctieregels, of leeg dict als het bestand niet bestaat.
    """
    global _correcties_cache
    if _correcties_cache is not None:
        return _correcties_cache

    pad = getattr(config, 'AIRFLOW_CORRECTIES_CONFIG', None)
    if not pad or not os.path.isfile(pad):
        logger.info(f"Geen correctiebestand gevonden op {pad} — geen gemeente-specifieke correcties.")
        _correcties_cache = {}
        return _correcties_cache

    try:
        with open(pad, 'r') as f:
            result = yaml.safe_load(f)
    except yaml.YAMLError as e:
        logger.error(f"Ongeldig YAML in {pad}: {e} — geen correcties toegepast.")
        _correcties_cache = {}
        return _correcties_cache

    if not isinstance(result, dict):
        logger.error(f"Correctiebestand {pad} bevat geen YAML-dictionary (type={type(result).__name__}) — geen correcties toegepast.")
        _correcties_cache = {}
        return _correcties_cache

    _correcties_cache = result
    logger.info(f"Correctiebestand geladen: {pad}")
    return _correcties_cache


def fixProjectNames():
    """Pas brondata-correcties toe uit het correctiebestand (correcties.yml).

    Leest correctieregels uit de sectie 'brondata_correcties'. Elke regel
    specificeert een staging-collectie, veld, regex-patroon en waarde.
    Dit fixt raw veldwaarden in staging vóór harmonisatie — nodig als
    brondata afwijkende codes bevat die niet matchen met de projectenlijst.

    Daarnaast worden projectcodes die geen string zijn altijd naar string
    geconverteerd (generieke correctie, niet gemeente-specifiek).
    """
    try:
        logger.info("Calling update statements to fix project codes...")
        myclient = pymongo.MongoClient(str(config.MONGO_URI))
        stagingdb = myclient[str(config.DB_STAGING)]

        correcties = laadCorrecties()

        # Brondata-correcties: fix raw velden in staging-collecties
        for i, fix in enumerate(correcties.get('brondata_correcties', [])):
            try:
                coll_name = getattr(config, fix['collectie'], None)
                if not coll_name:
                    logger.warning(f"  Onbekende collectie-constante: {fix['collectie']} — overslaan")
                    continue
                coll = stagingdb[coll_name]
                zoek_veld = fix.get('zoek_veld', fix.get('veld', 'projectcd'))
                doel_veld = fix.get('doel_veld', zoek_veld)
                result = coll.update_many(
                    {zoek_veld: {"$regex": str(fix['patroon'])}},
                    {"$set": {doel_veld: str(fix['waarde'])}}
                )
                if result.modified_count > 0:
                    logger.info(f"  Brondata fix: {fix['collectie']}.{zoek_veld}~/{fix['patroon']}/ → {doel_veld}={fix['waarde']} ({result.modified_count} docs)")
            except (KeyError, TypeError) as e:
                logger.error(f"  Ongeldige brondata_correctie #{i}: {fix} — {e}. Overslaan.")
                continue

        # Generieke correctie: projectcd naar string converteren (niet gemeente-specifiek)
        stagingdb[config.COLL_STAGING_OUD].update_many(
            {'projectcd': {'$not': {"$type": 2}}},
            [{"$set": {"projectcd": {"$toString": "$projectcd"}}}]
        )
        stagingdb[config.COLL_PLAATJES].update_many(
            {'projectcd': {'$not': {"$type": 2}}},
            [{"$set": {"projectcd": {"$toString": "$projectcd"}}}]
        )

    except Exception as err:
        msg = "Onbekende fout bij het fixen van projectcodes met melding: " + str(err)
        logger.error(msg)
        raise Exception(msg) from err
    finally:
        myclient.close()


def fixMonsterProjectcds():
    """
    Method to fix the old projectnames that are being used in the Monsterdatabase. Unknown projectcodes are set to "Unknowm"

    Old projectnames are matched with the data from DeltIT Opgravingen, where both old and new values are found.
    """
    
    try:
        logger.info("Starting fix of old projectcodes of Monster Database...")
        myclient = pymongo.MongoClient(str(config.MONGO_URI))
        analyseDb = myclient[str(config.DB_ANALYSE)]
        analyseCol = analyseDb[config.COLL_ANALYSE]

        # Early return als er geen Monster-records in de database zitten
        monster_count = analyseCol.count_documents({'soort': 'Monster'})
        if monster_count == 0:
            logger.info("Geen Monster-records gevonden in Single_Store — overslaan.")
            return

        # Fisrt set all projeccd to Unknown
        analyseCol.update_many({'soort': 'Monster'}, { "$set": { "projectcd": None } })

        #Then get all Monsters with an old code
        df_monsters = pd.DataFrame(list(analyseCol.find({'soort': 'Monster', 'brondata.PROJECT': {'$exists': True}}, {'projectcd':0})))

        if df_monsters.empty or 'project' not in df_monsters.columns:
            logger.info("Geen Monster-records met brondata.PROJECT gevonden — overslaan.")
            return

        df_project = pd.DataFrame(list(analyseCol.find({'soort': 'Project'}, {'projectcd':1, 'project': 1, '_id':0})))

        if df_project.empty or 'projectcd' not in df_project.columns or 'project' not in df_project.columns:
            logger.warning("Geen Project-records met projectcd en project gevonden — kan Monster-projectcodes niet matchen.")
            return

        df2_project = pd.concat([df_project['projectcd'], df_project['projectcd']], axis=1, ignore_index=True)
        df2_project.columns = ['projectcd', 'project']

        # Add projectcd and project as porject-field to make sure all occurences are matched
        df_project.dropna(subset=['project'], inplace=True)
        df_project = pd.concat([df_project, df2_project], ignore_index=True)
        df_project.drop_duplicates(subset=['project'], inplace=True)

        # Set alle projectcd of monster database
        df_monsters = df_monsters.merge(df_project, on=['project'], how='left')
        df_monsters['projectcd'] = df_monsters['projectcd'].fillna(value = const.ONBEKEND_PROJECT)
        
        #Some projects were not found: report these
        logger.warning(f"Not all old projectcodes of Monsterdatabase could be fixed. These could not be matched: {set(list(df_monsters[df_monsters.projectcd == const.ONBEKEND_PROJECT]['project']))}")
        
        if not df_monsters.empty:
            # Update soort documents 
            updates=[ pymongo.UpdateOne({'_id':row['_id']}, {'$set':{'projectcd': row['projectcd']}}) for index, row in df_monsters.iterrows()]  # 
            analyseCol.bulk_write(updates)
        else:
            logger.warning(f"trying to update empty dataframe of monsters to fix old projeccodes.")

    except Exception as err:
        msg = "Onbekende fout bij het old projectcodes of Monster Database met melding: " + str(err)
        logger.error(msg)    
        raise Exception(msg) from err
    finally:
        myclient.close()



def harmonize(collection, strOrAggr):
    if type(strOrAggr) == str:
        pipeline = harmonizer.getHarmonizeAggr(str(strOrAggr)) 
    else:
        pipeline = strOrAggr[0]

    try: 
        logger.info("Calling aggregation with pipeline: " + str(pipeline))
        myclient = pymongo.MongoClient(str(config.MONGO_URI))
        stagingdb = myclient[str(config.DB_STAGING)]
        stagingcollection = stagingdb[collection]
        stagingcollection.aggregate(pipeline)

    except Exception as err:
        msg = "Onbekende fout bij het aanroepen van een aggregation met melding: " + str(err)
        logger.error(msg)    
        raise Exception(msg) from err
    finally:
        myclient.close()



''''
Parse alle filenames of imported files, and split them into:
1. Artfact pictures
2. Site pictures
3. "Sfeer" pictures

Also set projectcd, vondstnr, artefactnr and subnummer
'''
def parseFotobestanden():   
    try: 
        myclient = pymongo.MongoClient(str(config.MONGO_URI))
        stagingDb = myclient[str(config.DB_STAGING)]
        analyseDb = myclient[str(config.DB_ANALYSE)]
        stagingCol = stagingDb[config.COLL_PLAATJES]
        analyseCol = analyseDb[config.COLL_ANALYSE]

        #extract projectinfo from filename
        for doc in stagingCol.find():

            # Get projectcd from fullfilename (via gemeenteprofiel)
            profiel = get_profiel()
            projectcd = profiel.extract_projectcode_uit_bestandsnaam(doc['fileName'], doc.get('directory', ''))



            try: 
                # Remove double file extensions
                if not os.path.splitext(os.path.splitext(doc['fileName'])[0])[1] == '':
                    doc['fileName'] = os.path.splitext(doc['fileName'])[0]

                # Alle word-bestanden worden als Overige Rapport ingelezen 
                if doc['fileType'] and str(doc['fileType']).lower() in ['.doc', '.docx']:
                    doc['rapportnr'] = doc['fullFileName']   
                    doc['key'] = 'R' + doc['fullFileName']        
                    doc['soort'] = 'Rapport' 
                    doc['fototype'] = 'R' 
                    doc['bestandsoort'] = const.RAPP_OVERIGE_RAPPORTAGE
                    analyseCol.replace_one({"_id": doc['_id']}, doc, upsert=True)
                    continue


                # Per-entiteit identificatie via gemeenteprofiel
                # Probeer achtereenvolgens: foto, tekening
                parsed = profiel.identificeer_foto(doc, projectcd)
                if parsed is not None:
                    analyseCol.replace_one({"_id": doc['_id']}, parsed, upsert=True)
                    continue

                parsed = profiel.identificeer_tekening(doc, projectcd)
                if parsed is not None:
                    analyseCol.replace_one({"_id": doc['_id']}, parsed, upsert=True)
                    continue


                # Rapporten: bestanden waarvan de naam begint met een rapportcode-prefix
                rapport_prefixen_raw = laadCorrecties().get('rapportcode_prefixen', [])
                # Filter ongeldige entries (ontbrekende prefix/type)
                rapport_prefixen = [p for p in rapport_prefixen_raw if isinstance(p, dict) and 'prefix' in p and 'type' in p]
                if rapport_prefixen:
                    prefix_patroon = '|'.join(str(p['prefix']) for p in rapport_prefixen)
                    prefix_type_map = {str(p['prefix']).upper(): p['type'] for p in rapport_prefixen}
                    matchObj = re.match(r'^(' + prefix_patroon + r')\s*([0-9]{2,3}).*', doc['fileName'], re.M|re.I)
                    if matchObj:
                        doc['rapportnr'] = matchObj.group(1) + str(int(matchObj.group(2))).zfill(3)
                        doc['key'] = 'R' + doc['rapportnr']
                        doc['soort'] = 'Rapport'
                        doc['fototype'] = 'R'
                        # Bepaal bestandsoort op basis van het prefix-type uit de configuratie
                        matched_prefix = matchObj.group(1).upper()
                        rapport_type = prefix_type_map.get(matched_prefix, 'archeologische_rapportage')
                        if rapport_type == 'archeologische_rapportage':
                            doc['bestandsoort'] = const.RAPP_ARCHEOLOGISCHE_RAPPORTAGE
                        else:
                            doc['bestandsoort'] = const.RAPP_ARCHEOLOGISCHE_NOTITIE
                        analyseCol.replace_one({"_id": doc['_id']}, doc, upsert=True)
                        continue




                # Match Tekeningen
                if 'tekening' in str(doc['fileName']).lower() and not 'aantekening' in str(doc['fileName']).lower():
                    doc['projectcd'] = projectcd
                    doc['soort'] = 'Tekening' 
                    doc['bestandsoort'] = const.TEK_OVERIGE
                    doc['fototype'] = 'T'
                    doc['tekeningcd'] = doc['fullFileName']

                    analyseCol.replace_one({"_id": doc['_id']}, doc, upsert=True)
                    continue


                # Non classified photos
                doc['projectcd'] = projectcd
                doc['fototype'] = 'N' 
                doc['soort'] = 'Bestand' 
                doc['bestandsoort'] = const.BESTAND_OVERIGE
                analyseCol.replace_one({"_id": doc['_id']}, doc, upsert=True)

            except Exception as err:
                msg = f"Unknown error while collecting image {doc['fileName']} with message: " + str(err)
                logger.error(msg)    
    
    finally:
        myclient.close()





