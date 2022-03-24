db.getCollection("Single_Store").aggregate(
// Pipeline
[
{"$match": {"soort": "Artefact"}},
{"$match": {"$and": [{"subnr": {"$exists": True}}, {"brondata.ARTEFACT": {"$exists": False}}, {"brondata.table": {"$nin": ["ROMEINS AARDEWERK"]}}, {"projectcd": {"$nin": ["DC112"]}}] }},
{"$replaceRoot": {"newRoot": {"$arrayToObject": { "$filter" : { "input" : { "$objectToArray" : "$$ROOT"}, "as" : "item", "cond" : { "$and" : [{ "$ne" : ["$$item.v", np.nan]}, { "$ne" : ["$$item.v", None]},{ "$ne" : ["$$item.v", '-']}]}}}}}},
{"$group": {'_id': {'key_subnr': '$key_subnr', 'artefactsoort': '$artefactsoort'},'doc': {'$mergeObjects': '$$ROOT'},'brondata': {'$addToSet': '$$ROOT.brondata'},'tables': {'$addToSet': '$$ROOT.brondata.table'},'projects': {'$addToSet': '$$ROOT.brondata.project'}}},
{"$project": {"doc.brondata": 0}},
{"$addFields": { "doc.brondata": "$brondata", "doc.wasstraat.tables": "$tables", "doc.wasstraat.projects": "$projects" }},
{"$replaceRoot": {"newRoot": '$doc'}},
{"$addFields": {"brondata_count": { "$size": "$brondata" }}}
]