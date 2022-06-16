import config
import wasstraat.harmonizer as harmonizer
import copy
import wasstraat.util as util
import logging
logger = logging.getLogger("airflow.task")


HARMONIZE_PIPELINES = "HARMONIZE_PIPELINES"
SET_KEYS_PIPELINES = "SET_KEYS_PIPELINES"
MOVEANDMERGE_MOVE = "MOVEANDMERGE_MOVE"
MOVEANDMERGE_MERGE = "MOVEANDMERGE_MERGE"
MOVEANDMERGE_INHERITED = "MOVEANDMERGE_INHERITED"
STAGING_COLLECTION = "STAGING_COLLECTION"
EXTRA_FIELDS = 'extra_fields'
MOVEANDMERGE_GENERATE_MISSING_PIPELINES = 'MOVEANDMERGE_GENERATE_MISSING_PIPELINES'
SET_HAMRONIZE = 'SET_HAMRONIZE'
SET_SOORTLIKE = 'SET_SOORTLIKE'


aggr_key_vondst = {'$concat': [ "P", "$projectcd", 
                    {"$cond": ["$vondstkey_met_putnr", {'$concat': ["P", {'$toString': "$putnr" }]}, ""]},
                    {'$concat': ["V", {'$toString': "$vondstnr" }]}]}


INITIALIZED = False

