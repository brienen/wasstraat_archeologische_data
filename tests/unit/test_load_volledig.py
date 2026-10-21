"""
Unit tests voor de volledige load (loadAll) met gebruikersdata (issue 71).

De volledige cyclus leegt de gebruikerstabellen niet meer. Transform 4 kent
stabiele sleutels toe; loadAll bepaalt na het laden van de {tabel}_new-tabellen
welke rijen bij de swap hun primary_key verliezen (bepaalVervallenRijen:
verdwenen of hernummerd), koppelt gebruikersdata daarvan los of verwijdert de
koppelrijen (koppelGebruikersdataLos) en koppelt na de rename op key terug
(werkGebruikersdataBijNaSwap).

Verder: shared/fulltext.indexTable slaat koppeltabellen zonder primary_key
over (die blijven nu gevuld, en hun Index-taak faalde daarop).

PostgreSQL wordt nagebootst met de in-memory database uit
test_load_incrementeel.py, aangevuld met de statements van de atomic swap
(CREATE TABLE ... LIKE, RENAME, DROP TABLE) en van deze helpers. Het echte
gedrag wordt getest in tests/integration/test_incremental_synthetic_data.py
(stap i: volledige cyclus na de incrementele runs).
"""
import logging
import re
import types

import pytest

import wasstraat.loadToDatabase_functions as load
from tests.unit.test_load_incrementeel import NepPgCursor, NepPostgres, kolommen, laadFulltext, NU


# ============================================================
# Nabootsing van PostgreSQL met de atomic swap
# ============================================================

class SwapCursor(NepPgCursor):
    """NepPgCursor met de statements van loadAll en van de helpers voor de volledige load."""

    def execute(self, sql, params=None):
        tekst = ' '.join(sql.split())
        tabellen = self.db.tabellen
        m = re.match(r'SELECT o\.primary_key, n\.primary_key IS NULL FROM "(\w+)" AS o LEFT JOIN "(\w+)" AS n '
                     r'ON n\.primary_key = o\.primary_key WHERE n\.primary_key IS NULL OR \((.*)\)$', tekst)
        if m:
            oud, nieuw, voorwaarde = m.groups()
            self.db.log.append(sql)
            self.resultaat = []
            for pk, rij in tabellen[oud]['rijen'].items():
                nieuwe_rij = tabellen[nieuw]['rijen'].get(pk)
                if nieuwe_rij is None:
                    self.resultaat.append((pk, True))
                elif voorwaarde != 'FALSE' and rij.get('key') is not None and rij.get('key') != nieuwe_rij.get('key'):
                    self.resultaat.append((pk, False))
            return
        m = re.match(r'DELETE FROM "(\w+)" AS g WHERE g\."(\w+)" = ANY\(%s\)$', tekst)
        if m:
            self.db.log.append(sql)
            tabel, kolom = m.groups()
            weg = [k for k, rij in tabellen[tabel]['rijen'].items() if rij.get(kolom) in params[0]]
            for k in weg:
                del tabellen[tabel]['rijen'][k]
            self.rowcount = len(weg)
            return
        m = re.match(r'DROP TABLE IF EXISTS "(\w+)" CASCADE$', tekst)
        if m:
            self.db.log.append(sql)
            tabellen.pop(m.group(1), None)
            return
        m = re.match(r'CREATE TABLE "(\w+)" \(LIKE "(\w+)" INCLUDING INDEXES INCLUDING DEFAULTS\)$', tekst)
        if m:
            self.db.log.append(sql)
            tabellen[m.group(1)] = {'kolommen': dict(tabellen[m.group(2)]['kolommen']), 'rijen': {}}
            return
        m = re.match(r'ALTER TABLE "(\w+)" RENAME TO "(\w+)"$', tekst)
        if m:
            self.db.log.append(sql)
            tabellen[m.group(2)] = tabellen.pop(m.group(1))
            return
        super().execute(sql, params)


class SwapPostgres(NepPostgres):
    def cursor(self):
        return SwapCursor(self)


