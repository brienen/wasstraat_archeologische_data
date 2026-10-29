"""
Unit tests voor het verwerkingsrapport (issue 62, wasstraat/verwerkingsrapport.py).

Met een nagebootst run-document, nagebootste collecties (tests/unit/nep_mongo.py),
een nagebootste PostgreSQL en een nagebootste Airflow DagRun:

- de opbouw per sectie: bronbestanden, objecttotalen (incrementeel en volledig),
  kwaliteitsmeldingen, foutbeleid en pipeline (doorlooptijd per stap);
- de JSON-structuur en de Markdown-koppen, ook bij lege secties en zonder run-document;
- een sectie die niet opgebouwd kan worden (het rapport komt er toch);
- het schrijven (bestandsnaam met run-id, soort en tijdstip; terugval naar
  AIRFLOW_LOGDIR/rapporten) en het veld rapport in het run-document;
- de versie uit de omgeving of uit een bestand.
"""
import json
import os
import types
from datetime import datetime, timedelta

import pytest

import wasstraat.verwerkingsrapport as rapportmodule
import wasstraat.verwerkingsrun as verwerkingsrun
from tests.unit.nep_mongo import NepClient

T0 = datetime(2026, 10, 29, 10, 0, 0)
KOPPEN = ['## Foutbeleid', '### Fouten', '### Waarschuwingen', '### Mislukte taken', '## Bronbestanden',
          '### Totalen per categorie', '### Bestanden', '## Objecttotalen', '### Artefacten per soort',
          '## Kwaliteitsmeldingen', '### Verwerkingsfouten (Transform 2)', '### Afbeeldingen en rapporten',
          '### Access-databases', '### Overgeslagen paden (paden_overslaan)',
          '### Harmonisatie: tabellen bij meer dan één soort', '### Locatiefouten',
          '### Onherkende bestandsnamen', '### Rijen zonder key', '### Verwijzingen (FK)', '### Gebruikersdata',
          '### Sleutels', '### Afgeleide velden', '## Pipeline', '### Doorlooptijd per stap', '### Langste taken']


def ti(task_id, state='success', start=0, duur=10, pogingen=1):
    begin = T0 + timedelta(seconds=start) if start is not None else None
    return types.SimpleNamespace(task_id=task_id, state=state, start_date=begin,
                                 end_date=begin + timedelta(seconds=duur) if begin and duur is not None else None,
                                 duration=duur if begin else None, try_number=pogingen)


class NepDagRun:
    def __init__(self, tis, run_id='manual__1', dag_id='Extract_Transform_Load_Incremental', start=T0):
        self.tis = tis
        self.run_id = run_id
        self.dag_id = dag_id
        self.start_date = start

    def get_task_instances(self):
        return self.tis


TAKEN_GESLAAGD = [ti('Start_Run', start=0, duur=1), ti('Extract_Group.Extract_Data_From_Projecten', start=1, duur=20),
                  ti('Extract_Group.Controleer_Databases', start=21, duur=1),
                  ti('Transform1_Harmonize_Group.Harmonize_Vondst', start=22, duur=5),
                  ti('Load_Upsert', start=30, duur=15), ti('Index_Def_Project', start=45, duur=3),
                  ti('Index_Klaar', start=48, duur=0), ti('Registreer_Run', start=49, duur=2),
                  ti('Markeer_Run_Mislukt', state='skipped', start=None)]


def maakRun(soort='incrementeel', status='afgerond', **extra):
    run = verwerkingsrun.maakRunDocument('20261029T100000', soort, airflow_run_id='manual__1', tijdstip=T0,
                                         dag_id='Extract_Transform_Load_Incremental')
    run.update({'status': status, 'beeindigd_op': T0 + timedelta(seconds=55)})
    run.update(extra)
    return run


# ============================================================
# Klasse 1: pipeline en taken
# ============================================================

@pytest.mark.unit
class TestPipeline:

    def test_taken_uit_airflow(self):
        taken = rapportmodule.leesTaken(NepDagRun(TAKEN_GESLAAGD + [ti('Verwerkingsrapport', 'running', 60)]),
                                        uitsluiten={'Verwerkingsrapport'})
        assert [t['taak'] for t in taken][:2] == ['Start_Run', 'Extract_Group.Extract_Data_From_Projecten']
        assert taken[-1]['taak'] == 'Markeer_Run_Mislukt' and taken[-1]['start'] is None
        load = next(t for t in taken if t['taak'] == 'Load_Upsert')
        assert load == {'taak': 'Load_Upsert', 'stap': 'load', 'status': 'success', 'start': T0 + timedelta(seconds=30),
                        'eind': T0 + timedelta(seconds=45), 'duur_seconden': 15, 'start_geschat': False,
                        'pogingen': 1, 'cruciaal': True}

    def test_start_geschat_bij_airflow_dags_test(self):
        """airflow dags test legt alleen het einde vast: start = einde van de vorige taak."""
        tis = [types.SimpleNamespace(task_id=t, state='success', start_date=None, end_date=T0 + timedelta(seconds=s),
                                     duration=None, try_number=1)
               for t, s in [('Start_Run', 2), ('Load_Upsert', 12), ('Registreer_Run', 13)]]
        taken = {t['taak']: t for t in rapportmodule.leesTaken(NepDagRun(tis))}
        assert taken['Load_Upsert']['start'] == T0 + timedelta(seconds=2) and taken['Load_Upsert']['duur_seconden'] == 10
        assert taken['Start_Run']['duur_seconden'] == 0 and taken['Start_Run']['start_geschat'] is True

    def test_doorlooptijd_per_stap(self):
        stappen = {s['stap']: s for s in rapportmodule.bepaalStappen(rapportmodule.leesTaken(NepDagRun(TAKEN_GESLAAGD)))}
        assert stappen['extractie']['duur_seconden'] == 21 and stappen['extractie']['taken'] == 2
        assert stappen['index']['taken'] == 2 and stappen['index']['som_taakduur_seconden'] == 3
        assert stappen['afsluiting']['overgeslagen'] == 1 and stappen['afsluiting']['duur_seconden'] is None

    def test_mislukte_en_niet_uitgevoerde_taken(self):
        taken = rapportmodule.leesTaken(NepDagRun([ti('Load_Upsert', 'failed'), ti('Registreer_Run', 'upstream_failed', None)]))
        stap = {s['stap']: s for s in rapportmodule.bepaalStappen(taken)}
        assert stap['load']['mislukt'] == 1 and stap['registratie']['niet_uitgevoerd'] == 1


