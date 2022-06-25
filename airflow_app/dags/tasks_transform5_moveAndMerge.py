from airflow.utils.task_group import TaskGroup
from airflow.operators.dummy import DummyOperator
from airflow.operators.python import PythonOperator

import shared.config as config
import wasstraat.mongoUtils as mongoUtils
import wasstraat.meta as meta
import wasstraat.merge_functions as merge_functions


def getMoveAndMergeTaskGroup():

    tg1 = TaskGroup(group_id='Transform5_Move_And_Merge_Group')
    with tg1:
        first = DummyOperator(task_id="first")
        middle1 = DummyOperator(task_id="middle1")
        middle2 = DummyOperator(task_id="middle2")
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
        Set_Index_SingleStoreClean >> middle1

        obj_types = meta.getKeys(meta.MOVEANDMERGE_MOVE)
        #obj_types.remove('Vondst') ## Fix this in meta or in harmonizet
        #obj_types.remove('Foto') ## Fix this in meta or in harmonizet
        for obj_type in obj_types:
            tsk = PythonOperator(
                task_id=f'Move_{obj_type}',
                python_callable=merge_functions.moveSoort,
                op_kwargs={'soort': obj_type}
            )
            Drop_SingleStoreClean >> tsk >> Set_Index_SingleStoreClean

        #obj_types = ['Artefact', 'Vondst'] ## Fix this in meta or in harmonizet
        obj_types = meta.getKeys(meta.MOVEANDMERGE_MERGE)
        for obj_type in obj_types:
            tsk = PythonOperator(
                task_id=f'Merge_{obj_type}',
                python_callable=merge_functions.mergeSoort,
                op_kwargs={'soort': obj_type}
            )
            middle1 >> tsk >> middle2

        MergeFotoinfo = PythonOperator(
            task_id='MergeFotoinfo',
            python_callable=merge_functions.mergeFotoinfo
        )
        middle1 >> MergeFotoinfo >> middle2

        obj_types = meta.getKeys(meta.MOVEANDMERGE_GENERATE_MISSING_PIPELINES)
        for obj_type in obj_types:
            tsk = PythonOperator(
                task_id=f'Generate_Missing_{obj_type}',
                python_callable=merge_functions.mergeMissing,
                op_kwargs={'soort': obj_type}
            )
            middle2 >> tsk >> last


    return tg1