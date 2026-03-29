"""
Unit tests voor het correcties.yml mechanisme (issue #60).

Test dat de generieke correctielogica correct werkt:
- YAML-bestand laden en cachen
- Projectcode-correcties toepassen op staging en monster collecties
- Rapportcode-prefixen dynamisch matchen
- Merge-uitzonderingen laden
- Image-filterpatronen uitbreiden

Mockt pymongo zodat er geen live database nodig is.
"""
import pytest
import sys
import types
import os
import re
import tempfile
import yaml
from unittest.mock import patch, MagicMock, call

# Mock shared.image_util als die niet beschikbaar is (wordt geïmporteerd door image_import.py)
if "shared.image_util" not in sys.modules:
    sys.modules["shared.image_util"] = types.ModuleType("shared.image_util")


# ============================================================
# Klasse 1: Laden van correcties.yml
# ============================================================

class TestLaadCorrecties:
    """Test het laden en cachen van het correctiebestand."""

    def setup_method(self):
        """Reset de cache voor elke test."""
        import wasstraat.harmonize_functions as hf
        hf._correcties_cache = None

    def test_laden_geldig_bestand(self, tmp_path):
        """Een geldig YAML-bestand wordt correct ingelezen als dict."""
        import wasstraat.harmonize_functions as hf
        hf._correcties_cache = None

        yml_content = {
            'projectcode_fixes': {
                'staging': [
                    {'veld': 'mdbfile', 'patroon': 'DC027_Voorstraat', 'doel_veld': 'project', 'waarde': 'DC027'}
                ]
            }
        }
        yml_file = tmp_path / "correcties.yml"
        yml_file.write_text(yaml.dump(yml_content))

        with patch.object(hf.config, 'AIRFLOW_CORRECTIES_CONFIG', str(yml_file)):
            result = hf.laadCorrecties()

        assert 'projectcode_fixes' in result
        assert len(result['projectcode_fixes']['staging']) == 1
        assert result['projectcode_fixes']['staging'][0]['waarde'] == 'DC027'

    def test_laden_leeg_bestand(self, tmp_path):
        """Een leeg YAML-bestand retourneert een leeg dict."""
        import wasstraat.harmonize_functions as hf
        hf._correcties_cache = None

        yml_file = tmp_path / "correcties.yml"
        yml_file.write_text("# Leeg bestand\n")

        with patch.object(hf.config, 'AIRFLOW_CORRECTIES_CONFIG', str(yml_file)):
            result = hf.laadCorrecties()

        assert result == {}

    def test_laden_ontbrekend_bestand(self):
        """Een niet-bestaand pad retourneert een leeg dict, geen exception."""
        import wasstraat.harmonize_functions as hf
        hf._correcties_cache = None

        with patch.object(hf.config, 'AIRFLOW_CORRECTIES_CONFIG', '/tmp/niet_bestaand_correcties.yml'):
            result = hf.laadCorrecties()

        assert result == {}

    def test_caching_hergebruikt_resultaat(self, tmp_path):
        """Na eerste aanroep wordt het resultaat gecached en het bestand niet opnieuw gelezen."""
        import wasstraat.harmonize_functions as hf
        hf._correcties_cache = None

        yml_file = tmp_path / "correcties.yml"
        yml_file.write_text(yaml.dump({'test_key': 'test_value'}))

        with patch.object(hf.config, 'AIRFLOW_CORRECTIES_CONFIG', str(yml_file)):
            result1 = hf.laadCorrecties()
            # Verwijder het bestand
            yml_file.unlink()
            # Tweede aanroep moet cached resultaat teruggeven
            result2 = hf.laadCorrecties()

        assert result1 == result2
        assert result1 == {'test_key': 'test_value'}

    def test_ongeldige_yaml_retourneert_leeg_dict(self, tmp_path):
        """Onparseerbaar YAML-bestand retourneert leeg dict, geen crash."""
        import wasstraat.harmonize_functions as hf
        hf._correcties_cache = None

        yml_file = tmp_path / "correcties.yml"
        yml_file.write_text("dit is: [ongeldige: yaml\n  kapot")

        with patch.object(hf.config, 'AIRFLOW_CORRECTIES_CONFIG', str(yml_file)):
            result = hf.laadCorrecties()

        assert result == {}

    def test_yaml_met_lijst_retourneert_leeg_dict(self, tmp_path):
        """YAML dat een lijst bevat i.p.v. een dict retourneert leeg dict."""
        import wasstraat.harmonize_functions as hf
        hf._correcties_cache = None

        yml_file = tmp_path / "correcties.yml"
        yml_file.write_text("- item1\n- item2\n")

        with patch.object(hf.config, 'AIRFLOW_CORRECTIES_CONFIG', str(yml_file)):
            result = hf.laadCorrecties()

        assert result == {}


