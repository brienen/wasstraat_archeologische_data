#!/bin/bash

if [ $# -ne 2 ] && [ $# -ne 3 ]
then
    echo "Aanroepen met Dir en Collection, optioneel gevolgd door een lijstbestand"
    exit 1
fi

# Optioneel derde argument: lijstbestand met de te verwerken MDB/ACCDB-bestanden,
# één pad per regel (geschreven door Bepaal_Delta van de incrementele cyclus).
# Zonder derde argument worden alle bestanden in de input-directory verwerkt.
LIJSTBESTAND="${3:-}"

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
# Zet ENCODING_WAS_CONVERTED=1 als er daadwerkelijk een conversie plaatsvond.
# Compatibel met zowel GNU (Linux) als BSD (macOS) versies van iconv en grep.
ENCODING_WAS_CONVERTED=0
convert_to_utf8() {
    local INPUT_FILE="$1"
    local CONTEXT="$2"  # voor logging (bijv. "tabel X in bestand Y")
    ENCODING_WAS_CONVERTED=0

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
            ENCODING_WAS_CONVERTED=1
            return 0
        fi
        rm -f "${INPUT_FILE}.utf8"
    fi

    # Stap 4: Fallback naar Windows-1252 (meest voorkomend in NL Access-databases)
    echo "ENCODING: Fallback naar Windows-1252 conversie voor $CONTEXT"
    if _iconv_convert "WINDOWS-1252" "UTF-8//TRANSLIT" "$INPUT_FILE" "${INPUT_FILE}.utf8"; then
        mv "${INPUT_FILE}.utf8" "$INPUT_FILE"
        echo "ENCODING: Succesvol geconverteerd van Windows-1252 (fallback) naar UTF-8 voor $CONTEXT"
        ENCODING_WAS_CONVERTED=1
        return 0
    fi
    rm -f "${INPUT_FILE}.utf8"

    # Stap 5: Laatste redmiddel - ISO-8859-1 (superklasse van Windows-1252, accepteert alle bytes)
    echo "ENCODING: Laatste fallback naar ISO-8859-1 conversie voor $CONTEXT"
    if _iconv_convert "ISO-8859-1" "UTF-8//TRANSLIT" "$INPUT_FILE" "${INPUT_FILE}.utf8"; then
        mv "${INPUT_FILE}.utf8" "$INPUT_FILE"
        echo "ENCODING: Geconverteerd van ISO-8859-1 (noodfallback) naar UTF-8 voor $CONTEXT"
        ENCODING_WAS_CONVERTED=1
        return 0
    fi
    rm -f "${INPUT_FILE}.utf8"

    # Stap 6: Allerlaatste poging - ISO-8859-1 zonder TRANSLIT (macOS kent soms //TRANSLIT niet)
    echo "ENCODING: Laatste poging ISO-8859-1 zonder TRANSLIT voor $CONTEXT"
    if _iconv_convert "ISO-8859-1" "UTF-8" "$INPUT_FILE" "${INPUT_FILE}.utf8"; then
        mv "${INPUT_FILE}.utf8" "$INPUT_FILE"
        echo "ENCODING: Geconverteerd van ISO-8859-1 (zonder TRANSLIT) naar UTF-8 voor $CONTEXT"
        ENCODING_WAS_CONVERTED=1
        return 0
    fi
    rm -f "${INPUT_FILE}.utf8"

    echo "ERROR ENCODING: Alle conversie-pogingen gefaald voor $CONTEXT" | tee -a "$ERRORLOG"
    return 1
}

# Functie: hernoom dubbele CSV-kolomnamen
# mongoimport weigert CSV-bestanden met identieke header-velden.
# Deze functie voegt een suffix _2, _3, ... toe aan duplicaten.
fix_duplicate_csv_headers() {
    local CSV_FILE="$1"
    python3 -c "
import sys, csv, io

with open('$CSV_FILE', 'r', encoding='utf-8', errors='replace') as f:
    first_line = f.readline()

# Parse header met csv-module (respecteert quoting)
reader = csv.reader(io.StringIO(first_line))
headers = next(reader)

# Detecteer en hernoom duplicaten
seen = {}
new_headers = []
changed = False
for h in headers:
    if h in seen:
        seen[h] += 1
        new_headers.append(f'{h}_{seen[h]}')
        changed = True
    else:
        seen[h] = 1
        new_headers.append(h)

if changed:
    dupes = [h for h, c in seen.items() if c > 1]
    print(f'DUPLICATE_HEADERS: Hernoemde dubbele kolommen: {dupes}', file=sys.stderr)
    # Herschrijf alleen de header-regel
    with open('$CSV_FILE', 'r', encoding='utf-8', errors='replace') as f:
        _ = f.readline()  # skip originele header
        rest = f.read()
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(new_headers)
    with open('$CSV_FILE', 'w', encoding='utf-8') as f:
        f.write(out.getvalue())
        f.write(rest)
" 2>&1
}

# Functie: exporteer een Access-tabel naar CSV met een correct gequote kopregel
# mdb-export (1.0.0) zet de kolomnamen in de kopregel niet tussen aanhalingstekens.
# Een kolomnaam met een komma (bijv. "FORMAAT IN MM, HORIZONTAAL") telt dan als
# twee velden, waardoor de kopregel meer velden heeft dan de rijen en mongoimport
# (--headerline) alle waarden verschuift, inclusief de velden die dit script
# achteraan toevoegt (table, projectcd, bron, loadtime, mdbfile).
# Daarom schrijven we de kopregel zelf: de kolomnamen komen tab-gescheiden uit
# mdb-export (kolomnamen bevatten geen tabs) en worden met Python's csv.writer
# gequote waar nodig (komma, aanhalingsteken, newline). De data volgt daaronder
# via mdb-export -H (zonder kopregel), met de gewone quoting van mdb-export.
# Bytes die (nog) geen geldig UTF-8 zijn blijven ongewijzigd (surrogateescape);
# convert_to_utf8 converteert daarna het hele bestand.
# Retourneert 0 bij succes, 1 als er geen kopregel gelezen kon worden
# (het CSV-bestand is dan leeg en wordt verderop als lege tabel overgeslagen).
export_table_to_csv() {
    local MDBFILE="$1"
    local TABLE_NAME="$2"
    local CSV_FILE="$3"

    if ! mdb-export -d $'\t' -Q "$MDBFILE" "$TABLE_NAME" 2>/dev/null | head -1 | python3 -c '
import csv, io, sys

regel = sys.stdin.buffer.read().decode("utf-8", "surrogateescape").rstrip("\r\n")
if not regel:
    sys.exit(1)
uit = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="surrogateescape", newline="")
csv.writer(uit, quoting=csv.QUOTE_MINIMAL, lineterminator="\n").writerow(regel.split("\t"))
uit.flush()
' > "$CSV_FILE"; then
        : > "$CSV_FILE"
        return 1
    fi

    mdb-export -H "$MDBFILE" "$TABLE_NAME" >> "$CSV_FILE"
}

