import os
from datetime import datetime, timedelta

from airflow.utils.task_group import TaskGroup
from airflow.operators.bash import BashOperator
from airflow.operators.dummy import DummyOperator
from airflow.operators.python import PythonOperator

import config
import wasstraat.mongoUtils as mongoUtils
import wasstraat.references_functions as references_functions
import wasstraat.setAttributes_functions as setAttributes_functions
import wasstraat.meta as meta
import wasstraat.merge_functions as merge_functions


def getMoveAndMergeTaskGroup():

    tg1 = TaskGroup(group_id='Transform5_Move_And_Merge_Group')
    with tg1:
        first = DummyOperator(task_id="first")
        middle = DummyOperator(task_id="middle")
        last = DummyOperator(task_id="last")

        Drop_SingleStoreClean = PythonOperator(
            task_id='Drop_SingleStoreClean',
            python_callable=mongoUtils.dropSingleStoreClean
        )
        first >> Drop_SingleStoreClean

        Set_Index_SingleStoreClean = PythonOperator(
            task_id='Set_Index_SingleStoreClean',
            python_callable=mongoUtils.setIndexes,
            op_kwargs={'collection': config.COLL_ANALYSE_CLEAN}
        )
        Set_Index_SingleStoreClean >> middle

        obj_types = meta.getKeys(meta.MOVE_FASE)
        for obj_type in obj_types:
            tsk = PythonOperator(
                task_id=f'Move_{obj_type}',
                python_callable=merge_functions.moveSoort,
                op_kwargs={'soort': obj_type}
            )
            Drop_SingleStoreClean >> tsk >> Set_Index_SingleStoreClean

        Merge_Inherited = PythonOperator(
            task_id='Merge_Inherited',
            python_callable=merge_functions.mergeSoort,
            op_kwargs={'soort': "Artefact"}
        )
        middle >> Merge_Inherited >> last

    return tg1