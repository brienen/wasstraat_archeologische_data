"""
Testscript voor reparatie 7: Robuustere kolomselectie in mergeFotoinfo.

Probleem: In merge_functions.py wordt een harde kolomlijst gebruikt om het
resultaat-DataFrame te filteren. Als een kolom ontbreekt in de brondata,
crasht de code met een KeyError. Daarnaast bevat de kolomlijst 'subnr'
twee keer.

Het materiaal-veld wordt op een onveilige manier gecombineerd:
    df_merge.apply(lambda x: util.firstValue(x['materiaal'], x['materiaalgroep'])
        if 'materiaal' in df_merge.columns else x['materiaalgroep'], axis=1)
Dit werkt niet correct: de `if` wordt eenmaal geevalueerd op DataFrame-niveau,
maar de lambda wordt per rij aangeroepen.

De reparatie:
- Controleert de aanwezigheid van kolommen VOOR selectie
- Logt ontbrekende kolommen als warning
- Verwijdert de dubbele 'subnr'
- Veilige materiaal-kolom combinatie

Gebruik: pytest tests/unit/test_fix_7_kolomselectie.py -v
"""

import unittest
import os
import py_compile
import re

import pandas as pd
import numpy as np


BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def read_source(relative_path):
    """Lees bronbestand als string."""
    full_path = os.path.join(BASE_DIR, relative_path)
    with open(full_path, 'r', encoding='utf-8') as f:
        return f.read()


class TestFix7_Kolomselectie_StaticAnalysis(unittest.TestCase):
    """Statische analyse van de kolomselectie in mergeFotoinfo."""

    @classmethod
    def setUpClass(cls):
        cls.source = read_source('../airflow_app/dags/wasstraat/merge_functions.py')
        match = re.search(
            r'(def mergeFotoinfo\(\):.*?)(?=\ndef |\Z)',
            cls.source, re.DOTALL)
        cls.func_source = match.group(1) if match else ''

    def test_syntax_valid(self):
        """Verifieer dat het bestand geldige Python-syntax heeft."""
        path = os.path.join(BASE_DIR, '../airflow_app/dags/wasstraat/merge_functions.py')
        try:
            py_compile.compile(path, doraise=True)
        except py_compile.PyCompileError as e:
            self.fail(f"Syntax-fout in merge_functions.py: {e}")

    def test_function_exists(self):
        """Verifieer dat mergeFotoinfo bestaat."""
        self.assertIn('def mergeFotoinfo(', self.source,
            "Functie mergeFotoinfo ontbreekt")

    def test_safe_column_selection(self):
        """Verifieer dat kolommen veilig geselecteerd worden (met beschikbaarheidscheck)."""
        # Er moet een constructie zijn die ontbrekende kolommen filtert
        self.assertTrue(
            'available_col' in self.func_source
            or 'if c in df_merge.columns' in self.func_source
            or '[c for c in' in self.func_source,
            "Veilige kolomselectie ontbreekt. "
            "Kolommen moeten gecontroleerd worden op aanwezigheid voor selectie.")

    def test_no_duplicate_subnr(self):
        """Verifieer dat 'subnr' niet meer dubbel voorkomt in de kolomlijst."""
        # Zoek alle kolomlijsten in de functie
        # Patroon: [...'subnr'...] als Python list
        lists = re.findall(r'\[([^\]]*)\]', self.func_source)
        for lst_str in lists:
            if "'subnr'" in lst_str or '"subnr"' in lst_str:
                count = lst_str.count("'subnr'") + lst_str.count('"subnr"')
                self.assertLessEqual(count, 1,
                    f"'subnr' komt {count}x voor in een kolomlijst (moet 1x zijn)")

    def test_materiaal_column_safe(self):
        """Verifieer dat de materiaal-kolom veilig wordt samengesteld."""
        # Er moet een check zijn op de aanwezigheid van zowel 'materiaal' als 'materiaalgroep'
        self.assertTrue(
            "'materiaal' in df_merge.columns" in self.func_source
            or '"materiaal" in df_merge.columns' in self.func_source,
            "Check op aanwezigheid van 'materiaal' kolom ontbreekt")
        self.assertTrue(
            "'materiaalgroep' in df_merge.columns" in self.func_source
            or '"materiaalgroep" in df_merge.columns' in self.func_source,
            "Check op aanwezigheid van 'materiaalgroep' kolom ontbreekt")

    def test_missing_columns_logged(self):
        """Verifieer dat ontbrekende kolommen gelogd worden."""
        # Bij de kolomselectie in het else-blok (met koppeldata)
        # moet er een warning zijn voor ontbrekende kolommen
        self.assertTrue(
            'missing' in self.func_source.lower() or 'ontbrekend' in self.func_source.lower()
            or 'logger.warning' in self.func_source,
            "Logging van ontbrekende kolommen ontbreekt")