ARTEFACT_KOLOMMEN = kolommen('primary_key', '_id', 'key', 'soort', primary_key='integer')
BRUIKLEEN_KOLOMMEN = kolommen('primary_key', 'artefactID', 'projectID', 'partijID', 'artefact_verdwenen_key',
                              'artefact_verdwenen_op', 'project_verdwenen_key', 'project_verdwenen_op')
CONSERVERING_KOLOMMEN = kolommen('id', 'conservering_id', 'artefact_id', 'artefact_verdwenen_key', 'artefact_verdwenen_op')


def artefact(pk, key):
    return {'primary_key': pk, '_id': f'oid{pk}', 'key': key, 'soort': 'Artefact'}


def bruikleen(pk, artefact_id, project_id=0, **markering):
    rij = {'primary_key': pk, 'artefactID': artefact_id, 'projectID': project_id, 'partijID': 0,
           'artefact_verdwenen_key': None, 'artefact_verdwenen_op': None,
           'project_verdwenen_key': None, 'project_verdwenen_op': None}
    rij.update(markering)
    return rij


def maakPostgres(artefacten, bruiklenen=None, conservering=None, abr=None):
    """PostgreSQL met Def_Project (PSY001 op 0), Def_Artefact en de gebruikerstabellen."""
    return SwapPostgres({
        'Def_Project': {'kolommen': kolommen('primary_key', '_id', 'key', 'soort', primary_key='integer'),
                        'rijen': {0: {'primary_key': 0, '_id': 'p0', 'key': 'PSY001', 'soort': 'Project'}}},
        'Def_Artefact': {'kolommen': ARTEFACT_KOLOMMEN, 'rijen': {r['primary_key']: r for r in artefacten}},
        'Def_Bruikleen': {'kolommen': BRUIKLEEN_KOLOMMEN, 'rijen': {r['primary_key']: r for r in bruiklenen or []}},
        'Def_artefact_conservering': {'kolommen': CONSERVERING_KOLOMMEN, 'rijen': dict(enumerate(conservering or []))},
        'Def_artefact_abr': {'kolommen': kolommen('id', 'abr_materiaal_id', 'artefact_id'),
                             'rijen': dict(enumerate(abr or []))},
        'Def_Partij': {'kolommen': kolommen('primary_key', 'naam'), 'rijen': {0: {'primary_key': 0, 'naam': 'Museum'}}},
    }, fks=[
        ('Def_Bruikleen', 'Def_Bruikleen_artefactID_fkey',
         'FOREIGN KEY ("artefactID") REFERENCES "Def_Artefact"(primary_key) DEFERRABLE', 'Def_Artefact'),
        ('Def_Bruikleen', 'Def_Bruikleen_partijID_fkey',
         'FOREIGN KEY ("partijID") REFERENCES "Def_Partij"(primary_key) DEFERRABLE', 'Def_Partij'),
    ])


@pytest.fixture
def laadAll(monkeypatch):
    """Draai loadAll op een nagebootste PostgreSQL; de nieuwe rijen per soort komen uit een dict."""
    monkeypatch.setattr(load, 'LOAD_TABELLEN', ['Def_Project', 'Def_Artefact'])
    monkeypatch.setattr(load, 'herberekenAfgeleideVelden', lambda cursor: {})

    def draai(pg, nieuw):
        def nepTransfer(soort, table, cursor):
            for rij in nieuw.get(soort, []):
                pg.tabellen[table]['rijen'][rij['primary_key']] = dict(rij)
        monkeypatch.setattr(load, 'getPgConnection', lambda: pg)
        monkeypatch.setattr(load, 'transferToDB', nepTransfer)
        return load.loadAll()
    return draai


PROJECT = [{'primary_key': 0, '_id': 'p0nieuw', 'key': 'PSY001', 'soort': 'Project'}]


# ============================================================
# Klasse 1: vervallen rijen
# ============================================================

