#!/bin/bash
#
# Unit tests voor de functies in importMDB.sh:
#   1. convert_to_utf8 - encoding conversie + ENCODING_WAS_CONVERTED vlag
#   2. fix_duplicate_csv_headers - dubbele kolomnamen hernoemen
#   3. generate_metainfo_json - robuuste JSON generatie vanuit mdb-prop output
#
# Gebruik:
#   bash tests/unit/test_importMDB_functions.sh
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

# Extraheer functies uit importMDB.sh met Python
extract_functions() {
    python3 -c "
import re

with open('$IMPORT_SCRIPT', 'r') as f:
    content = f.read()

# Extraheer alle top-level functies
funcs = ['convert_to_utf8', 'fix_duplicate_csv_headers', 'generate_metainfo_json']
result = []

for func_name in funcs:
    pattern = func_name + '()'
    try:
        start = content.index(pattern)
    except ValueError:
        continue
    # Zoek naar de bijbehorende sluit-accolade
    # We moeten de ENCODING_WAS_CONVERTED variabele meenemen voor convert_to_utf8
    if func_name == 'convert_to_utf8':
        # Neem de regel 'ENCODING_WAS_CONVERTED=0' mee die er vlak boven staat
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
echo "  Unit Tests - importMDB.sh functies"
echo "============================================================"

# ================================================================
# SECTIE A: convert_to_utf8 + ENCODING_WAS_CONVERTED teller
# ================================================================
echo ""
echo -e "${YELLOW}--- A. convert_to_utf8 + ENCODING_WAS_CONVERTED ---${NC}"

# Test A1: UTF-8 bestand -> geen conversie, vlag blijft 0
TEST_FILE="$TMPDIR/a1.csv"
printf "vondstnr,beschrijving\n1,Café te Delft\n" > "$TEST_FILE"
RESULT=$(bash -c "
ERRORLOG=\"$ERRORLOG\"
$FUNC_TEXT
convert_to_utf8 \"$TEST_FILE\" \"test_a1\"
echo \"\$ENCODING_WAS_CONVERTED\"
" 2>/dev/null | tail -1)
if [ "$RESULT" = "0" ]; then
    pass "A1: UTF-8 bestand -> ENCODING_WAS_CONVERTED=0"
else
    fail "A1: UTF-8 bestand" "verwacht 0, kreeg '$RESULT'"
fi

# Test A2: Non-UTF-8 bestand -> conversie, vlag wordt 1
TEST_FILE="$TMPDIR/a2.csv"
printf "naam\nDelft\x92s centrum\n" > "$TEST_FILE"
RESULT=$(bash -c "
ERRORLOG=\"$ERRORLOG\"
$FUNC_TEXT
convert_to_utf8 \"$TEST_FILE\" \"test_a2\"
echo \"\$ENCODING_WAS_CONVERTED\"
" 2>/dev/null | tail -1)
if [ "$RESULT" = "1" ]; then
    pass "A2: Non-UTF-8 bestand -> ENCODING_WAS_CONVERTED=1"
else
    fail "A2: Non-UTF-8 bestand" "verwacht 1, kreeg '$RESULT'"
fi

# Test A3: Na twee opeenvolgende aanroepen reset de vlag correct
TEST_FILE_A="$TMPDIR/a3a.csv"
TEST_FILE_B="$TMPDIR/a3b.csv"
printf "naam\nDelft\x92s\n" > "$TEST_FILE_A"
printf "naam\nDelft\n" > "$TEST_FILE_B"
RESULT=$(bash -c "
ERRORLOG=\"$ERRORLOG\"
$FUNC_TEXT
convert_to_utf8 \"$TEST_FILE_A\" \"test_a3a\"
FIRST=\"\$ENCODING_WAS_CONVERTED\"
convert_to_utf8 \"$TEST_FILE_B\" \"test_a3b\"
SECOND=\"\$ENCODING_WAS_CONVERTED\"
echo \"\$FIRST \$SECOND\"
" 2>/dev/null | tail -1)
if [ "$RESULT" = "1 0" ]; then
    pass "A3: Vlag reset correct tussen aanroepen (1 -> 0)"
else
    fail "A3: Vlag reset" "verwacht '1 0', kreeg '$RESULT'"
fi


# ================================================================
# SECTIE B: fix_duplicate_csv_headers
# ================================================================
echo ""
echo -e "${YELLOW}--- B. fix_duplicate_csv_headers ---${NC}"

# Test B1: CSV zonder duplicaten -> ongewijzigd
TEST_FILE="$TMPDIR/b1.csv"
printf "vondstnr,materiaal,beschrijving\n1,AW,scherf\n" > "$TEST_FILE"
BEFORE=$(md5sum "$TEST_FILE" | cut -d' ' -f1)
bash -c "
$FUNC_TEXT
fix_duplicate_csv_headers \"$TEST_FILE\"
" 2>/dev/null
AFTER=$(md5sum "$TEST_FILE" | cut -d' ' -f1)
if [ "$BEFORE" = "$AFTER" ]; then
    pass "B1: CSV zonder duplicaten ongewijzigd"
else
    fail "B1: CSV zonder duplicaten" "bestand is onverwacht gewijzigd"
fi

# Test B2: CSV met dubbele kolom -> hernoemen
TEST_FILE="$TMPDIR/b2.csv"
printf '"FORMAAT IN MM","kleur","FORMAAT IN MM"\n10,rood,20\n' > "$TEST_FILE"
bash -c "
$FUNC_TEXT
fix_duplicate_csv_headers \"$TEST_FILE\"
" 2>/dev/null
HEADER=$(head -1 "$TEST_FILE")
if echo "$HEADER" | grep -q "FORMAAT IN MM_2"; then
    pass "B2: Dubbele kolom hernoemd naar _2"
else
    fail "B2: Dubbele kolom" "header is: $HEADER"
fi

# Test B3: Data-regels ongewijzigd na hernoemen
DATA_LINE=$(sed -n '2p' "$TEST_FILE")
if [ "$DATA_LINE" = "10,rood,20" ]; then
    pass "B3: Data-regels intact na hernoemen"
else
    fail "B3: Data-regels" "verwacht '10,rood,20', kreeg '$DATA_LINE'"
fi

# Test B4: Drie keer dezelfde kolom -> _2 en _3
TEST_FILE="$TMPDIR/b4.csv"
printf 'naam,naam,naam\na,b,c\n' > "$TEST_FILE"
bash -c "
$FUNC_TEXT
fix_duplicate_csv_headers \"$TEST_FILE\"
" 2>/dev/null
HEADER=$(head -1 "$TEST_FILE")
if echo "$HEADER" | grep -q "naam" && echo "$HEADER" | grep -q "naam_2" && echo "$HEADER" | grep -q "naam_3"; then
    pass "B4: Drie identieke kolommen -> naam, naam_2, naam_3"
else
    fail "B4: Drie identieke kolommen" "header is: $HEADER"
fi

# Test B5: Kolommen met komma's in quotes
TEST_FILE="$TMPDIR/b5.csv"
printf '"score, totaal","score, totaal","materiaal"\n10,20,AW\n' > "$TEST_FILE"
bash -c "
$FUNC_TEXT
fix_duplicate_csv_headers \"$TEST_FILE\"
" 2>/dev/null
HEADER=$(head -1 "$TEST_FILE")
if echo "$HEADER" | grep -q "score, totaal_2"; then
    pass "B5: Quoted kolommen met komma correct hernoemd"
else
    fail "B5: Quoted kolommen" "header is: $HEADER"
fi


# ================================================================
# SECTIE C: generate_metainfo_json
# ================================================================
echo ""
echo -e "${YELLOW}--- C. generate_metainfo_json ---${NC}"

# Voor deze testen mocken we mdb-prop met een dummy-script
MDB_PROP_MOCK="$TMPDIR/mock_mdb_prop.sh"

# Test C1: Normale mdb-prop output -> geldig JSON
cat > "$MDB_PROP_MOCK" << 'MOCKEOF'
#!/bin/bash
cat << 'EOF'
name: VONDST
type: TABLE
number_of_columns: 5
GUID: {abcd-1234}
ColumnWidth: 100
  inner_stuff: hidden
ColumnHidden: false
Description: Vondstenlijst
EOF
MOCKEOF
chmod +x "$MDB_PROP_MOCK"

OUTPUT="$TMPDIR/c1.json"
# We moeten mdb-prop mocken door het pad te overschrijven
bash -c "
# Overschrijf mdb-prop met mock
mdb_prop_orig=\$(which mdb-prop 2>/dev/null || echo '/usr/bin/mdb-prop')
export PATH=\"$TMPDIR:\$PATH\"
ln -sf \"$MDB_PROP_MOCK\" \"$TMPDIR/mdb-prop\"

$FUNC_TEXT
generate_metainfo_json 'dummy.mdb' 'VONDST' 'DB001' '42' '$OUTPUT'
" 2>/dev/null

# Controleer of output geldig JSON is
if python3 -c "import json; json.load(open('$OUTPUT'))" 2>/dev/null; then
    pass "C1: Normale mdb-prop output -> geldig JSON"
else
    fail "C1: Geldig JSON" "output is: $(cat "$OUTPUT")"
fi

# Test C2: JSON bevat de juiste velden
HAS_TABLE=$(python3 -c "import json; d=json.load(open('$OUTPUT')); print(d.get('table',''))" 2>/dev/null)
HAS_PROJECT=$(python3 -c "import json; d=json.load(open('$OUTPUT')); print(d.get('projectcd',''))" 2>/dev/null)
HAS_TELLER=$(python3 -c "import json; d=json.load(open('$OUTPUT')); print(d.get('teller',''))" 2>/dev/null)
if [ "$HAS_TABLE" = "VONDST" ] && [ "$HAS_PROJECT" = "DB001" ] && [ "$HAS_TELLER" = "42" ]; then
    pass "C2: JSON bevat table, projectcd, teller"
else
    fail "C2: JSON velden" "table=$HAS_TABLE, projectcd=$HAS_PROJECT, teller=$HAS_TELLER"
fi

# Test C3: GUID is gefilterd uit output
HAS_GUID=$(python3 -c "import json; d=json.load(open('$OUTPUT')); print('GUID' in d)" 2>/dev/null)
if [ "$HAS_GUID" = "False" ]; then
    pass "C3: GUID gefilterd uit JSON"
else
    fail "C3: GUID filtering" "GUID zit nog in output"
fi

# Test C4: ColumnWidth/ColumnHidden blok is gefilterd
HAS_CW=$(python3 -c "import json; d=json.load(open('$OUTPUT')); print('ColumnWidth' in d or 'inner_stuff' in d)" 2>/dev/null)
if [ "$HAS_CW" = "False" ]; then
    pass "C4: ColumnWidth/ColumnHidden blok gefilterd"
else
    fail "C4: ColumnWidth filtering" "blok zit nog in output"
fi

# Test C5: Lege mdb-prop output -> minimale JSON
cat > "$MDB_PROP_MOCK" << 'MOCKEOF'
#!/bin/bash
# Geeft niks terug
true
MOCKEOF
chmod +x "$MDB_PROP_MOCK"

OUTPUT="$TMPDIR/c5.json"
bash -c "
export PATH=\"$TMPDIR:\$PATH\"
ln -sf \"$MDB_PROP_MOCK\" \"$TMPDIR/mdb-prop\"
$FUNC_TEXT
generate_metainfo_json 'dummy.mdb' 'LEEG' 'DB099' '0' '$OUTPUT'
" 2>/dev/null

if python3 -c "import json; d=json.load(open('$OUTPUT')); assert d['table']=='LEEG'" 2>/dev/null; then
    pass "C5: Lege mdb-prop output -> minimale geldige JSON"
else
    fail "C5: Lege mdb-prop" "output is: $(cat "$OUTPUT")"
fi

# Test C6: mdb-prop output met speciale tekens (quotes, backslashes)
cat > "$MDB_PROP_MOCK" << 'MOCKEOF'
#!/bin/bash
cat << 'EOF'
name: SPOOR
Description: "Sporen" met \ backslash en "quotes"
type: TABLE
EOF
MOCKEOF
chmod +x "$MDB_PROP_MOCK"

OUTPUT="$TMPDIR/c6.json"
bash -c "
export PATH=\"$TMPDIR:\$PATH\"
ln -sf \"$MDB_PROP_MOCK\" \"$TMPDIR/mdb-prop\"
$FUNC_TEXT
generate_metainfo_json 'dummy.mdb' 'SPOOR' 'DB002' '10' '$OUTPUT'
" 2>/dev/null

if python3 -c "import json; json.load(open('$OUTPUT'))" 2>/dev/null; then
    pass "C6: Speciale tekens (quotes, backslashes) -> geldig JSON"
else
    fail "C6: Speciale tekens" "output is: $(cat "$OUTPUT")"
fi

# Test C7: DatasheetFontItalic-regel en de regel erna worden overgeslagen
cat > "$MDB_PROP_MOCK" << 'MOCKEOF'
#!/bin/bash
cat << 'EOF'
name: TEST
DatasheetFontItalic: True
volgende_regel_skip: ja
type: TABLE
Description: Test tabel
EOF
MOCKEOF
chmod +x "$MDB_PROP_MOCK"

OUTPUT="$TMPDIR/c7.json"
bash -c "
export PATH=\"$TMPDIR:\$PATH\"
ln -sf \"$MDB_PROP_MOCK\" \"$TMPDIR/mdb-prop\"
$FUNC_TEXT
generate_metainfo_json 'dummy.mdb' 'TEST' 'DB003' '5' '$OUTPUT'
" 2>/dev/null

HAS_DSI=$(python3 -c "import json; d=json.load(open('$OUTPUT')); print('DatasheetFontItalic' in d or 'volgende_regel_skip' in d)" 2>/dev/null)
if [ "$HAS_DSI" = "False" ]; then
    pass "C7: DatasheetFontItalic + volgende regel gefilterd"
else
    fail "C7: DatasheetFontItalic" "veld zit nog in output: $(cat "$OUTPUT")"
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