# ============================================================
# Klasse 2: bronbestanden
# ============================================================

@pytest.mark.unit
class TestBronbestanden:

    def test_incrementele_run(self):
        run = maakRun(tellingen={
            'delta': {'totaal': {'nieuw': 3}},
            'extractie': {'onleesbare_databases': [{'bestand': '/p/SY003/kapot.mdb', 'categorie': 'projecten'}],
                          'lege_databases': [{'bestand': '/p/SY004/leeg.mdb', 'categorie': 'projecten'}],
                          'overgeslagen_tabellen': [{'bestand': '/p/SY003/nieuw.mdb', 'tabel': 'MUNTEN',
                                                     'reden': 'geen kopregel gelezen', 'categorie': 'projecten'}]},
            'paden_overgeslagen': {'projecten': 1, 'totaal': 1}},
            paden_overgeslagen={'projecten': ['/p/DC024/werkmap/kopie.mdb']})
        run_bestanden = [
            {'pad': '/p/SY001/oud.mdb', 'categorie': 'projecten', 'status': 'ongewijzigd', 'grootte': 10},
            {'pad': '/p/SY003/nieuw.mdb', 'categorie': 'projecten', 'status': 'nieuw', 'grootte': 20},
            {'pad': '/p/SY003/kapot.mdb', 'categorie': 'projecten', 'status': 'nieuw', 'grootte': 5},
            {'pad': '/p/SY004/leeg.mdb', 'categorie': 'projecten', 'status': 'nieuw', 'grootte': 5},
            {'pad': '/p/SY003/F001.jpg', 'categorie': 'afbeeldingen', 'status': 'nieuw', 'grootte': 99},
            {'pad': '/p/SY003/F002.jpg', 'categorie': 'afbeeldingen', 'status': 'verwijderd', 'grootte': None},
            {'pad': '/p/SY001/F009.jpg', 'categorie': 'afbeeldingen', 'status': 'ongewijzigd', 'grootte': 99},
        ]
        registratie = [
            {'pad': '/p/SY003/nieuw.mdb', 'categorie': 'projecten', 'grootte': 20, 'status': 'verwerkt', 'aantal_records': 57},
            {'pad': '/p/SY003/kapot.mdb', 'categorie': 'projecten', 'grootte': 5, 'status': 'verwerkt', 'aantal_records': 0},
            {'pad': '/p/SY004/leeg.mdb', 'categorie': 'projecten', 'grootte': 5, 'status': 'verwerkt', 'aantal_records': 0},
            {'pad': '/p/SY003/F001.jpg', 'categorie': 'afbeeldingen', 'grootte': 99, 'status': 'verwerkt', 'aantal_records': 0},
            {'pad': '/p/SY003/F002.jpg', 'categorie': 'afbeeldingen', 'grootte': None, 'status': 'verwijderd', 'aantal_records': 0},
        ]
        afbeeldingen = [{'filename': '/p/SY003/F003.tif', 'processed': True, 'overgeslagen': 'jpg-versie aanwezig'},
                        {'filename': '/p/SY003/kapot.jpg', 'processed': False, 'fout': 'cannot identify image'}]
        sectie = rapportmodule.bouwBronbestanden(run, registratie, run_bestanden, afbeeldingen)

        per_bestand = {b['bestand']: b for b in sectie['bestanden']}
        assert per_bestand['/p/SY003/kapot.mdb']['status'] == 'mislukt'
        assert 'onleesbaar' in per_bestand['/p/SY003/kapot.mdb']['reden']
        assert per_bestand['/p/SY004/leeg.mdb']['records'] == 0 and 'geen records' in per_bestand['/p/SY004/leeg.mdb']['reden']
        assert per_bestand['/p/SY003/nieuw.mdb']['records'] == 57
        assert per_bestand['/p/SY003/nieuw.mdb']['tabellen_overgeslagen'] == [{'tabel': 'MUNTEN', 'reden': 'geen kopregel gelezen'}]
        assert per_bestand['/p/SY003/F001.jpg']['wijziging'] == 'nieuw'
        assert per_bestand['/p/SY003/F002.jpg']['status'] == 'verwijderd'
        assert per_bestand['/p/SY003/F003.tif']['status'] == 'overgeslagen'
        assert per_bestand['/p/SY003/kapot.jpg']['status'] == 'mislukt'
        assert per_bestand['/p/DC024/werkmap/kopie.mdb']['reden'] == 'paden_overslaan (correcties.yml)'
        # Ongewijzigde bestanden tellen mee, maar staan niet in de lijst
        assert '/p/SY001/oud.mdb' not in per_bestand and '/p/SY001/F009.jpg' not in per_bestand
        assert sectie['totalen']['projecten'] == {'verwerkt': 2, 'overgeslagen': 1, 'mislukt': 1, 'onverwerkt': 0,
                                                  'verwijderd': 0, 'ongewijzigd': 1}
        assert sectie['totalen']['afbeeldingen']['ongewijzigd'] == 1 and sectie['totalen']['afbeeldingen']['mislukt'] == 1
        # Volgorde: eerst de problemen
        assert sectie['bestanden'][0]['status'] == 'mislukt'
        assert sectie['registratie_uitgevoerd'] is True and sectie['weggelaten'] == 0
        assert sectie['paden_overgeslagen'] == {'projecten': 1, 'totaal': 1}

    def test_volledige_cyclus_noemt_verwerkte_afbeeldingen_niet(self):
        registratie = [{'pad': f'/p/F{i}.jpg', 'categorie': 'afbeeldingen', 'grootte': 1, 'status': 'verwerkt',
                        'aantal_records': 0} for i in range(5)]
        sectie = rapportmodule.bouwBronbestanden(maakRun('volledig'), registratie, [], [])
        assert sectie['bestanden'] == [] and sectie['totalen']['afbeeldingen']['verwerkt'] == 5

    def test_begrensde_lijst(self, monkeypatch):
        monkeypatch.setattr(rapportmodule, 'MAX_BESTANDEN', 2)
        registratie = [{'pad': f'/p/{i}.mdb', 'categorie': 'projecten', 'grootte': 1, 'status': 'verwerkt',
                        'aantal_records': 1} for i in range(5)]
        sectie = rapportmodule.bouwBronbestanden(maakRun('volledig'), registratie, [], [])
        assert len(sectie['bestanden']) == 2 and sectie['weggelaten'] == 3

    def test_mislukte_run_zonder_registratie(self):
        """De run stopte vóór de registratie: nieuwe bestanden zijn onverwerkt, verwijderde blijven verwijderd."""
        run_bestanden = [{'pad': '/p/nieuw.mdb', 'categorie': 'projecten', 'status': 'nieuw', 'grootte': 1},
                         {'pad': '/p/weg.mdb', 'categorie': 'projecten', 'status': 'verwijderd', 'grootte': None}]
        sectie = rapportmodule.bouwBronbestanden(maakRun(status='mislukt'), [], run_bestanden, [])
        assert {b['bestand']: b['status'] for b in sectie['bestanden']} == {'/p/nieuw.mdb': 'onverwerkt',
                                                                            '/p/weg.mdb': 'verwijderd'}
        assert sectie['registratie_uitgevoerd'] is False

    def test_zonder_registratie(self):
        sectie = rapportmodule.bouwBronbestanden(None, [], [], [])
        assert sectie['registratie_uitgevoerd'] is False and sectie['bestanden'] == [] and sectie['totalen'] == {}


