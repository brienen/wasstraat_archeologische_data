
from airflow.utils.task_group import TaskGroup
from airflow.operators.dummy import DummyOperator
from airflow.operators.python import PythonOperator

import config
import wasstraat.harmonize_functions as harmonize_functions
import wasstraat.meta as meta


def getHarmonizeTaskGroup():

    tg1 = TaskGroup(group_id='Transform1_Harmonize_Group')
    with tg1:
        first = DummyOperator(task_id="first")
        last = DummyOperator(task_id="last")

        obj_types = meta.getKeys(meta.HARMONIZE_PIPELINES)
        for obj_type in obj_types:
            tsk = PythonOperator(
                task_id=f'Harmonize_{obj_type}',
                python_callable=harmonize_functions.callAggregation,
                op_kwargs={'collection': meta.getHarmonizeStagingCollection(obj_type), 'pipeline': meta.getHarmonizePipeline(obj_type)}
            )
            first >> tsk >> last

        Collect_ImageInfo = PythonOperator(
            task_id='Collect_ImageInfo',
            python_callable=harmonize_functions.collectImageInfo,
        )
        first >> Collect_ImageInfo >> last
        
    return tg1