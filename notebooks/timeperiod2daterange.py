"""

Converts a string containing one or more Dutch time period(s) to a list containing the start year and end year for that expression

Usage (direct):
    ./timeperiod2daterange.py

Usage (import into another script)
    import sys
    sys.path.insert(1, 'timeperiod-to-daterange/') # path to folder
    import timeperiod2daterange
    timeperiod2daterange.detection2daterange('1200 n. Chr') # output: [1200, 1200]

Author:
    Alex Brandsen
    
"""



# LOAD LIBRARIES ---------------------------------------------------

import traceback
import csv
import re
import datetime
from nltk.util import ngrams
import editdistance



# OPTIONS ---------------------------------------------------

# set debug, if 1, print verbose info
debug = 0

# set location of ontology (csv format)
ontologyLocation = 'ontologies/periodo_extended.csv'

# set current year
now = datetime.datetime.now()
currentYear = now.year




# SET REGEX / CONVERSION DICTS / OPTION LISTS ---------------------------------------------------

has_numeric_ordinal_strict = re.compile('[0-9]+(ste|de|e)')
has_numeric_ordinal = re.compile('[0-9]+(ste|de|e)*')

ordinal_to_cardinal = {
    'eerste':1,
    'tweede':2,
    'derde':3,
    'vierde':4,
    'vijfde':5,
    'zesde':6,
    'zevende':7,
    'achtste':8,
    'negende':9,
    'tiende':10,
    'elfde':11,
    'twaalfde':12,
    'dertiende':13,
    'veertiende':14,
    'vijftiende':15,
    'zestiende':16,
    'zeventiende':17,
    'achtiende':18,
    'negentiende':19,
    'twintigste':20,
    'vorige': 20 # I know, this isn't really an ordinal... but easier than adding yet another if statement
}

has_digits = re.compile('\d')
extract_year_from_date = re.compile('\d{1,2}[/.-]\d{1,2}[/.-](\d{2,4})')

datePattern = r"([0-9.,]+)[ ]*(�|\+/-|\+-|14C BP|yr BP|14 C-jaar|14C-jaar|14C jaar|\+|\^)"
errormarginPattern = r"([0-9.,]+)[ ]*(14C jaren|14C-jaar|14C jaar)*[ ]*(yr )*BP"

words_to_remove = ['tussen ','vanaf ','na ', 'circa ', 'ongeveer ', 'van het ',' ? ']

negativeTimeWords = ['v. chr', 'voor chr',' bc','v.chr.','v. chr.','voor christus','v chr']
positiveTimewords = ['n. chr', 'na chr', ' ad ','n.chr.','n. chr.','na christus','n chr']

extract_digits = re.compile('([0-9.,]+)')

comboWords = [
    ' en/of ',
    ' en / of ', 
    ' of in de ',
    ' of ',
    ' t/m ',
    ' t / m ',
    ' tot en met ',
    ' tot in de ',
    ' tot op ',
    ' tot ',
    ' en ',
    ' naar het ', 
    ' / ',
    ' - ',
    ' -',
    '- ',
    ' � ', #middle-length en dash
    '� ',
    ' �',
    ' � ', #emdash
    ' �',
    '� ',
]
comboRegexpString = '|'.join(comboWords)



# DEFINE FUNCTIONS ---------------------------------------------------

# turns ontology csv file into dict {'period name':[startdate,enddate],...}
def ontology2dict(location):
    output = {}
    with open(location, encoding="utf-8") as csv_file:
        csv_reader = csv.reader(csv_file, delimiter=',')
        next(csv_reader, None)  # skip the headers
        for row in csv_reader:
            output[row[1].lower()] = [int(row[2]),int(row[3])]
            output[row[1].lower().replace(' ','')] = [int(row[2]),int(row[3])] # add version without spaces, to counteract ocr errors
            for i in range(4,17):
                if row[i]:
                    output[row[i].lower()] = [int(row[2]),int(row[3])]
                    output[row[i].lower().replace(' ','')] = [int(row[2]),int(row[3])] # add version without spaces, to counteract ocr errors
        return output

