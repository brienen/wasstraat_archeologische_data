"""
Unit tests voor wasstraat/verwerkingsrun.py (incrementeel laden, issue 61).

Test het beheer van het run-document in de collectie Verwerkingsruns:
starten (één actieve run), bijwerken, beëindigen, markeren als mislukt,
overname van sleutels uit mislukte runs en het opvragen van de delta.
MongoDB wordt nagebootst met tests/unit/nep_mongo.py.
"""
import pytest
from datetime import datetime

import wasstraat.verwerkingsrun as verwerkingsrun
from tests.unit.nep_mongo import NepClient


@pytest.fixture
def nep_client(monkeypatch):
    """Vervang de MongoClient van verwerkingsrun door een in-memory nabootsing."""
    client = NepClient()
    monkeypatch.setattr(verwerkingsrun, '_getClient', lambda: client)
    return client


def runCollectie(client):
    return client[verwerkingsrun.config.DB_STAGING][verwerkingsrun.COLL_VERWERKINGSRUNS]


# ============================================================
# Klasse 1: run-id en run-document
# ============================================================

@pytest.mark.unit
class TestRunDocument:
    """Test het opbouwen van run-id en run-document."""

    def test_run_id_is_tijdstempel(self):
        assert verwerkingsrun.maakRunId(datetime(2026, 10, 21, 14, 30, 5)) == '20261021T143005'

    def test_run_document_bevat_ontwerpvelden(self):
        doc = verwerkingsrun.maakRunDocument('20261021T143005', 'incrementeel', airflow_run_id='manual__x')
        assert doc['_id'] == doc['run_id'] == '20261021T143005'
        assert doc['status'] == 'actief'
        assert doc['soort'] == 'incrementeel'
        assert doc['airflow_run_id'] == 'manual__x'
        for veld in ['nieuw', 'gewijzigd', 'ongewijzigd', 'verwijderd', 'verwijderde_keys']:
            assert doc[veld] == {}
        assert doc['geraakte_projecten'] == []
        assert doc['tellingen'] == {}
        assert isinstance(doc['gestart_op'], datetime)

    def test_verwijderde_keys_samenvoegen_zonder_dubbelingen(self):
        a = {'Vondst': [{'key': 'K1', 'projectcd': 'SY001'}]}
        b = {'Vondst': [{'key': 'K1', 'projectcd': 'SY001'}, {'key': 'K2', 'projectcd': 'SY001'}],
             'Artefact': [{'key': 'A1', 'projectcd': 'SY001', 'key_subnr': 'A1S1', 'artefactsoort': 'Glas'}]}
        resultaat = verwerkingsrun.voegVerwijderdeKeysSamen(a, b)
        assert [e['key'] for e in resultaat['Vondst']] == ['K1', 'K2']
        assert resultaat['Artefact'][0]['artefactsoort'] == 'Glas'

    def test_artefacten_met_zelfde_key_andere_soort_blijven_apart(self):
        a = {'Artefact': [{'key': 'A1', 'projectcd': 'P', 'key_subnr': 'S1', 'artefactsoort': 'Glas'}]}
        b = {'Artefact': [{'key': 'A1', 'projectcd': 'P', 'key_subnr': 'S1', 'artefactsoort': 'Metaal'}]}
        assert len(verwerkingsrun.voegVerwijderdeKeysSamen(a, b)['Artefact']) == 2


# ============================================================
# Klasse 2: starten en beëindigen
# ============================================================

