"""
Unit tests voor het profielensysteem.

Test de profielselectie, het standaard ConventieProfiel,
het DelftProfiel, en het VoorbeeldProfiel.
"""
import pytest
from unittest.mock import patch

import shared.const as const


# ============================================================
# Profielselectie
# ============================================================

@pytest.mark.unit
class TestProfielSelectie:
    """Test dat get_profiel() het juiste profiel laadt."""

    def setup_method(self):
        from wasstraat.profielen import reset_profiel
        reset_profiel()

    def teardown_method(self):
        from wasstraat.profielen import reset_profiel
        reset_profiel()

    def test_default_is_delft(self):
        """Zonder WASSTRAAT_GEMEENTE wordt Delft geladen."""
        from wasstraat.profielen import get_profiel
        profiel = get_profiel()
        assert profiel.naam == "delft"

    def test_delft_expliciet(self):
        """WASSTRAAT_GEMEENTE=delft laadt DelftProfiel."""
        import shared.config as config
        from wasstraat.profielen import get_profiel, reset_profiel
        with patch.object(config, 'WASSTRAAT_GEMEENTE', 'delft', create=True):
            reset_profiel()
            profiel = get_profiel()
            assert profiel.naam == "delft"

    def test_voorbeeld_profiel(self):
        """WASSTRAAT_GEMEENTE=voorbeeld laadt VoorbeeldProfiel."""
        import shared.config as config
        from wasstraat.profielen import get_profiel, reset_profiel
        with patch.object(config, 'WASSTRAAT_GEMEENTE', 'voorbeeld', create=True):
            reset_profiel()
            profiel = get_profiel()
            assert profiel.naam == "voorbeeld"

    def test_onbekend_profiel_error(self):
        """Onbekende gemeente geeft ValueError."""
        import shared.config as config
        from wasstraat.profielen import get_profiel, reset_profiel
        with patch.object(config, 'WASSTRAAT_GEMEENTE', 'onbekend', create=True):
            reset_profiel()
            with pytest.raises(ValueError, match="Onbekend gemeenteprofiel"):
                get_profiel()

    def test_profiel_wordt_gecached(self):
        """Meerdere aanroepen geven hetzelfde object terug."""
        from wasstraat.profielen import get_profiel
        p1 = get_profiel()
        p2 = get_profiel()
        assert p1 is p2

    def test_reset_profiel_wist_cache(self):
        """Na reset wordt een nieuw object aangemaakt."""
        from wasstraat.profielen import get_profiel, reset_profiel
        p1 = get_profiel()
        reset_profiel()
        p2 = get_profiel()
        assert p1 is not p2


# ============================================================
# ConventieProfiel (standaard)
# ============================================================

