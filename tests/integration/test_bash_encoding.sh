#!/bin/bash
#
# Integratietests voor de convert_to_utf8 functie in importMDB.sh
#
# Gebruik:
#   bash tests/integration/test_bash_encoding.sh
#
# Deze tests creeren tijdelijke bestanden met bekende encodings
# en verifieren dat convert_to_utf8 ze correct naar UTF-8 converteert.
#

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
IMPORT_SCRIPT="$PROJECT_ROOT/airflow_app/scripts/importMDB.sh"
TMPDIR=$(mktemp -d)
ERRORLOG="$TMPDIR/errors.log"
PASSED=0
FAILED=0

# Kleur-output (als terminal dit ondersteunt)
RED='\033[0;31m'
GREEN='\033[0;32m'
NC='\033[0m' # No Color

pass() {
    PASSED=$((PASSED + 1))
    echo -e "  ${GREEN}PASS${NC}  $1"
}

fail() {
    FAILED=$((FAILED + 1))
    echo -e "  ${RED}FAIL${NC}  $1: $2"
}

# Extraheer de convert_to_utf8 functie uit importMDB.sh
# We gebruiken sed om alles van "convert_to_utf8()" tot de bijbehorende "}" te extraheren
extract_function() {
    # Gebruik python voor betrouwbare extractie van de functie
    python3 -c "
import re
with open('$IMPORT_SCRIPT', 'r') as f:
    content = f.read()
start = content.index('convert_to_utf8() {')
brace = 0
end = start
for i, c in enumerate(content[start:]):
    if c == '{': brace += 1
    elif c == '}':
        brace -= 1
        if brace == 0:
            end = start + i + 1
            break
print(content[start:end])
"
}

FUNC_TEXT=$(extract_function)

# Helper: maak een test-script dat de functie aanroept
run_convert() {
    local INPUT_FILE="$1"
    local CONTEXT="$2"

    bash -c "
ERRORLOG=\"$ERRORLOG\"
$FUNC_TEXT
convert_to_utf8 \"$INPUT_FILE\" \"$CONTEXT\"
" 2>&1
    return ${PIPESTATUS[0]}
}


echo ""
echo "=========================================="
echo "  Bash Encoding Tests - convert_to_utf8"
echo "=========================================="
echo ""

# --- Test 1: Geldig UTF-8 bestand blijft ongewijzigd ---
TEST_FILE="$TMPDIR/test1.csv"
printf "vondstnr,beschrijving\n1,Caf\xc3\xa9 te Delft\n" > "$TEST_FILE"
BEFORE=$(md5sum "$TEST_FILE" | cut -d' ' -f1)
run_convert "$TEST_FILE" "test1_utf8" > /dev/null 2>&1
AFTER=$(md5sum "$TEST_FILE" | cut -d' ' -f1)
if [ "$BEFORE" == "$AFTER" ]; then
    pass "UTF-8 bestand ongewijzigd"
else
    fail "UTF-8 bestand ongewijzigd" "bestand is gewijzigd terwijl het al geldig UTF-8 was"
fi

# --- Test 2: Windows-1252 bestand wordt geconverteerd ---
TEST_FILE="$TMPDIR/test2.csv"
printf "naam\nDelft\x92s centrum\n" > "$TEST_FILE"
run_convert "$TEST_FILE" "test2_win1252" > /dev/null 2>&1
# Controleer of resultaat geldig UTF-8 is
if iconv -f UTF-8 -t UTF-8 "$TEST_FILE" > /dev/null 2>&1; then
    pass "Windows-1252 -> UTF-8 conversie"
else
    fail "Windows-1252 -> UTF-8 conversie" "resultaat is geen geldig UTF-8"
fi

# --- Test 3: Latin-1 bestand wordt geconverteerd ---
TEST_FILE="$TMPDIR/test3.csv"
printf "naam\nPr\xe9historisch\n" > "$TEST_FILE"
run_convert "$TEST_FILE" "test3_latin1" > /dev/null 2>&1
if iconv -f UTF-8 -t UTF-8 "$TEST_FILE" > /dev/null 2>&1; then
    pass "Latin-1 -> UTF-8 conversie"
else
    fail "Latin-1 -> UTF-8 conversie" "resultaat is geen geldig UTF-8"
fi

# --- Test 4: Pure ASCII bestand ---
TEST_FILE="$TMPDIR/test4.csv"
printf "vondstnr,materiaal\n1,Aardewerk\n2,Glas\n" > "$TEST_FILE"
run_convert "$TEST_FILE" "test4_ascii" > /dev/null 2>&1
CONTENT=$(cat "$TEST_FILE")
if echo "$CONTENT" | grep -q "Aardewerk"; then
    pass "ASCII bestand intact"
