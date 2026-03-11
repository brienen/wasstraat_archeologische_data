#!/bin/bash
#
# Integratietests voor importMDB.sh
# Test de volledige verwerkingspipeline met gesimuleerde data:
#   - Encoding conversie + teller
#   - Dubbele kolomnamen in CSV
#   - Metainfo JSON generatie
#   - Encoding-rapport correctheid
#
# Gebruik:
#   bash tests/integration/test_importMDB_pipeline.sh
#
# Vereisten: python3, iconv, file (standaard Linux-tools)
#

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
IMPORT_SCRIPT="$PROJECT_ROOT/airflow_app/scripts/importMDB.sh"
TMPDIR=$(mktemp -d)
ERRORLOG="$TMPDIR/errors.log"
touch "$ERRORLOG"
PASSED=0
FAILED=0

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

pass() {
    PASSED=$((PASSED + 1))
    echo -e "  ${GREEN}PASS${NC}  $1"
}

fail() {
    FAILED=$((FAILED + 1))
    echo -e "  ${RED}FAIL${NC}  $1: $2"
}

# Extraheer alle functies uit importMDB.sh
extract_functions() {
    python3 -c "
import re

with open('$IMPORT_SCRIPT', 'r') as f:
    content = f.read()

funcs = ['convert_to_utf8', 'fix_duplicate_csv_headers', 'generate_metainfo_json']
result = []

for func_name in funcs:
    pattern = func_name + '()'
    try:
        start = content.index(pattern)
    except ValueError:
        continue
    if func_name == 'convert_to_utf8':
        pre_start = content.rfind('ENCODING_WAS_CONVERTED=0', 0, start)
        if pre_start >= 0:
            start = pre_start
    brace = 0
    in_func = False
    end = start
    for i, c in enumerate(content[start:]):
        if c == '{':
            brace += 1
            in_func = True
        elif c == '}':
            brace -= 1
            if in_func and brace == 0:
                end = start + i + 1
                break
    result.append(content[start:end])

print('\n'.join(result))
"
}

FUNC_TEXT=$(extract_functions)

echo ""
echo "============================================================"
echo "  Integratietests - importMDB.sh pipeline"
echo "============================================================"

# ================================================================
# Test I1: Volledige encoding + duplicate-header pipeline
# ================================================================
echo ""
echo -e "${YELLOW}--- I1: Encoding + duplicate headers pipeline ---${NC}"

# Maak een CSV met non-UTF-8 encoding EN dubbele kolomnamen
TEST_CSV="$TMPDIR/i1.csv"
printf '"FORMAAT IN MM","kleur","FORMAAT IN MM"\n10,r\xf6d,20\n15,gr\xfcn,25\n' > "$TEST_CSV"

