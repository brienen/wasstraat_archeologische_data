db.getCollection("Staging_Projecten_Oud").aggregate(

    // Pipeline
    [
        // Stage 1
        {
            $match: {
                // enter query here
                'table': 'VONDST'
            }
        },

        // Stage 2
        {
            $replaceRoot: {
                'newRoot': {'_id': '$_id', 'brondata': ['$$ROOT']}
            }
        },

        // Stage 3
        {
            $addFields: {
             'stelling': '$brondata.0.stelling', 'inhoud': '$brondata.0.inhoud', 'table': '$brondata.0.table', 'soort': 'stelling', 'putnr': {'$ifNull': ['$brondata.0.VERZMWIJZE', '$brondata.0.OPMERKING']}
            }
        }
    ],

    // Options
    {

    }

    // Created with Studio 3T, the IDE for MongoDB - https://studio3t.com/

);