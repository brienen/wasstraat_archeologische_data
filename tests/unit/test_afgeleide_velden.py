"""
Unit tests voor de herberekening van de afgeleide velden in de laadstap (issue 72).

Test loadToDatabase_functions.herberekenAfgeleideVelden en
werkAfgeleideKolommenBij: de opbouw van de SQL, en de uitkomst op een kleine
database in SQLite (de SQL gebruikt alleen wat PostgreSQL en SQLite >= 3.39
allebei kennen: UPDATE ... FROM, COUNT(*) FILTER, IS DISTINCT FROM en CAST).
De verwachte waarden volgen init.init() van de webapplicatie
(app/app/init.py), inclusief de observers van models.py die daarbij meedoen.
Klasse TestGelijkAanFlaskInit draait het echte init.init() (ORM, models.py en
de observers van sqlalchemy_utils) op dezelfde SQLite-database en vergelijkt
de uitkomst met die van de pipeline.

De aanroep vanuit loadIncrementeel staat in test_load_incrementeel.py
(klasse TestLoadIncrementeel, test_afgeleide_velden_*), die vanuit loadAll in
test_loadToDatabase.py (klasse TestLoadAllSequences). De vergelijking met
init.init() op PostgreSQL staat in tests/integration/test_incremental_synthetic_data.py.
"""
import importlib
import importlib.util
import os
import random
import re
import sqlite3
import sys
import types

import pytest

import wasstraat.loadToDatabase_functions as load


ARTEFACT_KOLOMMEN = ['aantal_fotos', 'vondstdatering_vanaf', 'vondstdatering_tot', 'spoordatering_vanaf',
                     'spoordatering_tot', 'datering_vanaf', 'datering_tot']

SQLITE_TE_OUD = sqlite3.sqlite_version_info < (3, 39, 0)


# ============================================================
# Hulpfuncties
# ============================================================

class OpnameCursor:
    """Cursor die de statements bewaart; de telquery geeft per kolom een vast aantal terug."""

    def __init__(self, aantal=0, rowcount=0):
        self.statements = []
        self.aantal = aantal
        self.rowcount = rowcount

    def execute(self, sql, params=None):
        self.statements.append(sql)

    def fetchone(self):
        return tuple(self.aantal for _ in range(self.statements[-1].count('COUNT(*) FILTER')))


