"""
Unit tests voor de bestandsnaam-parsing logica uit harmonize_functions.py

De functie parseFotobestanden() bevat complexe regex-patronen die foto's,
tekeningen en rapporten herkennen op basis van hun bestandsnaam. Deze tests
valideren die patronen zonder een database nodig te hebben.
"""
import pytest
import re

import shared.const as const

# --- De regex-patronen uit harmonize_functions.parseFotobestanden ---

# Objectfoto's: bevatten _H en beginnen met projectcode
RE_OBJECTFOTO = re.compile(
    r'^([a-zA-Z0-9]+)(_B?P([0-9Xx]+))?_H([a-zA-Z0-9]+)(_([a-zA-Z0-9]+))?_([0-9Xx]+)\.[a-z]{3}$',
    re.M | re.I
)

# Tekeningen: letter B-E of P/T gevolgd door nummer
RE_TEKENING = re.compile(
    r'^([a-zA-Z0-9]+)_([ABCDEPT])([a-zA-Z0-9]+)(_LZW)?\.[a-z]{3}$',
    re.M | re.I
)

# Projectfoto's: letter F of G gevolgd door nummer
RE_PROJECTFOTO = re.compile(
    r'^([a-zA-Z0-9]+)_([FG])([a-zA-Z0-9]+).*\.[a-z]{3}$',
    re.M | re.I
)

# Rapporten: beginnen met DAN of DAR
RE_RAPPORT = re.compile(
    r'^(DAN|DAR)\s*([0-9]{2,3}).*',
    re.M | re.I
)

# Projectcode uit bestandsnaam
RE_PROJECTCD = re.compile(
    r'^([a-z0-9]+).*',
    re.M | re.I
)


# ============================================================
# Objectfoto's
# ============================================================

class TestObjectfotoRegex:
    """Foto's met _H patroon (Hoofdvondstnummer)."""

    def test_standard_objectfoto(self):
        m = RE_OBJECTFOTO.match("DC001_H123_456_001.jpg")
        assert m is not None
        assert m.group(4) == "123"    # vondstnr
        assert m.group(7) == "001"    # fotonr

    def test_objectfoto_met_putnr(self):
        m = RE_OBJECTFOTO.match("DC001_P3_H456_789_002.jpg")
        assert m is not None
        assert m.group(3) == "3"      # putnr
        assert m.group(4) == "456"    # vondstnr

    def test_objectfoto_met_subnr(self):
        m = RE_OBJECTFOTO.match("DC001_H123_45_003.jpg")
        assert m is not None
        assert m.group(6) == "45"     # subnr

    def test_geen_objectfoto(self):
        m = RE_OBJECTFOTO.match("DC001_F001.jpg")
        assert m is None

    def test_objectfoto_met_BP(self):
        m = RE_OBJECTFOTO.match("DC001_BP3_H456_789_002.jpg")
        assert m is not None


# ============================================================
# Tekeningen
# ============================================================

class TestTekeningRegex:
    """Tekeningen met type-letters A-E, P, T."""

    @pytest.mark.parametrize("filename,tektype", [
        ("DC001_A001.jpg", "A"),   # Bouwtekening
        ("DC001_B002.tif", "B"),   # Veldtekening
        ("DC001_C003.png", "C"),   # Overzichtstekening
        ("DC001_D004.jpg", "D"),   # Objecttekening
        ("DC001_E005.jpg", "E"),   # Uitwerkingstekening
        ("DC001_P006.jpg", "P"),   # Veldtekening publiceerbaar
        ("DC001_T007.jpg", "T"),   # Objecttekening publiceerbaar
    ])
    def test_tekening_types(self, filename, tektype):
        m = RE_TEKENING.match(filename)
        assert m is not None, f"{filename} wordt niet herkend als tekening"
        assert m.group(2) == tektype

    def test_tekening_met_lzw(self):
        m = RE_TEKENING.match("DC001_B002_LZW.tif")
        assert m is not None
        assert m.group(4) == "_LZW"

    def test_geen_tekening(self):
        m = RE_TEKENING.match("DC001_H123_456_001.jpg")
        assert m is None  # Dit is een objectfoto, geen tekening


# ============================================================
# Projectfoto's
# ============================================================