@pytest.mark.unit
class TestStartEnBeeindig:
    """Test startRun, huidigeRun, werkRunBij en beeindigRun."""

    def test_start_maakt_actieve_run(self, nep_client):
        run_id = verwerkingsrun.startRun('incrementeel', airflow_run_id='manual__1')
        run = verwerkingsrun.huidigeRun()
        assert run['run_id'] == run_id
        assert run['status'] == 'actief'
        assert run['airflow_run_id'] == 'manual__1'

    def test_onbekende_soort_faalt(self, nep_client):
        with pytest.raises(Exception, match="Onbekende soort"):
            verwerkingsrun.startRun('half')

    def test_tweede_actieve_run_faalt_met_duidelijke_melding(self, nep_client):
        verwerkingsrun.startRun('incrementeel')
        with pytest.raises(Exception, match="al een actieve verwerkingsrun"):
            verwerkingsrun.startRun('incrementeel')

    def test_na_beeindigen_kan_nieuwe_run_starten(self, nep_client, monkeypatch):
        monkeypatch.setattr(verwerkingsrun, 'maakRunId', lambda tijdstip=None: '20260101T000000')
        eerste = verwerkingsrun.startRun('incrementeel')
        verwerkingsrun.beeindigRun('afgerond')
        tweede = verwerkingsrun.startRun('volledig')
        # Zelfde seconde: de tweede run krijgt een volgnummer
        assert eerste == '20260101T000000'
        assert tweede == '20260101T000000_2'
        assert verwerkingsrun.huidigeRun()['soort'] == 'volledig'

    def test_huidige_run_zonder_actieve_run(self, nep_client):
        assert verwerkingsrun.huidigeRun(verplicht=False) is None
        with pytest.raises(Exception, match="Geen actieve verwerkingsrun"):
            verwerkingsrun.huidigeRun()

    def test_werk_run_bij_met_punt_notatie(self, nep_client):
        verwerkingsrun.startRun('incrementeel')
        verwerkingsrun.werkRunBij({'tellingen.delta': {'totaal': {'nieuw': 3}}, 'registratie_leeg': False})
        run = verwerkingsrun.huidigeRun()
        assert run['tellingen']['delta']['totaal']['nieuw'] == 3
        assert run['registratie_leeg'] is False

    def test_beeindig_zet_status_en_tijdstip(self, nep_client):
        run_id = verwerkingsrun.startRun('incrementeel')
        verwerkingsrun.beeindigRun('afgerond')
        doc = runCollectie(nep_client).find_one({'_id': run_id})
        assert doc['status'] == 'afgerond'
        assert isinstance(doc['beeindigd_op'], datetime)
        assert verwerkingsrun.huidigeRun(verplicht=False) is None

    def test_beeindig_met_ongeldige_status_faalt(self, nep_client):
        verwerkingsrun.startRun('incrementeel')
        with pytest.raises(Exception, match="Ongeldige eindstatus"):
            verwerkingsrun.beeindigRun('actief')


# ============================================================
# Klasse 2b: Start_Run laadt het gemeenteprofiel (issue 87)
# ============================================================

@pytest.fixture
def profiel(monkeypatch):
    """Kies WASSTRAAT_GEMEENTE voor de test; de cache van het profiel is voor en na de test leeg."""
    import shared.config as config
    from wasstraat.profielen import reset_profiel

    def kies(gemeente):
        reset_profiel()
        monkeypatch.setattr(config, 'WASSTRAAT_GEMEENTE', gemeente, raising=False)

    reset_profiel()
    yield kies
    reset_profiel()


@pytest.mark.unit
class TestStartRunMetProfiel:
    """Start_Run (startRunEnLaadProfiel) stopt de run direct bij een onbekend gemeenteprofiel."""

    def test_bekend_profiel_start_de_run(self, nep_client, profiel):
        profiel('voorbeeld')
        run_id = verwerkingsrun.startRunEnLaadProfiel('volledig', airflow_run_id='manual__1', dag_id='DAG_X')
        run = verwerkingsrun.huidigeRun()
        assert run['run_id'] == run_id and run['status'] == 'actief' and run['meldingen'] == []

    @pytest.mark.parametrize('soort', ['volledig', 'incrementeel', 'laden'])
    def test_onbekend_profiel_is_cruciale_fout(self, nep_client, profiel, soort):
        import wasstraat.foutbeleid as foutbeleid
        profiel('rotterdam')
        with pytest.raises(foutbeleid.CrucialeFout, match=r"Onbekend gemeenteprofiel: 'rotterdam'.*delft, voorbeeld"):
            verwerkingsrun.startRunEnLaadProfiel(soort, airflow_run_id='manual__1')
        doc = runCollectie(nep_client).find_one({'airflow_run_id': 'manual__1'})
        assert doc['status'] == 'mislukt' and 'WASSTRAAT_GEMEENTE' in doc['melding']
        assert isinstance(doc['beeindigd_op'], datetime)
        assert [(m['niveau'], m['soort'], m['taak'], m['stap']) for m in doc['meldingen']] == [
            ('fout', foutbeleid.SOORT_PROFIEL_ONBEKEND, 'Start_Run', 'voorbereiding')]
        # De run blokkeert de volgende niet
        assert verwerkingsrun.huidigeRun(verplicht=False) is None

    def test_actieve_run_faalt_zonder_profiel_te_laden(self, nep_client, profiel, monkeypatch):
        import wasstraat.profielen as profielen
        verwerkingsrun.startRun('incrementeel', airflow_run_id='manual__A')
        geladen = []
        monkeypatch.setattr(profielen, 'get_profiel', lambda: geladen.append(1))
        with pytest.raises(Exception, match="al een actieve verwerkingsrun"):
            verwerkingsrun.startRunEnLaadProfiel('incrementeel', airflow_run_id='manual__B')
        assert geladen == []
        assert verwerkingsrun.huidigeRun()['airflow_run_id'] == 'manual__A'


