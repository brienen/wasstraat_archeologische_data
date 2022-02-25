db.getCollection("Single_Store").aggregate(

    // Pipeline
    [
        // Stage 1
        {
            $match: {
                // enter query here
                "soort": "Vondst"
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
                '_id': '$key',
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
        }
    ],

    // Options
    {

    }

    // Created with Studio 3T, the IDE for MongoDB - https://studio3t.com/

);