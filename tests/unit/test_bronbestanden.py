"""
Unit tests voor wasstraat/bronbestanden.py (incrementeel laden, issue 61).

Test met tijdelijke mappen:
- de selectie van MDB-bestanden (gelijk aan de glob van importMDB.sh)
- de vingerafdruk (grootte + mtime, sha256 alleen bij afwijking)
- de statusbepaling nieuw/gewijzigd/ongewijzigd/verwijderd
- het schrijven van de lijstbestanden voor importMDB.sh
- de registratierijen voor Def_Bronbestand
- de taken bepaalDelta, registreerBronbestanden en registreerVolledigeCyclus
  met een nagebootste MongoDB (nep_mongo) en zonder PostgreSQL.
"""
import hashlib
import os
import sys
import types
import pytest
from unittest.mock import MagicMock

# Mock shared.image_util (wordt geïmporteerd door image_import.py, vereist PIL/pdf2image/magic)
if "shared.image_util" not in sys.modules:
    sys.modules["shared.image_util"] = types.ModuleType("shared.image_util")

import shared.config as config
import wasstraat.verwerkingsrun as verwerkingsrun
import wasstraat.bronbestanden as bronbestanden
from tests.unit.nep_mongo import NepClient


# ============================================================
# Hulpfuncties en fixtures
# ============================================================

def schrijf(pad, inhoud=b'inhoud', mtime=None):
    """Schrijf een bestand (mappen worden aangemaakt) en zet optioneel de mtime."""
    os.makedirs(os.path.dirname(pad), exist_ok=True)
    with open(pad, 'wb') as f:
        f.write(inhoud)
    if mtime is not None:
        os.utime(pad, (mtime, mtime))
    return str(pad)


def sha(inhoud):
    return hashlib.sha256(inhoud).hexdigest()


@pytest.fixture
def invoer(tmp_path, monkeypatch):
    """Zet alle invoerpaden van config naar een tijdelijke mappenstructuur."""
    mappen = {
        'AIRFLOW_INPUT_PROJECTEN': tmp_path / 'input' / 'projecten',
        'AIRFLOW_INPUT_PROJECTENLIJST': tmp_path / 'input' / 'projectenlijst',
        'AIRFLOW_INPUT_MAGAZIJNLIJST': tmp_path / 'input' / 'magazijnlijst',
        'AIRFLOW_INPUT_FOTOLIJST': tmp_path / 'input' / 'fotolijst',
        'AIRFLOW_INPUT_MONSTER': tmp_path / 'input' / 'monsterdatabase',
        'AIRFLOW_INPUT_RAPPORTEN': tmp_path / 'input' / 'rapporten',
    }
    for naam, pad in mappen.items():
        pad.mkdir(parents=True)
        monkeypatch.setattr(config, naam, str(pad))
    monkeypatch.setattr(config, 'FILE_ABREXCEL', str(tmp_path / 'input' / 'referentietabellen' / 'abr.xlsx'))
    monkeypatch.setattr(config, 'FILE_EXTRA_PROJECTS', str(tmp_path / 'input' / 'projectenlijst' / 'extra.xlsx'))
    monkeypatch.setattr(config, 'FILE_IMPORT_FILES_EXCEL', str(tmp_path / 'input' / 'referentietabellen' / 'bestanden.xlsx'))
    monkeypatch.setattr(config, 'AIRFLOW_TEMPDIR', str(tmp_path / 'tmp'))
    # Afbeeldingen: de selectie zelf zit in image_import en wordt hier vervangen
    afbeeldingen = []
    monkeypatch.setattr(bronbestanden.image_import, 'getImageFilenames', lambda overgeslagen=None: list(afbeeldingen))
    return types.SimpleNamespace(root=tmp_path, afbeeldingen=afbeeldingen,
                                 **{naam: str(pad) for naam, pad in mappen.items()})


@pytest.fixture
def nep_client(monkeypatch):
    """Vervang de MongoClients van verwerkingsrun en bronbestanden door een in-memory nabootsing."""
    client = NepClient()
    monkeypatch.setattr(verwerkingsrun, '_getClient', lambda: client)
    monkeypatch.setattr(bronbestanden, '_getClient', lambda: client)
    return client