@pytest.mark.unit
class TestConventieProfiel:
    """Test het standaard ConventieProfiel."""

    @pytest.fixture
    def profiel(self):
        from wasstraat.profielen.conventie import ConventieProfiel
        return ConventieProfiel()

    def test_naam(self, profiel):
        assert profiel.naam == "conventie"

    def test_extract_projectcode_simpel(self, profiel):
        assert profiel.extract_projectcode_uit_bestandsnaam("AB001_F001.jpg", "/pad") == "AB001"

    def test_extract_projectcode_geen_prefix_validatie(self, profiel):
        """ConventieProfiel accepteert elke projectcode."""
        assert profiel.extract_projectcode_uit_bestandsnaam("XYZ_test.jpg", "/pad") == "XYZ"

    def test_identificeer_foto_geeft_none(self, profiel):
        """Standaard profiel herkent geen foto-bestandsnamen."""
        doc = {"fileName": "test.jpg", "fullFileName": "/pad/test.jpg"}
        assert profiel.identificeer_foto(doc, "TEST") is None

    def test_identificeer_tekening_geeft_none(self, profiel):
        """Standaard profiel herkent geen tekening-bestandsnamen."""
        doc = {"fileName": "test.jpg", "fullFileName": "/pad/test.jpg"}
        assert profiel.identificeer_tekening(doc, "TEST") is None

    def test_identificerende_velden_bevat_kerntypes(self, profiel):
        """IDENTIFICERENDE_VELDEN bevat alle kerntypes."""
        for soort in ['Project', 'Put', 'Vlak', 'Spoor', 'Vondst', 'Artefact', 'Monster', 'Doos']:
            assert soort in profiel.IDENTIFICERENDE_VELDEN, f"{soort} ontbreekt"

    def test_identificeer_dispatcher(self, profiel):
        """identificeer() dispatcht naar juiste methode."""
        doc = {'projectcd': 'TEST', 'putnr': '5'}
        result = profiel.identificeer('Put', doc)
        assert result is doc  # zelfde object, gewijzigd in-place

    def test_identificeer_onbekend_soort(self, profiel):
        """Onbekend soort gebruikt standaard-methode."""
        doc = {'projectcd': 'TEST'}
        result = profiel.identificeer('OnbekendType', doc)
        assert result is doc

    @pytest.mark.parametrize("soort", ['Foto', 'Tekening', 'Rapport'])
    def test_identificeer_bestandsoort_kiest_db_variant(self, profiel, soort):
        """identificeer() kiest voor bestands-entiteiten identificeer_<soort>_db, niet de bestandsnaam-parser.

        De parser identificeer_<soort>(doc, projectcd) verwacht twee argumenten;
        hem kiezen gaf een TypeError (en voor Foto: geen artefactkoppeling).
        """
        doc = {'soort': soort, 'projectcd': 'TEST', 'fileName': 'TEST_P1_H2_3_4.jpg'}
        result = profiel.identificeer(soort, doc)
        assert result is doc
        assert 'vondstnr' not in result, "de bestandsnaam-parser is aangeroepen"

    def test_identificeer_foto_normaliseert_nummers(self, profiel):
        """Een Foto-record krijgt integers voor putnr, vondstnr, subnr en fotonr (nodig voor key_foto1)."""
        doc = {'soort': 'Foto', 'projectcd': 'TEST', 'putnr': '3', 'vondstnr': '456', 'subnr': '789', 'fotonr': '2'}
        result = profiel.identificeer('Foto', doc)
        assert result['projectcd'] == 'TEST'
        assert (result['putnr'], result['vondstnr'], result['subnr'], result['fotonr']) == (3, 456, 789, 2)
        for veld in ['putnr', 'vondstnr', 'subnr', 'fotonr']:
            assert type(result[veld]) is int, f"{veld} is geen int maar {type(result[veld])}"

    def test_identificeer_tekening_en_rapport_db_passthrough(self, profiel):
        """De standaard _db-varianten normaliseren projectcd en laten tekeningcd en rapportnr ongemoeid."""
        tekening = profiel.identificeer('Tekening', {'soort': 'Tekening', 'projectcd': 'TEST', 'tekeningcd': 'B2'})
        assert tekening['tekeningcd'] == 'B2'
        rapport = profiel.identificeer('Rapport', {'soort': 'Rapport', 'rapportnr': 'DAR 12', 'brondata': {}})
        assert rapport['rapportnr'] == 'DAR 12'

    def test_normaliseer_projectcode_passthrough(self, profiel):
        assert profiel.normaliseer_projectcode("abc123") == "abc123"

    def test_normaliseer_tekeningcode_passthrough(self, profiel):
        assert profiel.normaliseer_tekeningcode("B2") == "B2"

    def test_normaliseer_rapportnr_passthrough(self, profiel):
        assert profiel.normaliseer_rapportnr("DAR123", {}) == "DAR123"

    def test_detecteer_artefactsoort_aardewerk(self, profiel):
        assert profiel.detecteer_artefactsoort("/fotos/aardewerk/test.jpg") == const.ARTF_AARDEWERK

    def test_detecteer_artefactsoort_onbekend(self, profiel):
        assert profiel.detecteer_artefactsoort("/fotos/onbekend/test.jpg") == const.ARTF_ONBEKEND


# ============================================================
# DelftProfiel
# ============================================================

