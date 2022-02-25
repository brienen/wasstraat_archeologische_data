db.getCollection("Staging_Projecten_Magazijnlijst").aggregate(
[{'$match': {'table': 'stellingen'}}, {'$replaceRoot': {'newRoot': {'_id': '$_id', 'brondata': ['$$ROOT']}}}, {'$addFields': {'stelling': '$brondata.0.stelling', 'inhoud': '$brondata.0.inhoud', 'table': '$brondata.0.table', 'soort': 'stelling', 'putnr': {'$ifNull': ['$brondata.0.PUT', '$brondata.0.PUTNO']}}}
])