def maakDatabase():
    """Kleine database met de tabellen en kolommen die de herberekening leest en schrijft.

    Spoor 1 (1200-1300), spoor 2 (leeg-1350). Vondsten: 1 (spoor 1, 1400-1500),
    2 (spoor 1, leeg), 3 (spoor 2, 0-1450), 4 (zonder spoor, 1600-leeg),
    5 (verwijst naar een niet-bestaand spoor). Artefacten 0 t/m 7, zie
    VERWACHT_ARTEFACT. Foto's: twee objectfoto's en een opgravingsfoto van
    artefact 0, een objectfoto van artefact 1, een objectfoto zonder artefact en
    een van een niet-bestaand artefact.
    """
    db = sqlite3.connect(':memory:')
    cursor = db.cursor()
    cursor.executescript('''
        CREATE TABLE "Def_Project" (primary_key INTEGER PRIMARY KEY, aantal_artefacten INTEGER);
        CREATE TABLE "Def_Spoor" (primary_key INTEGER PRIMARY KEY, spoordatering_vanaf INTEGER,
                                  spoordatering_tot INTEGER);
        CREATE TABLE "Def_Vondst" (primary_key INTEGER PRIMARY KEY, "spoorID" INTEGER,
                                   vondstdatering_vanaf INTEGER, vondstdatering_tot INTEGER);
        CREATE TABLE "Def_Artefact" (primary_key INTEGER PRIMARY KEY, "projectID" INTEGER, "vondstID" INTEGER,
                                     artefactdatering_vanaf INTEGER, artefactdatering_tot INTEGER,
                                     aantal_fotos INTEGER, vondstdatering_vanaf INTEGER, vondstdatering_tot INTEGER,
                                     spoordatering_vanaf INTEGER, spoordatering_tot INTEGER,
                                     datering_vanaf INTEGER, datering_tot INTEGER);
        CREATE TABLE "Def_Bestand" (primary_key INTEGER PRIMARY KEY, "artefactID" INTEGER, bestandsoort TEXT);

        INSERT INTO "Def_Project" VALUES (0, 3), (1, 7), (2, NULL);
        INSERT INTO "Def_Spoor" VALUES (1, 1200, 1300), (2, NULL, 1350);
        INSERT INTO "Def_Vondst" VALUES (1, 1, 1400, 1500), (2, 1, NULL, NULL), (3, 2, 0, 1450),
                                        (4, NULL, 1600, NULL), (5, 99, NULL, NULL);
        INSERT INTO "Def_Artefact" (primary_key, "projectID", "vondstID", artefactdatering_vanaf,
                                    artefactdatering_tot, aantal_fotos) VALUES
            (0, 0, 1, 1450, 1475, 2),
            (1, 0, 1, NULL, NULL, 5),
            (2, 0, 2, NULL, NULL, NULL),
            (3, 1, 3, 0, 0, NULL),
            (4, 1, 4, NULL, 1700, NULL),
            (5, NULL, NULL, 1800, NULL, NULL),
            (6, 1, 5, NULL, NULL, NULL),
            (7, 1, 77, NULL, NULL, NULL);
        INSERT INTO "Def_Bestand" VALUES (0, 0, 'Objectfoto'), (1, 0, 'Objectfoto'), (2, 0, 'Opgravingsfoto'),
                                         (3, 1, 'Objectfoto'), (4, NULL, 'Objectfoto'), (5, 9, 'Objectfoto');
    ''')
    return db


# Per artefact: aantal_fotos, vondstdatering_vanaf/_tot, spoordatering_vanaf/_tot, datering_vanaf/_tot
VERWACHT_ARTEFACT = {
    0: (2, 1400, 1500, 1200, 1300, 1450, 1475),        # artefactdatering gaat voor
    1: (1, 1400, 1500, 1200, 1300, 1400, 1500),        # vondstdatering
    2: (0, None, None, 1200, 1300, 1200, 1300),        # vanaf en tot uit het spoor
    3: (0, 0, 1450, None, 1350, None, 1450),           # 0 telt als leeg: vanaf via vondst (0) naar spoor (leeg)
    4: (0, 1600, None, None, None, 1600, 1700),        # vondst zonder spoor
    5: (0, None, None, None, None, 1800, None),        # artefact zonder vondst
    6: (0, None, None, None, None, None, None),        # vondst met een niet-bestaand spoor
    7: (0, None, None, None, None, None, None),        # niet-bestaande vondst
}
VERWACHT_PROJECT = {0: 3, 1: 4, 2: 0}


def leesArtefacten(db):
    kolommen = ', '.join(ARTEFACT_KOLOMMEN)
    return {r[0]: tuple(r[1:]) for r in db.execute(f'SELECT primary_key, {kolommen} FROM "Def_Artefact"')}


def leesProjecten(db):
    return dict(db.execute('SELECT primary_key, aantal_artefacten FROM "Def_Project"'))


# ============================================================
# Klasse 1: opbouw van de SQL
# ============================================================