@pytest.mark.unit
class TestVervallenRijen:
    """bepaalVervallenRijen: verdwenen en hernummerde primary_keys tussen de huidige en de nieuwe tabel."""

    def test_verdwenen_en_hernummerd(self):
        pg = maakPostgres([artefact(0, 'A'), artefact(1, 'B'), artefact(2, 'C'), artefact(3, None)])
        pg.tabellen['Def_Artefact_new'] = {'kolommen': ARTEFACT_KOLOMMEN, 'rijen': {
            0: artefact(0, 'A'), 1: artefact(1, 'X'), 3: artefact(3, 'D'), 7: artefact(7, 'C')}}
        vervallen = load.bepaalVervallenRijen(pg.cursor(), 'Def_Artefact', 'Def_Artefact_new')
        # 2 (C) heeft een nieuw nummer; 1 hoort nu bij een andere key; 3 had geen key en telt niet als hernummerd
        assert vervallen == {'verdwenen': [2], 'hernummerd': [1]}

    def test_lege_huidige_tabel(self):
        """Eerste run: de tabel is net door de webapplicatie aangemaakt en leeg."""
        pg = maakPostgres([])
        pg.tabellen['Def_Artefact_new'] = {'kolommen': ARTEFACT_KOLOMMEN, 'rijen': {0: artefact(0, 'A')}}
        assert load.bepaalVervallenRijen(pg.cursor(), 'Def_Artefact', 'Def_Artefact_new') == {
            'verdwenen': [], 'hernummerd': []}

    def test_tabel_zonder_key_alleen_verdwenen(self):
        pg = SwapPostgres({
            'Def_X': {'kolommen': kolommen('primary_key', 'naam'), 'rijen': {0: {'primary_key': 0, 'naam': 'a'},
                                                                           1: {'primary_key': 1, 'naam': 'b'}}},
            'Def_X_new': {'kolommen': kolommen('primary_key', 'naam'), 'rijen': {0: {'primary_key': 0, 'naam': 'c'}}},
        })
        cursor = pg.cursor()
        assert load.bepaalVervallenRijen(cursor, 'Def_X', 'Def_X_new') == {'verdwenen': [1], 'hernummerd': []}
        assert pg.log[-1].endswith('OR (FALSE)')

    def test_waarschuwing_bij_hernummerde_rijen(self, caplog):
        pg = maakPostgres([artefact(0, 'A'), artefact(1, 'B')])
        pg.tabellen['Def_Artefact_new'] = {'kolommen': ARTEFACT_KOLOMMEN,
                                           'rijen': {0: artefact(0, 'B'), 1: artefact(1, 'A')}}
        with caplog.at_level(logging.WARNING, logger='airflow.task'):
            vervallen = load.bepaalVervallenSleutels(pg.cursor(), [('Def_Artefact', 'Def_Artefact_new')])
        assert vervallen == {'Def_Artefact': {'verdwenen': [], 'hernummerd': [0, 1]}}
        assert any('Sleutels niet stabiel' in r.getMessage() for r in caplog.records)

    def test_key_controle_alleen_voor_doelen_van_gebruikersdata(self):
        """Alleen Def_Artefact en Def_Project: bij de ABR is de primary_key uit de bron de identiteit,
        en een bestand kan zijn primary_key houden (map en bestandsnaam) terwijl zijn key verandert."""
        assert load.getTabellenMetKeyControle() == ['Def_Artefact', 'Def_Project']

    def test_andere_key_bij_bestand_en_abr_is_geen_hernummering(self, caplog):
        pg = SwapPostgres({})
        for tabel, oud, nieuw in [('Def_Bestand', 'PSY001S1', 'PSY001S2'), ('Def_ABR', 'Ahttp://abr/1', 'Ahttps://abr/1')]:
            pg.tabellen[tabel] = {'kolommen': ARTEFACT_KOLOMMEN, 'rijen': {0: artefact(0, oud)}}
            pg.tabellen[f'{tabel}_new'] = {'kolommen': ARTEFACT_KOLOMMEN, 'rijen': {0: artefact(0, nieuw)}}
        with caplog.at_level(logging.WARNING, logger='airflow.task'):
            vervallen = load.bepaalVervallenSleutels(pg.cursor(), [('Def_Bestand', 'Def_Bestand_new'),
                                                                   ('Def_ABR', 'Def_ABR_new')])
        assert vervallen == {'Def_Bestand': {'verdwenen': [], 'hernummerd': []},
                             'Def_ABR': {'verdwenen': [], 'hernummerd': []}}
        assert not [r for r in caplog.records if r.levelno >= logging.WARNING]

    def test_geen_waarschuwing_bij_stabiele_sleutels(self, caplog):
        pg = maakPostgres([artefact(0, 'A'), artefact(1, 'B')])
        pg.tabellen['Def_Artefact_new'] = {'kolommen': ARTEFACT_KOLOMMEN, 'rijen': {0: artefact(0, 'A')}}
        with caplog.at_level(logging.WARNING, logger='airflow.task'):
            vervallen = load.bepaalVervallenSleutels(pg.cursor(), [('Def_Artefact', 'Def_Artefact_new')])
        assert vervallen == {'Def_Artefact': {'verdwenen': [1], 'hernummerd': []}}
        assert not [r for r in caplog.records if r.levelno >= logging.WARNING]


