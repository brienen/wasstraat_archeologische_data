import shared.config as config
import pandas as pd
import re
import copy
import ast
import wasstraat.util as util
import wasstraat.meta as meta

import logging
logger = logging.getLogger("airflow.task")


AIRFLOW_WASSTRAAT_CONFIG = config.AIRFLOW_WASSTRAAT_CONFIG
HARMONIZE_AGGR = [
    {'$match': {"table": {"$in" : ["XXX","YYY"]}}},
    {"$match": {"table": {"$in" : ["XXX","YYY"]}}},
    {"$replaceRoot" : {"newRoot" : {"_id" : "$_id", "brondata" : "$$ROOT"}}},
    {"$addFields" : { 
        "projectcd" : "$brondata.projectcd"}}
    ,{ "$merge": { "into": { "db": config.DB_ANALYSE, "coll": config.COLL_ANALYSE }, "on": "_id",  "whenMatched": "replace", "whenNotMatched": "insert"}}
]
HARMONIZER = None


def getAggrTables(root, tabellen, include): 
    lst_tabellen = ast.literal_eval(tabellen)
    if len(lst_tabellen) == 0:
        root["table"] = {"$in" : []} if include else {"$not": {"$in" : []}}
    elif len(lst_tabellen) == 1:
        regx = re.compile(lst_tabellen[0], re.IGNORECASE)
        #root["table"] = {'$regex': lst_tabellen[0], '$options': 'i'} if include else {"$not": {'$regex': lst_tabellen[0], '$options': 'i'}}
        root["table"] = regx if include else {"$not": regx}
    else:
        or_lst = []
        for tabel in lst_tabellen:
            regx = re.compile(tabel, re.IGNORECASE)
            #or_lst.append({"table": {'$regex': tabel, '$options': 'i'}} if include else {"table": {"$not": {'$regex': tabel, '$options': 'i'}}})
            or_lst.append({"table": regx} if include else {"table": {"$not": regx}})
        root = {"$or": or_lst} if include else {"$and": or_lst}
    return root


def getKolomValues(kolommen):
    if len(kolommen) == 0:
        return None
    elif len(kolommen) == 1:
        return "$brondata." + kolommen[0]
    else:
        val = kolommen.pop(0)
        return {'$ifNull': ["$brondata." + val, getKolomValues(kolommen)]}

    
def getAttributes(root, df_attributes):
    for index, row in df_attributes.iterrows():        
        kolommen = row['Kolommen']
        if re.match(r"\[.*\]", str(kolommen)):
            kolommen = ast.literal_eval(kolommen)
            root[row['Attribute']] = getKolomValues(kolommen)
        else:
            root[row['Attribute']] = kolommen
        
    return root


# initialize all attributes so that they can be used for inheritenace
def initAttributes(xl):
    aggr = copy.deepcopy(HARMONIZE_AGGR)
    lst_objecten = xl['Objecten']['Object'].unique()
    aggr = aggr[3]['$addFields']
    return { obj:getAttributes(copy.deepcopy(aggr), xl[obj]) for obj in lst_objecten if obj in xl.keys() }


def createAggr(soort, tabellen, tabellen_Ignore, xl, attrs, abr_materiaal):
    aggr = copy.deepcopy(HARMONIZE_AGGR)

    idx_addfields = 3
    # Fase Negative match
    aggr[0]["$match"] = getAggrTables(aggr[0]["$match"], tabellen_Ignore, False)
    # Fase Positive match
    aggr[1]["$match"] = getAggrTables(aggr[1]["$match"], tabellen, True)
    # Fase create addFields from inherited Class
    overerven_van = xl['Objecten'][xl['Objecten']['Object'] == soort]['Overerven'].values[0]

    # Fase create inherited fields
    if overerven_van != "" and pd.notna(overerven_van):
        idx_addfields += 1
        aggr_flds = copy.deepcopy(aggr[3])
        aggr_flds['$addFields'] = attrs[overerven_van]
        aggr.insert(idx_addfields-1, aggr_flds)

    # Fase create addFields
    if soort in xl.keys():
        aggr[idx_addfields]['$addFields'] = attrs[soort]
    aggr[idx_addfields]['$addFields']['soort'] = soort

    # Add ABR if available
    if util.not_empty(abr_materiaal):
        aggr[idx_addfields]['$addFields']['abr_materiaal'] = abr_materiaal

    return aggr
   
    
def loadHarmonizer():
    xl = pd.read_excel(AIRFLOW_WASSTRAAT_CONFIG, sheet_name=None)
    attrs = initAttributes(xl)
    
    df = xl['Objecten']    
    df['Object'] = df['Object'].apply(lambda x: x.strip())
    df['aggr'] = df.apply(lambda x: createAggr(x['Object'], x['Tabellen'], df[df.Object == 'Ignore']['Tabellen'].values[0], xl, attrs, x['ABR-materiaal']), axis=1)   
    
    HARMONIZER = df    
    return HARMONIZER
  
    
def getHarmonizeAggr(soort, reload=False):
    global HARMONIZER
    
    if not isinstance(HARMONIZER, type(pd.DataFrame))  or reload:
        HARMONIZER = loadHarmonizer()
      
    if not soort in HARMONIZER['Object'].unique():
        msg = 'Error while loading harmonizer, ' + soort + ' does not exist in Excel.'
        logger.error(msg) 
        raise Exception(msg)

    aggr = HARMONIZER[HARMONIZER.Object == soort]['aggr'].values[0]
    if soort in meta.lst_artefactsoort:
        aggr.insert(-1, { '$addFields': {"artefactsoort": soort, 'soort': 'Artefact'}})
    return aggr


def getObjects(inherit=False, merge=False):
    if inherit and merge:
        msg = 'When getting objects, inherit and merge cannot both be True.'
        logger.error(msg) 
        raise Exception(msg)

    df = pd.read_excel(AIRFLOW_WASSTRAAT_CONFIG, sheet_name='Objecten')
    if not inherit and not merge:
        return list(df[pd.isnull(df.Overerven) & pd.isnull(df.Overerven)]['Object'])
    elif not inherit:
        return list(df[pd.notnull(df.Samenvoegen)]['Object'])
    else:
        return list(df[pd.notnull(df.Overerven)]['Object'])


def getMergeWith(soort, inherit=True):
    df = pd.read_excel(AIRFLOW_WASSTRAAT_CONFIG, sheet_name='Objecten')

    return df[df.Object == soort]['Overerven'].values[0] if inherit else df[df.Object == soort]['Samenvoegen'].values[0]


    

