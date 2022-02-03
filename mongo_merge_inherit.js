// Stages that have been excluded from the aggregation pipeline query
__3tsoftwarelabs_disabled_aggregation_stages = [

    {
        // Stage 4 - excluded
        stage: 4,  source: {
            $match: {
                // enter query here
                "matchsize": {"$gt": 0}
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
                'soort': {"$in": ['Aardewerk', 'Bot', 'Glas', 'Leer', 'Steen', 'Kleipijp', 'Skelet', 'Hout', 'Spijker', 'Muur', 'Keramiek', 'Metaal', 'Munt']}
            }
        },

        // Stage 2
        {
            $lookup: // Equality Match
            {
                from: "Single_Store",
                let: {"key": "$key"},
                pipeline: [
                    {"$match": {"$expr": {"$and": [
                        { "$eq": [ "$soort",  "Artefact" ] }, 
                        { "$eq": [ "$key",  "$$key" ] }]}}}
                ],
                as: "Artefacts"
            }
            
            // Uncorrelated Subqueries
            // (supported as of MongoDB 3.6)
            // {
            //    from: "<collection to join>",
            //    let: { <var_1>: <expression>, …, <var_n>: <expression> },
            //    pipeline: [ <pipeline to execute on the collection to join> ],
            //    as: "<output array field>"
            // }
        },

        // Stage 3
        {
            $addFields: {
                "matchsize": {"$size": "$Artefacts"} //, "_id": {"$ifNull": ["$Artefacts.0._id", "$$ROOT._id"] }
            }
        },

        // Stage 5
        {
            $replaceRoot: {
                newRoot: { $mergeObjects: [ "$$ROOT", { $arrayElemAt: [ "$Artefacts", 0 ]}] }
            }
        },

        // Stage 6
        {
            $addFields: {
                "artefactsoort": "$soort", "soort": "Artefact"
            }
        },

        // Stage 7
        {
            $project: {
                // specifications
                "Artefacts":0, "matchsize":0
            }
        },

        // Stage 8
        {
            $merge: {
                 // The $merge operator must be the last stage in the pipeline
                 into: "Single_Store_Clean",
                 on: "_id",  // optional
                 whenMatched: "replace",
                 whenNotMatched: "insert"                     // optional
            }
        }
    ],

    // Options
    {

    }

    // Created with Studio 3T, the IDE for MongoDB - https://studio3t.com/

);