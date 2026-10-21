"""
Unit tests voor de incrementele load (incrementeel laden, fase 3, issue 61).

Test loadToDatabase_functions.loadIncrementeel en de hulpfuncties
(upsertRijen, bepaalUpsertKolommen, getBetrokkenFkConstraints, zetSequence,
werkGeometrieBij, vulArtefactKey/leesDocumenten) en de Elasticsearch-delta
shared/fulltext.indexTableIncrementeel.

PostgreSQL wordt nagebootst met een kleine in-memory database die de
SQL-statements van de load herkent; MongoDB met tests/unit/nep_mongo.py.
Het echte gedrag van PostgreSQL en Elasticsearch wordt getest in
tests/integration/test_incremental_synthetic_data.py.
"""
import importlib.util
import os
import re
import types

import pytest
from bson import ObjectId

import wasstraat.loadToDatabase_functions as load
import wasstraat.verwerkingsrun as verwerkingsrun
from tests.unit.nep_mongo import NepClient, NepCollectie, NepCursor, NepDatabase


# ============================================================
# Nabootsing van MongoDB (find met projection= en limit)
# ============================================================

class LimietCursor(NepCursor):
    def limit(self, aantal):
        return LimietCursor(self[:aantal])


class LoadCollectie(NepCollectie):
    def find(self, filt=None, projectie=None, projection=None):
        return LimietCursor(super().find(filt, projection if projection is not None else projectie))


class LoadDatabase(NepDatabase):
    def __getitem__(self, naam):
        return self.collecties.setdefault(naam, LoadCollectie(naam))


class LoadClient(NepClient):
    def __getitem__(self, naam):
        return self.databases.setdefault(naam, LoadDatabase(naam))


# ============================================================
# Nabootsing van PostgreSQL
# ============================================================

class NepPostgres:
    """In-memory PostgreSQL met tabellen, FK-constraints en een log van alle statements.

    tabellen: naam -> {'kolommen': {kolom: (data_type, max_length)}, 'rijen': {primary_key: {kolom: waarde}}}
    fks: lijst met (tabel, naam, definitie, verwezen tabel)
    """

    def __init__(self, tabellen, fks=None, sequences=True):
        self.tabellen = tabellen
        self.fks = list(fks or [])
        self.sequences = sequences
        self.log = []
        self.commits = 0
        self.rollbacks = 0
        self.gesloten = False

    def cursor(self):
        return NepPgCursor(self)

    def commit(self):
        self.log.append('COMMIT')
        self.commits += 1

    def rollback(self):
        self.log.append('ROLLBACK')
        self.rollbacks += 1

    def close(self):
        self.gesloten = True

    def sqlVoor(self, tabel):
        """Alle statements waarin een tabel voorkomt."""
        return [s for s in self.log if isinstance(s, str) and f'"{tabel}"' in s]


class NepPgCursor:
    def __init__(self, db):
        self.db = db
        self.resultaat = []
        self.rowcount = 0

    def execute(self, sql, params=None):
        db = self.db
        db.log.append(sql)
        self.resultaat = []
        self.rowcount = 0
        if 'information_schema.table_constraints' in sql:
            self.resultaat = [(t, n, d, f'"{r}"') for t, n, d, r in db.fks]
        elif 'ORDER BY ordinal_position' in sql:
            tabel = db.tabellen.get(params[0])
            if tabel:
                self.resultaat = [(k, dt, 'x', ml, 'YES') for k, (dt, ml) in tabel['kolommen'].items()]
        elif 'JOIN pg_enum' in sql:
            self.resultaat = []
        elif sql.strip().startswith('SELECT column_name FROM information_schema.columns'):
            tabel = db.tabellen.get(params[0])
            self.resultaat = [(k,) for k in tabel['kolommen']] if tabel else []
        elif sql.startswith('SELECT "primary_key"'):
            velden = re.findall(r'"(\w+)"', sql.split(' FROM ')[0])
            tabel = re.search(r'FROM "(\w+)"', sql).group(1)
            self.resultaat = [tuple(rij.get(v) for v in velden) for rij in db.tabellen[tabel]['rijen'].values()]
        elif sql.startswith('DELETE FROM'):
            tabel = re.search(r'DELETE FROM "(\w+)"', sql).group(1)
            rijen = db.tabellen[tabel]['rijen']
            for pk in params[0]:
                if rijen.pop(pk, None) is not None:
                    self.rowcount += 1
        elif 'pg_get_serial_sequence' in sql:
            self.resultaat = [(f'public.{params[0][:-1]}_primary_key_seq"' if db.sequences else None,)]
        elif 'setval' in sql:
            tabel = re.search(r'FROM "(\w+)"', sql).group(1)
            self.resultaat = [(max(db.tabellen[tabel]['rijen'], default=0) + 1,)]

    def fetchall(self):
        return self.resultaat

    def fetchone(self):
        return self.resultaat[0] if self.resultaat else None


