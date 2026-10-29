"""
Unit tests voor het foutbeleid (issue 54).

Test per beleidskeuze, met nagebootste fouten:

- het beleid per taak (cruciaal, waarschuwing, afsluiting) en de stap van een taak;
- de drempel (bepaalDrempel, toetsDrempel) en de meldingen in het run-document;
- de on_failure_callback (registreerTaakfout);
- de controle van een DAG op trigger rules en bewaking (controleerBewaking), met
  nagebootste taken;
- het run-document voor alle cycli: aansluiten bij de lopende volledige cyclus,
  soort laden, de grens van de overname uit mislukte runs, zoeken op Airflow-run,
  markeren als mislukt met de mislukte taken, afronden;
- Drop_All_Databases laat Verwerkingsruns staan en faalt bij een fout;
- Transform 2: drempel op verwerkingsfouten; Transform 3: fout per project is een
  waarschuwing, een fout daarbuiten laat de taak falen;
- de laadstap: hernummerde sleutels, niet gevalideerde FK's en de tellingen in het
  run-document (loadAll).

MongoDB wordt nagebootst met tests/unit/nep_mongo.py, PostgreSQL met de nabootsing
uit test_load_incrementeel.py en test_load_volledig.py.
"""
import types
from datetime import datetime, timedelta

import pytest

import wasstraat.foutbeleid as foutbeleid
import wasstraat.verwerkingsrun as verwerkingsrun
from tests.unit.nep_mongo import NepClient
from tests.unit.test_load_incrementeel import omgeving  # noqa: F401 (fixture: MongoDB en PostgreSQL voor de laadstap)


@pytest.fixture
def nep_client(monkeypatch):
    """Vervang de MongoClient van verwerkingsrun door een in-memory nabootsing."""
    client = NepClient()
    monkeypatch.setattr(verwerkingsrun, '_getClient', lambda: client)
    return client


def runCollectie(client):
    return client[verwerkingsrun.config.DB_STAGING][verwerkingsrun.COLL_VERWERKINGSRUNS]


class NepTaak:
    """Taak met de attributen die controleerBewaking gebruikt."""

    def __init__(self, task_id, trigger_rule='all_success'):
        self.task_id = task_id
        self.trigger_rule = trigger_rule
        self.upstream_task_ids = set()
        self.downstream_task_ids = set()

    def __rshift__(self, andere):
        for a in (andere if isinstance(andere, list) else [andere]):
            self.downstream_task_ids.add(a.task_id)
            a.upstream_task_ids.add(self.task_id)
        return andere


class NepDag:
    def __init__(self, taken):
        self.tasks = taken


def maakDag(index_naar_eind=False, onbewaakt=False, rapport_mist=None):
    """Een kleine DAG volgens het beleid: Start_Run → Load → Index_X → Index_Klaar → Registreer → Eind."""
    t = {naam: NepTaak(naam) for naam in ['Start_Run', 'Load_Upsert', 'Index_Def_Project', 'Registreer_Run', 'End']}
    t['Index_Klaar'] = NepTaak('Index_Klaar', 'all_done')
    t['Markeer_Run_Mislukt'] = NepTaak('Markeer_Run_Mislukt', 'one_failed')
    t['Verwerkingsrapport'] = NepTaak('Verwerkingsrapport', 'all_done')
    t['Start_Run'] >> t['Load_Upsert'] >> t['Index_Def_Project'] >> t['Index_Klaar']
    t['Load_Upsert'] >> t['Registreer_Run']
    t['Index_Klaar'] >> t['Registreer_Run']
    t['Registreer_Run'] >> t['End']
    if index_naar_eind:
        t['Index_Def_Project'] >> t['End']
    bewaakt = ['Start_Run', 'Load_Upsert'] + ([] if onbewaakt else ['Registreer_Run'])
    for naam in bewaakt:
        t[naam] >> t['Markeer_Run_Mislukt']
    for naam, taak in t.items():
        if naam not in ('Verwerkingsrapport', 'End', rapport_mist):
            taak >> t['Verwerkingsrapport']
    t['Verwerkingsrapport'] >> t['End']
    return NepDag(list(t.values()))


# ============================================================
# Klasse 1: beleid per taak
# ============================================================