@pytest.mark.unit
class TestAfgeleideVeldenSql:
    """De queries en de UPDATE die herberekenAfgeleideVelden uitvoert."""

    def test_tabellen_en_kolommen(self):
        assert list(load.AFGELEIDE_VELDEN) == ['Def_Artefact', 'Def_Project']
        assert load.AFGELEIDE_VELDEN['Def_Artefact']['kolommen'] == ARTEFACT_KOLOMMEN
        assert load.AFGELEIDE_VELDEN['Def_Project']['kolommen'] == ['aantal_artefacten']

    def test_bron_artefact(self):
        bron = ' '.join(load.AFGELEIDE_VELDEN['Def_Artefact']['bron'].split())
        # Alleen objectfoto's (het model Objectfoto), als tekst vergeleken: geen afhankelijkheid van het enumtype
        assert "WHERE CAST(b.bestandsoort AS TEXT) = 'Objectfoto'" in bron
        assert 'COALESCE(f.aantal, 0) AS aantal_fotos' in bron
        # LEFT JOIN: artefacten zonder foto, vondst of spoor doen mee (0 en NULL, zoals init.init())
        assert 'LEFT JOIN "Def_Vondst" v ON v.primary_key = a."vondstID"' in bron
        assert 'LEFT JOIN "Def_Spoor" s ON s.primary_key = v."spoorID"' in bron
        assert ('CASE WHEN COALESCE(a.artefactdatering_vanaf, 0) <> 0 THEN a.artefactdatering_vanaf '
                'WHEN COALESCE(v.vondstdatering_vanaf, 0) <> 0 THEN v.vondstdatering_vanaf '
                'ELSE s.spoordatering_vanaf END AS datering_vanaf') in bron
        assert ('CASE WHEN COALESCE(a.artefactdatering_tot, 0) <> 0 THEN a.artefactdatering_tot '
                'WHEN COALESCE(v.vondstdatering_tot, 0) <> 0 THEN v.vondstdatering_tot '
                'ELSE s.spoordatering_tot END AS datering_tot') in bron

    def test_bron_project(self):
        bron = ' '.join(load.AFGELEIDE_VELDEN['Def_Project']['bron'].split())
        assert 'COUNT(a.primary_key) AS aantal_artefacten' in bron
        assert 'LEFT JOIN "Def_Artefact" a ON a."projectID" = p.primary_key' in bron

    def test_update_alleen_bij_verschil(self):
        cursor = OpnameCursor(aantal=3, rowcount=4)
        tellingen = load.werkAfgeleideKolommenBij(cursor, 'Def_Project', ['x', 'y'], 'SELECT 1')
        telquery, update = cursor.statements
        assert telquery == ('SELECT COUNT(*) FILTER (WHERE t."x" IS DISTINCT FROM n."x"), '
                            'COUNT(*) FILTER (WHERE t."y" IS DISTINCT FROM n."y") FROM "Def_Project" AS t '
                            'JOIN (SELECT 1) AS n ON n.primary_key = t.primary_key')
        assert update == ('UPDATE "Def_Project" AS t SET "x" = n."x", "y" = n."y" FROM (SELECT 1) AS n '
                          'WHERE n.primary_key = t.primary_key '
                          'AND (t."x" IS DISTINCT FROM n."x" OR t."y" IS DISTINCT FROM n."y")')
        assert tellingen == {'x': 3, 'y': 3, 'rijen': 4}

    def test_herbereken_alle_tabellen(self, caplog):
        cursor = OpnameCursor()
        with caplog.at_level('INFO'):
            tellingen = load.herberekenAfgeleideVelden(cursor)
        assert tellingen == {'Def_Artefact': dict({k: 0 for k in ARTEFACT_KOLOMMEN}, rijen=0),
                             'Def_Project': {'aantal_artefacten': 0, 'rijen': 0}}
        assert [s.split(' AS t ')[0] for s in cursor.statements if s.startswith('UPDATE')] == [
            'UPDATE "Def_Artefact"', 'UPDATE "Def_Project"']
        # Alleen de twee tabellen met afgeleide velden worden geschreven
        geschreven = {s.split('"')[1] for s in cursor.statements if s.startswith('UPDATE')}
        assert geschreven == {'Def_Artefact', 'Def_Project'}
        assert 'Afgeleide velden van Def_Artefact herberekend' in caplog.text
        assert "'aantal_fotos': 0" in caplog.text


