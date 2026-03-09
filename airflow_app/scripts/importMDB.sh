#!/bin/bash

if [ $# -ne 2 ]
then
    echo "Aanroepen met Dir en Collection"
    exit 1
fi

WORKDIR=$AIRFLOW_TEMPDIR
DATABASE=$DB_STAGING

timestamp=`date --iso-8601=seconds`
Collection="$2"
LOG=${AIRFLOW_LOGDIR}/${Collection}.log
ERRORLOG=${AIRFLOW_LOGDIR}/${Collection}_encoding_errors.log

echo Loading from "$1" to collection "$Collection" in database "$DATABASE" and logging to "$LOG"
# Setting logging to log files, including error log
exec &> >(tee "$LOG") 2>&1
echo Loading from "$1" to collection "$Collection" in database "$DATABASE" and logging to "$LOG"

# ============================================================
# Encoding configuratie voor mdbtools
# Nederlandse Access-databases gebruiken vrijwel altijd Windows-1252.
# MDB_JET3_CHARSET vertelt mdbtools welke broncodering de MDB heeft.
# MDB_ICONV vertelt mdbtools om de output naar UTF-8 te converteren.
# ============================================================
export MDB_JET3_CHARSET="CP1252"
export MDB_ICONV="UTF-8"

# Tellers voor encoding-rapportage
TOTAL_TABLES=0
TOTAL_TABLES_OK=0
TOTAL_TABLES_ENCODING_FIXED=0
TOTAL_TABLES_ENCODING_FAILED=0
TOTAL_FILES=0
TOTAL_FILES_FAILED=0

# Functie: converteer bestand naar gevalideerd UTF-8
# Retourneert 0 bij succes, 1 bij falen
# Compatibel met zowel GNU (Linux) als BSD (macOS) versies van iconv en grep.
convert_to_utf8() {
    local INPUT_FILE="$1"
    local CONTEXT="$2"  # voor logging (bijv. "tabel X in bestand Y")

    # Stap 1: Controleer of het bestand al geldig UTF-8 is
    if iconv -f UTF-8 -t UTF-8 "$INPUT_FILE" > /dev/null 2>&1; then
        return 0  # Al geldig UTF-8, niets te doen
    fi

    echo "ENCODING: Bestand is geen geldig UTF-8, conversie nodig voor $CONTEXT"

    # Stap 2: Detecteer encoding met file-commando
    # NB: grep -oP (Perl regex) bestaat niet op macOS BSD grep, dus we gebruiken sed.
    local DETECTED_ENCODING
    DETECTED_ENCODING=$(file -bi "$INPUT_FILE" 2>/dev/null | sed -n 's/.*charset=\([^ ;]*\).*/\1/p')
    # macOS file -bI (hoofdletter I) als alternatief
    if [ -z "$DETECTED_ENCODING" ]; then
        DETECTED_ENCODING=$(file -bI "$INPUT_FILE" 2>/dev/null | sed -n 's/.*charset=\([^ ;]*\).*/\1/p')
    fi
    echo "ENCODING: Gedetecteerde encoding: '$DETECTED_ENCODING' voor $CONTEXT"

    # Helper: iconv met redirect i.p.v. -o flag (macOS BSD iconv kent geen -o)
    _iconv_convert() {
        local FROM_ENC="$1"
        local TO_ENC="$2"
        local SRC="$3"
        local DST="$4"
        iconv -f "$FROM_ENC" -t "$TO_ENC" < "$SRC" > "$DST" 2>/dev/null
    }

    # Stap 3: Probeer conversie met gedetecteerde encoding
    if [ -n "$DETECTED_ENCODING" ] && [ "$DETECTED_ENCODING" != "binary" ] && [ "$DETECTED_ENCODING" != "unknown-8bit" ]; then
        if _iconv_convert "$DETECTED_ENCODING" "UTF-8//TRANSLIT" "$INPUT_FILE" "${INPUT_FILE}.utf8"; then
            mv "${INPUT_FILE}.utf8" "$INPUT_FILE"
            echo "ENCODING: Succesvol geconverteerd van $DETECTED_ENCODING naar UTF-8 voor $CONTEXT"
            return 0
        fi
        rm -f "${INPUT_FILE}.utf8"
    fi

    # Stap 4: Fallback naar Windows-1252 (meest voorkomend in NL Access-databases)
    echo "ENCODING: Fallback naar Windows-1252 conversie voor $CONTEXT"
    if _iconv_convert "WINDOWS-1252" "UTF-8//TRANSLIT" "$INPUT_FILE" "${INPUT_FILE}.utf8"; then
        mv "${INPUT_FILE}.utf8" "$INPUT_FILE"
        echo "ENCODING: Succesvol geconverteerd van Windows-1252 (fallback) naar UTF-8 voor $CONTEXT"
        return 0
    fi
    rm -f "${INPUT_FILE}.utf8"

    # Stap 5: Laatste redmiddel - ISO-8859-1 (superklasse van Windows-1252, accepteert alle bytes)
    echo "ENCODING: Laatste fallback naar ISO-8859-1 conversie voor $CONTEXT"
    if _iconv_convert "ISO-8859-1" "UTF-8//TRANSLIT" "$INPUT_FILE" "${INPUT_FILE}.utf8"; then
        mv "${INPUT_FILE}.utf8" "$INPUT_FILE"
        echo "ENCODING: Geconverteerd van ISO-8859-1 (noodfallback) naar UTF-8 voor $CONTEXT"
        return 0
    fi
    rm -f "${INPUT_FILE}.utf8"

    # Stap 6: Allerlaatste poging - ISO-8859-1 zonder TRANSLIT (macOS kent soms //TRANSLIT niet)
    echo "ENCODING: Laatste poging ISO-8859-1 zonder TRANSLIT voor $CONTEXT"
    if _iconv_convert "ISO-8859-1" "UTF-8" "$INPUT_FILE" "${INPUT_FILE}.utf8"; then
        mv "${INPUT_FILE}.utf8" "$INPUT_FILE"
        echo "ENCODING: Geconverteerd van ISO-8859-1 (zonder TRANSLIT) naar UTF-8 voor $CONTEXT"
        return 0
    fi
    rm -f "${INPUT_FILE}.utf8"

    echo "ERROR ENCODING: Alle conversie-pogingen gefaald voor $CONTEXT" | tee -a "$ERRORLOG"
    return 1
}


DB_STAGING_URI=mongodb://${MONGO_INITDB_ROOT_USERNAME}:${MONGO_INITDB_ROOT_PASSWORD}@${MONGO_SERVER}
shopt -s globstar
for mdbfile in "$1"/**/*.{mdb,accdb}
do
	TOTAL_FILES=$((TOTAL_FILES + 1))
	PROJECT_R=${mdbfile#$1"/"}
	PROJECT_L=${PROJECT_R%%/*}
	[[ $PROJECT_L =~ ^([A-Z0-9]+).* ]] && PROJECT=${BASH_REMATCH[1]}
    echo "Processing $mdbfile file for project $PROJECT ..."

	# Controleer of het MDB-bestand leesbaar is voordat we tabellen proberen te lezen
	if ! mdb-tables -d , "$mdbfile" > /dev/null 2>&1; then
		echo "ERROR: Kan MDB-bestand niet lezen (mogelijk corrupt of encoding-probleem): $mdbfile" | tee -a "$ERRORLOG"
		TOTAL_FILES_FAILED=$((TOTAL_FILES_FAILED + 1))
		continue
	fi

	IFS=","
  	TABLES=`mdb-tables -d , "$mdbfile"`
	echo "$TABLES"
	for TABLE in $TABLES
	do
		TOTAL_TABLES=$((TOTAL_TABLES + 1))
	   	CSV="$WORKDIR"/opgraving"$PROJECT"."$TABLE".csv
	    echo Reading "$TABLE" into "$CSV" and loading into Mongo database "$DATABASE" collection "$Collection"
	    mdb-export "$mdbfile" "$TABLE" > "$CSV"

		# Encoding-conversie van CSV naar gevalideerd UTF-8
		CONTEXT="tabel '$TABLE' in bestand '$mdbfile'"
		if convert_to_utf8 "$CSV" "$CONTEXT"; then
			if [ $? -eq 0 ]; then
				# Controleer of er een conversie nodig was (functie logt dit al)
				:
			fi
		else
			echo "WARNING: CSV encoding-conversie gefaald voor $CONTEXT, probeer toch te importeren" | tee -a "$ERRORLOG"
			TOTAL_TABLES_ENCODING_FAILED=$((TOTAL_TABLES_ENCODING_FAILED + 1))
		fi

		LENGTE=`wc -l < $CSV`
		let LENGTE=$LENGTE-1 # To correct for the header
		echo Length of tabel $CSV in file $mdbfile is: $LENGTE
		if [ $LENGTE -lt 2 ]; then # on empty CSV stop loop and continue to nect cycle
			rm "$CSV"
			continue
    	fi

		echo Reading data
		sed -i s/$/,"$TABLE","$PROJECT",opgraving"$PROJECT","$timestamp","${mdbfile//\//\\/}"/ "$CSV"
		sed -i 1s/,"$TABLE","$PROJECT",opgraving"$PROJECT","$timestamp","${mdbfile//\//\\/}"/,table,projectcd,bron,loadtime,mdbfile/ "$CSV"

		# Valideer dat CSV na sed-bewerking nog steeds geldig UTF-8 is
		if ! iconv -f UTF-8 -t UTF-8 "$CSV" > /dev/null 2>&1; then
			echo "WARNING: CSV is na sed-bewerking geen geldig UTF-8 meer voor $CONTEXT" | tee -a "$ERRORLOG"
			# Forceer UTF-8 met TRANSLIT als noodmaatregel
			iconv -f UTF-8 -t UTF-8//IGNORE < "$CSV" > "${CSV}.clean" 2>/dev/null && mv "${CSV}.clean" "$CSV"
		fi

		# Import CSV into Mongo
		mongoimport --host "$MONGO_SERVER" --password "$MONGO_INITDB_ROOT_PASSWORD" --username "$MONGO_INITDB_ROOT_USERNAME" --authenticationDatabase admin --db "$DATABASE" --collection "$Collection" --type csv --headerline --ignoreBlanks --mode upsert --file "$CSV"
		IMPORT_EXIT=$?
		if [ $IMPORT_EXIT -ne 0 ]; then
			echo "ERROR: mongoimport gefaald (exit $IMPORT_EXIT) voor $CONTEXT" | tee -a "$ERRORLOG"
		else
			TOTAL_TABLES_OK=$((TOTAL_TABLES_OK + 1))
		fi

		echo Reading metainfo
		METAINFO="$WORKDIR"/"$PROJECT"."$TABLE".meta.json
		# Removing lines with GUID and everything between ColumnWidth and ColumnHidden to overcome encoding problem
		mdb-prop "$mdbfile" "$TABLE" | sed '/GUID:/d' | sed '/DatasheetFontItalic/,+1d' | sed '/ColumnWidth/,/ColumnHidden/{//!d}' | sed -r 's/\\/\\\\/g ' | sed -r 's/\"/\\\"/g '  | sed -r '/name/a table: '"$TABLE"'' | sed -r '/name/a projectcd: '"$PROJECT"'' | sed -r '/name/a teller: '"$LENGTE"'' | sed -r 's/^[\t]*([a-zA-Z0-9]+): (.*)/\"\1\": \"\2\",/' | sed -r 's/^$/}/' | tac | sed '/}/ {n; s/,$//}' | tac | sed -r 's/^\"name/{\"name/' | sed '/\":\|}/!d' > "$METAINFO"

		# Encoding-conversie van metainfo JSON
		convert_to_utf8 "$METAINFO" "metainfo van $CONTEXT"

		mongoimport --host "$MONGO_SERVER" --password "$MONGO_INITDB_ROOT_PASSWORD" --username "$MONGO_INITDB_ROOT_USERNAME" --authenticationDatabase admin --db "$DATABASE"  --collection "$COLL_STAGING_METAINFO" --mode upsert --file "$METAINFO"

	    rm -f "$WORKDIR"/"$TABLE".meta.json
	done
done

# Encoding-rapport
echo ""
echo "========================================================"
echo "ENCODING RAPPORT - $(date --iso-8601=seconds)"
echo "========================================================"
echo "Totaal MDB-bestanden verwerkt:       $TOTAL_FILES"
echo "Totaal MDB-bestanden onleesbaar:     $TOTAL_FILES_FAILED"
echo "Totaal tabellen verwerkt:            $TOTAL_TABLES"
echo "Totaal tabellen succesvol:           $TOTAL_TABLES_OK"
echo "Totaal tabellen encoding-conversie:  $TOTAL_TABLES_ENCODING_FIXED"
echo "Totaal tabellen encoding-gefaald:    $TOTAL_TABLES_ENCODING_FAILED"
echo "========================================================"
if [ $TOTAL_TABLES_ENCODING_FAILED -gt 0 ] || [ $TOTAL_FILES_FAILED -gt 0 ]; then
    echo "WAARSCHUWING: Er waren encoding-problemen. Zie $ERRORLOG voor details."
fi
 