wasstraat_model = {
  "Put": {
        STAGING_COLLECTION: config.COLL_STAGING_OUD,
        SET_HAMRONIZE: 'Put',
        #HARMONIZE_PIPELINES: [harmonizer.getHarmonizeAggr('Put')],
        SET_KEYS_PIPELINES: [[ 
            { '$match': {'soort': "Put"}},
            { '$addFields': {'key': { '$concat': [ "P", "$projectcd", "P", {'$toString': "$putnr"}] }}},  		
            { '$addFields': {'key_project': { '$concat': [ "P", "$projectcd"]}}}
        ]],
        MOVEANDMERGE_GENERATE_MISSING_PIPELINES: [[
            { '$match': {'putnr': { '$exists': {"$toBool": 1} }, 'projectcd': { '$exists': {"$toBool": 1} }}},
            { '$group':{'_id': {"projectcd" : "$projectcd", 'putnr': "$putnr"}}},
            { '$unwind': "$_id"},
            { '$project': {'_id': 0, 'projectcd': "$_id.projectcd", 'putnr': "$_id.putnr"}},       
            { '$addFields': {'brondata.table': 'generated_put', 'brondata.project': '$projectcd', 'soort': 'Put'}}
        ]]
  },
  "Vlak": {
        STAGING_COLLECTION: config.COLL_STAGING_OUD,
        SET_HAMRONIZE: 'Vlak',
        #HARMONIZE_PIPELINES: [harmonizer.getHarmonizeAggr('Vlak')],
        SET_KEYS_PIPELINES: [[ 
            { '$match': {'soort': "Vlak"}},
            { '$addFields': {'key': { '$concat': [ "P", "$projectcd", {'$ifNull': [{'$concat': ["P", {'$toString': "$putnr" }]}, ""]}, "V", {'$toString': "$vlaknr"}] }}},  		
            { '$addFields': {'key_project': { '$concat': [ "P", "$projectcd"]}}},
            { '$addFields': {'key_put': { '$concat': [ "P", "$projectcd", {'$concat': ["P", {'$toString': "$putnr" }]}] }}}	
        ]],
        MOVEANDMERGE_GENERATE_MISSING_PIPELINES: [[
            { '$match': {'vlaknr': { '$exists': {"$toBool": 1} }, 'projectcd': { '$exists': {"$toBool": 1} }, 'putnr': { '$exists': {"$toBool": 1} }}},
            { '$group':{'_id': {"projectcd" : "$projectcd", 'putnr': "$putnr", 'vlaknr': "$vlaknr"}}},
            { '$unwind': "$_id"},
            { '$project': {'_id': 0, 'projectcd': "$_id.projectcd", 'putnr': "$_id.putnr", 'vlaknr': "$_id.vlaknr"}},
            { '$addFields': {'brondata.table': 'generated_vlak', 'brondata.project': '$projectcd', 'soort': 'Vlak'}}
        ]]
  },
  "Spoor": {
        STAGING_COLLECTION: config.COLL_STAGING_OUD,
        SET_HAMRONIZE: 'Spoor',
        #HARMONIZE_PIPELINES: [harmonizer.getHarmonizeAggr('Spoor')],
        SET_KEYS_PIPELINES: [[ 
            { '$match': {'soort': "Spoor"}},
            { '$addFields': {'key': { '$concat': [ "P", "$projectcd", 
                {'$ifNull': [{'$concat': ["P", {'$toString': "$putnr" }]}, ""]},
                {'$ifNull': [{'$concat': ["V", {'$toString': "$vlaknr"}]}, ""]}, "S", {'$toString': "$spoornr"}] }}},  		
            { '$addFields': {'key_vlak': { '$concat': [ "P", "$projectcd", 
                {'$ifNull': [{'$concat': ["P", {'$toString': "$putnr" }]}, ""]},
                {'$ifNull': [{'$concat': ["V", {'$toString': "$vlaknr"}]}, ""]}] }}},  	
            { '$addFields': {'key_project': { '$concat': [ "P", "$projectcd"]}}},
            { '$addFields': {'key_vondst': aggr_key_vondst}}

        ]],
        MOVEANDMERGE_GENERATE_MISSING_PIPELINES: [[
            { '$match': {'vlaknr': { '$exists': {"$toBool": 1} }, 'projectcd': { '$exists': {"$toBool": 1} }, 'putnr': { '$exists': {"$toBool": 1} }, 'spoornr': { '$exists': {"$toBool": 1} }}},
            { '$group':{'_id': {'projectcd':"$projectcd", 'putnr':"$putnr", 'spoornr':"$spoornr", 'vlaknr':"$vlaknr"}, 'aard': {'$max': "$aard"}}},  
            { '$unwind': "$_id"},
            { '$project': {'_id': 0, 'projectcd': "$_id.projectcd", 'putnr': "$_id.putnr", 'spoornr': "$_id.spoornr", 'vlaknr': "$_id.vlaknr"}},
            { '$addFields': {'brondata.table': 'generated_spoor', 'brondata.project': '$projectcd', 'soort': 'Spoor'}}
        ]]
  },
  "Stelling": {
        STAGING_COLLECTION: config.COLL_STAGING_MAGAZIJNLIJST,
        HARMONIZE_PIPELINES: [
            [{ "$match": {"table": "stellingen"}},
            { "$replaceRoot": {"newRoot": {"_id": "$_id", "brondata": "$$ROOT"}}},
            { "$addFields": {"stelling": "$brondata.stelling","inhoud":"$brondata.inhoud", "table":"$brondata.table", "soort": "stelling", "table": "$brondata.table"}},
            { "$merge": { "into": { "db": config.DB_ANALYSE, "coll": config.COLL_ANALYSE }, "on": "_id",  "whenMatched": "replace", "whenNotMatched": "insert" } }]],
        SET_KEYS_PIPELINES: [[ 
            { '$match': {'table': "stellingen"}},
            { '$addFields': {'herkomst': ["magazijnlijst"], 'soort': 'Stelling'}},  	
            { '$addFields': {'key': { '$concat': ['S', "$stelling"]}, 'herkomst': ["stellingen"]}}	
        ]]
  },
  "Artefact": {
        STAGING_COLLECTION: config.COLL_STAGING_OUD,
        SET_HAMRONIZE: 'Artefact',
        #HARMONIZE_PIPELINES: [harmonizer.getHarmonizeAggr('Artefact')],
        SET_KEYS_PIPELINES: [[ 
            { '$match': { 'soort': "Artefact" } },
            { '$addFields': {'key_doos': { '$concat': [ "P", "$projectcd", "D", {'$toString': "$doosnr"}] }}},
            { '$addFields': {'key_project': { '$concat': [ "P", "$projectcd"]}}}, 
            { '$addFields': {'key_put': { '$concat': [ "P", "$projectcd", 
                            {'$concat': ["P", {'$toString': "$putnr" }]}]}}},  				
            { '$addFields': {'key_plaatsing': "$key_doos"}},
            { '$addFields': {'key': { '$concat': [ "P", "$projectcd", 
                {'$ifNull': [{'$concat': ["P", {'$toString': "$putnr" }]}, ""]},
                             {'$concat': ["V", {'$toString': "$vondstnr" }]},
                             {'$concat': ["A", {'$toString': "$artefactnr"}]},  		
                {'$ifNull': [{'$concat': ["S", {'$toString': "$splitid" }]}, ""]}]}}},
            { '$addFields': {'key_subnr': { '$concat': [ "P", "$projectcd", 
                {'$ifNull': [{'$concat': ["P", {'$toString': "$putnr" }]}, ""]},
                             {'$concat': ["V", {'$toString': "$vondstnr" }]},
                             {'$concat': ["A", {'$toString': "$subnr"}]},  		
                {'$ifNull': [{'$concat': ["S", {'$toString': "$splitid" }]}, ""]}]}}},
            { '$addFields': {'key_vondst': aggr_key_vondst}}
    ]]
  },
  "Standplaats": {
      STAGING_COLLECTION: config.COLL_STAGING_MAGAZIJNLIJST,
      HARMONIZE_PIPELINES: [[
        { "$match": { "$or": [{"table": "magazijnlijst"}, {"table": "doosnr"}]}},
        { "$replaceRoot": {"newRoot": {"brondata": "$$ROOT"}}},
        { "$addFields": {"projectcd": "$brondata.CODE", "projectnaam": "$brondata.PROJECT", "stelling": "$brondata.STELLING", "vaknr": "$brondata.VAKNO", "volgletter": "$brondata.VOLGLETTER", "inhoud":"$brondata.INHOUD", "doosnr": "$brondata.DOOSNO", 
            "uitgeleend": "$brondata.UIT", "table": "$brondata.table", "soort": "Standplaats"}},
        { "$merge": { "into": { "db": config.DB_ANALYSE, "coll": config.COLL_ANALYSE }, "on": "_id",  "whenMatched": "keepExisting", "whenNotMatched": "insert" } }
      ]],
      SET_KEYS_PIPELINES: [[ 
        { '$match': {'soort': "Standplaats"}},
        { '$addFields': {'key': { '$concat': [ "S", {'$toString': "$stelling"}, { '$ifNull': [ {'$concat': ["V", {'$toString': "$vaknr"}]}, ""]}, { '$ifNull': [ {'$concat': ["L", {'$toString': "$volgletter"}]}, "" ] }] }}},  	
        { '$addFields': {'key_stelling': { '$concat': [ "S", {'$toString': "$stelling"}]}}}
    ]]
  },
  "Project": {
        STAGING_COLLECTION: config.COLL_STAGING_DELFIT,
        HARMONIZE_PIPELINES: [[ 
            { '$match': { 'table': "OPGRAVINGEN" } },
            { '$replaceRoot': {'newRoot': {'_id': "$_id", 'brondata': "$$ROOT"}}},
            { '$addFields': {'projectcd': "$brondata.CODE", 'projectnaam': "$brondata.OPGRAVING", 'toponiem': "$brondata.TOPONIEM", 'xcoor_rd': "$brondata.XCOORD", 'ycoor_rd': "$brondata.YCOORD", 
                'trefwoorden': "$brondata.TREFWOORDEN", 'jaar': "$brondata.JAAR", 'table': "$brondata.table", 'soort':"project"}},
            { "$merge": { "into": { "db": config.DB_ANALYSE, "coll": config.COLL_ANALYSE }, "on": "_id",  "whenMatched": "replace", "whenNotMatched": "insert" } }
        ]],
        SET_KEYS_PIPELINES: [[ 
            { '$match': { 'soort': "project" } },
            { '$addFields': {'key': { '$concat': [ "P", "$projectcd"]}}},
            { '$addFields': {'soort': 'Project'}}	
        ]]
  },
  "Vindplaats": {
        STAGING_COLLECTION: config.COLL_STAGING_DELFIT,
        HARMONIZE_PIPELINES: [[ 
            { '$match': { 'table': "VINDPLAATSEN" } },
            { '$replaceRoot': {'newRoot': {'_id': "$_id", 'brondata': "$$ROOT"}}},
            { '$addFields': {
                'projectcd': "$brondata.code", 'vindplaats': "$brondata.vindplaats", 'gemeente': "$brondata.gemeente", 'datering': "$brondata.datering", 'soort': "vindplaats",
            'begindatering': "$brondata.begin", 'einddatering': "$brondata.einde", 'aard': "$brondata.aard", 'onderzoek': "$brondata.onderzoek", 'mobilia': "$brondata.mobilia",
            'depot': "$brondata.depot", 'documentatie': "$brondata.documentatie", 'beschrijving': "$brondata.beschrijving", 'xcoor_rd': "$brondata.x-coord", 'ycoor_rd': "$brondata.y-coord", 'soort': "vindplaats", 'table': "$brondata.table"}},
            { "$merge": { "into": { "db": config.DB_ANALYSE, "coll": config.COLL_ANALYSE }, "on": "_id",  "whenMatched": "replace", "whenNotMatched": "insert" } }
        ]],
        SET_KEYS_PIPELINES: [[ 
            { '$match': { 'soort': "vindplaats" } },
            { '$addFields': {'soort': 'Vindplaats'}}	
        ]]
  },
  "Vondst": {
        STAGING_COLLECTION: config.COLL_STAGING_OUD,
        SET_HAMRONIZE: 'Vondst',
        #HARMONIZE_PIPELINES: [harmonizer.getHarmonizeAggr('Vondst')],
        SET_KEYS_PIPELINES: [[ 
            { '$match': { 'soort': "Vondst" } },
            { '$addFields': {'key': aggr_key_vondst}},
            { '$addFields': {'key_vlak': { '$concat': [ "P", "$projectcd", 
                {'$ifNull': [{'$concat': ["P", {'$toString': "$putnr" }]}, ""]},
                    {'$concat': ["V", {'$toString': "$vlaknr"}]}] }}},  		
            { '$addFields': {'key_put': { '$concat': [ "P", "$projectcd", {'$concat': ["P", {'$toString': "$putnr" }]}] }}},
            { '$addFields': {'key_project': { '$concat': [ "P", "$projectcd"]}}}
        ]],
        MOVEANDMERGE_GENERATE_MISSING_PIPELINES: [[
            { '$match': {'putnr': { '$exists': {"$toBool": 1} }, 'projectcd': { '$exists': {"$toBool": 1} }, 'vondstnr': { '$exists': {"$toBool": 1} }}},
            { '$group':{'_id': {"projectcd" : "$projectcd", 'putnr': "$putnr", 'vondstnr': "$vondstnr"}}},
            { '$unwind': "$_id"},
            { '$project': {'_id': 0, 'projectcd': "$_id.projectcd", 'putnr': "$_id.putnr", 'vondstnr': "$_id.vondstnr"}},       
            { '$addFields': {'brondata.table': 'generated_vondst', 'brondata.project': '$projectcd', 'soort': 'Vondst'}}
        ]]
  },
  "Foto": {
        HARMONIZE_PIPELINES: [[]],
        SET_KEYS_PIPELINES: [[ 
            { '$match': { 'soort': "Foto" } },
            { '$addFields': {'key': { '$concat': [ "P", "$projectcd", 
                { '$ifNull': [{'$concat': ["P", {'$toString': "$putnr" }]}, ""]},
                { '$ifNull': [{'$concat': ["V", {'$toString': "$vondstnr" }]}, ""]},
                { '$ifNull': [{'$concat': ["A", {'$toString': "$artefactnr" }]}, ""]},
                { '$ifNull': [{'$concat': ["S", {'$toString': "$fotosubnr"}]}, ""]}]}}},  		
            { '$addFields': {'key_artefact': { '$concat': [ "P", "$projectcd", 
                { '$ifNull': [{'$concat': ["P", {'$toString': "$putnr" }]}, ""]},
                {'$concat': ["V", {'$toString': "$vondstnr" }]},
                {'$concat': ["A", {'$toString': "$artefactnr"}]}]}}},  		
            { '$addFields': {'key_vondst': { '$concat': [ "P", "$projectcd", 
                { '$ifNull': [{'$concat': ["P", {'$toString': "$putnr" }]}, ""]},
                { '$concat': ["V", {'$toString': "$vondstnr" }]}]}}},  		
            { '$addFields': {'key_project': { '$concat': [ "P", "$projectcd"]}}}, 
            { '$addFields': {'key_project_type': { '$concat': [ "$fototype", "P", "$projectcd"]}}}
        ]],
        EXTRA_FIELDS: ['projectcd', 'putnr', 'vondstnr', 'artefactnr', 'fotonr', 'fototype', 'soort']
  },
  "Fotobeschrijving": {
        STAGING_COLLECTION: config.COLL_STAGING_OUD,
        SET_HAMRONIZE: 'Fotobeschrijving',
        #HARMONIZE_PIPELINES: [harmonizer.getHarmonizeAggr('Fotobeschrijving')],
        SET_KEYS_PIPELINES: [[ 
            { '$match': { 'soort': "Fotobeschrijving" } },
            { '$addFields': {'key_vondst': { '$concat': [ "P", "$projectcd", 
                { '$ifNull': [{'$concat': ["P", {'$toString': "$putnr" }]}, ""]},
                { '$concat': ["V", {'$toString': "$vondstnr" }]}]}}}  		
        ]]
  },
  "Fotokoppel": {
        STAGING_COLLECTION: config.COLL_STAGING_DIGIFOTOS,
        SET_HAMRONIZE: 'Fotokoppel',
        #HARMONIZE_PIPELINES: [harmonizer.getHarmonizeAggr('Fotokoppel')],
        SET_KEYS_PIPELINES: [[]] 
  },
  "Plaatsing": {
        STAGING_COLLECTION: config.COLL_STAGING_MAGAZIJNLIJST,
        HARMONIZE_PIPELINES: [[
            { '$match': { 'table': "magazijnlijst" } },
            { '$replaceRoot': {'newRoot': {'brondata': "$$ROOT"}}},
            { '$addFields': {'projectcd': "$brondata.CODE", 'projectnaam': "$brondata.PROJECT", "stelling": "$brondata.stelling","inhoud":"$brondata.INHOUD", "vaknr": "$brondata.VAKNO", "volgletter": "$brondata.VOLGLETTER", "inhoud":"$brondata.INHOUD", "doosnr": "$brondata.DOOSNO", 
                "uitgeleend": "$brondata.UIT", 'stelling': '$brondata.STELLING', 'soort':"Plaatsing"}},
            { "$merge": { "into": { "db": config.DB_ANALYSE, "coll": config.COLL_ANALYSE }, "on": "_id",  "whenMatched": "fail", "whenNotMatched": "insert" } }
        ]],
        SET_KEYS_PIPELINES: [[ 
            { '$match': {'soort': "Plaatsing"}},	
            { '$addFields': {'key_standplaats': 
                { '$concat': [ "S", {'$toString': "$stelling"}, "V", {'$toString': "$vaknr"}, { '$ifNull': [ {'$concat': ["L", {'$toString': "$volgletter"}]}, "" ] }] }		   
            }},  	
            { '$addFields': {'key_doos': 
                { '$concat': [ "P", {"$toString": "$projectcd"}, "D", {'$toString': "$doosnr"}]},		   
            }}  	
        ]]
  },
  "Doos": {
        STAGING_COLLECTION: config.COLL_STAGING_MAGAZIJNLIJST,
        HARMONIZE_PIPELINES: [[
                { '$match': {'table': "magazijnlijst", 'DOOSNO': {"$exists": {"$toBool": 1}}}},
                { '$replaceRoot': {'newRoot': {'brondata': "$$ROOT"}}},
                { '$addFields': {'projectcd': "$brondata.CODE", 'projectnaam': "$brondata.PROJECT", "doosnr": "$brondata.DOOSNO", 'uitgeleend': "$brondata.UIT", "vaknr": "$brondata.VAKNO", "inhoud": "$brondata.INHOUD", 'soort':"Doos", "stelling": "$brondata.STELLING"}},
                { "$merge": { "into": { "db": config.DB_ANALYSE, "coll": config.COLL_ANALYSE }, "on": "_id",  "whenMatched": "fail", "whenNotMatched": "insert" } }
        ]],
        SET_KEYS_PIPELINES: [
            [ 
                { '$match': {'soort': "Doos"}},
                { '$addFields': {'key': { '$concat': [ "P",  '$projectcd', "D", {'$toString': "$doosnr"}]}}},
                { '$addFields': {'key_stelling': { '$concat': [ "S", "$stelling"]}}},
                { '$addFields': {'key_project': { '$concat': [ "P", "$projectcd"]}}}
            ]],        
        MOVEANDMERGE_GENERATE_MISSING_PIPELINES: [
            [ 
                { '$match': {'doosnr': { '$exists': {"$toBool": 1} }, 'soort': "Artefact"}},            
                { '$group':{'_id': {"projectcd" : "$projectcd", 'doosnr': "$doosnr"}}},
                { '$unwind': "$_id"},
                { '$project': {'_id': 0, 'projectcd': "$_id.projectcd", 'doosnr': "$_id.doosnr"}},
                { '$addFields': {'brondata.table': 'generated_Doos', 'brondata.project': '$projectcd', 'soort': 'Doos'}}
            ]
        ],
        EXTRA_FIELDS: ['key_stelling']
  }
}


