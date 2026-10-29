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

    tabellen: naam -> {'kolommen': {kolom: (data_type, max_length)}, 'rijen': {primary_key: {kolom: waarde}},
    optioneel 'niet_null': set met kolommen met NOT NULL}
    fks: lijst met (tabel, naam, definitie, verwezen tabel)

    De statements van de verwijzingen vanuit gebruikerstabellen (issue 73) worden
    herkend aan hun vorm (alias g voor de gebruikerstabel, d voor de doeltabel);
    CURRENT_TIMESTAMP wordt de waarde NU.
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
        if self.verwijzingen(sql, params):
            return
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
        elif sql.startswith('SELECT COUNT(*) FILTER'):
            # Telling van de afgeleide velden (herberekenAfgeleideVelden): niets verandert
            self.resultaat = [tuple(0 for _ in range(sql.count('COUNT(*) FILTER')))]

    def verwijzingen(self, sql, params):
        """Schemamigratie en verwijzingen vanuit gebruikerstabellen (issue 73); True als het statement herkend is."""
        db = self.db
        tekst = ' '.join(sql.split())
        if tekst.startswith('SELECT column_name, is_nullable FROM information_schema.columns'):
            tabel = db.tabellen.get(params[0])
            if tabel:
                self.resultaat = [(k, 'NO' if k in tabel.get('niet_null', set()) else 'YES') for k in tabel['kolommen']]
            return True
        m = re.match(r'ALTER TABLE "(\w+)" ADD COLUMN IF NOT EXISTS "(\w+)" (\w+)$', tekst)
        if m:
            soort = {'TEXT': 'text', 'TIMESTAMP': 'timestamp without time zone'}[m.group(3)]
            db.tabellen[m.group(1)]['kolommen'].setdefault(m.group(2), (soort, None))
            return True
        m = re.match(r'ALTER TABLE "(\w+)" ALTER COLUMN "(\w+)" DROP NOT NULL$', tekst)
        if m:
            db.tabellen[m.group(1)].get('niet_null', set()).discard(m.group(2))
            return True
        # Loskoppelen vóór het verwijderen: key uit de doeltabel
        m = re.match(r'UPDATE "(\w+)" AS g SET "(\w+)" = NULL, "(\w+)" = d\.key, "(\w+)" = CURRENT_TIMESTAMP '
                     r'FROM "(\w+)" AS d WHERE d\.primary_key = g\."\2" AND d\.primary_key = ANY\(%s\) '
                     r'RETURNING g\."\3"$', tekst)
        if m:
            tabel, kolom, key_kolom, op_kolom, doel = m.groups()
            doelrijen = db.tabellen[doel]['rijen']
            for rij in db.tabellen[tabel]['rijen'].values():
                if rij.get(kolom) in params[0] and rij.get(kolom) in doelrijen:
                    rij.update({kolom: None, key_kolom: doelrijen[rij[kolom]].get('key'), op_kolom: NU})
                    self.resultaat.append((rij[key_kolom],))
            self.rowcount = len(self.resultaat)
            return True
        # Vangnet: verwijzing naar een niet-bestaande rij
        m = re.match(r'(UPDATE|DELETE FROM) "(\w+)" AS g (?:SET "(\w+)" = NULL, "(\w+)" = NULL, '
                     r'"(\w+)" = CURRENT_TIMESTAMP )?WHERE g\."(\w+)" IS NOT NULL AND NOT EXISTS '
                     r'\(SELECT 1 FROM "(\w+)" AS d WHERE d\.primary_key = g\."\6"\)$', tekst)
        if m:
            actie, tabel, _, key_kolom, op_kolom, kolom, doel = m.groups()
            rijen = db.tabellen[tabel]['rijen']
            zonder_doel = [pk for pk, rij in rijen.items()
                           if rij.get(kolom) is not None and rij[kolom] not in db.tabellen[doel]['rijen']]
            for pk in zonder_doel:
                if actie == 'DELETE FROM':
                    del rijen[pk]
                else:
                    rijen[pk].update({kolom: None, key_kolom: None, op_kolom: NU})
            self.rowcount = len(zonder_doel)
            return True
        # Terugkoppelen op een unieke key, en de telling van dubbele keys
        m = re.match(r'UPDATE "(\w+)" AS g SET "(\w+)" = d\.primary_key, "(\w+)" = NULL, "(\w+)" = NULL '
                     r'FROM \(SELECT key, MIN\(primary_key\) AS primary_key FROM "(\w+)" WHERE key IS NOT NULL '
                     r'GROUP BY key HAVING COUNT\(\*\) = 1\) AS d WHERE g\."\2" IS NULL AND g\."\3" = d\.key$', tekst)
        if m:
            tabel, kolom, key_kolom, op_kolom, doel = m.groups()
            per_key = {}
            for pk, rij in db.tabellen[doel]['rijen'].items():
                if rij.get('key') is not None:
                    per_key.setdefault(rij['key'], []).append(pk)
            for rij in db.tabellen[tabel]['rijen'].values():
                pks = per_key.get(rij.get(key_kolom))
                if rij.get(kolom) is None and pks and len(pks) == 1:
                    rij.update({kolom: pks[0], key_kolom: None, op_kolom: None})
                    self.rowcount += 1
            return True
        m = re.match(r'SELECT COUNT\(\*\) FROM "(\w+)" AS g WHERE g\."(\w+)" IS NULL AND g\."(\w+)" IN '
                     r'\(SELECT key FROM "(\w+)" WHERE key IS NOT NULL GROUP BY key HAVING COUNT\(\*\) > 1\)$', tekst)
        if m:
            tabel, kolom, key_kolom, doel = m.groups()
            keys = [rij.get('key') for rij in db.tabellen[doel]['rijen'].values() if rij.get('key') is not None]
            dubbel = {k for k in keys if keys.count(k) > 1}
            self.resultaat = [(sum(1 for rij in db.tabellen[tabel]['rijen'].values()
                                   if rij.get(kolom) is None and rij.get(key_kolom) in dubbel),)]
            return True
        return False

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
NU = 'NU'  # CURRENT_TIMESTAMP in de nagebootste PostgreSQL
BRUIKLEEN_0 = {'primary_key': 0, 'artefactID': 0, 'projectID': 0, 'partijID': 0}


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
        # Schema van vóór issue 73: artefactID en projectID NOT NULL, geen markering
        'Def_Bruikleen': {'kolommen': kolommen('primary_key', 'artefactID', 'projectID', 'partijID'),
                          'niet_null': {'artefactID', 'projectID', 'partijID'},
                          'rijen': {0: dict(BRUIKLEEN_0)}},
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
        """Gebruikersdata die naar bestaande rijen verwijst blijft gelijk; Def_Partij blijft buiten beeld."""
        load.loadIncrementeel()
        pg = omgeving.pg
        assert pg.tabellen['Def_Bruikleen']['rijen'] == {0: BRUIKLEEN_0}
        assert pg.tabellen['Def_Partij']['rijen'] == {0: {'primary_key': 0, 'naam': 'Museum'}}
        # Alleen de verwijzing naar Def_Artefact wordt tijdelijk verwijderd en hersteld; Def_Partij blijft buiten beeld
        assert pg.sqlVoor('Def_Partij') == []
        bruikleen = [s for s in pg.sqlVoor('Def_Bruikleen') if 'CONSTRAINT' in s]
        assert len(bruikleen) == 3
        assert all('"Def_Bruikleen_artefactID_fkey"' in s for s in bruikleen)
        # Verder alleen de schemamigratie en de verwijzingen (issue 73): nooit invoegen, verwijderen of legen
        overig = [s for s in pg.sqlVoor('Def_Bruikleen') if 'CONSTRAINT' not in s]
        assert all(s.startswith(('ALTER TABLE "Def_Bruikleen" A', 'UPDATE "Def_Bruikleen" AS g', 'SELECT COUNT(*)'))
                   for s in overig), overig
        assert not any('TRUNCATE' in s for s in pg.log if isinstance(s, str))

    def test_volgorde_fk_mechaniek(self, omgeving):
        load.loadIncrementeel()
        log = omgeving.pg.log

        def eerste(fragment):
            return next(i for i, s in enumerate(log) if fragment in s)

        def laatste(fragment):
            return max(i for i, s in enumerate(log) if fragment in s)

        # Eerst de schemamigratie van de gebruikerstabellen (issue 73) in een eigen transactie
        assert log[0] == "SET LOCAL lock_timeout = '30s'"
        commits = [i for i, s in enumerate(log) if s == 'COMMIT']
        assert log[commits[0] + 1] == "SET lock_timeout = '30s'"
        assert laatste('DROP CONSTRAINT') < eerste('INSERT INTO')
        assert laatste('DELETE FROM') < eerste('ADD CONSTRAINT')
        assert all(s.endswith(' NOT VALID') for s in log if 'ADD CONSTRAINT' in s)
        # Eén commit na het herstel (upsert atomair), validatie daarna in een eigen transactie
        assert eerste('ADD CONSTRAINT') < commits[1] < eerste('VALIDATE CONSTRAINT')
        assert log[-1] == 'COMMIT' and omgeving.pg.commits == 3
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
        # Alleen de schemamigratie (eigen transactie) is gecommit
        assert omgeving.pg.commits == 1 and omgeving.pg.rollbacks == 1

    def test_dubbel_id_geeft_fout(self, omgeving):
        omgeving.clean.insert_one({'soort': 'Project', 'key': 'PSY004', 'naam': 'Dubbel', 'ID': 1})
        with pytest.raises(Exception, match="dubbele ID's"):
            load.loadIncrementeel()
        assert omgeving.pg.commits == 1  # alleen de schemamigratie

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
        assert pg.commits == 1 and pg.rollbacks == 1  # alleen de schemamigratie is gecommit
        assert 'ROLLBACK TO SAVEPOINT fk_restore_sp' in pg.log
        # De andere constraint is nog wel geprobeerd; gevalideerd wordt er niets meer
        assert any('ADD CONSTRAINT "Def_Artefact_projectID_fkey"' in s for s in pg.log)
        assert not any('VALIDATE CONSTRAINT' in s for s in pg.log)
        assert 'load' not in (verwerkingsrun.huidigeRun().get('tellingen') or {})

    def test_afgeleide_velden_in_transactie_voor_fk_herstel(self, omgeving):
        """Issue 72: na de upsert en vóór het herstel van de FK's, zonder commit ertussen."""
        load.loadIncrementeel()
        log = omgeving.pg.log
        updates = [i for i, s in enumerate(log) if isinstance(s, str) and s.startswith('UPDATE "Def_') and ' AS t ' in s]
        assert [log[i].split(' AS t ')[0] for i in updates] == ['UPDATE "Def_Artefact"', 'UPDATE "Def_Project"']
        laatste_delete = max(i for i, s in enumerate(log) if s.startswith('DELETE FROM'))
        eerste_add = min(i for i, s in enumerate(log) if 'ADD CONSTRAINT' in s)
        assert laatste_delete < min(updates) and max(updates) < eerste_add
        # Geen commit tussen het begin van de upsert-transactie en het herstel (alleen die van de schemamigratie ervoor)
        begin = log.index("SET lock_timeout = '30s'")
        assert 'COMMIT' not in log[begin:eerste_add]

    def test_afgeleide_velden_in_run_document(self, omgeving, monkeypatch):
        tellingen = {'Def_Artefact': {'aantal_fotos': 2, 'rijen': 2}, 'Def_Project': {'aantal_artefacten': 1, 'rijen': 1}}
        monkeypatch.setattr(load, 'herberekenAfgeleideVelden', lambda cursor: tellingen)
        resultaat = load.loadIncrementeel()
        run = verwerkingsrun.huidigeRun()
        assert run['tellingen']['afgeleide_velden'] == tellingen
        assert 'afgeleide_velden' not in run['tellingen']['load']
        assert resultaat['afgeleide_velden'] == tellingen

    def test_fout_in_afgeleide_velden_is_waarschuwing(self, omgeving, monkeypatch):
        """Issue 54: een fout in de afgeleide velden draait alleen die herberekening terug (SAVEPOINT).

        De upsert gaat door en wordt gecommit; de fout komt als waarschuwing in de meldingen
        van het run-document, en tellingen.afgeleide_velden ontbreekt. Tot issue 54 draaide
        zo'n fout de hele upsert terug.
        """
        def kapot(cursor):
            raise RuntimeError('afgeleide velden kapot')
        monkeypatch.setattr(load, 'herberekenAfgeleideVelden', kapot)
        resultaat = load.loadIncrementeel()
        log = omgeving.pg.log
        assert log.index('SAVEPOINT afgeleide_velden_sp') < log.index('ROLLBACK TO SAVEPOINT afgeleide_velden_sp')
        assert 'RELEASE SAVEPOINT afgeleide_velden_sp' not in log
        assert omgeving.pg.rollbacks == 0 and omgeving.pg.commits >= 2  # schemamigratie en upsert gecommit
        assert resultaat['afgeleide_velden'] is None
        run = verwerkingsrun.huidigeRun()
        assert 'load' in run['tellingen'] and 'afgeleide_velden' not in run['tellingen']
        meldingen = [m for m in run['meldingen'] if m['soort'] == 'afgeleide_velden_mislukt']
        assert len(meldingen) == 1 and meldingen[0]['niveau'] == 'waarschuwing'
        assert 'afgeleide velden kapot' in meldingen[0]['melding']

    def test_afgeleide_velden_in_savepoint(self, omgeving):
        """Zonder fout: SAVEPOINT vóór en RELEASE na de herberekening, in de transactie van de upsert."""
        load.loadIncrementeel()
        log = omgeving.pg.log
        updates = [i for i, s in enumerate(log) if isinstance(s, str) and s.startswith('UPDATE "Def_') and ' AS t ' in s]
        assert log.index('SAVEPOINT afgeleide_velden_sp') < min(updates)
        assert max(updates) < log.index('RELEASE SAVEPOINT afgeleide_velden_sp')
        assert 'ROLLBACK TO SAVEPOINT afgeleide_velden_sp' not in log

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
# Klasse 4: schemamigratie en verwijzingen vanuit gebruikerstabellen (issue 73)
# ============================================================

