import config
import pymongo
import numpy as np
import pandas as pd
import json
import re
import copy
import ast


myclient = pymongo.MongoClient(str(config.MONGO_URI))
stagingDb = myclient[str(config.DB_STAGING)]
analyseDb = myclient[str(config.DB_ANALYSE)]
stagingCol = stagingDb[config.COLL_PLAATJES]
stagingOud = stagingDb[config.COLL_STAGING_OUD]
stagingNieuw = stagingDb[config.COLL_STAGING_NIEUW]
analyseCol = analyseDb[config.COLL_ANALYSE]
analyseColClean = analyseDb[config.COLL_ANALYSE_CLEAN]
metaCollection = stagingDb['Kolominformatie']

AIRFLOW_WASSTRAAT_CONFIG = "./wasstraat_config/Wasstraat_Config_Harmonize.xlsx"
SUGGESTIE_XL = "./wasstraat_config/Wasstraat_Attribuut_Suggestie.xlsx"

xl = pd.read_excel(AIRFLOW_WASSTRAAT_CONFIG, None);
df_table = xl['Objecten']

objecten = list(xl.keys())
objecten.pop(0)

df_attr = pd.DataFrame()
for obj in objecten:
    df_tmp = pd.DataFrame()
    df_tmp = xl[obj][['Attribute', 'Kolommen']]
    df_tmp['Object'] = obj
    df_attr = pd.concat([df_attr, df_tmp])
     
df_attr['Kolommen'] = df_attr.apply(lambda x: ast.literal_eval(x['Kolommen']), axis=1)
df_attr = df_attr.explode('Kolommen').reset_index().drop(['index'], axis=1)

# Add Inherited attributes
df_overerven = pd.DataFrame()
for index, row in df_table[df_table.Overerven.notnull()].iterrows():
    df_tmp = copy.deepcopy(df_attr)
    df_tmp = df_tmp[df_attr.Object == row['Overerven']] #.copy()
    df_tmp['Object'] = row['Object']
    df_overerven = pd.concat([df_overerven, df_tmp])
df_attr = pd.concat([df_attr, df_overerven])


mapper = {"$arrayToObject" : {"$filter": {"input" : {"$objectToArray" : "$brondata"}, 
                                          "as" : "item", 
                                          "cond" : {"$and" : [{"$ne" : ["$$item.v",np.NaN]},{"$ne" : ["$$item.v",None]}, {"$ne" : ["$$item.v",""]}]}}}}

df_count = pd.DataFrame(list(analyseCol.aggregate([
    {"$match": {"brondata": {"$exists": {"$Bool": 1}}, "soort": {"$exists": {"$Bool": 1}}}},
    {"$replaceRoot": { "newRoot": { "$mergeObjects": [ { "soort": {"$ifNull": ["$artefactsoort", "$soort"]}}, mapper ] } } }])))
df_count = df_count.groupby(['soort']).agg(['count'])
df_count.columns = list(df_count.columns.levels[0])
df_count = df_count.reset_index(level=0)
df_count = df_count.melt(id_vars=["soort", "_id"])
df_count = df_count[df_count.value != 0]
df_count.rename(columns={'value': 'teller', 'soort': 'Object', 'variable': 'Kolommen'}, inplace=True)
df_count.sort_values(by=['Object', 'Kolommen'], inplace=True)
df_count['percentage_gevuld'] = pd.to_numeric(100 * df_count['teller'] / df_count['_id'], downcast='integer').round(0)
df_count.drop(columns=['_id'], inplace=True)


def getObject(table):
    for index, row in xl['Objecten'].iterrows():
        kolommen = ast.literal_eval(row['Tabellen'])
        for kolom in kolommen:
            if re.match(kolom, str(table)):
                return row['Object']
    
    return 'Geen' #Nothing found

def flatten(lst):
    flat_list = [item for sublist in lst for item in sublist]
    return list(set(flat_list))


def getAllAttributes():
    #First get table info from MSAccess metainfoi 
    grp_aggr = [{"$match" : {'project': {'$nin': ['MAGAZIJN', 'DELF-IT', 'Digifotos']}, 'table': { '$not': {'$regex':"^SYS.*"}}}},
                {"$group": { "_id": {'table': "$table", 'name': '$name'}, "count": {"$sum": 1},  "omschrijvingen": { "$push": "$Description" },  "projecten": { "$push": "$project" }}},
                {'$replaceRoot': {'newRoot': {'table': "$_id.table", 'name': "$_id.name", 'count': '$count', 'omschrijvingen': "$omschrijvingen", "projecten": "$projecten"}}}]
    df_meta_old = pd.DataFrame(list(metaCollection.aggregate(grp_aggr)))

    #Then for the new projects get meta info from SYS_FIELDS
    grp_aggr = [{"$match" : {'table': 'SYS_FIELDS'}},
                {"$group": { "_id": {'table': "$TABNAAM", 'name': '$VELDNAAM'}, "count": {"$sum": 1},  "omschrijvingen": { "$push": "$VELDINFO" },  "projecten": { "$push": "$project" }}},
                {'$replaceRoot': {'newRoot': {'table': "$_id.table", 'name': "$_id.name", 'count': '$count', 'omschrijvingen': "$omschrijvingen", "projecten": "$projecten"}}}]
    df_meta_new = pd.DataFrame(list(stagingOud.aggregate(grp_aggr)))

    # Now Concat them 
    df = pd.concat([df_meta_old, df_meta_new], ignore_index=True)
    df['Object'] = df.apply(lambda x: getObject(x['table']), axis=1)

    # Now get all unique attributes 
    df = df.groupby(['Object', 'name']).agg({'omschrijvingen':lambda x: list(x), 'count':lambda x: sum(x), 'projecten': lambda x: list(x)}).reset_index()
    df['omschrijvingen'] = df.apply(lambda x: flatten(x['omschrijvingen']), axis=1)
    df['projecten'] = df.apply(lambda x: flatten(x['projecten']), axis=1)
    df = df.rename(columns={"name": "Kolommen"})

    #Merge it with the attrubutes used in the Excel to 
    df = pd.merge(df, df_attr, on=['Object', 'Kolommen'], how='left')
    df['Attribute'] = df['Attribute'].fillna(value="")

    #Merge with the count of the columns
    df = pd.merge(df, df_count, on=['Object', 'Kolommen'], how='left')
    #df = df.dropna()
    df['teller'] = pd.to_numeric(df['teller'], downcast='integer')
    
    return df


def getArtefactAttributes():
    df_table = xl['Artefact']
    return list(df_table['Attribute'].unique())
    