def addToMetaLike(soort_add, soort_like):
    try:
        set_references_pipelines = copy.deepcopy(wasstraat_model[soort_like]['SET_KEYS_PIPELINES'])
        #set_references_pipelines[0][0] = {'$match': {'soort': soort_add}}

        wasstraat_model[soort_add] = {
            STAGING_COLLECTION: wasstraat_model[soort_like][STAGING_COLLECTION],
            SET_HAMRONIZE: soort_add,
            SET_SOORTLIKE: soort_like,
            #HARMONIZE_PIPELINES: [harmonizer.getHarmonizeAggr(soort_add)],
            SET_KEYS_PIPELINES: set_references_pipelines
        }
        #wasstraat_model[soort_add][HARMONIZE_PIPELINES][0].insert(-1, { '$addFields': {f"{soort_like}soort".lower(): soort_add, 'soort': soort_like}})
    except Exception as err:
        msg = f"Onbekende fout bij het toevoegen van {soort_add} aan meta.wasstraat_model volgens {soort_like} met melding: {str(err)}"
        logger.error(msg)   
        raise Exception(msg) from err

lst_artefactsoort = ['Aardewerk', 'Dierlijk_Bot', 'Glas', 'Leer', 'Steen', 'Kleipijp', 'Menselijk_Bot', 'Hout', 'Bouwaardewerk', 'Metaal', 'Munt', 'Schelp', 'Onbekend', 'Textiel']
[addToMetaLike(soort, 'Artefact') for soort in lst_artefactsoort]  





