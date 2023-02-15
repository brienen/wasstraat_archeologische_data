from airflow.utils.task_group import TaskGroup
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

    tg1 = TaskGroup(group_id='Load_To_Database_And_Inxdex_Group')
    with tg1:

        Start_cycle = DummyOperator(
            task_id='Start_cycle',
        )
        End_cycle = DummyOperator(
            task_id='End_cycle',
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
            LoadToDatabase_postgres >> tsk >> End_cycle

    return tg1