@pytest.mark.unit
class TestBeleidPerTaak:

    @pytest.mark.parametrize("task_id,stap", [
        ('Start_Run', 'voorbereiding'),
        ('Drop_All_Databases', 'voorbereiding'),
        ('Extract_Group.Controleer_Databases', 'extractie'),
        ('Transform1_Harmonize_Group.Harmonize_Vondst', 'transform1'),
        ('Transform2_Enhance_Attributes_Group.Enhance_All_Attributes', 'transform2'),
        ('Transform3_Set_Keys_Group.Set_Artefactnr_Unique', 'transform3'),
        ('Transform5_Move_And_Merge_Group.Merge_Artefact', 'transform5'),
        ('Transform4_Set_References_Group.Set_PrimaryKey_Vondst', 'transform4'),
        ('Load_To_Database_And_Inxdex_Group.LoadToDatabase_postgres', 'load'),
        ('Load_Upsert', 'load'),
        ('Load_To_Database_And_Inxdex_Group.Index_Def_Project', 'index'),
        ('Index_Def_Artefact', 'index'),
        ('Index_Klaar', 'index'),
        ('Registreer_Bronbestanden', 'registratie'),
        ('Rond_Run_Af', 'registratie'),
        ('Verwerkingsrapport', 'afsluiting'),
        ('End_ETL_full_cycle', 'overig'),
        (None, 'overig'),
    ])
    def test_stap_van_taak(self, task_id, stap):
        assert foutbeleid.bepaalStap(task_id) == stap

    @pytest.mark.parametrize("task_id", ['Index_Def_Project', 'Load_To_Database_And_Inxdex_Group.Index_Def_ABR'])
    def test_index_taken_zijn_waarschuwing(self, task_id):
        assert foutbeleid.isWaarschuwingstaak(task_id)
        assert not foutbeleid.isCrucialeTaak(task_id)

    @pytest.mark.parametrize("task_id", ['Start_Run', 'Drop_All_Databases', 'Extract_Group.Controleer_Afbeeldingen',
                                         'Load_Upsert', 'Load_To_Database_And_Inxdex_Group.LoadToDatabase_postgres',
                                         'Registreer_Run', 'Index_Klaar'])
    def test_cruciale_taken(self, task_id):
        assert foutbeleid.isCrucialeTaak(task_id)

    @pytest.mark.parametrize("task_id", ['Markeer_Run_Mislukt', 'Verwerkingsrapport'])
    def test_afsluitingstaken(self, task_id):
        assert foutbeleid.isAfsluitingstaak(task_id)
        assert not foutbeleid.isCrucialeTaak(task_id) and not foutbeleid.isWaarschuwingstaak(task_id)

    @pytest.mark.parametrize("totaal,aantal,pct,drempel", [
        (10, 2, 5, 2), (100, 2, 5, 5), (1000, 10, 1, 10), (100000, 10, 1, 1000), (0, 0, 0, 0), (33, 0, 1.5, 0)])
    def test_drempel_grootste_van_aantal_en_percentage(self, totaal, aantal, pct, drempel):
        assert foutbeleid.bepaalDrempel(totaal, aantal, pct) == drempel


# ============================================================
# Klasse 2: meldingen en drempels in het run-document
# ============================================================

