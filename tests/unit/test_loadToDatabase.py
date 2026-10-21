"""Unit tests voor loadToDatabase_functions.py (psycopg2-versie).

Test de pure Python helper-functies zonder database-connecties.
"""
import pytest
from datetime import date
from unittest.mock import MagicMock, patch, call

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../airflow_app/dags'))

from wasstraat.loadToDatabase_functions import (
    parsePgUri,
    convertToInt,
    convertToFloat,
    convertToDatePure,
    isNanOrEmpty,
    transformRow,
    insertBatch,
    getColumnMetadata,
    getEnumColumns,
)


# ============================================================
# TestParsePgUri
# ============================================================

@pytest.mark.unit
class TestParsePgUri:
    """Test URI parsing naar psycopg2 connect-parameters."""

    def test_standaard_uri(self):
        result = parsePgUri('postgresql://user:pass@localhost:5432/mydb')
        assert result['host'] == 'localhost'
        assert result['port'] == 5432
        assert result['dbname'] == 'mydb'
        assert result['user'] == 'user'
        assert result['password'] == 'pass'

    def test_zonder_port(self):
        result = parsePgUri('postgresql://user:pass@dbhost/mydb')
        assert result['host'] == 'dbhost'
        assert result['port'] == 5432  # default
        assert result['dbname'] == 'mydb'

    def test_met_speciale_tekens_in_wachtwoord(self):
        """URL-encoded wachtwoorden worden door urlparse niet gedecodeerd."""
        result = parsePgUri('postgresql://user:p%40ss%23word@host/db')
        assert result['user'] == 'user'
        # urlparse retourneert URL-encoded wachtwoorden ongewijzigd;
        # psycopg2 accepteert dit niet, dus we moeten unquoten
        assert result['password'] == 'p@ss#word'

    def test_postgres_plus_psycopg2(self):
        """URI met +psycopg2 driver specificatie."""
        result = parsePgUri('postgresql+psycopg2://user:pass@host/db')
        assert result['host'] == 'host'
        assert result['dbname'] == 'db'
        assert result['user'] == 'user'


# ============================================================
# TestConvertToInt
# ============================================================

@pytest.mark.unit
class TestConvertToInt:
    """Test integer-conversie met error coercion."""

    def test_none(self):
        assert convertToInt(None) is None

    def test_geheel_getal(self):
        assert convertToInt(42) == 42

    def test_string_getal(self):
        assert convertToInt("123") == 123

    def test_float_waarde(self):
        assert convertToInt(3.7) == 3

    def test_float_string(self):
        assert convertToInt("3.7") == 3

    def test_nan_string(self):
        assert convertToInt("nan") is None

    def test_ongeldig(self):
        assert convertToInt("abc") is None

    def test_lege_string(self):
        assert convertToInt("") is None

    def test_nul(self):
        assert convertToInt(0) == 0

    def test_negatief(self):
        assert convertToInt(-5) == -5


# ============================================================
# TestConvertToFloat
# ============================================================

@pytest.mark.unit
class TestConvertToFloat:
    """Test float-conversie met error coercion."""

    def test_none(self):
        assert convertToFloat(None) is None

    def test_float(self):
        assert convertToFloat(3.14) == pytest.approx(3.14)

    def test_string_float(self):
        assert convertToFloat("3.14") == pytest.approx(3.14)

    def test_nan_string(self):
        assert convertToFloat("nan") is None

    def test_ongeldig(self):
        assert convertToFloat("abc") is None

    def test_nul(self):
        assert convertToFloat(0.0) == 0.0

    def test_integer_input(self):
        assert convertToFloat(5) == 5.0


# ============================================================
# TestConvertToDatePure
# ============================================================

@pytest.mark.unit
class TestConvertToDatePure:
    """Test datum-conversie zonder pandas."""

    def test_none(self):
        assert convertToDatePure(None) is None

    def test_nan_string(self):
        assert convertToDatePure("nan") is None

    def test_lege_string(self):
        assert convertToDatePure("") is None

    def test_nat_string(self):
        assert convertToDatePure("NaT") is None

    def test_dd_mm_yyyy_streepje(self):
        assert convertToDatePure("15-03-2024") == date(2024, 3, 15)

    def test_dd_mm_yyyy_slash(self):
        assert convertToDatePure("15/03/2024") == date(2024, 3, 15)

    def test_yyyy_mm_dd(self):
        assert convertToDatePure("2024-03-15") == date(2024, 3, 15)

    def test_dd_mm_yy(self):
        result = convertToDatePure("15-03-24")
        assert result is not None
        assert result.month == 3
        assert result.day == 15

    def test_datetime_object(self):
        from datetime import datetime
        dt = datetime(2024, 3, 15, 10, 30, 0)
        assert convertToDatePure(dt) == date(2024, 3, 15)

    def test_date_object(self):
        d = date(2024, 3, 15)
        assert convertToDatePure(d) == d

    def test_ongeldig(self):
        assert convertToDatePure("geen datum") is None


