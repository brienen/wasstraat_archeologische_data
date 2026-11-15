"""
Unit tests voor de controles na de extractie (issue 54, wasstraat/controle_extractie.py).

- leesImportLog: het log van importMDB.sh lezen (verwerkte, onleesbare en lege
  databases, overgeslagen tabellen, overige meldingen, een log van een eerdere run);
- controleerDatabases: tellingen in het run-document, waarschuwingen en de drempel
  op onleesbare databases (nagebootste fout: een database die mdb-tables niet kan lezen);
- controleerAfbeeldingen: de controle van issue 70 met tellingen en een melding,
  ook in het run-document van de volledige cyclus en ook als de controle faalt.

MongoDB wordt nagebootst met tests/unit/nep_mongo.py; de logs staan in een tijdelijke map.
"""
import os
import sys
import time
import types
from datetime import timedelta

import pytest

# Mock shared.image_util (wordt geïmporteerd door image_import.py, vereist PIL/pdf2image/magic)
if "shared.image_util" not in sys.modules:
    sys.modules["shared.image_util"] = types.ModuleType("shared.image_util")

import wasstraat.controle_extractie as controle
import wasstraat.foutbeleid as foutbeleid
import wasstraat.image_import as image_import
import wasstraat.verwerkingsrun as verwerkingsrun
from tests.unit.nep_mongo import NepClient

PROJECTEN = '/input/projecten'
SY001 = f'{PROJECTEN}/SY001/C Database/opgravingSY001.mdb'
SY002 = f'{PROJECTEN}/SY002/C Database/opgravingSY002.mdb'
KAPOT = f'{PROJECTEN}/SY003/C Database/kapot.mdb'
LEEG = f'{PROJECTEN}/SY004/C Database/leeg.mdb'

LOG_PROJECTEN = f"""Loading from {PROJECTEN} to collection Staging_Projecten_Oud in database Arch_Staging and logging to x
INFO: 4 MDB/ACCDB-bestand(en) gevonden in '{PROJECTEN}'.
Processing {SY001} file for project SY001 ...
Reading OPGRAVINGEN into /opt/airflow/tmp/opgravingSY001.OPGRAVINGEN.csv and loading into Mongo database
WARNING: mdb-prop gaf geen bruikbare output voor tabel 'OPGRAVINGEN', minimale metainfo gegenereerd
Processing {KAPOT} file for project SY003 ...
ERROR: Kan MDB-bestand niet lezen (mogelijk corrupt of encoding-probleem): {KAPOT}
Processing {SY002} file for project SY002 ...
WARNING: Geen kopregel gelezen voor tabel 'VREEMD' in bestand '{SY002}', tabel overgeslagen
ERROR: Kolommen toevoegen gefaald voor tabel 'MEMO' in bestand '{SY002}', tabel overgeslagen
ERROR: mongoimport gefaald (exit 1) voor tabel 'MUNTEN' in bestand '{SY002}'
ERROR ENCODING: Alle conversie-pogingen gefaald voor tabel 'GLAS' in bestand '{SY002}'
WARNING: CSV encoding-conversie gefaald voor tabel 'GLAS' in bestand '{SY002}', probeer toch te importeren
Processing {LEEG} file for project SY004 ...
WARNING: Bestand '/input/projecten/SY005/weg.mdb' uit lijstbestand bestaat niet, overgeslagen.
========================================================
Totaal MDB-bestanden verwerkt:       4
"""


@pytest.fixture
def nep_client(monkeypatch):
    client = NepClient()
    monkeypatch.setattr(verwerkingsrun, '_getClient', lambda: client)
    monkeypatch.setattr(controle.pymongo, 'MongoClient', lambda *args, **kwargs: client)
    return client


@pytest.fixture
def logmap(tmp_path, monkeypatch):
    monkeypatch.setattr(controle.config, 'AIRFLOW_LOGDIR', str(tmp_path))
    return tmp_path


@pytest.fixture
def staging(monkeypatch):
    """Aantal staging-documenten per database: SY001 en SY002 hebben records, LEEG niet."""
    aantallen = {SY001: 120, SY002: 80}
    gevraagd = []

    def tel(client, paden=None):
        gevraagd.append(sorted(paden))
        return {p: aantallen[p] for p in paden if p in aantallen}
    monkeypatch.setattr(controle.bronbestanden, 'telStagingRecords', tel)
    return gevraagd


def schrijfLog(logmap, collectie, tekst, leeftijd=None):
    pad = logmap / f'{collectie}.log'
    pad.write_text(tekst, encoding='utf-8')
    if leeftijd is not None:
        oud = time.time() - leeftijd
        os.utime(pad, (oud, oud))
    return str(pad)


def runDoc(client):
    return client[verwerkingsrun.config.DB_STAGING][verwerkingsrun.COLL_VERWERKINGSRUNS].find_one({})