else
    fail "ASCII bestand intact" "inhoud is veranderd"
fi

# --- Test 5: CSV met diverse Windows-1252 tekens ---
TEST_FILE="$TMPDIR/test5.csv"
# \xe9 = e-accent, \xfc = u-umlaut, \x92 = apostrof, \x96 = en-dash
printf "naam,datering\nCaf\xe9,1200\x961500\nDelft\x92s,M\xfcnster\n" > "$TEST_FILE"
run_convert "$TEST_FILE" "test5_diverse" > /dev/null 2>&1
if iconv -f UTF-8 -t UTF-8 "$TEST_FILE" > /dev/null 2>&1; then
    # Extra check: bestand heeft nog steeds 3 regels
    LINES=$(wc -l < "$TEST_FILE")
    if [ "$LINES" -eq 3 ]; then
        pass "Diverse Win-1252 tekens geconverteerd (3 regels intact)"
    else
        fail "Diverse Win-1252 tekens" "verwacht 3 regels, kreeg $LINES"
    fi
else
    fail "Diverse Win-1252 tekens" "resultaat is geen geldig UTF-8"
fi

# --- Test 6: Leeg bestand ---
TEST_FILE="$TMPDIR/test6.csv"
touch "$TEST_FILE"
run_convert "$TEST_FILE" "test6_empty" > /dev/null 2>&1
if [ -f "$TEST_FILE" ]; then
    pass "Leeg bestand zonder crash"
else
    fail "Leeg bestand" "bestand is verdwenen"
fi

# --- Test 7: Groot bestand met herhaalde patronen ---
TEST_FILE="$TMPDIR/test7.csv"
printf "nr,beschrijving\n" > "$TEST_FILE"
for i in $(seq 1 100); do
    printf "$i,\"Caf\xe9 nummer $i in Delft\x92s centrum\"\n" >> "$TEST_FILE"
done
run_convert "$TEST_FILE" "test7_large" > /dev/null 2>&1
if iconv -f UTF-8 -t UTF-8 "$TEST_FILE" > /dev/null 2>&1; then
    LINES=$(wc -l < "$TEST_FILE")
    if [ "$LINES" -eq 101 ]; then
        pass "Groot bestand (100 rijen) correct geconverteerd"
    else
        fail "Groot bestand" "verwacht 101 regels, kreeg $LINES"
    fi
else
    fail "Groot bestand" "resultaat is geen geldig UTF-8"
fi

# --- Test 8: Bestand met BOM (Byte Order Mark) ---
TEST_FILE="$TMPDIR/test8.csv"
printf "\xef\xbb\xbfnaam,waarde\ntest,123\n" > "$TEST_FILE"
run_convert "$TEST_FILE" "test8_bom" > /dev/null 2>&1
if iconv -f UTF-8 -t UTF-8 "$TEST_FILE" > /dev/null 2>&1; then
    pass "UTF-8 met BOM verwerkt"
else
    fail "UTF-8 met BOM" "resultaat is geen geldig UTF-8"
fi

# --- Test 9: Controleer dat TRANSLIT werkt (speciale tekens worden benaderd) ---
TEST_FILE="$TMPDIR/test9.csv"
# \xa9 = copyright sign in Latin-1
printf "info\n\xa9 2024 Gemeente Delft\n" > "$TEST_FILE"
run_convert "$TEST_FILE" "test9_translit" > /dev/null 2>&1
if iconv -f UTF-8 -t UTF-8 "$TEST_FILE" > /dev/null 2>&1; then
    pass "TRANSLIT modus werkt voor speciale tekens"
else
    fail "TRANSLIT modus" "resultaat is geen geldig UTF-8"
fi

# --- Test 10: Verifieer dat metainfo JSON ook geconverteerd wordt ---
TEST_FILE="$TMPDIR/test10.json"
printf '{"name": "Caf\xe9", "table": "VONDST"}\n' > "$TEST_FILE"
run_convert "$TEST_FILE" "test10_json" > /dev/null 2>&1
if iconv -f UTF-8 -t UTF-8 "$TEST_FILE" > /dev/null 2>&1; then
    pass "JSON metainfo encoding-conversie"
else
    fail "JSON metainfo" "resultaat is geen geldig UTF-8"
fi


# Opruimen
rm -rf "$TMPDIR"

# Rapport
echo ""
echo "=========================================="
TOTAL=$((PASSED + FAILED))
if [ $FAILED -eq 0 ]; then
    echo -e "  ${GREEN}ALL $PASSED TESTS PASSED${NC}"
else
    echo -e "  $PASSED passed, ${RED}$FAILED failed${NC} (total: $TOTAL)"
fi
echo "=========================================="
echo ""

exit $FAILED