def nepExecuteValues(cursor, sql, rijen, page_size=100, fetch=False):
    """Voer een INSERT ... ON CONFLICT DO UPDATE ... RETURNING primary_key uit op de nep-database."""
    db = cursor.db
    db.log.append(sql)
    tabel = re.search(r'INSERT INTO "(\w+)"', sql).group(1)
    kolommen = re.findall(r'"(\w+)"', sql.split(' VALUES ')[0].split('(', 1)[1])
    bestaand = db.tabellen[tabel]['rijen']
    geraakt = []
    for rij in rijen:
        nieuw = dict(zip(kolommen, rij))
        pk = nieuw['primary_key']
        oud = bestaand.get(pk)
        if oud is None or any(oud.get(k) != v for k, v in nieuw.items()):
            bestaand[pk] = dict(oud or {}, **nieuw)
            geraakt.append((pk,))
    return geraakt if fetch else None


def kolommen(*namen, **typen):
    """Kolomdefinities: standaard tekst, met typen={'naam': 'integer'} voor afwijkende typen."""
    return {naam: (typen.get(naam, 'text'), None) for naam in namen}


PG_KOLOMMEN = ('primary_key', '_id', 'key', 'soort', 'naam', 'ft_search', 'aantal_fotos')
OID_P0, OID_P1, OID_P2, OID_A0, OID_B0 = (ObjectId() for _ in range(5))


@pytest.fixture
def omgeving(monkeypatch):
    """MongoDB met Single_Store_Clean en een actieve run, PostgreSQL met pipeline- en gebruikerstabellen."""
    client = LoadClient()
    monkeypatch.setattr(verwerkingsrun, '_getClient', lambda: client)
    monkeypatch.setattr(load, '_getClient', lambda: client)
    monkeypatch.setattr(load, 'LOAD_TABELLEN', ['Def_Project', 'Def_Artefact', 'Def_Bestand', 'Def_Stelling'])
    monkeypatch.setattr(load.psycopg2.extras, 'execute_values', nepExecuteValues)

    def nepGetFields(col, soort):
        velden = {'ID'}
        for doc in col.find({'soort': soort}):
            velden.update(doc.keys())
        return sorted(velden)
    monkeypatch.setattr(load, 'getFields', nepGetFields)

    clean = client[load.config.DB_ANALYSE][load.config.COLL_ANALYSE_CLEAN]
    clean.insert_many([
        {'_id': OID_P0, 'soort': 'Project', 'key': 'PSY001', 'naam': 'Opgraving 1', 'ID': 0},
        {'_id': OID_P1, 'soort': 'Project', 'key': 'PSY002', 'naam': 'Opgraving 2 (gewijzigd)', 'ID': 1},
        {'_id': OID_P2, 'soort': 'Project', 'key': 'PSY003', 'naam': 'Opgraving 3', 'ID': 6},
        {'_id': OID_A0, 'soort': 'Artefact', 'key_subnr': 'PSY001P1V1A1', 'artefactsoort': 'Glas', 'ID': 0},
        {'_id': OID_B0, 'soort': 'Bestand', 'key': 'PSY001S1', 'naam': 'SY001_F001.jpg', 'ID': 0},
    ])

    pg = NepPostgres({
        'Def_Project': {'kolommen': kolommen(*PG_KOLOMMEN, primary_key='integer', aantal_fotos='integer'), 'rijen': {
            0: {'primary_key': 0, '_id': str(OID_P0), 'key': 'PSY001', 'soort': 'Project', 'naam': 'Opgraving 1'},
            1: {'primary_key': 1, '_id': str(OID_P1), 'key': 'PSY002', 'soort': 'Project', 'naam': 'Opgraving 2'},
            5: {'primary_key': 5, '_id': 'weg', 'key': 'PSY009', 'soort': 'Project', 'naam': 'Verdwenen'},
        }},
        'Def_Artefact': {'kolommen': kolommen(*PG_KOLOMMEN, 'artefactsoort', primary_key='integer'), 'rijen': {
            0: {'primary_key': 0, '_id': str(OID_A0), 'key': None, 'soort': 'Artefact', 'artefactsoort': 'Glas'},
        }},
        'Def_Bestand': {'kolommen': kolommen(*PG_KOLOMMEN, primary_key='integer'), 'rijen': {
            0: {'primary_key': 0, '_id': str(OID_B0), 'key': 'PSY001S1', 'soort': 'Bestand', 'naam': 'SY001_F001.jpg'},
        }},
        'Def_Bruikleen': {'kolommen': kolommen('primary_key', 'artefactID', 'partijID'), 'rijen': {
            0: {'primary_key': 0, 'artefactID': 0, 'partijID': 0}}},
        'Def_Partij': {'kolommen': kolommen('primary_key', 'naam'), 'rijen': {0: {'primary_key': 0, 'naam': 'Museum'}}},
    }, fks=[
        ('Def_Artefact', 'Def_Artefact_projectID_fkey', 'FOREIGN KEY ("projectID") REFERENCES "Def_Project"(primary_key) DEFERRABLE', 'Def_Project'),
        ('Def_Bruikleen', 'Def_Bruikleen_artefactID_fkey', 'FOREIGN KEY ("artefactID") REFERENCES "Def_Artefact"(primary_key) DEFERRABLE', 'Def_Artefact'),
        ('Def_Bruikleen', 'Def_Bruikleen_partijID_fkey', 'FOREIGN KEY ("partijID") REFERENCES "Def_Partij"(primary_key) DEFERRABLE', 'Def_Partij'),
    ])
    monkeypatch.setattr(load, 'getPgConnection', lambda: pg)

    verwerkingsrun.startRun('incrementeel')
    return types.SimpleNamespace(client=client, clean=clean, pg=pg)


