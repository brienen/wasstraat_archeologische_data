import config
import wasstraat.harmonizer as harmonizer

HARMONIZE_PIPELINES = "HARMONIZE_PIPELINES"
SET_REFERENCES_PIPELINES = "SET_REFERENCES_PIPELINES"
STAGING_COLLECTION = "STAGING_COLLECTION"
EXTRA_FIELDS = 'extra_fields'



wasstraat_model = {
  "Put": {
        STAGING_COLLECTION: config.COLL_STAGING_OUD,
        HARMONIZE_PIPELINES: [harmonizer.getHarmonizeAggr('Put')],
        SET_REFERENCES_PIPELINES: [[ 
            #{ '$match': { '$and': [{'putnr': { '$exists': True }}, {'projectcd': { '$exists': True }}]}},
            #{ '$group':{'_id': {"projectcd" : "$projectcd", 'putnr': "$putnr"}}},
            #{ '$unwind': "$_id"},
            #{ '$project': {'_id': 0, 'projectcd': "$_id.projectcd", 'putnr': "$_id.putnr"}},
            { '$match': {'soort': "Spoor"}},
            { '$addFields': {'key': { '$concat': [ "P", "$projectcd", "P", {'$toString': "$putnr"}] }}},  		
            { '$addFields': {'key_project': { '$concat': [ "P", "$projectcd"]}}},
            { '$addFields': {'soort': 'Put'}}	
        ]]
  },
  "Vlak": {
        STAGING_COLLECTION: config.COLL_STAGING_OUD,
        HARMONIZE_PIPELINES: [harmonizer.getHarmonizeAggr('Vlak')],
        SET_REFERENCES_PIPELINES: [[ 
            #{ '$match': {'vlaknr': { '$exists': True }}},
            #{ '$group':{'_id': {"projectcd" : "$projectcd", 'putnr': "$putnr", 'vlaknr': "$vlaknr"}}},
            #{ '$unwind': "$_id"},
            #{ '$project': {'_id': 0, 'projectcd': "$_id.projectcd", 'putnr': "$_id.putnr", 'vlaknr': "$_id.vlaknr"}},
            { '$match': {'soort': "Vlak"}},
            { '$addFields': {'key': { '$concat': [ "P", "$projectcd", {'$ifNull': [{'$concat': ["P", {'$toString': "$putnr" }]}, ""]}, "V", {'$toString': "$vlaknr"}] }}},  		
            { '$addFields': {'key_project': { '$concat': [ "P", "$projectcd"]}}},
            { '$addFields': {'key_put': { '$concat': [ "P", "$projectcd", {'$ifNull': [{'$concat': ["P", {'$toString': "$putnr" }]}, ""]}] }, 'soort': 'Vlak'}}	
        ]]
  },
  "Spoor": {
        STAGING_COLLECTION: config.COLL_STAGING_OUD,
        HARMONIZE_PIPELINES: [harmonizer.getHarmonizeAggr('Spoor')],
        SET_REFERENCES_PIPELINES: [[ 
            #{'$match': {'spoornr': { '$exists': True }}},
            #{ '$group':{'_id': {'projectcd':"$projectcd", 'putnr':"$putnr", 'spoornr':"$spoornr", 'vlaknr':"$vlaknr"}, 'aard': {'$max': "$aard"}}},  
            #{ '$unwind': "$_id"},
            #{ '$project': {'_id': 0, 'projectcd': "$_id.projectcd", 'putnr': "$_id.putnr", 'spoornr': "$_id.spoornr", 'vlaknr': "$_id.vlaknr"}},
            { '$match': {'soort': "Spoor"}},
            { '$addFields': {'key': { '$concat': [ "P", "$projectcd", 
                {'$ifNull': [{'$concat': ["P", {'$toString': "$putnr" }]}, ""]},
                {'$ifNull': [{'$concat': ["V", {'$toString': "$vlaknr"}]}, ""]}, "S", {'$toString': "$spoornr"}] }}},  		
            { '$addFields': {'key_vlak': { '$concat': [ "P", "$projectcd", 
                {'$ifNull': [{'$concat': ["P", {'$toString': "$putnr" }]}, ""]},
                {'$ifNull': [{'$concat': ["V", {'$toString': "$vlaknr"}]}, ""]}] }}},  	
            { '$addFields': {'key_project': { '$concat': [ "P", "$projectcd"]}}},
            { '$addFields': {'soort': 'Spoor'}}	
        ]]
  },
  "Stelling": {
        STAGING_COLLECTION: config.COLL_STAGING_MAGAZIJNLIJST,
        HARMONIZE_PIPELINES: [
            [{ "$match": {"table": "stellingen"}},
            { "$replaceRoot": {"newRoot": {"_id": "$_id", "brondata": "$$ROOT"}}},
            { "$addFields": {"stelling": "$brondata.stelling","inhoud":"$brondata.inhoud", "table":"$brondata.table", "soort": "stelling", "table": "$brondata.table"}},
            { "$merge": { "into": { "db": config.DB_ANALYSE, "coll": config.COLL_ANALYSE }, "on": "_id",  "whenMatched": "replace", "whenNotMatched": "insert" } }]],
        SET_REFERENCES_PIPELINES: [[ 
            { '$match': {'table': "stellingen"}},
            { '$addFields': {'herkomst': ["magazijnlijst"], 'soort': 'Stelling'}},  	
            { '$addFields': {'key': { '$concat': ['S', "$stelling"]}, 'herkomst': ["stellingen"]}}	
        ]]
  },
  "Aardewerk": {
        STAGING_COLLECTION: config.COLL_STAGING_OUD,
        HARMONIZE_PIPELINES: [harmonizer.getHarmonizeAggr('Aardewerk')],
        SET_REFERENCES_PIPELINES: [[]]
  },
  "Artefact": {
        STAGING_COLLECTION: config.COLL_STAGING_OUD,
        HARMONIZE_PIPELINES: [harmonizer.getHarmonizeAggr('Artefact')],
          #[ 
          #  {'$match': { '$or': [
          #  {'table': {'$regex':'.*steen.*', '$options': 'i'}},
          #  {'table': {'$regex':'.*aardewerk.*', '$options': 'i'}},
          #  {'table': {'$regex':'.*hout.*', '$options': 'i'}},
          #  {'table': {'$regex':'.*glas.*', '$options': 'i'}},
          #  {'table': {'$regex':'.*leer.*', '$options': 'i'}},					
          #  {'table': {'$regex':'.*metaal.*', '$options': 'i'}},					
          #  {'table': {'$regex':'.*penning.*', '$options': 'i'}},					
          #  {'table': {'$regex':'.*spijker.*', '$options': 'i'}},					
          #  {'table': {'$regex':'.*kleipijp.*', '$options': 'i'}},					
          #  {'table': {'$regex':'.*bot.*', '$options': 'i'}},					
          #  {'table': {'$regex':'.*skelet.*', '$options': 'i'}},					
          # ]}},
          #  {'$match': { 'table': {'$not': {'$regex':'.*backup.*', '$options': 'i'}}}},
          #  {'$match': { 'table': {'$not': {'$regex':'.*kopie.*', '$options': 'i'}}}},
          #  {'$replaceRoot': {'newRoot': {'_id': "$_id", 'brondata': "$$ROOT"}}},
          #  {'$addFields': {'putnr': {'$ifNull': ["$brondata.PUTNO", "$brondata.Put"]}}},  		
          #  {'$addFields': {'spoornr': {'$ifNull': ["$brondata.SPOORNO", "$brondata.Spoor"]}}},  		
          #  {'$addFields': {'vondstnr': {'$ifNull': ["$brondata.VONDSTNO", "$brondata.Vondst"]}}},  		
          #  {'$addFields': {'doosnr': {'$ifNull': ["$brondata.DOOSNO", "$brondata.10a"]}}},
          #  {'$addFields': {'herkomst': {'$concat': ["$brondata.project", ".", "$brondata.table"]}}},  		  	  	  
          #  {'$addFields': {'projectcd': "$brondata.project", 'soort': "artefact"}},
          #  {'$addFields': {'datering': {'$ifNull': ["$brondata.3", "$brondata.1c"]}}},  		
          #  {'$addFields': {'datering': {'$ifNull': ["$datering","$brondata.DATERING"]}}},  		
          #  {'$addFields': {'artefactnr': "$brondata.SUBNO", 'beschrijving': "$brondata.4b", 'vindplek': "$brondata.1b", 'dateringvanaf': "$brondata.3a", 'dateringtot': "$brondata.3b", 'typecd': "$brondata.2", 'opmerkingen': "$brondata.OPMERKING", 
          #      'typevoorwerp': "$brondata.7a", 'functievoorwerp': "$brondata.7b", 'origine': "$brondata.8", 'literatuur': "$brondata.9",'tekeningnr': "$brondata.10b", 'fotonrs': "$brondata.10d", 'dianrs': "$brondata.10c", 'restauratie': "$brondata.12", 'exposabel': "$brondata.13", 'conserveren': "$brondata.14", 'soort': "artefact", 'table': "$brondata.table"}},
            #{'$addFields': {'artefactsoort': { '$switch': {
            #    'branches': [
            #        { 'case': {'table': {'$regex':'.*steen.*', '$options': 'i'}}, 'then': "bot" },
            #        { 'case': {'table': {'$regex':'.*aardewerk.*', '$options': 'i'}}, 'then': "aardewerk" },
            #        { 'case': {'table': {'$regex':'.*hout.*', '$options': 'i'}}, 'then': "hout" },
            #        { 'case': {'table': {'$regex':'.*glas.*', '$options': 'i'}}, 'then': "glas" },
            #        { 'case': {'table': {'$regex':'.*leer.*', '$options': 'i'}}, 'then': "leer" },
            #        { 'case': {'table': {'$regex':'.*metaal.*', '$options': 'i'}}, 'then': "metaal" },
            #        { 'case': {'table': {'$regex':'.*penning.*', '$options': 'i'}}, 'then': "penning" },
            #        { 'case': {'table': {'$regex':'.*spijker.*', '$options': 'i'}}, 'then': "spijker" },
            #        { 'case': {'table': {'$regex':'.*bot.*', '$options': 'i'}}, 'then': "bot" },
            #        { 'case': {'table': {'$regex':'.*skelet.*', '$options': 'i'}}, 'then': "skelet" },
            #        { 'case': {'table': {'$regex':'.*kleipijp.*', '$options': 'i'}}, 'then': "kleipijp" }
            #    ],
            #    'default': "Onbekend" }}}},	  	  	           
            #{ "$merge": { "into": { "db": config.DB_ANALYSE, "coll": config.COLL_ANALYSE }, "on": "_id",  "whenMatched": "replace", "whenNotMatched": "insert" } }
            #]],
        SET_REFERENCES_PIPELINES: [[ 
            { '$match': { 'soort': "artefact" } },
            { '$addFields': {'key_doos': { '$concat': [ "P", "$projectcd", "D", {'$toString': "$doosnr"}] }}},
            { '$addFields': {'key_project': { '$concat': [ "P", "$projectcd"]}}}, 
            { '$addFields': {'key_put': { '$concat': [ "P", "$projectcd", 
                {'$ifNull': [{'$concat': ["P", {'$toString': "$putnr" }]}, ""]}]}}},  				
            { '$addFields': {'key_plaatsing': "$key_doos"}},
            { '$addFields': {'key': { '$concat': [ "P", "$projectcd", 
                {'$ifNull': [{'$concat': ["P", {'$toString': "$putnr" }]}, ""]},
                {'$ifNull': [{'$concat': ["V", {'$toString': "$vondstnr" }]}, ""]},
                {'$ifNull': [{'$concat': ["A", {'$toString': "$artefactnr"}]}, ""]}]}}},  		
            { '$addFields': {'key_vondst': { '$concat': [ "P", "$projectcd", 
                {'$ifNull': [{'$concat': ["P", {'$toString': "$putnr" }]}, ""]},
                "V", {'$toString': "$vondstnr"}] }}},  	
            { '$addFields': {'soort': 'Artefact'}}	
    ]]
  },
  "Magazijnlocatie": {
      STAGING_COLLECTION: config.COLL_STAGING_MAGAZIJNLIJST,
      HARMONIZE_PIPELINES: [[
        { "$match": { "$or": [{"table": "magazijnlijst"}, {"table": "doosnr"}]}},
        { "$replaceRoot": {"newRoot": {"_id": "$_id", "brondata": "$$ROOT"}}},
        { "$addFields": {"projectcd": "$brondata.CODE", "projectnaam": "$brondata.PROJECT", "stelling": "$brondata.STELLING", "vaknr": "$brondata.VAKNO", "volgletter": "$brondata.VOLGLETTER", "inhoud":"$brondata.INHOUD", "doosnr": "$brondata.DOOSNO", 
            "uitgeleend": "$brondata.UIT", "table": "$brondata.table"}},
        { "$merge": { "into": { "db": config.DB_ANALYSE, "coll": config.COLL_ANALYSE }, "on": "_id",  "whenMatched": "replace", "whenNotMatched": "insert" } }
      ]],
      SET_REFERENCES_PIPELINES: [[ 
        { '$match': {'table': "magazijnlijst"}},
        { '$addFields': {'herkomst': ["magazijnlijst"], 'soort': 'Magazijnlocatie'}},  	
        { '$addFields': {'key': { '$concat': [ "S", "$stelling", { '$ifNull': [ {'$concat': ["V", {'$toString': "$vaknr"}]}, ""]}, { '$ifNull': [ {'$concat': ["L", "$volgletter"]}, "" ] }] }}},  	
        { '$addFields': {'soort':  { '$concat': [ "S", "$stelling"]}}},
        { '$addFields': {'key_stelling': 'Magazijnlocatie'}},
        { '$project': {'_id':0}} # Make sure magazijnlijsten do not interfere with plaatsingen
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
        SET_REFERENCES_PIPELINES: [[ 
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
        SET_REFERENCES_PIPELINES: [[ 
            { '$match': { 'soort': "vindplaats" } },
            { '$addFields': {'soort': 'Vindplaats'}}	
        ]]
  },
  "Vondst": {
        STAGING_COLLECTION: config.COLL_STAGING_OUD,
        HARMONIZE_PIPELINES: [harmonizer.getHarmonizeAggr('Vondst')],
            #[ 
            #{ '$match': {'table': "VONDSTENLIJST"}},
            #{ '$replaceRoot': {'newRoot': {'_id': "$_id", 'brondata': "$$ROOT"}}},
            #{ '$addFields': {'projectcd': "$brondata.project", 'vondstnr': {'$ifNull': ["$brondata.VONDSTNO", "$brondata.Vondst"]}}},  		
            #{ '$addFields': {'putnr': {'$ifNull': ["$brondata.PUTNO", "$brondata.Put"]}}},  		
            #{ '$addFields': {'spoornr': {'$ifNull': ["$brondata.SPOORNO", "$brondata.Spoor"]}}},  		
            #{ '$addFields': {'vlaknr': {'$ifNull': ["$brondata.VLAKNO", "$brondata.Vlak"]}}},  		
            #{ '$addFields': {'lengte': "$brondata.LENGTE", 'breedte': "$brondata.BREEDTE", 'diepte': "$brondata.DIEPTE", 'omstandigheden': "$brondata.VONDSTOMSTH", 'inhoud': "$brondata.INHOUD",
            #    'datering': "$brondata.VOORLOPIGEDATERING", 'xcoor_rd': "$brondata.XCOORD", 'ycoor_rd': "$brondata.YCOORD", 'datum': "$brondata.DATUM", 'table': "$brondata.table", 'soort':"vondst"}},
            #{ "$merge": { "into": { "db": config.DB_ANALYSE, "coll": config.COLL_ANALYSE }, "on": "_id",  "whenMatched": "replace", "whenNotMatched": "insert" } }
        #]],
        SET_REFERENCES_PIPELINES: [[ 
            { '$match': { 'soort': "vondst" } },
            { '$addFields': {'key': { '$concat': [ "P", "$projectcd", 
                {'$ifNull': [{'$concat': ["P", {'$toString': "$putnr" }]}, ""]},
                {'$ifNull': [{'$concat': ["V", {'$toString': "$vondstnr" }]}, ""]}]}}},
            { '$addFields': {'key_vlak': { '$concat': [ "P", "$projectcd", 
                {'$ifNull': [{'$concat': ["P", {'$toString': "$putnr" }]}, ""]},
                {'$ifNull': [{'$concat': ["V", {'$toString': "$vlaknr"}]}, ""]}] }}},  		
            { '$addFields': {'key_put': { '$concat': [ "P", "$projectcd", 
                {'$ifNull': [{'$concat': ["P", {'$toString': "$putnr" }]}, ""]}] }}},  		
            { '$addFields': {'key_project': { '$concat': [ "P", "$projectcd"]}}},
            { '$addFields': {'soort': 'Vondst'}}	
        ]]
  },
  "Foto": {
        HARMONIZE_PIPELINES: [[]],
        SET_REFERENCES_PIPELINES: [[ 
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
  "Plaatsing": {
        STAGING_COLLECTION: config.COLL_STAGING_MAGAZIJNLIJST,
        HARMONIZE_PIPELINES: [[]],
        SET_REFERENCES_PIPELINES: [[ 
            { '$match': {'table': "magazijnlijst"}},	
            { '$addFields': {'key_magazijnlocatie': 
                { '$concat': [ "S", "$STELLING", "V", {'$toString': "$VAKNO"}, { '$ifNull': [ {'$concat': ["L", "$VOLGLETTER"]}, "" ] }] }		   
            }},  	
            { '$addFields': {'key_doos': 
                { '$concat': [ "P", "$projectcd", "D", {'$toString': "$doosnr"}]},		   
            }},  	
            { '$addFields': {'herkomst': ["magazijnlijst"]}},  	
            { '$addFields': {'soort': 'Plaatsing'}}	
            #, { '$merge': {'into': config.COLL_ANALYSE_CLEAN}}
        ]]
  },
  "Doos": {
        STAGING_COLLECTION: config.COLL_STAGING_MAGAZIJNLIJST,
        HARMONIZE_PIPELINES: [[]],
        SET_REFERENCES_PIPELINES: [[ 
                { '$match': { '$and': [{'doosnr': { '$exists': True }}, {'soort': "artefact"}]}},
                { '$group':{'_id': {"projectcd" : "$projectcd", 'doosnr': "$doosnr"}}},
                { '$unwind': "$_id"},
                { '$project': {'_id': 0, 'projectcd': "$_id.projectcd", 'doosnr': "$_id.doosnr"}},
                { '$addFields': {'key': { '$concat': [ "P", "$projectcd", "D", {'$toString': "$doosnr"}] }, 'soort': 'Doos'}},
                { '$addFields': {'key_project': { '$concat': [ "P", "$projectcd"]}}}
                ,{ "$out": config.COLL_ANALYSE_DOOS}
            ],[
                { '$match': { '$and': [ {'table': "magazijnlijst"}, {'doosnr': { '$exists': True }} ] } },	
                { '$addFields': {'herkomst': ["magazijnlijst"]}},  	
                { '$addFields': {'key': { '$concat': [ "P", { '$ifNull': [ '$projectcd', {'$concat': ["I",{'$toString': '$_id'}]} ] }, "D", {'$toString': "$doosnr"}] }}},  	
                { '$addFields': {'key_magazijnlocatie': { '$concat': [ "S", "$stelling", "V", {'$toString': "$vaknr"}, { '$ifNull': [ {'$concat': ["L", "$volgletter"]}, "" ] }] }}},  
                { '$addFields': {'key_project': { '$concat': [ "P", { '$ifNull': [ '$projectcd', {'$concat': ["I",{'$toString': '$_id'}]} ] }]}}},
                { '$addFields': {'soort': 'Doos'}},	
                { '$project': {'_id':0}},
                { "$merge": { "into": config.COLL_ANALYSE_DOOS, "on": "key",  "whenMatched": "merge", "whenNotMatched": "insert" } }
            ],[ 
                { '$match': {'table': "doosnr"}},
                { '$addFields': {'key': { '$concat': [ "P", { '$ifNull': [ '$projectcd', {'$concat': ["I",{'$toString': '$_id'}]} ] }, "D", {'$toString': "$doosnr"}] }}},
                { '$project': {'_id':0}},
                { '$addFields': {'soort': 'Doos'}},	
                { '$addFields': {'key_project': { '$concat': [ "P", { '$ifNull': [ '$projectcd', {'$concat': ["I",{'$toString': '$_id'}]} ] }]}}},
                { "$merge": { "into": config.COLL_ANALYSE_DOOS, "on": "key",  "whenMatched": "merge", "whenNotMatched": "insert" } }
            ]],
        EXTRA_FIELDS: ['key_stelling']
  }
}
wasstraat_model["Plaatsing"][HARMONIZE_PIPELINES] = wasstraat_model['Magazijnlocatie']['HARMONIZE_PIPELINES']
wasstraat_model["Doos"][HARMONIZE_PIPELINES] = [wasstraat_model['Magazijnlocatie']['HARMONIZE_PIPELINES'][0]]
wasstraat_model["Aardewerk"][SET_REFERENCES_PIPELINES] = wasstraat_model['Artefact']['SET_REFERENCES_PIPELINES']



def getHarmonizeStagingCollection(soort):
    if soort in wasstraat_model.keys():
        return wasstraat_model[soort][STAGING_COLLECTION]
    else:
        raise Exception(f'Fout bij het opvragen van collection van metadata. {soort} is een onbekend metadatasoort.')

def getHarmonizePipeline(soort):
    if soort in wasstraat_model.keys():
        return wasstraat_model[soort][HARMONIZE_PIPELINES][0]
    else:
        raise Exception(f'Fout bij het opvragen van metadata. {soort} is een onbekend metadatasoort.')

def getHarmonizePipelines(soort):
    if soort in wasstraat_model.keys():
        return wasstraat_model[soort][HARMONIZE_PIPELINES]
    else:
        raise Exception(f'Fout bij het opvragen van metadata. {soort} is een onbekend metadatasoort.')

def getReferenceKeysPipeline(soort):
    if soort in wasstraat_model.keys():
        return wasstraat_model[soort][SET_REFERENCES_PIPELINES][0]
    else:
        raise Exception(f'Fout bij het opvragen van metadata. {soort} is een onbekend metadatasoort.')

def getReferenceKeysPipelines(soort):
    if soort in wasstraat_model.keys():
        return wasstraat_model[soort][SET_REFERENCES_PIPELINES]
    else:
        raise Exception(f'Fout bij het opvragen van metadata. {soort} is een onbekend metadatasoort.')


def getVeldnamen(soort):    
    keyset = set([])
    lst_pipelines = []
    for p in  wasstraat_model[soort][HARMONIZE_PIPELINES]:
        lst_pipelines += p
    for p in  wasstraat_model[soort][SET_REFERENCES_PIPELINES]:
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


def getKeys(fase):
    if not fase in [HARMONIZE_PIPELINES, SET_REFERENCES_PIPELINES]:
        raise Exception(f'Fout bij het opvragen van metadata. {fase} is een onbekend fase.')

    all_keys = wasstraat_model.keys()
    keys = []
    for k in all_keys:
        if wasstraat_model[k][fase] != [[]]:
            keys.append(k)
    return keys
