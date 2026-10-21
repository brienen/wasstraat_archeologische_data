"""Beheer van het run-document van een verwerkingsrun (incrementeel laden, issue 61).

Elke run van de incrementele cyclus (en de registratiestap aan het eind van de
volledige cyclus) krijgt een run-document in de collectie ``Verwerkingsruns`` in
de staging-database. De taken van de DAG lezen en schrijven dit document via
``huidigeRun()`` in plaats van via XCom, zodat ``airflow dags test`` en
handmatige aanroepen precies hetzelfde werken. Er kan maar één run tegelijk
de status ``actief`` hebben.

Velden van het run-document:

- ``_id`` / ``run_id``: tijdstempel van de start, bijv. ``20261021T143005``
- ``soort``: ``incrementeel`` of ``volledig``
- ``status``: ``actief``, ``afgerond`` of ``mislukt``
- ``airflow_run_id``: run_id van de Airflow DagRun die de run startte
- ``gestart_op``, ``beeindigd_op``: tijdstippen (UTC)
- ``registratie_leeg``: True als ``Def_Bronbestand`` leeg was bij de start
- ``nieuw``, ``gewijzigd``, ``ongewijzigd``, ``verwijderd``: per categorie
  (bijv. ``projecten``, ``afbeeldingen``) een lijst met paden
- ``verwijderde_keys``: per soort een lijst met ``{key, projectcd}``; voor
  Artefact ook ``key_subnr`` en ``artefactsoort``
- ``geraakte_projecten``: projectcodes van verwijderde of vervangen records
- ``tellingen``: aantallen per stap (``delta``, ``opruimen``, ``registratie``)
- ``overgenomen_van``: run_id's van mislukte runs waarvan verwijderde_keys en
  geraakte_projecten zijn overgenomen

De vingerafdrukken per bestand staan niet in het run-document (dat zou bij
~100.000 foto's de documentlimiet van 16 MB overschrijden) maar in de collectie
``Verwerkingsrun_Bestanden``: één document per bestand per run.
"""
from datetime import datetime, timezone

import pymongo
from pymongo.errors import DuplicateKeyError

import shared.config as config
import logging

logger = logging.getLogger("airflow.task")

COLL_VERWERKINGSRUNS = 'Verwerkingsruns'
COLL_RUN_BESTANDEN = 'Verwerkingsrun_Bestanden'

SOORT_INCREMENTEEL = 'incrementeel'
SOORT_VOLLEDIG = 'volledig'
SOORTEN_RUN = [SOORT_INCREMENTEEL, SOORT_VOLLEDIG]

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


def maakRunDocument(run_id, soort, airflow_run_id=None, tijdstip=None):
    """Bouw een nieuw run-document met alle velden uit het ontwerp.

    Args:
        run_id: unieke run-id
        soort: 'incrementeel' of 'volledig'
        airflow_run_id: run_id van de Airflow DagRun (optioneel)
        tijdstip: starttijdstip (standaard nu)

    Returns:
        Dict met het run-document
    """
    return {
        '_id': run_id,
        'run_id': run_id,
        'soort': soort,
        'status': STATUS_ACTIEF,
        'airflow_run_id': airflow_run_id,
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
    """
    laatste_geslaagd = col.find_one({'status': STATUS_AFGEROND}, sort=[('gestart_op', pymongo.DESCENDING)])
    filter_mislukt = {'status': STATUS_MISLUKT, 'soort': SOORT_INCREMENTEEL}
    if laatste_geslaagd:
        filter_mislukt['gestart_op'] = {'$gt': laatste_geslaagd['gestart_op']}

    for mislukt in col.find(filter_mislukt).sort('gestart_op', pymongo.ASCENDING):
        run_doc['verwijderde_keys'] = voegVerwijderdeKeysSamen(run_doc['verwijderde_keys'], mislukt.get('verwijderde_keys'))
        run_doc['geraakte_projecten'] = sorted(set(run_doc['geraakte_projecten']) | set(mislukt.get('geraakte_projecten') or []))
        run_doc['overgenomen_van'].append(mislukt['run_id'])

    if run_doc['overgenomen_van']:
        logger.info(f"Verwijderde sleutels en geraakte projecten overgenomen van mislukte runs: {run_doc['overgenomen_van']}")
    return run_doc


def startRun(soort, airflow_run_id=None):
    """Start een nieuwe verwerkingsrun en maak het run-document aan.

    Args:
        soort: 'incrementeel' of 'volledig'
        airflow_run_id: run_id van de Airflow DagRun (in de DAG via '{{ run_id }}')

    Returns:
        De run_id van de nieuwe run

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
        if actief:
            msg = (f"Er is al een actieve verwerkingsrun ({actief['run_id']}, soort {actief.get('soort')}, "
                   f"gestart op {actief.get('gestart_op')}). Wacht tot die klaar is of zet hem op 'mislukt' "
                   f"(verwerkingsrun.beeindigRun('mislukt')) voordat je een nieuwe run start.")
            logger.error(msg)
            raise Exception(msg)

        tijdstip = nu()
        run_id = maakRunId(tijdstip)
        run_doc = maakRunDocument(run_id, soort, airflow_run_id=airflow_run_id, tijdstip=tijdstip)
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


def markeerRunMislukt(airflow_run_id=None):
    """Zet de actieve run op 'mislukt' (voor de taak met trigger_rule one_failed).

    Alleen de run die door dezelfde Airflow DagRun is gestart wordt gemarkeerd,
    zodat een mislukte Start_Run (omdat er al een andere run actief is) die
    andere run niet afbreekt.

    Args:
        airflow_run_id: run_id van de Airflow DagRun; zonder waarde wordt elke actieve run gemarkeerd
    """
    run = huidigeRun(verplicht=False)
    if run is None:
        logger.info("Geen actieve verwerkingsrun om op 'mislukt' te zetten.")
        return
    if airflow_run_id and run.get('airflow_run_id') != airflow_run_id:
        logger.warning(f"Actieve run {run['run_id']} hoort bij Airflow-run {run.get('airflow_run_id')}, "
                       f"niet bij {airflow_run_id}; status niet gewijzigd.")
        return
    beeindigRun(STATUS_MISLUKT, run_id=run['run_id'], melding=f"Een taak in Airflow-run {airflow_run_id} is mislukt.")


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
