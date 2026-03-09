"""
Unit tests voor encoding-afhandeling in de Wasstraat pipeline.

Test de sanitize_text functies in archutils.py en de bash-level
encoding-conversie via importMDB.sh.

Deze tests valideren:
1. Correcte afhandeling van Windows-1252 mojibake
2. Behoud van Nederlandse diakritische tekens
3. Verwijdering van control characters
4. Unicode NFC-normalisatie
5. Logging van onleesbare tekens
6. Bash encoding-conversie functie (convert_to_utf8)
"""
import pytest
import os
import subprocess
import tempfile
import logging

from wasstraat.archutils import (
    sanitize_text, sanitize_text_field, sanitize_all_string_fields,
    REPLACEMENT_CHAR
)


# ============================================================
# sanitize_text - Basis
# ============================================================

class TestSanitizeTextBasic:
    """Test basisfunctionaliteit van sanitize_text."""

    def test_none_returns_none(self):
        assert sanitize_text(None) is None

    def test_empty_string(self):
        assert sanitize_text("") == ""

    def test_normal_text_unchanged(self):
        assert sanitize_text("Gewone tekst") == "Gewone tekst"

    def test_non_string_converted(self):
        """Niet-string waarden worden naar str geconverteerd."""
        assert sanitize_text(42) == "42"
        assert sanitize_text(3.14) == "3.14"

    def test_strips_whitespace(self):
        assert sanitize_text("  tekst  ") == "tekst"


# ============================================================
# sanitize_text - Nederlandse diakritische tekens
# ============================================================

class TestSanitizeTextDiacritics:
    """Test dat Nederlandse diakritische tekens correct behouden blijven."""

    @pytest.mark.parametrize("input_text,expected", [
        ("cafe\u0301", "caf\u00e9"),              # cafe + combining acute -> cafe (NFC)
        ("caf\u00e9", "caf\u00e9"),                # al NFC, ongewijzigd
        ("Maastrichtse gra\u0308ften", "Maastrichtse gr\u00e4ften"),  # combining diaeresis
        ("\u00fcberhaupt", "\u00fcberhaupt"),       # u-umlaut ongewijzigd
        ("na\u00efviteit", "na\u00efviteit"),       # i-trema ongewijzigd
    ])
    def test_dutch_diacritics_preserved(self, input_text, expected):
        result = sanitize_text(input_text)
        assert result == expected

    def test_ij_digraph(self):
        """De Nederlandse IJ-digraph (U+0132/U+0133) moet behouden blijven."""
        assert sanitize_text("\u0132sselmeer") == "\u0132sselmeer"

    def test_common_dutch_names(self):
        """Veelvoorkomende Nederlandse namen met speciale tekens."""
        assert sanitize_text("Zuidoost-Groningen") == "Zuidoost-Groningen"
        assert sanitize_text("Nieuw-Vennep") == "Nieuw-Vennep"
        assert sanitize_text("'s-Gravenhage") == "'s-Gravenhage"


# ============================================================
# sanitize_text - Windows-1252 mojibake reparatie
# ============================================================

class TestSanitizeTextMojibake:
    """
    Test reparatie van Windows-1252 tekens die fout gedecodeerd zijn.

    Dit simuleert het scenario waarbij Access-databases in Windows-1252
    zijn opgeslagen en de tekens in het 0x80-0x9F bereik als Latin-1
    zijn geinterpreteerd (wat de C1 control characters oplevert).
    """

    def test_smart_single_quote_right(self):
        """\\x92 (Windows-1252 right single quote) -> U+2019."""
        # Dit is het meest voorkomende probleem in NL Access-databases:
        # apostrof in namen als "Schermerhorn's" of "t Lam"
        result = sanitize_text("Schermerhorn\x92s graafwerk")
        assert result == "Schermerhorn\u2019s graafwerk"

    def test_smart_double_quotes(self):
        """\\x93/\\x94 (Windows-1252 double quotes) -> U+201C/U+201D."""
        result = sanitize_text("\x93Vondstnummer\x94")
        assert result == "\u201cVondstnummer\u201d"

    def test_euro_sign(self):
        """\\x80 (Windows-1252 Euro sign) -> U+20AC."""
        result = sanitize_text("Kosten: \x80 1.500")
        assert result == "Kosten: \u20ac 1.500"

    def test_en_dash(self):
        """\\x96 (Windows-1252 en dash) -> U+2013."""
        result = sanitize_text("1200\x961500 na Chr.")
        assert result == "1200\u20131500 na Chr."

    def test_em_dash(self):
        """\\x97 (Windows-1252 em dash) -> U+2014."""
        result = sanitize_text("Delft \x97 centrum")
        assert result == "Delft \u2014 centrum"

    def test_ellipsis(self):
        """\\x85 (Windows-1252 ellipsis) -> U+2026."""
        result = sanitize_text("Meer gegevens\x85")
        assert result == "Meer gegevens\u2026"

    def test_bullet(self):
        """\\x95 (Windows-1252 bullet) -> U+2022."""
        result = sanitize_text("\x95 Item 1")
        assert result == "\u2022 Item 1"

    def test_trademark(self):
        """\\x99 (Windows-1252 trademark) -> U+2122."""
        result = sanitize_text("Product\x99")
        assert result == "Product\u2122"

    def test_multiple_mojibake_in_one_string(self):
        """Meerdere mojibake-tekens in een enkele string."""
        input_text = "\x93Archeologisch rapport\x94 \x96 Delft\x92s centrum"
        expected = "\u201cArcheologisch rapport\u201d \u2013 Delft\u2019s centrum"
        assert sanitize_text(input_text) == expected