@pytest.mark.unit
class TestMeldingen:

    def test_zonder_run_geen_melding(self, nep_client):
        assert foutbeleid.meld('waarschuwing', 'x', 'tekst') is None

    def test_melding_in_run_document(self, nep_client):
        run_id = verwerkingsrun.startRun('volledig', airflow_run_id='manual__1')
        doc = foutbeleid.meld('waarschuwing', foutbeleid.SOORT_DATABASE_LEEG, 'leeg', aantal=2, details=['a'],
                              taak='Extract_Group.Controleer_Databases')
        run = runCollectie(nep_client).find_one({'_id': run_id})
        assert run['meldingen'] == [doc]
        assert doc['stap'] == 'extractie' and doc['niveau'] == 'waarschuwing' and doc['aantal'] == 2
        assert isinstance(doc['tijdstip'], datetime)

    def test_onbekend_niveau_faalt(self, nep_client):
        with pytest.raises(ValueError):
            foutbeleid.meld('ramp', 'x', 'tekst')

    def test_meldingen_begrensd(self, nep_client, monkeypatch):
        monkeypatch.setattr(verwerkingsrun, 'MAX_MELDINGEN', 3)
        monkeypatch.setattr(verwerkingsrun, 'MAX_LENGTE_MELDING', 5)
        run_id = verwerkingsrun.startRun('incrementeel')
        for i in range(5):
            foutbeleid.meld('waarschuwing', 'x', f'melding {i}', taak='t')
        meldingen = runCollectie(nep_client).find_one({'_id': run_id})['meldingen']
        assert len(meldingen) == 3
        assert [m['melding'] for m in meldingen] == ['meldi'] * 3

    def test_fout_bij_schrijven_stopt_niets(self, nep_client, monkeypatch, caplog):
        verwerkingsrun.startRun('incrementeel')

        def kapot(melding, run_id):
            raise RuntimeError('mongo weg')
        monkeypatch.setattr(verwerkingsrun, 'voegMeldingToe', kapot)
        assert foutbeleid.meld('waarschuwing', 'x', 'tekst', taak='t') is None
        assert 'niet in het run-document' in caplog.text

    def test_drempel_nul_fouten_geen_melding(self, nep_client):
        run_id = verwerkingsrun.startRun('incrementeel')
        uitkomst = foutbeleid.toetsDrempel('s', 0, 50, 2, 5, 'Omschrijving', 'X', telling='controle')
        assert uitkomst['boven_drempel'] is False
        run = runCollectie(nep_client).find_one({'_id': run_id})
        assert run['meldingen'] == [] and run['tellingen']['controle']['aantal'] == 0

    def test_onder_drempel_waarschuwing(self, nep_client):
        run_id = verwerkingsrun.startRun('incrementeel')
        uitkomst = foutbeleid.toetsDrempel('s', 2, 10, 2, 5, 'Onleesbaar', 'X', details=['a', 'b'])
        assert uitkomst == {'aantal': 2, 'totaal': 10, 'drempel': 2, 'max_aantal': 2, 'max_pct': 5,
                            'boven_drempel': False}
        melding = runCollectie(nep_client).find_one({'_id': run_id})['meldingen'][0]
        assert melding['niveau'] == 'waarschuwing' and melding['aantal'] == 2 and melding['details'] == ['a', 'b']

    def test_boven_drempel_cruciale_fout(self, nep_client):
        run_id = verwerkingsrun.startRun('incrementeel')
        with pytest.raises(foutbeleid.CrucialeFout, match='meer dan de drempel van 2'):
            foutbeleid.toetsDrempel('s', 3, 10, 2, 5, 'Onleesbaar', 'AIRFLOW_MAX_X', telling='controle')
        run = runCollectie(nep_client).find_one({'_id': run_id})
        assert run['meldingen'][0]['niveau'] == 'fout'
        assert 'AIRFLOW_MAX_X=2' in run['meldingen'][0]['melding'] and 'AIRFLOW_MAX_X_PCT=5' in run['meldingen'][0]['melding']
        # De telling staat er ook bij een overschreden drempel
        assert run['tellingen']['controle']['boven_drempel'] is True


# ============================================================
# Klasse 3: on_failure_callback
# ============================================================

def context(task_id, run_id='manual__1', start=None, fout=None):
    dag_run = types.SimpleNamespace(run_id=run_id, start_date=start or (verwerkingsrun.nu() - timedelta(minutes=1)))
    return {'task_instance': types.SimpleNamespace(task_id=task_id), 'dag_run': dag_run,
            'exception': fout if fout is not None else RuntimeError('kapot')}