@pytest.fixture
def registratie(monkeypatch):
    """Vervang de PostgreSQL-registratie door een dict; schrijfacties worden vastgelegd."""
    staat = types.SimpleNamespace(rijen={}, geschreven=[], bijgewerkt=[])
    monkeypatch.setattr(bronbestanden, 'leesRegistratie', lambda: dict(staat.rijen))

    def schrijfRegistratie(rijen, bijwerken):
        staat.geschreven.extend(rijen)
        staat.bijgewerkt.extend(bijwerken)
    monkeypatch.setattr(bronbestanden, 'schrijfRegistratie', schrijfRegistratie)
    return staat


def staging(client):
    return client[config.DB_STAGING]


# ============================================================
# Klasse 1: selectie van MDB-bestanden
# ============================================================

@pytest.mark.unit
class TestZoekMdbBestanden:
    """De selectie moet gelijk zijn aan de glob "$1"/**/*.mdb "$1"/**/*.accdb van importMDB.sh."""

    def test_recursief_mdb_en_accdb(self, tmp_path):
        a = schrijf(tmp_path / 'SY001' / 'C Database' / 'opgravingSY001.mdb')
        b = schrijf(tmp_path / 'SY002' / 'db.accdb')
        c = schrijf(tmp_path / 'top.mdb')
        assert bronbestanden.zoekMdbBestanden(str(tmp_path)) == sorted([a, b, c])

    def test_extensie_is_hoofdlettergevoelig(self, tmp_path):
        schrijf(tmp_path / 'SY001' / 'OUD.MDB')
        schrijf(tmp_path / 'SY001' / 'notities.txt')
        assert bronbestanden.zoekMdbBestanden(str(tmp_path)) == []

    def test_verborgen_bestanden_en_mappen_overgeslagen(self, tmp_path):
        schrijf(tmp_path / '.verborgen' / 'x.mdb')
        schrijf(tmp_path / 'SY001' / '.y.mdb')
        zichtbaar = schrijf(tmp_path / 'SY001' / 'y.mdb')
        assert bronbestanden.zoekMdbBestanden(str(tmp_path)) == [zichtbaar]

    def test_niet_bestaande_map(self, tmp_path):
        assert bronbestanden.zoekMdbBestanden(str(tmp_path / 'bestaat_niet')) == []
        assert bronbestanden.zoekMdbBestanden(None) == []


# ============================================================
# Klasse 2: vingerafdruk
# ============================================================

@pytest.mark.unit
class TestVingerafdruk:
    """Test grootte/mtime en sha256."""

    def test_sha256_gelijk_aan_hashlib(self, tmp_path):
        inhoud = os.urandom(3 * 1024 * 1024 + 17)  # meerdere blokken
        pad = schrijf(tmp_path / 'groot.mdb', inhoud)
        assert bronbestanden.berekenSha256(pad) == sha(inhoud)

    def test_grootte_en_mtime(self, tmp_path):
        pad = schrijf(tmp_path / 'a.mdb', b'12345', mtime=1700000000.5)
        assert bronbestanden.leesVingerafdruk(pad) == (5, 1700000000.5)


# ============================================================
# Klasse 3: statusbepaling
# ============================================================

