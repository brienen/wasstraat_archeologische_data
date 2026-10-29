"""Controles na de extractie (issue 54): Access-databases en afbeeldingen tellen, melden en toetsen.

``importMDB.sh`` slaat een onleesbare Access-database of een tabel die de
export niet aankan over met een regel ``ERROR``/``WARNING`` in zijn log en
eindigt met exit 0, zodat één kapotte database de extractie niet stopt. Tot
issue 54 bleef dat alleen in het log van de taak (en een lege database werd bij
de registratie als verwerkt met 0 records geteld). De taak
``Controleer_Databases`` leest na de extractie de logs van ``importMDB.sh``
(``AIRFLOW_LOGDIR/<collectie>.log``, per run overschreven), telt per categorie
de verwerkte, onleesbare en lege databases en de overgeslagen tabellen, zet de
tellingen in het run-document (``tellingen.extractie``) en meldt ze als
waarschuwing. Zijn meer databases onleesbaar dan de drempel
(``AIRFLOW_MAX_MISLUKTE_DATABASES`` / ``_PCT``), dan is er vermoedelijk iets
structureel mis (bijv. mdbtools) en stopt de run.

``controleerAfbeeldingen`` omhult de bestaande controle van de afbeeldingen
(``image_import.controleerAfbeeldingen``, issue 70) en zet de tellingen en een
melding ook in het run-document van de volledige cyclus.
"""
import os
import re
from datetime import datetime

import pymongo

import shared.config as config
import wasstraat.bronbestanden as bronbestanden
import wasstraat.foutbeleid as foutbeleid
import wasstraat.image_import as image_import
import wasstraat.verwerkingsrun as verwerkingsrun
import logging

logger = logging.getLogger("airflow.task")

# Maximaal aantal bestanden of tabellen per lijst in het run-document (de aantallen tellen alles)
MAX_IN_LIJST = 200

# Regels in het log van importMDB.sh (zie airflow_app/scripts/importMDB.sh)
RE_VERWERKT = re.compile(r"^Processing (.+) file for project .*\.\.\.\s*$")
RE_ONLEESBAAR = re.compile(r"^ERROR: Kan MDB-bestand niet lezen[^:]*: (.+?)\s*$")
RE_TABEL_OVERGESLAGEN = [
    (re.compile(r"^WARNING: Geen kopregel gelezen voor tabel '(.*)' in bestand '(.*)', tabel overgeslagen"),
     'geen kopregel gelezen'),
    (re.compile(r"^ERROR: Kolommen toevoegen gefaald voor tabel '(.*)' in bestand '(.*)', tabel overgeslagen"),
     'kolommen toevoegen mislukt'),
]
RE_MONGOIMPORT = re.compile(r"^ERROR: mongoimport gefaald \(exit (\d+)\) voor tabel '(.*)' in bestand '(.*)'")
RE_LIJST_ONTBREEKT = re.compile(r"^WARNING: Bestand '(.*)' uit lijstbestand bestaat niet, overgeslagen")
# Meldingen zonder gevolgen voor de data (alleen metainformatie) of herhalingen van een andere regel
RE_GENEGEERD = re.compile(r"^(WARNING: mdb-prop gaf geen bruikbare output|WARNING: mongoimport metainfo gefaald|"
                          r"ERROR ENCODING: Alle conversie-pogingen gefaald)")
RE_MELDING = re.compile(r"^(ERROR|WARNING)\b")


def leegLogResultaat():
    """Retourneer een leeg resultaat van leesImportLog."""
    return {'aanwezig': False, 'verwerkt': [], 'onleesbaar': [], 'tabellen_overgeslagen': [],
            'lijst_ontbreekt': [], 'overig': []}