# ============================================================
# Klasse 2: loadAll met gebruikersdata
# ============================================================

@pytest.mark.unit
class TestLoadAllGebruikersdata:
    """loadAll bewaart de gebruikerstabellen en houdt hun verwijzingen geldig (issue 71)."""

    def test_stabiele_sleutels_gebruikersdata_blijft_gekoppeld(self, laadAll):
        pg = maakPostgres([artefact(0, 'A'), artefact(1, 'B')], bruiklenen=[bruikleen(0, 1)],
                          conservering=[{'id': 0, 'conservering_id': 0, 'artefact_id': 0}],
                          abr=[{'id': 0, 'abr_materiaal_id': 3, 'artefact_id': 1}])
        resultaat = laadAll(pg, {'Project': PROJECT, 'Artefact': [artefact(0, 'A'), artefact(1, 'B'), artefact(2, 'N')]})

        assert sorted(pg.tabellen['Def_Artefact']['rijen']) == [0, 1, 2]
        assert pg.tabellen['Def_Bruikleen']['rijen'] == {0: bruikleen(0, 1)}
        assert pg.tabellen['Def_artefact_conservering']['rijen'] == {0: {'id': 0, 'conservering_id': 0, 'artefact_id': 0}}
        assert pg.tabellen['Def_artefact_abr']['rijen'] == {0: {'id': 0, 'abr_materiaal_id': 3, 'artefact_id': 1}}
        assert pg.tabellen['Def_Partij']['rijen'] == {0: {'primary_key': 0, 'naam': 'Museum'}}
        assert resultaat['vervallen']['Def_Artefact'] == {'verdwenen': 0, 'hernummerd': 0}
        assert resultaat['gebruikersdata']['Def_Bruikleen']['artefactID'] == {
            'losgekoppeld': 0, 'teruggekoppeld': 0, 'dubbele_key': 0}
        # Geen _new- of _old-tabellen over en geen TRUNCATE
        assert not [t for t in pg.tabellen if t.endswith(('_new', '_old'))]
        assert not [s for s in pg.log if isinstance(s, str) and 'TRUNCATE' in s]

    def test_verdwenen_artefact_losgekoppeld_koppelrij_verwijderd(self, laadAll):
        pg = maakPostgres([artefact(0, 'A'), artefact(1, 'B')], bruiklenen=[bruikleen(0, 0), bruikleen(1, 1)],
                          conservering=[{'id': 0, 'conservering_id': 0, 'artefact_id': 1}],
                          abr=[{'id': 0, 'abr_materiaal_id': 3, 'artefact_id': 1},
                               {'id': 1, 'abr_materiaal_id': 3, 'artefact_id': 0}])
        resultaat = laadAll(pg, {'Project': PROJECT, 'Artefact': [artefact(0, 'A')]})

        assert pg.tabellen['Def_Bruikleen']['rijen'][0] == bruikleen(0, 0)
        assert pg.tabellen['Def_Bruikleen']['rijen'][1] == bruikleen(1, None, artefact_verdwenen_key='B',
                                                                     artefact_verdwenen_op=NU)
        assert pg.tabellen['Def_artefact_conservering']['rijen'][0] == {
            'id': 0, 'conservering_id': 0, 'artefact_id': None, 'artefact_verdwenen_key': 'B', 'artefact_verdwenen_op': NU}
        assert pg.tabellen['Def_artefact_abr']['rijen'] == {1: {'id': 1, 'abr_materiaal_id': 3, 'artefact_id': 0}}
        assert resultaat['vervallen']['Def_Artefact'] == {'verdwenen': 1, 'hernummerd': 0}
        assert resultaat['gebruikersdata']['Def_Bruikleen']['artefactID']['losgekoppeld'] == 1
        assert resultaat['gebruikersdata']['Def_artefact_abr']['artefact_id']['verwijderd'] == 1

    def test_eerder_losgekoppelde_bruikleen_keert_terug(self, laadAll):
        """Een bruikleen die een incrementele run losgekoppeld heeft, wordt gekoppeld als de key terugkomt."""
        pg = maakPostgres([artefact(0, 'A')], bruiklenen=[bruikleen(0, None, artefact_verdwenen_key='B',
                                                                    artefact_verdwenen_op='gisteren')])
        resultaat = laadAll(pg, {'Project': PROJECT, 'Artefact': [artefact(0, 'A'), artefact(4, 'B')]})
        assert pg.tabellen['Def_Bruikleen']['rijen'][0] == bruikleen(0, 4)
        assert resultaat['gebruikersdata']['Def_Bruikleen']['artefactID']['teruggekoppeld'] == 1

    def test_hernummerde_sleutels_loskoppelen_en_op_key_terugkoppelen(self, laadAll, caplog):
        """Vangnet voor Mongo-data zonder stabiele sleutels (DAG_Load_Only): A en B wisselen van nummer."""
        pg = maakPostgres([artefact(0, 'A'), artefact(1, 'B'), artefact(2, 'K'), artefact(3, 'L')],
                          bruiklenen=[bruikleen(0, 0), bruikleen(1, 2)],
                          abr=[{'id': 0, 'abr_materiaal_id': 3, 'artefact_id': 0},
                               {'id': 1, 'abr_materiaal_id': 3, 'artefact_id': 3}])
        nieuw = [artefact(0, 'B'), artefact(1, 'A'), artefact(5, 'K'), artefact(6, 'K'), artefact(3, 'L')]
        with caplog.at_level(logging.WARNING, logger='airflow.task'):
            resultaat = laadAll(pg, {'Project': PROJECT, 'Artefact': nieuw})

        assert any('Sleutels niet stabiel' in r.getMessage() for r in caplog.records)
        bruiklenen = pg.tabellen['Def_Bruikleen']['rijen']
        # A heeft nu nummer 1: de bruikleen volgt de key, niet het nummer
        assert bruiklenen[0] == bruikleen(0, 1)
        # K komt nu twee keer voor: losgekoppeld met markering, niet teruggekoppeld
        assert bruiklenen[1] == bruikleen(1, None, artefact_verdwenen_key='K', artefact_verdwenen_op=NU)
        # Koppelrij van een hernummerd artefact verwijderd, die van een stabiel artefact (L) blijft
        assert pg.tabellen['Def_artefact_abr']['rijen'] == {1: {'id': 1, 'abr_materiaal_id': 3, 'artefact_id': 3}}
        assert resultaat['vervallen']['Def_Artefact'] == {'verdwenen': 1, 'hernummerd': 2}
        assert resultaat['gebruikersdata']['Def_Bruikleen']['artefactID'] == {
            'losgekoppeld': 2, 'teruggekoppeld': 1, 'dubbele_key': 1}

    def test_abr_met_gewijzigde_uri_houdt_koppelrij(self, laadAll, monkeypatch):
        """De primary_key van een ABR-begrip komt uit de bron; een nieuwe uri (key) laat de koppelrij staan."""
        monkeypatch.setattr(load, 'LOAD_TABELLEN', ['Def_ABR', 'Def_Project', 'Def_Artefact'])
        pg = maakPostgres([artefact(0, 'A')], abr=[{'id': 0, 'abr_materiaal_id': 3, 'artefact_id': 0}])
        pg.tabellen['Def_ABR'] = {'kolommen': ARTEFACT_KOLOMMEN, 'rijen': {3: artefact(3, 'Ahttp://abr/3')}}
        resultaat = laadAll(pg, {'Project': PROJECT, 'Artefact': [artefact(0, 'A')], 'ABR': [artefact(3, 'Ahttps://abr/3')]})
        assert pg.tabellen['Def_artefact_abr']['rijen'] == {0: {'id': 0, 'abr_materiaal_id': 3, 'artefact_id': 0}}
        assert resultaat['vervallen']['Def_ABR'] == {'verdwenen': 0, 'hernummerd': 0}
        assert resultaat['gebruikersdata']['Def_artefact_abr'] == {'artefact_id': {'verwijderd': 0},
                                                                  'abr_materiaal_id': {'verwijderd': 0}}

    def test_eerste_run_op_lege_database(self, laadAll):
        pg = maakPostgres([])
        pg.tabellen['Def_Project']['rijen'] = {}
        resultaat = laadAll(pg, {'Project': PROJECT, 'Artefact': [artefact(0, 'A')]})
        assert sorted(pg.tabellen['Def_Artefact']['rijen']) == [0]
        assert resultaat['vervallen'] == {'Def_Project': {'verdwenen': 0, 'hernummerd': 0},
                                          'Def_Artefact': {'verdwenen': 0, 'hernummerd': 0}}
        assert pg.tabellen['Def_Bruikleen']['rijen'] == {}

    def test_loskoppelen_voor_rename_terugkoppelen_erna(self, laadAll):
        pg = maakPostgres([artefact(0, 'A'), artefact(1, 'B')], bruiklenen=[bruikleen(0, 1)])
        laadAll(pg, {'Project': PROJECT, 'Artefact': [artefact(0, 'A')]})
        log = [s for s in pg.log if isinstance(s, str)]
        loskoppelen = log.index(next(s for s in log if s.startswith('UPDATE "Def_Bruikleen" AS g SET "artefactID" = NULL')))
        renames = [i for i, s in enumerate(log) if 'RENAME TO' in s]
        terug = log.index(next(s for s in log if s.startswith('UPDATE "Def_Bruikleen" AS g SET "artefactID" = d.primary_key')))
        assert loskoppelen < min(renames) and max(renames) < terug
        swap = log.index("SET lock_timeout = '5s'")
        einde_swap = log.index('COMMIT', terug)
        assert 'COMMIT' not in log[swap:terug] and einde_swap > terug
        # De FK's van de gebruikerstabellen worden na de swap hersteld (FASE 2b)
        herstel = [i for i, s in enumerate(log) if 'ADD CONSTRAINT "Def_Bruikleen_artefactID_fkey"' in s]
        assert herstel and herstel[0] > einde_swap