@pytest.mark.unit
class TestRegistreerTaakfout:

    def test_cruciale_taak_geeft_fout(self, nep_client):
        run_id = verwerkingsrun.startRun('volledig', airflow_run_id='manual__1')
        foutbeleid.registreerTaakfout(context('Transform1_Harmonize_Group.Harmonize_Vondst'))
        melding = runCollectie(nep_client).find_one({'_id': run_id})['meldingen'][0]
        assert melding['niveau'] == 'fout' and melding['soort'] == 'taak_mislukt'
        assert melding['stap'] == 'transform1' and melding['melding'] == 'RuntimeError: kapot'

    def test_index_taak_geeft_waarschuwing(self, nep_client):
        run_id = verwerkingsrun.startRun('volledig', airflow_run_id='manual__1')
        foutbeleid.registreerTaakfout(context('Load_To_Database_And_Inxdex_Group.Index_Def_Project',
                                              fout=ConnectionError('elasticsearch onbereikbaar')))
        melding = runCollectie(nep_client).find_one({'_id': run_id})['meldingen'][0]
        assert melding['niveau'] == 'waarschuwing' and melding['stap'] == 'index'
        assert 'elasticsearch onbereikbaar' in melding['melding']

    def test_mislukt_rapport_is_waarschuwing(self, nep_client):
        run_id = verwerkingsrun.startRun('laden', airflow_run_id='manual__1')
        foutbeleid.registreerTaakfout(context('Verwerkingsrapport'))
        assert runCollectie(nep_client).find_one({'_id': run_id})['meldingen'][0]['niveau'] == 'waarschuwing'

    def test_geen_dubbele_fout_na_drempel(self, nep_client):
        run_id = verwerkingsrun.startRun('volledig', airflow_run_id='manual__1')
        foutbeleid.meld('fout', foutbeleid.SOORT_DATABASE_ONLEESBAAR, 'boven drempel', taak='Extract_Group.Controleer_Databases')
        foutbeleid.registreerTaakfout(context('Extract_Group.Controleer_Databases'))
        assert len(runCollectie(nep_client).find_one({'_id': run_id})['meldingen']) == 1

    def test_run_van_andere_airflow_run_ongemoeid(self, nep_client):
        run_id = verwerkingsrun.startRun('incrementeel', airflow_run_id='manual__ander')
        foutbeleid.registreerTaakfout(context('Start_Run', run_id='manual__1'))
        assert runCollectie(nep_client).find_one({'_id': run_id})['meldingen'] == []

    def test_oude_run_met_zelfde_airflow_run_id_telt_niet(self, nep_client):
        """airflow dags test met dezelfde datum geeft dezelfde run_id: alleen runs na de start van de DagRun tellen."""
        oud = verwerkingsrun.startRun('incrementeel', airflow_run_id='manual__1')
        verwerkingsrun.beeindigRun('afgerond')
        foutbeleid.registreerTaakfout(context('Start_Run', start=verwerkingsrun.nu() + timedelta(minutes=1)))
        assert runCollectie(nep_client).find_one({'_id': oud})['meldingen'] == []

    def test_airflow_dags_test_met_logische_datum_als_start(self, nep_client):
        """Bij 'airflow dags test' is start_date van de DagRun de logische datum: de vroegste taakstart telt."""
        oud = verwerkingsrun.startRun('laden', airflow_run_id='manual__1')
        verwerkingsrun.beeindigRun('afgerond')
        taak_start = verwerkingsrun.nu() + timedelta(minutes=1)
        dag_run = types.SimpleNamespace(
            run_id='manual__1', start_date=datetime(2026, 1, 1),
            # Zoals bij airflow dags test: alleen het einde vastgelegd, een taak die nog niet draaide zonder tijdstip
            get_task_instances=lambda: [types.SimpleNamespace(start_date=None, end_date=taak_start),
                                        types.SimpleNamespace(start_date=None, end_date=None),
                                        types.SimpleNamespace(start_date=taak_start + timedelta(seconds=5),
                                                              end_date=taak_start + timedelta(seconds=6))])
        assert verwerkingsrun.startVanAirflowRun(dag_run) == taak_start
        foutbeleid.registreerTaakfout({'task_instance': types.SimpleNamespace(task_id='Start_Run'), 'dag_run': dag_run,
                                       'exception': RuntimeError('al een run actief')})
        assert runCollectie(nep_client).find_one({'_id': oud})['meldingen'] == []

    def test_fout_in_callback_wordt_niet_doorgegeven(self, nep_client, monkeypatch):
        def kapot(*args, **kwargs):
            raise RuntimeError('mongo weg')
        monkeypatch.setattr(verwerkingsrun, 'zoekRunVanAirflowRun', kapot)
        foutbeleid.registreerTaakfout(context('Start_Run'))


# ============================================================
# Klasse 4: controle van een DAG
# ============================================================

@pytest.mark.unit
class TestControleerBewaking:

    def test_dag_volgens_beleid(self):
        assert foutbeleid.controleerBewaking(maakDag()) == []

    def test_index_taak_die_de_dag_laat_falen(self):
        problemen = foutbeleid.controleerBewaking(maakDag(index_naar_eind=True))
        assert any('waarschuwingstaak Index_Def_Project laat de DAG falen' in p for p in problemen)

    def test_cruciale_taak_niet_bewaakt(self):
        problemen = foutbeleid.controleerBewaking(maakDag(onbewaakt=True))
        assert problemen == ['Cruciale taak Registreer_Run wordt niet bewaakt door Markeer_Run_Mislukt']

    def test_rapport_wacht_niet_op_alle_taken(self):
        problemen = foutbeleid.controleerBewaking(maakDag(rapport_mist='Index_Klaar'))
        assert problemen == ["Verwerkingsrapport wacht niet op: ['Index_Klaar']"]

    def test_verkeerde_trigger_rule_markeer(self):
        dag = maakDag()
        next(t for t in dag.tasks if t.task_id == 'Markeer_Run_Mislukt').trigger_rule = 'all_done'
        assert any('verwacht one_failed' in p for p in foutbeleid.controleerBewaking(dag))

    def test_twee_eindtaken(self):
        dag = maakDag()
        dag.tasks.append(NepTaak('Los'))
        assert any('precies één eindtaak' in p for p in foutbeleid.controleerBewaking(dag))


