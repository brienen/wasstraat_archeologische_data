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

import shared.config as config
import tasks_transform5_moveAndMerge
import tasks_transform4_references


rootDir = str(config.AIRFLOW_INPUTDIR)
tmpDir = str(config.AIRFLOW_TEMPDIR)

with DAG(
    dag_id='DAG_Transform_Move_And_References_Only',
    start_date=datetime(2021, 1, 1),
    schedule_interval=None,
    catchup=False,
    dagrun_timeout=timedelta(minutes=60),
    template_searchpath="/opt/airflow"
) as dag:
    Start_cycle = DummyOperator(
        task_id='Start_cycle',
    )
    End_cycle = DummyOperator(
        task_id='End_cycle',
    )
    tg_references = tasks_transform4_references.getSetReferencesTaskGroup()
    tg_move = tasks_transform5_moveAndMerge.getMoveAndMergeTaskGroup()

    Start_cycle >> tg_move >> tg_references >> End_cycle 
