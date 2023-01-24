# Import the os module, for the os.walk function
from os import urandom
import pymongo
import re
import pandas as pd
import numpy as np
from wasstraat.rijksdriehoek import rd_to_wgs
import wasstraat.archutils as ut
import wasstraat.mongoUtils as mongoUtil

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


def setDateringFields(doc, field):
    datering = ut.fixDatering(doc[field])
    if datering:
        doc[field + '_vanaf'] = datering[0]
        doc[field + '_tot'] = datering[1]
        doc['datering_origineel'] = doc[field]
        doc['datering'] = str(datering)
    return doc


def enhanceAllAttributes():   
    try: 
        myclient = pymongo.MongoClient(str(config.MONGO_URI))
        filesdb = myclient[str(config.DB_FILES)]
        stagingDb = myclient[str(config.DB_STAGING)]
        analyseDb = myclient[str(config.DB_ANALYSE)]
        stagingCol = stagingDb[config.COLL_PLAATJES]
        analyseCol = analyseDb[config.COLL_ANALYSE]

        

        #loop over all docs in Collection
        #for doc in analyseCol.find({"soort": "Monster"}):
        #for doc in analyseCol.find({"datering": {"$exists": True}}):
        for doc in analyseCol.find():
            
            try: 
                # Set all projectcd to capital letters and remove zeros in number
                if 'projectcd' in doc and doc['projectcd']:
                    matchObj = re.match( r'([a-zA-Z]+)-?([0-9]*)', doc['projectcd'], re.M|re.I)
                    if matchObj:
                        deel1 = matchObj.group(1).upper()
                        deel2 = "" if (matchObj.group(2) == '' or matchObj.group(2) is None) else str(pd.to_numeric(matchObj.group(2))).zfill(3)
                        doc['projectcd'] = deel1 + deel2

                #@set projectname 
                if 'projectnaam' in doc:
                    if doc['projectnaam'] == '' and 'toponiem' in doc:
                        doc['projectnaam'] =  doc['toponiem']    
                        doc['projectnaam'] = str(doc['projectnaam']).title()        

                #set dates
                if 'artefactdatering_vanaf' not in doc and 'artefactdatering' in doc:
                    doc = setDateringFields(doc, 'artefactdatering')
                if 'spoordatering' in doc:
                    doc = setDateringFields(doc, 'spoordatering')
                if 'vondstdatering' in doc:
                    doc = setDateringFields(doc, 'vondstdatering')

                #clean Functie Voorwerp
                if 'functievoorwerp' in doc:
                    doc['functievoorwerp'] =  str(doc['functievoorwerp']).replace('?', '').strip().title()  

                #clean Type Voorwerp
                if 'typevoorwerp' in doc:
                    doc['typevoorwerp'] =  str(doc['typevoorwerp']).replace('?', '').strip().title()  

                #clean Type Voorwerp
                if 'tekeningcd' in doc:
                    doc['tekeningcd'] = str(doc['tekeningcd']).replace('?', '').replace('!', '').replace('-', '').strip()
                    matchObj = re.match( r'^([A-Z])([0-9]+)$', doc['tekeningcd'], re.M|re.I)
                    if matchObj:
                        doc['tekeningcd'] = matchObj.group(1) + str(int(matchObj.group(2))).zfill(3)

                #clean Type Voorwerp
                if 'rapportnr' in doc:
                    doc['rapportnr'] = str(doc['rapportnr']).replace(' ', '')
                    if str(doc['rapportnr']).isdigit(): # Some DAR-numbers do not contain DAR in front of code
                        if 'DARnr' in doc['brondata'].keys():
                            doc['rapportnr'] = 'DAR' + doc['rapportnr']
                        elif 'DANnr' in doc['brondata'].keys():
                            doc['rapportnr'] = 'DAN' + doc['rapportnr']
                        else:
                            doc['rapportnr'] = ''


                ut.convertToInt(doc, 'putnr', True) 
                ut.convertToInt(doc, 'vondstnr', True) 
                ut.convertToInt(doc, 'spoornr', True) 
                ut.convertToInt(doc, 'vlaknr', False) 
                ut.convertToInt(doc, 'artefactnr', True) 
                ut.convertToInt(doc, 'subnr', True) 
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
                ut.convertToInt(doc, 'jaar_uitgave', True) 
                ut.convertToInt(doc, 'artefactdatering_vanaf', True) 
                ut.convertToInt(doc, 'artefactdatering_tot', True) 
                ut.convertToInt(doc, 'vondstdatering_vanaf', True) 
                ut.convertToInt(doc, 'vondstdatering_tot', True) 
                ut.convertToInt(doc, 'spoordatering_vanaf', True) 
                ut.convertToInt(doc, 'spoodatering_tot', True) 
                ut.convertToInt(doc, 'aantal', True) 

                ut.convertToBoolDoc(doc, 'exposabel')
                ut.convertToBoolDoc(doc, 'conserveren')
                ut.convertToBoolDoc(doc, 'restauratie')
                ut.convertToBoolDoc(doc, 'weggegooid')
                ut.convertToBoolDoc(doc, 'uitgeleend')
                ut.convertToBoolDoc(doc, 'definitief')
                ut.convertToBoolDoc(doc, 'rob')
                ut.convertToBoolDoc(doc, 'kb')
                ut.convertToBoolDoc(doc, 'archief')
                

                ut.convertToDateDoc(doc, 'datum', True)
                #doc['loadtime'] = pd.to_datetime(doc['loadtime'])

                if 'xcoor_rd' in doc and doc['xcoor_rd'] != '':
                    if doc['xcoor_rd'] == '' or doc['ycoor_rd'] == '':               
                        ut.logError(doc, "Afwijkende locatie", "Locatie van project heeft lege waarde, locatie van "+doc['projectcd']+" wordt genegeerd. ", 2)
                        del doc['xcoor_rd']
                        del doc['ycoor_rd']            
                    #elif int(doc['xcoor_rd']) > 100000 or int(doc['xcoor_rd']) < 60000  or int(doc['ycoor_rd']) > 600000 or int(doc['ycoor_rd']) < 300000:               
                    #    ut.logError(doc, "Afwijkende locatie", "Locatie van project ligt meer dan 150km van Delft, locatie van "+doc['projectcd']+" wordt genegeerd. ", 2)
                    #    del doc['xcoor_rd']
                    #    del doc['ycoor_rd']            
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
                    raise Exception(msg) from e

    finally:
        myclient.close()
        

