from airflow.utils.task_group import TaskGroup
from airflow.operators.dummy import DummyOperator
from airflow.operators.python import PythonOperator

import wasstraat.harmonize_functions as harmonize_functions
import wasstraat.harmonisatie_voorrang as harmonisatie_voorrang
import wasstraat.delta_transform as delta_transform
import wasstraat.meta as meta


def getHarmonizeTaskGroup(incrementeel=False):
    """Maak de taakgroep voor Transform 1 (harmonisatie).

    Args:
        incrementeel: als True harmoniseren de taken alleen de nieuwe en
            gewijzigde bronbestanden uit de actieve verwerkingsrun en werkt een
            extra taak aan het eind de geraakte projecten in het run-document bij
            (incrementele cyclus)
    """
    delta_kwargs = {'incrementeel': True} if incrementeel else {}

    tg1 = TaskGroup(group_id='Transform1_Harmonize_Group')
    with tg1:
        first = DummyOperator(task_id="first")
        last = DummyOperator(task_id="last")

        FixProjectNames = PythonOperator(
            task_id='FixProjectNames',
            python_callable=harmonize_functions.fixProjectNames,
        )
        first >> FixProjectNames

        FixMonsterProjectcds = PythonOperator(
            task_id='fixMonsterProjectcds',
            python_callable=harmonize_functions.fixMonsterProjectcds,
            op_kwargs=delta_kwargs,
        )
        if incrementeel:
            # Projectcodes van de delta-documenten toevoegen aan geraakte_projecten in het run-document
            Werk_Geraakte_Projecten_Bij = PythonOperator(
                task_id='Werk_Geraakte_Projecten_Bij',
                python_callable=delta_transform.werkGeraakteProjectenBij,
            )
            FixMonsterProjectcds >> Werk_Geraakte_Projecten_Bij >> last
        else:
            FixMonsterProjectcds >> last


        # De taken draaien parallel; welke pipeline een tabel harmoniseert die meer pipelines selecteren,
        # bepaalt elke taak zelf (issue 89, wasstraat/harmonisatie_voorrang.py)
        for obj_type in harmonisatie_voorrang.getHarmonizeSoorten():
            tsk = PythonOperator(
                task_id=f'Harmonize_{obj_type}',
                python_callable=harmonize_functions.harmonize,
                op_kwargs=dict({'collection': meta.getHarmonizeStagingCollection(obj_type), 'strOrAggr': meta.getHarmonizePipelines(obj_type),
                                'soort': obj_type}, **delta_kwargs)
            )
            FixProjectNames >> tsk >> FixMonsterProjectcds

        Collect_ImageInfo = PythonOperator(
            task_id='ParseFotobestanden',
            python_callable=harmonize_functions.parseFotobestanden,
            op_kwargs=delta_kwargs,
        )
        FixProjectNames >> Collect_ImageInfo >> FixMonsterProjectcds

    return tg1
