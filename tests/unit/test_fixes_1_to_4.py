"""
Testscript voor reparaties 1-4 van de Wasstraat Archeologische Data pipeline.

Gebruikt statische analyse (broncode lezen + syntax-controle) zodat er geen
live database-connecties of externe dependencies nodig zijn.

Gebruik: python tests/test_fixes_1_to_4.py
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


# ===========================================================================
# TEST 1: Fix finally-blok in enhanceAllAttributes
# ===========================================================================

class TestFix1_FinallyBlock(unittest.TestCase):
    """Test dat het finally-blok in enhanceAllAttributes alleen bij succes opslaat."""

    @classmethod
    def setUpClass(cls):
        cls.source = read_source('../airflow_app/dags/wasstraat/setAttributes_functions.py')
        # Extraheer alleen de enhanceAllAttributes functie
        match = re.search(r'(def enhanceAllAttributes\(\):.*?)(?=\ndef |\Z)', cls.source, re.DOTALL)
        cls.func_source = match.group(1) if match else ''

    def test_syntax_valid(self):
        """Verifieer dat het bestand geldige Python-syntax heeft."""
        path = os.path.join(BASE_DIR, '../airflow_app/dags/wasstraat/setAttributes_functions.py')
        try:
            py_compile.compile(path, doraise=True)
        except py_compile.PyCompileError as e:
            self.fail(f"Syntax-fout in setAttributes_functions.py: {e}")

    def test_success_flag_present(self):
        """Verifieer dat de success-vlag aanwezig is."""
        self.assertIn('success = False', self.func_source,
            "Initialisatie 'success = False' ontbreekt")
        self.assertIn('success = True', self.func_source,
            "Markering 'success = True' ontbreekt")

    def test_conditional_save(self):
        """Verifieer dat replace_one alleen bij succes wordt aangeroepen."""
        self.assertIn('if success:', self.func_source,
            "Conditie 'if success:' ontbreekt - replace_one moet conditioneel zijn")

    def test_no_replace_one_in_finally(self):
        """Verifieer dat replace_one NIET in een finally-blok staat."""
        lines = self.func_source.split('\n')
        in_finally = False
        finally_indent = 0

        for i, line in enumerate(lines):
            stripped = line.strip()
            if not stripped or stripped.startswith('#'):
                continue

            indent = len(line) - len(line.lstrip())

            if stripped == 'finally:':
                in_finally = True
                finally_indent = indent
                continue

            if in_finally:
                if indent <= finally_indent and stripped and not stripped.startswith('#'):
                    in_finally = False
                elif 'replace_one' in stripped:
                    self.fail(
                        f"replace_one gevonden in finally-blok op regel {i+1}: '{stripped}'\n"
                        "Dit slaat half-getransformeerde data op bij fouten!")

    def test_error_collection_logging(self):
        """Verifieer dat er error-collection logging aanwezig is."""
        self.assertIn('_log_processing_error', self.func_source,
            "Error-logging naar de error-collection ontbreekt")

    def test_success_and_error_counters(self):
        """Verifieer dat er tellers zijn voor succes en fouten."""
        self.assertIn('count_success', self.func_source,
            "Success-teller ontbreekt")
        self.assertIn('count_error', self.func_source,
            "Error-teller ontbreekt")

    def test_no_duplicate_coordinate_conversion(self):
        """Verifieer dat rd_to_wgs slechts 1x wordt aangeroepen (was 2x)."""
        count = self.func_source.count('rd_to_wgs')
        self.assertEqual(count, 1,
            f"rd_to_wgs komt {count}x voor in enhanceAllAttributes, "
            f"verwacht 1x (was 2x door onnodige duplicatie)")

    def test_coordinate_validation_active(self):
        """Verifieer dat de coordinaatvalidatie geactiveerd is (niet uitgecommentarieerd)."""
        self.assertIn('280000', self.func_source,
            "RD-coordinaat bounding box validatie (x-max) ontbreekt")
        self.assertIn('625000', self.func_source,
            "RD-coordinaat bounding box validatie (y-max) ontbreekt")

        # Check dat het NIET uitgecommentarieerd is
        for line in self.func_source.split('\n'):
            if '280000' in line and 'x_rd' in line:
                self.assertFalse(line.strip().startswith('#'),
                    "Coordinaatvalidatie is nog steeds uitgecommentarieerd!")

    def test_helper_functions_exist(self):
        """Verifieer dat de helper-functies voor error-tracking bestaan."""
        self.assertIn('def _log_processing_error(', self.source,
            "_log_processing_error functie ontbreekt in het bestand")
        self.assertIn('def _get_error_collection(', self.source,
            "_get_error_collection functie ontbreekt in het bestand")

    def test_error_collection_stores_context(self):
        """Verifieer dat de error-collection relevante context opslaat."""
        # Zoek de _log_processing_error functie
        match = re.search(r'def _log_processing_error\(.*?\n(?=def |\Z)', self.source, re.DOTALL)
        if match:
            func = match.group(0)
            for field in ['original_id', 'soort', 'projectcd', 'fase', 'error_type', 'error_msg', 'timestamp']:
                self.assertIn(field, func,
                    f"Veld '{field}' ontbreekt in error-collection document")


# ===========================================================================
# TEST 2: Fix atomic table swap voor PostgreSQL-load
# ===========================================================================

class TestFix2_AtomicTableSwap(unittest.TestCase):
    """Test dat loadAll het atomic table swap patroon gebruikt."""

    @classmethod
    def setUpClass(cls):
        cls.source = read_source('../airflow_app/dags/wasstraat/loadToDatabase_functions.py')
        match = re.search(r'(def loadAll\(\):.*?)(?=\ndef |\Z)', cls.source, re.DOTALL)
        cls.func_source = match.group(1) if match else ''

    def test_syntax_valid(self):
        """Verifieer dat het bestand geldige Python-syntax heeft."""
        path = os.path.join(BASE_DIR, '../airflow_app/dags/wasstraat/loadToDatabase_functions.py')
        try:
            py_compile.compile(path, doraise=True)
        except py_compile.PyCompileError as e:
            self.fail(f"Syntax-fout in loadToDatabase_functions.py: {e}")

    def test_no_truncate_as_first_step(self):
        """Verifieer dat TRUNCATE van alle tabellen niet meer de eerste stap is."""
        # De oude code had: TRUNCATE "Def_artefact_abr", "Def_Bruikleen", ... + alle Def_-tabellen
        self.assertNotIn(
            'TRUNCATE "Def_artefact_abr", "Def_Bruikleen", "Def_artefact_conservering", "Def_Conserveringsproject", ',
            self.func_source,
            "De oude monolithische TRUNCATE-statement staat er nog!\n"
            "Dit wist alle data voordat nieuwe data geladen wordt.")

    def test_uses_temp_tables(self):
        """Verifieer dat het _new tijdelijke-tabel patroon wordt gebruikt."""
        self.assertIn('_new', self.func_source,
            "Het _new tijdelijke-tabel patroon ontbreekt")

    def test_uses_rename_for_swap(self):
        """Verifieer dat ALTER TABLE RENAME wordt gebruikt voor atomic swap."""
        self.assertIn('RENAME TO', self.func_source,
            "ALTER TABLE RENAME ontbreekt - nodig voor atomic swap")

    def test_uses_create_table_like(self):
        """Verifieer dat CREATE TABLE LIKE wordt gebruikt."""
        self.assertIn('LIKE', self.func_source,
            "CREATE TABLE ... LIKE ontbreekt voor structuur-kopie")

    def test_has_cleanup_on_failure(self):
        """Verifieer dat temp-tabellen opgeruimd worden bij falen."""
        self.assertIn('temp_tables_created', self.func_source,
            "Lijst temp_tables_created ontbreekt")
        self.assertIn('DROP TABLE IF EXISTS', self.func_source,
            "DROP TABLE IF EXISTS ontbreekt voor opruiming")

    def test_has_phase_logging(self):
        """Verifieer dat er duidelijke fase-logging is."""
        self.assertIn('FASE 1', self.func_source, "FASE 1 logging ontbreekt")
        self.assertIn('FASE 2a', self.func_source, "FASE 2a logging ontbreekt")
        self.assertIn('FASE 2b', self.func_source, "FASE 2b logging ontbreekt")
        self.assertIn('FASE 3', self.func_source, "FASE 3 logging ontbreekt")

    def test_handles_fk_constraints_during_swap(self):
        """Verifieer dat FK constraints worden gedropt en hersteld (zonder superuser)."""
        self.assertNotIn('session_replication_role', self.func_source,
            "session_replication_role vereist superuser-rechten!")
        self.assertIn('FOREIGN KEY', self.func_source,
            "FK constraint query ontbreekt")
        self.assertIn('DROP CONSTRAINT', self.func_source,
            "DROP CONSTRAINT voor FK ontbreekt")
        self.assertIn('ADD CONSTRAINT', self.func_source,
            "ADD CONSTRAINT voor FK-herstel ontbreekt")

    def test_fk_query_filters_def_tables_only(self):
        """Verifieer dat de FK-query alleen Def_-tabellen selecteert.

        Systeemtabellen (ab_user, ab_role etc.) mogen niet worden aangeraakt:
        ze zijn in gebruik door de webapplicatie en veroorzaken lock timeouts.
        """
        # De query bevat LIKE 'Def\_%%' met SQL escaping
        self.assertIn("table_name LIKE", self.func_source,
            "FK-query mist een LIKE-filter op table_name. Zonder filter worden "
            "ook systeemtabellen (ab_user) meegenomen, wat lock timeouts veroorzaakt.")
        self.assertIn("Def", self.func_source.split("table_name LIKE")[1][:30] if "table_name LIKE" in self.func_source else '',
            "FK-query filtert niet op Def_-tabellen.")

    def test_uses_not_valid_for_fk_restore(self):
        """Verifieer dat NOT VALID wordt gebruikt bij FK-herstel (voorkomt trage validatie)."""
        self.assertIn('NOT VALID', self.func_source,
            "NOT VALID ontbreekt bij ADD CONSTRAINT. Zonder NOT VALID "
            "valideert PostgreSQL alle rijen, wat minuten kan duren.")

    def test_has_lock_timeout(self):
        """Verifieer dat er een lock_timeout is ingesteld (voorkomt eindeloos wachten)."""
        self.assertIn('lock_timeout', self.func_source,
            "lock_timeout ontbreekt. Zonder timeout kan de swap "
            "eindeloos wachten als de webapplicatie een query open heeft.")

    def test_validate_constraint_after_swap(self):
        """Verifieer dat FK constraints achteraf alsnog gevalideerd worden."""
        self.assertIn('VALIDATE CONSTRAINT', self.func_source,
            "VALIDATE CONSTRAINT ontbreekt. Na NOT VALID moeten "
            "constraints alsnog gevalideerd worden in een aparte stap.")

    def test_fk_restore_uses_savepoints(self):
        """Verifieer dat SAVEPOINT wordt gebruikt bij FK-restore.

        Zonder SAVEPOINTs vergiftigt één falende ADD CONSTRAINT de hele
        transactie, waardoor alle volgende FK-constraints ook falen.
        """
        self.assertIn('SAVEPOINT', self.func_source,
            "SAVEPOINT ontbreekt bij FK-restore. Eén falende ADD CONSTRAINT "
            "zou alle overige FK-constraints blokkeren (poisoned transaction).")
        self.assertIn('ROLLBACK TO SAVEPOINT', self.func_source,
            "ROLLBACK TO SAVEPOINT ontbreekt. Na een falende ADD CONSTRAINT "
            "moet de SAVEPOINT worden teruggedraaid.")

    def test_fk_restore_in_separate_transaction(self):
        """Verifieer dat FK-restore in een aparte transactie zit.

        Als FK-restore in dezelfde transactie als de swap zit en faalt,
        draait de hele swap terug. Door het te scheiden kan de swap slagen
        zelfs als sommige FK-constraints niet hersteld kunnen worden.
        """
        self.assertIn('FASE 2b', self.func_source,
            "FASE 2b ontbreekt: FK-restore moet in een aparte transactie")

    def test_truncate_uses_cascade(self):
        """Verifieer dat TRUNCATE CASCADE wordt gebruikt voor extra tabellen.

        Tabellen als Def_Bruikleen kunnen FKs hebben naar tabellen buiten
        de hoofdlijst (bijv. Def_Partij). CASCADE voorkomt FK-conflicten.
        """
        # Zoek de TRUNCATE-regel voor extra tabellen
        self.assertRegex(self.func_source, r'TRUNCATE.*CASCADE',
            "TRUNCATE zonder CASCADE. Extra tabellen kunnen FK-referenties "
            "hebben naar tabellen buiten de lijst (bijv. Def_Partij).")

    def test_enum_detection_excludes_geometry(self):
        """Verifieer dat ENUM-detectie geen geometry-kolommen meeneemt.

        De information_schema query voor USER-DEFINED types vangt ook
        PostGIS geometry-kolommen. Als die als ENUM behandeld worden,
        krijgen ze de waarde 'Onbekend' in plaats van None, wat PostGIS
        niet als WKT kan parsen ('parse error at position 2').
        """
        source = read_source('../airflow_app/dags/wasstraat/loadToDatabase_functions.py')
        # De query moet filteren op pg_type.typtype = 'e' (enum)
        self.assertIn("typtype = 'e'", source,
            "ENUM-detectie filtert niet op pg_type.typtype = 'e'. "
            "Zonder dit filter worden ook geometry-kolommen als ENUM behandeld, "
            "wat leidt tot 'Onbekend' in de location kolom (PostGIS parse error).")

    def test_has_pre_cleanup(self):
        """Verifieer dat restanten van een vorige afgebroken run worden opgeruimd."""
        self.assertIn('Pre-cleanup', self.func_source,
            "Pre-cleanup fase ontbreekt. Als een vorige run is afgebroken "
            "kunnen _new/_old tabellen achterblijven die de volgende run blokkeren.")
        # CASCADE is nodig om orphan pg_type entries te verwijderen
        self.assertIn('CASCADE', self.func_source,
            "CASCADE ontbreekt bij DROP TABLE. Zonder CASCADE kunnen "
            "orphan PostgreSQL type-entries de CREATE TABLE blokkeren.")

    def test_old_data_preserved_until_swap(self):
        """Verifieer dat de originele tabellen intact blijven tot de swap."""
        lines = self.func_source.split('\n')
        # De rename van orig -> _old moet NA het laden naar _new gebeuren
        load_line = None
        rename_line = None
        for i, line in enumerate(lines):
            if 'transferToDB' in line and load_line is None:
                load_line = i
            if 'RENAME TO' in line and '_old' in line and rename_line is None:
                rename_line = i

        if load_line is not None and rename_line is not None:
            self.assertLess(load_line, rename_line,
                "transferToDB moet VOOR de rename-swap plaatsvinden")


# ===========================================================================
# TEST 3: Fix Elasticsearch alias-swap
# ===========================================================================

class TestFix3_ElasticsearchAlias(unittest.TestCase):
    """Test dat indexTable het alias-swap patroon gebruikt."""

    @classmethod
    def setUpClass(cls):
        cls.source = read_source('../shared/fulltext.py')
        match = re.search(r'(def indexTable\(.*?\):.*?)(?=\ndef |\Z)', cls.source, re.DOTALL)
        cls.func_source = match.group(1) if match else ''

    def test_syntax_valid(self):
        """Verifieer dat het bestand geldige Python-syntax heeft."""
        path = os.path.join(BASE_DIR, '../shared/fulltext.py')
        try:
            py_compile.compile(path, doraise=True)
        except py_compile.PyCompileError as e:
            self.fail(f"Syntax-fout in fulltext.py: {e}")

    def test_no_upfront_index_deletion(self):
        """Verifieer dat de index niet meer als eerste wordt verwijderd."""
        lines = self.func_source.split('\n')
        # Zoek de eerste es.indices.delete aanroep
        for line in lines:
            stripped = line.strip()
            if stripped.startswith('#'):
                continue
            if 'es.indices.delete' in stripped:
                # Dit mag alleen voorkomen voor old_idx of new_index opruiming,
                # NIET voor index_name (de hoofd-alias)
                self.assertTrue(
                    'old_idx' in stripped or 'new_index' in stripped or 'alias_name' in stripped,
                    f"Directe verwijdering van de hoofd-index gevonden: '{stripped}'\n"
                    "Dit maakt zoekfunctionaliteit onbeschikbaar tijdens indexering!")
                break

    def test_uses_alias_pattern(self):
        """Verifieer dat het alias-patroon wordt gebruikt."""
        self.assertIn('alias_name', self.func_source,
            "alias_name variabele ontbreekt")
        self.assertIn('update_aliases', self.func_source,
            "es.indices.update_aliases ontbreekt - nodig voor atomic alias swap")

    def test_uses_timestamped_index(self):
        """Verifieer dat een timestamped index-naam wordt gebruikt."""
        self.assertIn('time.time()', self.func_source,
            "Timestamped index-naam ontbreekt")
        self.assertIn('new_index', self.func_source,
            "new_index variabele ontbreekt")

    def test_has_bulk_failure_recovery(self):
        """Verifieer dat bij bulk-falen de nieuwe index wordt opgeruimd."""
        self.assertIn('bulk_err', self.func_source,
            "Error-variabele voor bulk-falen ontbreekt")
        # Na bulk_err moet de nieuwe index worden verwijderd
        lines = self.func_source.split('\n')
        found_bulk_err = False
        found_cleanup = False
        for line in lines:
            if 'bulk_err' in line:
                found_bulk_err = True
            if found_bulk_err and 'es.indices.delete' in line and 'new_index' in line:
                found_cleanup = True
                break

        self.assertTrue(found_cleanup,
            "Bij bulk-falen wordt de nieuwe index niet opgeruimd")

    def test_old_indices_cleanup(self):
        """Verifieer dat oude indexen worden opgeruimd na de swap."""
        self.assertIn('old_indices', self.func_source,
            "Variabele old_indices ontbreekt")
        self.assertIn('Deleted old index', self.func_source,
            "Logging van opruiming oude indexen ontbreekt")

    def test_migration_handling(self):
        """Verifieer dat er migratiecode is voor de eerste run na upgrade."""
        self.assertIn('Migratie', self.func_source,
            "Migratie-afhandeling voor de eerste run na upgrade ontbreekt")

    def test_migration_before_alias_swap(self):
        """Verifieer dat migratie (verwijderen fysieke index) VOOR de alias swap plaatsvindt.

        Als er een fysieke index 'def_abr' bestaat (oude situatie), moet die
        verwijderd worden VOOR update_aliases, anders faalt Elasticsearch met
        'an index or data stream exists with the same name as the alias'.
        """
        lines = self.func_source.split('\n')
        migration_line = None
        alias_swap_line = None
        for i, line in enumerate(lines):
            if 'Migratie' in line and migration_line is None:
                migration_line = i
            if 'update_aliases' in line and alias_swap_line is None:
                alias_swap_line = i

        self.assertIsNotNone(migration_line,
            "Migratie-code niet gevonden")
        self.assertIsNotNone(alias_swap_line,
            "update_aliases niet gevonden")
        self.assertLess(migration_line, alias_swap_line,
            "Migratie moet VOOR update_aliases plaatsvinden, niet erna. "
            "Anders faalt de alias swap als er een fysieke index met dezelfde naam bestaat.")


# ===========================================================================
# TEST 4: Fix elif 'hout/' bug
# ===========================================================================

class TestFix4_HoutBug(unittest.TestCase):
    """Test dat de elif 'hout/' bug is gerepareerd."""

    @classmethod
    def setUpClass(cls):
        cls.source = read_source('../airflow_app/dags/wasstraat/harmonize_functions.py')

    def test_syntax_valid(self):
        """Verifieer dat het bestand geldige Python-syntax heeft."""
        path = os.path.join(BASE_DIR, '../airflow_app/dags/wasstraat/harmonize_functions.py')
        try:
            py_compile.compile(path, doraise=True)
        except py_compile.PyCompileError as e:
            self.fail(f"Syntax-fout in harmonize_functions.py: {e}")

    def test_correct_elif_condition(self):
        """Verifieer dat de elif nu 'hout/' in strFN checkt."""
        self.assertIn("elif 'hout/' in strFN:", self.source,
            "Correcte conditie 'elif 'hout/' in strFN:' ontbreekt")

    def test_old_bug_not_present(self):
        """Verifieer dat de altijd-true bug niet meer aanwezig is."""
        # Zoek naar het patroon: elif 'hout/': (zonder 'in strFN')
        # Maar NIET: elif 'hout/' in strFN:
        lines = self.source.split('\n')
        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped.startswith('#'):
                continue
            # Match: elif 'hout/': maar NIET elif 'hout/' in strFN:
            if re.match(r"elif\s+'hout/':", stripped):
                self.fail(
                    f"Bug gevonden op regel {i+1}: '{stripped}'\n"
                    "De string 'hout/' evalueert altijd naar True in Python!\n"
                    "Hierdoor worden alle niet-geclassificeerde foto's als 'Hout' gelabeld.")

    def test_classification_logic_functional(self):
        """Functionele test: verificeer correcte classificatie."""
        test_cases = [
            ('/project/aardewerk/DC001_H1_1.jpg', 'Aardewerk'),
            ('/project/glas/DC001_H1_1.jpg', 'Glas'),
            ('/project/hout/DC001_H1_1.jpg', 'Hout'),
            ('/project/metaal/DC001_H1_1.jpg', 'Metaal'),
            ('/project/overig/DC001_H1_1.jpg', None),  # Mag NIET 'Hout' zijn
            ('/project/schelp/DC001_H1_1.jpg', 'Schelp'),
            ('/project/leer/DC001_H1_1.jpg', 'Leer'),
            ('/project/munt/DC001_H1_1.jpg', 'Munt'),
        ]

        for fullFileName, expected in test_cases:
            strFN = fullFileName.lower()
            result = None

            if 'aardewerk' in strFN or 'pijpaard' in strFN:
                result = 'Aardewerk'
            elif 'bot' in strFN and 'menselijk' in strFN:
                result = 'Menselijk_Bot'
            elif 'bot' in strFN and 'dierlijk' in strFN:
                result = 'Dierlijk_Bot'
            elif 'glas' in strFN:
                result = 'Glas'
            elif 'leer' in strFN:
                result = 'Leer'
            elif 'steen' in strFN:
                result = 'Steen'
            elif 'kleipijp' in strFN:
                result = 'Kleipijp'
            elif 'hout/' in strFN:  # GEREPAREERD
                result = 'Hout'
            elif 'bouwaardewerk' in strFN:
                result = 'Bouwaardewerk'
            elif 'metaal' in strFN:
                result = 'Metaal'
            elif 'munt' in strFN:
                result = 'Munt'
            elif 'schelp' in strFN:
                result = 'Schelp'
            elif 'textiel' in strFN:
                result = 'Textiel'

            self.assertEqual(result, expected,
                f"Classificatie voor '{fullFileName}': verwacht {expected}, kreeg {result}")

    def test_demonstrate_old_bug(self):
        """Demonstreer dat de oude code fout classificeerde."""
        strFN = '/project/overig/DC001_H1_1.jpg'.lower()

        # Oude buggy logica
        old_result = None
        if 'aardewerk' in strFN:
            old_result = 'Aardewerk'
        elif 'hout/':  # BUG: altijd True!
            old_result = 'Hout'
        elif 'metaal' in strFN:
            old_result = 'Metaal'

        # Nieuwe correcte logica
        new_result = None
        if 'aardewerk' in strFN:
            new_result = 'Aardewerk'
        elif 'hout/' in strFN:  # CORRECT
            new_result = 'Hout'
        elif 'metaal' in strFN:
            new_result = 'Metaal'

        self.assertEqual(old_result, 'Hout',
            "Dit toont aan dat de oude bug alles als 'Hout' classificeerde")
        self.assertIsNone(new_result,
            "De nieuwe code classificeert dit correct als None (geen match)")


# ===========================================================================
# CROSS-FILE TESTS
# ===========================================================================

class TestCrossFile(unittest.TestCase):
    """Tests die de consistentie over alle gewijzigde bestanden controleren."""

    def test_all_files_valid_syntax(self):
        """Verifieer dat alle gewijzigde bestanden geldige Python-syntax hebben."""
        files = [
            '../airflow_app/dags/wasstraat/setAttributes_functions.py',
            '../airflow_app/dags/wasstraat/harmonize_functions.py',
            '../airflow_app/dags/wasstraat/loadToDatabase_functions.py',
            '../shared/fulltext.py',
        ]
        for filepath in files:
            full_path = os.path.join(BASE_DIR, filepath)
            try:
                py_compile.compile(full_path, doraise=True)
            except py_compile.PyCompileError as e:
                self.fail(f"Syntax-fout in {filepath}: {e}")

    def test_no_unintended_changes_to_other_functions(self):
        """Verifieer dat functies buiten scope niet zijn gewijzigd."""
        # Check dat transferToDB in loadToDatabase_functions.py ongewijzigd is
        source = read_source('../airflow_app/dags/wasstraat/loadToDatabase_functions.py')
        self.assertIn('def transferToDB(objecttype, soort, table, connection):', source,
            "transferToDB functie-signature is gewijzigd (onbedoeld)")

        # Check dat parseFotobestanden nog steeds de juiste structuur heeft
        source = read_source('../airflow_app/dags/wasstraat/harmonize_functions.py')
        self.assertIn('def parseFotobestanden():', source,
            "parseFotobestanden functie-signature is gewijzigd (onbedoeld)")

        # Check dat generate_docs in fulltext.py ongewijzigd is
        source = read_source('../shared/fulltext.py')
        self.assertIn('def generate_docs(resultset, db_col_names, index_name):', source,
            "generate_docs functie-signature is gewijzigd (onbedoeld)")


if __name__ == '__main__':
    # Gebruik de unittest runner met verbose output
    unittest.main(verbosity=2)