# ============================================================
# Klasse 1: hulpfuncties
# ============================================================

@pytest.mark.unit
class TestHulpfuncties:
    """Test de opbouw van de SQL en de kolomkeuze."""

    def test_upsert_sql(self, monkeypatch):
        aanroepen = []

        def opname(cursor, sql, rijen, page_size=100, fetch=False):
            aanroepen.append((sql, rijen, page_size, fetch))
            return [(1,), (2,)]
        monkeypatch.setattr(load.psycopg2.extras, 'execute_values', opname)

        geraakt = load.upsertRijen('cursor', 'Def_Vondst', ['_id', 'key', 'primary_key'], [('a', 'k', 1), ('b', 'l', 2)])
        assert geraakt == {1, 2}
        sql, rijen, page_size, fetch = aanroepen[0]
        assert sql.startswith('INSERT INTO "Def_Vondst" ("_id", "key", "primary_key") VALUES %s ')
        assert 'ON CONFLICT (primary_key) DO UPDATE SET "_id" = EXCLUDED."_id", "key" = EXCLUDED."key" ' in sql
        assert '"primary_key" = EXCLUDED' not in sql
        assert ('WHERE ROW("Def_Vondst"."_id"::text, "Def_Vondst"."key"::text) '
                'IS DISTINCT FROM ROW(EXCLUDED."_id"::text, EXCLUDED."key"::text)') in sql
        assert sql.endswith('RETURNING primary_key')
        assert fetch is True and rijen == [('a', 'k', 1), ('b', 'l', 2)]

    def test_upsert_zonder_rijen_of_alleen_primary_key(self, monkeypatch):
        aanroepen = []
        monkeypatch.setattr(load.psycopg2.extras, 'execute_values',
                            lambda cursor, sql, rijen, page_size=100, fetch=False: aanroepen.append(sql) or [])
        assert load.upsertRijen('cursor', 'Def_Vondst', ['primary_key'], []) == set()
        assert aanroepen == []
        load.upsertRijen('cursor', 'Def_Vondst', ['primary_key'], [(1,)])
        assert 'ON CONFLICT (primary_key) DO NOTHING' in aanroepen[0]

    def test_upsert_kolommen(self):
        """Velden uit getFields die geen document meer heeft worden geleegd; onbekende kolommen blijven buiten de upsert."""
        kolommen_ = load.bepaalUpsertKolommen(
            fields=['ID', '_id', 'key', 'beschrijving', 'key_project'],
            all_doc_keys={'_id', 'key', 'primary_key', 'projectcd', 'location'},
            db_colnames={'primary_key', '_id', 'key', 'beschrijving', 'location', 'aantal_fotos', 'ft_search'})
        assert kolommen_ == ['_id', 'beschrijving', 'key', 'primary_key']

    def test_betrokken_fk_constraints(self):
        fks = [
            {'table': 'Def_Vondst', 'name': 'a', 'referenced_table': 'Def_Project'},
            {'table': 'Def_Bruikleen', 'name': 'b', 'referenced_table': 'Def_Artefact'},
            {'table': 'Def_Bruikleen', 'name': 'c', 'referenced_table': 'Def_Partij'},
            {'table': 'Def_artefact_conservering', 'name': 'd', 'referenced_table': 'Def_Conserveringsproject'},
        ]
        betrokken = load.getBetrokkenFkConstraints(fks, ['Def_Vondst', 'Def_Project', 'Def_Artefact'])
        assert [fk['name'] for fk in betrokken] == ['a', 'b']

    def test_lees_fk_constraints_verwezen_tabel(self):
        class Cursor:
            def execute(self, sql, params=None):
                self.sql = sql

            def fetchall(self):
                return [('Def_Vondst', 'x', 'FOREIGN KEY', '"Def_Project"'),
                        ('Def_Vondst', 'y', 'FOREIGN KEY', 'public."Def_Put"'),
                        ('Def_Vondst', 'z', 'FOREIGN KEY', None)]
        fks = load.leesFkConstraints(Cursor())
        assert [fk['referenced_table'] for fk in fks] == ['Def_Project', 'Def_Put', None]
        assert all(set(fk) == {'table', 'name', 'definition', 'referenced_table'} for fk in fks)

    def test_sequence_bestaat(self):
        pg = NepPostgres({'Def_Put': {'kolommen': {}, 'rijen': {0: {}, 7: {}}}})
        assert load.zetSequence(pg.cursor(), 'Def_Put') == 8
        assert not any('CREATE SEQUENCE' in s for s in pg.log)
        setval = [s for s in pg.log if 'setval' in s][0]
        assert 'COALESCE((SELECT MAX(primary_key) FROM "Def_Put"), 0) + 1, false' in setval

    def test_ontbrekende_sequence_wordt_aangemaakt(self):
        """Na de atomic swap van de volledige cyclus ontbreekt de sequence; de upsert maakt hem opnieuw aan."""
        pg = NepPostgres({'Def_Put': {'kolommen': {}, 'rijen': {3: {}}}}, sequences=False)
        assert load.zetSequence(pg.cursor(), 'Def_Put') == 4
        assert 'CREATE SEQUENCE IF NOT EXISTS "Def_Put_primary_key_seq" OWNED BY "Def_Put".primary_key' in pg.log
        assert any(s.startswith('ALTER TABLE "Def_Put" ALTER COLUMN primary_key SET DEFAULT nextval') for s in pg.log)

    def test_geometrie_sql(self):
        pg = NepPostgres({})
        load.werkGeometrieBij(pg.cursor(), 'Def_Project')
        sql = pg.log[0]
        assert 'UPDATE "Def_Project"' in sql
        assert 'longitude IS NOT NULL AND latitude IS NOT NULL AND longitude > 1' in sql
        assert 'ST_SetSRID(ST_MakePoint(longitude, latitude), 4326)' in sql
        assert 'IS DISTINCT FROM' in sql