# ============================================================
# Klasse 5: run-document voor alle cycli
# ============================================================

@pytest.mark.unit
class TestRunDocumentAlleCycli:

    def test_registratie_sluit_aan_bij_lopende_volledige_cyclus(self, nep_client):
        """registreerVolledigeCyclus roept startRun('volledig') aan zonder airflow_run_id."""
        run_id = verwerkingsrun.startRun('volledig', airflow_run_id='manual__1', dag_id='Extract_Transform_Load_Full_Cycle')
        assert verwerkingsrun.startRun('volledig') == run_id
        assert runCollectie(nep_client).count_documents({}) == 1
        assert verwerkingsrun.huidigeRun()['dag_id'] == 'Extract_Transform_Load_Full_Cycle'

    def test_geen_aansluiting_bij_incrementele_run(self, nep_client):
        verwerkingsrun.startRun('incrementeel', airflow_run_id='manual__1')
        with pytest.raises(Exception, match='al een actieve verwerkingsrun'):
            verwerkingsrun.startRun('volledig')

    def test_nieuwe_volledige_cyclus_naast_actieve_run_faalt(self, nep_client):
        verwerkingsrun.startRun('volledig', airflow_run_id='manual__1')
        with pytest.raises(Exception, match='al een actieve verwerkingsrun'):
            verwerkingsrun.startRun('volledig', airflow_run_id='manual__2')

    def test_soort_laden(self, nep_client):
        verwerkingsrun.startRun('laden', airflow_run_id='manual__1')
        run = verwerkingsrun.huidigeRun()
        assert run['soort'] == 'laden' and run['meldingen'] == []

    def test_geen_overname_van_voor_een_volledige_cyclus(self, nep_client):
        """Een volledige cyclus (ook een mislukte) leegt MongoDB: oudere sleutels tellen niet meer."""
        verwerkingsrun.startRun('incrementeel')
        verwerkingsrun.werkRunBij({'verwijderde_keys': {'Vondst': [{'key': 'K1', 'projectcd': 'SY003'}]}})
        verwerkingsrun.beeindigRun('mislukt')
        verwerkingsrun.startRun('volledig')
        verwerkingsrun.beeindigRun('mislukt')
        verwerkingsrun.startRun('incrementeel')
        assert verwerkingsrun.huidigeRun()['overgenomen_van'] == []

    def test_laden_telt_niet_als_geslaagde_run_voor_overname(self, nep_client):
        verwerkingsrun.startRun('incrementeel')
        verwerkingsrun.werkRunBij({'verwijderde_keys': {'Vondst': [{'key': 'K1', 'projectcd': 'SY003'}]}})
        mislukt = verwerkingsrun.huidigeRun()['run_id']
        verwerkingsrun.beeindigRun('mislukt')
        verwerkingsrun.startRun('laden')
        verwerkingsrun.beeindigRun('afgerond')
        verwerkingsrun.startRun('incrementeel')
        assert verwerkingsrun.huidigeRun()['overgenomen_van'] == [mislukt]

    def test_zoek_run_van_airflow_run_ook_na_afloop(self, nep_client):
        start = verwerkingsrun.nu() - timedelta(seconds=5)
        run_id = verwerkingsrun.startRun('volledig', airflow_run_id='manual__1')
        verwerkingsrun.beeindigRun('afgerond')
        assert verwerkingsrun.zoekRunVanAirflowRun('manual__1', sinds=start)['run_id'] == run_id
        assert verwerkingsrun.zoekRunVanAirflowRun('manual__2', sinds=start) is None
        assert verwerkingsrun.zoekRunVanAirflowRun('manual__1', sinds=verwerkingsrun.nu() + timedelta(minutes=1)) is None

    def test_zoek_run_met_tijdzone(self, nep_client):
        from datetime import timezone
        run_id = verwerkingsrun.startRun('volledig', airflow_run_id='manual__1')
        sinds = datetime.now(timezone.utc) - timedelta(minutes=1)
        assert verwerkingsrun.zoekRunVanAirflowRun('manual__1', sinds=sinds)['run_id'] == run_id

    def test_markeer_mislukt_noemt_mislukte_taken(self, nep_client):
        verwerkingsrun.startRun('volledig', airflow_run_id='manual__1')
        tis = [types.SimpleNamespace(task_id='Extract_Group.Controleer_Afbeeldingen', state='failed'),
               types.SimpleNamespace(task_id='Extract_Group.last', state='upstream_failed'),
               types.SimpleNamespace(task_id='Start_Run', state='success')]
        dag_run = types.SimpleNamespace(get_task_instances=lambda: tis)
        verwerkingsrun.markeerRunMislukt(airflow_run_id='manual__1', dag_run=dag_run)
        run = runCollectie(nep_client).find_one({})
        assert run['status'] == 'mislukt'
        assert run['melding'] == 'Mislukte taak in Airflow-run manual__1: Extract_Group.Controleer_Afbeeldingen.'

    def test_rond_run_af(self, nep_client):
        verwerkingsrun.startRun('laden', airflow_run_id='manual__1')
        verwerkingsrun.rondRunAf(airflow_run_id='manual__2')
        assert verwerkingsrun.huidigeRun()['status'] == 'actief'
        verwerkingsrun.rondRunAf(airflow_run_id='manual__1')
        assert runCollectie(nep_client).find_one({})['status'] == 'afgerond'

    def test_run_van_taak_alleen_eigen_airflow_run(self, nep_client, monkeypatch):
        verwerkingsrun.startRun('incrementeel', airflow_run_id='manual__ander')
        monkeypatch.setattr(verwerkingsrun, 'getAirflowContext',
                            lambda: {'dag_run': types.SimpleNamespace(run_id='manual__1')})
        assert verwerkingsrun.runVanTaak() is None
        monkeypatch.setattr(verwerkingsrun, 'getAirflowContext',
                            lambda: {'dag_run': types.SimpleNamespace(run_id='manual__ander')})
        assert verwerkingsrun.runVanTaak()['airflow_run_id'] == 'manual__ander'
        monkeypatch.setattr(verwerkingsrun, 'getAirflowContext', lambda: None)
        assert verwerkingsrun.runVanTaak() is not None