# ============================================================
# Klasse 2: uitkomst op een echte (SQLite-)database
# ============================================================

@pytest.mark.unit
@pytest.mark.skipif(SQLITE_TE_OUD, reason='SQLite < 3.39 kent IS DISTINCT FROM niet')
class TestAfgeleideVeldenUitkomst:
    """De uitkomst van de SQL op een kleine database met de randgevallen van init.init()."""

    def test_waarden(self):
        db = maakDatabase()
        load.herberekenAfgeleideVelden(db.cursor())
        assert leesArtefacten(db) == VERWACHT_ARTEFACT
        assert leesProjecten(db) == VERWACHT_PROJECT

    def test_tellingen_per_veld(self):
        """Alleen echte wijzigingen tellen: artefact 0 had al 2 foto's, project 0 al 3 artefacten."""
        db = maakDatabase()
        tellingen = load.herberekenAfgeleideVelden(db.cursor())
        assert tellingen['Def_Artefact'] == {
            'aantal_fotos': 7,           # alle behalve artefact 0
            'vondstdatering_vanaf': 4,   # artefact 0, 1, 3 (0) en 4; de andere blijven NULL
            'vondstdatering_tot': 3,     # artefact 0, 1 en 3
            'spoordatering_vanaf': 3,    # artefact 0, 1 en 2
            'spoordatering_tot': 4,      # artefact 0, 1, 2 en 3
            'datering_vanaf': 5,         # artefact 0, 1, 2, 4 en 5
            'datering_tot': 5,           # artefact 0, 1, 2 (spoor), 3 en 4
            'rijen': 8,
        }
        assert tellingen['Def_Project'] == {'aantal_artefacten': 2, 'rijen': 2}

    def test_tweede_keer_niets_gewijzigd(self):
        db = maakDatabase()
        load.herberekenAfgeleideVelden(db.cursor())
        tellingen = load.herberekenAfgeleideVelden(db.cursor())
        assert all(aantal == 0 for t in tellingen.values() for aantal in t.values()), tellingen

    def test_wijziging_in_bron_volgt(self):
        """Een nieuwe foto, een verplaatst artefact en een gewijzigde vondstdatering werken door."""
        db = maakDatabase()
        load.herberekenAfgeleideVelden(db.cursor())
        db.executescript('''
            INSERT INTO "Def_Bestand" VALUES (6, 2, 'Objectfoto');
            UPDATE "Def_Artefact" SET "projectID" = 2 WHERE primary_key = 4;
            UPDATE "Def_Vondst" SET vondstdatering_tot = 1550 WHERE primary_key = 2;
        ''')
        tellingen = load.herberekenAfgeleideVelden(db.cursor())
        artefacten = leesArtefacten(db)
        assert artefacten[2] == (1, None, 1550, 1200, 1300, 1200, 1550)
        assert leesProjecten(db) == {0: 3, 1: 3, 2: 1}
        assert tellingen['Def_Artefact'] == {'aantal_fotos': 1, 'vondstdatering_vanaf': 0, 'vondstdatering_tot': 1,
                                             'spoordatering_vanaf': 0, 'spoordatering_tot': 0,
                                             'datering_vanaf': 0, 'datering_tot': 1, 'rijen': 1}
        assert tellingen['Def_Project'] == {'aantal_artefacten': 2, 'rijen': 2}


# ============================================================
# Klasse 3: gelijk aan het echte init.init() van de webapplicatie
# ============================================================

APP_PAD = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'app'))