# ============================================================
# sanitize_text - Control characters
# ============================================================

class TestSanitizeTextControlChars:
    """Test verwijdering van control characters."""

    def test_null_byte_removed(self):
        assert sanitize_text("tekst\x00rest") == "tekstrest"

    def test_bell_removed(self):
        assert sanitize_text("tekst\x07rest") == "tekstrest"

    def test_tab_preserved(self):
        assert sanitize_text("kolom1\tkolom2") == "kolom1\tkolom2"

    def test_newline_preserved(self):
        assert sanitize_text("regel1\nregel2") == "regel1\nregel2"

    def test_backspace_removed(self):
        assert sanitize_text("tekst\x08rest") == "tekstrest"

    def test_vertical_tab_removed(self):
        """\\x0B (vertical tab) is een control character, moet verwijderd worden."""
        assert sanitize_text("tekst\x0Brest") == "tekstrest"


# ============================================================
# sanitize_text - Unicode replacement character
# ============================================================

class TestSanitizeTextReplacementChar:
    """Test afhandeling van het Unicode replacement character U+FFFD."""

    def test_replacement_char_removed(self):
        result = sanitize_text("Delft \ufffd centrum")
        assert "\ufffd" not in result
        assert result == "Delft  centrum"

    def test_replacement_char_logged(self, caplog):
        """Verwijderde replacement characters worden gelogd."""
        with caplog.at_level(logging.WARNING):
            sanitize_text("test \ufffd data", field_name="naam", doc_id="ABC123")
        assert any("ENCODING" in r.message and "naam" in r.message for r in caplog.records)

    def test_multiple_replacement_chars_counted(self, caplog):
        """Meerdere replacement characters worden geteld in de warning."""
        with caplog.at_level(logging.WARNING):
            sanitize_text("\ufffd\ufffd\ufffd", field_name="veld")
        assert any("3 onleesbare" in r.message for r in caplog.records)


# ============================================================
# sanitize_text - Combinaties (realistische archeologische data)
# ============================================================

class TestSanitizeTextArchaeologicalData:
    """Test met realistische archeologische datavelden."""

    def test_projectnaam_with_apostrophe(self):
        """Projectnaam met Windows-1252 apostrof."""
        result = sanitize_text("Delft, \x92s-Gravenhof")
        assert result == "Delft, \u2019s-Gravenhof"

    def test_functievoorwerp_with_question_marks(self):
        """
        Vraagtekens in veldwaarden moeten NIET verwijderd worden.
        Dit is het verschil met de oude replace('?','') aanpak.
        Echte vraagtekens zijn valide leestekens.
        """
        result = sanitize_text("Drinkbeker?")
        assert result == "Drinkbeker?"

    def test_datering_met_vraagteken(self):
        """Dateringen bevatten soms vraagtekens als onzekerheidsmarkering."""
        result = sanitize_text("14e eeuw?")
        assert result == "14e eeuw?"

    def test_beschrijving_with_mixed_encoding_issues(self):
        """Beschrijvingsveld met diverse encoding-problemen."""
        input_text = "Rand van \x93type A\x94 met \x96 decoratie\x00"
        expected = "Rand van \u201ctype A\u201d met \u2013 decoratie"
        assert sanitize_text(input_text) == expected

    def test_toponiem(self):
        """Toponiemen met diakritische tekens."""
        assert sanitize_text("Duinkerke-Zuyd") == "Duinkerke-Zuyd"
        assert sanitize_text("Bo\u00ebl") == "Bo\u00ebl"

    def test_empty_projectcd(self):
        """Lege projectcode mag geen crash geven."""
        assert sanitize_text("") == ""

    def test_numeric_field_as_string(self):
        """Numerieke velden die als string binnenkomen."""
        assert sanitize_text("12345") == "12345"
        assert sanitize_text("0") == "0"


