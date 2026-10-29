"""Taken rond het run-document: start, bewaking, afronding en verwerkingsrapport (issues 54 en 62).

Gebruikt door de volledige cyclus, de incrementele cyclus en DAG_Load_Only,
zodat de drie DAG's dezelfde opbouw hebben:

    Start_Run → ... verwerking ... → (registratie of Rond_Run_Af) → eindtaak
    bewaakte taken → Markeer_Run_Mislukt (one_failed)
    alle taken → Verwerkingsrapport (all_done) → eindtaak (all_success)

De eindtaak is de enige taak zonder stroomafwaartse taken en bepaalt de
eindstatus van de DAG: hij faalt als een cruciale taak faalde (via
upstream_failed) of als het rapport niet gemaakt kon worden, en slaagt als
alleen een waarschuwingstaak (Index_*) faalde. Het rapport wacht op álle
andere taken, zodat het ook na een fout pas draait als de rest klaar is.
"""
from airflow.operators.python import PythonOperator
from airflow.utils.trigger_rule import TriggerRule

import wasstraat.foutbeleid as foutbeleid
import wasstraat.verwerkingsrun as verwerkingsrun
import wasstraat.verwerkingsrapport as verwerkingsrapport


def getDefaultArgs():
    """Standaardargumenten voor de taken: leg de foutmelding van een mislukte taak vast in het run-document."""
    return {'on_failure_callback': foutbeleid.registreerTaakfout}


def maakStartRun(soort):
    """Taak Start_Run: maak het run-document aan (faalt als er al een run actief is)."""
    return PythonOperator(
        task_id='Start_Run',
        python_callable=verwerkingsrun.startRun,
        op_kwargs={'soort': soort, 'airflow_run_id': '{{ run_id }}', 'dag_id': '{{ dag.dag_id }}'},
    )


def maakMarkeerRunMislukt():
    """Taak Markeer_Run_Mislukt: zet de run op 'mislukt' zodra een bewaakte taak faalt."""
    return PythonOperator(
        task_id='Markeer_Run_Mislukt',
        python_callable=verwerkingsrun.markeerRunMislukt,
        op_kwargs={'airflow_run_id': '{{ run_id }}'},
        trigger_rule=TriggerRule.ONE_FAILED,
    )


def maakRondRunAf():
    """Taak Rond_Run_Af: zet de run op 'afgerond' (DAG_Load_Only; de cycli doen dat bij de registratie)."""
    return PythonOperator(
        task_id='Rond_Run_Af',
        python_callable=verwerkingsrun.rondRunAf,
        op_kwargs={'airflow_run_id': '{{ run_id }}'},
    )


def voegVerwerkingsrapportToe(dag, eindtaak):
    """Voeg de taak Verwerkingsrapport toe na alle andere taken en vóór de eindtaak.

    Args:
        dag: de DAG (alle taken moeten al bestaan)
        eindtaak: de enige taak zonder stroomafwaartse taken (trigger rule all_success)

    Returns:
        De taak Verwerkingsrapport
    """
    rapport = PythonOperator(
        task_id='Verwerkingsrapport',
        python_callable=verwerkingsrapport.maakVerwerkingsrapport,
        trigger_rule=TriggerRule.ALL_DONE,
        dag=dag,
    )
    for taak in list(dag.tasks):
        if taak.task_id not in (rapport.task_id, eindtaak.task_id):
            taak >> rapport
    rapport >> eindtaak
    return rapport
