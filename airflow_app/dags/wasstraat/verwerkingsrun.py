"""Beheer van het run-document van een verwerkingsrun (incrementeel laden, issue 61).

Elke run van de incrementele cyclus, de volledige cyclus en ``DAG_Load_Only``
krijgt een run-document in de collectie ``Verwerkingsruns`` in de
staging-database (sinds issue 54 maakt de volledige cyclus het aan het begin
aan, met de taak ``Start_Run``; daarvoor alleen aan het eind, bij de
registratie van de bronbestanden). De taken van de DAG lezen en schrijven dit
document via ``huidigeRun()`` in plaats van via XCom, zodat ``airflow dags
test`` en handmatige aanroepen precies hetzelfde werken. Er kan maar één run
tegelijk de status ``actief`` hebben. De volledige cyclus laat de collectie
staan als hij de staging-database leegt, zodat de geschiedenis van runs (en de
verwerkingsrapporten, issue 62) bewaard blijft.

Velden van het run-document:

- ``_id`` / ``run_id``: tijdstempel van de start, bijv. ``20261021T143005``
- ``soort``: ``incrementeel``, ``volledig`` of ``laden`` (``DAG_Load_Only``)
- ``status``: ``actief``, ``afgerond`` of ``mislukt``
- ``airflow_run_id``: run_id van de Airflow DagRun die de run startte
- ``dag_id``: de DAG van die DagRun (als bekend)
- ``gestart_op``, ``beeindigd_op``: tijdstippen (UTC)
- ``registratie_leeg``: True als ``Def_Bronbestand`` leeg was bij de start
- ``nieuw``, ``gewijzigd``, ``ongewijzigd``, ``verwijderd``: per categorie
  (bijv. ``projecten``, ``afbeeldingen``) een lijst met paden
- ``verwijderde_keys``: per soort een lijst met ``{key, projectcd}``; voor
  Artefact ook ``key_subnr`` en ``artefactsoort``
- ``geraakte_projecten``: projectcodes van verwijderde of vervangen records
- ``tellingen``: aantallen per stap (``delta``, ``opruimen``, ``registratie``,
  ``extractie``, ``afbeeldingen``, ``transform``, ``load`` enz.)
- ``overgenomen_van``: run_id's van mislukte runs waarvan verwijderde_keys en
  geraakte_projecten zijn overgenomen
- ``meldingen`` (issue 54): waarschuwingen en fouten per stap, elk met
  ``niveau`` (``waarschuwing`` of ``fout``), ``stap``, ``taak``, ``soort``,
  ``melding``, ``aantal``, ``details`` en ``tijdstip`` (zie wasstraat.foutbeleid)
- ``rapport`` (issue 62): paden en samenvatting van het verwerkingsrapport

De vingerafdrukken per bestand staan niet in het run-document (dat zou bij
~100.000 foto's de documentlimiet van 16 MB overschrijden) maar in de collectie
``Verwerkingsrun_Bestanden``: één document per bestand per run.
"""
from datetime import datetime, timedelta, timezone

import pymongo
from pymongo.errors import DuplicateKeyError

import shared.config as config
import logging

logger = logging.getLogger("airflow.task")

COLL_VERWERKINGSRUNS = 'Verwerkingsruns'
COLL_RUN_BESTANDEN = 'Verwerkingsrun_Bestanden'

SOORT_INCREMENTEEL = 'incrementeel'
SOORT_VOLLEDIG = 'volledig'
SOORT_LADEN = 'laden'
SOORTEN_RUN = [SOORT_INCREMENTEEL, SOORT_VOLLEDIG, SOORT_LADEN]

# Maximaal aantal meldingen per run-document (de eerste blijven bewaard) en hun lengte
MAX_MELDINGEN = 500
MAX_LENGTE_MELDING = 2000

STATUS_ACTIEF = 'actief'
STATUS_AFGEROND = 'afgerond'
STATUS_MISLUKT = 'mislukt'