def leesImportLog(pad, sinds=None):
    """Lees het log van importMDB.sh voor één staging-collectie.

    Args:
        pad: pad van het log (AIRFLOW_LOGDIR/<collectie>.log)
        sinds: optioneel naïef UTC-tijdstip; een log dat daarvóór is geschreven
            hoort niet bij deze run en telt niet

    Returns:
        Dict met aanwezig (bool), verwerkt (paden), onleesbaar ({bestand, melding}),
        tabellen_overgeslagen ({bestand, tabel, reden}), lijst_ontbreekt (paden) en
        overig (overige ERROR- en WARNING-regels)
    """
    resultaat = leegLogResultaat()
    if not pad or not os.path.isfile(pad):
        return resultaat
    if sinds is not None and datetime.utcfromtimestamp(os.path.getmtime(pad)) < sinds:
        logger.info(f"Log {pad} is van vóór deze run ({sinds}); niet gelezen.")
        return resultaat
    resultaat['aanwezig'] = True
    with open(pad, encoding='utf-8', errors='replace') as f:
        for regel in f:
            regel = regel.rstrip('\r\n')
            m = RE_VERWERKT.match(regel)
            if m:
                resultaat['verwerkt'].append(m.group(1))
                continue
            m = RE_ONLEESBAAR.match(regel)
            if m:
                resultaat['onleesbaar'].append({'bestand': m.group(1), 'melding': regel})
                continue
            gevonden = False
            for patroon, reden in RE_TABEL_OVERGESLAGEN:
                m = patroon.match(regel)
                if m:
                    resultaat['tabellen_overgeslagen'].append({'bestand': m.group(2), 'tabel': m.group(1), 'reden': reden})
                    gevonden = True
                    break
            if gevonden:
                continue
            m = RE_MONGOIMPORT.match(regel)
            if m:
                resultaat['tabellen_overgeslagen'].append(
                    {'bestand': m.group(3), 'tabel': m.group(2), 'reden': f'mongoimport mislukt (exit {m.group(1)})'})
                continue
            m = RE_LIJST_ONTBREEKT.match(regel)
            if m:
                resultaat['lijst_ontbreekt'].append(m.group(1))
                continue
            if RE_GENEGEERD.match(regel):
                continue
            if RE_MELDING.match(regel):
                resultaat['overig'].append(regel[:500])
    # Een bestand kan meer dan eens voorkomen (bijv. bij een herhaling van de taak): ontdubbelen
    resultaat['verwerkt'] = sorted(set(resultaat['verwerkt']))
    return resultaat


def _bepaalSinds(run, context):
    """Bepaal vanaf wanneer een log bij deze run hoort: de start van de run of van de Airflow-run."""
    if run is not None and run.get('gestart_op'):
        return run['gestart_op']
    dag_run = (context or {}).get('dag_run')
    if dag_run is not None:
        return verwerkingsrun.startVanAirflowRun(dag_run)
    return None


def _begrens(lijst):
    """Begrens een lijst voor het run-document."""
    return lijst[:MAX_IN_LIJST]