@pytest.mark.unit
class TestBepaalStatussen:
    """Test nieuw/gewijzigd/ongewijzigd/verwijderd en wanneer de hash wordt berekend."""

    def maakScan(self, pad, categorie='projecten'):
        grootte, mtime = bronbestanden.leesVingerafdruk(pad)
        return {pad: {'categorie': categorie, 'grootte': grootte, 'mtime': mtime}}

    def reg(self, pad, inhoud, status='verwerkt', categorie='projecten', mtime=None):
        grootte, huidige_mtime = bronbestanden.leesVingerafdruk(pad)
        return {pad: {'categorie': categorie, 'grootte': len(inhoud), 'mtime': mtime if mtime is not None else huidige_mtime,
                      'sha256': sha(inhoud), 'status': status}}

    def statusVan(self, records, pad):
        return [r for r in records if r['pad'] == pad][0]

    def test_nieuw_bestand_krijgt_hash(self, tmp_path):
        pad = schrijf(tmp_path / 'SY003' / 'a.mdb', b'nieuw')
        records, hashes = bronbestanden.bepaalStatussen(self.maakScan(pad), {})
        assert records[0]['status'] == 'nieuw'
        assert records[0]['sha256'] == sha(b'nieuw')
        assert hashes == 1

    def test_ongewijzigd_zonder_hash_berekening(self, tmp_path):
        pad = schrijf(tmp_path / 'a.mdb', b'zelfde', mtime=1700000000)
        teller = MagicMock(side_effect=AssertionError("hash mag niet berekend worden"))
        records, hashes = bronbestanden.bepaalStatussen(self.maakScan(pad), self.reg(pad, b'zelfde'), berekenHash=teller)
        assert records[0]['status'] == 'ongewijzigd'
        assert records[0]['vingerafdruk_bijgewerkt'] is False
        assert hashes == 0
        teller.assert_not_called()

    def test_alleen_mtime_gewijzigd_is_ongewijzigd_met_nieuwe_vingerafdruk(self, tmp_path):
        pad = schrijf(tmp_path / 'a.mdb', b'zelfde', mtime=1700000500)
        records, hashes = bronbestanden.bepaalStatussen(self.maakScan(pad), self.reg(pad, b'zelfde', mtime=1700000000))
        assert records[0]['status'] == 'ongewijzigd'
        assert records[0]['vingerafdruk_bijgewerkt'] is True
        assert records[0]['mtime'] == 1700000500
        assert hashes == 1

    def test_inhoud_gewijzigd(self, tmp_path):
        pad = schrijf(tmp_path / 'a.mdb', b'nieuwe inhoud', mtime=1700000500)
        records, hashes = bronbestanden.bepaalStatussen(self.maakScan(pad), self.reg(pad, b'oude inhoud', mtime=1700000000))
        assert records[0]['status'] == 'gewijzigd'
        assert records[0]['sha256'] == sha(b'nieuwe inhoud')
        assert hashes == 1

    def test_zelfde_grootte_en_mtime_maar_andere_hash_in_registratie_telt_niet(self, tmp_path):
        """Bij gelijke grootte en mtime wordt de geregistreerde hash vertrouwd (snelle vingerafdruk)."""
        pad = schrijf(tmp_path / 'a.mdb', b'abc', mtime=1700000000)
        geregistreerd = {pad: {'categorie': 'projecten', 'grootte': 3, 'mtime': 1700000000.0, 'sha256': 'x' * 64, 'status': 'verwerkt'}}
        records, hashes = bronbestanden.bepaalStatussen(self.maakScan(pad), geregistreerd)
        assert records[0]['status'] == 'ongewijzigd'
        assert hashes == 0

    def test_verwijderd_bestand(self, tmp_path):
        pad = str(tmp_path / 'weg.mdb')
        geregistreerd = {pad: {'categorie': 'projecten', 'grootte': 3, 'mtime': 1.0, 'sha256': 'a' * 64, 'status': 'verwerkt'}}
        records, hashes = bronbestanden.bepaalStatussen({}, geregistreerd)
        assert records == [{'pad': pad, 'categorie': 'projecten', 'status': 'verwijderd', 'grootte': 3, 'mtime': 1.0,
                            'sha256': 'a' * 64, 'vingerafdruk_bijgewerkt': False}]
        assert hashes == 0

    def test_al_verwijderd_wordt_niet_opnieuw_gemeld(self, tmp_path):
        pad = str(tmp_path / 'weg.mdb')
        geregistreerd = {pad: {'categorie': 'projecten', 'grootte': 3, 'mtime': 1.0, 'sha256': 'a' * 64, 'status': 'verwijderd'}}
        records, _ = bronbestanden.bepaalStatussen({}, geregistreerd)
        assert records == []

    def test_teruggekeerd_bestand_is_nieuw(self, tmp_path):
        pad = schrijf(tmp_path / 'terug.mdb', b'terug')
        records, _ = bronbestanden.bepaalStatussen(self.maakScan(pad), self.reg(pad, b'terug', status='verwijderd'))
        assert records[0]['status'] == 'nieuw'

    def test_mislukt_bestand_wordt_opnieuw_verwerkt(self, tmp_path):
        pad = schrijf(tmp_path / 'a.mdb', b'zelfde', mtime=1700000000)
        records, hashes = bronbestanden.bepaalStatussen(self.maakScan(pad), self.reg(pad, b'zelfde', status='mislukt'))
        assert records[0]['status'] == 'gewijzigd'
        assert hashes == 0

    def test_categorie_uit_scan(self, tmp_path):
        pad = schrijf(tmp_path / 'f.jpg', b'jpg')
        records, _ = bronbestanden.bepaalStatussen(self.maakScan(pad, categorie='afbeeldingen'), {})
        assert records[0]['categorie'] == 'afbeeldingen'