def init():
    initialized = INITIALIZED

    if not initialized:
        try:
            for soort in wasstraat_model.keys():
                if SET_HAMRONIZE in wasstraat_model[soort].keys():
                    wasstraat_model[soort][HARMONIZE_PIPELINES] = [harmonizer.getHarmonizeAggr(wasstraat_model[soort][SET_HAMRONIZE])]
                if SET_SOORTLIKE in wasstraat_model[soort].keys():
                    soort_like = wasstraat_model[soort][SET_SOORTLIKE]
                    wasstraat_model[soort][HARMONIZE_PIPELINES][0].insert(-1, { '$addFields': {f"{soort_like}soort".lower(): soort, 'soort': soort_like}})

            initialized = True
        except Exception as err:
            msg = f"Onbekende fout bij het initialiseren van meta.wasstraat_model met melding: {str(err)}"
            logger.error(msg)   
            raise Exception(msg) from err
    else:
        pass
    

    
def getHarmonizeStagingCollection(soort):
    init()

    if soort in wasstraat_model.keys():
        return wasstraat_model[soort][STAGING_COLLECTION]
    else:
        raise Exception(f'Fout bij het opvragen van collection van metadata. {soort} is een onbekend metadatasoort.')

def getHarmonizePipeline(soort):
    init()

    if soort in wasstraat_model.keys():
        return wasstraat_model[soort][HARMONIZE_PIPELINES][0]
    else:
        raise Exception(f'Fout bij het opvragen van metadata. {soort} is een onbekend metadatasoort.')