@pytest.mark.unit
class TestDelftProfiel:
    """Test het Delft-profiel."""

    @pytest.fixture
    def profiel(self):
        from wasstraat.profielen.delft import DelftProfiel
        return DelftProfiel()

    def test_naam(self, profiel):
        assert profiel.naam == "delft"

    # --- Projectcode extractie ---

    def test_extract_projectcd_db_prefix(self, profiel):
        assert profiel.extract_projectcode_uit_bestandsnaam("DB034_H001.jpg", "/pad") == "DB034"

    def test_extract_projectcd_dc_prefix(self, profiel):
        assert profiel.extract_projectcode_uit_bestandsnaam("DC001_F001.jpg", "/pad") == "DC001"

    def test_extract_projectcd_fallback_directory(self, profiel):
        """Als bestandsnaam niet met DB/DC begint, gebruik directory."""
        result = profiel.extract_projectcode_uit_bestandsnaam("test_H001.jpg", "/DC045/fotos")
        assert result == "DC045"

    def test_extract_projectcd_geen_match(self, profiel):
        """Als noch bestandsnaam noch directory DB/DC bevat."""
        result = profiel.extract_projectcode_uit_bestandsnaam("test_H001.jpg", "/andere/map")
        # Geeft de bestandsnaam-extractie terug (geen DB/DC validatie-faal)
        assert result == "test"

    # --- Bestandsnaam-parsing: objectfoto ---

    def test_identificeer_objectfoto(self, profiel):
        doc = {"fileName": "DC001_P3_H456_789_002.jpg", "fullFileName": "/fotos/aardewerk/DC001_P3_H456_789_002.jpg"}
        result = profiel.identificeer_foto(doc, "DC001")
        assert result is not None
        assert result['soort'] == 'Foto'
        assert result['bestandsoort'] == const.FOTO_OBJECTFOTO
        assert result['putnr'] == '3'
        assert result['vondstnr'] == '456'
        assert result['fotonr'] == '2'
        assert result['artefactsoort'] == const.ARTF_AARDEWERK

    def test_identificeer_objectfoto_zonder_putnr(self, profiel):
        doc = {"fileName": "DC001_H123_456_001.jpg", "fullFileName": "/fotos/DC001_H123_456_001.jpg"}
        result = profiel.identificeer_foto(doc, "DC001")
        assert result is not None
        assert 'putnr' not in result or result.get('putnr') is None

    # --- Database-identificatie van foto's (Type A, via de dispatcher) ---

    def test_identificeer_foto_via_dispatcher_faalt_niet(self, profiel):
        """identificeer('Foto', doc) roept niet de bestandsnaam-parser met twee argumenten aan (gaf TypeError)."""
        doc = {'soort': 'Foto', 'projectcd': 'DB34', 'fileName': 'DB34_P10_H0230_216_3.jpg'}
        result = profiel.identificeer('Foto', doc)
        assert result is doc
        assert 'vondstnr' not in result, "de bestandsnaam-parser is aangeroepen"

    def test_identificeer_foto_normaliseert_projectcode_en_nummers(self, profiel):
        """Een geparste objectfoto krijgt in Transform 2 projectcode DB034 en integers, net als het artefact."""
        doc = {"fileName": "DB34_P10_H0230_216_3.jpg",
               "fullFileName": "/input/projecten/DB034/L Fotos/H (Objectfoto's)/Aardewerk/DB34_P10_H0230_216_3.jpg"}
        projectcd = profiel.extract_projectcode_uit_bestandsnaam(doc['fileName'], '')
        doc = profiel.identificeer_foto(doc, projectcd)
        assert (doc['projectcd'], doc['putnr'], doc['vondstnr'], doc['subnr'], doc['fotonr']) == ('DB34', '10', '230', '216', '3')

        result = profiel.identificeer('Foto', doc)
        assert result['projectcd'] == 'DB034'
        assert (result['putnr'], result['vondstnr'], result['subnr'], result['fotonr']) == (10, 230, 216, 3)
        for veld in ['putnr', 'vondstnr', 'subnr', 'fotonr']:
            assert type(result[veld]) is int, f"{veld} is geen int maar {type(result[veld])}"
        assert result['artefactsoort'] == const.ARTF_AARDEWERK

    def test_identificeer_foto_zelfde_sleutelvelden_als_artefact(self, profiel):
        """Foto en artefact krijgen dezelfde velden voor key_foto1: projectcd, artefactsoort, putnr, vondstnr, subnr."""
        foto = profiel.identificeer('Foto', {'soort': 'Foto', 'projectcd': 'DB34', 'putnr': '10',
                                             'vondstnr': '230', 'subnr': '216', 'artefactsoort': 'Aardewerk'})
        artefact = profiel.identificeer('Artefact', {'soort': 'Artefact', 'projectcd': 'db-34', 'putnr': 10,
                                                     'vondstnr': 230, 'subnr': 216, 'artefactnr': 5, 'artefactsoort': 'Aardewerk'})
        velden = ['projectcd', 'artefactsoort', 'putnr', 'vondstnr', 'subnr']
        assert [foto[v] for v in velden] == [artefact[v] for v in velden] == ['DB034', 'Aardewerk', 10, 230, 216]

    def test_identificeer_foto_ongeldig_putnr_verwijderd(self, profiel):
        """Een niet-numeriek putnr (DB34_PX_H...) verdwijnt; een niet-numeriek fotonr blijft tekst."""
        result = profiel.identificeer('Foto', {'soort': 'Foto', 'projectcd': 'DB34', 'putnr': 'X', 'vondstnr': '12', 'fotonr': '1a'})
        assert 'putnr' not in result
        assert result['vondstnr'] == 12
        assert result['fotonr'] == '1a'

    def test_identificeer_tekening_en_rapport_via_dispatcher(self, profiel):
        """identificeer() normaliseert tekeningcd en rapportnr via de Delftse _db-varianten."""
        tekening = profiel.identificeer('Tekening', {'soort': 'Tekening', 'projectcd': 'dc16', 'tekeningcd': 'B2'})
        assert (tekening['projectcd'], tekening['tekeningcd']) == ('DC016', 'B002')
        rapport = profiel.identificeer('Rapport', {'soort': 'Rapport', 'rapportnr': 'DAR 12', 'brondata': {}})
        assert rapport['rapportnr'] == 'DAR012'

    # --- Bestandsnaam-parsing: tekening ---

    def test_identificeer_tekening(self, profiel):
        doc = {"fileName": "DC001_B002.tif", "fullFileName": "/tek/DC001_B002.tif"}
        result = profiel.identificeer_tekening(doc, "DC001")
        assert result is not None
        assert result['soort'] == 'Tekening'
        assert result['bestandsoort'] == const.TEK_VELDTEKENING
        assert result['tekeningcd'] == 'B002'

    @pytest.mark.parametrize("letter,expected_soort", [
        ("A", const.TEK_BOUWTEKENING),
        ("B", const.TEK_VELDTEKENING),
        ("C", const.TEK_OVERZICHTSTEKENING),
        ("D", const.TEK_OBJECTTEKENING),
        ("E", const.TEK_UITWERKINGSTEKENING),
        ("P", const.TEK_VELDTEKENING_PUBL),
        ("T", const.TEK_OBJECTTEKENING_PUBL),
    ])
    def test_identificeer_tekening_types(self, profiel, letter, expected_soort):
        doc = {"fileName": f"DC001_{letter}001.jpg", "fullFileName": f"/tek/DC001_{letter}001.jpg"}
        result = profiel.identificeer_tekening(doc, "DC001")
        assert result is not None
        assert result['bestandsoort'] == expected_soort

    # --- Bestandsnaam-parsing: projectfoto ---

    def test_identificeer_sfeerfoto(self, profiel):
        doc = {"fileName": "DC001_F001.jpg", "fullFileName": "/fotos/DC001_F001.jpg"}
        result = profiel.identificeer_foto(doc, "DC001")
        assert result is not None
        assert result['soort'] == 'Foto'
        assert result['bestandsoort'] == const.FOTO_SFEERFOTO

    def test_identificeer_opgravingsfoto(self, profiel):
        doc = {"fileName": "DC001_G002.jpg", "fullFileName": "/fotos/DC001_G002.jpg"}
        result = profiel.identificeer_foto(doc, "DC001")
        assert result is not None
        assert result['bestandsoort'] == const.FOTO_OPGRAVINGSFOTO

    # --- Niet-herkend bestand ---

    def test_identificeer_onbekend_bestand(self, profiel):
        doc = {"fileName": "verslag_opgraving.pdf", "fullFileName": "/docs/verslag_opgraving.pdf"}
        result_foto = profiel.identificeer_foto(doc, "DC001")
        result_tekening = profiel.identificeer_tekening(doc, "DC001")
        assert result_foto is None
        assert result_tekening is None

    # --- Projectcode normalisatie ---

    @pytest.mark.parametrize("raw,expected", [
        ("dc-16", "DC016"),
        ("DC016", "DC016"),
        ("DB034", "DB034"),
        ("DB", "DB"),
        ("dc16", "DC016"),
        ("DC 16", "DC"),  # Spatie breekt de match, geeft alleen letters
    ])
    def test_normaliseer_projectcode(self, profiel, raw, expected):
        assert profiel.normaliseer_projectcode(raw) == expected

    # --- Tekeningcode normalisatie ---

    @pytest.mark.parametrize("raw,expected", [
        ("B2", "B002"),
        ("A15", "A015"),
        ("B002", "B002"),
        ("tekst", "tekst"),  # Geen match → passthrough
    ])
    def test_normaliseer_tekeningcode(self, profiel, raw, expected):
        assert profiel.normaliseer_tekeningcode(raw) == expected

    # --- Rapportnummer normalisatie ---

    def test_normaliseer_rapportnr_met_prefix(self, profiel):
        assert profiel.normaliseer_rapportnr("DAR 123", {}) == "DAR123"

    def test_normaliseer_rapportnr_zonder_prefix_met_dar_veld(self, profiel):
        assert profiel.normaliseer_rapportnr("45", {"DARnr": 45}) == "DAR045"

    def test_normaliseer_rapportnr_zonder_prefix_met_dan_veld(self, profiel):
        assert profiel.normaliseer_rapportnr("7", {"DANnr": 7}) == "DAN007"

    def test_normaliseer_rapportnr_zonder_prefix_zonder_veld(self, profiel):
        assert profiel.normaliseer_rapportnr("123", {}) == ""

    def test_normaliseer_rapportnr_ongeldig(self, profiel):
        assert profiel.normaliseer_rapportnr("iets_anders", {}) == "iets_anders"