# get ontology
ontology = ontology2dict(ontologyLocation)

# checks if string is a defined time period, or very similar to one, returns [startdate,enddate] or False if no match     
def check_ontology(string, do_ngrams = True):
    
    # clean string
    string = string.lower() # lowercase to match with ontology
    string = string.replace(' de ',' ').replace('het ',' ') # remove stopwords
    if string[:3] == 'de ': # remove 'de ' at beginning of string
        string = string[2:]
    string = string.strip() # strip witespace on either side of string
    
    if debug:
        print('String is: '+string)

    if string in ontology:
        return ontology[string]
    
    # take off last char to sort 's' and 'e' (prehistorische, middeleeuws)
    elif string[:-1] in ontology: 
        return ontology[string[:-1]]
    
    # take off ' periode' (jonge dryas periode)
    elif string.replace(' periode','') in ontology: 
        return ontology[string.replace(' periode','')]
    
    # remove ' periode' and sort 's' and 'e' (middeleeuwse periode)
    elif string[:-1].replace(' periode','') in ontology: 
        return ontology[string[:-1].replace(' periode','')]
    
    # remove dashes and strip whitespace (- middeleeuwen)
    elif string.replace('-','').strip() in ontology: 
        return ontology[string.replace('-','').strip()]
    
    # replace dash with space (midden-romeinse tijd -> midden romeinse tijd)
    elif string.replace('-',' ') in ontology: 
        return ontology[string.replace('-',' ')]
    
    # remove dash  (swifterband-cultuur -> swifterbantcultuur)
    elif string.replace('-','') in ontology: 
        return ontology[string.replace('-','')]
    
    # remove brackets, dashes, and resulting extra whitespace  ((sub-)recent)
    elif string.replace('(','').replace(')','').replace('-','').replace('  ',' ').strip() in ontology: 
        return ontology[string.replace('(','').replace(')','').replace('-','').replace('  ',' ').strip()]
    
    # remove brackets, dashes, resulting extra whitespace and last 'e'  ((pre-)historische)
    elif string[:-1].replace('(','').replace(')','').replace('-','').replace('  ',' ').strip() in ontology: 
        return ontology[string[:-1].replace('(','').replace(')','').replace('-','').replace('  ',' ').strip()]
    
    # late / laat (laat pleniglaciaal)
    elif string.replace('late ','').replace('laat ','').replace('laat-','') in ontology: 
        dates = ontology[string.replace('late ','').replace('laat ','').replace('laat-','')]
        return [round(dates[0]+dates[1]-dates[0]/2),dates[1]]
    
    # late / laat and sort 's' and 'e' (laat-romeinse)
    elif string[:-1].replace('late ','').replace('laat ','').replace('laat-','') in ontology: 
        dates = ontology[string[:-1].replace('late ','').replace('laat ','').replace('laat-','')]
        return [round(dates[0]+dates[1]-dates[0]/2),dates[1]]
    
    # vroege / vroeg 
    elif string.replace('vroege ','').replace('vroeg ','').replace('vroeg-','') in ontology: 
        dates = ontology[string.replace('vroege ','').replace('vroeg ','').replace('vroeg-','')]
        return [dates[0],round(dates[0]+dates[1]-dates[0]/2)]
    
    # vroege / vroeg and sort 's' and 'e' (vroeg-romeinse)
    elif string[:-1].replace('vroege ','').replace('vroeg ','').replace('vroeg-','') in ontology: 
        dates = ontology[string[:-1].replace('vroege ','').replace('vroeg ','').replace('vroeg-','')]
        return [dates[0],round(dates[0]+dates[1]-dates[0]/2)]
    
    # eerste helft
    elif string.replace('eerste helft ','').replace('1e helft ','').replace('de ','').replace('het ','').replace('van ','') in ontology: 
        dates = ontology[string.replace('eerste helft ','').replace('1e helft ','').replace('de ','').replace('het ','').replace('van ','')]
        return [dates[0],round(dates[0]+dates[1]-dates[0]/2)]
    
    # laatste helft
    elif string.replace('laatste helft ','').replace('de ','').replace('het ','').replace('van ','') in ontology: 
        dates = ontology[string.replace('laatste helft ','').replace('de ','').replace('het ','').replace('van ','')]
        return [round(dates[0]+dates[1]-dates[0]/2),dates[1]]
    
    # tweede helft
    elif string.replace('tweede helft ','').replace('de ','').replace('het ','').replace('van ','') in ontology: 
        dates = ontology[string.replace('tweede helft ','').replace('de ','').replace('het ','').replace('van ','')]
        return [round(dates[0]+dates[1]-dates[0]/2),dates[1]]
    
    # eerste kwart
    elif string.replace('eerste kwart ','').replace('1e kwart ','').replace('de ','').replace('het ','').replace('van ','') in ontology: 
        dates = ontology[string.replace('eerste kwart ','').replace('1e kwart ','').replace('de ','').replace('het ','').replace('van ','')]
        return [dates[0],round(dates[0]+dates[1]-dates[0]*0.25)]
    
    # laatste kwart
    elif string.replace('laatste kwart ','').replace('de ','').replace('het ','').replace('van ','') in ontology: 
        dates = ontology[string.replace('laatste kwart ','').replace('de ','').replace('het ','').replace('van ','')]
        return [round(dates[0]+dates[1]-dates[0]*0.75),dates[1]]
    
    # try splitting in 2 on dash, and do each one seperately (bronstijd-ijzertijd)
    elif '-' in string:
        strings = string.split('-')
        startdate = check_ontology(strings[0])
        if startdate:
            startdate = startdate[0]
        enddate = check_ontology(strings[1])
        if enddate:
            enddate = enddate[1]
        if startdate and enddate:
            return [startdate,enddate]

    
    # still nothing, try n-grams. max length of entry in ontology is 3, so do 1-, 2- and 3-grams
    if (' ' in string or '-' in string) and do_ngrams == True:
    
        if debug:
            print('doing ngrams')
            
        tokens = [token for token in re.split(" |-|–",string) if token != ""]
        
        if debug:
            print(tokens)
            
        max_n = min(4,len(tokens))
        for i in range(max_n,1,-1): # reverse order so we do 3 -> 2 -> 1 grams
            token_ngrams = ngrams(tokens, i)
            for token_ngram in token_ngrams:
                token_ngram_temp = ' '.join(token_ngram)
                # recursively call this function, but with do_ngrams = False, so we don't go into infinite loop
                dates = check_ontology(token_ngram_temp,False)   
                if dates:
                    return dates
            
    
    # last resort, check if any time periods occur in the timeperiod string (Bronstijdonderzoek) and do edit distance
    for ontPeriod, daterange in ontology.items():
        #print(ontPeriod+' '+string)
        if len(ontPeriod) > 4: # this is to leave out ABR codes such as 'NT' which will occur in a lot of words
            if ontPeriod in string:
                return daterange

            # also calculate edit distance between each ngram and the ontology entry, if low, return the daterange (middeleewen)
            elif 'token_ngrams' in locals():
                for token_ngram in token_ngrams:
                    token_ngram_temp = ' '.join(token_ngram)
                    if editdistance.eval(token_ngram_temp, ontPeriod) < 3:
                        return daterange
            # or if no ngrams, do edit distance for whole string
            else:
                if editdistance.eval(string, ontPeriod) < 3:
                    return daterange
    
    # can't find any match :( return False
    return False
    
 