@pytest.fixture
def flaskInit(monkeypatch):
    """Het echte app/app/init.py met het echte models.py; shared.database en shared.fulltext nagebootst."""
    for pakket in ('flask_appbuilder', 'sqlalchemy_utils', 'geoalchemy2'):
        pytest.importorskip(pakket)
    monkeypatch.syspath_prepend(APP_PAD)
    monkeypatch.syspath_prepend(os.path.join(APP_PAD, 'app'))
    for naam in ('shared.database', 'shared.fulltext'):
        monkeypatch.setitem(sys.modules, naam, types.ModuleType(naam))
    # Een andere test kan models in sys.modules hebben vervangen door een nabootsing
    if not hasattr(sys.modules.get('models'), 'Model'):
        monkeypatch.delitem(sys.modules, 'models', raising=False)
    models = importlib.import_module('models')
    spec = importlib.util.spec_from_file_location('init_onder_test', os.path.join(APP_PAD, 'app', 'init.py'))
    init = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(init)
    return types.SimpleNamespace(init=init, models=models)


def maakFlaskDatabase(pad, models, seed):
    """SQLite-database met alle tabellen van models.py, de randgevallen van maakDatabase en willekeurige data.

    SQLite kent geen geometrietype: die kolommen worden BLOB. Alleen
    objectfoto's krijgen een artefactID: init.init() faalt (en verandert dan
    niets) als een ander soort bestand een artefactID heeft, omdat de observer
    van Artefact.fotos dan een bestand laadt dat geen Objectfoto is.
    """
    from sqlalchemy.dialects import sqlite as sqlite_dialect
    from sqlalchemy.schema import CreateTable

    db = sqlite3.connect(pad)
    for tabel in models.Model.metadata.sorted_tables:
        ddl = str(CreateTable(tabel).compile(dialect=sqlite_dialect.dialect()))
        db.execute(re.sub(r'geometry\(\w+,\s*\d+\)', 'BLOB', ddl))
    db.executescript('''
        INSERT INTO "Def_Project" (primary_key, projectcd, aantal_artefacten) VALUES (0, 'P0', 3), (1, 'P1', 7), (2, 'P2', NULL);
        INSERT INTO "Def_Spoor" (primary_key, spoordatering_vanaf, spoordatering_tot) VALUES (1, 1200, 1300), (2, NULL, 1350);
        INSERT INTO "Def_Vondst" (primary_key, "spoorID", vondstdatering_vanaf, vondstdatering_tot) VALUES
            (1, 1, 1400, 1500), (2, 1, NULL, NULL), (3, 2, 0, 1450), (4, NULL, 1600, NULL), (5, 99, NULL, NULL);
        INSERT INTO "Def_Artefact" (primary_key, "projectID", "vondstID", artefactdatering_vanaf, artefactdatering_tot,
                                    aantal_fotos, artefactsoort) VALUES
            (0, 0, 1, 1450, 1475, 2, 'Glas'), (1, 0, 1, NULL, NULL, 5, 'Glas'), (2, 0, 2, NULL, NULL, NULL, 'Aardewerk'),
            (3, 1, 3, 0, 0, NULL, 'Onbekend'), (4, 1, 4, NULL, 1700, NULL, 'Glas'),
            (5, NULL, NULL, 1800, NULL, NULL, 'Metaal'), (6, 1, 5, NULL, NULL, NULL, 'Glas'),
            (7, 1, 77, NULL, NULL, NULL, 'Glas');
        INSERT INTO "Def_Bestand" (primary_key, "artefactID", bestandsoort) VALUES (0, 0, 'Objectfoto'),
            (1, 0, 'Objectfoto'), (2, NULL, 'Opgravingsfoto'), (3, 1, 'Objectfoto'), (4, NULL, 'Objectfoto'),
            (5, 9, 'Objectfoto');
    ''')
    rnd = random.Random(seed)
    jaren = [None, None, 0, 1100, 1200, 1300, 1400, 1500]
    for pk in range(10, 40):
        db.execute('INSERT INTO "Def_Spoor" (primary_key, spoordatering_vanaf, spoordatering_tot) VALUES (?, ?, ?)',
                   (pk, rnd.choice(jaren), rnd.choice(jaren)))
    for pk in range(10, 80):
        db.execute('INSERT INTO "Def_Vondst" (primary_key, "spoorID", vondstdatering_vanaf, vondstdatering_tot) '
                   'VALUES (?, ?, ?, ?)', (pk, rnd.choice([None, 999] + list(range(10, 40))),
                                           rnd.choice(jaren), rnd.choice(jaren)))
    for pk in range(10, 300):
        db.execute('INSERT INTO "Def_Artefact" (primary_key, "projectID", "vondstID", artefactdatering_vanaf, '
                   'artefactdatering_tot, aantal_fotos, datering_vanaf, artefactsoort) VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
                   (pk, rnd.choice([None, 0, 1, 2, 5]), rnd.choice([None, 999] + list(range(10, 80))),
                    rnd.choice(jaren), rnd.choice(jaren), rnd.choice([None, 0, 3]), rnd.choice([None, 1]),
                    rnd.choice(['Glas', 'Aardewerk', 'Onbekend', 'Metaal'])))
    for pk in range(10, 500):
        db.execute('INSERT INTO "Def_Bestand" (primary_key, "artefactID", bestandsoort) VALUES (?, ?, ?)',
                   (pk, rnd.choice([None, 9999] + list(range(10, 300))), 'Objectfoto'))
    for pk in range(500, 560):
        db.execute('INSERT INTO "Def_Bestand" (primary_key, bestandsoort) VALUES (?, ?)',
                   (pk, rnd.choice(['Opgravingsfoto', 'Sfeerfoto', 'Objectfoto'])))
    db.commit()
    return db