# ============================================================
# Klasse 3: objecttotalen en kwaliteit
# ============================================================

@pytest.mark.unit
class TestObjecttotalenEnKwaliteit:

    def test_incrementeel_uit_upsert(self):
        run = maakRun(tellingen={'load': {'Def_Vondst': {'upsert': 10, 'ingevoegd': 2, 'bijgewerkt': 1, 'verwijderd': 3},
                                          'totaal': {}},
                                 'transform': {'primary_keys': {'Vondst': {'nieuw': 2}}}})
        sectie = rapportmodule.bouwObjecttotalen(run, {'Def_Vondst': 9, 'Def_Project': 2}, {'Glas': 3}, {'Vondst': 4})
        assert sectie['tabellen']['Def_Vondst'] == {'totaal': 9, 'aangemaakt': 2, 'bijgewerkt': 1, 'samengevoegd': 4,
                                                   'verwijderd': 3, 'nieuwe_sleutels': 2}
        assert sectie['tabellen']['Def_Project']['aangemaakt'] is None
        assert sectie['totaal'] == {'totaal': 11, 'aangemaakt': 2, 'bijgewerkt': 1, 'samengevoegd': 4, 'verwijderd': 3}
        assert sectie['load_uitgevoerd'] is True and sectie['artefactsoorten'] == {'Glas': 3}

    def test_volledig_uit_vergelijking_van_tabellen(self):
        run = maakRun('volledig', tellingen={'load': {'Def_Vondst': {'rijen_voor': 8, 'rijen': 9, 'ingevoegd': 2,
                                                                     'verwijderd': 1, 'hernummerd': 0}}})
        sectie = rapportmodule.bouwObjecttotalen(run, {'Def_Vondst': 9}, {}, {})
        assert sectie['tabellen']['Def_Vondst']['aangemaakt'] == 2 and sectie['tabellen']['Def_Vondst']['bijgewerkt'] is None

    def test_zonder_load(self):
        sectie = rapportmodule.bouwObjecttotalen(maakRun(status='mislukt'), {'Def_Vondst': 9}, {}, {})
        assert sectie['load_uitgevoerd'] is False and sectie['totaal']['totaal'] == 9 and sectie['totaal']['aangemaakt'] is None

    def test_kwaliteit_uit_run_document(self):
        run = maakRun('volledig', tellingen={
            'load': {'Def_Artefact': {'hernummerd': 2}, 'fk_niet_hersteld': 0, 'fk_niet_gevalideerd': ['fk_a']},
            'gebruikersdata': {'Def_Bruikleen': {'artefactID': {'losgekoppeld': 1}}},
            'transform': {'primary_keys': {'Artefact': {'nieuw': 3, 'verdwenen': 1}, 'Put': {'nieuw': 0, 'verdwenen': 0}}},
            'afbeeldingen': {'totaal': 5, 'mislukt': 1},
            'extractie': {'databases': 3, 'onleesbaar': 1, 'leeg': 0, 'tabellen_overgeslagen': 0, 'drempel': 2}},
            meldingen=[{'niveau': 'waarschuwing', 'soort': 'afgeleide_velden_mislukt', 'melding': 'kapot'}])
        kw = rapportmodule.bouwKwaliteit(run, [{'fase': 'enhance_attributes', 'soort': 'Vondst', 'fouttype': 'KeyError',
                                                'aantal': 2, 'voorbeelden': []}],
                                         {'locatiefouten': [], 'onherkende_bestandsnamen': {'aantal': 0}}, {'Def_Put': 1})
        assert kw['verwerkingsfouten']['totaal'] == 2
        assert kw['sleutels'] == {'hernummerd': {'Def_Artefact': 2}, 'nieuw_en_verdwenen': {'Artefact': {'nieuw': 3, 'verdwenen': 1}}}
        assert kw['fk']['niet_gevalideerd'] == ['fk_a'] and kw['databases']['onleesbaar'] == 1
        assert kw['afgeleide_velden']['mislukt'] is True and kw['rijen_zonder_key'] == {'Def_Put': 1}

    def test_kwaliteit_zonder_run(self):
        kw = rapportmodule.bouwKwaliteit(None, [], None, None)
        assert kw['afbeeldingen'] is None and kw['databases'] is None and kw['fk'] is None
        assert kw['harmonisatie_voorrang'] == []

    def test_voorrang_bij_de_harmonisatie(self):
        """Issue 89: de besluiten per melder uit het run-document, één lijst op collectie en tabel."""
        aw1 = {'tabel': 'AW1DeterminatiesJohan', 'collectie': 'Staging_Projecten_Oud', 'kandidaten': ['Aardewerk', 'Artefact'],
               'gekozen': 'Aardewerk', 'bron': 'correcties.yml'}
        code = {'tabel': 'CODES', 'collectie': 'Staging_Projecten_Oud', 'kandidaten': ['Vlak', 'Metaal'],
                'gekozen': None, 'bron': 'correcties.yml'}
        regel = {'tabel': 'X', 'collectie': 'Staging_Projecten_Monster', 'kandidaten': ['Monster', 'Monster_Schelp'],
                 'gekozen': 'Monster', 'bron': 'voorrangsregel'}
        ongeldig = dict(regel, tabel='Y', ongeldige_instelling='Glas')
        run = maakRun('volledig', tellingen={'transform': {'harmonisatie_voorrang': {
            'Aardewerk': [aw1], 'Vlak': [code], 'Monster': [regel, ongeldig]}}})
        kw = rapportmodule.bouwKwaliteit(run, [], None, None)
        assert [b['tabel'] for b in kw['harmonisatie_voorrang']] == ['X', 'Y', 'AW1DeterminatiesJohan', 'CODES']
        md = rapportmodule.maakMarkdown({'kwaliteitsmeldingen': kw})
        assert '| AW1DeterminatiesJohan | Staging_Projecten_Oud | Aardewerk, Artefact | Aardewerk | correcties.yml |' in md
        assert '| CODES | Staging_Projecten_Oud | Vlak, Metaal | geen enkele soort | correcties.yml |' in md
        assert '| X | Staging_Projecten_Monster | Monster, Monster_Schelp | Monster | voorrangsregel (waarschuwing) |' in md
        assert 'voorrangsregel; instelling Glas genegeerd' in md