@pytest.mark.unit
class TestVerwijderKoppelrijen:
    """verwijderKoppelrijen: alleen verwijzingen met beleid VERWIJDEREN naar de vervallen primary_keys."""

    def test_alleen_koppelrijen_naar_vervallen_rijen(self):
        pg = maakPostgres([artefact(0, 'A')], bruiklenen=[bruikleen(0, 0)],
                          abr=[{'id': 0, 'abr_materiaal_id': 3, 'artefact_id': 0},
                               {'id': 1, 'abr_materiaal_id': 3, 'artefact_id': 5}])
        cursor = pg.cursor()
        verwijzingen, tellingen = load.bepaalVerwijzingen(cursor, ['Def_Artefact'])
        aantal = load.verwijderKoppelrijen(cursor, 'Def_Artefact', [0], verwijzingen, tellingen)
        assert aantal == 1
        assert pg.tabellen['Def_artefact_abr']['rijen'] == {1: {'id': 1, 'abr_materiaal_id': 3, 'artefact_id': 5}}
        # De bruikleen (beleid LOSKOPPELEN) is niet aangeraakt
        assert pg.tabellen['Def_Bruikleen']['rijen'] == {0: bruikleen(0, 0)}
        assert tellingen['Def_artefact_abr']['artefact_id'] == {'verwijderd': 1}

    def test_geen_primary_keys_geen_statement(self):
        pg = maakPostgres([artefact(0, 'A')])
        cursor = pg.cursor()
        verwijzingen, tellingen = load.bepaalVerwijzingen(cursor, ['Def_Artefact'])
        voor = len(pg.log)
        assert load.verwijderKoppelrijen(cursor, 'Def_Artefact', [], verwijzingen, tellingen) == 0
        assert len(pg.log) == voor