# ============================================================
# sanitize_text_field - Document-level
# ============================================================

class TestSanitizeTextField:
    """Test sanitize_text_field op MongoDB document-niveau."""

    def test_existing_field_sanitized(self):
        doc = {"_id": "test1", "functievoorwerp": "Beker\x92s rand"}
        sanitize_text_field(doc, "functievoorwerp")
        assert doc["functievoorwerp"] == "Beker\u2019s rand"

    def test_missing_field_ignored(self):
        doc = {"_id": "test1", "soort": "Artefact"}
        sanitize_text_field(doc, "functievoorwerp")
        assert "functievoorwerp" not in doc

    def test_none_field_stays_none(self):
        doc = {"_id": "test1", "functievoorwerp": None}
        sanitize_text_field(doc, "functievoorwerp")
        assert doc["functievoorwerp"] is None


# ============================================================
# sanitize_all_string_fields - Bulk document sanitatie
# ============================================================

class TestSanitizeAllStringFields:
    """Test sanitize_all_string_fields op hele documenten."""

    def test_all_strings_sanitized(self):
        doc = {
            "_id": "test1",
            "naam": "Delft\x92s depot",
            "type": "Aardewerk\x00",
            "aantal": 5,
            "brondata": {"raw": "niet\x92 aanraken"}
        }
        sanitize_all_string_fields(doc)
        assert doc["naam"] == "Delft\u2019s depot"
        assert doc["type"] == "Aardewerk"
        assert doc["aantal"] == 5
        # brondata moet NIET gesanitized worden
        assert doc["brondata"]["raw"] == "niet\x92 aanraken"

    def test_exclude_fields(self):
        doc = {
            "_id": "test1",
            "naam": "test\x92",
            "mdbfile": "/pad/met\x92apostrof"
        }
        sanitize_all_string_fields(doc)
        # mdbfile staat in de default exclude list
        assert doc["mdbfile"] == "/pad/met\x92apostrof"
        assert doc["naam"] == "test\u2019"


# ============================================================
# Bash encoding-conversie (integratietests voor importMDB.sh)
# ============================================================

