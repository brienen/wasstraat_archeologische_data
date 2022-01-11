import os
from datetime import datetime, timedelta

from airflow.utils.task_group import TaskGroup
from airflow.operators.bash import BashOperator
from airflow.operators.dummy import DummyOperator
from airflow.operators.python import PythonOperator

import config
import wasstraat.mongoUtils as mongoUtils
import wasstraat.collect_functions as collect_functions
import wasstraat.meta as meta


def getCollectTaskGroup():

    tg1 = TaskGroup(group_id='Collect_Group')
    with tg1:
        Collect_Stellingen = PythonOperator(
            task_id='Collect_Stellingen',
            python_callable=collect_functions.callAggregation,
            op_kwargs={'collection': str(config.COLL_STAGING_MAGAZIJNLIJST), 'pipeline': meta.getCollectPipeline('Stelling')}
        )
        Collect_Magazijnlocatie = PythonOperator(
            task_id='Collect_Magazijnlocatie',
            python_callable=collect_functions.callAggregation,
            op_kwargs={'collection': str(config.COLL_STAGING_MAGAZIJNLIJST), 'pipeline': meta.getCollectPipeline('Magazijnlocatie')}
        )
        Collect_Project = PythonOperator(
            task_id='Collect_Project',
            python_callable=collect_functions.callAggregation,
            op_kwargs={'collection': str(config.COLL_STAGING_DELFIT), 'pipeline': meta.getCollectPipeline('Project')}
        )
        Collect_Vindplaats = PythonOperator(
            task_id='Collect_Vindplaats',
            python_callable=collect_functions.callAggregation,
            op_kwargs={'collection': str(config.COLL_STAGING_DELFIT), 'pipeline': meta.getCollectPipeline('Vindplaats')}
        )
        Collect_Vondst = PythonOperator(
            task_id='Collect_Vondst',
            python_callable=collect_functions.callAggregation,
            op_kwargs={'collection': str(config.COLL_STAGING_OUD), 'pipeline': meta.getCollectPipeline('Vondst')}
        )
        Collect_Artefact = PythonOperator(
            task_id='Collect_Artefact',
            python_callable=collect_functions.callAggregation,
            op_kwargs={'collection': str(config.COLL_STAGING_OUD), 'pipeline': meta.getCollectPipeline('Artefact')}
        )
        Collect_ImageInfo = PythonOperator(
            task_id='Collect_ImageInfo',
            python_callable=collect_functions.collectImageInfo,
        )

        
        [Collect_Stellingen, Collect_Magazijnlocatie, Collect_Project, Collect_Vindplaats, Collect_Vondst, Collect_Artefact, Collect_ImageInfo]
        
    return tg1