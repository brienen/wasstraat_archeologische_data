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

import config
import wasstraat.loadToDatabase_functions as loadToDatabase


rootDir = str(config.AIRFLOW_INPUTDIR)
tmpDir = str(config.AIRFLOW_TEMPDIR)

with DAG(
    dag_id='DAG_Load_Only',
    start_date=datetime(2021, 1, 1),
    schedule_interval=None,
    catchup=False,
    dagrun_timeout=timedelta(minutes=60),
    template_searchpath="/opt/airflow"
) as dag:
    Start_cycle = DummyOperator(
        task_id='Start_cycle',
    )

    #def importImages(rootDir, mongo_uri, db_files, db_staging):   
    LoadToDatabase_postgres = PythonOperator(
        task_id='LoadToDatabase_postgres',
        python_callable=loadToDatabase.loadAll
    )

    End_cycle = DummyOperator(
        task_id='End_cycle',
    )
    

    Start_cycle >> LoadToDatabase_postgres >> End_cycle 