class TestBashEncodingConversion:
    """
    Test de convert_to_utf8 bash-functie uit importMDB.sh.

    Deze tests creeren tijdelijke bestanden met bekende encodings
    en verifieer dat het bash-script ze correct naar UTF-8 converteert.
    """

    @pytest.fixture
    def bash_function(self):
        """Extract de convert_to_utf8 functie uit importMDB.sh voor standalone testen."""
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        script_path = os.path.join(project_root, "airflow_app", "scripts", "importMDB.sh")

        # Lees het script en extraheer de functie
        with open(script_path, "r") as f:
            script_content = f.read()

        # Extract alles van "convert_to_utf8()" tot de volgende functie/hoofdloop
        start = script_content.index("convert_to_utf8() {")
        # Zoek het einde: de regel met alleen "}" die de functie sluit
        brace_count = 0
        end = start
        for i, char in enumerate(script_content[start:]):
            if char == '{':
                brace_count += 1
            elif char == '}':
                brace_count -= 1
                if brace_count == 0:
                    end = start + i + 1
                    break

        function_text = script_content[start:end]
        return function_text

    def _run_convert(self, bash_function, input_bytes, expected_text):
        """Helper: schrijf bytes naar temp file, draai convert_to_utf8, controleer resultaat.

        Returns:
            (actual_text, stdout, returncode, is_valid_utf8)
            actual_text is str als geldig UTF-8, anders de raw bytes als latin-1 decoded string.
            is_valid_utf8 geeft aan of het resultaat geldig UTF-8 is.
        """
        with tempfile.NamedTemporaryFile(mode='wb', suffix='.csv', delete=False) as f:
            f.write(input_bytes)
            temp_path = f.name

        errorlog = temp_path + ".errors"

        try:
            # Bouw een mini-bash-script dat de functie definieert en aanroept
            test_script = f"""#!/bin/bash
ERRORLOG="{errorlog}"
{bash_function}
convert_to_utf8 "{temp_path}" "test_context"
echo "EXIT:$?"
"""
            result = subprocess.run(
                ["bash", "-c", test_script],
                capture_output=True, text=True, timeout=10
            )

            # Lees het geconverteerde bestand - probeer UTF-8, fallback naar raw bytes
            with open(temp_path, 'rb') as f:
                raw_bytes = f.read()

            is_valid_utf8 = True
            try:
                actual_text = raw_bytes.decode('utf-8')
            except UnicodeDecodeError:
                # Bestand is geen geldig UTF-8 - decodeer als latin-1 voor inspectie
                actual_text = raw_bytes.decode('latin-1')
                is_valid_utf8 = False

            return actual_text, result.stdout, result.returncode, is_valid_utf8
        finally:
            os.unlink(temp_path)
            if os.path.exists(errorlog):
                os.unlink(errorlog)

    def test_utf8_file_unchanged(self, bash_function):
        """Een al-geldig UTF-8 bestand moet ongewijzigd blijven."""
        input_bytes = "Caf\u00e9 te Delft\n".encode('utf-8')
        actual, stdout, _, is_utf8 = self._run_convert(bash_function, input_bytes, "Caf\u00e9 te Delft\n")
        assert is_utf8, "Resultaat moet geldig UTF-8 zijn"
        assert actual == "Caf\u00e9 te Delft\n"

    def test_windows_1252_converted(self, bash_function):
        """Windows-1252 bestand met typische Nederlandse tekens."""
        # \xe9 = e-accent in Windows-1252
        # \x92 = right single quote in Windows-1252
        input_bytes = b"Caf\xe9 in Delft\x92s centrum\n"
        actual, stdout, _, is_utf8 = self._run_convert(bash_function, input_bytes, None)
        assert is_utf8, (
            f"Resultaat moet geldig UTF-8 zijn na conversie van Windows-1252. "
            f"Bash output: {stdout[-500:]}"
        )
        assert "\n" in actual  # bestand is leesbaar

    def test_latin1_converted(self, bash_function):
        """ISO-8859-1 (Latin-1) bestand met diakritische tekens."""
        input_bytes = "Pr\u00e9historisch onderzoek\n".encode('latin-1')
        actual, stdout, _, is_utf8 = self._run_convert(bash_function, input_bytes, None)
        assert is_utf8, (
            f"Resultaat moet geldig UTF-8 zijn na conversie van Latin-1. "
            f"Bash output: {stdout[-500:]}"
        )
        assert "historisch" in actual

    def test_csv_with_headers_and_data(self, bash_function):
        """Realistisch CSV-bestand met kolommen en rijen."""
        # Windows-1252 CSV zoals uit mdb-export zou komen
        header = b"vondstnr,beschrijving,materiaal\n"
        row1 = b"1,\"Rand van een beker\",Aardewerk\n"
        row2 = b"2,\"Delft\x92s eigen product\",Aardewerk\n"  # \x92 = apostrof
        row3 = b"3,\"Caf\xe9-aardewerk\",Aardewerk\n"  # \xe9 = e-accent

        input_bytes = header + row1 + row2 + row3
        actual, stdout, _, is_utf8 = self._run_convert(bash_function, input_bytes, None)
        assert is_utf8, (
            f"CSV met Windows-1252 tekens moet na conversie geldig UTF-8 zijn. "
            f"Bash output: {stdout[-500:]}"
        )
        lines = actual.strip().split('\n')
        assert len(lines) == 4  # header + 3 rijen
        assert "vondstnr" in lines[0]  # header intact

    def test_mixed_ascii_and_special_chars(self, bash_function):
        """Bestand met mix van pure ASCII en speciale tekens."""
        input_bytes = b"putnr,spoornr,beschrijving\n1,5,\"Gewone tekst\"\n2,3,\"M\xfcnster-type\"\n"
        actual, stdout, _, is_utf8 = self._run_convert(bash_function, input_bytes, None)
        assert is_utf8, (
            f"Gemixte ASCII/speciale tekens moeten naar geldig UTF-8 geconverteerd worden. "
            f"Bash output: {stdout[-500:]}"
        )
        assert "putnr" in actual

    def test_already_valid_utf8_with_bom(self, bash_function):
        """UTF-8 bestand met BOM (Byte Order Mark) - soms door Excel gegenereerd."""
        input_bytes = b"\xef\xbb\xbfvondstnr,materiaal\n1,Aardewerk\n"
        actual, stdout, _, is_utf8 = self._run_convert(bash_function, input_bytes, None)
        assert is_utf8, "UTF-8 met BOM moet geldig UTF-8 blijven"


