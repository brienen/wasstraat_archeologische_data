
from airflow.utils.task_group import TaskGroup
from airflow.operators.dummy import DummyOperator
from airflow.operators.python import PythonOperator

import wasstraat.harmonize_functions as harmonize_functions
import wasstraat.meta as meta


def getHarmonizeTaskGroup():

    tg1 = TaskGroup(group_id='Transform1_Harmonize_Group')
    with tg1:
        first = DummyOperator(task_id="first")
        last = DummyOperator(task_id="last")

        FixProjectNames = PythonOperator(
            task_id='FixProjectNames',
            python_callable=harmonize_functions.fixProjectNames,
        )
        first >> FixProjectNames

        obj_types = meta.getKeys(meta.HARMONIZE_PIPELINES)
        obj_types.remove('Foto')
        for obj_type in obj_types:
            tsk = PythonOperator(
                task_id=f'Harmonize_{obj_type}',
                python_callable=harmonize_functions.harmonize,
                op_kwargs={'collection': meta.getHarmonizeStagingCollection(obj_type), 'strOrAggr': meta.getHarmonizePipelines(obj_type)}
            )
            FixProjectNames >> tsk >> last

        Collect_ImageInfo = PythonOperator(
            task_id='ParseFotobestanden',
            python_callable=harmonize_functions.parseFotobestanden,
        )
        FixProjectNames >> Collect_ImageInfo >> last
        
    return tg1