ARTEFACT_WEG = 'PSY001P1V1A9|Metaal'  # key van een artefact dat in Single_Store_Clean ontbreekt


@pytest.fixture
def gebruikersdata(omgeving):
    """Omgeving met gebruikersdata die naar een verdwijnend artefact (3) en project (5, PSY009) verwijst.

    - bruikleen 0: artefact 0 en project 0 (blijven bestaan);
    - bruikleen 1: artefact 3 (verdwijnt) en project 5 (verdwijnt);
    - conservering 0: artefact 3, conservering 1: artefact 0;
    - extra ABR-materiaal 0: artefact 3, 1: artefact 0.
    """
    pg = omgeving.pg
    pg.tabellen['Def_Artefact']['rijen'][3] = {'primary_key': 3, '_id': 'weg', 'key': ARTEFACT_WEG,
                                               'soort': 'Artefact', 'artefactsoort': 'Metaal'}
    pg.tabellen['Def_Bruikleen']['rijen'][1] = {'primary_key': 1, 'artefactID': 3, 'projectID': 5, 'partijID': 0}
    pg.tabellen['Def_artefact_conservering'] = {
        'kolommen': kolommen('id', 'conservering_id', 'artefact_id'), 'rijen': {
            0: {'id': 0, 'conservering_id': 0, 'artefact_id': 3},
            1: {'id': 1, 'conservering_id': 0, 'artefact_id': 0}}}
    pg.tabellen['Def_artefact_abr'] = {
        'kolommen': kolommen('id', 'abr_materiaal_id', 'artefact_id'), 'rijen': {
            0: {'id': 0, 'abr_materiaal_id': 0, 'artefact_id': 3},
            1: {'id': 1, 'abr_materiaal_id': 0, 'artefact_id': 0}}}
    return omgeving