STATUS_NIEUW = 'nieuw'
STATUS_GEWIJZIGD = 'gewijzigd'
STATUS_ONGEWIJZIGD = 'ongewijzigd'
STATUS_VERWIJDERD = 'verwijderd'
STATUSSEN_BESTAND = [STATUS_NIEUW, STATUS_GEWIJZIGD, STATUS_ONGEWIJZIGD, STATUS_VERWIJDERD]


def nu():
    """Retourneer het huidige tijdstip in UTC (zonder tijdzone, zoals pymongo het teruggeeft)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def maakRunId(tijdstip=None):
    """Maak een run_id op basis van een tijdstempel.

    Args:
        tijdstip: datetime; standaard het huidige tijdstip

    Returns:
        String in de vorm ``JJJJMMDDTuummss``, bijv. ``20261021T143005``
    """
    tijdstip = tijdstip if tijdstip else nu()
    return tijdstip.strftime('%Y%m%dT%H%M%S')


def _getClient():
    """Maak een MongoClient op basis van de configuratie."""
    return pymongo.MongoClient(str(config.MONGO_URI))


def getRunCollectie(client):
    """Retourneer de collectie met run-documenten en zorg voor de indexen.

    De partiële unieke index op ``status`` (alleen voor ``actief``) garandeert
    dat er nooit twee actieve runs tegelijk zijn, ook niet bij gelijktijdige starts.
    """
    col = client[str(config.DB_STAGING)][COLL_VERWERKINGSRUNS]
    col.create_index([("status", pymongo.ASCENDING)], name='idx_een_actieve_run', unique=True,
                     partialFilterExpression={'status': STATUS_ACTIEF})
    return col


def getRunBestandenCollectie(client):
    """Retourneer de collectie met de vingerafdrukken per bestand per run."""
    col = client[str(config.DB_STAGING)][COLL_RUN_BESTANDEN]
    col.create_index([("run_id", pymongo.ASCENDING), ("status", pymongo.ASCENDING)], name='idx_run_status')
    return col


def maakRunDocument(run_id, soort, airflow_run_id=None, tijdstip=None, dag_id=None):
    """Bouw een nieuw run-document met alle velden uit het ontwerp.

    Args:
        run_id: unieke run-id
        soort: 'incrementeel', 'volledig' of 'laden'
        airflow_run_id: run_id van de Airflow DagRun (optioneel)
        tijdstip: starttijdstip (standaard nu)
        dag_id: de DAG van de Airflow DagRun (optioneel)

    Returns:
        Dict met het run-document
    """
    return {
        '_id': run_id,
        'run_id': run_id,
        'soort': soort,
        'status': STATUS_ACTIEF,
        'airflow_run_id': airflow_run_id,
        'dag_id': dag_id,
        'meldingen': [],
        'gestart_op': tijdstip if tijdstip else nu(),
        'beeindigd_op': None,
        'registratie_leeg': None,
        STATUS_NIEUW: {},
        STATUS_GEWIJZIGD: {},
        STATUS_ONGEWIJZIGD: {},
        STATUS_VERWIJDERD: {},
        'verwijderde_keys': {},
        'geraakte_projecten': [],
        'tellingen': {},
        'overgenomen_van': [],
        'melding': None,
    }


def sleutelVanEntry(entry):
    """Retourneer een hashbare sleutel voor een entry uit verwijderde_keys (voor ontdubbelen)."""
    return (entry.get('key'), entry.get('projectcd'), entry.get('key_subnr'), entry.get('artefactsoort'))


def voegVerwijderdeKeysSamen(bestaand, nieuw):
    """Voeg twee verwijderde_keys-structuren ({soort: [entry]}) samen zonder dubbelingen.

    Args:
        bestaand: dict soort -> lijst entries
        nieuw: dict soort -> lijst entries

    Returns:
        Nieuwe dict soort -> lijst entries
    """
    resultaat = {}
    for bron in [bestaand or {}, nieuw or {}]:
        for soort, entries in bron.items():
            lst = resultaat.setdefault(soort, [])
            gezien = {sleutelVanEntry(e) for e in lst}
            for entry in entries:
                sleutel = sleutelVanEntry(entry)
                if sleutel not in gezien:
                    gezien.add(sleutel)
                    lst.append(entry)
    return resultaat


def _neemOverVanMislukteRuns(col, run_doc):
    """Neem verwijderde_keys en geraakte_projecten over van mislukte runs sinds de laatste geslaagde run.

    Als een eerdere run mislukte nadat Opruimen_Oude_Records al documenten uit
    Single_Store had verwijderd, staan die sleutels alleen nog in het run-document
    van die mislukte run. Zonder overname zou een volgende run ze niet meer
    opnieuw samenvoegen.

    Alleen runs na de laatste geslaagde incrementele of volledige run tellen, en
    na de start van de laatste volledige cyclus (ook een mislukte): die leegt
    MongoDB, dus sleutels van daarvóór zeggen niets meer. Sinds issue 54 blijven
    run-documenten over een volledige cyclus heen bewaard; runs van
    ``DAG_Load_Only`` (soort laden) veranderen MongoDB niet en tellen niet mee.
    """
    grenzen = []
    laatste_geslaagd = col.find_one({'status': STATUS_AFGEROND, 'soort': {'$in': [SOORT_INCREMENTEEL, SOORT_VOLLEDIG]}},
                                    sort=[('gestart_op', pymongo.DESCENDING)])
    if laatste_geslaagd:
        grenzen.append(laatste_geslaagd['gestart_op'])
    laatste_volledig = col.find_one({'soort': SOORT_VOLLEDIG}, sort=[('gestart_op', pymongo.DESCENDING)])
    if laatste_volledig:
        grenzen.append(laatste_volledig['gestart_op'])
    filter_mislukt = {'status': STATUS_MISLUKT, 'soort': SOORT_INCREMENTEEL}
    if grenzen:
        filter_mislukt['gestart_op'] = {'$gt': max(grenzen)}

    for mislukt in col.find(filter_mislukt).sort('gestart_op', pymongo.ASCENDING):
        run_doc['verwijderde_keys'] = voegVerwijderdeKeysSamen(run_doc['verwijderde_keys'], mislukt.get('verwijderde_keys'))
        run_doc['geraakte_projecten'] = sorted(set(run_doc['geraakte_projecten']) | set(mislukt.get('geraakte_projecten') or []))
        run_doc['overgenomen_van'].append(mislukt['run_id'])

    if run_doc['overgenomen_van']:
        logger.info(f"Verwijderde sleutels en geraakte projecten overgenomen van mislukte runs: {run_doc['overgenomen_van']}")
    return run_doc


def startRun(soort, airflow_run_id=None, dag_id=None):
    """Start een nieuwe verwerkingsrun en maak het run-document aan.

    Sluit aan bij een lopende volledige cyclus: wordt een run van soort
    'volledig' gestart zonder airflow_run_id (zoals door
    bronbestanden.registreerVolledigeCyclus aan het eind van de volledige
    cyclus) terwijl er een actieve run van soort 'volledig' is, dan wordt de
    run_id van die run teruggegeven in plaats van een fout. Sinds issue 54
    start de volledige cyclus zijn run-document al aan het begin (Start_Run).

    Args:
        soort: 'incrementeel', 'volledig' of 'laden'
        airflow_run_id: run_id van de Airflow DagRun (in de DAG via '{{ run_id }}')
        dag_id: de DAG van die DagRun (in de DAG via '{{ dag.dag_id }}')

    Returns:
        De run_id van de nieuwe (of lopende volledige) run

    Raises:
        Exception: bij een onbekende soort of als er al een actieve run is
    """
    if soort not in SOORTEN_RUN:
        msg = f"Onbekende soort run '{soort}'. Gebruik een van {SOORTEN_RUN}."
        logger.error(msg)
        raise Exception(msg)

    myclient = _getClient()
    try:
        col = getRunCollectie(myclient)
        actief = col.find_one({'status': STATUS_ACTIEF})
        if actief and soort == SOORT_VOLLEDIG and airflow_run_id is None and actief.get('soort') == SOORT_VOLLEDIG:
            logger.info(f"Aangesloten bij de lopende volledige cyclus {actief['run_id']} "
                        f"(Airflow-run {actief.get('airflow_run_id')}).")
            return actief['run_id']
        if actief:
            msg = (f"Er is al een actieve verwerkingsrun ({actief['run_id']}, soort {actief.get('soort')}, "
                   f"gestart op {actief.get('gestart_op')}). Wacht tot die klaar is of zet hem op 'mislukt' "
                   f"(verwerkingsrun.beeindigRun('mislukt')) voordat je een nieuwe run start.")
            logger.error(msg)
            raise Exception(msg)

        tijdstip = nu()
        run_id = maakRunId(tijdstip)
        run_doc = maakRunDocument(run_id, soort, airflow_run_id=airflow_run_id, tijdstip=tijdstip, dag_id=dag_id)
        if soort == SOORT_INCREMENTEEL:
            run_doc = _neemOverVanMislukteRuns(col, run_doc)

        # Bij een botsing van run_id's (twee starts binnen dezelfde seconde) een volgnummer toevoegen
        volgnummer = 1
        while True:
            try:
                col.insert_one(run_doc)
                break
            except DuplicateKeyError as err:
                if col.find_one({'status': STATUS_ACTIEF}):
                    msg = f"Er is al een actieve verwerkingsrun; run {run_id} kan niet starten: {err}"
                    logger.error(msg)
                    raise Exception(msg) from err
                volgnummer += 1
                run_doc['_id'] = run_doc['run_id'] = f"{run_id}_{volgnummer}"

        # Vingerafdrukken van eerdere runs zijn niet meer nodig
        getRunBestandenCollectie(myclient).delete_many({'run_id': {'$ne': run_doc['run_id']}})

        logger.info(f"Verwerkingsrun {run_doc['run_id']} (soort {soort}) gestart.")
        return run_doc['run_id']
    finally:
        myclient.close()


def startRunEnLaadProfiel(soort, airflow_run_id=None, dag_id=None):
    """Taak Start_Run: start de run (startRun) en laad het gemeenteprofiel (issue 87).

    Een onbekende WASSTRAAT_GEMEENTE liet tot issue 87 pas Transform 1
    (ParseFotobestanden) of Transform 2 falen, met een verwerkingsfout per
    document, na een extractie die uren kan duren. Nu stopt de run bij de
    eerste taak: de fout komt als melding (niveau fout, soort profiel_onbekend)
    in het run-document, de run krijgt status mislukt en de taak faalt als
    cruciale fout (foutbeleid.CrucialeFout, zonder herhalingen). Is er al een
    run actief, dan faalt startRun zoals voorheen en wordt het profiel niet
    geladen.

    Args:
        soort: 'incrementeel', 'volledig' of 'laden'
        airflow_run_id: run_id van de Airflow DagRun (in de DAG via '{{ run_id }}')
        dag_id: de DAG van die DagRun (in de DAG via '{{ dag.dag_id }}')

    Returns:
        De run_id van de nieuwe run

    Raises:
        foutbeleid.CrucialeFout: als het gemeenteprofiel niet te laden is
    """
    # Hier geïmporteerd: foutbeleid importeert deze module
    import wasstraat.foutbeleid as foutbeleid
    from wasstraat.profielen import get_profiel

    run_id = startRun(soort, airflow_run_id=airflow_run_id, dag_id=dag_id)
    try:
        profiel = get_profiel()
    except Exception as err:
        msg = (f"Het gemeenteprofiel is niet te laden: {err} Stel WASSTRAAT_GEMEENTE in op een bekend profiel "
               f"(zie docs/componenten/gemeenteprofielen.md) en start de run opnieuw; er is nog niets verwerkt.")
        logger.error(msg)
        foutbeleid.meld(foutbeleid.NIVEAU_FOUT, foutbeleid.SOORT_PROFIEL_ONBEKEND, msg, taak='Start_Run',
                        run_id=run_id)
        beeindigRun(STATUS_MISLUKT, run_id=run_id, melding=msg)
        raise foutbeleid.CrucialeFout(msg) from err
    logger.info(f"Verwerkingsrun {run_id} gebruikt gemeenteprofiel {profiel.naam}.")
    return run_id


def huidigeRun(verplicht=True):
    """Retourneer het run-document van de actieve run.

    Args:
        verplicht: als True wordt een fout gegeven als er geen actieve run is

    Returns:
        Het run-document, of None als er geen actieve run is en verplicht False is

    Raises:
        Exception: als er geen actieve run is en verplicht True is
    """
    myclient = _getClient()
    try:
        run = getRunCollectie(myclient).find_one({'status': STATUS_ACTIEF})
    finally:
        myclient.close()

    if run is None and verplicht:
        msg = "Geen actieve verwerkingsrun gevonden. Start eerst een run met de taak Start_Run (verwerkingsrun.startRun)."
        logger.error(msg)
        raise Exception(msg)
    return run


def werkRunBij(velden, run_id=None):
    """Werk velden van het run-document bij met $set.

    Args:
        velden: dict met veldnamen (ook met punten, bijv. 'tellingen.delta') en waarden
        run_id: run om bij te werken; standaard de actieve run
    """
    run_id = run_id if run_id else huidigeRun()['run_id']
    myclient = _getClient()
    try:
        result = getRunCollectie(myclient).update_one({'_id': run_id}, {'$set': velden})
        if result.matched_count == 0:
            msg = f"Run-document {run_id} niet gevonden bij het bijwerken van {list(velden.keys())}."
            logger.error(msg)
            raise Exception(msg)
    finally:
        myclient.close()


def beeindigRun(status, run_id=None, melding=None):
    """Beëindig een run door de status en het eindtijdstip te zetten.

    Args:
        status: 'afgerond' of 'mislukt'
        run_id: run om te beëindigen; standaard de actieve run
        melding: optionele toelichting (bijv. een foutmelding)
    """
    if status not in [STATUS_AFGEROND, STATUS_MISLUKT]:
        msg = f"Ongeldige eindstatus '{status}'. Gebruik '{STATUS_AFGEROND}' of '{STATUS_MISLUKT}'."
        logger.error(msg)
        raise Exception(msg)

    velden = {'status': status, 'beeindigd_op': nu()}
    if melding:
        velden['melding'] = melding
    run_id = run_id if run_id else huidigeRun()['run_id']
    werkRunBij(velden, run_id=run_id)
    logger.info(f"Verwerkingsrun {run_id} beëindigd met status {status}.")


def getMislukteTaken(context):
    """Retourneer de task_id's van de mislukte taken (status failed) van de lopende Airflow DagRun.

    Args:
        context: Airflow-context van een taak (met 'dag_run'); mag leeg zijn

    Returns:
        Gesorteerde lijst met task_id's (leeg zonder context)
    """
    dag_run = (context or {}).get('dag_run')
    if dag_run is None:
        return []
    try:
        return sorted(ti.task_id for ti in dag_run.get_task_instances() if ti.state == 'failed')
    except Exception as err:
        logger.warning(f"Mislukte taken van de Airflow-run niet gelezen: {err}")
        return []


def markeerRunMislukt(airflow_run_id=None, **context):
    """Zet de actieve run op 'mislukt' (voor de taak met trigger_rule one_failed).

    Alleen de run die door dezelfde Airflow DagRun is gestart wordt gemarkeerd,
    zodat een mislukte Start_Run (omdat er al een andere run actief is) die
    andere run niet afbreekt. De melding noemt de mislukte taken (issue 54); de
    foutmelding per taak staat in de meldingen van het run-document
    (foutbeleid.registreerTaakfout).

    Args:
        airflow_run_id: run_id van de Airflow DagRun; zonder waarde wordt elke actieve run gemarkeerd
        context: Airflow-context (PythonOperator geeft die mee); gebruikt voor de mislukte taken
    """
    run = huidigeRun(verplicht=False)
    if run is None:
        logger.info("Geen actieve verwerkingsrun om op 'mislukt' te zetten.")
        return
    if airflow_run_id and run.get('airflow_run_id') != airflow_run_id:
        logger.warning(f"Actieve run {run['run_id']} hoort bij Airflow-run {run.get('airflow_run_id')}, "
                       f"niet bij {airflow_run_id}; status niet gewijzigd.")
        return
    mislukt = getMislukteTaken(context)
    if mislukt:
        melding = f"Mislukte taak in Airflow-run {airflow_run_id}: {', '.join(mislukt)}."
    else:
        melding = f"Een taak in Airflow-run {airflow_run_id} is mislukt."
    beeindigRun(STATUS_MISLUKT, run_id=run['run_id'], melding=melding)


def rondRunAf(airflow_run_id=None):
    """Zet de actieve run van deze Airflow-run op 'afgerond' (taak Rond_Run_Af van DAG_Load_Only).

    De volledige en de incrementele cyclus ronden hun run af in de taak die de
    bronbestanden registreert; DAG_Load_Only registreert niets.

    Args:
        airflow_run_id: run_id van de Airflow DagRun; een actieve run van een andere Airflow-run blijft ongemoeid
    """
    run = huidigeRun(verplicht=False)
    if run is None or (airflow_run_id and run.get('airflow_run_id') != airflow_run_id):
        logger.warning(f"Geen actieve verwerkingsrun van Airflow-run {airflow_run_id} om af te ronden.")
        return
    beeindigRun(STATUS_AFGEROND, run_id=run['run_id'])


def _naiefUtc(tijdstip):
    """Zet een (tijdzonebewust) tijdstip om naar een naïef UTC-tijdstip zoals pymongo het teruggeeft."""
    if tijdstip is None:
        return None
    if tijdstip.tzinfo is not None:
        tijdstip = tijdstip.astimezone(timezone.utc)
    return datetime(tijdstip.year, tijdstip.month, tijdstip.day, tijdstip.hour, tijdstip.minute,
                    tijdstip.second, tijdstip.microsecond)


def startVanAirflowRun(dag_run):
    """Bepaal de start van een Airflow DagRun: het vroegste tijdstip van zijn taakinstanties.

    ``airflow dags test <dag> <datum>`` geeft de DagRun als start_date de
    logische datum (bijv. 2026-01-01) en bij elke aanroep dezelfde run_id; de
    taakinstanties van een vorige aanroep worden dan verwijderd. Het vroegste
    tijdstip van de taken is daarom de betrouwbare grens om runs van eerdere
    aanroepen uit te sluiten. ``airflow dags test`` legt van een taak alleen
    het einde vast (start_date blijft leeg); dan telt het einde. Zonder taken
    met een tijdstip geldt start_date van de DagRun.

    Args:
        dag_run: Airflow DagRun

    Returns:
        Naïef UTC-tijdstip, of None
    """
    starts = []
    try:
        starts = [_naiefUtc(ti.start_date or ti.end_date) for ti in dag_run.get_task_instances()
                  if (ti.start_date or ti.end_date) is not None]
    except Exception as err:
        logger.warning(f"Taakinstanties van de Airflow-run niet gelezen: {err}")
    if starts:
        return min(starts)
    return _naiefUtc(getattr(dag_run, 'start_date', None))


def zoekRunVanAirflowRun(airflow_run_id, sinds=None):
    """Zoek het run-document dat door een Airflow DagRun is gestart, ook als de run al is beëindigd.

    ``airflow dags test`` met dezelfde datum geeft elke keer dezelfde Airflow
    run_id; daarom telt alleen een run die is gestart na ``sinds`` (de start van
    de DagRun) en wint de laatste.

    Args:
        airflow_run_id: run_id van de Airflow DagRun
        sinds: optioneel starttijdstip van de DagRun (mag tijdzonebewust zijn)

    Returns:
        Het run-document, of None
    """
    if not airflow_run_id:
        return None
    filt = {'airflow_run_id': airflow_run_id}
    if sinds is not None:
        # Een seconde marge: MongoDB bewaart tijdstippen in milliseconden
        filt['gestart_op'] = {'$gte': _naiefUtc(sinds) - timedelta(seconds=1)}
    myclient = _getClient()
    try:
        return getRunCollectie(myclient).find_one(filt, sort=[('gestart_op', pymongo.DESCENDING)])
    finally:
        myclient.close()


def getAirflowContext():
    """Retourneer de Airflow-context van de lopende taak, of None (buiten een taak of zonder Airflow)."""
    try:
        from airflow.operators.python import get_current_context
    except ImportError:
        return None
    try:
        return get_current_context()
    except Exception:
        return None


def runVanTaak():
    """Retourneer het run-document van de actieve run, als die bij de lopende Airflow-run hoort.

    Een taak uit een DAG zonder eigen run (bijv. DAG_Transform_Load_Only) mag
    niet schrijven in de run van een andere DAG die toevallig actief is. Is de
    Airflow-run niet te bepalen (buiten Airflow, unit tests), dan geldt de
    actieve run.

    Returns:
        Het run-document, of None
    """
    run = huidigeRun(verplicht=False)
    if run is None:
        return None
    context = getAirflowContext()
    dag_run = context.get('dag_run') if context else None
    if dag_run is not None and run.get('airflow_run_id') and run.get('airflow_run_id') != dag_run.run_id:
        return None
    return run


def voegMeldingToe(melding, run_id):
    """Voeg een melding toe aan de lijst meldingen van een run-document ($push).

    De lijst wordt begrensd op MAX_MELDINGEN (de eerste blijven bewaard) en de
    tekst op MAX_LENGTE_MELDING tekens. Zie foutbeleid.meld voor de opbouw.

    Args:
        melding: dict met niveau, stap, taak, soort, melding, aantal, details en tijdstip
        run_id: run om bij te werken
    """
    melding = dict(melding)
    melding['melding'] = str(melding.get('melding') or '')[:MAX_LENGTE_MELDING]
    myclient = _getClient()
    try:
        getRunCollectie(myclient).update_one(
            {'_id': run_id}, {'$push': {'meldingen': {'$each': [melding], '$slice': MAX_MELDINGEN}}})
    finally:
        myclient.close()


def getDeltaPaden(categorie, statussen=None, run=None):
    """Retourneer de paden van een categorie met de gevraagde statussen uit het run-document.

    Args:
        categorie: bijv. 'afbeeldingen' of 'referentietabellen'
        statussen: lijst statussen; standaard nieuw en gewijzigd
        run: run-document; standaard de actieve run

    Returns:
        Gesorteerde lijst met paden
    """
    statussen = statussen if statussen else [STATUS_NIEUW, STATUS_GEWIJZIGD]
    run = run if run else huidigeRun()
    paden = set()
    for status in statussen:
        paden.update((run.get(status) or {}).get(categorie, []))
    return sorted(paden)


def isInDelta(pad, categorie, statussen=None, run=None):
    """Bepaal of een pad in de delta van de actieve run zit (standaard nieuw of gewijzigd)."""
    return pad in getDeltaPaden(categorie, statussen=statussen, run=run)