@pytest.mark.unit
@pytest.mark.skipif(SQLITE_TE_OUD, reason='SQLite < 3.39 kent IS DISTINCT FROM niet')
class TestGelijkAanFlaskInit:
    """De pipeline geeft dezelfde afgeleide velden als init.init() met de ORM en de observers van models.py."""

    @pytest.mark.parametrize('seed', [1, 2, 3])
    def test_gelijk_aan_init(self, flaskInit, tmp_path, monkeypatch, seed):
        import sqlalchemy as sa

        pad = str(tmp_path / 'afgeleid.db')
        db = maakFlaskDatabase(pad, flaskInit.models, seed)

        # Pipeline
        load.herberekenAfgeleideVelden(db.cursor())
        db.commit()
        pipeline = (leesArtefacten(db), leesProjecten(db))
        assert pipeline[0][2] == VERWACHT_ARTEFACT[2] and pipeline[0][3] == VERWACHT_ARTEFACT[3]

        # Velden leegmaken en init.init() laten rekenen; SQLite kent ST_AsEWKB (geometrie van Project) niet
        db.execute('UPDATE "Def_Artefact" SET ' + ', '.join(f'{k} = NULL' for k in ARTEFACT_KOLOMMEN))
        db.execute('UPDATE "Def_Project" SET aantal_artefacten = NULL')
        db.commit()

        def maakEngine(uri):
            engine = sa.create_engine(f'sqlite:///{pad}')

            @sa.event.listens_for(engine, 'connect')
            def geometrieFuncties(verbinding, record):
                for naam in ('ST_AsEWKB', 'AsEWKB'):
                    verbinding.create_function(naam, 1, lambda waarde: waarde)
            return engine
        monkeypatch.setattr(flaskInit.init, 'create_engine', maakEngine)
        flaskInit.init.init()
        flask = (leesArtefacten(db), leesProjecten(db))

        verschillen = {pk: (waarden, flask[0].get(pk)) for pk, waarden in pipeline[0].items() if waarden != flask[0].get(pk)}
        assert not verschillen, f"{len(verschillen)} artefacten wijken af (pipeline, init): {list(verschillen.items())[:5]}"
        assert flask[1] == pipeline[1]
        # De data dekt de randgevallen: dateringen uit artefact, vondst en spoor, en lege dateringen
        assert sum(1 for w in flask[0].values() if w[5] is None) > 0
        assert sum(1 for w in flask[0].values() if w[0] > 0) > 0
