// Stages that have been excluded from the aggregation pipeline query
__3tsoftwarelabs_disabled_aggregation_stages = [

    {
        // Stage 8 - excluded
        stage: 8,  source: {
            $match: {
                // enter query here
                "$and": [{"brondata_count": {"$gt": 1}}]
            }
        }
    }
]

db.getCollection("Single_Store").aggregate(

    // Pipeline
    [
        // Stage 1
        {
            $match: {
                // enter query here
                "$and": [{"soort": "Artefact"}, {"subnr": {"$exists": true}}, {"brondata.ARTEFACT": {"$exists": false}}, {"brondata.table": {"$nin": ["ROMEINS AARDEWERK"]}}, {"projectcd": {"$nin": ["DC112"]}}] //Nog toevoegen allerlei projectcodees die we niet willen samenvoegen
            }
        },

        // Stage 2
        {
            $replaceRoot: {
                newRoot: {"$arrayToObject": { 
                                            "$filter" : { 
                                                "input" : { 
                                                    "$objectToArray" : "$$ROOT"
                                                }, 
                                                "as" : "item", 
                                                "cond" : { 
                                                    "$and" : [
                                                        { 
                                                            "$ne" : [
                                                                "$$item.v", 
                                                                'NaN'
                                                            ]
                                                        }, 
                                                        { 
                                                            "$ne" : [
                                                                "$$item.v", 
                                                                null
                                                            ]
                                                        },
                                                        { 
                                                            "$ne" : [
                                                                "$$item.v", 
                                                                '-'
                                                            ]
                                                        }
                                                    ]
                                                }
                                            }
                                        }}
            }
        },

        // Stage 3
        {
            $group: {
                '_id': {'key_subnr': '$key_subnr', 'artefactsoort': '$artefactsoort'},
                'doc': {'$mergeObjects': '$$ROOT'},
                'brondata': {'$addToSet': '$$ROOT.brondata'},
                'tables': {'$addToSet': '$$ROOT.brondata.table'},
                'projects': {'$addToSet': '$$ROOT.brondata.project'}
                //<field1>: { <accumulator1> : <expression1> },
                //...
            }
        },

        // Stage 4
        {
            $project: {
                // specifications
                "doc.brondata": 0
            }
        },

        // Stage 5
        {
            $addFields: {
                 "doc.brondata": "$brondata", "doc.wasstraat.tables": "$tables", "doc.wasstraat.projects": "$projects" 
            }
        },

        // Stage 6
        {
            $replaceRoot: {
                newRoot: '$doc'
            }
        },

        // Stage 7
        {
            $addFields: {
                "brondata_count": { "$size": "$brondata" }
            
            }
        }
    ],

    // Options
    {

    }

    // Created with Studio 3T, the IDE for MongoDB - https://studio3t.com/

);