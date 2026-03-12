"""
Testscript voor reparatie 5: NoneType-fout in extractImagedataFromFileNames.

Probleem: In setAttributes_functions.py worden chained .get() calls gebruikt
op file_dict, waardoor een NoneType-fout optreedt als een directory niet in
file_dict voorkomt. Bijvoorbeeld:
    file_dict.get(foto.get('directory')).get('projectcd')
Als file_dict.get() None retourneert, faalt de tweede .get() met AttributeError.

Dit testscript test zowel de huidige code (statische analyse) als de
functionele logica van de voorgestelde reparatie.

Gebruik: pytest tests/unit/test_fix_5_nonetype_foto.py -v
"""

import unittest
import os
import py_compile
import re


BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def read_source(relative_path):
    """Lees bronbestand als string."""
    full_path = os.path.join(BASE_DIR, relative_path)
    with open(full_path, 'r', encoding='utf-8') as f:
        return f.read()


class TestFix5_NoneTypeFoto_StaticAnalysis(unittest.TestCase):
    """Statische analyse van extractImagedataFromFileNames."""

    @classmethod
    def setUpClass(cls):
        cls.source = read_source('../airflow_app/dags/wasstraat/setAttributes_functions.py')
        match = re.search(
            r'(def extractImagedataFromFileNames\(\):.*?)(?=\ndef |\Z)',
            cls.source, re.DOTALL)
        cls.func_source = match.group(1) if match else ''

    def test_syntax_valid(self):
        """Verifieer dat het bestand geldige Python-syntax heeft."""
        path = os.path.join(BASE_DIR, '../airflow_app/dags/wasstraat/setAttributes_functions.py')
        try:
            py_compile.compile(path, doraise=True)
        except py_compile.PyCompileError as e:
            self.fail(f"Syntax-fout in setAttributes_functions.py: {e}")

    def test_function_exists(self):
        """Verifieer dat extractImagedataFromFileNames bestaat."""
        self.assertIn('def extractImagedataFromFileNames(', self.source,
            "Functie extractImagedataFromFileNames ontbreekt")

    def test_no_unsafe_chained_get(self):
        """Verifieer dat er geen onveilige chained .get().get() aanroepen zijn.

        Het patroon file_dict.get(x).get(y) crasht als de eerste .get() None retourneert.
        De veilige variant is: eerst het resultaat opslaan en checken op None.
        """
        lines = self.func_source.split('\n')
        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped.startswith('#'):
                continue
            # Zoek naar: file_dict.get(...).get(...) — inclusief geneste haakjes
            if re.search(r'file_dict\.get\(.*?\)\.get\(', stripped):
                self.fail(
                    f"Onveilige chained .get() op regel {i+1}: '{stripped}'\n"
                    "Als file_dict.get() None retourneert, "
                    "crasht de tweede .get() met AttributeError.\n"
                    "Gebruik: dir_info = file_dict.get(...); if dir_info is None: continue")

    def test_none_check_present(self):
        """Verifieer dat er een None-check is na file_dict lookup."""
        self.assertTrue(
            'is None' in self.func_source or 'is not None' in self.func_source
            or 'if dir_info' in self.func_source or 'if not dir_info' in self.func_source,
            "Geen None-check gevonden na file_dict lookup. "
            "Er moet gecontroleerd worden of de directory in file_dict voorkomt.")

    def test_continue_on_missing_directory(self):
        """Verifieer dat foto's met ontbrekende directory overgeslagen worden."""
        self.assertIn('continue', self.func_source,
            "'continue' ontbreekt — foto's met ontbrekende directory moeten overgeslagen worden")

    def test_warning_logged_for_missing_directory(self):
        """Verifieer dat er een warning wordt gelogd bij ontbrekende directory."""
        self.assertTrue(
            'logger.warning' in self.func_source or 'logger.warn' in self.func_source,
            "Er wordt geen warning gelogd bij ontbrekende directory-info. "
            "Dit maakt het onmogelijk om te achterhalen welke foto's overgeslagen zijn.")

    def test_safe_filename_access_in_except(self):
        """Verifieer dat het except-blok .get() gebruikt voor fileName (niet direct key access).

        Als een foto-document geen 'fileName' veld heeft, crasht foto['fileName']
        met KeyError. Gebruik foto.get('fileName', 'onbekend') in het except-blok.
        """
        # Zoek het except-blok in de functie
        lines = self.func_source.split('\n')
        in_except = False
        for line in lines:
            stripped = line.strip()
            if stripped.startswith('except'):
                in_except = True
                continue
            if in_except:
                if "foto['fileName']" in stripped and '.get(' not in stripped:
                    self.fail(
                        f"Onveilige key access foto['fileName'] in except-blok: '{stripped}'\n"
                        "Gebruik foto.get('fileName', 'onbekend') om een tweede crash te voorkomen.")
                if stripped and not stripped.startswith('#') and not stripped.startswith('except'):
                    if re.match(r'^(def |class |$)', stripped):
                        in_except = False