# ============================================================
# Klasse 4: zoekindex van koppeltabellen (shared/fulltext.indexTable)
# ============================================================

class _NepVerbindingMetTransactie:
    def __init__(self, uitgevoerd):
        self.uitgevoerd = uitgevoerd

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execution_options(self, **kwargs):
        return self

    def begin(self):
        return self

    def execute(self, sql):
        self.uitgevoerd.append(sql)
        return iter([{'primary_key': 3, 'naam': 'a'}])


@pytest.fixture
def indexeren(monkeypatch):
    """shared/fulltext.indexTable met een nagebootste PostgreSQL (MetaData) en Elasticsearch."""
    module = laadFulltext()
    uitgevoerd, aangemaakt, gebulkt = [], [], []

    class NepMetaData:
        def __init__(self, bind=None):
            self.tables = {
                'Def_artefact_abr': types.SimpleNamespace(columns={'id': 1, 'abr_materiaal_id': 1, 'artefact_id': 1}),
                'Def_Vondst': types.SimpleNamespace(columns={'primary_key': 1, 'naam': 1}),
            }

        @staticmethod
        def reflect(metadata):
            return None

    indices = types.SimpleNamespace(
        create=lambda index, ignore=None: aangemaakt.append(index),
        exists=lambda index: False, exists_alias=lambda name: False,
        update_aliases=lambda body: None, delete=lambda index, ignore=None: None)
    es = types.SimpleNamespace(indices=indices, count=lambda index: {'count': 1})
    monkeypatch.setattr(module, 'db', types.SimpleNamespace(MetaData=NepMetaData))
    monkeypatch.setattr(module, 'Elasticsearch', lambda host: es)
    monkeypatch.setattr(module, 'create_engine', lambda uri: types.SimpleNamespace(
        connect=lambda: _NepVerbindingMetTransactie(uitgevoerd)))
    monkeypatch.setattr(module, 'getCols', lambda verbinding, tabel: [{'name': 'primary_key'}, {'name': 'naam'}])
    monkeypatch.setattr(module.helpers, 'bulk', lambda client, docs: gebulkt.extend(docs))
    return types.SimpleNamespace(module=module, uitgevoerd=uitgevoerd, aangemaakt=aangemaakt, gebulkt=gebulkt)


@pytest.mark.unit
class TestIndexKoppeltabellen:
    """Koppeltabellen zonder primary_key worden niet geïndexeerd (issue 71).

    Tot issue 71 leegde de volledige cyclus Def_artefact_abr en
    Def_artefact_conservering, zodat hun taak Index_<tabel> niets te doen had.
    Nu blijven hun rijen staan; zonder primary_key faalde de indexering.
    """

    def test_koppeltabel_overgeslagen(self, indexeren):
        indexeren.module.indexTable('Def_artefact_abr')
        assert indexeren.uitgevoerd == [] and indexeren.aangemaakt == [] and indexeren.gebulkt == []

    def test_tabel_met_primary_key_wordt_geindexeerd(self, indexeren):
        indexeren.module.indexTable('Def_Vondst')
        assert indexeren.uitgevoerd == ['SELECT "primary_key", "naam" FROM public."Def_Vondst"']
        assert len(indexeren.aangemaakt) == 1 and indexeren.aangemaakt[0].startswith('def_vondst_')
        assert [d['_id'] for d in indexeren.gebulkt] == [3]
