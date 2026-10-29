from airflow.utils.task_group import TaskGroup
from airflow.utils.trigger_rule import TriggerRule
from airflow.operators.dummy import DummyOperator
from airflow.operators.python import PythonOperator

import shared.config as config
import wasstraat.mongoUtils as mongoUtils
import wasstraat.meta as meta
import wasstraat.merge_functions as merge_functions
import shared.config as config
import shared.fulltext as fulltext
import shared.database as database
import wasstraat.loadToDatabase_functions as loadToDatabase


def getLoadToDatabaseAndIndexTaskGroup():
    """Maak de taakgroep voor de load naar PostgreSQL en de Elasticsearch-indexering.

    LoadToDatabase_postgres → Index_<tabel> (parallel) → Index_Klaar → End_cycle.
    Foutbeleid (issue 54): een mislukte Index-taak is een waarschuwing. Index_Klaar
    (trigger rule all_done) wacht tot alle Index-taken klaar zijn, ook als er een
    mislukt; End_cycle hangt af van LoadToDatabase_postgres en Index_Klaar, zodat de
    groep (en de DAG) slaagt als de load slaagt, ook als de indexering haperde. De
    index is uit PostgreSQL af te leiden en los opnieuw te bouwen (DAG_Load_Only).
    Tot issue 54 hing End_cycle direct aan de Index-taken en faalde de hele
    volledige cyclus op een haperende Elasticsearch.
    """
    tg1 = TaskGroup(group_id='Load_To_Database_And_Inxdex_Group')
    with tg1:

        Start_cycle = DummyOperator(
            task_id='Start_cycle',
        )
        End_cycle = DummyOperator(
            task_id='End_cycle',
        )
        Index_Klaar = DummyOperator(
            task_id='Index_Klaar',
            trigger_rule=TriggerRule.ALL_DONE,
        )

        LoadToDatabase_postgres = PythonOperator(
            task_id='LoadToDatabase_postgres',
            python_callable=loadToDatabase.loadAll
        )
        Start_cycle >> LoadToDatabase_postgres

        tables = database.getAllTables()
        for table in tables:
            tsk = PythonOperator(
                task_id=f'Index_{table}',
                python_callable=fulltext.indexTable,
                op_kwargs={'table': table}
            )
            LoadToDatabase_postgres >> tsk >> Index_Klaar
        LoadToDatabase_postgres >> Index_Klaar
        [LoadToDatabase_postgres, Index_Klaar] >> End_cycle

    return tg1