# ============================================================
# Klasse 4: scannen
# ============================================================

@pytest.mark.unit
class TestScanBronbestanden:
    """Test het scannen van alle categorieën."""

    def test_alle_categorieen(self, invoer):
        mdb = schrijf(os.path.join(invoer.AIRFLOW_INPUT_PROJECTEN, 'SY001', 'C Database', 'opgravingSY001.mdb'))
        lijst = schrijf(os.path.join(invoer.AIRFLOW_INPUT_PROJECTENLIJST, 'projectenlijst.mdb'))
        monster = schrijf(os.path.join(invoer.AIRFLOW_INPUT_MONSTER, 'MONSTERS.mdb'))
        foto = schrijf(os.path.join(invoer.AIRFLOW_INPUT_PROJECTEN, 'SY001', 'L Fotos', 'SY001_F001.jpg'))
        invoer.afbeeldingen.extend([foto, foto])  # dubbelingen worden ontdubbeld
        abr = schrijf(config.FILE_ABREXCEL)
        extra = schrijf(config.FILE_EXTRA_PROJECTS)

        gescand = bronbestanden.scanBronbestanden()
        categorieen = {pad: info['categorie'] for pad, info in gescand.items()}
        assert categorieen == {mdb: 'projecten', lijst: 'projectenlijst', monster: 'monsterdatabase',
                               foto: 'afbeeldingen', abr: 'referentietabellen', extra: 'extra_projecten'}
        assert gescand[mdb]['grootte'] == len(b'inhoud')

    def test_ontbrekende_losse_bestanden_worden_overgeslagen(self, invoer):
        assert bronbestanden.scanBronbestanden() == {}

    def test_onleesbaar_bestand_wordt_overgeslagen(self, invoer):
        invoer.afbeeldingen.append(os.path.join(invoer.AIRFLOW_INPUT_PROJECTEN, 'weg.jpg'))
        assert bronbestanden.scanBronbestanden() == {}


# ============================================================
# Klasse 5: lijsten, tellingen en lijstbestanden
# ============================================================

RECORDS = [
    {'pad': '/input/projecten/SY003/a.mdb', 'categorie': 'projecten', 'status': 'nieuw'},
    {'pad': '/input/projecten/SY002/b.mdb', 'categorie': 'projecten', 'status': 'gewijzigd'},
    {'pad': '/input/projecten/SY001/c.mdb', 'categorie': 'projecten', 'status': 'ongewijzigd'},
    {'pad': '/input/projecten/SY004/d.mdb', 'categorie': 'projecten', 'status': 'verwijderd'},
    {'pad': '/input/projecten/SY003/f.jpg', 'categorie': 'afbeeldingen', 'status': 'nieuw'},
]