# ============================================================
# Klasse 1: het log van importMDB.sh
# ============================================================

@pytest.mark.unit
class TestLeesImportLog:

    def test_onderdelen_van_het_log(self, logmap):
        log = controle.leesImportLog(schrijfLog(logmap, 'Staging_Projecten_Oud', LOG_PROJECTEN))
        assert log['aanwezig'] is True
        assert log['verwerkt'] == sorted([SY001, SY002, KAPOT, LEEG])
        assert [o['bestand'] for o in log['onleesbaar']] == [KAPOT]
        assert [(t['tabel'], t['reden']) for t in log['tabellen_overgeslagen']] == [
            ('VREEMD', 'geen kopregel gelezen'), ('MEMO', 'kolommen toevoegen mislukt'),
            ('MUNTEN', 'mongoimport mislukt (exit 1)')]
        assert all(t['bestand'] == SY002 for t in log['tabellen_overgeslagen'])
        assert log['lijst_ontbreekt'] == ['/input/projecten/SY005/weg.mdb']
        # Alleen de encoding-waarschuwing is 'overig'; mdb-prop en ERROR ENCODING worden genegeerd
        assert log['overig'] == [f"WARNING: CSV encoding-conversie gefaald voor tabel 'GLAS' in bestand '{SY002}', "
                                 f"probeer toch te importeren"]

    def test_ontbrekend_log(self, logmap):
        assert controle.leesImportLog(str(logmap / 'bestaat_niet.log')) == controle.leegLogResultaat()

    def test_log_van_eerdere_run_telt_niet(self, logmap):
        pad = schrijfLog(logmap, 'Staging_Projecten_Oud', LOG_PROJECTEN, leeftijd=3600)
        log = controle.leesImportLog(pad, sinds=verwerkingsrun.nu() - timedelta(minutes=5))
        assert log['aanwezig'] is False and log['verwerkt'] == []

    def test_log_zonder_meldingen(self, logmap):
        log = controle.leesImportLog(schrijfLog(logmap, 'x', f"Processing {SY001} file for project SY001 ...\n"))
        assert log['verwerkt'] == [SY001] and not log['onleesbaar'] and not log['overig']


# ============================================================
# Klasse 2: Controleer_Databases
# ============================================================

@pytest.mark.unit
class TestControleerDatabases:

    def test_onleesbare_database_onder_drempel_is_waarschuwing(self, nep_client, logmap, staging):
        verwerkingsrun.startRun('incrementeel', airflow_run_id='manual__1')
        schrijfLog(logmap, 'Staging_Projecten_Oud', LOG_PROJECTEN)
        tellingen = controle.controleerDatabases(incrementeel=True)

        assert (tellingen['databases'], tellingen['onleesbaar'], tellingen['leeg'], tellingen['tabellen_overgeslagen']) \
            == (4, 1, 1, 3)
        assert tellingen['drempel'] == 2 and tellingen['boven_drempel'] is False
        assert staging == [sorted([SY001, SY002, LEEG])]  # de onleesbare database wordt niet geteld
        assert tellingen['lege_databases'] == [{'bestand': LEEG, 'categorie': 'projecten'}]
        assert tellingen['per_categorie']['projecten'] == {'log_gelezen': True, 'verwerkt': 4, 'onleesbaar': 1,
                                                           'tabellen_overgeslagen': 3, 'leeg': 1}
        assert tellingen['per_categorie']['magazijnlijst']['log_gelezen'] is False

        run = runDoc(nep_client)
        assert run['tellingen']['extractie']['onleesbaar'] == 1
        assert {'bestand': SY001, 'records': 120} in run['tellingen']['extractie']['records']
        soorten = {m['soort']: m for m in run['meldingen']}
        assert set(soorten) == {'database_leeg', 'tabel_overgeslagen', 'import_melding', 'database_onleesbaar'}
        assert all(m['niveau'] == 'waarschuwing' for m in run['meldingen'])
        assert soorten['database_onleesbaar']['details'][0]['bestand'] == KAPOT

    def test_onleesbare_database_boven_drempel_stopt_de_run(self, nep_client, logmap, staging, monkeypatch):
        monkeypatch.setattr(controle.config, 'AIRFLOW_MAX_MISLUKTE_DATABASES', 0)
        monkeypatch.setattr(controle.config, 'AIRFLOW_MAX_MISLUKTE_DATABASES_PCT', 0)
        verwerkingsrun.startRun('volledig', airflow_run_id='manual__1')
        schrijfLog(logmap, 'Staging_Projecten_Oud', LOG_PROJECTEN)
        with pytest.raises(foutbeleid.CrucialeFout, match=r'Onleesbare Access-databases .*: 1 van 4, meer dan de drempel van 0'):
            controle.controleerDatabases()
        run = runDoc(nep_client)
        # Tellingen staan er ook als de drempel wordt overschreden
        assert run['tellingen']['extractie']['boven_drempel'] is True
        assert [m['niveau'] for m in run['meldingen'] if m['soort'] == 'database_onleesbaar'] == ['fout']

    def test_alles_in_orde_geen_meldingen(self, nep_client, logmap, staging):
        verwerkingsrun.startRun('volledig')
        schrijfLog(logmap, 'Staging_Projecten_Oud', f"Processing {SY001} file for project SY001 ...\n")
        tellingen = controle.controleerDatabases()
        assert tellingen['databases'] == 1 and tellingen['onleesbaar'] == 0
        assert runDoc(nep_client)['meldingen'] == []

    def test_zonder_run_alleen_tellen(self, nep_client, logmap, staging):
        """Extract_only heeft geen run-document: de controle telt en toetst, zonder meldingen."""
        schrijfLog(logmap, 'Staging_Projecten_Oud', LOG_PROJECTEN)
        tellingen = controle.controleerDatabases()
        assert tellingen['onleesbaar'] == 1 and runDoc(nep_client) is None