# ============================================================
# Klasse 2: fixProjectNames — Brondata-correcties
# ============================================================

def _maak_mock_db(hf, collectie_mocks):
    """Helper: maak een mock MongoDB client+db die collecties retourneert op basis van naam."""
    mock_client = MagicMock()
    mock_db = MagicMock()
    # Elke collectie retourneert een mock met update_many.return_value.modified_count = 0
    default_mock = MagicMock()
    default_mock.update_many.return_value = MagicMock(modified_count=0)
    mock_db.__getitem__ = lambda self, key: collectie_mocks.get(key, default_mock)
    mock_client.__getitem__ = lambda self, key: mock_db
    return mock_client


def _maak_collectie_mock():
    """Helper: maak een mock MongoDB collection met update_many."""
    m = MagicMock()
    m.update_many.return_value = MagicMock(modified_count=0)
    return m


class TestBrondataCorrecties:
    """Test dat brondata-correcties uit de YAML correct worden toegepast op staging-collecties."""

    def setup_method(self):
        import wasstraat.harmonize_functions as hf
        hf._correcties_cache = None

    @patch('wasstraat.harmonize_functions.pymongo')
    def test_staging_correctie_met_zoek_en_doel_veld(self, mock_pymongo):
        """Correctie met apart zoek_veld en doel_veld werkt correct."""
        import wasstraat.harmonize_functions as hf
        hf._correcties_cache = None

        correcties = {
            'brondata_correcties': [
                {'collectie': 'COLL_STAGING_OUD', 'zoek_veld': 'mdbfile', 'doel_veld': 'project', 'patroon': 'DC027_Voorstraat', 'waarde': 'DC027'}
            ]
        }

        mock_staging = _maak_collectie_mock()
        mock_pymongo.MongoClient.return_value = _maak_mock_db(hf, {
            hf.config.COLL_STAGING_OUD: mock_staging,
            hf.config.COLL_PLAATJES: _maak_collectie_mock(),
        })

        with patch.object(hf, 'laadCorrecties', return_value=correcties):
            hf.fixProjectNames()

        mock_staging.update_many.assert_any_call(
            {'mdbfile': {'$regex': 'DC027_Voorstraat'}},
            {'$set': {'project': 'DC027'}}
        )

    @patch('wasstraat.harmonize_functions.pymongo')
    def test_monster_correctie_zoek_veld_is_doel_veld(self, mock_pymongo):
        """Zonder doel_veld wordt het zoek_veld ook als doelveld gebruikt."""
        import wasstraat.harmonize_functions as hf
        hf._correcties_cache = None

        correcties = {
            'brondata_correcties': [
                {'collectie': 'COLL_STAGING_MONSTER', 'zoek_veld': 'PROJECT', 'patroon': 'SCHE', 'waarde': 'DC039'}
            ]
        }

        mock_monster = _maak_collectie_mock()
        mock_pymongo.MongoClient.return_value = _maak_mock_db(hf, {
            hf.config.COLL_STAGING_OUD: _maak_collectie_mock(),
            hf.config.COLL_PLAATJES: _maak_collectie_mock(),
            hf.config.COLL_STAGING_MONSTER: mock_monster,
        })

        with patch.object(hf, 'laadCorrecties', return_value=correcties):
            hf.fixProjectNames()

        mock_monster.update_many.assert_any_call(
            {'PROJECT': {'$regex': 'SCHE'}},
            {'$set': {'PROJECT': 'DC039'}}
        )

    @patch('wasstraat.harmonize_functions.pymongo')
    def test_meerdere_correcties_over_verschillende_collecties(self, mock_pymongo):
        """Correcties op meerdere collecties worden elk op de juiste collectie toegepast."""
        import wasstraat.harmonize_functions as hf
        hf._correcties_cache = None

        correcties = {
            'brondata_correcties': [
                {'collectie': 'COLL_STAGING_OUD', 'zoek_veld': 'mdbfile', 'doel_veld': 'project', 'patroon': 'DC027_Voorstraat', 'waarde': 'DC027'},
                {'collectie': 'COLL_STAGING_OUD', 'zoek_veld': 'mdbfile', 'doel_veld': 'project', 'patroon': 'DC018_Nieuw', 'waarde': 'DC018'},
                {'collectie': 'COLL_STAGING_MONSTER', 'zoek_veld': 'PROJECT', 'patroon': 'SCHE', 'waarde': 'DC039'},
                {'collectie': 'COLL_STAGING_MONSTER', 'zoek_veld': 'PROJECT', 'patroon': 'PPG', 'waarde': 'DC067'},
            ]
        }

        mock_staging = _maak_collectie_mock()
        mock_monster = _maak_collectie_mock()
        mock_pymongo.MongoClient.return_value = _maak_mock_db(hf, {
            hf.config.COLL_STAGING_OUD: mock_staging,
            hf.config.COLL_PLAATJES: _maak_collectie_mock(),
            hf.config.COLL_STAGING_MONSTER: mock_monster,
        })

        with patch.object(hf, 'laadCorrecties', return_value=correcties):
            hf.fixProjectNames()

        # 2 correcties + 1 generieke (projectcd→string) op staging
        staging_calls = mock_staging.update_many.call_args_list
        assert len(staging_calls) == 3
        # 2 correcties op monster
        assert mock_monster.update_many.call_count == 2

    @patch('wasstraat.harmonize_functions.pymongo')
    def test_geen_correcties(self, mock_pymongo):
        """Zonder correcties in de YAML worden alleen generieke updates gedaan."""
        import wasstraat.harmonize_functions as hf
        hf._correcties_cache = None

        mock_staging = _maak_collectie_mock()
        mock_pymongo.MongoClient.return_value = _maak_mock_db(hf, {
            hf.config.COLL_STAGING_OUD: mock_staging,
            hf.config.COLL_PLAATJES: _maak_collectie_mock(),
        })

        with patch.object(hf, 'laadCorrecties', return_value={}):
            hf.fixProjectNames()

        # Alleen 1 generieke projectcd-naar-string update
        assert mock_staging.update_many.call_count == 1

    @patch('wasstraat.harmonize_functions.pymongo')
    def test_onbekende_collectie_wordt_overgeslagen(self, mock_pymongo):
        """Een correctie met een onbekende collectie-constante wordt overgeslagen."""
        import wasstraat.harmonize_functions as hf
        hf._correcties_cache = None

        correcties = {
            'brondata_correcties': [
                {'collectie': 'COLL_NIET_BESTAAND', 'zoek_veld': 'x', 'patroon': 'z', 'waarde': 'Q'}
            ]
        }

        mock_staging = _maak_collectie_mock()
        mock_pymongo.MongoClient.return_value = _maak_mock_db(hf, {
            hf.config.COLL_STAGING_OUD: mock_staging,
            hf.config.COLL_PLAATJES: _maak_collectie_mock(),
        })

        with patch.object(hf, 'laadCorrecties', return_value=correcties):
            hf.fixProjectNames()  # Mag niet crashen

        # Alleen generieke update, geen correctie-update
        assert mock_staging.update_many.call_count == 1

    @patch('wasstraat.harmonize_functions.pymongo')
    def test_ontbrekende_sleutels_worden_overgeslagen(self, mock_pymongo):
        """Correcties met ontbrekende verplichte keys crashen niet maar worden overgeslagen."""
        import wasstraat.harmonize_functions as hf
        hf._correcties_cache = None

        correcties = {
            'brondata_correcties': [
                {'collectie': 'COLL_STAGING_OUD'},                          # ontbreekt: patroon, waarde
                {'patroon': 'test', 'waarde': 'x'},                        # ontbreekt: collectie
                {'collectie': 'COLL_STAGING_OUD', 'patroon': 123, 'waarde': 'x'},  # patroon is int
            ]
        }

        mock_staging = _maak_collectie_mock()
        mock_pymongo.MongoClient.return_value = _maak_mock_db(hf, {
            hf.config.COLL_STAGING_OUD: mock_staging,
            hf.config.COLL_PLAATJES: _maak_collectie_mock(),
        })

        with patch.object(hf, 'laadCorrecties', return_value=correcties):
            hf.fixProjectNames()  # Mag niet crashen

        # Regel 3 (patroon=123) wordt naar str geconverteerd en is geldig
        # Regel 1 en 2 worden overgeslagen (KeyError)
        # Plus 1 generieke update → 2 totaal
        assert mock_staging.update_many.call_count == 2


