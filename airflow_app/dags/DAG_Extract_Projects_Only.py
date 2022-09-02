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
from airflow.operators.bash import BashOperator


import shared.config as config
import tasks_extract
import wasstraat.mongoUtils as mongoUtils


with DAG(
    dag_id='Extract_Projects_only',
    start_date=datetime(2021, 1, 1),
    schedule_interval=None,
    catchup=False,
    dagrun_timeout=timedelta(minutes=480),
    template_searchpath="/opt/airflow"
) as dag:
    Start_Extract_Projects_only = DummyOperator(
        task_id='Start_Extract_only',
    )
    End_Extract_Projects_only = DummyOperator(
        task_id='End_Extract_only',
    )
    Drop_Project_Collection = PythonOperator(
        task_id='Drop_Project_Collection',
        python_callable=mongoUtils.dropProjectsStore
    )
    # [START howto_operator_bash]
    Extract_Data_From_Projecten = BashOperator(
        task_id='Extract_Data_From_Projecten',
        bash_command="${AIRFLOW_HOME}/scripts/importMDB.sh %s %s " % (config.AIRFLOW_INPUT_PROJECTEN, config.COLL_STAGING_OUD)
    )
    


    Start_Extract_Projects_only >> Drop_Project_Collection >> Extract_Data_From_Projecten >> End_Extract_Projects_only