# ============================================================
# Klasse 3: Controleer_Afbeeldingen
# ============================================================

def vulFilenames(client, mislukt=0, verwerkt=3):
    col = client[controle.config.DB_FILES][controle.config.COLL_FILENAMES]
    for i in range(verwerkt):
        col.insert_one({'filename': f'/input/f{i}.jpg', 'processed': True})
    for i in range(mislukt):
        col.insert_one({'filename': f'/input/kapot{i}.jpg', 'processed': False, 'fout': 'kan niet decoderen'})


@pytest.mark.unit
class TestControleerAfbeeldingen:

    @pytest.fixture(autouse=True)
    def standaardDrempel(self, monkeypatch):
        monkeypatch.setattr(image_import.config, 'AIRFLOW_MAX_MISLUKTE_AFBEELDINGEN', 10)
        monkeypatch.setattr(image_import.config, 'AIRFLOW_MAX_MISLUKTE_AFBEELDINGEN_PCT', 1.0)
        monkeypatch.setattr(image_import.pymongo, 'MongoClient', lambda *args, **kwargs: None)

    def test_volledige_cyclus_tellingen_en_waarschuwing(self, nep_client, monkeypatch):
        monkeypatch.setattr(image_import, 'controleerAfbeeldingen', lambda incrementeel=False: None)
        vulFilenames(nep_client, mislukt=1)
        verwerkingsrun.startRun('volledig')
        controle.controleerAfbeeldingen()
        run = runDoc(nep_client)
        assert run['tellingen']['afbeeldingen']['mislukt'] == 1 and run['tellingen']['afbeeldingen']['drempel'] == 10
        melding = run['meldingen'][0]
        assert melding['soort'] == 'afbeeldingen_mislukt' and melding['niveau'] == 'waarschuwing'
        assert melding['details'][0]['filename'] == '/input/kapot0.jpg'

    def test_mislukte_controle_geeft_fout_en_wordt_doorgegeven(self, nep_client, monkeypatch):
        def faal(incrementeel=False):
            raise image_import.OnherstelbareFout('boven de drempel')
        monkeypatch.setattr(image_import, 'controleerAfbeeldingen', faal)
        vulFilenames(nep_client, mislukt=2)
        verwerkingsrun.startRun('volledig')
        with pytest.raises(image_import.OnherstelbareFout, match='boven de drempel'):
            controle.controleerAfbeeldingen()
        run = runDoc(nep_client)
        assert run['tellingen']['afbeeldingen']['mislukt'] == 2
        assert run['meldingen'][0]['niveau'] == 'fout'

    def test_incrementeel_leest_tellingen_uit_run_document(self, nep_client, monkeypatch):
        def controle_incr(incrementeel=False):
            verwerkingsrun.werkRunBij({'tellingen.afbeeldingen': {'totaal': 2, 'mislukt': 0, 'onverwerkt': 0}})
        monkeypatch.setattr(image_import, 'controleerAfbeeldingen', controle_incr)
        verwerkingsrun.startRun('incrementeel')
        controle.controleerAfbeeldingen(incrementeel=True)
        run = runDoc(nep_client)
        assert run['tellingen']['afbeeldingen']['totaal'] == 2 and run['meldingen'] == []

    def test_zonder_run_alleen_de_controle(self, nep_client, monkeypatch):
        aangeroepen = []
        monkeypatch.setattr(image_import, 'controleerAfbeeldingen', lambda incrementeel=False: aangeroepen.append(1))
        controle.controleerAfbeeldingen()
        assert aangeroepen == [1] and runDoc(nep_client) is None