# ============================================================
# Klasse 2: key van artefacten (volledige en incrementele load)
# ============================================================

@pytest.mark.unit
class TestArtefactKey:
    """De kolom key van Def_Artefact krijgt key_subnr|artefactsoort als het artefact geen key heeft."""

    def test_vul_artefact_key(self):
        assert load.vulArtefactKey({'key_subnr': 'PSY001P1V1A1', 'artefactsoort': 'Glas'})['key'] == 'PSY001P1V1A1|Glas'
        assert load.vulArtefactKey({'key': float('nan'), 'key_subnr': 'S', 'artefactsoort': 'Glas'})['key'] == 'S|Glas'
        assert load.vulArtefactKey({'key': 'PSY001P1V1A9', 'key_subnr': 'S'})['key'] == 'PSY001P1V1A9'
        assert load.vulArtefactKey({'artefactsoort': 'Glas'})['key'] is None

    def test_lees_documenten(self, omgeving):
        _, artefacten = load.leesDocumenten(omgeving.clean, 'Artefact')
        assert artefacten[0]['key'] == 'PSY001P1V1A1|Glas'
        _, projecten = load.leesDocumenten(omgeving.clean, 'Project')
        assert [p['key'] for p in projecten] == ['PSY001', 'PSY002', 'PSY003']

    def test_transfer_to_db_vult_key(self, omgeving, monkeypatch):
        """De volledige cyclus (transferToDB) laadt de samengestelde sleutel ook."""
        ingevoegd = []
        monkeypatch.setattr(load, 'getAnalyseCleanCollection', lambda: omgeving.clean)
        monkeypatch.setattr(load, 'insertBatch', lambda cursor, table, kolommen_, rijen: ingevoegd.append(
            (table, kolommen_, rijen)) or len(rijen))
        load.transferToDB('Artefact', 'Def_Artefact_new', omgeving.pg.cursor())
        table, kolommen_, rijen = ingevoegd[0]
        assert table == 'Def_Artefact_new'
        assert dict(zip(kolommen_, rijen[0]))['key'] == 'PSY001P1V1A1|Glas'