def parse_century(timeperiod):
    
    cardinal = False
    
    # clean split digits (1 0e eeuw, 1 1 e-eeuwse)
    timeperiod = re.sub(r'(\d)\s+(\d)\s+(e)*', r'\1\2\3', timeperiod)
    
    tokens = re.split(' |-|�|�', timeperiod)
    
    # number cardinal (1e eeuw, 4e millenium)
    if has_numeric_ordinal.search(timeperiod):
        for token in tokens:
            tokenMinusEnding = token.replace('ste','').replace('de','').replace('e','')
            if tokenMinusEnding.isdigit():
                cardinal = int(tokenMinusEnding)
                break
        
        # nothing found, remove numbers and rerun this function, so it'll try the written out cardinal section below
        if not cardinal:
            stringWithoutNumbers = ''.join(i for i in timeperiod if not i.isdigit())
            return parse_century(stringWithoutNumbers)
    

    # written out cardinal (eerste eeuw, vierde millenium)
    else:
    
        if debug:
            print('written out cardinal')
            
        for token in tokens:
            if token in ordinal_to_cardinal:
                cardinal = ordinal_to_cardinal[token]
                break
    
    if cardinal:
    
        if debug:
            print(cardinal)
            
        # check century (eeuw) or millenium. 2e eeuw = [100,199]. 2e eeuw v. chr = [-199,-100]
        if 'millennium' in timeperiod or 'millenium' in timeperiod:
            startdate = (cardinal * 1000) - 1000
            enddate = (cardinal * 1000) - 1
        else:
            # assume century if we don't know for sure
            startdate = (cardinal * 100) - 100
            enddate = (cardinal * 100) - 1


        # check quantifiers (eerste helft, midden van, laatste kwart)
        if 'eerste helft ' in timeperiod or '1e helft ' in timeperiod: 
            enddate = enddate-50

        elif 'laatste helft ' in timeperiod or 'tweede helft ' in timeperiod or '2e helft ' in timeperiod: 
            startdate = startdate+50

        elif 'eerste kwart ' in timeperiod or '1e kwart ' in timeperiod or '1ste kwart ' in timeperiod or 'begin van ' in timeperiod  or 'begin ' in timeperiod or 'vroege ' in timeperiod: 
            enddate = enddate-75

        elif 'tweede kwart ' in timeperiod or '2e kwart ' in timeperiod: 
            startdate = startdate+25
            enddate = enddate-50

        elif 'derde kwart ' in timeperiod or '3e kwart ' in timeperiod: 
            startdate = startdate+50
            enddate = enddate-25

        elif 'laatste kwart ' in timeperiod or 'einde van ' in timeperiod or 'eind ' in timeperiod or 'late ' in timeperiod: 
            startdate = startdate+75

        elif 'midden van ' in timeperiod: # 2e eeuw = 100 - 200
            startdate=startdate+25
            enddate=enddate-25


        # if BC, make dates negative and swap start and end date
        if any(negativeTimeWord in timeperiod.lower() for negativeTimeWord in negativeTimeWords): 
            temp = startdate
            startdate = enddate * -1
            enddate = temp * -1
        
        if debug:
            print([startdate,enddate])
            
        return [startdate,enddate]
    
    else:
        return False
        

