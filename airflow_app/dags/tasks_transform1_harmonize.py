
from airflow.utils.task_group import TaskGroup
from airflow.operators.python import PythonOperator

import config
import wasstraat.harmonize_functions as harmonize_functions
import wasstraat.meta as meta


def getHarmonizeTaskGroup():

    tg1 = TaskGroup(group_id='Transform1_Harmonize_Group')
    with tg1:
        Harmonize_Stellingen = PythonOperator(
            task_id='Harmonize_Stellingen',
            python_callable=harmonize_functions.callAggregation,
            op_kwargs={'collection': str(config.COLL_STAGING_MAGAZIJNLIJST), 'pipeline': meta.getHarmonizePipeline('Stelling')}
        )
        Harmonize_Magazijnlocatie = PythonOperator(
            task_id='Harmonize_Magazijnlocatie',
            python_callable=harmonize_functions.callAggregation,
            op_kwargs={'collection': str(config.COLL_STAGING_MAGAZIJNLIJST), 'pipeline': meta.getHarmonizePipeline('Magazijnlocatie')}
        )
        Harmonize_Project = PythonOperator(
            task_id='Harmonize_Project',
            python_callable=harmonize_functions.callAggregation,
            op_kwargs={'collection': str(config.COLL_STAGING_DELFIT), 'pipeline': meta.getHarmonizePipeline('Project')}
        )
        Harmonize_Vindplaats = PythonOperator(
            task_id='Harmonize_Vindplaats',
            python_callable=harmonize_functions.callAggregation,
            op_kwargs={'collection': str(config.COLL_STAGING_DELFIT), 'pipeline': meta.getHarmonizePipeline('Vindplaats')}
        )
        Harmonize_Vondst = PythonOperator(
            task_id='Harmonize_Vondst',
            python_callable=harmonize_functions.callAggregation,
            op_kwargs={'collection': str(config.COLL_STAGING_OUD), 'pipeline': meta.getHarmonizePipeline('Vondst')}
        )
        Harmonize_Artefact = PythonOperator(
            task_id='Harmonize_Artefact',
            python_callable=harmonize_functions.callAggregation,
            op_kwargs={'collection': str(config.COLL_STAGING_OUD), 'pipeline': meta.getHarmonizePipeline('Artefact')}
        )
        Harmonize_Put = PythonOperator(
            task_id='Harmonize_Put',
            python_callable=harmonize_functions.callAggregation,
            op_kwargs={'collection': str(config.COLL_STAGING_OUD), 'pipeline': meta.getHarmonizePipeline('Put')}
        )
        Harmonize_Spoor = PythonOperator(
            task_id='Harmonize_Spoor',
            python_callable=harmonize_functions.callAggregation,
            op_kwargs={'collection': str(config.COLL_STAGING_OUD), 'pipeline': meta.getHarmonizePipeline('Spoor')}
        )
        Harmonize_Aardewerk = PythonOperator(
            task_id='Harmonize_Aardewerk',
            python_callable=harmonize_functions.callAggregation,
            op_kwargs={'collection': str(config.COLL_STAGING_OUD), 'pipeline': meta.getHarmonizePipeline('Aardewerk')}
        )
        Collect_ImageInfo = PythonOperator(
            task_id='Collect_ImageInfo',
            python_callable=harmonize_functions.collectImageInfo,
        )

        
        [Harmonize_Stellingen, Harmonize_Magazijnlocatie, Harmonize_Project, Harmonize_Vindplaats, Harmonize_Vondst, Harmonize_Artefact, Harmonize_Put, Collect_ImageInfo, Harmonize_Aardewerk, Harmonize_Spoor]
        
    return tg1