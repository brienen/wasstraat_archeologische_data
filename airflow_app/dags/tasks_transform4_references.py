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


def getSetReferencesTaskGroup():

    tg1 = TaskGroup(group_id='Transform4_Set_References_Group')
    with tg1:
        first = DummyOperator(task_id="first")
        middle = DummyOperator(task_id="middle")
        last = DummyOperator(task_id="last")

        obj_types = meta.getKeys(meta.MOVE_FASE)
        for obj_type in obj_types:
            tsk = PythonOperator(
                task_id=f'Set_PrimaryKey_{obj_type}',
                python_callable=references_functions.setPrimaryKeys,
                op_kwargs={'soort': obj_type, 'col': 'analyseclean'}
            )
            first >> tsk >> middle

        curr = middle
        obj_types = meta.getKeys(meta.MOVE_FASE)
        for obj_type in obj_types:
            tsk = PythonOperator(
                task_id=f'Set_Reference_{obj_type}',
                python_callable=references_functions.setReferences,
                op_kwargs={'soort': obj_type, 'col': 'analyseclean'}
            )
            curr >> tsk
            curr = tsk

        tsk_iamge = PythonOperator(
            task_id=f'Set_Reference_Images_to_Subnr',
            python_callable=references_functions.setReferences,
            op_kwargs={'soort': 'Artefact', 'col': 'analyseclean', 'key': 'key_subnr'}
        )

        curr >> tsk_iamge >> last


    return tg1