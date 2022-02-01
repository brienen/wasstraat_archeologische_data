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


def getSetKeysTaskGroup():

    tg1 = TaskGroup(group_id='Transform3_Set_Keys_Group')
    with tg1:
        first = DummyOperator(task_id="first")
        last = DummyOperator(task_id="last")

        Set_Artefactnr_Unique = PythonOperator(
            task_id='Set_Artefactnr_Unique',
            python_callable=references_functions.setArtefactnrUnique,
        )
        first >> Set_Artefactnr_Unique

        obj_types = meta.getKeys(meta.SET_REFERENCES_PIPELINES)
        for obj_type in obj_types:
            tsk = PythonOperator(
                task_id=f'Set_ReferenceKeys_{obj_type}',
                python_callable=references_functions.setReferenceKeys,
                op_kwargs={'pipeline': meta.getReferenceKeysPipeline(obj_type), 'soort': obj_type}
            )
            Set_Artefactnr_Unique >> tsk >> last

        #Set_Reference_Keys_Doos = PythonOperator(
        #    task_id='Set_Reference_Keys_Dozen',
        #    python_callable=references_functions.setReferenceKeysDozen,
        #)
        #Set_Artefactnr_Unique >> Set_Reference_Keys_Doos >> last

    return tg1