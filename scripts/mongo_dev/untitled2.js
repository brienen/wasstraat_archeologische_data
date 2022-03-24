db.getCollection("Staging_Projecten_Oud").aggregate(

    // Pipeline
    [
        // Stage 1
        {
            $match: {
                // enter query here
                "table": "ARTEFACT"
            }
        },

        // Stage 2
        {
            $lookup: // Equality Match
            {
                from: "Arch_Analyse.Single_Store",
                localField: "ARTEFACT",
                foreignField: "ARTEFACT",
                as: "artfs"
            }
            
            // Uncorrelated Subqueries
            // (supported as of MongoDB 3.6)
            // {
            //    from: "<collection to join>",
            //    let: { <var_1>: <expression>, …, <var_n>: <expression> },
            //    pipeline: [ <pipeline to execute on the collection to join> ],
            //    as: "<output array field>"
            // }
        }
    ],

    // Options
    {

    }

    // Created with Studio 3T, the IDE for MongoDB - https://studio3t.com/

);