# ============================================================
# VoorbeeldProfiel
# ============================================================

@pytest.mark.unit
class TestVoorbeeldProfiel:
    """Test het PoC voorbeeld-profiel."""

    @pytest.fixture
    def profiel(self):
        from wasstraat.profielen.voorbeeld import VoorbeeldProfiel
        return VoorbeeldProfiel()

    def test_naam(self, profiel):
        assert profiel.naam == "voorbeeld"

    def test_erft_van_conventie(self, profiel):
        """VoorbeeldProfiel gedraagt zich als ConventieProfiel."""
        assert profiel.normaliseer_projectcode("abc123") == "abc123"
        assert profiel.identificeer_foto(
            {"fileName": "test.jpg", "fullFileName": "/test.jpg"}, "TEST"
        ) is None

    def test_identificeer_bestandsoorten_zonder_overrides(self, profiel):
        """Ook zonder eigen _db-methoden werkt identificeer() voor Foto, Tekening en Rapport."""
        foto = profiel.identificeer('Foto', {'soort': 'Foto', 'projectcd': 'ab1', 'vondstnr': '7'})
        assert (foto['projectcd'], foto['vondstnr']) == ('ab1', 7)
        tekening = profiel.identificeer('Tekening', {'soort': 'Tekening', 'projectcd': 'ab1', 'tekeningcd': 'B2'})
        assert tekening['tekeningcd'] == 'B2'
        rapport = profiel.identificeer('Rapport', {'soort': 'Rapport', 'rapportnr': '12'})
        assert rapport['rapportnr'] == '12'