# ============================================================
# Klasse 3: loadIncrementeel
# ============================================================

@pytest.mark.unit
class TestLoadIncrementeel:
    """Test de upsert-load met de nagebootste databases."""

    def test_upsert_verwijderen_en_tellingen(self, omgeving):
        resultaat = load.loadIncrementeel()
        pg = omgeving.pg

        projecten = pg.tabellen['Def_Project']['rijen']
        assert sorted(projecten) == [0, 1, 6]
        assert projecten[1]['naam'] == 'Opgraving 2 (gewijzigd)'
        assert projecten[6]['_id'] == str(OID_P2)
        assert pg.tabellen['Def_Artefact']['rijen'][0]['key'] == 'PSY001P1V1A1|Glas'

        assert resultaat['Def_Project'] == {'upsert': 3, 'ingevoegd': 1, 'bijgewerkt': 1, 'verwijderd': 1}
        assert resultaat['Def_Artefact'] == {'upsert': 1, 'ingevoegd': 0, 'bijgewerkt': 1, 'verwijderd': 0}
        assert resultaat['Def_Bestand'] == {'upsert': 1, 'ingevoegd': 0, 'bijgewerkt': 0, 'verwijderd': 0}
        assert 'Def_Stelling' not in resultaat  # tabel bestaat niet: overgeslagen
        assert resultaat['totaal'] == {'upsert': 5, 'ingevoegd': 1, 'bijgewerkt': 2, 'verwijderd': 1}
        assert resultaat['fk_niet_gevalideerd'] == [] and resultaat['fk_niet_hersteld'] == 0

        # Tellingen in het run-document
        run = verwerkingsrun.huidigeRun()
        assert run['tellingen']['load']['Def_Project'] == resultaat['Def_Project']
        assert run['tellingen']['load']['totaal'] == resultaat['totaal']

    def test_gebruikerstabellen_niet_aangeraakt(self, omgeving):
        load.loadIncrementeel()
        pg = omgeving.pg
        assert pg.tabellen['Def_Bruikleen']['rijen'] == {0: {'primary_key': 0, 'artefactID': 0, 'partijID': 0}}
        assert pg.tabellen['Def_Partij']['rijen'] == {0: {'primary_key': 0, 'naam': 'Museum'}}
        # Alleen de verwijzing naar Def_Artefact wordt tijdelijk verwijderd en hersteld; Def_Partij blijft buiten beeld
        assert pg.sqlVoor('Def_Partij') == []
        bruikleen = pg.sqlVoor('Def_Bruikleen')
        assert len(bruikleen) == 3
        assert all('"Def_Bruikleen_artefactID_fkey"' in s for s in bruikleen)
        assert not any(s.startswith(('INSERT', 'DELETE', 'UPDATE', 'TRUNCATE')) for s in bruikleen)
        assert not any('TRUNCATE' in s for s in pg.log if isinstance(s, str))

    def test_volgorde_fk_mechaniek(self, omgeving):
        load.loadIncrementeel()
        log = omgeving.pg.log

        def eerste(fragment):
            return next(i for i, s in enumerate(log) if fragment in s)

        def laatste(fragment):
            return max(i for i, s in enumerate(log) if fragment in s)

        assert log[0] == "SET lock_timeout = '30s'"
        assert laatste('DROP CONSTRAINT') < eerste('INSERT INTO')
        assert laatste('DELETE FROM') < eerste('ADD CONSTRAINT')
        assert all(s.endswith(' NOT VALID') for s in log if 'ADD CONSTRAINT' in s)
        # Eén commit na het herstel (upsert atomair), validatie daarna in een eigen transactie
        assert eerste('ADD CONSTRAINT') < log.index('COMMIT') < eerste('VALIDATE CONSTRAINT')
        assert log[-1] == 'COMMIT' and omgeving.pg.commits == 2
        assert omgeving.pg.gesloten

    def test_lege_clean_geeft_fout(self, omgeving):
        omgeving.clean.delete_many({})
        with pytest.raises(Exception, match='volledige cyclus'):
            load.loadIncrementeel()
        assert omgeving.pg.log == []
        assert sorted(omgeving.pg.tabellen['Def_Project']['rijen']) == [0, 1, 5]

    def test_document_zonder_id_rolt_terug(self, omgeving):
        omgeving.clean.insert_one({'soort': 'Project', 'key': 'PSY004', 'naam': 'Zonder ID'})
        with pytest.raises(Exception, match='geen ID'):
            load.loadIncrementeel()
        assert omgeving.pg.commits == 0 and omgeving.pg.rollbacks == 1

    def test_dubbel_id_geeft_fout(self, omgeving):
        omgeving.clean.insert_one({'soort': 'Project', 'key': 'PSY004', 'naam': 'Dubbel', 'ID': 1})
        with pytest.raises(Exception, match="dubbele ID's"):
            load.loadIncrementeel()
        assert omgeving.pg.commits == 0

    def test_tweede_run_verandert_niets(self, omgeving):
        load.loadIncrementeel()
        resultaat = load.loadIncrementeel()
        assert resultaat['totaal'] == {'upsert': 5, 'ingevoegd': 0, 'bijgewerkt': 0, 'verwijderd': 0}

    def test_fk_niet_hersteld_rolt_alles_terug(self, omgeving, monkeypatch):
        """Een FK-constraint die niet hersteld kan worden mag na een commit niet definitief verdwijnen."""
        origineel = NepPgCursor.execute

        def execute(self, sql, params=None):
            origineel(self, sql, params)
            if 'ADD CONSTRAINT "Def_Bruikleen_artefactID_fkey"' in sql:
                raise Exception('nep: constraint kan niet hersteld worden')
        monkeypatch.setattr(NepPgCursor, 'execute', execute)

        with pytest.raises(Exception, match=r'Def_Bruikleen\.Def_Bruikleen_artefactID_fkey'):
            load.loadIncrementeel()

        pg = omgeving.pg
        assert pg.commits == 0 and pg.rollbacks == 1
        assert 'ROLLBACK TO SAVEPOINT fk_restore_sp' in pg.log
        # De andere constraint is nog wel geprobeerd; gevalideerd wordt er niets meer
        assert any('ADD CONSTRAINT "Def_Artefact_projectID_fkey"' in s for s in pg.log)
        assert not any('VALIDATE CONSTRAINT' in s for s in pg.log)
        assert 'load' not in (verwerkingsrun.huidigeRun().get('tellingen') or {})

    def test_herstel_fk_geeft_namen_van_mislukte_constraints(self):
        class FoutCursor:
            def execute(self, sql, params=None):
                if 'ADD CONSTRAINT "fk_b"' in sql:
                    raise Exception('mislukt')

        fks = [{'table': 'Def_A', 'name': 'fk_a', 'definition': 'FOREIGN KEY (x) REFERENCES "Def_P"(primary_key)'},
               {'table': 'Def_B', 'name': 'fk_b', 'definition': 'FOREIGN KEY (y) REFERENCES "Def_P"(primary_key)'}]
        namen = []
        assert load.herstelFkConstraints(FoutCursor(), fks, namen) == (1, 1)
        assert namen == ['Def_B.fk_b']
        # Zonder lijst (loadAll) werkt de functie zoals voorheen
        assert load.herstelFkConstraints(FoutCursor(), fks) == (1, 1)


