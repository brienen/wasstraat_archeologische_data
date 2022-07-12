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
import numpy as np
from datetime import timedelta, datetime

from airflow import DAG
from airflow.utils.task_group import TaskGroup
from airflow.operators.bash import BashOperator
from airflow.operators.dummy import DummyOperator
from airflow.operators.python import PythonOperator

import shared.config as config
from wasstraat.image_import import importImages, getAndStoreImageFilenames


with DAG(
    dag_id='Redo_Images',
    start_date=datetime(2021, 1, 1),
    schedule_interval=None,
    catchup=False,
    dagrun_timeout=timedelta(minutes=480),
    template_searchpath="/opt/airflow"
) as dag:
    first = DummyOperator(
        task_id='Start_Extract_only',
    )
    last = DummyOperator(
        task_id='End_Extract_only',
    )
    
    i=0
    while i < 5:
        tsk = PythonOperator(
            task_id='Extract_Data_From_Fotos_' + str(i),
            python_callable=importImages,
            op_kwargs={'index': i, 'of': 5},
            retries=5,
            retry_delay=timedelta(minutes=1)

        )
        first >> tsk >> last
        i += 1

