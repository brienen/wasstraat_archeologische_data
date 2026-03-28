"""
Unit tests voor fixMonsterProjectcds in harmonize_functions.py

Test het inlezen en matchen van projectcodes uit de Monsterdatabase.
Mockt MongoDB zodat er geen live database nodig is.
"""
import pytest
from unittest.mock import patch, MagicMock
import pandas as pd

from wasstraat.harmonize_functions import fixMonsterProjectcds


def _make_mock_collection(documents):
    """Maak een mock MongoDB collection die documenten retourneert op basis van query."""
    col = MagicMock()

    def mock_find(query, projection=None):
        results = []
        for doc in documents:
            match = all(
                doc.get(k) == v if not isinstance(v, dict)
                else _match_query(doc, k, v)
                for k, v in query.items()
            )
            if match:
                if projection:
                    filtered = {}
                    for pk, pv in projection.items():
                        if pk == '_id' and pv == 0:
                            continue
                        if pv == 1 and pk in doc:
                            filtered[pk] = doc[pk]
                        elif pv == 0:
                            # exclusie-projectie: neem alles behalve dit veld
                            pass
                    if any(v == 0 and k != '_id' for k, v in projection.items()):
                        filtered = {k: v for k, v in doc.items() if k not in [pk for pk, pv in projection.items() if pv == 0]}
                    results.append(filtered)
                else:
                    results.append(doc)
        return results

    def mock_count_documents(query):
        return len([d for d in documents if all(
            d.get(k) == v if not isinstance(v, dict)
            else _match_query(d, k, v)
            for k, v in query.items()
        )])

    col.find = mock_find
    col.count_documents = mock_count_documents
    col.update_many = MagicMock()
    col.bulk_write = MagicMock()
    return col


def _match_query(doc, key, value):
    """Simpele MongoDB query matching voor $exists."""
    if isinstance(value, dict) and '$exists' in value:
        parts = key.split('.')
        obj = doc
        for part in parts:
            if isinstance(obj, dict) and part in obj:
                obj = obj[part]
            else:
                return not value['$exists']
        return value['$exists']
    return doc.get(key) == value


def _setup_mock_client(mock_pymongo, documents):
    """Configureer de pymongo mock met een collection vol documenten."""
    mock_client = MagicMock()
    mock_col = _make_mock_collection(documents)
    mock_client.__getitem__ = lambda self, key: MagicMock(__getitem__=lambda self2, key2: mock_col)
    mock_pymongo.MongoClient.return_value = mock_client
    return mock_col


class TestFixMonsterProjectcdsGeenMonsters:
    """Test dat de functie correct terugkeert als er geen Monster-records zijn."""

    @patch('wasstraat.harmonize_functions.pymongo')
    def test_geen_monsters_early_return(self, mock_pymongo):
        """Als er geen Monster-records zijn, moet de functie direct terugkeren."""
        mock_col = _setup_mock_client(mock_pymongo, [
            {'soort': 'Project', 'projectcd': 'P001', 'project': 'TestProject'}
        ])

        fixMonsterProjectcds()

        mock_col.update_many.assert_not_called()
        mock_col.bulk_write.assert_not_called()


class TestFixMonsterProjectcdsGeenProjecten:
    """Test dat de functie correct omgaat met ontbrekende Project-records."""

    @patch('wasstraat.harmonize_functions.pymongo')
    def test_geen_projecten_geen_crash(self, mock_pymongo):
        """Als er geen Project-records zijn, mag de functie niet crashen met KeyError."""
        documents = [
            {'_id': 'm1', 'soort': 'Monster', 'project': 'OudProject', 'brondata': {'PROJECT': 'OudProject'}},
        ]
        mock_col = _setup_mock_client(mock_pymongo, documents)

        # Dit was de bug: KeyError: 'projectcd' wanneer df_project leeg is
        fixMonsterProjectcds()

        # Geen bulk_write verwacht want er zijn geen projecten om te matchen
        mock_col.bulk_write.assert_not_called()


class TestFixMonsterProjectcdsNormaal:
    """Test de normale werking: Monster-records worden gematcht met Project-records."""

    @patch('wasstraat.harmonize_functions.pymongo')
    def test_monster_wordt_gematcht_met_project(self, mock_pymongo):
        """Monster-records met een oud projectcode worden gematcht via Project-records."""
        documents = [
            {'_id': 'p1', 'soort': 'Project', 'projectcd': 'P001', 'project': 'Delft Centrum'},
            {'_id': 'm1', 'soort': 'Monster', 'project': 'Delft Centrum', 'brondata': {'PROJECT': 'Delft Centrum'}},
        ]
        mock_col = _setup_mock_client(mock_pymongo, documents)

        fixMonsterProjectcds()

        # bulk_write moet aangeroepen zijn om de projectcd te updaten
        mock_col.bulk_write.assert_called_once()

    @patch('wasstraat.harmonize_functions.pymongo')
    def test_meerdere_monsters_met_verschillende_projecten(self, mock_pymongo):
        """Meerdere monsters met verschillende projectcodes worden correct gematcht."""
        documents = [
            {'_id': 'p1', 'soort': 'Project', 'projectcd': 'P001', 'project': 'Project A'},
            {'_id': 'p2', 'soort': 'Project', 'projectcd': 'P002', 'project': 'Project B'},
            {'_id': 'm1', 'soort': 'Monster', 'project': 'Project A', 'brondata': {'PROJECT': 'OudA'}},
            {'_id': 'm2', 'soort': 'Monster', 'project': 'Project B', 'brondata': {'PROJECT': 'OudB'}},
        ]
        mock_col = _setup_mock_client(mock_pymongo, documents)

        fixMonsterProjectcds()

        mock_col.bulk_write.assert_called_once()
        updates = mock_col.bulk_write.call_args[0][0]
        assert len(updates) == 2


class TestFixMonsterProjectcdsOnbekend:
    """Test dat ongematchte Monster-records het label 'Unknown' krijgen."""

    @patch('wasstraat.harmonize_functions.pymongo')
    def test_onbekend_project_bij_geen_match(self, mock_pymongo):
        """Monsters die niet gematcht kunnen worden krijgen ONBEKEND_PROJECT als projectcd."""
        documents = [
            {'_id': 'p1', 'soort': 'Project', 'projectcd': 'P001', 'project': 'Bekend Project'},
            {'_id': 'm1', 'soort': 'Monster', 'project': 'Totaal Onbekend', 'brondata': {'PROJECT': 'Totaal Onbekend'}},
        ]
        mock_col = _setup_mock_client(mock_pymongo, documents)

        fixMonsterProjectcds()

        mock_col.bulk_write.assert_called_once()
        updates = mock_col.bulk_write.call_args[0][0]
        assert len(updates) == 1


class TestFixMonsterProjectcdsZonderBrondata:
    """Test gedrag wanneer Monster-records geen brondata.PROJECT hebben."""

    @patch('wasstraat.harmonize_functions.pymongo')
    def test_monsters_zonder_brondata_project(self, mock_pymongo):
        """Monsters zonder brondata.PROJECT worden overgeslagen."""
        documents = [
            {'_id': 'p1', 'soort': 'Project', 'projectcd': 'P001', 'project': 'TestProject'},
            {'_id': 'm1', 'soort': 'Monster'},  # geen brondata.PROJECT
        ]
        mock_col = _setup_mock_client(mock_pymongo, documents)

        fixMonsterProjectcds()

        # update_many wordt wel aangeroepen (zet alles op None), maar geen bulk_write
        # want er zijn geen monsters met brondata.PROJECT
        mock_col.bulk_write.assert_not_called()