# ============================================================
# MDB_JET3_CHARSET environment variable
# ============================================================

class TestMdbExportEncoding:
    """
    Test dat de MDB_JET3_CHARSET en MDB_ICONV environment variables
    correct gezet worden in importMDB.sh.
    """

    def test_script_sets_charset_env(self):
        """Verifieer dat importMDB.sh de MDB encoding env vars zet."""
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        script_path = os.path.join(project_root, "airflow_app", "scripts", "importMDB.sh")

        with open(script_path, 'r') as f:
            content = f.read()

        assert 'export MDB_JET3_CHARSET="CP1252"' in content, \
            "importMDB.sh moet MDB_JET3_CHARSET=CP1252 exporteren"
        assert 'export MDB_ICONV="UTF-8"' in content, \
            "importMDB.sh moet MDB_ICONV=UTF-8 exporteren"

    def test_script_has_convert_to_utf8_function(self):
        """Verifieer dat importMDB.sh de convert_to_utf8 functie bevat."""
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        script_path = os.path.join(project_root, "airflow_app", "scripts", "importMDB.sh")

        with open(script_path, 'r') as f:
            content = f.read()

        assert 'convert_to_utf8()' in content, \
            "importMDB.sh moet de convert_to_utf8 functie bevatten"
        assert 'iconv' in content, \
            "importMDB.sh moet iconv gebruiken voor encoding-conversie"
        assert 'WINDOWS-1252' in content, \
            "importMDB.sh moet Windows-1252 als fallback encoding ondersteunen"
        assert 'ISO-8859-1' in content, \
            "importMDB.sh moet ISO-8859-1 als laatste-redmiddel encoding ondersteunen"

    def test_script_has_encoding_report(self):
        """Verifieer dat importMDB.sh een encoding-rapport genereert."""
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        script_path = os.path.join(project_root, "airflow_app", "scripts", "importMDB.sh")

        with open(script_path, 'r') as f:
            content = f.read()

        assert 'ENCODING RAPPORT' in content, \
            "importMDB.sh moet een encoding-rapport genereren aan het einde"
        assert 'TOTAL_TABLES_ENCODING_FAILED' in content, \
            "importMDB.sh moet encoding-fouten tellen"

    def test_script_validates_utf8_after_sed(self):
        """Verifieer dat importMDB.sh UTF-8 valideert na sed-bewerkingen."""
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        script_path = os.path.join(project_root, "airflow_app", "scripts", "importMDB.sh")

        with open(script_path, 'r') as f:
            content = f.read()

        # Zoek naar de post-sed validatie
        assert 'na sed-bewerking' in content, \
            "importMDB.sh moet UTF-8 valideren na sed-bewerkingen"


# ============================================================
# Regressietests: oude replace('?','') gedrag vs nieuw
# ============================================================

class TestQuestionMarkRegression:
    """
    Verifieer dat de nieuwe sanitize_text GEEN vraagtekens verwijdert.
    Dit is een bewuste gedragsverandering t.o.v. de oude code.
    """

    def test_question_mark_preserved_in_datering(self):
        """Vraagtekens in dateringen zijn significante onzekerheidsindicatoren."""
        assert "?" in sanitize_text("1650?")

    def test_question_mark_preserved_in_beschrijving(self):
        assert "?" in sanitize_text("Mogelijk een beker?")

    def test_question_mark_preserved_in_typevoorwerp(self):
        assert "?" in sanitize_text("Drinkgerei?")

    def test_only_encoding_artifacts_removed(self):
        """
        Alleen echte encoding-artefacten worden verwijderd,
        niet legitieme leestekens als '?', '!', etc.
        """
        result = sanitize_text("Test! Met? Leestekens.")
        assert result == "Test! Met? Leestekens."