def getHarmonizePipelines(soort):
    init()

    if soort in wasstraat_model.keys():
        return wasstraat_model[soort][HARMONIZE_PIPELINES]
    else:
        raise Exception(f'Fout bij het opvragen van metadata. {soort} is een onbekend metadatasoort.')

def getReferenceKeysPipeline(soort):
    init()

    if soort in wasstraat_model.keys():
        return wasstraat_model[soort][SET_KEYS_PIPELINES][0]
    else:
        raise Exception(f'Fout bij het opvragen van metadata. {soort} is een onbekend metadatasoort.')


def getGenerateMissingPipelines(soort):
    init()

    if soort in getKeys(MOVEANDMERGE_GENERATE_MISSING_PIPELINES):
        aggr1_lst = copy.deepcopy(wasstraat_model[soort][MOVEANDMERGE_GENERATE_MISSING_PIPELINES])
        aggr2 = getReferenceKeysPipeline(soort)

        aggrs = [aggr + aggr2 for aggr in aggr1_lst]

        return aggrs
    else:
        raise Exception(f'Fout bij het opvragen van metadata. {soort} is een onbekend metadatasoort.')



def getVeldnamen(soort):    
    init()

    keyset = set([])
    lst_pipelines = []
    for p in  wasstraat_model[soort][HARMONIZE_PIPELINES]:
        lst_pipelines += p
    for p in  wasstraat_model[soort][SET_KEYS_PIPELINES]:
        lst_pipelines += p

    for x in lst_pipelines:
        if x.get('$addFields'): 
            lst = list(x.get('$addFields').keys())
            keyset.update(lst)
        elif x.get('$project'):
            lst = list(x.get('$project').keys())
            keyset.update(lst)
    
    if EXTRA_FIELDS in wasstraat_model[soort].keys():
        lst = wasstraat_model[soort].get(EXTRA_FIELDS)
        keyset.update(lst)

    keyset.update(['_id'])
    
    result = list(keyset)
    result.sort()    
    return result