RESULT=$(bash -c "
ERRORLOG=\"$ERRORLOG\"
$FUNC_TEXT

TOTAL_TABLES_ENCODING_FIXED=0

# Stap 1: encoding conversie
convert_to_utf8 \"$TEST_CSV\" \"test_i1\"
if [ \"\$ENCODING_WAS_CONVERTED\" -eq 1 ]; then
    TOTAL_TABLES_ENCODING_FIXED=\$((TOTAL_TABLES_ENCODING_FIXED + 1))
fi

# Stap 2: fix duplicate headers
fix_duplicate_csv_headers \"$TEST_CSV\"

# Output: encoding_teller|utf8_valid|has_renamed_header|data_intact
UTF8_VALID=\$(iconv -f UTF-8 -t UTF-8 \"$TEST_CSV\" > /dev/null 2>&1 && echo yes || echo no)
HAS_RENAMED=\$(head -1 \"$TEST_CSV\" | grep -c 'FORMAAT IN MM_2')
DATA_LINES=\$(tail -n +2 \"$TEST_CSV\" | wc -l | tr -d ' ')
echo \"\$TOTAL_TABLES_ENCODING_FIXED|\$UTF8_VALID|\$HAS_RENAMED|\$DATA_LINES\"
" 2>/dev/null | tail -1)

IFS='|' read -r ENC_COUNT UTF8_OK RENAMED DLINES <<< "$RESULT"

if [ "$ENC_COUNT" = "1" ]; then
    pass "I1a: Encoding-teller correct opgehoogd"
else
    fail "I1a: Encoding-teller" "verwacht 1, kreeg '$ENC_COUNT'"
fi

if [ "$UTF8_OK" = "yes" ]; then
    pass "I1b: Resultaat is geldig UTF-8"
else
    fail "I1b: UTF-8 validatie" "resultaat is geen geldig UTF-8"
fi

if [ "$RENAMED" = "1" ]; then
    pass "I1c: Dubbele kolom hernoemd"
else
    fail "I1c: Dubbele kolom" "geen _2 suffix gevonden"
fi

if [ "$DLINES" = "2" ]; then
    pass "I1d: Data-regels intact (2 regels)"
else
    fail "I1d: Data-regels" "verwacht 2, kreeg '$DLINES'"
fi


# ================================================================
# Test I2: Meerdere tabellen met gemixte encodings -> rapport
# ================================================================
echo ""
echo -e "${YELLOW}--- I2: Encoding-rapport over meerdere tabellen ---${NC}"

RESULT=$(bash -c "
ERRORLOG=\"$ERRORLOG\"
$FUNC_TEXT

TOTAL_TABLES_ENCODING_FIXED=0

# Tabel 1: al UTF-8
FILE1=\"$TMPDIR/i2_utf8.csv\"
printf 'naam\nCafé\n' > \"\$FILE1\"
convert_to_utf8 \"\$FILE1\" \"utf8_tabel\"
[ \"\$ENCODING_WAS_CONVERTED\" -eq 1 ] && TOTAL_TABLES_ENCODING_FIXED=\$((TOTAL_TABLES_ENCODING_FIXED + 1))

# Tabel 2: Windows-1252
FILE2=\"$TMPDIR/i2_win.csv\"
printf 'naam\nDelft\x92s\n' > \"\$FILE2\"
convert_to_utf8 \"\$FILE2\" \"win1252_tabel\"
[ \"\$ENCODING_WAS_CONVERTED\" -eq 1 ] && TOTAL_TABLES_ENCODING_FIXED=\$((TOTAL_TABLES_ENCODING_FIXED + 1))

# Tabel 3: Latin-1
FILE3=\"$TMPDIR/i2_lat.csv\"
printf 'naam\nPr\xe9historisch\n' > \"\$FILE3\"
convert_to_utf8 \"\$FILE3\" \"latin1_tabel\"
[ \"\$ENCODING_WAS_CONVERTED\" -eq 1 ] && TOTAL_TABLES_ENCODING_FIXED=\$((TOTAL_TABLES_ENCODING_FIXED + 1))

# Tabel 4: al UTF-8
FILE4=\"$TMPDIR/i2_ascii.csv\"
printf 'naam\nTest\n' > \"\$FILE4\"
convert_to_utf8 \"\$FILE4\" \"ascii_tabel\"
[ \"\$ENCODING_WAS_CONVERTED\" -eq 1 ] && TOTAL_TABLES_ENCODING_FIXED=\$((TOTAL_TABLES_ENCODING_FIXED + 1))

echo \"\$TOTAL_TABLES_ENCODING_FIXED\"
" 2>/dev/null | tail -1)

if [ "$RESULT" = "2" ]; then
    pass "I2: Encoding-rapport telt precies 2 conversies van 4 tabellen"
else
    fail "I2: Encoding-rapport" "verwacht 2 conversies, kreeg '$RESULT'"
fi


# ================================================================
# Test I3: Metainfo JSON met encoding-problematische input
# ================================================================
echo ""
echo -e "${YELLOW}--- I3: Metainfo JSON met encoding-problematische input ---${NC}"

# Mock mdb-prop met non-ASCII output
MDB_PROP_MOCK="$TMPDIR/mdb-prop"
cat > "$MDB_PROP_MOCK" << 'MOCKEOF'
#!/bin/bash
# Simuleer mdb-prop output met problematische tekens
cat << 'EOF'
name: MÜNZEN_TABELLE
type: TABLE
Description: Münzen und Penningen
GUID: {some-guid-here}
number_of_columns: 3
ColumnWidth: 80
   innerdata: verborgen
ColumnHidden: true
DatasheetFontItalic: True
skip_this_too: ja
Validation: Café > "test" \ 123
EOF
MOCKEOF
chmod +x "$MDB_PROP_MOCK"

OUTPUT="$TMPDIR/i3.json"
bash -c "
export PATH=\"$TMPDIR:\$PATH\"
ERRORLOG=\"$ERRORLOG\"
$FUNC_TEXT
generate_metainfo_json 'dummy.mdb' 'MÜNZEN' 'DB055' '99' '$OUTPUT'
convert_to_utf8 '$OUTPUT' 'metainfo test'
" 2>/dev/null

# Check 1: Geldig JSON
if python3 -c "import json; json.load(open('$OUTPUT'))" 2>/dev/null; then
    pass "I3a: Metainfo met speciale tekens -> geldig JSON"
else
    fail "I3a: Geldig JSON" "output: $(cat "$OUTPUT")"
fi

# Check 2: Geldig UTF-8
if iconv -f UTF-8 -t UTF-8 "$OUTPUT" > /dev/null 2>&1; then
    pass "I3b: Metainfo JSON is geldig UTF-8"
else
    fail "I3b: UTF-8" "output is geen geldig UTF-8"
fi

# Check 3: Gefilterde velden
FILTERED=$(python3 -c "
import json
d = json.load(open('$OUTPUT'))
bad = [k for k in d if k in ('GUID', 'ColumnWidth', 'innerdata', 'ColumnHidden', 'DatasheetFontItalic', 'skip_this_too')]
print(','.join(bad) if bad else 'OK')
" 2>/dev/null)
if [ "$FILTERED" = "OK" ]; then
    pass "I3c: Alle probleemvelden correct gefilterd"
else
    fail "I3c: Filtering" "velden nog aanwezig: $FILTERED"
fi

# Check 4: Bewaard veld met speciale tekens (Description bevat Münzen, Validation bevat Café)
DESC=$(python3 -c "import json; d=json.load(open('$OUTPUT')); print(d.get('Description',''))" 2>/dev/null)
VAL=$(python3 -c "import json; d=json.load(open('$OUTPUT')); print(d.get('Validation',''))" 2>/dev/null)
if echo "$DESC" | grep -q "Münzen" && echo "$VAL" | grep -q "Café"; then
    pass "I3d: Velden met speciale tekens (Münzen, Café) bewaard"
else
    fail "I3d: Speciale tekens" "Description='$DESC', Validation='$VAL'"
fi


# ================================================================
# Test I4: Grotere CSV met meerdere dubbele kolommen + encoding
# ================================================================
echo ""
echo -e "${YELLOW}--- I4: Realistische CSV (20 kolommen, duplicaten, encoding) ---${NC}"

TEST_CSV="$TMPDIR/i4.csv"
# Header met duplicaten
printf '"nr","FORMAAT IN MM","kleur","gewicht","FORMAAT IN MM","materiaal","datering","FORMAAT IN MM","opmerking","vondstnr"\n' > "$TEST_CSV"
# 10 data-regels met non-UTF-8 tekens
for i in $(seq 1 10); do
    printf "$i,10,r\xf6d,5.2,20,\"Aardewerk\",\"1200-1500\",30,\"caf\xe9\",V$i\n" >> "$TEST_CSV"
done

RESULT=$(bash -c "
ERRORLOG=\"$ERRORLOG\"
$FUNC_TEXT

convert_to_utf8 \"$TEST_CSV\" \"i4_test\"
fix_duplicate_csv_headers \"$TEST_CSV\"

# Controleer resultaten
HEADER=\$(head -1 \"$TEST_CSV\")
UTF8_OK=\$(iconv -f UTF-8 -t UTF-8 \"$TEST_CSV\" > /dev/null 2>&1 && echo yes || echo no)
DATA_LINES=\$(tail -n +2 \"$TEST_CSV\" | wc -l | tr -d ' ')
HAS_2=\$(echo \"\$HEADER\" | grep -c 'FORMAAT IN MM_2')
HAS_3=\$(echo \"\$HEADER\" | grep -c 'FORMAAT IN MM_3')
echo \"\$UTF8_OK|\$DATA_LINES|\$HAS_2|\$HAS_3\"
" 2>/dev/null | tail -1)

IFS='|' read -r UTF8 LINES HAS2 HAS3 <<< "$RESULT"

if [ "$UTF8" = "yes" ] && [ "$LINES" = "10" ] && [ "$HAS2" = "1" ] && [ "$HAS3" = "1" ]; then
    pass "I4: Realistische CSV correct verwerkt (UTF-8, 10 regels, _2 en _3 suffix)"
else
    fail "I4: Realistische CSV" "utf8=$UTF8, lines=$LINES, has_2=$HAS2, has_3=$HAS3"
fi


# ================================================================
# Test I5: Edge case - lege CSV (alleen header)
# ================================================================
echo ""
echo -e "${YELLOW}--- I5: Edge cases ---${NC}"

TEST_CSV="$TMPDIR/i5.csv"
printf 'naam,naam\n' > "$TEST_CSV"
bash -c "
$FUNC_TEXT
fix_duplicate_csv_headers \"$TEST_CSV\"
" 2>/dev/null
HEADER=$(head -1 "$TEST_CSV")
if echo "$HEADER" | grep -q "naam_2"; then
    pass "I5a: Lege CSV (alleen header) met duplicaat correct afgehandeld"
else
    fail "I5a: Lege CSV" "header: $HEADER"
fi

# Test I5b: CSV met alleen 1 kolom (geen komma's)
TEST_CSV="$TMPDIR/i5b.csv"
printf 'vondstnr\n1\n2\n' > "$TEST_CSV"
BEFORE=$(md5sum "$TEST_CSV" | cut -d' ' -f1)
bash -c "
$FUNC_TEXT
fix_duplicate_csv_headers \"$TEST_CSV\"
" 2>/dev/null
AFTER=$(md5sum "$TEST_CSV" | cut -d' ' -f1)
if [ "$BEFORE" = "$AFTER" ]; then
    pass "I5b: CSV met 1 kolom ongewijzigd"
else
    fail "I5b: CSV met 1 kolom" "bestand is gewijzigd"
fi


# Opruimen
rm -rf "$TMPDIR"

# Rapport
echo ""
echo "============================================================"
TOTAL=$((PASSED + FAILED))
if [ $FAILED -eq 0 ]; then
    echo -e "  ${GREEN}ALL $PASSED TESTS PASSED${NC}"
else
    echo -e "  $PASSED passed, ${RED}$FAILED failed${NC} (total: $TOTAL)"
fi
echo "============================================================"
echo ""

exit $FAILED
