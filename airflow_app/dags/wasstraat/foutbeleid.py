"""Foutbeleid van de Wasstraat (issue 54): welke fouten een run stoppen en welke een waarschuwing geven.

Uitgangspunt: een fout waardoor de data in PostgreSQL onvolledig of onjuist
zou worden is *cruciaal*: de taak faalt, de run krijgt status ``mislukt``
(taak ``Markeer_Run_Mislukt``) en de DAG faalt. Een fout die één bestand, één
tabel of één record raakt, of die alleen de zoekindex betreft, is een
*waarschuwing*: de run gaat door, de fout wordt geteld en komt in het
run-document (``meldingen``) en het verwerkingsrapport. Waar een systematisch
probleem zich als een reeks losse fouten voordoet (veel onleesbare databases,
afbeeldingen of records), geldt een drempel: daarboven wordt de waarschuwing
alsnog cruciaal. Het volledige overzicht per taak staat in
docs/componenten/verwerkingsrapport.md (sectie Foutbeleid).

Onderdelen:

- ``meld()``: schrijf een waarschuwing of fout in de meldingen van het
  run-document van de lopende run;
- ``toetsDrempel()``: tel, meld een waarschuwing of stop boven de drempel
  (``bepaalDrempel``: het grootste van een vast aantal en een percentage);
- ``registreerTaakfout()``: on_failure_callback van alle taken van de cycli;
  legt de foutmelding van een mislukte taak vast (fout bij een cruciale taak,
  waarschuwing bij een Index-taak);
- ``isCrucialeTaak()``, ``isWaarschuwingstaak()``, ``bepaalStap()``: het
  beleid per taak;
- ``controleerBewaking()``: controleer de trigger rules van een DAG tegen dit
  beleid (gebruikt door de integratietest op de DagBag).
"""
import re

import wasstraat.verwerkingsrun as verwerkingsrun
import logging

logger = logging.getLogger("airflow.task")

try:
    from airflow.exceptions import AirflowFailException as _FaalZonderHerhaling
except ImportError:  # unit tests zonder Airflow
    _FaalZonderHerhaling = Exception


class CrucialeFout(_FaalZonderHerhaling):
    """Fout die de run stopt, zonder herhalingen van de taak (de oorzaak verdwijnt niet vanzelf)."""


NIVEAU_FOUT = 'fout'
NIVEAU_WAARSCHUWING = 'waarschuwing'
NIVEAUS = [NIVEAU_FOUT, NIVEAU_WAARSCHUWING]

# Soorten meldingen
SOORT_TAAK_MISLUKT = 'taak_mislukt'
SOORT_DATABASE_ONLEESBAAR = 'database_onleesbaar'
SOORT_DATABASE_LEEG = 'database_leeg'
SOORT_TABEL_OVERGESLAGEN = 'tabel_overgeslagen'
SOORT_IMPORT_MELDING = 'import_melding'
# Transform 1 (issue 89): een tabel die meer dan één harmonisatie-pipeline selecteert, zonder keuze in
# correcties.yml (harmonisatie_voorrang); de voorrangsregel heeft gekozen
SOORT_TABEL_DUBBEL_GESELECTEERD = 'tabel_dubbel_geselecteerd'
# Een regel in de configuratie (harmonisatie-Excel, correcties.yml) die niet te gebruiken is en wordt
# overgeslagen, bijv. een object dat geen soort is of een onbekend type bij rapportcode_prefixen (issue 87)
SOORT_CONFIGURATIE_ONGELDIG = 'configuratie_ongeldig'
# Start_Run: het gemeenteprofiel (WASSTRAAT_GEMEENTE) is niet te laden; de run stopt (issue 87)
SOORT_PROFIEL_ONBEKEND = 'profiel_onbekend'
SOORT_AFBEELDINGEN_MISLUKT = 'afbeeldingen_mislukt'
SOORT_VERWERKINGSFOUTEN = 'verwerkingsfouten'
# Transform 2 (issue 86): artefacten zonder artefactsoort met een materiaalcode waaruit geen artefactsoort
# volgt (wasstraat/artefactsoort_materiaal.py); ze worden geladen als Onbekend
SOORT_ARTEFACTSOORT_NIET_AFGELEID = 'artefactsoort_niet_afgeleid'
SOORT_UNICITEIT_NIET_BEPAALD = 'uniciteit_niet_bepaald'
SOORT_FK_NIET_HERSTELD = 'fk_niet_hersteld'
SOORT_FK_NIET_GEVALIDEERD = 'fk_niet_gevalideerd'
SOORT_SLEUTELS_NIET_STABIEL = 'sleutels_niet_stabiel'
SOORT_AFGELEIDE_VELDEN = 'afgeleide_velden_mislukt'
SOORT_RAPPORT = 'rapport'

