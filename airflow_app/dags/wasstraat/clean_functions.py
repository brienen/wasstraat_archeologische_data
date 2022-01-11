# Import the os module, for the os.walk function
import pymongo
import json
import re
import pandas as pd
import numpy as np
import roman
from wasstraat.rijksdriehoek import rd_to_wgs
import wasstraat.archutils as ut
import wasstraat.mongoUtils as mongoUtil

 
import logging
logger = logging.getLogger("airflow.task")

# Import app code
# Absolute imports for Hydrogen (Jupyter Kernel) compatibility
import config

def clean():   
    try: 
        myclient = pymongo.MongoClient(str(config.MONGO_URI))
        filesdb = myclient[str(config.DB_FILES)]
        stagingDb = myclient[str(config.DB_STAGING)]
        analyseDb = myclient[str(config.DB_ANALYSE)]
        stagingCol = stagingDb[config.COLL_PLAATJES]
        analyseCol = analyseDb[config.COLL_ANALYSE]

        #loop over all docs in Collection
        #for doc in analyseCol.find({"projectcd": "MD108"}):
        #for doc in analyseCol.find({"datering": {"$exists": True}}):
        for doc in analyseCol.find():
            
            try: 
                # Set all projectcd to capital letters and remove zeros in number
                if 'projectcd' in doc:
                    matchObj = re.match( r'([a-zA-Z]+)-?([0-9]*)', doc['projectcd'], re.M|re.I)
                    if matchObj:
                        deel1 = matchObj.group(1).upper()
                        deel2 = "" if (matchObj.group(2) == '' or matchObj.group(2) is None) else str(pd.to_numeric(matchObj.group(2)))
                        doc['projectcd'] = deel1 + deel2

                #@set projectname 
                if 'projectnaam' in doc:
                    if doc['projectnaam'] == '' and 'toponiem' in doc:
                        doc['projectnaam'] =  doc['toponiem']    
                        doc['projectnaam'] = str(doc['projectnaam']).title()        

                #set dates
                if 'dateringvanaf' not in doc and 'datering' in doc:
                    ut.fixDatering(doc)

                #clean Functie Voorwerp
                if 'functievoorwerp' in doc:
                    doc['functievoorwerp'] =  str(doc['functievoorwerp']).replace('?', '').strip().title()  

                #clean Type Voorwerp
                if 'typevoorwerp' in doc:
                    doc['typevoorwerp'] =  str(doc['typevoorwerp']).replace('?', '').strip().title()  

                ut.convertToInt(doc, 'putnr', False) 
                ut.convertToInt(doc, 'vondstnr', False) 
                ut.convertToInt(doc, 'spoornr', False) 
                ut.convertToInt(doc, 'vlaknr', False) 
                ut.convertToInt(doc, 'artefactnr', False) 
                ut.convertToInt(doc, 'doosnr', True) 
                ut.convertToInt(doc, 'fotonr', False) 
                ut.convertToInt(doc, 'fotosubnr', False) 
                ut.convertToInt(doc, 'volgnr', False) 
                ut.convertToInt(doc, 'lengte', True) 
                ut.convertToInt(doc, 'breedte', True) 
                ut.convertToInt(doc, 'diepte', True) 
                ut.convertToInt(doc, 'jaarvanaf', True) 
                ut.convertToInt(doc, 'jaartot', True) 
                ut.convertToInt(doc, 'jaar', True) 
                ut.convertToInt(doc, 'dateringvanaf', True) 
                ut.convertToInt(doc, 'dateringtot', True) 

                ut.convertToDate(doc, 'datum', True)
                #doc['loadtime'] = pd.to_datetime(doc['loadtime'])

                if 'xcoor_rd' in doc and doc['xcoor_rd'] != '':
                    if doc['xcoor_rd'] == '' or doc['ycoor_rd'] == '':               
                        ut.logError(doc, "Afwijkende locatie", "Locatie van project heeft lege waarde, locatie van "+doc['projectcd']+" wordt genegeerd. ", 2)
                        del doc['xcoor_rd']
                        del doc['ycoor_rd']            
                    elif int(doc['xcoor_rd']) > 100000 or int(doc['xcoor_rd']) < 60000  or int(doc['ycoor_rd']) > 600000 or int(doc['ycoor_rd']) < 300000:               
                        ut.logError(doc, "Afwijkende locatie", "Locatie van project ligt meer dan 150km van Delft, locatie van "+doc['projectcd']+" wordt genegeerd. ", 2)
                        del doc['xcoor_rd']
                        del doc['ycoor_rd']            
                    else:    
                        doc['coor_wgs'] = {'type': "Point", 'coordinates': rd_to_wgs(doc['xcoor_rd'], doc['ycoor_rd'])}
                        doc['latitude'] = doc['coor_wgs']['coordinates'][0]
                        doc['longitude'] = doc['coor_wgs']['coordinates'][1]
                        doc['coor_rd'] = {'type': "Point", 'coordinates': [doc['xcoor_rd'], doc['ycoor_rd']]}

                        #Convert to lat and long values
                        doc['coor_wgs'] = {'type': "Point", 'coordinates': rd_to_wgs(doc['xcoor_rd'], doc['ycoor_rd'])}
                        doc['latitude'] = doc['coor_wgs']['coordinates'][0]
                        doc['longitude'] = doc['coor_wgs']['coordinates'][1]
                        doc['coor_rd'] = {'type': "Point", 'coordinates': [doc['xcoor_rd'], doc['ycoor_rd']]}


            except Exception as err:
                msg = "Onbekende fout bij het cleanen van de attributen van doc met _id:" + str(doc['_id']) + " met melding: " + str(err)
                logger.error(msg)
            finally:
                try:
                    #analyseCol.save(doc) ## ReplaceOne 
                    analyseCol.replace_one({'_id': doc['_id']}, doc)
                except Exception as e:
                    msg = "Onbekende gestapelde fout: kon document niet bewaren van doc met _id:" + str(doc['_id']) + " Met melding: " + str(e)
                    logger.error(msg)
    finally:
        myclient.close()
        

