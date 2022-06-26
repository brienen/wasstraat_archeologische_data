import os
import numpy as np

from airflow.utils.task_group import TaskGroup
from airflow.operators.bash import BashOperator
from airflow.operators.dummy import DummyOperator
from airflow.operators.python import PythonOperator

import shared.config as config
from wasstraat.image_import import importImages, getAndStoreImageFilenames



rootDir = str(config.AIRFLOW_INPUTDIR)
tmpDir = str(config.AIRFLOW_TEMPDIR)
imageExtensions = str(config.IMAGE_EXTENSIONS)

def getImageNamesFromDir(dir):
    return [os.path.join(dp, f) for dp, dn, filenames in os.walk(dir) for f in filenames if os.path.splitext(f)[1].lower() in config.IMAGE_EXTENSIONS] 


def getExtractTaskGroup():

    tg1 = TaskGroup(group_id='Extract_Group')
    with tg1:
        first = DummyOperator(task_id="first")
        last = DummyOperator(task_id="last")

        # [START howto_operator_bash]
        Extract_Data_From_DC = BashOperator(
            task_id='Extract_Data_From_DC_Projecten',
            bash_command="${AIRFLOW_HOME}/scripts/importMDB.sh %s %s " % (rootDir + "/projectdatabase/digidepot_DC", config.COLL_STAGING_OUD)
        )
        # [START howto_operator_bash]
        Extract_Data_From_DB = BashOperator(
            task_id='Extract_Data_From_DB_Projecten',
            bash_command="${AIRFLOW_HOME}/scripts/importMDB.sh %s %s " % (rootDir + "/projectdatabase/digidepot_DB", config.COLL_STAGING_OUD)
        )
        # [START howto_operator_bash]
        Extract_Data_From_DelfIT = BashOperator(
            task_id='Extract_Data_From_DelfIT',
            bash_command="${AIRFLOW_HOME}/scripts/importMDB.sh %s %s " % (rootDir + "/projectdatabase/Delf-IT", config.COLL_STAGING_DELFIT)
        )
        # [START howto_operator_bash]
        Extract_Data_From_Magazijnlijst = BashOperator(
            task_id='Extract_Data_From_Magazijnlijst',
            bash_command="${AIRFLOW_HOME}/scripts/importMDB.sh %s %s " % (rootDir + "/projectdatabase/magazijnlijst", config.COLL_STAGING_MAGAZIJNLIJST)
        )
        # [START howto_operator_bash]
        Extract_Data_From_DigiFotolijst = BashOperator(
            task_id='Extract_Data_From_DigiFotolijst',
            bash_command="${AIRFLOW_HOME}/scripts/importMDB.sh %s %s " % (rootDir + "/projectdatabase/digifotos", config.COLL_STAGING_DIGIFOTOS)
        )
        GetAndStoreImageFilenames = PythonOperator(
            task_id='GetAndStoreImageFilenames',
            python_callable=getAndStoreImageFilenames,
        )
        first >> GetAndStoreImageFilenames
        i=0
        while i < 10:
            tsk = PythonOperator(
                task_id='Extract_Data_From_Fotos_' + str(i),
                python_callable=importImages,
                op_kwargs={'index': i, 'of': 10}
            )
            GetAndStoreImageFilenames >> tsk >> last
            i += 1
        
        
        first >> [Extract_Data_From_DC, Extract_Data_From_DB, Extract_Data_From_DelfIT, Extract_Data_From_Magazijnlijst, Extract_Data_From_DigiFotolijst] >> last
        
    return tg1