# ============================================================
# TestIsNanOrEmpty
# ============================================================

@pytest.mark.unit
class TestIsNanOrEmpty:
    """Test nan/empty detectie."""

    def test_none(self):
        assert isNanOrEmpty(None) is True

    def test_nan_string(self):
        assert isNanOrEmpty("nan") is True

    def test_empty_string(self):
        assert isNanOrEmpty("") is True

    def test_none_string(self):
        assert isNanOrEmpty("None") is True

    def test_nat_string(self):
        assert isNanOrEmpty("NaT") is True

    def test_gewone_waarde(self):
        assert isNanOrEmpty("hallo") is False

    def test_nul(self):
        assert isNanOrEmpty(0) is False

    def test_getal(self):
        assert isNanOrEmpty(42) is False


# ============================================================
# TestTransformRow
# ============================================================

@pytest.mark.unit
class TestTransformRow:
    """Test rij-transformatie van MongoDB naar PostgreSQL."""

    def _col_lookup(self):
        return {
            'primary_key': {'name': 'primary_key', 'data_type': 'integer', 'udt_name': 'int4', 'max_length': None, 'nullable': False},
            'naam': {'name': 'naam', 'data_type': 'character varying', 'udt_name': 'varchar', 'max_length': 10, 'nullable': True},
            'score': {'name': 'score', 'data_type': 'double precision', 'udt_name': 'float8', 'max_length': None, 'nullable': True},
            'actief': {'name': 'actief', 'data_type': 'boolean', 'udt_name': 'bool', 'max_length': None, 'nullable': True},
            'artefactsoort': {'name': 'artefactsoort', 'data_type': 'USER-DEFINED', 'udt_name': 'discrartefactsoortenum', 'max_length': None, 'nullable': True},
            '_id': {'name': '_id', 'data_type': 'character varying', 'udt_name': 'varchar', 'max_length': 255, 'nullable': True},
        }

    def test_varchar_truncatie(self):
        doc = {'naam': 'Dit is een hele lange naam'}
        result = transformRow(doc, ['naam'], self._col_lookup(), set())
        assert result['naam'] == 'Dit is een'  # max_length=10

    def test_integer_conversie(self):
        doc = {'ID': '42'}
        result = transformRow(doc, ['primary_key'], self._col_lookup(), set())
        assert result['primary_key'] == 42

    def test_float_conversie(self):
        doc = {'score': '3.14'}
        result = transformRow(doc, ['score'], self._col_lookup(), set())
        assert result['score'] == pytest.approx(3.14)

    def test_enum_default_bij_leeg(self):
        doc = {'artefactsoort': ''}
        enum_cols = {'artefactsoort': ['Onbekend', 'Aardewerk', 'Glas']}
        result = transformRow(doc, ['artefactsoort'], self._col_lookup(), enum_cols)
        assert result['artefactsoort'] == 'Onbekend'

    def test_enum_default_bij_none(self):
        doc = {'artefactsoort': None}
        enum_cols = {'artefactsoort': ['Onbekend', 'Aardewerk', 'Glas']}
        result = transformRow(doc, ['artefactsoort'], self._col_lookup(), enum_cols)
        assert result['artefactsoort'] == 'Onbekend'

    def test_enum_fallback_zonder_onbekend(self):
        """Als 'Onbekend' geen geldige ENUM-waarde is, gebruik de eerste waarde."""
        doc = {'bestandsoort': ''}
        enum_cols = {'bestandsoort': ['Bestand', 'Foto', 'Tekening']}
        result = transformRow(doc, ['bestandsoort'], self._col_lookup(), enum_cols)
        assert result['bestandsoort'] == 'Bestand'

    def test_enum_behoudt_waarde(self):
        doc = {'artefactsoort': 'Aardewerk'}
        enum_cols = {'artefactsoort': ['Onbekend', 'Aardewerk', 'Glas']}
        result = transformRow(doc, ['artefactsoort'], self._col_lookup(), enum_cols)
        assert result['artefactsoort'] == 'Aardewerk'

    def test_id_rename(self):
        doc = {'ID': 5, 'naam': 'test'}
        result = transformRow(doc, ['primary_key', 'naam'], self._col_lookup(), {})
        assert result['primary_key'] == 5

    def test_id_string_conversie(self):
        from bson import ObjectId
        oid = ObjectId()
        doc = {'_id': oid}
        result = transformRow(doc, ['_id'], self._col_lookup(), {})
        assert isinstance(result['_id'], str)

    def test_none_waarde(self):
        doc = {'score': None}
        result = transformRow(doc, ['score'], self._col_lookup(), {})
        assert result['score'] is None

    def test_nan_waarde(self):
        doc = {'score': 'nan'}
        result = transformRow(doc, ['score'], self._col_lookup(), {})
        assert result['score'] is None