# ============================================================
# Klasse 3: mislukte runs
# ============================================================

@pytest.mark.unit
class TestMislukteRuns:
    """Test markeerRunMislukt en de overname van sleutels uit mislukte runs."""

    def test_markeer_alleen_eigen_airflow_run(self, nep_client):
        verwerkingsrun.startRun('incrementeel', airflow_run_id='manual__A')
        verwerkingsrun.markeerRunMislukt(airflow_run_id='manual__B')
        assert verwerkingsrun.huidigeRun()['status'] == 'actief'
        verwerkingsrun.markeerRunMislukt(airflow_run_id='manual__A')
        assert verwerkingsrun.huidigeRun(verplicht=False) is None
        assert runCollectie(nep_client).find_one({})['status'] == 'mislukt'

    def test_markeer_zonder_actieve_run_doet_niets(self, nep_client):
        verwerkingsrun.markeerRunMislukt(airflow_run_id='manual__A')

    def test_sleutels_van_mislukte_run_worden_overgenomen(self, nep_client):
        verwerkingsrun.startRun('incrementeel')
        verwerkingsrun.werkRunBij({'verwijderde_keys': {'Vondst': [{'key': 'K1', 'projectcd': 'SY003'}]},
                                   'geraakte_projecten': ['SY003']})
        mislukt_id = verwerkingsrun.huidigeRun()['run_id']
        verwerkingsrun.beeindigRun('mislukt')

        verwerkingsrun.startRun('incrementeel')
        run = verwerkingsrun.huidigeRun()
        assert run['verwijderde_keys'] == {'Vondst': [{'key': 'K1', 'projectcd': 'SY003'}]}
        assert run['geraakte_projecten'] == ['SY003']
        assert run['overgenomen_van'] == [mislukt_id]

    def test_geen_overname_van_voor_laatste_geslaagde_run(self, nep_client):
        verwerkingsrun.startRun('incrementeel')
        verwerkingsrun.werkRunBij({'verwijderde_keys': {'Vondst': [{'key': 'K1', 'projectcd': 'SY003'}]}})
        verwerkingsrun.beeindigRun('mislukt')
        verwerkingsrun.startRun('incrementeel')
        verwerkingsrun.beeindigRun('afgerond')

        verwerkingsrun.startRun('incrementeel')
        run = verwerkingsrun.huidigeRun()
        assert run['verwijderde_keys'] == {}
        assert run['overgenomen_van'] == []


# ============================================================
# Klasse 4: delta opvragen
# ============================================================

@pytest.mark.unit
class TestDeltaPaden:
    """Test getDeltaPaden en isInDelta op een run-document."""

    RUN = {
        'nieuw': {'afbeeldingen': ['/input/b.jpg'], 'referentietabellen': ['/input/abr.xlsx']},
        'gewijzigd': {'afbeeldingen': ['/input/a.jpg']},
        'ongewijzigd': {'afbeeldingen': ['/input/c.jpg']},
        'verwijderd': {'afbeeldingen': ['/input/d.jpg']},
    }

    def test_standaard_nieuw_en_gewijzigd(self):
        assert verwerkingsrun.getDeltaPaden('afbeeldingen', run=self.RUN) == ['/input/a.jpg', '/input/b.jpg']

    def test_andere_statussen(self):
        assert verwerkingsrun.getDeltaPaden('afbeeldingen', statussen=['verwijderd'], run=self.RUN) == ['/input/d.jpg']

    def test_onbekende_categorie_is_leeg(self):
        assert verwerkingsrun.getDeltaPaden('projecten', run=self.RUN) == []

    def test_is_in_delta(self):
        assert verwerkingsrun.isInDelta('/input/abr.xlsx', 'referentietabellen', run=self.RUN)
        assert not verwerkingsrun.isInDelta('/input/c.jpg', 'afbeeldingen', run=self.RUN)