def controleerDatabases(incrementeel=False, **context):
    """Taak Controleer_Databases: tel onleesbare en lege Access-databases en overgeslagen tabellen.

    Leest per MDB-categorie het log van importMDB.sh van deze run, telt de
    staging-documenten per verwerkte database (een database zonder documenten
    die wel leesbaar was, is leeg) en schrijft het resultaat in het run-document
    onder tellingen.extractie. Lege databases, overgeslagen tabellen en overige
    meldingen van importMDB.sh zijn waarschuwingen; onleesbare databases ook,
    tot de drempel max(AIRFLOW_MAX_MISLUKTE_DATABASES,
    AIRFLOW_MAX_MISLUKTE_DATABASES_PCT % van de verwerkte databases).

    Args:
        incrementeel: True in de incrementele cyclus (alleen voor het log; de
            logs bevatten in beide cycli precies de databases van deze run)
        context: Airflow-context (voor de start van de Airflow-run zonder run-document)

    Returns:
        Dict met de tellingen (zie tellingen.extractie)

    Raises:
        foutbeleid.CrucialeFout: als meer databases onleesbaar zijn dan de drempel
    """
    run = verwerkingsrun.runVanTaak()
    sinds = _bepaalSinds(run, context)

    per_categorie = {}
    verwerkt, onleesbaar, tabellen, lijst_ontbreekt, overig = [], [], [], [], []
    for categorie, _, collectie in bronbestanden.getMdbCategorieen():
        log = leesImportLog(os.path.join(str(config.AIRFLOW_LOGDIR), f'{collectie}.log'), sinds)
        per_categorie[categorie] = {'log_gelezen': log['aanwezig'], 'verwerkt': len(log['verwerkt']),
                                    'onleesbaar': len(log['onleesbaar']),
                                    'tabellen_overgeslagen': len(log['tabellen_overgeslagen'])}
        verwerkt += [{'bestand': p, 'categorie': categorie} for p in log['verwerkt']]
        onleesbaar += [dict(o, categorie=categorie) for o in log['onleesbaar']]
        tabellen += [dict(t, categorie=categorie) for t in log['tabellen_overgeslagen']]
        lijst_ontbreekt += log['lijst_ontbreekt']
        overig += [{'categorie': categorie, 'regel': r} for r in log['overig']]

    onleesbare_paden = {o['bestand'] for o in onleesbaar}
    aantallen = {}
    te_tellen = [v['bestand'] for v in verwerkt if v['bestand'] not in onleesbare_paden]
    if te_tellen:
        client = pymongo.MongoClient(str(config.MONGO_URI))
        try:
            aantallen = bronbestanden.telStagingRecords(client, paden=te_tellen)
        finally:
            client.close()
    leeg = [v for v in verwerkt if v['bestand'] in te_tellen and not aantallen.get(v['bestand'])]
    for categorie, telling in per_categorie.items():
        telling['leeg'] = len([v for v in leeg if v['categorie'] == categorie])

    tellingen = {
        'databases': len(verwerkt),
        'onleesbaar': len(onleesbaar),
        'leeg': len(leeg),
        'tabellen_overgeslagen': len(tabellen),
        'per_categorie': per_categorie,
        'onleesbare_databases': _begrens(onleesbaar),
        'lege_databases': _begrens(leeg),
        'overgeslagen_tabellen': _begrens(tabellen),
        'niet_gevonden': _begrens(lijst_ontbreekt),
        'overige_meldingen': _begrens(overig),
        # Lijst en geen dict: paden bevatten punten, die in MongoDB-veldnamen lastig zijn
        'records': [{'bestand': p, 'records': aantallen.get(p, 0)} for p in te_tellen[:MAX_IN_LIJST]],
    }
    logger.info(f"Controle Access-databases: {tellingen['databases']} verwerkt, {tellingen['onleesbaar']} onleesbaar, "
                f"{tellingen['leeg']} leeg, {tellingen['tabellen_overgeslagen']} tabellen overgeslagen; "
                f"per categorie {per_categorie}.")

    if leeg:
        msg = (f"{len(leeg)} Access-database(s) leverden geen enkel record op (leeg, of alle tabellen leeg of "
               f"overgeslagen): {[v['bestand'] for v in leeg[:10]]}.")
        logger.warning(msg)
        foutbeleid.meld(foutbeleid.NIVEAU_WAARSCHUWING, foutbeleid.SOORT_DATABASE_LEEG, msg,
                        aantal=len(leeg), details=_begrens(leeg)[:20])
    if tabellen:
        msg = (f"{len(tabellen)} tabel(len) uit Access-databases overgeslagen door een fout in de export: "
               f"{[(t['bestand'], t['tabel'], t['reden']) for t in tabellen[:5]]}.")
        logger.warning(msg)
        foutbeleid.meld(foutbeleid.NIVEAU_WAARSCHUWING, foutbeleid.SOORT_TABEL_OVERGESLAGEN, msg,
                        aantal=len(tabellen), details=_begrens(tabellen)[:20])
    if lijst_ontbreekt or overig:
        msg = (f"importMDB.sh meldde {len(lijst_ontbreekt) + len(overig)} overige waarschuwing(en) of fout(en): "
               f"{(lijst_ontbreekt + [o['regel'] for o in overig])[:5]}.")
        logger.warning(msg)
        foutbeleid.meld(foutbeleid.NIVEAU_WAARSCHUWING, foutbeleid.SOORT_IMPORT_MELDING, msg,
                        aantal=len(lijst_ontbreekt) + len(overig), details=(lijst_ontbreekt + overig)[:20])

    # Eerst de tellingen in het run-document (ook als de drempel hieronder wordt overschreden)
    tellingen.update({
        'drempel': foutbeleid.bepaalDrempel(len(verwerkt), config.AIRFLOW_MAX_MISLUKTE_DATABASES,
                                            config.AIRFLOW_MAX_MISLUKTE_DATABASES_PCT),
        'max_aantal': config.AIRFLOW_MAX_MISLUKTE_DATABASES,
        'max_pct': config.AIRFLOW_MAX_MISLUKTE_DATABASES_PCT,
    })
    tellingen['boven_drempel'] = tellingen['onleesbaar'] > tellingen['drempel']
    foutbeleid.schrijfTelling('extractie', tellingen)
    foutbeleid.toetsDrempel(
        foutbeleid.SOORT_DATABASE_ONLEESBAAR, len(onleesbaar), len(verwerkt),
        config.AIRFLOW_MAX_MISLUKTE_DATABASES, config.AIRFLOW_MAX_MISLUKTE_DATABASES_PCT,
        "Onleesbare Access-databases (mogelijk corrupt; zie het log van de extractie)",
        'AIRFLOW_MAX_MISLUKTE_DATABASES', details=_begrens(onleesbaar)[:20])
    return tellingen