# takes 1 timeperiod as string, returns [startdate,enddate], used in timeperiod2daterange below
def timeperiod2daterange(timeperiod, timeType = 'AD'):
    daterange = False
    
    # clean string
    timeperiod = timeperiod.lower()
    for word in words_to_remove:
        timeperiod = timeperiod.replace(word,'')
        
    if debug:
        print(timeperiod)
      
    # century/millenium (eerste eeuw v. Chr., 4e eeuw na christus)laat - 1 1 e-eeuwse
    if '-eeuw' in timeperiod or ' eeuw' in timeperiod or ' millennium' in timeperiod or ' millenium' in timeperiod or has_numeric_ordinal_strict.search(timeperiod):
    
        if debug:
            print('eeuw/millenium parse')
            
        daterange = parse_century(timeperiod)
        
    # number in string
    elif has_digits.search(timeperiod):
    
        if debug:
            print('digit in string')
            
        year = extract_year_from_date.search(timeperiod)
        
        # digits only (1990, 400)
        if timeperiod.isdigit():
            daterange = [int(timeperiod),int(timeperiod)]
        
        # 18-03-2005 or 18/03/1980
        elif year:
        
            if debug:
                print('full date')
                
            year = year.group(1)
            
            if debug:
                print(year)
                
            if len(year) == 2: # shortened version of year (18-3-99)
                if int(year) > 25: # then assume 20st century
                    year = int('19'+year)
                else: # assume 21st century
                    year = int('20'+year)
            else:
                year = int(year)
            daterange = [year,year]
            
            if debug:
                print(daterange)
            
        # digits with spaces (1 900)
        elif timeperiod.replace(' ','').isdigit():
            daterange = [int(timeperiod.replace(' ','')),int(timeperiod.replace(' ',''))]
            
        # digits with dashes around them (-1800)
        elif timeperiod.replace('-','').strip().isdigit():
            daterange = [int(timeperiod.replace('-','').strip()),int(timeperiod.replace('-','').strip())] 
            
        # digits with just the 'v' from 'v.chr.'
        elif timeperiod.replace(' v','').replace('.','').strip().isdigit():
            daterange = [int(timeperiod.replace(' v','').replace('.','').strip()),int(timeperiod.replace(' v','').replace('.','').strip())] 
            
        # digits with just the 'n' from 'n.chr.'
        elif timeperiod.replace(' n','').replace('.','').strip().isdigit():
            daterange = [int(timeperiod.replace(' n','').replace('.','').strip()),int(timeperiod.replace(' n','').replace('.','').strip())] 
            
             
        # digits with brackets "350 (?)"
        elif timeperiod.replace('(','').replace(')','').strip().isdigit():
            if debug:
                print('brackets')
            daterange = [int(timeperiod.replace('(','').replace(')','').strip()),int(timeperiod.replace('(','').replace(')','').strip())]        
            
        # year + BC/AD (300 v. chr.)
        elif 'chr' in timeperiod or ' bc' in timeperiod:
            result = int(extract_digits.search(timeperiod).group(0).replace('.','').replace(',',''))
            daterange = [result,result]
            if debug:
                print(daterange)
        
        # 1 miljoen jaar geleden
        elif 'jaar geleden' in timeperiod:
            if debug:
                print('jaar geleden')
            years = timeperiod.replace('jaar geleden','').replace('.','').replace(',','').strip()
            if years.isdigit():
                years = int(years)
            elif 'miljoen' in years:
                years = extractDigits(years) * 1000000
            elif 'duizend' in years:
                years = extractDigits(years) * 1000
            elif 'honderd' in years:
                years = extractDigits(years) * 100
            elif years.replace(' ','').isdigit():
                years = extractDigits(years.replace(' ',''))
            else:
                years = extractDigits(years)
            
            if debug:
                print(years)
            if years:
                daterange = [years,years] 
                
         
        # +/- bp carbon dates ( 1300 +/- 30 BP) 45 1 0 � 60
        elif '+/-' in timeperiod or '+ / -' in timeperiod or '�' in timeperiod or '+-' in timeperiod:
            if debug:
                print('c14')
            
            # clean: remove spaces between digits (45 1 0 � 60)
            timeperiod = re.sub(r'(\d)\s(?=\d)', r'\1', timeperiod) # thanks to Martin Kroon for ?= (look forward)
            
            # get year
            date = re.search(datePattern,timeperiod)
            if not date and not '�' in timeperiod:
                date = re.search('([0-9.,]+)[ ]*BP',timeperiod)
            if not date:
                date = False
            else:
                try:
                    date = int(date.group(1))
                except:
                    # it's a kya instead of years BP
                    if ',' in date.group(1) or '.' in date.group(1):
                        date = int(float(date.group(1).replace(',','.')) * 1000)
                    else:
                        date = False
                        
            
            # get error margin 
            if not '�' in timeperiod and not '+/-' in timeperiod and not '+-' in timeperiod:
                errormargin = False
            else:          
                errormargin = re.search(errormarginPattern,timeperiod)
                if not errormargin:
                    errormargin = re.search('([0-9.,]+)[ ]*(14C yr)',timeperiod)
                if not errormargin:
                    errormargin = re.search('(?:�|\+/-)[ ]*([0-9.,]+)',timeperiod)
                if not errormargin:
                    errormargin = False
                else:
                    try:
                        errormargin = int(errormargin.group(1))
                    except:
                        # it's a kya instead of years BP
                        if ',' in errormargin.group(1) or '.' in errormargin.group(1):
                            errormargin = int(float(errormargin.group(1).replace(',','.')) * 1000)
                        else:
                            errormargin = False
                    
                    
            if date:
                if errormargin:
                    startdate = date+round(errormargin)
                    enddate = date-round(errormargin)
                    daterange = [startdate,enddate]
                else:
                    daterange = [date,date]
            
            if debug:
                print(daterange)
                print(errormargin)
                           
        # decades (jaren 1940 / jaren ’70)
        elif 'jaren ' in timeperiod:
            year = extractDigits(timeperiod)
            if year < 100: # jaren ’70
                if year > 10: # then assume 20st century
                    year += 1900
                else: # assume 21st century
                    year += 2000
            else: # jaren 1940
                year = int(year)
            daterange = [year,year+9]
            
        # shortened year (2003 / ’04)
        elif "'" in timeperiod or "’" in timeperiod:
            timeperiod = timeperiod.replace("'","").replace("’","").strip()
            if len(timeperiod) == 2:
                if int(timeperiod) > 25: # then assume 20st century
                    year = int('19'+timeperiod)
                else: # assume 21st century
                    year = int('20'+timeperiod)
                daterange = [year,year]  
                  
        # afgelopen 130 jaar
        elif 'afgelopen' in timeperiod and 'jaar' in timeperiod:
            years = extractDigits(timeperiod)
            daterange = [2000-years,2000]
           
        # no idea, just extract digits and hope it's a year
        else:
            result = extractDigits(timeperiod)
            daterange = [result,result]
        
    # no digits, check with time period list
    else:
        if debug:
            print('check ontology')
        daterange = check_ontology(timeperiod)
        return daterange # return this here, so we don't do bc/bp correction below, which is only for numerics
    
    # found a daterange,  check timetype and adjust if needed
    if debug:
        print(timeType)
    if not timeType: # if we didn't get a timetype, check it here
        timeType = checkTimeType(timeperiod)
    if(daterange):
        if timeType == 'BC':
            daterange[0] = daterange[0] * -1
            daterange[1] = daterange[1] * -1
        elif timeType == 'BP': 
            daterange[0] = (1950 - daterange[0]) 
            daterange[1] = (1950 - daterange[1]) 
            #print(daterange)
        elif timeType == 'YA': 
            daterange[0] = (2000 - daterange[0]) # doing [year of publication] - daterange would be even better, but this is close enough
            daterange[1] = (2000 - daterange[1]) 
            #print(daterange)
        return daterange
    
    else:
        return False


