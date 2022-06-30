#
# Licensed to the Apache Software Foundation (ASF) under one
# or more contributor license agreements.  See the NOTICE file
# distributed with this work for additional information
# regarding copyright ownership.  The ASF licenses this file
# to you under the Apache License, Version 2.0 (the
# "License"); you may not use this file except in compliance
# with the License.  You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an
# "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
# KIND, either express or implied.  See the License for the
# specific language governing permissions and limitations
# under the License.

"""Data Importeren"""
from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.dummy import DummyOperator
from airflow.operators.python import PythonOperator

import shared.config as config
import tasks_extract
import wasstraat.mongoUtils as mongoUtils


rootDir = str(config.AIRFLOW_INPUTDIR)
tmpDir = str(config.AIRFLOW_TEMPDIR)

with DAG(
    dag_id='Extract_only',
    start_date=datetime(2021, 1, 1),
    schedule_interval=None,
    catchup=False,
    dagrun_timeout=timedelta(minutes=60),
    template_searchpath="/opt/airflow"
) as dag:
    Start_Extract_only = DummyOperator(
        task_id='Start_Extract_only',
    )
    End_Extract_only = DummyOperator(
        task_id='End_Extract_only',
    )
    #def importImages(rootDir, mongo_uri, db_files, db_staging):   
    Drop_Staging_Database = PythonOperator(
        task_id='Drop_Staging_Database',
        python_callable=mongoUtils.dropStaging
    )
    Drop_Files_Database = PythonOperator(
        task_id='Drop_Files_Database',
        python_callable=mongoUtils.dropFileStore
    )
    
    tg_import = tasks_extract.getExtractTaskGroup()


    Start_Extract_only >> Drop_Staging_Database >> Drop_Files_Database >> tg_import >> End_Extract_only
