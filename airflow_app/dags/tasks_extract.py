import os
from datetime import datetime, timedelta

from airflow.utils.task_group import TaskGroup
from airflow.operators.bash import BashOperator
from airflow.operators.dummy import DummyOperator
from airflow.operators.python import PythonOperator

import config
import wasstraat.mongoUtils as mongoUtils
from wasstraat.image_import import importImages



rootDir = str(config.AIRFLOW_INPUTDIR)
tmpDir = str(config.AIRFLOW_TEMPDIR)


def getExtractTaskGroup():

    tg1 = TaskGroup(group_id='Extract_Group')
    with tg1:
        # [START howto_operator_bash]
        Extract_Data_From_old = BashOperator(
            task_id='Extract_Data_From_Oude_Projecten',
            bash_command="${AIRFLOW_HOME}/scripts/importMDB.sh %s %s " % (rootDir + "/projectdatabase/oud", config.COLL_STAGING_OUD)
        )
        # [START howto_operator_bash]
        Extract_Data_From_new = BashOperator(
            task_id='Extract_Data_From_Nieuwe_Projecten',
            bash_command="${AIRFLOW_HOME}/scripts/importMDB.sh %s %s " % (rootDir + "/projectdatabase/nieuw", config.COLL_STAGING_NIEUW)
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
        #def importImages(rootDir, mongo_uri, db_files, db_staging):   
        Extract_Data_From_Fotos = PythonOperator(
            task_id='Extract_Data_From_Fotos',
            python_callable=importImages,
            op_kwargs={'rootDir': rootDir + "/fotos", 'mongo_uri': config.MONGO_URI, 'db_files': config.DB_FILES, 'db_staging': config.DB_STAGING}
        )
        
        

        [Extract_Data_From_old, Extract_Data_From_new, Extract_Data_From_DelfIT, Extract_Data_From_Magazijnlijst, Extract_Data_From_DigiFotolijst, Extract_Data_From_Fotos]
        
    return tg1