class TestProjectfotoRegex:
    """Projectfoto's met F (sfeer) of G (opgraving)."""

    def test_sfeerfoto(self):
        m = RE_PROJECTFOTO.match("DC001_F001.jpg")
        assert m is not None
        assert m.group(2) == "F"
        assert m.group(3) == "001"

    def test_opgravingsfoto(self):
        m = RE_PROJECTFOTO.match("DC001_G002.jpg")
        assert m is not None
        assert m.group(2) == "G"

    def test_sfeerfoto_met_extra(self):
        m = RE_PROJECTFOTO.match("DC001_F001_extra_info.jpg")
        assert m is not None


# ============================================================
# Rapporten
# ============================================================

class TestRapportRegex:
    """DAN/DAR-rapporten."""

    def test_dar_rapport(self):
        m = RE_RAPPORT.match("DAR 123 Titel van rapport.pdf")
        assert m is not None
        assert m.group(1) == "DAR"
        assert m.group(2) == "123"

    def test_dan_rapport(self):
        m = RE_RAPPORT.match("DAN45.pdf")
        assert m is not None
        assert m.group(1) == "DAN"
        assert m.group(2) == "45"

    def test_dar_zonder_spatie(self):
        m = RE_RAPPORT.match("DAR012_rapport.pdf")
        assert m is not None

    def test_geen_rapport(self):
        m = RE_RAPPORT.match("DC001_F001.jpg")
        assert m is None


# ============================================================
# Projectcode extractie
# ============================================================

class TestProjectcodeExtractie:
    """Test het herkennen van projectcodes uit bestandsnamen."""

    @pytest.mark.parametrize("filename,expected", [
        ("DC001_F001.jpg", "DC001"),
        ("DB008_H123_456_001.jpg", "DB008"),
        ("dc032test.jpg", "dc032test"),
    ])
    def test_projectcode(self, filename, expected):
        m = RE_PROJECTCD.match(filename)
        assert m is not None
        assert m.group(1) == expected


# ============================================================
# Artefactsoort detectie uit bestandsnaam (directory-gebaseerd)
# ============================================================

class TestArtefactsoortDetectie:
    """
    De functie parseFotobestanden bepaalt artefactsoort op basis
    van het pad (fullFileName). Test die logica als pure functie.
    """

    MAPPING = {
        "aardewerk": const.ARTF_AARDEWERK,
        "pijpaard": const.ARTF_AARDEWERK,
        "glas": const.ARTF_GLAS,
        "leer": const.ARTF_LEER,
        "steen": const.ARTF_STEEN,
        "kleipijp": const.ARTF_KLEIPIJP,
        "metaal": const.ARTF_METAAL,
        "munt": const.ARTF_MUNT,
        "schelp": const.ARTF_SCHELP,
        "textiel": const.ARTF_TEXTIEL,
        "bouwaardewerk": const.ARTF_BOUWAARDEWERK,
    }

    @pytest.mark.parametrize("keyword,expected", list(MAPPING.items()))
    def test_keyword_mapping(self, keyword, expected):
        """Bestandspad met keyword moet juiste artefactsoort opleveren."""
        path = f"/fotos/DC001/objectfoto/{keyword}/DC001_H123_456_001.jpg"
        # Simuleer de logica uit parseFotobestanden
        strFN = path.lower()
        result = None
        if "bouwaardewerk" in strFN:
            result = const.ARTF_BOUWAARDEWERK
        elif "aardewerk" in strFN or "pijpaard" in strFN:
            result = const.ARTF_AARDEWERK
        elif "glas" in strFN:
            result = const.ARTF_GLAS
        elif "leer" in strFN:
            result = const.ARTF_LEER
        elif "steen" in strFN:
            result = const.ARTF_STEEN
        elif "kleipijp" in strFN:
            result = const.ARTF_KLEIPIJP
        elif "metaal" in strFN:
            result = const.ARTF_METAAL
        elif "munt" in strFN:
            result = const.ARTF_MUNT
        elif "schelp" in strFN:
            result = const.ARTF_SCHELP
        elif "textiel" in strFN:
            result = const.ARTF_TEXTIEL

        assert result == expected, f"'{keyword}' leverde '{result}' op i.p.v. '{expected}'"