# ============================================================
# Klasse 6: Drop_All_Databases
# ============================================================

class NepDropDatabase:
    def __init__(self, namen):
        self.namen = list(namen)
        self.verwijderd = []

    def list_collection_names(self):
        return list(self.namen)

    def drop_collection(self, naam):
        self.verwijderd.append(naam)


class NepDropClient:
    def __init__(self, staging, fout=None):
        self.staging = staging
        self.fout = fout
        self.gedropt = []
        self.gesloten = False

    def __getitem__(self, naam):
        return self.staging

    def drop_database(self, naam):
        if self.fout:
            raise self.fout
        self.gedropt.append(naam)

    def close(self):
        self.gesloten = True


@pytest.mark.unit
class TestDropAll:

    def test_verwerkingsruns_blijven_staan(self, monkeypatch):
        import wasstraat.mongoUtils as mongoUtils
        staging = NepDropDatabase(['Staging_Projecten_Oud', 'Verwerkingsruns', 'Verwerkingsrun_Bestanden', 'Plaatjes'])
        client = NepDropClient(staging)
        monkeypatch.setattr(mongoUtils.pymongo, 'MongoClient', lambda uri: client)
        mongoUtils.dropAll()
        assert staging.verwijderd == ['Staging_Projecten_Oud', 'Verwerkingsrun_Bestanden', 'Plaatjes']
        assert client.gedropt == [mongoUtils.config.DB_FILES, mongoUtils.config.DB_ANALYSE]
        assert client.gesloten

    def test_fout_laat_taak_falen(self, monkeypatch):
        """Tot issue 54 werd de fout alleen gelogd en las de extractie bovenop de oude data in."""
        import wasstraat.mongoUtils as mongoUtils
        client = NepDropClient(NepDropDatabase([]), fout=RuntimeError('geen verbinding'))
        monkeypatch.setattr(mongoUtils.pymongo, 'MongoClient', lambda uri: client)
        with pytest.raises(Exception, match='geen verbinding'):
            mongoUtils.dropAll()
        assert client.gesloten


# ============================================================
# Klasse 7: Transform 2 en 3
# ============================================================