# takes timeperiod string, checks if AD, BC or BP
def checkTimeType(timeperiod):
    timeperiod = timeperiod.lower()
    if any(negativeTimeWord in timeperiod for negativeTimeWord in negativeTimeWords):
        timeType = 'BC'
    elif ' bp' in timeperiod  or '+/-' in timeperiod or '+ / -' in timeperiod or '�' in timeperiod or '+-' in timeperiod:
        timeType = 'BP'
    elif 'jaar geleden' in timeperiod:
        timeType = 'YA' # Years Ago
    else:
        timeType = 'AD'
    return timeType


# takes string, returns only digits in string
def extractDigits(string):
    digits = string.replace(' ','').replace(',','').replace('.','') # take out spaces, dots and comma's to handle e.g. "10. 000"
    digits = int(extract_digits.search(digits).group(0))
    return digits


# takes 1 detected timeperiod, detects if 1 or 2 mentions, returns [startdate,enddate]
def detection2daterange(timeperiod):
    try:
        # multiple dates in 1 string
        if any(comboWord in timeperiod for comboWord in comboWords):
            
            if debug:
                print('multiple dates')
            multiDates = True
            
            # split into separate timeperiods
            timeperiods = re.split(comboRegexpString, timeperiod)
            
            # check if timeperiod is negative (BC), positive (AD), or before present (BP)
            timeType = checkTimeType(timeperiods[1])
            
            # get startdate from first mention
            startdate = timeperiod2daterange(timeperiods[0],timeType)
            if startdate:
                startrange = startdate
                startdate = startrange[0]
            elif len(re.split(' |-|�|�', timeperiods[1])) > 1: # 'vroege of midden ijzertijd' -> add last token of second mention to first mention, try again
                startdate = timeperiod2daterange(timeperiods[0]+' '+re.split(' |-|�|�', timeperiods[1]).pop(),timeType)
                if startdate:
                    startrange = startdate
                    startdate = startrange[0]
             
            # get enddate from last mention
            enddate = timeperiod2daterange(timeperiods[1],timeType)
            if enddate:
                endrange = enddate
                
                enddate = endrange[1]
                
            # nothing found, give whole string to function and hope for the best..
            if type(startdate) != int and type(enddate) != int: 
                daterange = timeperiod2daterange(timeperiod)
                if daterange:
                    startdate = daterange[0]
                    enddate = daterange[1]
                else:
                    startdate = False
                    enddate = False
            
        # single date in string    
        else:
            if debug:
                print('single date')
            multiDates = False
            timeType = checkTimeType(timeperiod)
            daterange = timeperiod2daterange(timeperiod,timeType)
            if daterange:
                startdate = daterange[0]
                enddate = daterange[1]
            else:
                startdate = False
                enddate = False
        
        # dates found!
        if type(startdate) == int and type(enddate) == int: # 'if startdate' doesn't work if startdate == 0
            return postCorrectDates(startdate,enddate,multiDates)
        
        # only found date in first part of mention, just return that daterange
        elif type(startdate) == int:
            return postCorrectDates(startrange[0],startrange[1],multiDates)
        
        # only found date in second part of mention, just return that daterange
        elif type(enddate) == int:
            return postCorrectDates(endrange[0],endrange[1],multiDates)
        
        # not able to calculate date range, return false
        else:
            return False
            
    # error in script somewhere, print it and return false        
    except Exception as e: 
        print('timeperiod string: '+timeperiod)
        print('timeperiod error: ')
        print(e)
        traceback.print_exc()
        
        return False
        
    
