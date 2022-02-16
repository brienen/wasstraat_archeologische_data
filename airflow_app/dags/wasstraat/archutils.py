import json
import pymongo
import json
import re
import pandas as pd
import numpy as np
import roman

import logging
logger = logging.getLogger("airflow.task")

def logError(doc, errtype, msg, severity):
    doc['error'] = {"Error": {  
        "Type": errtype, 
        "Message": msg,
        "Severity": severity,
        "ObjectID": doc['_id']}}
    logger.error(msg)

# Conveniece methods
def convertToInt(d, attr, force):
    if attr in d:
        d[attr] = pd.to_numeric(d[attr], errors='coerce' if force else 'ignore')
        if (d[attr] is np.nan or d[attr] != d[attr]): 
            del d[attr] 
        else:
            if 'numpy.float' in str(type(d[attr])): d[attr] = int(d[attr])
            if 'numpy.int' in str(type(d[attr])): d[attr] = int(d[attr])

# Conveniece methods
def convertToBool(d, attr):
    if attr in d:
        s = str(d[attr]).lower()
        d[attr] = 1 if d[attr] in ['1', 'true', 'ja'] else 0


def convertToDate(d, attr, force):
    if attr in d:
        d[attr] = pd.to_datetime(d[attr], dayfirst=True, cache=True, errors='coerce' if force else 'ignore')
        if (d[attr] is pd.NaT): 
            del d[attr] 
        
def fixDatering(doc):
    doc['datering_origineel'] = doc['datering']
    doc['datering'] = str(doc['datering']).replace(" ", "").replace("?", "")

    # Zo alle tijdseenheden doen volgens http://www.angelfire.com/me/ik/datering.html
    if "LMEb" in str(doc['datering']):
        doc['datering'] = '1250-1500'
    if "RT" in str(doc['datering']):
        doc['datering'] = '-1200-450'

    #Eerst romeins getalnotering omzetten
    matchObj = re.match( r'^([IVXLCMD]+)([a-e])?[-|=]?([IVXLCMD]+)?([a-e])?$', str(doc['datering']), re.M|re.I) 
    if matchObj:
        try:
            doc['datering'] = str(roman.fromRoman(str(matchObj.group(1)))) 
            if matchObj.group(2) is not None: 
                doc['datering'] += str(matchObj.group(2))
            if matchObj.group(3) is not None: 
                doc['datering'] += '-' + str(roman.fromRoman(str(matchObj.group(3))))
            if matchObj.group(4) is not None: 
                doc['datering'] += str(matchObj.group(4))
        except Exception as err:
            msg = "Fout bij omzetten romeinse waarde naar getal: <" + doc['datering'] + "> bij doc met ID: <"+str(doc['_id']) +" met melding: " + str(err)
            logError(doc, "Roman Conversion", msg, 4)

    #Nu eeuwen omzetten
    matchObj = re.match( r'(-?[0-9]{3,4})[-|=]?([0-9]{3,4})?', str(doc['datering']), re.M|re.I)
    if matchObj:
        doc['dateringvanaf'] = matchObj.group(1)
        doc['dateringtot'] = matchObj.group(2)
    else:
        matchObj = re.match( r'^([0-9]{1,2})([a-e])?[-|=]?([0-9]{1,2})?([a-e])?$', str(doc['datering']), re.M|re.I)
        if matchObj:
    #        if Zet in een array [a,b,c,d] doe index * 25 en trek er bij e 100 vanaf     
            doc['dateringvanaf'] = str(matchObj.group(1)) + "00"
            doc['dateringtot'] = str(matchObj.group(3)) + "00"
            doc['datering'] = str(doc['dateringvanaf']) + '-' + str(doc['dateringtot']) 



