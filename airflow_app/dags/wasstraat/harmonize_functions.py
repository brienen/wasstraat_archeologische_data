
# Import the os module, for the os.walk function
import pymongo
import json
import re
import os
import pandas as pd
import numpy as np

# Import app code
# Absolute imports for Hydrogen (Jupyter Kernel) compatibility
import config
import wasstraat.mongoUtils as mongoUtil

import logging
logger = logging.getLogger("airflow.task")


def callAggregation(collection, pipeline):   
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
                    if matchObj.group(3) is not None: doc['putnr'] = matchObj.group(3)
                    doc['vondstnr'] = matchObj.group(4)
                    if matchObj.group(7) is not None: doc['artefactnr'] = matchObj.group(6)
                    if matchObj.group(7) is not None: doc['fotonr'] = matchObj.group(7)
                    doc['fototype'] = 'H'
                    doc['soort'] = 'Foto' 
                    analyseCol.insert_one(doc)
                    continue

            # Graaffoto's extraheren (Bevatten altijd een _F en beginnen met projectcode)
                matchObj = re.match( r'^([a-zA-Z0-9]+)_F(\d+)(_(\w+))?\.[a-z]{3}$', doc['fileName'], re.M|re.I)
                if matchObj:
                    doc['projectcd'] = matchObj.group(1)       
                    doc['fototype'] = 'F' 
                    doc['fotonr'] = matchObj.group(2)
                    if matchObj.group(4) is not None: doc['fotosubnr'] = matchObj.group(4)
                    doc['soort'] = 'Foto' 
                    analyseCol.insert_one(doc)
                    continue

            # Graaffoto's extraheren (Bevatten altijd een _F en beginnen met projectcode)
                matchObj = re.match( r'^([a-zA-Z0-9]+)_G(\d+)(_(\w+))?\.[a-z]{3}$', doc['fileName'], re.M|re.I)
                if matchObj:
                    doc['projectcd'] = matchObj.group(1)       
                    doc['fototype'] = 'G' 
                    doc['fotonr'] = matchObj.group(2)
                    if matchObj.group(4) is not None: doc['fotosubnr'] = matchObj.group(4)
                    doc['soort'] = 'Foto' 
                    analyseCol.insert_one(doc)
                    continue

                # Non classified photos
                else:
                    doc['fototype'] = 'N' 
                    doc['soort'] = 'Foto' 
                    analyseCol.insert_one(doc)
            except Exception as err:
                msg = "Unknown error while collecting image info with message: " + str(err)
                logger.error(msg)    
    
    finally:
        myclient.close()