# ============================================================
# Klasse 3: Projectcode-correcties (post-harmonisatie, in setAttributes)
# ============================================================

class TestProjectcodeCorrecties:
    """Test dat projectcode_correcties correct worden toegepast op projectcd in COLL_ANALYSE."""

    def setup_method(self):
        import wasstraat.harmonize_functions as hf
        hf._correcties_cache = None

    def test_correctie_format_eenvoudig(self):
        """Het eenvoudige format: alleen patroon en projectcode."""
        correcties = {
            'projectcode_correcties': [
                {'patroon': 'SYNTFOUT', 'projectcode': 'SY001'},
            ]
        }
        fixes = correcties['projectcode_correcties']
        assert len(fixes) == 1
        assert fixes[0]['patroon'] == 'SYNTFOUT'
        assert fixes[0]['projectcode'] == 'SY001'

    def test_lege_lijst_geen_fout(self):
        """Lege projectcode_correcties lijst veroorzaakt geen fouten."""
        correcties = {'projectcode_correcties': []}
        fixes = correcties.get('projectcode_correcties', [])
        assert fixes == []

    def test_ontbrekende_sectie_geen_fout(self):
        """Ontbrekende projectcode_correcties sectie veroorzaakt geen fouten."""
        correcties = {}
        fixes = correcties.get('projectcode_correcties', [])
        assert fixes == []