@pytest.mark.unit
class TestTransformFouten:

    def test_verwerkingsfouten_onder_drempel_waarschuwing(self, nep_client):
        import wasstraat.setAttributes_functions as sa
        run_id = verwerkingsrun.startRun('volledig')
        sa.toetsVerwerkingsfouten('enhance_attributes', 3, 1000, [{'original_id': 'x'}])
        run = runCollectie(nep_client).find_one({'_id': run_id})
        assert run['tellingen']['verwerkingsfouten']['enhance_attributes']['drempel'] == 100
        assert run['meldingen'][0]['soort'] == 'verwerkingsfouten' and run['meldingen'][0]['niveau'] == 'waarschuwing'

    def test_verwerkingsfouten_boven_drempel_stopt(self, nep_client, monkeypatch):
        import wasstraat.setAttributes_functions as sa
        monkeypatch.setattr(sa.config, 'AIRFLOW_MAX_VERWERKINGSFOUTEN', 0)
        monkeypatch.setattr(sa.config, 'AIRFLOW_MAX_VERWERKINGSFOUTEN_PCT', 0)
        verwerkingsrun.startRun('volledig')
        with pytest.raises(foutbeleid.CrucialeFout, match='AIRFLOW_MAX_VERWERKINGSFOUTEN=0'):
            sa.toetsVerwerkingsfouten('imagedata', 1, 10, [])

    def test_maak_voorbeeld(self):
        import wasstraat.setAttributes_functions as sa
        voorbeeld = sa._maakVoorbeeld({'_id': 7, 'soort': 'Vondst', 'projectcd': 'SY001'}, KeyError('vondstnr'))
        assert voorbeeld == {'original_id': '7', 'soort': 'Vondst', 'projectcd': 'SY001', 'fout': "KeyError: 'vondstnr'"}


class NepUniekCollectie:
    """Collectie voor setAndVondstUniqueInProject: artefacten per project, projecten en een aggregatie."""

    def __init__(self, artefacten, projecten, aggregatie=None, fout_bij=None):
        self.artefacten = artefacten
        self.projecten = projecten
        self.aggregatie = aggregatie or []
        self.fout_bij = fout_bij
        self.vervangen = []
        self.bijgewerkt = []
        self.database = types.SimpleNamespace(client=types.SimpleNamespace(close=lambda: None))

    def find(self, filt, projection=None):
        if self.fout_bij == 'find':
            raise RuntimeError('mongo weg')
        if 'projectcd' in filt and isinstance(filt['projectcd'], str):
            return [d for d in self.artefacten if d['projectcd'] == filt['projectcd']]
        return types.SimpleNamespace(distinct=lambda veld: sorted({d['projectcd'] for d in self.artefacten}))

    def find_one(self, filt):
        return self.projecten.get(filt['projectcd'])

    def replace_one(self, filt, doc):
        self.vervangen.append(doc)

    def aggregate(self, pipeline):
        return iter(self.aggregatie)

    def update_many(self, filt, update):
        self.bijgewerkt.append(filt)


@pytest.mark.unit
class TestUniekeNummers:

    def draai(self, monkeypatch, col):
        import wasstraat.references_functions as rf
        monkeypatch.setattr(rf, 'getAnalyseCollection', lambda: col)
        rf.setAndVondstUniqueInProject()

    def test_fout_per_project_is_waarschuwing(self, nep_client, monkeypatch):
        verwerkingsrun.startRun('volledig')
        col = NepUniekCollectie(
            artefacten=[{'projectcd': 'SY001', 'subnr': 1}, {'projectcd': 'SY002', 'subnr': 1}],
            projecten={'SY001': {'_id': 1, 'projectcd': 'SY001'}})  # SY002 heeft geen projectrecord
        self.draai(monkeypatch, col)
        assert col.vervangen == [{'_id': 1, 'projectcd': 'SY001', 'artefactnrs_unique': True}]
        melding = verwerkingsrun.huidigeRun()['meldingen'][0]
        assert melding['soort'] == 'uniciteit_niet_bepaald' and melding['aantal'] == 1
        assert melding['details'][0]['projectcd'] == 'SY002'

    def test_geen_vondsten_in_meerdere_putten_geen_fout(self, nep_client, monkeypatch):
        """Een lege aggregatie gaf een KeyError die tot issue 54 als 'Severe error' werd genegeerd."""
        verwerkingsrun.startRun('volledig')
        col = NepUniekCollectie(artefacten=[{'projectcd': 'SY001', 'subnr': 1}],
                                projecten={'SY001': {'_id': 1, 'projectcd': 'SY001'}})
        self.draai(monkeypatch, col)
        assert col.bijgewerkt == [] and verwerkingsrun.huidigeRun()['meldingen'] == []

    def test_vlag_vondstkey_met_putnr(self, nep_client, monkeypatch):
        col = NepUniekCollectie(artefacten=[{'projectcd': 'SY001', 'subnr': 1}],
                                projecten={'SY001': {'_id': 1, 'projectcd': 'SY001'}},
                                aggregatie=[{'projectcd': 'SY001'}, {'projectcd': None}])
        self.draai(monkeypatch, col)
        assert col.bijgewerkt[0]['projectcd'] == {'$in': ['SY001']}

    def test_project_zonder_subnrs_geen_waarschuwing(self, nep_client, monkeypatch):
        verwerkingsrun.startRun('volledig')
        col = NepUniekCollectie(artefacten=[{'projectcd': 'SY001'}], projecten={'SY001': {'_id': 1, 'projectcd': 'SY001'}})
        self.draai(monkeypatch, col)
        assert col.vervangen == [] and verwerkingsrun.huidigeRun()['meldingen'] == []

    def test_fout_buiten_de_projecten_laat_taak_falen(self, nep_client, monkeypatch):
        col = NepUniekCollectie(artefacten=[], projecten={}, fout_bij='find')
        with pytest.raises(Exception, match='Severe error'):
            self.draai(monkeypatch, col)


