from airflow.utils.task_group import TaskGroup
from airflow.operators.bash import BashOperator
from airflow.operators.dummy import DummyOperator
from airflow.operators.python import PythonOperator

import wasstraat.references_functions as references_functions
import wasstraat.meta as meta


def getSetReferencesTaskGroup():
    """Maak de taakgroep voor Transform 4 (integer-sleutels en referenties).

    De Set_PrimaryKey-taken kennen in elke DAG stabiele sleutels toe
    (stabiel=True): documenten houden hun ID of krijgen hun primary_key uit
    PostgreSQL terug; alleen nieuwe entiteiten krijgen een nieuw nummer boven
    het bestaande maximum. Tot issue 71 deed alleen de incrementele cyclus dat
    en nummerde de volledige cyclus alles opnieuw, waardoor sleutels
    verschoven en de gebruikerstabellen geleegd moesten worden. De
    Set_Reference-taken werken altijd hetzelfde: ze vullen alleen ontbrekende
    <soort>ID-velden.
    """
    tg1 = TaskGroup(group_id='Transform4_Set_References_Group')
    with tg1:
        first = DummyOperator(task_id="first")
        middle = DummyOperator(task_id="middle")
        last = DummyOperator(task_id="last")

        obj_types = meta.getKeys(meta.SET_KEYS_PIPELINES)
        for obj_type in obj_types:
            tsk = PythonOperator(
                task_id=f'Set_PrimaryKey_{obj_type}',
                python_callable=references_functions.setPrimaryKeys,
                op_kwargs={'soort': obj_type, 'col': 'analyseclean', 'stabiel': True}
            )
            first >> tsk >> middle

        curr = middle
        obj_types = meta.getKeys(meta.SET_KEYS_PIPELINES)
        for obj_type in obj_types:
            tsk = PythonOperator(
                task_id=f'Set_Reference_{obj_type}',
                python_callable=references_functions.setReferences,
                op_kwargs={'soort': obj_type, 'col': 'analyseclean'}
            )
            curr >> tsk
            curr = tsk

        tsk_image1 = PythonOperator(
            task_id=f'Set_Reference_Images_to_Foto1',
            python_callable=references_functions.setReferences,
            op_kwargs={'soort': 'Artefact', 'col': 'analyseclean', 'key': 'key_foto1'}
        )
        tsk_image3 = PythonOperator(
            task_id=f'Set_Reference_Images_to_Foto3',
            python_callable=references_functions.setReferences,
            op_kwargs={'soort': 'Artefact', 'col': 'analyseclean', 'key': 'key_foto3'}
        )
        curr >> tsk_image1 >> tsk_image3 >> last
        tsk_abr_materiaal = PythonOperator(
            task_id=f'Set_Reference_ABR_Materiaal',
            python_callable=references_functions.setReferences,
            op_kwargs={'soort': 'ABR', 'col': 'analyseclean', 'refkey': 'abr_materiaal'}
        )
        curr >> tsk_abr_materiaal >> last
        tsk_abr_submateriaal = PythonOperator(
            task_id=f'Set_Reference_ABR_SubMateriaal',
            python_callable=references_functions.setReferences,
            op_kwargs={'soort': 'ABR', 'col': 'analyseclean', 'refkey': 'abr_submateriaal'}
        )
        curr >> tsk_abr_submateriaal >> last



    return tg1