# Stap van een taak, op volgorde van controle (eerste treffer telt)
STAPPEN = [
    ('voorbereiding', r'^(Start_Run|Drop_All_Databases|Bepaal_Delta|Opruimen_Oude_Records)$'),
    ('extractie', r'^Extract_Group\.'),
    ('transform1', r'^Transform1_'),
    ('transform2', r'^Transform2_'),
    ('transform3', r'^Transform3_'),
    ('transform5', r'^Transform5_'),
    ('transform4', r'^Transform4_'),
    ('index', r'(^|\.)Index_'),
    ('load', r'(^|\.)(LoadToDatabase_postgres|Load_Upsert)$|^Load_To_Database_And_Inxdex_Group\.'),
    ('registratie', r'^(Registreer_Bronbestanden|Registreer_Run|Rond_Run_Af)$'),
    ('afsluiting', r'^(Markeer_Run_Mislukt|Verwerkingsrapport)$'),
]
STAP_OVERIG = 'overig'
VOLGORDE_STAPPEN = [stap for stap, _ in STAPPEN] + [STAP_OVERIG]

# Taken waarvan een fout een waarschuwing is: de run gaat door en de DAG slaagt. De
# Elasticsearch-index is af te leiden uit PostgreSQL en los opnieuw te bouwen (DAG_Load_Only,
# of de volgende incrementele run); Index_Klaar is een verzameltaak (all_done) en faalt niet.
WAARSCHUWINGSTAKEN = [r'(^|\.)Index_(?!Klaar$)']

# Taken die de run afsluiten en buiten de verwerking staan
AFSLUITINGSTAKEN = ['Markeer_Run_Mislukt', 'Verwerkingsrapport']

# Trigger rules waarbij een fout stroomopwaarts als upstream_failed wordt doorgegeven
DOORGEVENDE_TRIGGER_RULES = ['all_success', 'none_failed', 'none_failed_min_one_success']


# ============================================================
# Beleid per taak
# ============================================================

def bepaalStap(task_id):
    """Bepaal de stap van de pipeline waartoe een taak hoort.

    Args:
        task_id: bijv. 'Extract_Group.Controleer_Afbeeldingen' of 'Index_Def_Project'

    Returns:
        Naam van de stap, bijv. 'extractie', 'transform2', 'load', 'index' of 'overig'
    """
    for stap, patroon in STAPPEN:
        if re.search(patroon, task_id or ''):
            return stap
    return STAP_OVERIG


def isWaarschuwingstaak(task_id):
    """True als een fout in deze taak alleen een waarschuwing is (de run gaat door)."""
    return any(re.search(patroon, task_id or '') for patroon in WAARSCHUWINGSTAKEN)


def isAfsluitingstaak(task_id):
    """True voor de taken die de run afsluiten (Markeer_Run_Mislukt, Verwerkingsrapport)."""
    return (task_id or '').split('.')[-1] in AFSLUITINGSTAKEN


def isCrucialeTaak(task_id):
    """True als een fout in deze taak de run stopt (status mislukt, DAG faalt)."""
    return not isWaarschuwingstaak(task_id) and not isAfsluitingstaak(task_id)


def bepaalDrempel(totaal, max_aantal, max_pct):
    """Bepaal hoeveel fouten nog acceptabel zijn: het grootste van een vast aantal en een percentage.

    Dezelfde regel als bij de afbeeldingen (image_import.bepaalDrempel): bij een
    kleine verzameling telt het vaste aantal, bij een grote het percentage.

    Args:
        totaal: aantal elementen waarover geteld is
        max_aantal: vast aantal
        max_pct: percentage van het totaal (decimaal mag)

    Returns:
        Het hoogste toegestane aantal fouten
    """
    return max(int(max_aantal), int(totaal * float(max_pct) / 100))