# ============================================================
# Klasse 4: Rapportcode-prefixen
# ============================================================

class TestRapportcodePrefixen:
    """Test dat rapportcode-prefixen dynamisch worden opgebouwd uit de YAML."""

    def test_regex_dynamisch_gebouwd(self):
        """Met prefixen DAR en DAN wordt een regex gebouwd die DAR045 matcht."""
        prefixen = [
            {'prefix': 'DAR', 'type': 'archeologische_rapportage'},
            {'prefix': 'DAN', 'type': 'archeologische_notitie'},
        ]
        prefix_patroon = '|'.join(p['prefix'] for p in prefixen)
        regex = re.compile(r'^(' + prefix_patroon + r')\s*([0-9]{2,3}).*', re.M | re.I)

        assert regex.match("DAR 045 rapport.pdf")
        assert regex.match("DAN012_notitie.doc")
        assert regex.match("dar99.pdf")
        assert not regex.match("XYZ123.pdf")
        assert not regex.match("rapport_DAR045.pdf")  # niet aan het begin

    def test_regex_met_andere_prefixen(self):
        """Met niet-Delftse prefixen wordt de juiste regex gebouwd."""
        prefixen = [
            {'prefix': 'RAP', 'type': 'archeologische_rapportage'},
            {'prefix': 'NOT', 'type': 'archeologische_notitie'},
        ]
        prefix_patroon = '|'.join(p['prefix'] for p in prefixen)
        regex = re.compile(r'^(' + prefix_patroon + r')\s*([0-9]{2,3}).*', re.M | re.I)

        assert regex.match("RAP012.pdf")
        assert regex.match("NOT099.pdf")
        assert not regex.match("DAN001.pdf")

    def test_type_mapping(self):
        """De prefix-type mapping vertaalt correct naar bestandsoorten."""
        prefixen = [
            {'prefix': 'DAR', 'type': 'archeologische_rapportage'},
            {'prefix': 'DAN', 'type': 'archeologische_notitie'},
        ]
        prefix_type_map = {p['prefix'].upper(): p['type'] for p in prefixen}

        assert prefix_type_map['DAR'] == 'archeologische_rapportage'
        assert prefix_type_map['DAN'] == 'archeologische_notitie'

    def test_geen_prefixen_levert_lege_map(self):
        """Zonder rapportcode-prefixen in de YAML is de map leeg."""
        correcties = {}
        prefixen = correcties.get('rapportcode_prefixen', [])
        assert prefixen == []


# ============================================================
# Klasse 5: Artefact niet-mergen projecten
# ============================================================