# ============================================================
# Klasse 4: Elasticsearch-delta (shared/fulltext.py)
# ============================================================

def laadFulltext():
    """Laad shared/fulltext.py los (shared is in de tests een nagebootste module zonder pakket)."""
    pad = os.path.join(os.path.dirname(__file__), '..', '..', 'shared', 'fulltext.py')
    spec = importlib.util.spec_from_file_location('fulltext_onder_test', pad)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class NepIndices:
    def __init__(self, aliassen):
        self.aliassen = aliassen
        self.ververst = []

    def exists_alias(self, name):
        return name in self.aliassen

    def get_alias(self, name):
        return {index: {} for index in self.aliassen[name]}

    def refresh(self, index):
        self.ververst.append(index)


class NepVerbinding:
    def __init__(self, rijen):
        self.rijen = rijen

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, sql):
        return iter(self.rijen)


@pytest.fixture
def fulltext(monkeypatch):
    module = laadFulltext()
    es = types.SimpleNamespace(indices=NepIndices({'def_vondst': ['def_vondst_1700000000']}))
    acties = []
    volledig = []
    rijen = [{'primary_key': 0, 'naam': 'a'}, {'primary_key': 2, 'naam': None}]

    def nepBulk(client, docs):
        docs = list(docs)
        acties.extend(docs)
        return len(docs), []

    monkeypatch.setattr(module, 'Elasticsearch', lambda host: es)
    monkeypatch.setattr(module.helpers, 'bulk', nepBulk)
    monkeypatch.setattr(module.helpers, 'scan', lambda client, index, query: iter(
        [{'_id': '0'}, {'_id': '2'}, {'_id': '9'}]))
    monkeypatch.setattr(module, 'create_engine', lambda uri: types.SimpleNamespace(
        connect=lambda: NepVerbinding(rijen), dispose=lambda: None))
    monkeypatch.setattr(module, 'inspect', lambda verbinding: types.SimpleNamespace(
        has_table=lambda tabel, schema=None: True))
    monkeypatch.setattr(module, 'getCols', lambda verbinding, tabel: [{'name': 'primary_key'}, {'name': 'naam'}])
    monkeypatch.setattr(module, 'indexTable', lambda tabel: volledig.append(tabel))
    return types.SimpleNamespace(module=module, es=es, acties=acties, volledig=volledig)


