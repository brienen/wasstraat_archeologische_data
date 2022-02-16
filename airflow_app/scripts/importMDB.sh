#!/bin/bash

if [ $# -ne 2 ]
then
    echo "Aanroepen met Dir en Collection"
    exit 1
fi

WORKDIR=$AIRFLOW_TEMPDIR
DATABASE=$DB_STAGING

#timestamp=`date --rfc-3339=seconds`
timestamp=`date --iso-8601=seconds`
#FILES="$1"/*.mdb
#FILES="$(find "$1" -name *.mdb)"
Collection="$2"
LOG=${AIRFLOW_LOGDIR}/${Collection}.log

echo Loading from "$1" to collection "$Collection" in database "$DATABASE" and logging to "$LOG" 
# Setting logging to log files, including error log
exec &> >(tee "$LOG") 2>&1
echo Loading from "$1" to collection "$Collection" in database "$DATABASE" and logging to "$LOG" 


DB_STAGING_URI=mongodb://${MONGO_INITDB_ROOT_USERNAME}:${MONGO_INITDB_ROOT_PASSWORD}@${MONGO_SERVER}
shopt -s globstar
for mdbfile in "$1"/**/*.mdb
#for mdbfile in $FILES
do
	PROJECT=${mdbfile%.mdb}
	PROJECT=${PROJECT##*\/} 
	PROJECT=${PROJECT##*opgraving} 
    echo "Processing $mdbfile file for project $PROJECT ..."
  

	IFS=","
  	TABLES=`mdb-tables -d, "$mdbfile"`
	echo "$TABLES"
	for TABLE in $TABLES
	do
	   	CSV="$WORKDIR"/opgraving"$PROJECT"."$TABLE".csv
	    echo Reading "$TABLE" into "$CSV" and loading into Mongo database "$DATABASE" collection "$Collection"
	    mdb-export "$mdbfile" "$CSV" "$TABLE" > "$CSV"  		
		LENGTE=`wc -l < $CSV`
		let LENGTE=$LENGTE-1 # To correct for the header 
		echo Length of tabel $CSV in file $mdbfile is: $LENGTE
		if [ $LENGTE -lt 2 ]; then # on empty CSV stop loop and continue to nect cycle
			rm "$CSV"
			continue
    	fi

		echo Reading data 
		sed -i s/$/,"$TABLE","$PROJECT",opgraving"$PROJECT","$timestamp"/ "$CSV"
		sed -i 1s/,"$TABLE","$PROJECT",opgraving"$PROJECT","$timestamp"/,table,project,bron,loadtime/ "$CSV"

		# Remove Duplicate Columns https://stackoverflow.com/questions/15854720/deleting-duplicate-columns-from-csv-file
		#awk -F, 'NR==1{for(i=1;i<=NF;i++)if(!($i in v)){ v[$i];t[i]}}{s=""; for(i=1;i<=NF;i++)if(i in t)s=s sprintf("%s,",$i);if(s){sub(/,$/,"",s);print s}} ' "$CSV"
		# Import CSV into Mongo
		mongoimport --host "$MONGO_SERVER" --password "$MONGO_INITDB_ROOT_PASSWORD" --username "$MONGO_INITDB_ROOT_USERNAME" --authenticationDatabase admin --db "$DATABASE" --collection "$Collection" --type csv --headerline --ignoreBlanks --mode upsert --file "$CSV"
		
		echo Reading metainfo
		METAINFO="$WORKDIR"/"$PROJECT"."$TABLE".meta.json
		# Removing lines with GUID and everythimng bnetween ColumnWidth  and ColumnHidden to overcome encoding problem
		mdb-prop "$mdbfile" "$TABLE" | sed '/GUID:/d' | sed '/DatasheetFontItalic/,+1d' | sed '/ColumnWidth/,/ColumnHidden/{//!d}' | sed -r 's/\\/\\\\/g ' | sed -r 's/\"/\\\"/g '  | sed -r '/name/a table: '"$TABLE"'' | sed -r '/name/a project: '"$PROJECT"'' | sed -r '/name/a teller: '"$LENGTE"'' | sed -r 's/^[\t]*([a-zA-Z0-9]+): (.*)/\"\1\": \"\2\",/' | sed -r 's/^$/}/' | tac | sed '/}/ {n; s/,$//}' | tac | sed -r 's/^\"name/{\"name/' | sed '/\":\|}/!d' > "$METAINFO"
		#ENCODING=`file -bi "$METAINFO" | awk -F'=' '{print $2 }'`
		#echo Encoding is "$ENCODING" for file "$METAINFO"
		#Setting encoding does not seem to ix errors
		#iconv -f "$ENCODING" -t utf-8 -c < "$METAINFO" > "$METAINFO"Encoded
		# Might use | sed '/\":\|}/!d' to fix unreadable chars

		mongoimport --host "$MONGO_SERVER" --password "$MONGO_INITDB_ROOT_PASSWORD" --username "$MONGO_INITDB_ROOT_USERNAME" --authenticationDatabase admin --db "$DATABASE"  --collection "$COLL_STAGING_METAINFO" --mode upsert --file "$METAINFO"

		# rm "$CSV"
	    # rm "$WORKDIR"/"$TABLE".meta.json
	done
done
 



