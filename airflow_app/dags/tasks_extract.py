import os
import numpy as np
from datetime import timedelta

from airflow.utils.task_group import TaskGroup
from airflow.operators.bash import BashOperator
from airflow.operators.dummy import DummyOperator
from airflow.operators.python import PythonOperator

import shared.config as config
from wasstraat.image_import import importImages, getAndStoreImageFilenames

NUM_PROCESSOR = 8



def getExtractTaskGroup():

    tg1 = TaskGroup(group_id='Extract_Group')
    with tg1:
        first = DummyOperator(task_id="first")
        last = DummyOperator(task_id="last")

        # [START howto_operator_bash]
        Extract_Data_From_Projecten = BashOperator(
            task_id='Extract_Data_From_Projecten',
            bash_command="${AIRFLOW_HOME}/scripts/importMDB.sh %s %s " % (config.AIRFLOW_INPUT_PROJECTEN, config.COLL_STAGING_OUD)
        )
        # [START howto_operator_bash]
        Extract_Data_From_DelfIT = BashOperator(
            task_id='Extract_Data_From_DelfIT',
            bash_command="${AIRFLOW_HOME}/scripts/importMDB.sh %s %s " % (config.AIRFLOW_INPUT_DELFIT, config.COLL_STAGING_DELFIT)
        )
        # [START howto_operator_bash]
        Extract_Data_From_Magazijnlijst = BashOperator(
            task_id='Extract_Data_From_Magazijnlijst',
            bash_command="${AIRFLOW_HOME}/scripts/importMDB.sh %s %s " % (config.AIRFLOW_INPUT_MAGAZIJNLIJST, config.COLL_STAGING_MAGAZIJNLIJST)
        )
        # [START howto_operator_bash]
        Extract_Data_From_DigiFotolijst = BashOperator(
            task_id='Extract_Data_From_DigiFotolijst',
            bash_command="${AIRFLOW_HOME}/scripts/importMDB.sh %s %s " % (config.AIRFLOW_INPUT_DIGIFOTOS, config.COLL_STAGING_DIGIFOTOS)
        )
        Extract_Data_From_MonsterDB = BashOperator(
            task_id='Extract_Data_From_MonsterDB',
            bash_command="${AIRFLOW_HOME}/scripts/importMDB.sh %s %s " % (config.AIRFLOW_INPUT_MONSTER, config.COLL_STAGING_MONSTER)
        )
        GetAndStoreImageFilenames = PythonOperator(
            task_id='GetAndStoreImageFilenames',
            python_callable=getAndStoreImageFilenames,
        )
        first >> GetAndStoreImageFilenames
        i=0
        while i < NUM_PROCESSOR:
            tsk = PythonOperator(
                task_id='Extract_Data_From_Fotos_' + str(i),
                python_callable=importImages,
                op_kwargs={'index': i, 'of': NUM_PROCESSOR},
                retries=5,
                retry_delay=timedelta(minutes=1)

            )
            GetAndStoreImageFilenames >> tsk >> last
            i += 1
        
        
        first >> [Extract_Data_From_Projecten, Extract_Data_From_DelfIT, Extract_Data_From_Magazijnlijst, Extract_Data_From_DigiFotolijst, Extract_Data_From_MonsterDB] >> last
        
    return tg1