def extractImagedataFromFileNames():
    try:        
        col = getAnalyseCollection()
        dirs = pd.DataFrame(list(col.find({'soort': 'Foto'}, projection={'directory':1}))).dropna()['directory'].unique()
        projs = pd.DataFrame(list(col.find({'soort': 'Project'}, projection={'projectcd':1}))).dropna()['projectcd'].unique()

        # Build dict with dirs as entry to projectcd, materiaal and fototype
        file_dict = {}
        for dr in dirs:    
            dr_dict = {}
            for proj in projs:
                if proj in re.split('/| ', dr):
                    dr_dict.update({'projectcd': proj})
            
            if 'objectfoto' in dr.lower() or 'h object' in dr.lower():
                dr_dict.update({'fotosoort': const.OBJECTFOTO})
                dr_dict.update({'materiaal': dr.split('/')[-1]})
            elif 'opgravingsfoto' in dr.lower():
                dr_dict.update({'fotosoort': const.OPGRAVINGSFOTO})
            elif 'velddocument' in dr.lower():
                dr_dict.update({'fotosoort': const.VELDDOCUMENT})
            else:
                dr_dict.update({'fotosoort': const.OVERIGE_AFBEELDING})

            file_dict.update({dr: dr_dict})
          
        # Set missing values in foto's       
        lst_foto = list(col.find({'soort': 'Foto'}))            
        for foto in lst_foto:
            try:
                if not foto.get('projectcd'):
                    foto['projectcd'] = file_dict.get(foto.get('directory')).get('projectcd')
                if not foto.get('fototype'):
                    foto['fototype'] = file_dict.get(foto.get('directory')).get('fototype')

                foto['materiaal'] = file_dict.get(foto.get('directory')).get('materiaal')  
                foto['fotosoort'] = file_dict.get(foto.get('directory')).get('fotosoort')                
                col.replace_one({'_id': foto['_id']}, foto)

            except Exception as exp2:
                filename = foto['fileName']
                logger.error(f'Error while setting missing values in foto {filename} with message: {str(exp2)} ')
    except Exception as exp1:
        msg = f'Severe error while while setting missing values on fotos: {str(exp1)} '
        logger.error(msg)
        raise Exception(msg) from exp1