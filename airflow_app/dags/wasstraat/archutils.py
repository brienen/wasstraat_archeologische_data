import sys
import re
import unicodedata
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


# ============================================================
# Encoding & tekst-sanitatie functies
# ============================================================

# Mapping van veelvoorkomende Windows-1252 tekens die fout gedecodeerd zijn
# naar hun correcte UTF-8 equivalenten. Dit vangt het geval op waarbij
# Windows-1252 bytes als Latin-1 zijn geinterpreteerd (0x80-0x9F range).
_WIN1252_MOJIBAKE_MAP = {
    '\x80': '\u20AC',  # Euro sign
    '\x85': '\u2026',  # Ellipsis
    '\x91': '\u2018',  # Left single quote
    '\x92': '\u2019',  # Right single quote / apostrophe
    '\x93': '\u201C',  # Left double quote
    '\x94': '\u201D',  # Right double quote
    '\x95': '\u2022',  # Bullet
    '\x96': '\u2013',  # En dash
    '\x97': '\u2014',  # Em dash
    '\x99': '\u2122',  # Trademark
    '\xA0': '\u00A0',  # Non-breaking space
    # C1 control characters die soms als mojibake verschijnen:
    '\xC2\x91': '\u2018',  # UTF-8 interpretatie van Latin-1 0x91
    '\xC2\x92': '\u2019',
    '\xC2\x93': '\u201C',
    '\xC2\x94': '\u201D',
    '\xC2\x96': '\u2013',
    '\xC2\x97': '\u2014',
}

# Unicode replacement character - teken dat encoding-conversie is mislukt
REPLACEMENT_CHAR = '\ufffd'


def sanitize_text(value, field_name=None, doc_id=None):
    """
    Normaliseer tekst: repareer encoding-problemen en verwijder onleesbare tekens.

    In tegenstelling tot de oude .replace('?', '') aanpak:
    - Repareert bekende Windows-1252 mojibake patronen
    - Verwijdert alleen echte control characters, niet leestekens als '?'
    - Logt wanneer er replacement characters gevonden worden
    - Past Unicode NFC-normalisatie toe (samengestelde diakritische tekens)

    Args:
        value: De te sanitizen waarde (wordt naar str geconverteerd)
        field_name: Optioneel veldnaam voor logging
        doc_id: Optioneel document-ID voor logging

    Returns:
        Gesanitizede string
    """
    if value is None:
        return None
    if not isinstance(value, str):
        value = str(value)

    original = value

    # Stap 1: Repareer bekende Windows-1252 mojibake patronen
    for bad_char, good_char in _WIN1252_MOJIBAKE_MAP.items():
        if bad_char in value:
            value = value.replace(bad_char, good_char)

    # Stap 2: Unicode NFC-normalisatie
    # Combineert losse diakritische tekens met hun basisletters (e + ´ -> e)
    value = unicodedata.normalize('NFC', value)

    # Stap 3: Verwijder control characters (C0/C1), behoud newline en tab
    cleaned_chars = []
    for c in value:
        cat = unicodedata.category(c)
        if cat.startswith('C') and c not in '\n\t\r':
            # Dit is een control character - overslaan
            continue
        cleaned_chars.append(c)
    value = ''.join(cleaned_chars)

    # Stap 4: Verwijder Unicode replacement characters (U+FFFD) en log dit
    if REPLACEMENT_CHAR in value:
        count = value.count(REPLACEMENT_CHAR)
        context = f" in veld '{field_name}'" if field_name else ""
        doc_context = f" van document {doc_id}" if doc_id else ""
        logger.warning(
            f"ENCODING: {count} onleesbare teken(s) verwijderd{context}{doc_context}. "
            f"Originele waarde: '{original[:100]}'"
        )
        value = value.replace(REPLACEMENT_CHAR, '')

    return value.strip()


def sanitize_text_field(doc, field_name):
    """
    Sanitize een specifiek tekstveld in een MongoDB document.
    Combineert sanitize_text met de juiste field_name en doc_id voor logging.

    Args:
        doc: MongoDB document (dict)
        field_name: Naam van het veld om te sanitizen
    """
    if field_name in doc and doc[field_name] is not None:
        doc[field_name] = sanitize_text(
            doc[field_name],
            field_name=field_name,
            doc_id=doc.get('_id')
        )


def sanitize_all_string_fields(doc, exclude_fields=None):
    """
    Sanitize alle string-velden in een MongoDB document.
    Slaat het 'brondata'-subdocument en systeem-velden over.

    Args:
        doc: MongoDB document (dict)
        exclude_fields: Set van veldnamen om over te slaan
    """
    if exclude_fields is None:
        exclude_fields = {'_id', 'brondata', 'loadtime', 'mdbfile', 'bron'}

    for key, value in doc.items():
        if key in exclude_fields:
            continue
        if isinstance(value, str):
            doc[key] = sanitize_text(value, field_name=key, doc_id=doc.get('_id'))


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
def convertToBoolDoc(d, attr):
    if attr in d:
        d[attr] = convertToBool(d[attr])

def convertToBool(attr):
    return 1 if str(attr).lower() in ['1', 'true', 'ja', 'j', 'yes', 'y'] else 0

def convertToDateDoc(d, attr, force):
    if attr in d:
        d[attr] = convertToDate(d[attr], force)
        if (d[attr] is pd.NaT): 
            del d[attr] 

def convertToDate(attr, force):
    return pd.to_datetime(attr, dayfirst=True, format='mixed', errors='coerce' if force else 'ignore')




def fixDatering(value):
    import timeperiod2daterange 

    try:
        value = sanitize_text(str(value), field_name='datering')
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
            if "LMEb".lower() in dat.lower():
                datset.add(1200)
                datset.add(1500)
                continue
            if "rt" in dat.lower() or 'romeins' in dat.lower() or dat.lower() == 'r':
                datset.add(-1200)
                datset.add(450)
                continue
            if "XIV C".lower() in dat.lower():
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
       
       
        



