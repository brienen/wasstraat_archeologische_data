"""
Testscript voor reparatie 6: Coordinaatvalidatie reactiveren.

Probleem: In setAttributes_functions.py was de coordinaatvalidatie
uitgecommentarieerd, waardoor ongeldige RD-coordinaten stilzwijgend
geconverteerd werden naar WGS84. Dit leverde punten op buiten Nederland.

De reparatie:
- Activeert de validatie met bounding box Nederland (x: 10000-280000, y: 300000-625000)
- Voegt ValueError/TypeError afhandeling toe voor niet-numerieke coordinaten
- Verwijdert de dubbele coordinaatconversie (rd_to_wgs werd 2x aangeroepen)

Gebruik: pytest tests/unit/test_fix_6_coordinaatvalidatie.py -v
"""

import unittest
import os
import py_compile
import re
import sys


BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def read_source(relative_path):
    """Lees bronbestand als string."""
    full_path = os.path.join(BASE_DIR, relative_path)
    with open(full_path, 'r', encoding='utf-8') as f:
        return f.read()


class TestFix6_CoordinaatValidatie_StaticAnalysis(unittest.TestCase):
    """Statische analyse van de coordinaatvalidatie in enhanceAllAttributes."""

    @classmethod
    def setUpClass(cls):
        cls.source = read_source('../airflow_app/dags/wasstraat/setAttributes_functions.py')
        match = re.search(
            r'(def enhanceAllAttributes\(\):.*?)(?=\ndef |\Z)',
            cls.source, re.DOTALL)
        cls.func_source = match.group(1) if match else ''

    def test_syntax_valid(self):
        """Verifieer dat het bestand geldige Python-syntax heeft."""
        path = os.path.join(BASE_DIR, '../airflow_app/dags/wasstraat/setAttributes_functions.py')
        try:
            py_compile.compile(path, doraise=True)
        except py_compile.PyCompileError as e:
            self.fail(f"Syntax-fout in setAttributes_functions.py: {e}")

    def test_validation_not_commented_out(self):
        """Verifieer dat de coordinaatvalidatie NIET uitgecommentarieerd is."""
        lines = self.func_source.split('\n')
        for line in lines:
            stripped = line.strip()
            # Zoek naar de validatielogica
            if '280000' in stripped and ('x_rd' in stripped or 'xcoor_rd' in stripped):
                self.assertFalse(stripped.startswith('#'),
                    f"Coordinaatvalidatie is uitgecommentarieerd: '{stripped}'")
                return
        # Als we hier komen, is de validatie er helemaal niet
        self.fail("Coordinaatvalidatie met bounding box (280000) niet gevonden")

    def test_bounding_box_values_correct(self):
        """Verifieer de correcte bounding box waarden voor Nederland."""
        # x-bereik: 10000 tot 280000 (west tot oost)
        self.assertIn('10000', self.func_source,
            "RD x-minimum (10000) ontbreekt in validatie")
        self.assertIn('280000', self.func_source,
            "RD x-maximum (280000) ontbreekt in validatie")
        # y-bereik: 300000 tot 625000 (zuid tot noord)
        self.assertIn('300000', self.func_source,
            "RD y-minimum (300000) ontbreekt in validatie")
        self.assertIn('625000', self.func_source,
            "RD y-maximum (625000) ontbreekt in validatie")

    def test_invalid_coords_deleted(self):
        """Verifieer dat ongeldige coordinaten verwijderd worden uit het document."""
        self.assertIn("del doc['xcoor_rd']", self.func_source,
            "del doc['xcoor_rd'] ontbreekt bij ongeldige coordinaten")
        self.assertIn("del doc['ycoor_rd']", self.func_source,
            "del doc['ycoor_rd'] ontbreekt bij ongeldige coordinaten")

    def test_error_logged_for_invalid_coords(self):
        """Verifieer dat er een error/warning wordt gelogd bij ongeldige coordinaten."""
        self.assertTrue(
            'logError' in self.func_source or 'logger.error' in self.func_source
            or 'logger.warning' in self.func_source,
            "Er wordt geen fout gelogd bij ongeldige coordinaten")

    def test_valueerror_handled(self):
        """Verifieer dat ValueError wordt afgevangen (niet-numerieke coordinaten)."""
        self.assertIn('ValueError', self.func_source,
            "ValueError afhandeling ontbreekt voor niet-numerieke coordinaten")

    def test_typeerror_handled(self):
        """Verifieer dat TypeError wordt afgevangen."""
        self.assertIn('TypeError', self.func_source,
            "TypeError afhandeling ontbreekt")

    def test_single_coordinate_conversion(self):
        """Verifieer dat rd_to_wgs slechts 1x wordt aangeroepen (was 2x gedupliceerd)."""
        count = self.func_source.count('rd_to_wgs')
        self.assertEqual(count, 1,
            f"rd_to_wgs komt {count}x voor, verwacht 1x "
            f"(oude code had een dubbele conversie)")

    def test_float_conversion_before_validation(self):
        """Verifieer dat coordinaten naar float geconverteerd worden voor de validatie."""
        # float() moet aangeroepen worden op de coordinaten
        self.assertTrue(
            "float(doc['xcoor_rd'])" in self.func_source
            or 'float(x_rd)' in self.func_source
            or 'x_rd = float(' in self.func_source,
            "float() conversie ontbreekt voor x-coordinaat")


