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
import os

from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.dummy import DummyOperator
from airflow.operators.python import PythonOperator

import config
import tasks_import
import tasks_extract
import tasks_collect
import wasstraat.mongoUtils as mongoUtils
import wasstraat.clean_functions as clean
import wasstraat.dbloader_functions as dbloader


rootDir = str(config.AIRFLOW_INPUTDIR)
tmpDir = str(config.AIRFLOW_TEMPDIR)

with DAG(
    dag_id='Load_data_to_database',
    start_date=datetime(2021, 1, 1),
    catchup=False,
    dagrun_timeout=timedelta(minutes=60),
    template_searchpath="/opt/airflow"
) as dag:
    start_import = DummyOperator(
        task_id='start_import',
    )

    #def importImages(rootDir, mongo_uri, db_files, db_staging):   
    DbLoader_function = PythonOperator(
        task_id='DbLoader_function',
        python_callable=dbloader.loadAll,
        op_kwargs={}
    )

    end_import = DummyOperator(
        task_id='end_import',
    )


    start_import >> DbLoader_function >> end_import 