# Functie: maak een waarde geschikt voor de vervangingstekst van sed en als CSV-veld
# De waarden die achter elke CSV-regel worden gezet (tabelnaam, projectcode,
# bron, tijdstempel, pad) staan letterlijk in de vervangingstekst van een
# sed-opdracht s/$/.../. Daarin betekent & "de gevonden tekst", is \ een
# escape-teken en is / het scheidingsteken van de opdracht. De Delftse tabel
# "AARDEWERK 1&2 VOORWERP" werd zo "AARDEWERK 12 VOORWERP".
# Voor de CSV: bevat de waarde een komma of aanhalingsteken, dan komt ze tussen
# dubbele aanhalingstekens en wordt " -> "" (zoals csv.writer met QUOTE_MINIMAL),
# zodat ze geen extra veld oplevert. Andere waarden blijven ongequote, zodat de
# uitvoer voor gewone tabelnamen en paden byte voor byte gelijk blijft.
# Altijd quoten kan niet: sed werkt per regel en zet de waarden ook achter elke
# regel binnen een tekstveld met een regeleinde (bijv. OPGRAVINGEN in de Delftse
# projectenlijst); een " daar breekt de CSV en mongoimport weigert de tabel.
# Daarna voor sed: \ -> \\, & -> \& en / -> \/.
# Een newline in de waarde wordt niet ondersteund (komt in tabelnamen en paden
# niet voor).
escape_sed_csv_value() {
    local WAARDE="$1"
    case "$WAARDE" in
        *[,\"]*) WAARDE="\"$(printf '%s' "$WAARDE" | sed -e 's/"/""/g')\"" ;;
    esac
    printf '%s' "$WAARDE" | sed -e 's/[\/&]/\\&/g'
}

# Functie: genereer metainfo JSON op een robuuste manier
# Vervangt de fragiele sed-pipeline door een Python-script dat altijd
# geldige JSON produceert, zelfs bij onverwachte mdb-prop output.
generate_metainfo_json() {
    local MDBFILE="$1"
    local TABLE="$2"
    local PROJECT="$3"
    local LENGTE="$4"
    local OUTPUT="$5"

    mdb-prop "$MDBFILE" "$TABLE" 2>/dev/null | python3 -c "
import sys, json, re

lines = sys.stdin.read().splitlines()
result = {}
skip_next_line = False   # voor DatasheetFontItalic (sla 1 regel over)
in_colwidth_block = False  # voor ColumnWidth..ColumnHidden blok

for line in lines:
    stripped = line.strip()
    # Skip GUID-regels (encoding-problematisch)
    if stripped.startswith('GUID:'):
        continue
    # Skip DatasheetFontItalic en de regel erna
    if skip_next_line:
        skip_next_line = False
        continue
    if 'DatasheetFontItalic' in stripped:
        skip_next_line = True
        continue
    # Skip ColumnWidth..ColumnHidden blok (inclusief grenzen)
    if in_colwidth_block:
        if 'ColumnHidden' in stripped:
            in_colwidth_block = False
        continue
    if 'ColumnWidth' in stripped:
        in_colwidth_block = True
        continue

    # Parse 'key: value' regels
    m = re.match(r'^[\t ]*([a-zA-Z0-9_]+):\s*(.*)', stripped)
    if m:
        key = m.group(1)
        val = m.group(2).strip()
        result[key] = val

# Voeg extra velden toe
result['table'] = '$TABLE'
result['projectcd'] = '$PROJECT'
result['teller'] = '$LENGTE'

json.dump(result, sys.stdout, ensure_ascii=False, indent=None)
print()  # newline aan het eind
" > "$OUTPUT" 2>/dev/null

    # Controleer of output geldig JSON is
    if [ ! -s "$OUTPUT" ]; then
        # Leeg bestand: maak minimale geldige JSON
        echo "{\"table\": \"$TABLE\", \"projectcd\": \"$PROJECT\", \"teller\": \"$LENGTE\"}" > "$OUTPUT"
        echo "WARNING: mdb-prop gaf geen bruikbare output voor tabel '$TABLE', minimale metainfo gegenereerd"
    fi
}


DB_STAGING_URI=mongodb://${MONGO_INITDB_ROOT_USERNAME}:${MONGO_INITDB_ROOT_PASSWORD}@${MONGO_SERVER}

if [ -n "$LIJSTBESTAND" ]; then
    # Incrementeel: verwerk alleen de paden uit het lijstbestand
    if [ ! -f "$LIJSTBESTAND" ]; then
        echo "ERROR: Lijstbestand '$LIJSTBESTAND' bestaat niet." | tee -a "$ERRORLOG"
        exit 1
    fi
    MDB_FILES=()
    while IFS= read -r REGEL || [ -n "$REGEL" ]; do
        REGEL="${REGEL%$'\r'}"
        [ -z "$REGEL" ] && continue
        if [ ! -f "$REGEL" ]; then
            echo "WARNING: Bestand '$REGEL' uit lijstbestand bestaat niet, overgeslagen." | tee -a "$ERRORLOG"
            continue
        fi
        MDB_FILES+=("$REGEL")
    done < "$LIJSTBESTAND"

    if [ ${#MDB_FILES[@]} -eq 0 ]; then
        echo "INFO: Lijstbestand '$LIJSTBESTAND' bevat geen bestanden, niets te verwerken."
    else
        echo "INFO: ${#MDB_FILES[@]} MDB/ACCDB-bestand(en) uit lijstbestand '$LIJSTBESTAND'."
    fi
else

# Controleer of de input-directory bestaat
if [ ! -d "$1" ]; then
    echo "INFO: Input-directory '$1' bestaat niet, overgeslagen."
    echo ""
    echo "========================================================"
    echo "ENCODING RAPPORT - $(date --iso-8601=seconds)"
    echo "========================================================"
    echo "Input-directory '$1' niet gevonden — geen bestanden verwerkt."
    echo "========================================================"
    exit 0
fi

# Zoek alle MDB/ACCDB-bestanden in de input-directory
shopt -s globstar nullglob
MDB_FILES=("$1"/**/*.mdb "$1"/**/*.accdb)
shopt -u nullglob

# Controleer of er bestanden gevonden zijn
if [ ${#MDB_FILES[@]} -eq 0 ]; then
    echo "INFO: Geen MDB/ACCDB-bestanden gevonden in '$1', overgeslagen."
    echo ""
    echo "========================================================"
    echo "ENCODING RAPPORT - $(date --iso-8601=seconds)"
    echo "========================================================"
    echo "Geen MDB/ACCDB-bestanden in '$1' — geen bestanden verwerkt."
    echo "========================================================"
    exit 0
fi

echo "INFO: ${#MDB_FILES[@]} MDB/ACCDB-bestand(en) gevonden in '$1'."

fi

for mdbfile in "${MDB_FILES[@]}"
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
		# Kopregel zelf schrijven (correct gequote), data via mdb-export -H
		if ! export_table_to_csv "$mdbfile" "$TABLE" "$CSV"; then
			echo "WARNING: Geen kopregel gelezen voor tabel '$TABLE' in bestand '$mdbfile', tabel overgeslagen" | tee -a "$ERRORLOG"
		fi

		# Encoding-conversie van CSV naar gevalideerd UTF-8
		CONTEXT="tabel '$TABLE' in bestand '$mdbfile'"
		if convert_to_utf8 "$CSV" "$CONTEXT"; then
			if [ "$ENCODING_WAS_CONVERTED" -eq 1 ]; then
				TOTAL_TABLES_ENCODING_FIXED=$((TOTAL_TABLES_ENCODING_FIXED + 1))
			fi
		else
			echo "WARNING: CSV encoding-conversie gefaald voor $CONTEXT, probeer toch te importeren" | tee -a "$ERRORLOG"
			TOTAL_TABLES_ENCODING_FAILED=$((TOTAL_TABLES_ENCODING_FAILED + 1))
		fi

		LENGTE=`wc -l < $CSV`
		let LENGTE=$LENGTE-1 # To correct for the header
		echo Length of tabel $CSV in file $mdbfile is: $LENGTE
		if [ $LENGTE -lt 1 ]; then # on empty CSV stop loop and continue to next cycle
			rm "$CSV"
			continue
    	fi

		echo Reading data
		# Voeg de kolommen table, projectcd, bron, loadtime en mdbfile toe: de waarden
		# achter elke datarij (regel 2 en verder), de kolomnamen achter de kopregel.
		# De waarden gaan via escape_sed_csv_value (veilig voor sed; tussen
		# aanhalingstekens als ze een komma of aanhalingsteken bevatten). mongoimport
		# leest gequote en ongequote waarden hetzelfde in (een getal blijft een getal,
		# tekst blijft tekst). De kopregel-sed gebruikt de waarden niet, zodat
		# bijzondere tekens in een tabelnaam of pad hem niet kunnen breken.
		SED_TABLE=$(escape_sed_csv_value "$TABLE")
		SED_PROJECT=$(escape_sed_csv_value "$PROJECT")
		SED_BRON=$(escape_sed_csv_value "opgraving$PROJECT")
		SED_LOADTIME=$(escape_sed_csv_value "$timestamp")
		SED_MDBFILE=$(escape_sed_csv_value "$mdbfile")
		sed -i "1!s/\$/,$SED_TABLE,$SED_PROJECT,$SED_BRON,$SED_LOADTIME,$SED_MDBFILE/" "$CSV"
		sed -i "1s/\$/,table,projectcd,bron,loadtime,mdbfile/" "$CSV"

		# Valideer dat CSV na sed-bewerking nog steeds geldig UTF-8 is
		if ! iconv -f UTF-8 -t UTF-8 "$CSV" > /dev/null 2>&1; then
			echo "WARNING: CSV is na sed-bewerking geen geldig UTF-8 meer voor $CONTEXT" | tee -a "$ERRORLOG"
			# Forceer UTF-8 met TRANSLIT als noodmaatregel
			iconv -f UTF-8 -t UTF-8//IGNORE < "$CSV" > "${CSV}.clean" 2>/dev/null && mv "${CSV}.clean" "$CSV"
		fi

		# Fix dubbele kolomnamen in CSV header (mongoimport weigert identieke velden)
		fix_duplicate_csv_headers "$CSV"

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
		# Genereer metainfo als geldige JSON via Python (vervangt fragiele sed-pipeline)
		generate_metainfo_json "$mdbfile" "$TABLE" "$PROJECT" "$LENGTE" "$METAINFO"

		# Encoding-conversie van metainfo JSON
		convert_to_utf8 "$METAINFO" "metainfo van $CONTEXT"

		mongoimport --host "$MONGO_SERVER" --password "$MONGO_INITDB_ROOT_PASSWORD" --username "$MONGO_INITDB_ROOT_USERNAME" --authenticationDatabase admin --db "$DATABASE"  --collection "$COLL_STAGING_METAINFO" --mode upsert --file "$METAINFO"
		METAINFO_EXIT=$?
		if [ $METAINFO_EXIT -ne 0 ]; then
			echo "WARNING: mongoimport metainfo gefaald (exit $METAINFO_EXIT) voor $CONTEXT" | tee -a "$ERRORLOG"
		fi

	    rm -f "$METAINFO"
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
 



