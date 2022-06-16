import sys
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




def fixDatering(value):
    import timeperiod2daterange 

    try:     
        value = str(value).replace("?", "")
        value = value.replace('-', ',').replace("/", ",").replace("+", ",").replace("=", ",").replace(",,", ",-").replace(")", "").replace("(", "")
        if value[0] == ',':
            value = value.replace(',', '-', 1)
        if value[-1] == ',':
            value = value[:-1]

        eersteDate = None
        datset = set()
        datlist = value.split(",")
        for dat in datlist:
            dat = str(dat)
            if "LMEb" in dat:
                datset.add(1200)
                datset.add(1500)
                continue
            if "RT" in dat or 'romeins' in dat:
                datset.add(-1200)
                datset.add(450)
                continue
            if "XIV C" in dat:
                datset.add(1450)
                datset.add(1475)
                continue
                

            matchObj = re.match( r'([0-9]{3,4})', dat.replace(" ", ""), re.M)
            if matchObj:
                datset.add(int(matchObj.group(1)))
                eersteDate = int(matchObj.group(1)) if not eersteDate else eersteDate
                continue
            else:
                matchObj = re.match( r'^([0-9]{1,2})([a-d]+)$', dat.replace(" ", ""), re.M|re.I)
                if matchObj:
                    intdate = int(matchObj.group(1)) * 100
                    eersteDate = intdate if not eersteDate else eersteDate
                    if matchObj.group(2) is not None: 
                        kwart = str(matchObj.group(2))
                        kwart_int_first = ord(kwart.lower()[0]) - 96
                        kwart_int_last = ord(kwart.lower()[-1]) - 96
                        datset.add(intdate + 25*(kwart_int_first-1))
                        datset.add(intdate + 25*kwart_int_last)
                        continue
                    else:
                        datset.add(intdate)
                        continue


            matchObj = re.match( r'^([IVXLCMD]+)([a-dA-D]+)?$', dat.replace(" ", ""), re.M) 
            if matchObj:
                try:
                    romandate = int(roman.fromRoman(str(matchObj.group(1)))) * 100
                    eersteDate = romandate if not eersteDate else eersteDate
                    if matchObj.group(2) is not None: 
                        kwart = str(matchObj.group(2))
                        kwart_int_first = ord(kwart.lower()[0]) - 96
                        kwart_int_last = ord(kwart.lower()[-1]) - 96
                        datset.add(romandate + 25*(kwart_int_first-1))
                        datset.add(romandate + 25*kwart_int_last)
                        continue
                    else:
                        datset.add(romandate)
                        continue

                except Exception as err:
                    msg = "Fout bij omzetten romeinse waarde naar getal: <" + value + ">"  +" met melding: " + str(err)
                    logger.warning(msg)

            matchObj = re.match( r'^([a-dA-D])?$', dat.replace(" ", ""), re.M) 
            if matchObj and eersteDate:
                try:
                        kwart = str(matchObj.group(1))
                        kwart_int_first = ord(kwart.lower()[0]) - 96
                        kwart_int_last = ord(kwart.lower()[-1]) - 96
                        datset.add(eersteDate + 25*(kwart_int_first-1))
                        datset.add(eersteDate + 25*kwart_int_last)
                        continue

                except Exception as err:
                    msg = "Fout bij omzetten kwarten (abcd) naar getal: <" + value + ">"  +" met melding: " + str(err)
                    logger.warning(msg)

            # If all fails try PHD-date fixer
            phdfix = timeperiod2daterange.detection2daterange(dat)
            if phdfix:
                datset.add(phdfix[0] if phdfix[0] < -25 or phdfix[0] > 25 else phdfix[0] * 100)
                datset.add(phdfix[1] if phdfix[1] < -25 or phdfix[1] > 25 else phdfix[1] * 100)

                
    except Exception as err:
        msg = "Fout bij omzetten van datering naar tijdreeks: <" + value + ">"  +" met melding: " + str(err)
        logger.warning(msg)
        return None
   
    return (min(datset), max(datset)) if len(datset) > 0 else None
       
       
        