# ============================================================
# Klasse 8: de laadstap
# ============================================================

@pytest.mark.unit
class TestLaadstapMeldingen:

    def test_hernummerde_sleutels_waarschuwing(self, nep_client):
        import wasstraat.loadToDatabase_functions as load
        from tests.unit.test_load_volledig import maakPostgres, artefact
        run_id = verwerkingsrun.startRun('laden')
        pg = maakPostgres([artefact(0, 'A')])
        pg.tabellen['Def_Artefact_new'] = {'kolommen': pg.tabellen['Def_Artefact']['kolommen'],
                                           'rijen': {0: artefact(0, 'B')}}
        load.bepaalVervallenSleutels(pg.cursor(), [('Def_Artefact', 'Def_Artefact_new')])
        melding = runCollectie(nep_client).find_one({'_id': run_id})['meldingen'][0]
        assert melding['soort'] == 'sleutels_niet_stabiel' and melding['details'] == {'Def_Artefact': 1}

    def test_tellingen_van_de_volledige_load(self, nep_client):
        import wasstraat.loadToDatabase_functions as load

        class TelCursor:
            AANTALLEN = {'Def_Artefact': 10, 'Def_Artefact_new': 12, 'Def_Project': 2, 'Def_Project_new': 2}

            def execute(self, sql, params=None):
                self.tabel = sql.split('"')[1]

            def fetchone(self):
                return (self.AANTALLEN[self.tabel],)

        vervallen = {'Def_Artefact': {'verdwenen': [3, 4], 'hernummerd': [5]}, 'Def_Project': {'verdwenen': [], 'hernummerd': []}}
        tellingen = load.telLaadRijen(TelCursor(), [('Def_Artefact', 'Def_Artefact_new'), ('Def_Project', 'Def_Project_new')],
                                      vervallen)
        assert tellingen['Def_Artefact'] == {'rijen_voor': 10, 'rijen': 12, 'ingevoegd': 4, 'verwijderd': 2, 'hernummerd': 1}
        assert tellingen['totaal'] == {'rijen_voor': 12, 'rijen': 14, 'ingevoegd': 4, 'verwijderd': 2, 'hernummerd': 1}

    def test_load_tellingen_in_run_document(self, nep_client):
        import wasstraat.loadToDatabase_functions as load
        run_id = verwerkingsrun.startRun('laden')
        load.schrijfLoadTellingen({'totaal': {'rijen': 3}}, {'Def_Bruikleen': {}}, None)
        run = runCollectie(nep_client).find_one({'_id': run_id})
        assert run['tellingen']['load'] == {'totaal': {'rijen': 3}}
        assert 'afgeleide_velden' not in run['tellingen']

    def test_load_tellingen_zonder_run(self, nep_client):
        import wasstraat.loadToDatabase_functions as load
        load.schrijfLoadTellingen({'totaal': {}}, {}, {})

    def test_niet_gevalideerde_fk_incrementeel_waarschuwing(self, omgeving, monkeypatch):
        import wasstraat.loadToDatabase_functions as load
        monkeypatch.setattr(load, 'valideerFkConstraints', lambda cursor, fks: ['Def_Artefact_projectID_fkey'])
        load.loadIncrementeel()
        run = verwerkingsrun.huidigeRun()
        assert run['tellingen']['load']['fk_niet_gevalideerd'] == ['Def_Artefact_projectID_fkey']
        melding = [m for m in run['meldingen'] if m['soort'] == 'fk_niet_gevalideerd'][0]
        assert melding['niveau'] == 'waarschuwing' and melding['aantal'] == 1