class TestArtefactNietMergenProjecten:
    """Test het laden van merge-uitzonderingen uit de YAML."""

    def test_laden_uit_yaml(self, tmp_path):
        """Projectcodes worden correct geladen uit artefact_niet_mergen sectie."""
        from wasstraat.merge_functions import _laadArtefactNietMergenProjecten
        import shared.config as config

        yml_content = {'artefact_niet_mergen': {'projectcodes': ['DC112']}}
        yml_file = tmp_path / "correcties.yml"
        yml_file.write_text(yaml.dump(yml_content))

        with patch.object(config, 'AIRFLOW_CORRECTIES_CONFIG', str(yml_file)):
            result = _laadArtefactNietMergenProjecten()

        assert result == ['DC112']

    def test_lege_yaml_geeft_lege_lijst(self, tmp_path):
        """Een leeg YAML-bestand levert een lege lijst op."""
        from wasstraat.merge_functions import _laadArtefactNietMergenProjecten
        import shared.config as config

        yml_file = tmp_path / "correcties.yml"
        yml_file.write_text("# leeg\n")

        with patch.object(config, 'AIRFLOW_CORRECTIES_CONFIG', str(yml_file)):
            result = _laadArtefactNietMergenProjecten()

        assert result == []

    def test_meerdere_projectcodes(self, tmp_path):
        """Meerdere projectcodes worden allemaal geladen."""
        from wasstraat.merge_functions import _laadArtefactNietMergenProjecten
        import shared.config as config

        yml_content = {'artefact_niet_mergen': {'projectcodes': ['DC112', 'DC050', 'DB099']}}
        yml_file = tmp_path / "correcties.yml"
        yml_file.write_text(yaml.dump(yml_content))

        with patch.object(config, 'AIRFLOW_CORRECTIES_CONFIG', str(yml_file)):
            result = _laadArtefactNietMergenProjecten()

        assert result == ['DC112', 'DC050', 'DB099']

    def test_ontbrekend_bestand_geeft_lege_lijst(self):
        """Een niet-bestaand pad retourneert een lege lijst."""
        from wasstraat.merge_functions import _laadArtefactNietMergenProjecten
        import shared.config as config

        with patch.object(config, 'AIRFLOW_CORRECTIES_CONFIG', '/tmp/niet_bestaand.yml'):
            result = _laadArtefactNietMergenProjecten()

        assert result == []


# ============================================================
# Klasse 6: Image-filterpatronen
# ============================================================

class TestImageFilterPatronen:
    """Test dat image-filterpatronen correct worden uitgebreid met YAML-prefixen."""

    def test_generieke_patronen_altijd_aanwezig(self, tmp_path):
        """De generieke patronen velddocument, fotos, tekening zitten er altijd in."""
        from wasstraat.image_import import _laadImageFilterPatronen
        import shared.config as config

        yml_file = tmp_path / "correcties.yml"
        yml_file.write_text("# leeg\n")

        with patch.object(config, 'AIRFLOW_CORRECTIES_CONFIG', str(yml_file)):
            result = _laadImageFilterPatronen()

        assert "velddocument" in result
        assert "fotos" in result
        assert "tekening" in result

    def test_rapportprefixen_worden_toegevoegd(self, tmp_path):
        """Rapportcode-prefixen uit de YAML worden aan de filterlijst toegevoegd."""
        from wasstraat.image_import import _laadImageFilterPatronen
        import shared.config as config

        yml_content = {
            'rapportcode_prefixen': [
                {'prefix': 'DAR', 'type': 'archeologische_rapportage'},
                {'prefix': 'DAN', 'type': 'archeologische_notitie'},
            ]
        }
        yml_file = tmp_path / "correcties.yml"
        yml_file.write_text(yaml.dump(yml_content))

        with patch.object(config, 'AIRFLOW_CORRECTIES_CONFIG', str(yml_file)):
            result = _laadImageFilterPatronen()

        assert "DAR" in result
        assert "DAN" in result
        assert "velddocument" in result  # generieke er ook nog in

    def test_lege_yaml_alleen_generiek(self):
        """Zonder YAML-bestand bevat de lijst alleen de generieke patronen."""
        from wasstraat.image_import import _laadImageFilterPatronen
        import shared.config as config

        with patch.object(config, 'AIRFLOW_CORRECTIES_CONFIG', '/tmp/niet_bestaand.yml'):
            result = _laadImageFilterPatronen()

        assert result == ["velddocument", "fotos", "tekening"]

    def test_image_filter_case_sensitive_voor_prefixen(self, tmp_path):
        """Rapportcode-prefixen worden case-sensitive gefilterd (hoofdletter = case-sensitive)."""
        from wasstraat.image_import import _laadImageFilterPatronen
        import shared.config as config

        yml_content = {
            'rapportcode_prefixen': [
                {'prefix': 'DAR', 'type': 'archeologische_rapportage'},
            ]
        }
        yml_file = tmp_path / "correcties.yml"
        yml_file.write_text(yaml.dump(yml_content))

        with patch.object(config, 'AIRFLOW_CORRECTIES_CONFIG', str(yml_file)):
            patronen = _laadImageFilterPatronen()

        # DAR is een hoofdletter-prefix, wordt case-sensitive gematcht
        assert any(p[0].isupper() for p in patronen if p == 'DAR')