# ============================================================
# Klasse 4: foutbeleid
# ============================================================

@pytest.mark.unit
class TestFoutbeleidSectie:

    def test_geslaagd(self):
        fb = rapportmodule.bepaalFoutbeleid(maakRun(), rapportmodule.leesTaken(NepDagRun(TAKEN_GESLAAGD)))
        assert fb['uitkomst'] == 'geslaagd' and fb['gestopt_door'] is None and fb['fouten'] == []

    def test_waarschuwing_bij_mislukte_index(self):
        taken = rapportmodule.leesTaken(NepDagRun([ti('Load_Upsert'), ti('Index_Def_Project', 'failed', 20)]))
        run = maakRun(meldingen=[{'niveau': 'waarschuwing', 'stap': 'index', 'taak': 'Index_Def_Project',
                                  'soort': 'taak_mislukt', 'melding': 'ConnectionError: es weg'}])
        fb = rapportmodule.bepaalFoutbeleid(run, taken)
        assert fb['uitkomst'] == 'geslaagd met waarschuwingen' and fb['gestopt_door'] is None
        assert fb['mislukte_taken'] == [{'taak': 'Index_Def_Project', 'stap': 'index', 'cruciaal': False}]

    def test_cruciale_fout_stopt_run(self):
        taken = rapportmodule.leesTaken(NepDagRun([ti('Extract_Group.Controleer_Afbeeldingen', 'failed', 5),
                                                   ti('Load_Upsert', 'upstream_failed', None)]))
        run = maakRun(status='mislukt', meldingen=[
            {'niveau': 'fout', 'stap': 'extractie', 'taak': 'Extract_Group.Controleer_Afbeeldingen',
             'soort': 'afbeeldingen_mislukt', 'melding': '1 van de 1 afbeeldingen niet verwerkt'}])
        fb = rapportmodule.bepaalFoutbeleid(run, taken)
        assert fb['uitkomst'] == 'mislukt' and fb['niet_uitgevoerd'] == 1
        assert fb['gestopt_door'] == {'taak': 'Extract_Group.Controleer_Afbeeldingen', 'stap': 'extractie',
                                      'melding': '1 van de 1 afbeeldingen niet verwerkt'}

    def test_mislukte_taak_zonder_melding(self):
        taken = rapportmodule.leesTaken(NepDagRun([ti('Load_Upsert', 'failed')]))
        fb = rapportmodule.bepaalFoutbeleid(maakRun(status='mislukt'), taken)
        assert fb['fouten'][0]['taak'] == 'Load_Upsert' and 'log van de taak' in fb['fouten'][0]['melding']
        assert fb['gestopt_door']['taak'] == 'Load_Upsert'

    def test_run_mislukt_zonder_mislukte_taak(self):
        fb = rapportmodule.bepaalFoutbeleid(maakRun(status='mislukt', melding='Registratie mislukt'), [])
        assert fb['uitkomst'] == 'mislukt' and fb['gestopt_door'] == {'taak': None, 'stap': None,
                                                                         'melding': 'Registratie mislukt'}

    def test_zonder_run_met_mislukte_start(self):
        fb = rapportmodule.bepaalFoutbeleid(None, rapportmodule.leesTaken(NepDagRun([ti('Start_Run', 'failed')])))
        assert fb['uitkomst'] == 'mislukt' and fb['gestopt_door']['taak'] == 'Start_Run'