class TestFix7_Kolomselectie_Functional(unittest.TestCase):
    """Functionele tests voor de veilige kolomselectie logica."""

    def _safe_select_columns(self, df, required_cols):
        """Simuleer de gerepareerde kolomselectie."""
        available = [c for c in required_cols if c in df.columns]
        missing = set(required_cols) - set(available)
        return df[available], missing

    def test_all_columns_present(self):
        """Test als alle kolommen aanwezig zijn."""
        df = pd.DataFrame({
            '_id': [1, 2],
            'fileName': ['a.jpg', 'b.jpg'],
            'soort': ['Bestand', 'Bestand'],
            'projectcd': ['DC001', 'DC002'],
        })
        required = ['_id', 'fileName', 'soort', 'projectcd']
        result, missing = self._safe_select_columns(df, required)
        self.assertEqual(len(missing), 0)
        self.assertEqual(list(result.columns), required)

    def test_some_columns_missing(self):
        """Test als sommige kolommen ontbreken (crashte voorheen)."""
        df = pd.DataFrame({
            '_id': [1],
            'fileName': ['a.jpg'],
            'soort': ['Bestand'],
        })
        required = ['_id', 'fileName', 'soort', 'projectcd', 'materiaal', 'putnr']
        result, missing = self._safe_select_columns(df, required)

        self.assertEqual(set(missing), {'projectcd', 'materiaal', 'putnr'})
        self.assertEqual(list(result.columns), ['_id', 'fileName', 'soort'])

    def test_no_columns_present(self):
        """Test als geen enkele gevraagde kolom aanwezig is."""
        df = pd.DataFrame({'onbekend': [1, 2]})
        required = ['_id', 'fileName', 'soort']
        result, missing = self._safe_select_columns(df, required)

        self.assertEqual(len(result.columns), 0)
        self.assertEqual(set(missing), {'_id', 'fileName', 'soort'})

    def test_empty_dataframe(self):
        """Test met een leeg DataFrame."""
        df = pd.DataFrame(columns=['_id', 'fileName'])
        required = ['_id', 'fileName', 'soort']
        result, missing = self._safe_select_columns(df, required)

        self.assertEqual(set(missing), {'soort'})
        self.assertEqual(len(result), 0)

    def test_old_code_crashes_on_missing_column(self):
        """Demonstreer dat de oude harde kolomselectie crasht bij ontbrekende kolommen."""
        df = pd.DataFrame({
            '_id': [1],
            'fileName': ['a.jpg'],
            'soort': ['Bestand'],
        })
        hard_columns = ['_id', 'fileName', 'soort', 'materiaal']

        with self.assertRaises(KeyError,
                msg="De oude code met harde kolomlijst crasht bij ontbrekende kolommen"):
            _ = df[hard_columns]

    def test_column_order_preserved(self):
        """Verifieer dat de kolomvolgorde behouden blijft."""
        df = pd.DataFrame({
            'soort': ['Bestand'],
            '_id': [1],
            'fileName': ['a.jpg'],
        })
        required = ['_id', 'fileName', 'soort']
        result, _ = self._safe_select_columns(df, required)
        self.assertEqual(list(result.columns), ['_id', 'fileName', 'soort'])


class TestFix7_MateriaalKolom(unittest.TestCase):
    """Tests voor de veilige materiaal-kolom combinatie."""

    def _safe_materiaal(self, df):
        """Simuleer de gerepareerde materiaal-kolom logica."""
        if 'materiaal' in df.columns and 'materiaalgroep' in df.columns:
            df['materiaal'] = df.apply(
                lambda x: x['materiaal'] if pd.notna(x['materiaal']) and x['materiaal']
                else x['materiaalgroep'], axis=1)
        elif 'materiaalgroep' in df.columns:
            df['materiaal'] = df['materiaalgroep']
        elif 'materiaal' not in df.columns:
            df['materiaal'] = None
        return df

    def test_both_columns_present(self):
        """Test als zowel materiaal als materiaalgroep aanwezig zijn."""
        df = pd.DataFrame({
            'materiaal': ['Keramiek', None, ''],
            'materiaalgroep': ['Aardewerk', 'Metaal', 'Glas'],
        })
        result = self._safe_materiaal(df)
        self.assertEqual(result['materiaal'].tolist(), ['Keramiek', 'Metaal', 'Glas'])

    def test_only_materiaalgroep(self):
        """Test als alleen materiaalgroep aanwezig is."""
        df = pd.DataFrame({
            'materiaalgroep': ['Aardewerk', 'Metaal'],
        })
        result = self._safe_materiaal(df)
        self.assertEqual(result['materiaal'].tolist(), ['Aardewerk', 'Metaal'])

    def test_only_materiaal(self):
        """Test als alleen materiaal aanwezig is (materiaalgroep ontbreekt)."""
        df = pd.DataFrame({
            'materiaal': ['Keramiek', 'Glas'],
        })
        result = self._safe_materiaal(df)
        self.assertEqual(result['materiaal'].tolist(), ['Keramiek', 'Glas'])

    def test_neither_column(self):
        """Test als geen van beide kolommen aanwezig is."""
        df = pd.DataFrame({
            '_id': [1, 2],
        })
        result = self._safe_materiaal(df)
        self.assertIn('materiaal', result.columns)
        self.assertTrue(all(v is None for v in result['materiaal']))

    def test_materiaal_nan_uses_materiaalgroep(self):
        """Test dat NaN in materiaal wordt opgevangen door materiaalgroep."""
        df = pd.DataFrame({
            'materiaal': [np.nan, 'Keramiek'],
            'materiaalgroep': ['Aardewerk', 'Metaal'],
        })
        result = self._safe_materiaal(df)
        self.assertEqual(result['materiaal'].iloc[0], 'Aardewerk')
        self.assertEqual(result['materiaal'].iloc[1], 'Keramiek')


if __name__ == '__main__':
    unittest.main(verbosity=2)