class TestFix6_CoordinaatValidatie_Functional(unittest.TestCase):
    """Functionele tests voor de coordinaatvalidatielogica."""

    # Bounding box Nederland in RD
    X_MIN, X_MAX = 10000, 280000
    Y_MIN, Y_MAX = 300000, 625000

    def _validate_rd_coords(self, x_str, y_str):
        """Simuleer de gerepareerde coordinaatvalidatie.

        Returns:
            dict met coor_wgs en coor_rd bij geldige coordinaten,
            None bij ongeldige coordinaten,
            'error' bij niet-numerieke invoer.
        """
        try:
            x = float(x_str)
            y = float(y_str)
        except (ValueError, TypeError):
            return 'error'

        if x < self.X_MIN or x > self.X_MAX or y < self.Y_MIN or y > self.Y_MAX:
            return None

        return {'x': x, 'y': y, 'valid': True}

    # --- Geldige coordinaten ---

    def test_amsterdam_valid(self):
        """Amsterdam (121687, 487484) moet geldig zijn."""
        result = self._validate_rd_coords('121687', '487484')
        self.assertIsNotNone(result)
        self.assertNotEqual(result, 'error')

    def test_rotterdam_valid(self):
        """Rotterdam (92565, 437428) moet geldig zijn."""
        result = self._validate_rd_coords('92565', '437428')
        self.assertIsNotNone(result)

    def test_maastricht_valid(self):
        """Maastricht (176331, 317462) moet geldig zijn."""
        result = self._validate_rd_coords('176331', '317462')
        self.assertIsNotNone(result)

    def test_delft_valid(self):
        """Delft (circa 84000, 449000) moet geldig zijn."""
        result = self._validate_rd_coords('84000', '449000')
        self.assertIsNotNone(result)

    # --- Grenswaarden ---

    def test_boundary_minimum_valid(self):
        """Exact op het minimum (10000, 300000) moet geldig zijn."""
        result = self._validate_rd_coords('10000', '300000')
        self.assertIsNotNone(result)
        self.assertNotEqual(result, 'error')

    def test_boundary_maximum_valid(self):
        """Exact op het maximum (280000, 625000) moet geldig zijn."""
        result = self._validate_rd_coords('280000', '625000')
        self.assertIsNotNone(result)

    def test_just_below_x_minimum(self):
        """Net onder x-minimum (9999) moet ongeldig zijn."""
        result = self._validate_rd_coords('9999', '450000')
        self.assertIsNone(result,
            "x=9999 ligt buiten Nederland en moet afgekeurd worden")

    def test_just_above_x_maximum(self):
        """Net boven x-maximum (280001) moet ongeldig zijn."""
        result = self._validate_rd_coords('280001', '450000')
        self.assertIsNone(result,
            "x=280001 ligt buiten Nederland en moet afgekeurd worden")

    def test_just_below_y_minimum(self):
        """Net onder y-minimum (299999) moet ongeldig zijn."""
        result = self._validate_rd_coords('150000', '299999')
        self.assertIsNone(result,
            "y=299999 ligt buiten Nederland en moet afgekeurd worden")

    def test_just_above_y_maximum(self):
        """Net boven y-maximum (625001) moet ongeldig zijn."""
        result = self._validate_rd_coords('150000', '625001')
        self.assertIsNone(result,
            "y=625001 ligt buiten Nederland en moet afgekeurd worden")

    # --- Duidelijk ongeldige coordinaten ---

    def test_zero_coordinates(self):
        """Coordinaten (0, 0) moeten ongeldig zijn."""
        result = self._validate_rd_coords('0', '0')
        self.assertIsNone(result,
            "Coordinaten (0, 0) liggen buiten Nederland")

    def test_negative_coordinates(self):
        """Negatieve coordinaten moeten ongeldig zijn."""
        result = self._validate_rd_coords('-50000', '-100000')
        self.assertIsNone(result,
            "Negatieve coordinaten liggen buiten Nederland")

    def test_very_large_coordinates(self):
        """Extreem grote coordinaten moeten ongeldig zijn."""
        result = self._validate_rd_coords('999999', '999999')
        self.assertIsNone(result,
            "Extreem grote coordinaten liggen buiten Nederland")

    # --- Niet-numerieke invoer ---

    def test_non_numeric_x(self):
        """Niet-numerieke x-coordinaat moet een error geven."""
        result = self._validate_rd_coords('abc', '450000')
        self.assertEqual(result, 'error',
            "Niet-numerieke x moet een error opleveren, geen crash")

    def test_non_numeric_y(self):
        """Niet-numerieke y-coordinaat moet een error geven."""
        result = self._validate_rd_coords('150000', 'xyz')
        self.assertEqual(result, 'error')

    def test_none_x(self):
        """None als x-coordinaat moet een error geven."""
        result = self._validate_rd_coords(None, '450000')
        self.assertEqual(result, 'error',
            "None als coordinaat moet afgevangen worden, geen crash")

    def test_empty_string(self):
        """Lege string als coordinaat moet een error geven."""
        result = self._validate_rd_coords('', '450000')
        self.assertEqual(result, 'error',
            "Lege string als coordinaat moet een error opleveren")

    # --- Coordinaatconversie test (met echte rd_to_wgs) ---

    def test_rd_to_wgs_amsterdam(self):
        """Verifieer dat RD-naar-WGS84 conversie correct is voor Amsterdam."""
        # Voeg het pad toe zodat we rijksdriehoek kunnen importeren
        dags_dir = os.path.join(BASE_DIR, '..', 'airflow_app', 'dags')
        if dags_dir not in sys.path:
            sys.path.insert(0, dags_dir)

        try:
            from wasstraat.rijksdriehoek import rd_to_wgs
            result = rd_to_wgs(121687, 487484)
            # Amsterdam: lat ~52.374, lon ~4.898
            self.assertAlmostEqual(result[0], 52.374, places=2,
                msg="Latitude Amsterdam klopt niet")
            self.assertAlmostEqual(result[1], 4.898, places=2,
                msg="Longitude Amsterdam klopt niet")
        except ImportError:
            self.skipTest("rijksdriehoek module niet beschikbaar")

    def test_rd_to_wgs_maastricht(self):
        """Verifieer RD-naar-WGS84 conversie voor Maastricht (zuidgrens)."""
        dags_dir = os.path.join(BASE_DIR, '..', 'airflow_app', 'dags')
        if dags_dir not in sys.path:
            sys.path.insert(0, dags_dir)

        try:
            from wasstraat.rijksdriehoek import rd_to_wgs
            result = rd_to_wgs(176331, 317462)
            # Maastricht: lat ~50.847, lon ~5.690
            self.assertAlmostEqual(result[0], 50.847, places=2,
                msg="Latitude Maastricht klopt niet")
            self.assertAlmostEqual(result[1], 5.690, places=2,
                msg="Longitude Maastricht klopt niet")
        except ImportError:
            self.skipTest("rijksdriehoek module niet beschikbaar")


if __name__ == '__main__':
    unittest.main(verbosity=2)