# ============================================================
# Klasse 5: rapport, JSON en Markdown
# ============================================================

@pytest.fixture
def lezers(monkeypatch):
    """Vervang de lezers van MongoDB en PostgreSQL door vaste waarden."""
    aanroepen = []

    def vast(naam, waarde):
        def lezer(*args, **kwargs):
            aanroepen.append(naam)
            if isinstance(waarde, Exception):
                raise waarde
            return waarde
        monkeypatch.setattr(rapportmodule, naam, lezer)

    vast('leesRegistratieVanRun', [{'pad': '/p/SY001.mdb', 'categorie': 'projecten', 'grootte': 1, 'status': 'verwerkt',
                                    'aantal_records': 12}])
    vast('leesRunBestanden', [])
    vast('leesAfbeeldingProblemen', [])
    vast('leesTabelaantallen', ({'Def_Project': 2, 'Def_Vondst': 9}, {'Glas': 1}))
    vast('leesSamengevoegd', {'Vondst': 1})
    vast('leesVerwerkingsfouten', [])
    vast('leesAnalyseKwaliteit', {'locatiefouten': [], 'onherkende_bestandsnamen': {'aantal': 0, 'voorbeelden': []}})
    vast('leesRijenZonderKey', {})
    return types.SimpleNamespace(aanroepen=aanroepen, vast=vast)