# ============================================================
# TestGetColumnMetadata
# ============================================================

@pytest.mark.unit
class TestGetColumnMetadata:
    """Test PostgreSQL metadata ophalen via mock cursor."""

    def test_metadata_query(self):
        cursor = MagicMock()
        cursor.fetchall.return_value = [
            ('primary_key', 'integer', 'int4', None, 'NO'),
            ('naam', 'character varying', 'varchar', 100, 'YES'),
        ]

        result = getColumnMetadata(cursor, 'Def_Project')

        cursor.execute.assert_called_once()
        assert len(result) == 2
        assert result[0]['name'] == 'primary_key'
        assert result[0]['data_type'] == 'integer'
        assert result[0]['nullable'] is False
        assert result[1]['name'] == 'naam'
        assert result[1]['max_length'] == 100
        assert result[1]['nullable'] is True


# ============================================================
# TestGetEnumColumns
# ============================================================

@pytest.mark.unit
class TestGetEnumColumns:
    """Test ENUM kolomdetectie via mock cursor."""

    def test_enum_detectie(self):
        cursor = MagicMock()
        cursor.fetchall.return_value = [
            ('artefactsoort', 'Onbekend'),
            ('artefactsoort', 'Aardewerk'),
            ('bestandsoort', 'Bestand'),
            ('bestandsoort', 'Foto'),
        ]

        result = getEnumColumns(cursor, 'Def_Artefact')

        assert set(result.keys()) == {'artefactsoort', 'bestandsoort'}
        assert result['artefactsoort'] == ['Onbekend', 'Aardewerk']
        assert result['bestandsoort'] == ['Bestand', 'Foto']


# ============================================================
# TestInsertBatch
# ============================================================

@pytest.mark.unit
class TestInsertBatch:
    """Test batch insert via mock cursor."""

    @patch('wasstraat.loadToDatabase_functions.psycopg2.extras.execute_values')
    def test_insert_rijen(self, mock_execute_values):
        cursor = MagicMock()
        columns = ['naam', 'score']
        rows = [('test', 3.14), ('test2', 2.71)]

        count = insertBatch(cursor, 'Def_Test', columns, rows)

        assert count == 2
        mock_execute_values.assert_called_once()
        call_args = mock_execute_values.call_args
        assert '"Def_Test"' in call_args[0][1]
        assert '"naam"' in call_args[0][1]
        assert '"score"' in call_args[0][1]

    @patch('wasstraat.loadToDatabase_functions.psycopg2.extras.execute_values')
    def test_lege_lijst(self, mock_execute_values):
        cursor = MagicMock()
        count = insertBatch(cursor, 'Def_Test', ['naam'], [])
        assert count == 0
        mock_execute_values.assert_not_called()



# ============================================================
# TestLoadAllSequences
# ============================================================