# ============================================================
# Meldingen in het run-document
# ============================================================

def maakMelding(niveau, soort, melding, aantal=None, details=None, taak=None, stap=None):
    """Bouw een melding voor het run-document.

    Args:
        niveau: 'fout' of 'waarschuwing'
        soort: soort melding (SOORT_*)
        melding: leesbare tekst
        aantal: optioneel aantal (bestanden, records, constraints)
        details: optionele lijst of dict met de eerste voorbeelden
        taak: task_id (standaard die van de lopende taak)
        stap: stap van de pipeline (standaard afgeleid van de taak)

    Returns:
        Dict met niveau, stap, taak, soort, melding, aantal, details en tijdstip
    """
    if niveau not in NIVEAUS:
        raise ValueError(f"Onbekend niveau '{niveau}'; gebruik een van {NIVEAUS}.")
    if taak is None:
        context = verwerkingsrun.getAirflowContext()
        ti = context.get('task_instance') if context else None
        taak = ti.task_id if ti is not None else None
    return {
        'niveau': niveau,
        'stap': stap if stap else bepaalStap(taak),
        'taak': taak,
        'soort': soort,
        'melding': str(melding)[:verwerkingsrun.MAX_LENGTE_MELDING],
        'aantal': aantal,
        'details': details,
        'tijdstip': verwerkingsrun.nu(),
    }


def meld(niveau, soort, melding, aantal=None, details=None, taak=None, stap=None, run_id=None):
    """Schrijf een waarschuwing of fout in de meldingen van het run-document.

    Zonder run (een DAG zonder run-document, zoals DAG_Transform_Only) gebeurt
    er niets: de aanroeper logt de melding zelf. Een fout bij het schrijven
    wordt gelogd en niet doorgegeven, zodat een melding de verwerking nooit
    stopt.

    Args:
        niveau, soort, melding, aantal, details, taak, stap: zie maakMelding
        run_id: run om bij te werken; standaard de actieve run van deze Airflow-run

    Returns:
        De melding, of None als er geen run is

    Raises:
        ValueError: bij een onbekend niveau (een programmeerfout, ook zonder run)
    """
    if niveau not in NIVEAUS:
        raise ValueError(f"Onbekend niveau '{niveau}'; gebruik een van {NIVEAUS}.")
    try:
        if run_id is None:
            run = verwerkingsrun.runVanTaak()
            if run is None:
                return None
            run_id = run['run_id']
        doc = maakMelding(niveau, soort, melding, aantal=aantal, details=details, taak=taak, stap=stap)
        verwerkingsrun.voegMeldingToe(doc, run_id)
        return doc
    except ValueError:
        raise
    except Exception as err:
        logger.warning(f"Melding ({niveau}, {soort}) niet in het run-document geschreven: {err}")
        return None


def schrijfTelling(pad, waarde):
    """Schrijf een telling in het run-document van de lopende run (tellingen.<pad>), als die er is.

    Een fout bij het schrijven wordt gelogd en niet doorgegeven.

    Args:
        pad: pad onder tellingen, bijv. 'verwerkingsfouten.enhance_attributes'
        waarde: de telling
    """
    try:
        run = verwerkingsrun.runVanTaak()
        if run is not None:
            verwerkingsrun.werkRunBij({f'tellingen.{pad}': waarde}, run_id=run['run_id'])
    except Exception as err:
        logger.warning(f"Telling {pad} niet in het run-document geschreven: {err}")