@pytest.mark.unit
class TestRapport:

    def test_json_structuur(self, lezers):
        run = maakRun(tellingen={'load': {'Def_Vondst': {'ingevoegd': 1, 'bijgewerkt': 0, 'verwijderd': 0}}})
        rapport = rapportmodule.verzamelRapport(run, rapportmodule.leesTaken(NepDagRun(TAKEN_GESLAAGD)),
                                                NepDagRun(TAKEN_GESLAAGD), gemaakt_op=T0 + timedelta(minutes=1))
        for sectie in rapportmodule.SECTIES:
            assert sectie in rapport, sectie
        assert rapport['run']['run_id'] == '20261029T100000' and rapport['run']['duur_seconden'] == 55
        assert rapport['run']['profiel'] == 'delft'
        assert rapport['objecttotalen']['tabellen']['Def_Vondst']['samengevoegd'] == 1
        assert rapport['samenvatting']['uitkomst'] == 'geslaagd'
        assert rapport['samenvatting']['objecten']['totaal'] == 11
        assert rapport['fouten_in_rapport'] == []
        # JSON-serialiseerbaar met de tijdstippen als ISO 8601
        tekst = json.dumps(rapport, default=rapportmodule._jsonWaarde)
        assert '"gestart_op": "2026-10-29T10:00:00"' in tekst

    def test_sectie_die_faalt_staat_als_niet_beschikbaar_in_het_rapport(self, lezers):
        lezers.vast('leesTabelaantallen', RuntimeError('postgres weg'))
        rapport = rapportmodule.verzamelRapport(maakRun(), [], None)
        assert rapport['fouten_in_rapport'] == [{'sectie': 'objecttotalen', 'fout': 'RuntimeError: postgres weg'}]
        assert rapport['objecttotalen']['tabellen'] == {}
        assert rapport['bronbestanden']['bestanden'][0]['bestand'] == '/p/SY001.mdb'
        assert rapport['samenvatting']['secties_niet_beschikbaar'] == ['objecttotalen']
        assert 'Niet alle gegevens konden worden verzameld' in rapportmodule.maakMarkdown(rapport)

    def test_laden_leest_geen_bronbestanden(self, lezers):
        rapport = rapportmodule.verzamelRapport(maakRun('laden'), [], None)
        assert 'leesRegistratieVanRun' not in lezers.aanroepen and 'leesVerwerkingsfouten' not in lezers.aanroepen
        assert rapport['bronbestanden']['van_toepassing'] is False
        assert 'alleen laden' in rapportmodule.maakMarkdown(rapport)

    def test_rijen_zonder_key_alleen_na_een_load(self, lezers):
        rapportmodule.verzamelRapport(maakRun(status='mislukt'), [], None)
        assert 'leesRijenZonderKey' not in lezers.aanroepen

    def test_markdown_koppen_ook_bij_lege_secties(self, lezers):
        rapport = rapportmodule.verzamelRapport(None, [], None)
        md = rapportmodule.maakMarkdown(rapport)
        assert md.startswith('# Verwerkingsrapport (geen run-document)')
        for kop in KOPPEN:
            assert f'\n{kop}\n' in md, kop
        assert 'Geen fout heeft de run gestopt.' in md and 'Geen.' in md

    def test_markdown_met_fout_en_tabellen(self, lezers):
        run = maakRun(status='mislukt', meldingen=[
            {'niveau': 'fout', 'stap': 'extractie', 'taak': 'Extract_Group.Controleer_Afbeeldingen',
             'soort': 'afbeeldingen_mislukt', 'melding': 'a | b\nc', 'aantal': 1}])
        taken = rapportmodule.leesTaken(NepDagRun([ti('Extract_Group.Controleer_Afbeeldingen', 'failed', 5)]))
        md = rapportmodule.maakMarkdown(rapportmodule.verzamelRapport(run, taken, NepDagRun([])))
        assert 'De run is gestopt door taak `Extract_Group.Controleer_Afbeeldingen` (stap extractie): a \\| b c' in md
        assert '| extractie | Extract_Group.Controleer_Afbeeldingen | afbeeldingen_mislukt | 1 | a \\| b c |' in md
        assert '| Def_Vondst | 9 |' in md and '| **Totaal** | 11 |' in md
        assert 'Uitkomst: **mislukt**' in md

    @pytest.mark.parametrize("seconden,tekst", [(None, '–'), (12.34, '12,3 s'), (492, '8 min 12 s'), (3900, '1 u 05 min')])
    def test_duur(self, seconden, tekst):
        assert rapportmodule._duur(seconden) == tekst


# ============================================================
# Klasse 6: schrijven en de taak
# ============================================================

@pytest.mark.unit
class TestSchrijven:

    def test_bestandsnaam(self):
        rapport = {'run': {'run_id': '20261029T100000', 'soort': 'volledig'}, 'gemaakt_op': T0 + timedelta(minutes=8)}
        assert rapportmodule.maakBestandsnaam(rapport) == 'verwerkingsrapport_20261029T100000_volledig_20261029T100800'
        zonder = {'run': {'dag_id': 'DAG_Load_Only'}, 'gemaakt_op': T0}
        assert rapportmodule.maakBestandsnaam(zonder) == 'verwerkingsrapport_zonder-run_DAG_Load_Only_20261029T100000'

    def test_rapportmap_en_terugval(self, tmp_path, monkeypatch):
        monkeypatch.setattr(rapportmodule.config, 'AIRFLOW_OUTPUT_RAPPORTEN', str(tmp_path / 'rapporten'))
        assert rapportmodule.bepaalRapportmap() == (str(tmp_path / 'rapporten'), False)
        # Een bestand op de plek van de map: niet te gebruiken, dus de reservemap in de logmap
        (tmp_path / 'bestand').write_text('x')
        monkeypatch.setattr(rapportmodule.config, 'AIRFLOW_OUTPUT_RAPPORTEN', str(tmp_path / 'bestand' / 'rapporten'))
        monkeypatch.setattr(rapportmodule.config, 'AIRFLOW_LOGDIR', str(tmp_path / 'logs'))
        assert rapportmodule.bepaalRapportmap() == (str(tmp_path / 'logs' / 'rapporten'), True)

    def test_schrijven_json_en_markdown(self, tmp_path):
        rapport = {'run': {'run_id': 'r1', 'soort': 'volledig'}, 'gemaakt_op': T0, 'x': T0}
        json_pad, md_pad = rapportmodule.schrijfRapport(rapport, '# kop\n', str(tmp_path))
        assert os.path.basename(json_pad) == 'verwerkingsrapport_r1_volledig_20261029T100000.json'
        assert json.load(open(json_pad))['x'] == '2026-10-29T10:00:00'
        assert open(md_pad).read() == '# kop\n'
        assert sorted(os.listdir(tmp_path)) == sorted([os.path.basename(json_pad), os.path.basename(md_pad)])

    def test_versie_uit_omgeving_of_bestand(self, tmp_path, monkeypatch):
        monkeypatch.setenv('WASSTRAAT_VERSION', '1.2.3')
        assert rapportmodule.leesVersie() == '1.2.3'
        monkeypatch.delenv('WASSTRAAT_VERSION')
        bestand = tmp_path / 'version.env'
        bestand.write_text('# versie\nVERSION=1.1.0\n')
        monkeypatch.setenv('WASSTRAAT_VERSIEBESTAND', str(bestand))
        assert rapportmodule.leesVersie() == '1.1.0'
        monkeypatch.setenv('WASSTRAAT_VERSIEBESTAND', str(tmp_path / 'bestaat_niet'))
        assert rapportmodule.leesVersie() is None