@pytest.mark.unit
class TestLoadAllSequences:
    """loadAll herstelt in FASE 3 de sequence van primary_key van elke tabel (zetSequence).

    CREATE TABLE ... LIKE INCLUDING DEFAULTS kopieert de default nextval(...) van
    de oude tabel; die sequence verdwijnt met DROP TABLE <tabel>_old CASCADE en
    de default dus ook. PostgreSQL, MongoDB en het laden zelf worden nagebootst;
    alleen de volgorde van de statements en aanroepen wordt gecontroleerd.
    """

    @staticmethod
    def draaiLoadAll(log, zet_sequence=None, afgeleid_fout=None, migratie_fout=None):
        """Draai loadAll met een nagebootste verbinding; statements en aanroepen komen in log."""
        import wasstraat.loadToDatabase_functions as load

        class Cursor:
            def execute(self, sql, params=None):
                log.append(('sql', sql))

        class Conn:
            def cursor(self):
                return Cursor()

            def commit(self):
                log.append(('commit',))

            def rollback(self):
                log.append(('rollback',))

            def close(self):
                log.append(('close',))

        def logZetSequence(cursor, table):
            log.append(('zetSequence', table))
            return zet_sequence(cursor, table) if zet_sequence else 1

        def nepValideer(cursor, fk_constraints):
            log.append(('valideerFkConstraints',))
            return []

        def nepAfgeleid(cursor):
            log.append(('herberekenAfgeleideVelden',))
            if afgeleid_fout:
                raise afgeleid_fout
            return {}

        def nepMigratie(conn, lock_timeout='30s'):
            log.append(('migreerSchemaGebruikersdata',))
            if migratie_fout:
                raise migratie_fout
            return []

        def logAanroep(naam, resultaat=None):
            def aanroep(*args, **kwargs):
                log.append((naam,))
                return resultaat
            return aanroep

        with patch.object(load, 'getPgConnection', return_value=Conn()), \
                patch.object(load, 'migreerSchemaGebruikersdata', side_effect=nepMigratie), \
                patch.object(load, 'transferToDB'), \
                patch.object(load, 'bepaalVervallenSleutels', side_effect=logAanroep('bepaalVervallenSleutels', {})), \
                patch.object(load, 'leesFkConstraints', return_value=[]), \
                patch.object(load, 'verwijderFkConstraints', side_effect=logAanroep('verwijderFkConstraints')), \
                patch.object(load, 'bepaalVerwijzingen', side_effect=logAanroep('bepaalVerwijzingen', ([], {}))), \
                patch.object(load, 'koppelGebruikersdataLos', side_effect=logAanroep('koppelGebruikersdataLos')), \
                patch.object(load, 'werkGebruikersdataBijNaSwap', side_effect=logAanroep('werkGebruikersdataBijNaSwap')), \
                patch.object(load, 'herstelFkConstraints', return_value=(0, 0)), \
                patch.object(load, 'valideerFkConstraints', side_effect=nepValideer), \
                patch.object(load, 'zetSequence', side_effect=logZetSequence), \
                patch.object(load, 'herberekenAfgeleideVelden', side_effect=nepAfgeleid):
            return load.loadAll()

    def test_zetSequence_voor_elke_tabel(self):
        from wasstraat.loadToDatabase_functions import LOAD_TABELLEN
        log = []
        self.draaiLoadAll(log)
        tabellen = [regel[1] for regel in log if regel[0] == 'zetSequence']
        assert tabellen == list(LOAD_TABELLEN)

    def test_na_opruimen_old_en_voor_laatste_commit(self):
        """zetSequence draait na de DROP van alle _old-tabellen, in de transactie van FASE 3."""
        log = []
        self.draaiLoadAll(log)
        drops_old = [i for i, regel in enumerate(log)
                     if regel[0] == 'sql' and regel[1].startswith('DROP TABLE IF EXISTS "')
                     and regel[1].endswith('_old" CASCADE')]
        renames = [i for i, regel in enumerate(log) if regel[0] == 'sql' and 'RENAME TO' in regel[1]]
        # De DROP's van FASE 3 zijn die na de swap (de laatste RENAME)
        drops_fase3 = [i for i in drops_old if i > max(renames)]
        posities = [i for i, regel in enumerate(log) if regel[0] == 'zetSequence']
        laatste_commit = max(i for i, regel in enumerate(log) if regel[0] == 'commit')
        assert drops_fase3
        assert min(posities) > max(drops_fase3)
        assert max(posities) < laatste_commit
        # Zelfde transactie: geen commit tussen het opruimen en het herstellen van de sequences
        assert ('commit',) not in log[min(drops_fase3):max(posities)]

    def test_fout_bij_sequence_rolt_fase3_terug(self):
        """Een fout in zetSequence valt onder de bestaande foutafhandeling: rollback en doorgeven."""
        def kapot(cursor, table):
            if table == 'Def_Vondst':
                raise RuntimeError('sequence kapot')
            return 1

        log = []
        with pytest.raises(RuntimeError, match='sequence kapot'):
            self.draaiLoadAll(log, zet_sequence=kapot)
        fout = log.index(('zetSequence', 'Def_Vondst'))
        assert log[fout + 1:] == [('rollback',), ('close',)]

    def test_afgeleide_velden_na_fase3_in_eigen_transactie(self):
        """Issue 72: FASE 4 herberekent de afgeleide velden na de commit van FASE 3 en commit zelf."""
        log = []
        self.draaiLoadAll(log)
        assert log[-5:] == [('valideerFkConstraints',), ('commit',), ('herberekenAfgeleideVelden',),
                            ('commit',), ('close',)]

    def test_schemamigratie_gebruikersdata_eerst(self):
        """Issue 73: de schemamigratie van de gebruikerstabellen draait vóór de rest (eigen transactie)."""
        log = []
        self.draaiLoadAll(log)
        assert log[0] == ('migreerSchemaGebruikersdata',)
        # Daarna pas het opruimen van restanten van een vorige run (eerste statement van loadAll)
        assert log[1][0] == 'sql' and log[1][1].startswith('DROP TABLE IF EXISTS "')

    def test_fout_in_schemamigratie_laadt_niets(self):
        log = []
        with pytest.raises(RuntimeError, match='migratie kapot'):
            self.draaiLoadAll(log, migratie_fout=RuntimeError('migratie kapot'))
        assert log == [('migreerSchemaGebruikersdata',), ('rollback',), ('close',)]

    def test_fout_in_afgeleide_velden_rolt_alleen_fase4_terug(self):
        log = []
        with pytest.raises(RuntimeError, match='afgeleid kapot'):
            self.draaiLoadAll(log, afgeleid_fout=RuntimeError('afgeleid kapot'))
        assert log[-5:] == [('valideerFkConstraints',), ('commit',), ('herberekenAfgeleideVelden',),
                            ('rollback',), ('close',)]

    def test_gebruikerstabellen_niet_geleegd_of_geswapt(self):
        """Issue 71: geen TRUNCATE meer en geen enkel statement op een gebruikerstabel (die blijven staan)."""
        from wasstraat.loadToDatabase_functions import GEBRUIKERS_TABELLEN
        log = []
        self.draaiLoadAll(log)
        statements = [regel[1] for regel in log if regel[0] == 'sql']
        assert not [s for s in statements if 'TRUNCATE' in s.upper()]
        for tabel in GEBRUIKERS_TABELLEN:
            assert not [s for s in statements if f'"{tabel}' in s], f"{tabel} wordt door loadAll aangeraakt"

    def test_gebruikersdata_rond_de_rename_in_de_swaptransactie(self):
        """Issue 71: loskoppelen na het verwijderen van de FK's en vóór de rename, terugkoppelen na de
        laatste rename, alles in de transactie van de swap; de vervallen sleutels vóór de commit van FASE 1."""
        log = []
        self.draaiLoadAll(log)
        positie = {regel[0]: i for i, regel in enumerate(log) if len(regel) == 1}
        renames = [i for i, regel in enumerate(log) if regel[0] == 'sql' and 'RENAME TO' in regel[1]]
        creates = [i for i, regel in enumerate(log) if regel[0] == 'sql' and regel[1].startswith('CREATE TABLE')]
        commits = [i for i, regel in enumerate(log) if regel[0] == 'commit']
        assert max(creates) < positie['bepaalVervallenSleutels'] < min(c for c in commits if c > max(creates))
        assert positie['verwijderFkConstraints'] < positie['bepaalVerwijzingen'] < positie['koppelGebruikersdataLos']
        assert positie['koppelGebruikersdataLos'] < min(renames)
        assert max(renames) < positie['werkGebruikersdataBijNaSwap']
        # Geen commit tussen het loskoppelen en het terugkoppelen (één transactie met de swap)
        assert not [c for c in commits if positie['koppelGebruikersdataLos'] < c < positie['werkGebruikersdataBijNaSwap']]

    def test_resultaat_met_tellingen(self):
        log = []
        resultaat = self.draaiLoadAll(log)
        assert resultaat == {'vervallen': {}, 'gebruikersdata': {}}