def toetsDrempel(soort, aantal, totaal, max_aantal, max_pct, omschrijving, instelling, details=None, telling=None):
    """Toets een aantal fouten aan de drempel: waarschuwing eronder, cruciale fout erboven.

    Args:
        soort: soort melding (SOORT_*)
        aantal: aantal fouten
        totaal: aantal elementen waarover geteld is
        max_aantal: vast aantal uit de configuratie
        max_pct: percentage uit de configuratie
        omschrijving: tekst voor de melding, bijv. 'Onleesbare Access-databases'
        instelling: naam van de omgevingsvariabele voor het aantal (het percentage heeft _PCT erachter)
        details: optionele voorbeelden voor de melding
        telling: optioneel pad onder tellingen in het run-document voor de uitkomst
            (ook geschreven als de drempel wordt overschreden)

    Returns:
        Dict met aantal, totaal, drempel, max_aantal, max_pct en boven_drempel

    Raises:
        CrucialeFout: als het aantal boven de drempel ligt
    """
    drempel = bepaalDrempel(totaal, max_aantal, max_pct)
    uitkomst = {'aantal': aantal, 'totaal': totaal, 'drempel': drempel, 'max_aantal': max_aantal,
                'max_pct': max_pct, 'boven_drempel': aantal > drempel}
    if telling:
        schrijfTelling(telling, uitkomst)
    if not aantal:
        return uitkomst
    if uitkomst['boven_drempel']:
        msg = (f"{omschrijving}: {aantal} van {totaal}, meer dan de drempel van {drempel} "
               f"({instelling}={max_aantal}, {instelling}_PCT={max_pct}). Herstel de oorzaak of verhoog de drempel "
               f"als deze fouten bekend en acceptabel zijn.")
        logger.error(msg)
        meld(NIVEAU_FOUT, soort, msg, aantal=aantal, details=details)
        raise CrucialeFout(msg)
    msg = f"{omschrijving}: {aantal} van {totaal}, binnen de drempel van {drempel}."
    logger.warning(msg)
    meld(NIVEAU_WAARSCHUWING, soort, msg, aantal=aantal, details=details)
    return uitkomst


def registreerTaakfout(context):
    """on_failure_callback: leg de foutmelding van een mislukte taak vast in het run-document.

    Een cruciale taak geeft een melding met niveau 'fout', een Index-taak of
    een afsluitingstaak (Verwerkingsrapport, Markeer_Run_Mislukt) een
    waarschuwing: die laatste stoppen de verwerking niet. Heeft de taak zelf al een fout gemeld (bijv. toetsDrempel),
    dan volgt geen tweede melding. Zonder run-document van deze Airflow-run
    (bijv. Start_Run mislukte omdat er al een run actief was) wordt alleen
    gelogd. Een fout in deze callback wordt nooit doorgegeven.

    Args:
        context: Airflow-context van de mislukte taak (met 'exception')
    """
    try:
        ti = context.get('task_instance') or context.get('ti')
        task_id = ti.task_id if ti is not None else None
        dag_run = context.get('dag_run')
        run = None
        if dag_run is not None:
            run = verwerkingsrun.zoekRunVanAirflowRun(dag_run.run_id, sinds=verwerkingsrun.startVanAirflowRun(dag_run))
        if run is None:
            logger.info(f"Taak {task_id} mislukt; geen run-document van deze Airflow-run om de fout in vast te leggen.")
            return
        niveau = NIVEAU_FOUT if isCrucialeTaak(task_id) else NIVEAU_WAARSCHUWING
        if niveau == NIVEAU_FOUT and any(m.get('taak') == task_id and m.get('niveau') == NIVEAU_FOUT
                                         for m in run.get('meldingen') or []):
            return
        fout = context.get('exception')
        tekst = f"{type(fout).__name__}: {fout}" if fout is not None else "Taak mislukt (geen foutmelding)."
        verwerkingsrun.voegMeldingToe(maakMelding(niveau, SOORT_TAAK_MISLUKT, tekst, taak=task_id), run['run_id'])
    except Exception as err:
        logger.warning(f"Fout van de taak niet in het run-document vastgelegd: {err}")


# ============================================================
# Controle van een DAG tegen het beleid
# ============================================================

def _faaltDoorTot(taak, doel_id, taken):
    """Bepaal of een fout van een taak doorwerkt tot een doeltaak.

    Een fout gaat als upstream_failed verder naar stroomafwaartse taken met een
    doorgevende trigger rule (all_success); bij een taak met all_done of
    one_failed stopt hij. Het doel zelf wordt bereikt als het een directe
    stroomafwaartse taak is van een taak op het pad.
    """
    bezocht = set()
    stapel = [taak]
    while stapel:
        huidig = stapel.pop()
        for volgende_id in huidig.downstream_task_ids:
            if volgende_id == doel_id:
                return True
            volgende = taken[volgende_id]
            if volgende_id not in bezocht and str(volgende.trigger_rule) in DOORGEVENDE_TRIGGER_RULES:
                bezocht.add(volgende_id)
                stapel.append(volgende)
    return False