def _tellingenAfbeeldingen(incrementeel, run):
    """Tellingen van de afbeeldingen voor het run-document (de volledige cyclus telt de hele collectie)."""
    if incrementeel:
        return (run.get('tellingen') or {}).get('afbeeldingen')
    max_aantal, max_pct = image_import.leesDrempels()
    client = pymongo.MongoClient(str(config.MONGO_URI))
    try:
        tellingen = image_import.telAfbeeldingStatussen(client[config.DB_FILES][config.COLL_FILENAMES])
    finally:
        client.close()
    niet_verwerkt = tellingen[image_import.STATUS_MISLUKT] + tellingen[image_import.STATUS_ONVERWERKT]
    drempel = image_import.bepaalDrempel(tellingen['totaal'], max_aantal, max_pct)
    tellingen.update({'drempel': drempel, 'max_aantal': max_aantal, 'max_pct': max_pct,
                      'boven_drempel': niet_verwerkt > drempel})
    verwerkingsrun.werkRunBij({'tellingen.afbeeldingen': tellingen}, run_id=run['run_id'])
    return tellingen


def controleerAfbeeldingen(incrementeel=False):
    """Taak Controleer_Afbeeldingen: controle van issue 70, met tellingen en melding in het run-document.

    Roept image_import.controleerAfbeeldingen aan (die faalt boven de drempel).
    Daarna, ook als de controle faalde: in de volledige cyclus komen de
    tellingen in het run-document (tellingen.afbeeldingen; de incrementele
    cyclus deed dat al), en mislukte of onverwerkte bestanden worden een
    waarschuwing (onder de drempel) of een fout (erboven) in de meldingen.

    Args:
        incrementeel: True in de incrementele cyclus

    Raises:
        De fout van image_import.controleerAfbeeldingen (boven de drempel)
    """
    fout = None
    try:
        image_import.controleerAfbeeldingen(incrementeel=incrementeel)
    except Exception as err:
        fout = err

    try:
        run = verwerkingsrun.runVanTaak()
        tellingen = _tellingenAfbeeldingen(incrementeel, run) if run is not None else None
        if tellingen:
            niet_verwerkt = tellingen[image_import.STATUS_MISLUKT] + tellingen[image_import.STATUS_ONVERWERKT]
            if niet_verwerkt:
                niveau = foutbeleid.NIVEAU_FOUT if fout is not None else foutbeleid.NIVEAU_WAARSCHUWING
                msg = (f"{niet_verwerkt} van de {tellingen['totaal']} afbeeldingen en rapporten niet verwerkt "
                       f"({tellingen[image_import.STATUS_MISLUKT]} mislukt, {tellingen[image_import.STATUS_ONVERWERKT]} "
                       f"onverwerkt; drempel {tellingen.get('drempel')}).")
                foutbeleid.meld(niveau, foutbeleid.SOORT_AFBEELDINGEN_MISLUKT, msg, aantal=niet_verwerkt,
                                details=tellingen.get('voorbeelden'), run_id=run['run_id'])
    except Exception as err:
        logger.warning(f"Tellingen van de afbeeldingen niet in het run-document geschreven: {err}")

    if fout is not None:
        raise fout