def nieuwArtefact(clean, id_, key_subnr='PSY001P1V1A9', artefactsoort='Metaal'):
    """Voeg een artefact toe aan Single_Store_Clean (de key wordt key_subnr|artefactsoort)."""
    clean.insert_one({'_id': ObjectId(), 'soort': 'Artefact', 'key_subnr': key_subnr,
                      'artefactsoort': artefactsoort, 'ID': id_})


@pytest.mark.unit
class TestSchemamigratieGebruikersdata:
    """shared/gebruikersdata.migreerSchema: idempotent, alleen wat nodig is, in een eigen transactie."""

    def test_schemawijzigingen_oud_schema(self):
        statements = load.gebruikersdata.bepaalSchemawijzigingen(
            'Def_Bruikleen', {'primary_key': 'NO', 'artefactID': 'NO', 'projectID': 'NO', 'partijID': 'NO'})
        assert statements == [
            'ALTER TABLE "Def_Bruikleen" ALTER COLUMN "artefactID" DROP NOT NULL',
            'ALTER TABLE "Def_Bruikleen" ADD COLUMN IF NOT EXISTS "artefact_verdwenen_key" TEXT',
            'ALTER TABLE "Def_Bruikleen" ADD COLUMN IF NOT EXISTS "artefact_verdwenen_op" TIMESTAMP',
            'ALTER TABLE "Def_Bruikleen" ALTER COLUMN "projectID" DROP NOT NULL',
            'ALTER TABLE "Def_Bruikleen" ADD COLUMN IF NOT EXISTS "project_verdwenen_key" TEXT',
            'ALTER TABLE "Def_Bruikleen" ADD COLUMN IF NOT EXISTS "project_verdwenen_op" TIMESTAMP',
        ]

    def test_schemawijzigingen_bijgewerkt_schema_of_geen_tabel(self):
        bijgewerkt = {'artefact_id': 'YES', 'artefact_verdwenen_key': 'YES', 'artefact_verdwenen_op': 'YES'}
        assert load.gebruikersdata.bepaalSchemawijzigingen('Def_artefact_conservering', bijgewerkt) == []
        assert load.gebruikersdata.bepaalSchemawijzigingen('Def_artefact_conservering', {}) == []
        # Koppelrijen die verwijderd worden hebben geen markering nodig
        assert load.gebruikersdata.bepaalSchemawijzigingen('Def_artefact_abr', {'artefact_id': 'YES'}) == []

    def test_migratie_bij_load_en_idempotent(self, gebruikersdata):
        pg = gebruikersdata.pg
        load.loadIncrementeel()
        alters = [s for s in pg.log if s.startswith('ALTER TABLE') and 'CONSTRAINT' not in s]
        assert sorted(alters) == sorted([
            'ALTER TABLE "Def_Bruikleen" ALTER COLUMN "artefactID" DROP NOT NULL',
            'ALTER TABLE "Def_Bruikleen" ALTER COLUMN "projectID" DROP NOT NULL',
            'ALTER TABLE "Def_Bruikleen" ADD COLUMN IF NOT EXISTS "artefact_verdwenen_key" TEXT',
            'ALTER TABLE "Def_Bruikleen" ADD COLUMN IF NOT EXISTS "artefact_verdwenen_op" TIMESTAMP',
            'ALTER TABLE "Def_Bruikleen" ADD COLUMN IF NOT EXISTS "project_verdwenen_key" TEXT',
            'ALTER TABLE "Def_Bruikleen" ADD COLUMN IF NOT EXISTS "project_verdwenen_op" TIMESTAMP',
            'ALTER TABLE "Def_artefact_conservering" ADD COLUMN IF NOT EXISTS "artefact_verdwenen_key" TEXT',
            'ALTER TABLE "Def_artefact_conservering" ADD COLUMN IF NOT EXISTS "artefact_verdwenen_op" TIMESTAMP',
        ])
        assert pg.tabellen['Def_Bruikleen']['niet_null'] == {'partijID'}
        # Vóór de upsert-transactie en in een eigen transactie gecommit
        assert pg.log.index('COMMIT') < pg.log.index("SET lock_timeout = '30s'")
        assert max(pg.log.index(s) for s in alters) < pg.log.index('COMMIT')

        # Tweede load: het schema klopt, dus alleen lezen
        pg.log.clear()
        load.loadIncrementeel()
        assert not [s for s in pg.log if s.startswith('ALTER TABLE') and 'CONSTRAINT' not in s]

    def test_ontbrekende_gebruikerstabel_overgeslagen(self, omgeving):
        """Def_artefact_conservering bestaat in deze omgeving niet: geen migratie, geen verwijzingen."""
        resultaat = load.loadIncrementeel()
        assert not any('Def_artefact_conservering' in s for s in omgeving.pg.log if s.startswith(('ALTER', 'UPDATE')))
        assert set(resultaat['gebruikersdata']) == {'Def_Bruikleen'}

    def test_fout_in_migratie_rolt_terug_en_laadt_niets(self, omgeving, monkeypatch):
        origineel = NepPgCursor.execute

        def execute(self, sql, params=None):
            if sql.startswith('ALTER TABLE "Def_Bruikleen" ADD COLUMN'):
                raise Exception('nep: lock timeout')
            origineel(self, sql, params)
        monkeypatch.setattr(NepPgCursor, 'execute', execute)
        with pytest.raises(Exception, match='lock timeout'):
            load.loadIncrementeel()
        pg = omgeving.pg
        assert pg.commits == 0 and pg.rollbacks >= 1
        assert not any(s.startswith('INSERT INTO') for s in pg.log)

    def test_migratie_in_transactie_met_set_local(self):
        pg = NepPostgres({'Def_Bruikleen': {'kolommen': kolommen('artefactID'), 'niet_null': {'artefactID'}, 'rijen': {}}})
        uitgevoerd = load.gebruikersdata.migreerSchemaInTransactie(pg, lock_timeout='10s')
        assert pg.log[0] == "SET LOCAL lock_timeout = '10s'"
        assert uitgevoerd[0] == 'ALTER TABLE "Def_Bruikleen" ALTER COLUMN "artefactID" DROP NOT NULL'
        assert pg.log[-1] == 'COMMIT' and pg.commits == 1