@pytest.mark.unit
class TestIndexTableIncrementeel:
    """Test de bulk-upsert en het verwijderen van verdwenen id's in de index achter de alias."""

    def test_upsert_en_verwijderen(self, fulltext):
        resultaat = fulltext.module.indexTableIncrementeel('Def_Vondst')
        assert resultaat == {'index': 'def_vondst_1700000000', 'geindexeerd': 2, 'verwijderd': 1}
        indexeren, verwijderen = fulltext.acties[:2], fulltext.acties[2:]
        assert indexeren == [
            {'_index': 'def_vondst_1700000000', '_id': 0, 'primary_key': '0', 'naam': 'a'},
            {'_index': 'def_vondst_1700000000', '_id': 2, 'primary_key': '2', 'naam': ''},
        ]
        assert verwijderen == [{'_op_type': 'delete', '_index': 'def_vondst_1700000000', '_id': 9}]
        assert fulltext.es.indices.ververst == ['def_vondst_1700000000']
        assert fulltext.volledig == []

    def test_zonder_alias_volledige_indexering(self, fulltext):
        assert fulltext.module.indexTableIncrementeel('Def_Put') == {'index': 'def_put', 'volledig': True}
        assert fulltext.volledig == ['Def_Put'] and fulltext.acties == []

    def test_alias_met_meerdere_indexen_volledige_indexering(self, fulltext):
        fulltext.es.indices.aliassen['def_vondst'].append('def_vondst_1700000001')
        assert fulltext.module.indexTableIncrementeel('Def_Vondst')['volledig'] is True
        assert fulltext.volledig == ['Def_Vondst']