@pytest.mark.unit
class TestLijsten:
    """Test maakDeltaLijsten, telDelta, schrijfLijstbestanden en begrensLijsten."""

    def test_delta_lijsten_per_status_en_categorie(self):
        lijsten = bronbestanden.maakDeltaLijsten(RECORDS)
        assert lijsten['nieuw'] == {'projecten': ['/input/projecten/SY003/a.mdb'], 'afbeeldingen': ['/input/projecten/SY003/f.jpg']}
        assert lijsten['verwijderd'] == {'projecten': ['/input/projecten/SY004/d.mdb']}
        assert set(lijsten) == {'nieuw', 'gewijzigd', 'ongewijzigd', 'verwijderd'}

    def test_tellingen(self):
        tellingen = bronbestanden.telDelta(bronbestanden.maakDeltaLijsten(RECORDS))
        assert tellingen['totaal'] == {'nieuw': 2, 'gewijzigd': 1, 'ongewijzigd': 1, 'verwijderd': 1}
        assert tellingen['projecten'] == {'nieuw': 1, 'gewijzigd': 1, 'ongewijzigd': 1, 'verwijderd': 1}
        assert tellingen['afbeeldingen']['nieuw'] == 1

    def test_lijstbestanden_bevatten_nieuw_en_gewijzigd(self, tmp_path, monkeypatch):
        monkeypatch.setattr(config, 'AIRFLOW_TEMPDIR', str(tmp_path / 'tmp'))
        bestanden = bronbestanden.schrijfLijstbestanden(bronbestanden.maakDeltaLijsten(RECORDS))
        assert set(bestanden) == {'projecten', 'projectenlijst', 'magazijnlijst', 'fotolijst', 'monsterdatabase', 'rapporten'}
        with open(bestanden['projecten'], encoding='utf-8') as f:
            assert f.read().splitlines() == ['/input/projecten/SY002/b.mdb', '/input/projecten/SY003/a.mdb']
        assert bestanden['projecten'] == str(tmp_path / 'tmp' / 'delta_projecten.txt')

    def test_leeg_lijstbestand_als_er_niets_te_doen_is(self, tmp_path, monkeypatch):
        monkeypatch.setattr(config, 'AIRFLOW_TEMPDIR', str(tmp_path))
        bestanden = bronbestanden.schrijfLijstbestanden(bronbestanden.maakDeltaLijsten(RECORDS))
        assert os.path.getsize(bestanden['magazijnlijst']) == 0

    def test_oude_lijst_wordt_overschreven(self, tmp_path, monkeypatch):
        monkeypatch.setattr(config, 'AIRFLOW_TEMPDIR', str(tmp_path))
        schrijf(tmp_path / 'delta_projecten.txt', b'/input/projecten/OUD/x.mdb\n')
        bronbestanden.schrijfLijstbestanden(bronbestanden.maakDeltaLijsten([]))
        assert os.path.getsize(tmp_path / 'delta_projecten.txt') == 0

    def test_paden_met_spaties_op_eigen_regel(self, tmp_path, monkeypatch):
        monkeypatch.setattr(config, 'AIRFLOW_TEMPDIR', str(tmp_path))
        pad = '/input/projecten/SY001/C Database/opgravingSY001.mdb'
        bestanden = bronbestanden.schrijfLijstbestanden({'nieuw': {'projecten': [pad]}})
        with open(bestanden['projecten'], encoding='utf-8') as f:
            assert f.read() == pad + '\n'

    def test_te_grote_lijsten_laten_ongewijzigd_weg(self, monkeypatch):
        lijsten = bronbestanden.maakDeltaLijsten(RECORDS)
        assert bronbestanden.begrensLijsten(lijsten)[1] is False
        monkeypatch.setattr(bronbestanden, 'MAX_LIJSTEN_BYTES', 10)
        begrensd, weggelaten = bronbestanden.begrensLijsten(lijsten)
        assert weggelaten is True
        assert begrensd['ongewijzigd'] == {}
        assert begrensd['nieuw'] == lijsten['nieuw']


# ============================================================
# Klasse 6: registratierijen
# ============================================================