@pytest.fixture
def nep_client(monkeypatch):
    client = NepClient()
    monkeypatch.setattr(verwerkingsrun, '_getClient', lambda: client)
    monkeypatch.setattr(rapportmodule, '_getClient', lambda: client)
    return client


@pytest.mark.unit
class TestTaakVerwerkingsrapport:

    def test_rapport_na_geslaagde_run(self, nep_client, lezers, tmp_path, monkeypatch):
        monkeypatch.setattr(rapportmodule.config, 'AIRFLOW_OUTPUT_RAPPORTEN', str(tmp_path))
        start = verwerkingsrun.nu() - timedelta(minutes=1)
        run_id = verwerkingsrun.startRun('incrementeel', airflow_run_id='manual__1')
        verwerkingsrun.beeindigRun('afgerond')
        eind = types.SimpleNamespace(task_id='End_ETL_incremental')
        rapport_ti = types.SimpleNamespace(task_id='Verwerkingsrapport',
                                           task=types.SimpleNamespace(get_flat_relatives=lambda upstream: [eind]))
        dag_run = NepDagRun(TAKEN_GESLAAGD + [ti('Verwerkingsrapport', 'running', 60), ti('End_ETL_incremental', None, None)],
                            start=start)
        paden = rapportmodule.maakVerwerkingsrapport(dag_run=dag_run, task_instance=rapport_ti)

        rapport = json.load(open(paden['json']))
        assert rapport['run']['run_id'] == run_id and rapport['run']['status'] == 'afgerond'
        assert 'Verwerkingsrapport' not in [t['taak'] for t in rapport['pipeline']['taken']]
        assert 'End_ETL_incremental' not in [t['taak'] for t in rapport['pipeline']['taken']]
        assert open(paden['markdown']).read().startswith(f'# Verwerkingsrapport {run_id}')
        doc = nep_client[verwerkingsrun.config.DB_STAGING][verwerkingsrun.COLL_VERWERKINGSRUNS].find_one({'_id': run_id})
        assert doc['rapport']['json'] == paden['json'] and doc['rapport']['markdown'] == paden['markdown']
        assert doc['rapport']['samenvatting']['uitkomst'] == 'geslaagd' and doc['rapport']['map_terugval'] is False

    def test_rapport_zonder_run_document(self, nep_client, lezers, tmp_path, monkeypatch):
        """Start_Run mislukte (er was al een run actief): rapport met alleen de Airflow-gegevens."""
        monkeypatch.setattr(rapportmodule.config, 'AIRFLOW_OUTPUT_RAPPORTEN', str(tmp_path))
        ander = verwerkingsrun.startRun('incrementeel', airflow_run_id='manual__ander')
        paden = rapportmodule.maakVerwerkingsrapport(dag_run=NepDagRun([ti('Start_Run', 'failed')]))
        rapport = json.load(open(paden['json']))
        assert rapport['run']['run_id'] is None and rapport['foutbeleid']['gestopt_door']['taak'] == 'Start_Run'
        assert 'rapport' not in verwerkingsrun.huidigeRun()  # de andere run blijft ongemoeid
        assert verwerkingsrun.huidigeRun()['run_id'] == ander

    def test_terugval_komt_in_rapport_en_run_document(self, nep_client, lezers, tmp_path, monkeypatch):
        (tmp_path / 'bestand').write_text('x')
        monkeypatch.setattr(rapportmodule.config, 'AIRFLOW_OUTPUT_RAPPORTEN', str(tmp_path / 'bestand' / 'r'))
        monkeypatch.setattr(rapportmodule.config, 'AIRFLOW_LOGDIR', str(tmp_path / 'logs'))
        run_id = verwerkingsrun.startRun('volledig', airflow_run_id='manual__1')
        paden = rapportmodule.maakVerwerkingsrapport(dag_run=NepDagRun([], start=verwerkingsrun.nu() - timedelta(minutes=1)))
        assert paden['json'].startswith(str(tmp_path / 'logs' / 'rapporten'))
        rapport = json.load(open(paden['json']))
        assert [w['soort'] for w in rapport['foutbeleid']['waarschuwingen']] == ['rapport']
        doc = nep_client[verwerkingsrun.config.DB_STAGING][verwerkingsrun.COLL_VERWERKINGSRUNS].find_one({'_id': run_id})
        assert doc['rapport']['map_terugval'] is True


# ============================================================
# Klasse 7: lezers van MongoDB en PostgreSQL
# ============================================================

