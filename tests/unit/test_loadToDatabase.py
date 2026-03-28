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
        result = transformRow(doc, ['artefactsoort'], self._col_lookup(), {'artefactsoort'})
        assert result['artefactsoort'] == 'Onbekend'

    def test_enum_default_bij_none(self):
        doc = {'artefactsoort': None}
        result = transformRow(doc, ['artefactsoort'], self._col_lookup(), {'artefactsoort'})
        assert result['artefactsoort'] == 'Onbekend'

    def test_enum_behoudt_waarde(self):
        doc = {'artefactsoort': 'Aardewerk'}
        result = transformRow(doc, ['artefactsoort'], self._col_lookup(), {'artefactsoort'})
        assert result['artefactsoort'] == 'Aardewerk'

    def test_id_rename(self):
        doc = {'ID': 5, 'naam': 'test'}
        result = transformRow(doc, ['primary_key', 'naam'], self._col_lookup(), set())
        assert result['primary_key'] == 5

    def test_id_string_conversie(self):
        from bson import ObjectId
        oid = ObjectId()
        doc = {'_id': oid}
        result = transformRow(doc, ['_id'], self._col_lookup(), set())
        assert isinstance(result['_id'], str)

    def test_none_waarde(self):
        doc = {'score': None}
        result = transformRow(doc, ['score'], self._col_lookup(), set())
        assert result['score'] is None

    def test_nan_waarde(self):
        doc = {'score': 'nan'}
        result = transformRow(doc, ['score'], self._col_lookup(), set())
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
            ('artefactsoort',),
            ('bestandsoort',),
        ]

        result = getEnumColumns(cursor, 'Def_Artefact')

        assert result == {'artefactsoort', 'bestandsoort'}


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