def controleerBewaking(dag, markeer_id='Markeer_Run_Mislukt', rapport_id='Verwerkingsrapport'):
    """Controleer de trigger rules en de bewaking van een DAG tegen het foutbeleid.

    Regels:

    - Markeer_Run_Mislukt heeft trigger rule one_failed en een fout van elke
      cruciale taak werkt erdoor tot die taak;
    - Verwerkingsrapport heeft trigger rule all_done en wacht op alle andere
      taken behalve de eindtaak;
    - er is precies één eindtaak (zonder stroomafwaartse taken), met trigger
      rule all_success, na het rapport; een fout van elke cruciale taak werkt
      erdoor tot de eindtaak (de DAG faalt);
    - een fout van een waarschuwingstaak (Index_*) werkt niet door tot
      Markeer_Run_Mislukt of de eindtaak.

    Taken met een andere trigger rule dan all_success (verzameltaken zoals
    Index_Klaar) falen niet zelf en worden overgeslagen.

    Args:
        dag: Airflow-DAG (of een object met tasks; elke taak heeft task_id,
            trigger_rule, upstream_task_ids en downstream_task_ids)
        markeer_id: task_id van de taak die de run op mislukt zet
        rapport_id: task_id van het verwerkingsrapport

    Returns:
        Lijst met beschrijvingen van overtredingen (leeg als alles klopt)
    """
    taken = {t.task_id: t for t in dag.tasks}
    problemen = []
    markeer = taken.get(markeer_id)
    rapport = taken.get(rapport_id)
    if markeer is None:
        problemen.append(f"Taak {markeer_id} ontbreekt")
    elif str(markeer.trigger_rule) != 'one_failed':
        problemen.append(f"{markeer_id} heeft trigger rule {markeer.trigger_rule}, verwacht one_failed")
    if rapport is None:
        problemen.append(f"Taak {rapport_id} ontbreekt")
    elif str(rapport.trigger_rule) != 'all_done':
        problemen.append(f"{rapport_id} heeft trigger rule {rapport.trigger_rule}, verwacht all_done")

    bladeren = sorted(t.task_id for t in taken.values() if not t.downstream_task_ids)
    if len(bladeren) != 1:
        problemen.append(f"Verwacht precies één eindtaak, gevonden: {bladeren}")
        return problemen
    eind = taken[bladeren[0]]
    if str(eind.trigger_rule) != 'all_success':
        problemen.append(f"Eindtaak {eind.task_id} heeft trigger rule {eind.trigger_rule}, verwacht all_success")
    if rapport is not None:
        if rapport_id not in eind.upstream_task_ids:
            problemen.append(f"Eindtaak {eind.task_id} hangt niet af van {rapport_id}")
        ontbrekend = sorted(set(taken) - {rapport_id, eind.task_id} - set(rapport.upstream_task_ids))
        if ontbrekend:
            problemen.append(f"{rapport_id} wacht niet op: {ontbrekend}")

    for task_id, taak in sorted(taken.items()):
        if task_id in (markeer_id, rapport_id, eind.task_id) or str(taak.trigger_rule) != 'all_success':
            continue
        naar_markeer = markeer is not None and _faaltDoorTot(taak, markeer_id, taken)
        naar_eind = _faaltDoorTot(taak, eind.task_id, taken)
        if isWaarschuwingstaak(task_id):
            if naar_markeer:
                problemen.append(f"Een fout in waarschuwingstaak {task_id} zet de run op mislukt")
            if naar_eind:
                problemen.append(f"Een fout in waarschuwingstaak {task_id} laat de DAG falen")
        elif isCrucialeTaak(task_id):
            if markeer is not None and not naar_markeer:
                problemen.append(f"Cruciale taak {task_id} wordt niet bewaakt door {markeer_id}")
            if not naar_eind:
                problemen.append(f"Een fout in cruciale taak {task_id} laat de DAG niet falen")
    return problemen
