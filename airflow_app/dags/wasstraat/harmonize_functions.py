
# Import the os module, for the os.walk function
import pymongo
import json
import re
import os
import pandas as pd
import numpy as np
import wasstraat.harmonizer as harmonizer

# Import app code
# Absolute imports for Hydrogen (Jupyter Kernel) compatibility
import shared.config as config
import shared.const as const
import wasstraat.mongoUtils as mongoUtil

import logging
logger = logging.getLogger("airflow.task")


def fixProjectNames():
    try: 
        logger.info("Calling update statements to fix project codes...")
        myclient = pymongo.MongoClient(str(config.MONGO_URI))
        stagingdb = myclient[str(config.DB_STAGING)]
        stagingcollection = stagingdb[config.COLL_STAGING_OUD]
        plaatjescollection = stagingdb[config.COLL_PLAATJES]
        monstercollection = stagingdb[config.COLL_STAGING_MONSTER]

        stagingcollection.update_many({"mdbfile" : {"$regex" : "DC027_Voorstraat"}}, { "$set": { "project": "DC027" } })
        stagingcollection.update_many({"mdbfile" : {"$regex" : "DC018_Nieuw"}}, { "$set": { "project": "DC018" } })
        stagingcollection.update_many({"mdbfile" : {"$regex" : "DC024_Stadskantoor"}}, { "$set": { "project": "DC024" } })
        stagingcollection.update_many({"mdbfile" : {"$regex" : "DC032_Hoogheem"}}, { "$set": { "project": "DC032" } })
        stagingcollection.update_many({"mdbfile" : {"$regex" : "DC039_Schutter"}}, { "$set": { "project": "DC039" } })

        stagingcollection.update_many({'projectcd': {'$not': {"$type": 2}}}, [{ "$set": { "projectcd": { "$toString": "$projectcd" } } }])
        plaatjescollection.update_many({'projectcd': {'$not': {"$type": 2}}}, [{ "$set": { "projectcd": { "$toString": "$projectcd" } } }])

        monstercollection.update_many({"PROJECT": {"$regex" : "DC 16"}}, { "$set": { "PROJECT": "DC016" } })
        monstercollection.update_many({"PROJECT": {"$regex" : "SCHE"}}, { "$set": { "PROJECT": "DC039" } })
        monstercollection.update_many({"PROJECT": {"$regex" : "PPG"}}, { "$set": { "PROJECT": "DC067" } })
        monstercollection.update_many({"PROJECT": {"$regex" : "BM"}}, { "$set": { "PROJECT": "DC046" } })
        monstercollection.update_many({"PROJECT": {"$regex" : "MB2000"}}, { "$set": { "PROJECT": "MD032" } })


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

        # Fisrt set all projeccd to Unknown
        analyseCol.update_many({'soort': 'Monster'}, { "$set": { "projectcd": None } })

        #Then get all Monsters with an old code
        df_monsters = pd.DataFrame(list(analyseCol.find({'soort': 'Monster', 'brondata.PROJECT': {'$exists': True}}, {'projectcd':0})))        
        
        df_project = pd.DataFrame(list(analyseCol.find({'soort': 'Project'}, {'projectcd':1, 'project': 1, '_id':0})))
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

            try: 
                # Remove double file extensions
                if not os.path.splitext(os.path.splitext(doc['fileName'])[0])[1] == '':
                    doc['fileName'] = os.path.splitext(doc['fileName'])[0]

                # Objectfoto's extraheren (Bevatten altijd een _H en beginnen met projectcode)
                matchObj = re.match( r'^([a-zA-Z0-9]+)(_B?P(\d+))?_H(\d+)(_(\w+))?_(\d+)\.[a-z]{3}$', doc['fileName'], re.M|re.I)
                if matchObj:
                    doc['projectcd'] = matchObj.group(1)
                    if matchObj.group(3) is not None: doc['putnr'] = matchObj.group(3).lstrip("0")
                    doc['vondstnr'] = matchObj.group(4).lstrip("0")
                    if matchObj.group(6) is not None: doc['subnr'] = matchObj.group(6).lstrip("0")
                    if matchObj.group(7) is not None: doc['fotonr'] = matchObj.group(7).lstrip("0")
                    doc['fototype'] = 'H'
                    doc['soort'] = 'Foto' 
                    doc['bestandsoort'] = const.FOTO_OBJECTFOTO

                    strFN = str(doc['fullFileName']).lower()
                    if 'aardewerk' in strFN:
                        doc['artefactsoort'] = const.ARTF_AARDEWERK
                    elif 'bot' in strFN and 'menselijk' in strFN:
                        doc['artefactsoort'] = const.ARTF_MENSELIJK_BOT
                    elif 'bot' in strFN and 'dierlijk' in strFN:
                        doc['artefactsoort'] = const.ARTF_DIELRIJK_BOT
                    elif 'glas' in strFN:
                        doc['artefactsoort'] = const.ARTF_GLAS
                    elif 'leer' in strFN:
                        doc['artefactsoort'] = const.ARTF_LEER
                    elif 'steen' in strFN:
                        doc['artefactsoort'] = const.ARTF_STEEN
                    elif 'kleipijp' in strFN:
                        doc['artefactsoort'] = const.ARTF_KLEIPIJP
                    elif 'hout/':
                        doc['artefactsoort'] = const.ARTF_HOUT
                    elif 'bouwaardewerk' in strFN:
                        doc['artefactsoort'] = const.ARTF_BOUWAARDEWERK
                    elif 'metaal' in strFN:
                        doc['artefactsoort'] = const.ARTF_METAAL
                    elif 'munt' in strFN:
                        doc['artefactsoort'] = const.ARTF_MUNT
                    elif 'schelp' in strFN:
                        doc['artefactsoort'] = const.ARTF_SCHELP
                    elif 'textiel' in strFN:
                        doc['artefactsoort'] = const.ARTF_TEXTIEL

                    analyseCol.replace_one({"_id": doc['_id']}, doc, upsert=True)
                    continue


                # Match Tekeningen
                matchObj = re.match( r'^([a-zA-Z0-9]+)_([ABCDEPT])(\d+).*\.[a-z]{3}$', doc['fileName'], re.M|re.I) 
                if matchObj:
                    doc['projectcd'] = matchObj.group(1)
                    doc['tekeningcd'] = matchObj.group(2) + str(int(matchObj.group(3))).zfill(3)
                    doc['soort'] = 'Tekening' 
                    
                    tektype = matchObj.group(2)
                    doc['fototype'] = tektype
                    if tektype == 'A':
                        doc['bestandsoort'] = const.TEK_BOUWTEKENING
                    elif tektype == 'B':
                        doc['bestandsoort'] = const.TEK_VELDTEKENING
                    elif tektype == 'C':
                        doc['bestandsoort'] = const.TEK_OVERZICHTSTEKENING
                    elif tektype == 'D':
                        doc['bestandsoort'] = const.TEK_OBJECTTEKENING
                    elif tektype == 'E':
                        doc['bestandsoort'] = const.TEK_UITWERKINGSTEKENING
                    elif tektype == 'P':
                        doc['bestandsoort'] = const.TEK_VELDTEKENING_PUBL
                    elif tektype == 'T':
                        doc['bestandsoort'] = const.TEK_OBJECTTEKENING_PUBL
                    else:
                        doc['bestandsoort'] = const.TEK_OVERIGE

                    analyseCol.replace_one({"_id": doc['_id']}, doc, upsert=True)
                    continue

                # Match projectFoto's
                matchObj = re.match( r'^([a-zA-Z0-9]+)_([FG])(\d+).*\.[a-z]{3}$', doc['fileName'], re.M|re.I)
                if matchObj:
                    doc['projectcd'] = matchObj.group(1)       
                    doc['fotonr'] = matchObj.group(3).lstrip("0")
                    doc['soort'] = 'Foto' 
                    
                    fototype = matchObj.group(2)
                    doc['fototype'] = fototype
                    if fototype == 'F':
                        doc['bestandsoort'] = const.FOTO_SFEERFOTO
                    elif fototype == 'G':
                        doc['bestandsoort'] = const.FOTO_OPGRAVINGSFOTO
                    else:
                        doc['bestandsoort'] = const.FOTO_OVERIGE

                    analyseCol.replace_one({"_id": doc['_id']}, doc, upsert=True)
                    continue


            # Rapporten hebben allemaal filenaam die begint met DAR of DAN
                matchObj = re.match( r'^(DAN|DAR)\s*([0-9]{2,3}).*', doc['rapportnr'], re.M|re.I)
                if matchObj:
                    doc['rapportnr'] = matchObj.group(1) + matchObj.group(2)        
                    doc['soort'] = 'Rapport' 
                    doc['fototype'] = 'R' 
                    doc['bestandsoort'] = const.RAPP_ARCHEOLOGISCHE_RAPPORTAGE if 'DAR' in str(doc['rapportnr']) else const.RAPP_ARCHEOLOGISCHE_NOTITIE
                    analyseCol.replace_one({"_id": doc['_id']}, doc, upsert=True)
                    continue
                # Non classified photos
                else:
                    doc['fototype'] = 'N' 
                    doc['soort'] = 'Bestand' 
                    doc['bestandsoort'] = const.BESTAND_OVERIGE
                    analyseCol.replace_one({"_id": doc['_id']}, doc, upsert=True)
            except Exception as err:
                msg = "Unknown error while collecting image info with message: " + str(err)
                logger.error(msg)    
    
    finally:
        myclient.close()