@pytest.mark.unit
class TestRegistratieRijen:
    """Test de omzetting van records naar rijen voor Def_Bronbestand."""

    def record(self, pad, categorie, status, bijgewerkt=False):
        return {'pad': pad, 'categorie': categorie, 'status': status, 'grootte': 10, 'mtime': 2.0,
                'sha256': 'b' * 64, 'vingerafdruk_bijgewerkt': bijgewerkt}

    def test_statussen(self, caplog):
        records = [
            self.record('/p/a.mdb', 'projecten', 'nieuw'),
            self.record('/p/b.mdb', 'projecten', 'gewijzigd'),
            self.record('/p/c.mdb', 'projecten', 'verwijderd'),
            self.record('/p/d.jpg', 'afbeeldingen', 'nieuw'),
            self.record('/p/e.mdb', 'projecten', 'ongewijzigd'),
            self.record('/p/f.mdb', 'projecten', 'ongewijzigd', bijgewerkt=True),
        ]
        with caplog.at_level('WARNING', logger='airflow.task'):
            rijen, bijwerken = bronbestanden.maakRegistratieRijen(records, {'/p/a.mdb': 12}, 'RUN1', 'T')
        per_pad = {r[0]: r for r in rijen}
        assert per_pad['/p/a.mdb'] == ('/p/a.mdb', 'projecten', 10, 2.0, 'b' * 64, 'verwerkt', 'T', 'RUN1', 12)
        # MDB zonder staging-documenten: verwerkt met 0 records en een waarschuwing per bestand
        assert per_pad['/p/b.mdb'] == ('/p/b.mdb', 'projecten', 10, 2.0, 'b' * 64, 'verwerkt', 'T', 'RUN1', 0)
        waarschuwingen = [rec.getMessage() for rec in caplog.records if rec.levelname == 'WARNING']
        assert len(waarschuwingen) == 1 and '/p/b.mdb' in waarschuwingen[0]
        assert per_pad['/p/c.mdb'][5] == 'verwijderd'
        assert per_pad['/p/c.mdb'][8] == 0
        # Afbeeldingen tellen als 0 records en zijn toch verwerkt
        assert per_pad['/p/d.jpg'][5] == 'verwerkt'
        assert '/p/e.mdb' not in per_pad
        assert bijwerken == [('/p/f.mdb', 10, 2.0, 'b' * 64)]
        assert bronbestanden.telRegistratie(rijen, bijwerken) == {'verwerkt': 3, 'mislukt': 0, 'verwijderd': 1, 'vingerafdruk_bijgewerkt': 1}

    def test_lege_mdb_wordt_niet_opnieuw_verwerkt(self, tmp_path):
        """Een Access-database zonder rijen geldt de volgende run als ongewijzigd."""
        pad = schrijf(tmp_path / 'leeg.mdb', b'leeg', mtime=1700000000)
        gescand = {pad: {'categorie': 'projecten', 'grootte': os.path.getsize(pad), 'mtime': os.path.getmtime(pad)}}
        records, _ = bronbestanden.bepaalStatussen(gescand, {})
        rijen, _ = bronbestanden.maakRegistratieRijen(records, {}, 'RUN1', 'T')
        assert rijen[0][5] == 'verwerkt' and rijen[0][8] == 0

        geregistreerd = {pad: {'categorie': 'projecten', 'grootte': rijen[0][2], 'mtime': rijen[0][3],
                               'sha256': rijen[0][4], 'status': rijen[0][5]}}
        records, hashes = bronbestanden.bepaalStatussen(gescand, geregistreerd)
        assert records[0]['status'] == 'ongewijzigd'
        assert hashes == 0

    def test_volledige_cyclus_registreert_ook_ongewijzigd(self):
        records = [self.record('/p/e.mdb', 'projecten', 'ongewijzigd')]
        rijen, bijwerken = bronbestanden.maakRegistratieRijen(records, {'/p/e.mdb': 3}, 'RUN1', 'T', alles_verwerkt=True)
        assert rijen[0][5] == 'verwerkt'
        assert rijen[0][8] == 3
        assert bijwerken == []

    def test_schrijf_registratie_upsert_in_een_transactie(self, monkeypatch):
        conn = MagicMock()
        monkeypatch.setattr(bronbestanden, 'getPgConnection', lambda: conn)
        execute_values = MagicMock()
        monkeypatch.setattr(bronbestanden.psycopg2.extras, 'execute_values', execute_values)

        bronbestanden.schrijfRegistratie([('/p/a.mdb', 'projecten', 1, 2.0, 'c' * 64, 'verwerkt', 'T', 'R', 4)],
                                         [('/p/b.mdb', 1, 3.0, 'd' * 64)])
        sqls = [c.args[1] for c in execute_values.call_args_list]
        assert 'ON CONFLICT (pad) DO UPDATE' in sqls[0]
        assert sqls[1].strip().startswith('UPDATE "Def_Bronbestand"')
        conn.commit.assert_called_once()
        conn.close.assert_called_once()
        create_sql = conn.cursor.return_value.execute.call_args_list[0].args[0]
        assert 'CREATE TABLE IF NOT EXISTS "Def_Bronbestand"' in create_sql
        assert 'pad TEXT PRIMARY KEY' in create_sql


# ============================================================
# Klasse 7: tellen in de staging
# ============================================================