# checks startdate/enddate for inconsistencies, fixes AD/BP and stardate > enddate
def postCorrectDates(startdate,enddate,multiDates = False):
    
    # check if dates are in the future, if so, inverse them so they're BC (could also be BP, but BC is best guess) 
    # TODO?: if > 10k, BP
    if startdate > currentYear:
        if debug:
            print('reverse date')
        startdate = startdate * -1
    if enddate > currentYear and enddate != 2099: # 2099 is 21st century
        if debug:
            print('reverse date')
        enddate = enddate * -1

    # Check if startdate < enddate (something went wrong, enddate is before startdate)
    if enddate < startdate:
        # enddate is BC, startdate AD, and reversed startdate is before enddate, so assume startdate is also BC
        if enddate < 0 and startdate > 0 and startdate * -1 < enddate:
            startdate = startdate * -1
        # small difference and multidate, so probably a BC date that doesn't include 'bc' or 'v. chr'
        elif multiDates and startdate - enddate < 400: 
            startdate = startdate * -1
            enddate = enddate * -1
        # not sure what happened, let's just use the startdate
        else:
            enddate = startdate
    
    return [startdate,enddate]



# -----------------------------------------------------------------

# EXAMPLES: take named entity detection (can contain multiple time periods, e.g. "Middeleeuwen tot Moderne Tijd"), return daterange

#detection2daterange('1200 n. Chr') 
    # output: [1200, 1200]

#detection2daterange('Middeleeuwen tot Moderne Tijd') 
    # output: [450, 1945]

#detection2daterange('eerste helft van de 2e eeuw') 
    # output: [100, 149]