@pytest.mark.unit
class TestVerwijzingenGebruikersdata:
    """Loskoppelen, verwijderen en terugkoppelen van gebruikersdata bij verdwenen rijen (issue 73)."""

    def test_loskoppelen_met_markering(self, gebruikersdata):
        resultaat = load.loadIncrementeel()
        pg = gebruikersdata.pg
        assert 3 not in pg.tabellen['Def_Artefact']['rijen'] and 5 not in pg.tabellen['Def_Project']['rijen']

        bruiklenen = pg.tabellen['Def_Bruikleen']['rijen']
        assert bruiklenen[0] == BRUIKLEEN_0
        assert bruiklenen[1] == {'primary_key': 1, 'artefactID': None, 'projectID': None, 'partijID': 0,
                                 'artefact_verdwenen_key': ARTEFACT_WEG, 'artefact_verdwenen_op': NU,
                                 'project_verdwenen_key': 'PSY009', 'project_verdwenen_op': NU}
        conservering = pg.tabellen['Def_artefact_conservering']['rijen']
        assert conservering[0] == {'id': 0, 'conservering_id': 0, 'artefact_id': None,
                                   'artefact_verdwenen_key': ARTEFACT_WEG, 'artefact_verdwenen_op': NU}
        assert conservering[1] == {'id': 1, 'conservering_id': 0, 'artefact_id': 0}
        # Extra ABR-materiaal is een pure koppelrij: verwijderd
        assert pg.tabellen['Def_artefact_abr']['rijen'] == {1: {'id': 1, 'abr_materiaal_id': 0, 'artefact_id': 0}}

        assert resultaat['gebruikersdata'] == {
            'Def_Bruikleen': {'artefactID': {'losgekoppeld': 1, 'teruggekoppeld': 0, 'dubbele_key': 0},
                              'projectID': {'losgekoppeld': 1, 'teruggekoppeld': 0, 'dubbele_key': 0}},
            'Def_artefact_conservering': {'artefact_id': {'losgekoppeld': 1, 'teruggekoppeld': 0, 'dubbele_key': 0}},
            'Def_artefact_abr': {'artefact_id': {'verwijderd': 1}},
        }
        run = verwerkingsrun.huidigeRun()
        assert run['tellingen']['gebruikersdata'] == resultaat['gebruikersdata']
        assert 'gebruikersdata' not in run['tellingen']['load']
        assert resultaat['fk_niet_gevalideerd'] == []

    def test_loskoppelen_voor_verwijderen_in_transactie(self, gebruikersdata):
        load.loadIncrementeel()
        log = gebruikersdata.pg.log
        loskoppelen = log.index(next(s for s in log if s.startswith('UPDATE "Def_Bruikleen" AS g SET "artefactID" = NULL')))
        verwijderen = log.index(next(s for s in log if s.startswith('DELETE FROM "Def_Artefact"')))
        abr = log.index(next(s for s in log if s.startswith('DELETE FROM "Def_artefact_abr" AS g')))
        eerste_add = min(i for i, s in enumerate(log) if 'ADD CONSTRAINT' in s)
        assert loskoppelen < verwijderen < abr < eerste_add
        begin = log.index("SET lock_timeout = '30s'")
        assert 'COMMIT' not in log[begin:eerste_add]

    def test_terugkoppelen_bij_terugkeer_van_dezelfde_key(self, gebruikersdata):
        load.loadIncrementeel()
        # Het artefact keert terug (zelfde key_subnr en artefactsoort) met een nieuwe primary_key
        nieuwArtefact(gebruikersdata.clean, 7)
        resultaat = load.loadIncrementeel()
        pg = gebruikersdata.pg
        assert pg.tabellen['Def_Artefact']['rijen'][7]['key'] == ARTEFACT_WEG

        bruikleen = pg.tabellen['Def_Bruikleen']['rijen'][1]
        assert bruikleen['artefactID'] == 7
        assert bruikleen['artefact_verdwenen_key'] is None and bruikleen['artefact_verdwenen_op'] is None
        # Het project PSY009 is niet teruggekeerd: die verwijzing blijft losgekoppeld
        assert bruikleen['projectID'] is None and bruikleen['project_verdwenen_key'] == 'PSY009'
        conservering = pg.tabellen['Def_artefact_conservering']['rijen'][0]
        assert conservering['artefact_id'] == 7 and conservering['artefact_verdwenen_key'] is None

        assert resultaat['gebruikersdata']['Def_Bruikleen'] == {
            'artefactID': {'losgekoppeld': 0, 'teruggekoppeld': 1, 'dubbele_key': 0},
            'projectID': {'losgekoppeld': 0, 'teruggekoppeld': 0, 'dubbele_key': 0}}
        assert resultaat['gebruikersdata']['Def_artefact_conservering']['artefact_id']['teruggekoppeld'] == 1
        # Een volgende run verandert niets meer
        assert load.loadIncrementeel()['gebruikersdata']['Def_Bruikleen']['artefactID'] == {
            'losgekoppeld': 0, 'teruggekoppeld': 0, 'dubbele_key': 0}

    def test_niet_terugkoppelen_bij_dubbele_key(self, gebruikersdata):
        load.loadIncrementeel()
        nieuwArtefact(gebruikersdata.clean, 7)
        nieuwArtefact(gebruikersdata.clean, 8)
        resultaat = load.loadIncrementeel()
        bruikleen = gebruikersdata.pg.tabellen['Def_Bruikleen']['rijen'][1]
        assert bruikleen['artefactID'] is None and bruikleen['artefact_verdwenen_key'] == ARTEFACT_WEG
        assert resultaat['gebruikersdata']['Def_Bruikleen']['artefactID'] == {
            'losgekoppeld': 0, 'teruggekoppeld': 0, 'dubbele_key': 1}

    def test_vangnet_voor_verwijzing_naar_niet_bestaande_rij(self, gebruikersdata):
        """Een bruikleen die al naar een niet-bestaand artefact wees (van vóór issue 73) wordt losgekoppeld zonder key."""
        pg = gebruikersdata.pg
        pg.tabellen['Def_Bruikleen']['rijen'][2] = {'primary_key': 2, 'artefactID': 42, 'projectID': 0, 'partijID': 0}
        pg.tabellen['Def_artefact_abr']['rijen'][2] = {'id': 2, 'abr_materiaal_id': 0, 'artefact_id': 42}
        resultaat = load.loadIncrementeel()
        bruikleen = pg.tabellen['Def_Bruikleen']['rijen'][2]
        assert bruikleen['artefactID'] is None and bruikleen['artefact_verdwenen_key'] is None
        assert bruikleen['artefact_verdwenen_op'] == NU and bruikleen['projectID'] == 0
        assert 2 not in pg.tabellen['Def_artefact_abr']['rijen']
        assert resultaat['gebruikersdata']['Def_Bruikleen']['artefactID']['losgekoppeld'] == 2
        assert resultaat['gebruikersdata']['Def_artefact_abr']['artefact_id']['verwijderd'] == 2

    def test_niets_verdwenen_niets_gewijzigd(self, omgeving):
        resultaat = load.loadIncrementeel()
        assert omgeving.pg.tabellen['Def_Bruikleen']['rijen'] == {0: BRUIKLEEN_0}
        assert resultaat['gebruikersdata'] == {
            'Def_Bruikleen': {'artefactID': {'losgekoppeld': 0, 'teruggekoppeld': 0, 'dubbele_key': 0},
                              'projectID': {'losgekoppeld': 0, 'teruggekoppeld': 0, 'dubbele_key': 0}}}

    def test_tabel_zonder_markering_overgeslagen(self, omgeving, monkeypatch):
        """Ontbreekt de markering (migratie overgeslagen), dan worden de verwijzingen niet bijgewerkt."""
        monkeypatch.setattr(load, 'migreerSchemaGebruikersdata', lambda conn, lock_timeout=None: [])
        omgeving.pg.tabellen['Def_Bruikleen']['rijen'][1] = {'primary_key': 1, 'artefactID': 0, 'projectID': 5,
                                                             'partijID': 0}
        resultaat = load.loadIncrementeel()
        assert resultaat['gebruikersdata'] == {}
        assert omgeving.pg.tabellen['Def_Bruikleen']['rijen'][1]['projectID'] == 5


# ============================================================
# Klasse 5: Elasticsearch-delta (shared/fulltext.py)
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