@pytest.mark.unit
class TestStaging:
    """Test controleerStagingLeeg en telStagingRecords."""

    def test_lege_staging_is_goed(self, nep_client):
        staging(nep_client)[verwerkingsrun.COLL_VERWERKINGSRUNS].insert_one({'status': 'actief'})
        bronbestanden.controleerStagingLeeg(nep_client)

    def test_gevulde_staging_verwijst_naar_volledige_cyclus(self, nep_client):
        staging(nep_client)[config.COLL_STAGING_OUD].insert_one({'mdbfile': '/x.mdb'})
        with pytest.raises(Exception, match="volledige cyclus"):
            bronbestanden.controleerStagingLeeg(nep_client)

    def test_gevulde_single_store_verwijst_naar_volledige_cyclus(self, nep_client):
        nep_client[config.DB_ANALYSE][config.COLL_ANALYSE].insert_one({'soort': 'Project'})
        with pytest.raises(Exception, match="Extract_Transform_Load_Full_Cycle"):
            bronbestanden.controleerStagingLeeg(nep_client)

    def test_tel_staging_records_per_bestand(self, nep_client, monkeypatch):
        monkeypatch.setattr(config, 'FILE_ABREXCEL', '/input/abr.xlsx')
        db = staging(nep_client)
        db[config.COLL_STAGING_OUD].insert_many([{'mdbfile': '/p/a.mdb'}, {'mdbfile': '/p/a.mdb'}, {'mdbfile': '/p/b.mdb'}])
        db[config.COLL_STAGING_PROJECTENLIJST].insert_many([{'mdbfile': '/l/lijst.mdb'}, {'mdbfile': '/l/extra.xlsx'}])
        db[config.COLL_STAGING_REFERENTIETABELLEN].insert_many([{'uri': 'https://a'}, {'uri': 'https://b'}])
        assert bronbestanden.telStagingRecords(nep_client) == {
            '/p/a.mdb': 2, '/p/b.mdb': 1, '/l/lijst.mdb': 1, '/l/extra.xlsx': 1, '/input/abr.xlsx': 2}
        assert bronbestanden.telStagingRecords(nep_client, paden=['/p/a.mdb']) == {'/p/a.mdb': 2}


# ============================================================
# Klasse 8: taken
# ============================================================