@pytest.mark.unit
class TestLezers:

    def test_verwerkingsfouten_van_deze_run_gegroepeerd(self, nep_client):
        col = nep_client[rapportmodule.config.DB_ANALYSE][rapportmodule.COLL_PROCESSING_ERRORS]
        col.insert_many([
            {'fase': 'enhance_attributes', 'soort': 'Vondst', 'error_type': 'KeyError', 'error_msg': 'x',
             'original_id': 1, 'timestamp': T0 + timedelta(seconds=5)},
            {'fase': 'enhance_attributes', 'soort': 'Vondst', 'error_type': 'KeyError', 'error_msg': 'y',
             'original_id': 2, 'timestamp': T0 + timedelta(seconds=6)},
            {'fase': 'imagedata', 'soort': 'Foto', 'error_type': 'TypeError', 'error_msg': 'z',
             'original_id': 3, 'timestamp': T0 + timedelta(seconds=7)},
            {'fase': 'enhance_attributes', 'soort': 'Put', 'error_type': 'KeyError', 'error_msg': 'oud',
             'original_id': 4, 'timestamp': T0 - timedelta(days=1)},
        ])
        groepen = rapportmodule.leesVerwerkingsfouten(maakRun())
        assert [(g['fase'], g['soort'], g['aantal']) for g in groepen] == [('enhance_attributes', 'Vondst', 2),
                                                                          ('imagedata', 'Foto', 1)]
        assert groepen[0]['voorbeelden'][0] == {'original_id': '1', 'projectcd': None, 'melding': 'x'}

    def test_analyse_kwaliteit_en_samengevoegd(self, nep_client):
        clean = nep_client[rapportmodule.config.DB_ANALYSE][rapportmodule.config.COLL_ANALYSE_CLEAN]
        run_id = '20261029T100000'
        clean.insert_many([
            {'soort': 'Project', 'projectcd': 'DB1', 'delta_run': run_id,
             'error': {'Error': {'Type': 'Afwijkende locatie', 'Message': 'buiten NL'}}},
            {'soort': 'Bestand', 'fototype': 'N', 'fullFileName': '/p/raar.jpg', 'delta_run': run_id},
            {'soort': 'Bestand', 'fototype': 'N', 'fullFileName': '/p/oud.jpg'},
            {'soort': 'Vondst', 'brondata_count': 2, 'delta_run': run_id},
            {'soort': 'Vondst', 'brondata_count': 3},
            {'soort': 'Vondst', 'brondata_count': 1, 'delta_run': run_id},
        ])
        incrementeel = rapportmodule.leesAnalyseKwaliteit(maakRun())
        assert incrementeel['locatiefouten'] == [{'soort': 'Project', 'type': 'Afwijkende locatie', 'aantal': 1,
                                                  'voorbeelden': [{'projectcd': 'DB1', 'melding': 'buiten NL'}]}]
        assert incrementeel['onherkende_bestandsnamen'] == {'aantal': 1, 'voorbeelden': ['/p/raar.jpg']}
        assert rapportmodule.leesAnalyseKwaliteit(maakRun('volledig'))['onherkende_bestandsnamen']['aantal'] == 2
        assert rapportmodule.leesSamengevoegd(maakRun()) == {'Vondst': 1}
        assert rapportmodule.leesSamengevoegd(maakRun('volledig')) == {'Vondst': 2}

    def test_afbeeldingen_van_deze_run(self, nep_client):
        col = nep_client[rapportmodule.config.DB_FILES][rapportmodule.config.COLL_FILENAMES]
        col.insert_many([{'filename': 'a', 'processed': False, 'fout': 'kapot'},
                         {'filename': 'b', 'processed': True, 'overgeslagen': 'jpg-versie aanwezig', 'verwerkt_op': T0 + timedelta(seconds=1)},
                         {'filename': 'c', 'processed': True, 'overgeslagen': 'jpg-versie aanwezig', 'verwerkt_op': T0 - timedelta(days=1)},
                         {'filename': 'd', 'processed': True, 'verwerkt_op': T0 + timedelta(seconds=1)}])
        assert sorted(a['filename'] for a in rapportmodule.leesAfbeeldingProblemen(maakRun())) == ['a', 'b']
        assert sorted(a['filename'] for a in rapportmodule.leesAfbeeldingProblemen(maakRun('volledig'))) == ['a', 'b', 'c']

    def test_postgres_lezers(self, monkeypatch):
        class Cursor:
            def __init__(self):
                self.resultaat = []

            def execute(self, sql, params=None):
                if 'to_regclass' in sql:
                    bestaat = 'Def_Ontbreekt' not in (params[0] if params else sql)
                    self.resultaat = [(bestaat,)]
                elif sql.startswith('SELECT pad'):
                    self.resultaat = [('/p/a.mdb', 'projecten', 3, 'verwerkt', 7)]
                elif 'information_schema.columns' in sql:
                    self.resultaat = [('Def_Vondst',)]
                elif 'WHERE key IS NULL' in sql:
                    self.resultaat = [(2,)]
                elif 'GROUP BY 1' in sql:
                    self.resultaat = [('Glas', 4)]
                elif sql.startswith('SELECT COUNT(*)'):
                    self.resultaat = [(9,)]

            def fetchone(self):
                return self.resultaat[0]

            def fetchall(self):
                return self.resultaat

        conn = types.SimpleNamespace(cursor=lambda: Cursor(), close=lambda: None)
        monkeypatch.setattr(rapportmodule, '_getPgConnection', lambda: conn)
        assert rapportmodule.leesRegistratieVanRun('r1') == [{'pad': '/p/a.mdb', 'categorie': 'projecten', 'grootte': 3,
                                                               'status': 'verwerkt', 'aantal_records': 7}]
        assert rapportmodule.leesTabelaantallen(['Def_Vondst', 'Def_Ontbreekt', 'Def_Artefact']) == (
            {'Def_Vondst': 9, 'Def_Ontbreekt': None, 'Def_Artefact': 9}, {'Glas': 4})
        assert rapportmodule.leesRijenZonderKey(['Def_Vondst', 'Def_Project']) == {'Def_Vondst': 2}
