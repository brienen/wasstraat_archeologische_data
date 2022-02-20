//db.getCollection("Single_Store").updateMany({'vondstnr': {"$exists": true}, 'projectcd': {"$exists": true}, 'projectcd': {'$in': ['DB34']}}, {'$set': {'vondstkey_met_putnr': true}})
db.getCollection("Single_Store").distinct("brondata.table", {'soort': 'Vondst'})
//db.getCollection("Single_Store").aggregate([
//[ 
//    { '$match': { 'soort': "Vondst" } },
//    { '$addFields': {'key': { '$concat': [ "P", "$projectcd", 
//        {"$cond": ["$vondstkey_met_putnr", {'$concat': ["P", {'$toString': "$putnr" }]}, ""]},
//            {'$concat': ["V", {'$toString': "$vondstnr" }]}]}}},
//    { '$addFields': {'key_vlak': { '$concat': [ "P", "$projectcd", 
//        {'$ifNull': [{'$concat': ["P", {'$toString': "$putnr" }]}, ""]},
//            {'$concat': ["V", {'$toString': "$vlaknr"}]}] }}},  		
//    { '$addFields': {'key_put': { '$concat': [ "P", "$projectcd", {'$concat': ["P", {'$toString': "$putnr" }]}] }}},
//    { '$addFields': {'key_project': { '$concat': [ "P", "$projectcd"]}}}
//

//{'$match': {'soort': 'Vondst'}}, {'$addFields': {'key': {'$concat': ['P', '$projectcd', {'$cond': ['$vondstkey_met_putnr', {'$concat': ['P', {'$toString': '$putnr'}]}, '']}, {'$concat': ['V', {'$toString': '$vondstnr'}]}]}}}, {'$addFields': {'key_vlak': {'$concat': ['P', '$projectcd', {'$ifNull': [{'$concat': ['P', {'$toString': '$putnr'}]}, '']}, {'$concat': ['V', {'$toString': '$vlaknr'}]}]}}}, {'$addFields': {'key_put': {'$concat': ['P', '$projectcd', {'$concat': ['P', {'$toString': '$putnr'}]}]}}}, {'$addFields': {'key_project': {'$concat': ['P', '$projectcd']}}}
//]
//)