# SET_KEYS_PIPELINES
def getKeys(fase):
    if not fase in [HARMONIZE_PIPELINES, SET_KEYS_PIPELINES, MOVEANDMERGE_MOVE, MOVEANDMERGE_MERGE, MOVEANDMERGE_INHERITED, MOVEANDMERGE_GENERATE_MISSING_PIPELINES]:
        raise Exception(f'Fout bij het opvragen van metadata. {fase} is een onbekend fase.')

    all_keys = wasstraat_model.keys()
    
    if fase == MOVEANDMERGE_MOVE:
        set_mrg = set(harmonizer.getObjects(merge=True))
        set_inh = set(harmonizer.getObjects(inherit=True))

        set_keys = set(all_keys) - set_mrg
        set_keys = set_keys - set_inh

        return(list(set_keys)) 

    elif fase == MOVEANDMERGE_MERGE:
        set_mv = set(harmonizer.getObjects(merge=True))
        set_keys = set(all_keys) 
        return(list(set_keys.intersection(set_mv))) 
    
    elif fase == MOVEANDMERGE_INHERITED:
        set_mv = set(harmonizer.getObjects(inherit=True))
        set_keys = set(all_keys) 
        return(list(set_keys.intersection(set_mv))) 
    elif fase == MOVEANDMERGE_GENERATE_MISSING_PIPELINES:
        key_lst = [key for key in all_keys if util.keys_exists(wasstraat_model[key], MOVEANDMERGE_GENERATE_MISSING_PIPELINES)]
        return key_lst
    elif fase == SET_KEYS_PIPELINES:
        keys = []
        for k in all_keys:
            if wasstraat_model[k][fase] != [[]]:
                keys.append(k)
        
        keys = [item for item in keys if item not in lst_artefactsoort]  # do not process all different arteactsoorten
        return keys
    else:
        keys = []
        for k in all_keys:
            if wasstraat_model[k][fase] != [[]]:
                keys.append(k)

        return keys