class TestFix5_NoneTypeFoto_Functional(unittest.TestCase):
    """Functionele tests voor de veilige file_dict lookup logica."""

    def setUp(self):
        """Stel testdata op die de werkelijke situatie simuleert."""
        self.file_dict = {
            'DC001/objectfoto/aardewerk': {
                'projectcd': 'DC001',
                'fotosoort': 'Objectfoto',
                'materiaal': 'aardewerk',
            },
            'DC002/opgravingsfoto': {
                'projectcd': 'DC002',
                'fotosoort': 'Opgravingsfoto',
            },
        }

    def _safe_lookup(self, foto, file_dict):
        """Simuleer de gerepareerde lookup-logica uit voorstel 5."""
        dir_info = file_dict.get(foto.get('directory'))
        if dir_info is None:
            return None  # directory niet gevonden
        result = {}
        if not foto.get('projectcd'):
            result['projectcd'] = dir_info.get('projectcd')
        if not foto.get('fototype'):
            result['fototype'] = dir_info.get('fototype')
        result['materiaal'] = dir_info.get('materiaal')
        result['fotosoort'] = dir_info.get('fotosoort')
        return result

    def test_known_directory(self):
        """Test lookup met een bekende directory."""
        foto = {'_id': 1, 'fileName': 'foto1.jpg', 'directory': 'DC001/objectfoto/aardewerk'}
        result = self._safe_lookup(foto, self.file_dict)
        self.assertIsNotNone(result)
        self.assertEqual(result['projectcd'], 'DC001')
        self.assertEqual(result['fotosoort'], 'Objectfoto')
        self.assertEqual(result['materiaal'], 'aardewerk')

    def test_unknown_directory_returns_none(self):
        """Test dat een onbekende directory None retourneert (geen crash)."""
        foto = {'_id': 2, 'fileName': 'foto2.jpg', 'directory': 'ONBEKEND/pad'}
        result = self._safe_lookup(foto, self.file_dict)
        self.assertIsNone(result,
            "Bij een onbekende directory moet None worden geretourneerd, geen crash")

    def test_missing_directory_field(self):
        """Test dat een foto zonder directory-veld None retourneert."""
        foto = {'_id': 3, 'fileName': 'foto3.jpg'}
        result = self._safe_lookup(foto, self.file_dict)
        self.assertIsNone(result,
            "Bij een ontbrekend directory-veld moet None worden geretourneerd")

    def test_none_directory_value(self):
        """Test dat directory=None correct wordt afgehandeld."""
        foto = {'_id': 4, 'fileName': 'foto4.jpg', 'directory': None}
        result = self._safe_lookup(foto, self.file_dict)
        self.assertIsNone(result,
            "Bij directory=None moet None worden geretourneerd")

    def test_existing_projectcd_not_overwritten(self):
        """Test dat een bestaande projectcd niet wordt overschreven."""
        foto = {'_id': 5, 'fileName': 'foto5.jpg',
                'directory': 'DC001/objectfoto/aardewerk',
                'projectcd': 'BESTAAND'}
        result = self._safe_lookup(foto, self.file_dict)
        self.assertIsNotNone(result)
        # projectcd mag niet gezet worden als het er al is
        self.assertNotIn('projectcd', result,
            "Bestaande projectcd mag niet overschreven worden")

    def test_demonstrate_old_bug(self):
        """Demonstreer dat de oude chained .get() crasht bij onbekende directory."""
        foto = {'_id': 6, 'fileName': 'foto6.jpg', 'directory': 'ONBEKEND/pad'}
        file_dict = self.file_dict

        # Oude code: file_dict.get(foto.get('directory')).get('projectcd')
        with self.assertRaises(AttributeError,
                msg="De oude code zou hier moeten crashen met AttributeError"):
            _ = file_dict.get(foto.get('directory')).get('projectcd')

    def test_empty_file_dict(self):
        """Test dat een lege file_dict geen crash veroorzaakt."""
        foto = {'_id': 7, 'fileName': 'foto7.jpg', 'directory': 'DC001/iets'}
        result = self._safe_lookup(foto, {})
        self.assertIsNone(result)

    def test_materiaal_none_when_not_in_dir_info(self):
        """Test dat materiaal None is als het niet in dir_info staat."""
        foto = {'_id': 8, 'fileName': 'foto8.jpg', 'directory': 'DC002/opgravingsfoto'}
        result = self._safe_lookup(foto, self.file_dict)
        self.assertIsNotNone(result)
        self.assertIsNone(result['materiaal'],
            "materiaal moet None zijn voor opgravingsfoto's (geen materiaal in dir_info)")


if __name__ == '__main__':
    unittest.main(verbosity=2)
