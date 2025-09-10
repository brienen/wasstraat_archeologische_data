#!/bin/bash

mdbfile="/input/projecten/Poppesteeg/C Database/Poppesteeg nieuw/poppesteeg.mdb"

PROJECT_R=${mdbfile#$1"/"}
echo "$PROJECT_R"
PROJECT_L=${PROJECT_R%%/*}
echo "$PROJECT_L"
[[ $PROJECT_L =~ ^([A-Z0-9]+).* ]] && PROJECT=${BASH_REMATCH[1]}
echo "$PROJECT"
#PROJECT=${mdbfile%.mdb}
#PROJECT=${PROJECT##*\/} 
#PROJECT=${PROJECT##*opgraving} 
echo "Processing $mdbfile file for project $PROJECT ..."
  