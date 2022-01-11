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


def getImportTaskGroup():

    tg1 = TaskGroup(group_id='Import_Group')
    with tg1:
        # [START howto_operator_bash]
        import_old = BashOperator(
            task_id='Importeer_Oude_Projecten',
            bash_command="${AIRFLOW_HOME}/scripts/importMDB.sh %s %s " % (rootDir + "/projectdatabase/oud", config.COLL_STAGING_OUD)
        )
        # [START howto_operator_bash]
        import_new = BashOperator(
            task_id='Importeer_Nieuwe_Projecten',
            bash_command="${AIRFLOW_HOME}/scripts/importMDB.sh %s %s " % (rootDir + "/projectdatabase/nieuw", config.COLL_STAGING_NIEUW)
        )
        # [START howto_operator_bash]
        import_DelfIT = BashOperator(
            task_id='Importeer_DelfIT',
            bash_command="${AIRFLOW_HOME}/scripts/importMDB.sh %s %s " % (rootDir + "/projectdatabase/Delf-IT", config.COLL_STAGING_DELFIT)
        )
        # [START howto_operator_bash]
        import_Magazijnlijst = BashOperator(
            task_id='Importeer_Magazijnlijst',
            bash_command="${AIRFLOW_HOME}/scripts/importMDB.sh %s %s " % (rootDir + "/projectdatabase/magazijnlijst", config.COLL_STAGING_MAGAZIJNLIJST)
        )
        # [START howto_operator_bash]
        Importeer_DigiFotolijst = BashOperator(
            task_id='Importeer_DigiFotolijst',
            bash_command="${AIRFLOW_HOME}/scripts/importMDB.sh %s %s " % (rootDir + "/projectdatabase/digifotos", config.COLL_STAGING_DIGIFOTOS)
        )
        #def importImages(rootDir, mongo_uri, db_files, db_staging):   
        Importeer_Fotos = PythonOperator(
            task_id='Importeer_Fotos',
            python_callable=importImages,
            op_kwargs={'rootDir': rootDir + "/fotos", 'mongo_uri': config.MONGO_URI, 'db_files': config.DB_FILES, 'db_staging': config.DB_STAGING}
        )
        
        

        [import_old, import_new, import_DelfIT, import_Magazijnlijst, Importeer_DigiFotolijst, Importeer_Fotos]
        
    return tg1