@pytest.mark.unit
class TestTaken:
    """Test bepaalDelta, registreerBronbestanden en registreerVolledigeCyclus."""

    def test_bepaal_delta_schrijft_run_document_en_lijstbestanden(self, invoer, nep_client, registratie):
        oud = schrijf(os.path.join(invoer.AIRFLOW_INPUT_PROJECTEN, 'SY001', 'a.mdb'), b'oud', mtime=1700000000)
        nieuw = schrijf(os.path.join(invoer.AIRFLOW_INPUT_PROJECTEN, 'SY003', 'c.mdb'), b'nieuw')
        foto = schrijf(os.path.join(invoer.AIRFLOW_INPUT_PROJECTEN, 'SY003', 'L Fotos', 'f.jpg'), b'jpg')
        invoer.afbeeldingen.append(foto)
        weg = os.path.join(invoer.AIRFLOW_INPUT_PROJECTEN, 'SY002', 'b.mdb')
        registratie.rijen = {
            oud: {'categorie': 'projecten', 'grootte': 3, 'mtime': 1700000000.0, 'sha256': sha(b'oud'), 'status': 'verwerkt'},
            weg: {'categorie': 'projecten', 'grootte': 3, 'mtime': 1.0, 'sha256': 'e' * 64, 'status': 'verwerkt'},
        }
        verwerkingsrun.startRun('incrementeel')

        tellingen = bronbestanden.bepaalDelta()

        run = verwerkingsrun.huidigeRun()
        assert run['nieuw'] == {'projecten': [nieuw], 'afbeeldingen': [foto]}
        assert run['ongewijzigd'] == {'projecten': [oud]}
        assert run['verwijderd'] == {'projecten': [weg]}
        assert run['gewijzigd'] == {}
        assert run['registratie_leeg'] is False
        assert run['tellingen']['delta']['totaal'] == {'nieuw': 2, 'gewijzigd': 0, 'ongewijzigd': 1, 'verwijderd': 1}
        assert run['tellingen']['hash_berekend'] == 2
        assert tellingen == run['tellingen']['delta']
        with open(bronbestanden.getLijstbestandPad('projecten'), encoding='utf-8') as f:
            assert f.read() == nieuw + '\n'
        # De vingerafdrukken staan per bestand in Verwerkingsrun_Bestanden
        records = staging(nep_client)[verwerkingsrun.COLL_RUN_BESTANDEN].find({'run_id': run['run_id']})
        assert {r['pad']: r['status'] for r in records} == {oud: 'ongewijzigd', nieuw: 'nieuw', foto: 'nieuw', weg: 'verwijderd'}

    def test_lege_registratie_met_lege_staging_alles_nieuw(self, invoer, nep_client, registratie):
        mdb = schrijf(os.path.join(invoer.AIRFLOW_INPUT_MONSTER, 'MONSTERS.mdb'))
        verwerkingsrun.startRun('incrementeel')
        bronbestanden.bepaalDelta()
        run = verwerkingsrun.huidigeRun()
        assert run['registratie_leeg'] is True
        assert run['nieuw'] == {'monsterdatabase': [mdb]}

    def test_lege_registratie_met_gevulde_staging_faalt(self, invoer, nep_client, registratie):
        schrijf(os.path.join(invoer.AIRFLOW_INPUT_MONSTER, 'MONSTERS.mdb'))
        staging(nep_client)[config.COLL_STAGING_MONSTER].insert_one({'mdbfile': 'x'})
        verwerkingsrun.startRun('incrementeel')
        with pytest.raises(Exception, match="Draai eerst de volledige"):
            bronbestanden.bepaalDelta()

    def test_registreer_bronbestanden_rondt_run_af(self, invoer, nep_client, registratie):
        nieuw = schrijf(os.path.join(invoer.AIRFLOW_INPUT_PROJECTEN, 'SY003', 'c.mdb'), b'nieuw')
        weg = os.path.join(invoer.AIRFLOW_INPUT_PROJECTEN, 'SY002', 'b.mdb')
        registratie.rijen = {weg: {'categorie': 'projecten', 'grootte': 3, 'mtime': 1.0, 'sha256': 'e' * 64, 'status': 'verwerkt'}}
        run_id = verwerkingsrun.startRun('incrementeel')
        bronbestanden.bepaalDelta()
        staging(nep_client)[config.COLL_STAGING_OUD].insert_many([{'mdbfile': nieuw}, {'mdbfile': nieuw}, {'mdbfile': nieuw}])

        tellingen = bronbestanden.registreerBronbestanden()

        per_pad = {r[0]: r for r in registratie.geschreven}
        assert per_pad[nieuw][5:] == ('verwerkt', per_pad[nieuw][6], run_id, 3)
        assert per_pad[nieuw][4] == sha(b'nieuw')
        assert per_pad[weg][5] == 'verwijderd'
        assert tellingen == {'verwerkt': 1, 'mislukt': 0, 'verwijderd': 1, 'vingerafdruk_bijgewerkt': 0}
        doc = staging(nep_client)[verwerkingsrun.COLL_VERWERKINGSRUNS].find_one({'_id': run_id})
        assert doc['status'] == 'afgerond'
        assert doc['tellingen']['registratie'] == tellingen

    def test_registreer_volledige_cyclus(self, invoer, nep_client, registratie):
        mdb = schrijf(os.path.join(invoer.AIRFLOW_INPUT_PROJECTEN, 'SY001', 'a.mdb'), b'a')
        foto = schrijf(os.path.join(invoer.AIRFLOW_INPUT_PROJECTEN, 'SY001', 'L Fotos', 'f.jpg'), b'jpg')
        invoer.afbeeldingen.append(foto)
        staging(nep_client)[config.COLL_STAGING_OUD].insert_one({'mdbfile': mdb})

        tellingen = bronbestanden.registreerVolledigeCyclus()

        assert {r[0]: r[5] for r in registratie.geschreven} == {mdb: 'verwerkt', foto: 'verwerkt'}
        assert tellingen['verwerkt'] == 2
        run = staging(nep_client)[verwerkingsrun.COLL_VERWERKINGSRUNS].find_one({})
        assert run['soort'] == 'volledig'
        assert run['status'] == 'afgerond'
        assert run['registratie_leeg'] is True

    def test_registreer_volledige_cyclus_zet_run_op_mislukt_bij_fout(self, invoer, nep_client, monkeypatch):
        def kapot():
            raise RuntimeError("PostgreSQL niet bereikbaar")
        monkeypatch.setattr(bronbestanden, 'leesRegistratie', kapot)
        with pytest.raises(Exception, match="PostgreSQL niet bereikbaar"):
            bronbestanden.registreerVolledigeCyclus()
        run = staging(nep_client)[verwerkingsrun.COLL_VERWERKINGSRUNS].find_one({})
        assert run['status'] == 'mislukt'
