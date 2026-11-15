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

"""Alleen laden: Single_Store_Clean naar PostgreSQL en Elasticsearch, zonder extractie en transformatie.

Sinds issues 54 en 62 heeft ook deze DAG een run-document (soort laden): Start_Run →
Load_To_Database_And_Inxdex_Group (LoadToDatabase_postgres → Index_<tabel> → Index_Klaar)
→ Rond_Run_Af. Markeer_Run_Mislukt zet de run op 'mislukt' als de load faalt; een
mislukte Index-taak is een waarschuwing. De taak Verwerkingsrapport schrijft na alle andere
taken het rapport van de run.
"""
from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.dummy import DummyOperator
from airflow.operators.python import PythonOperator

import shared.config as config
import shared.fulltext as fulltext
import shared.database as database
import wasstraat.loadToDatabase_functions as loadToDatabase
import wasstraat.verwerkingsrun as verwerkingsrun
import tasks_load_to_database_and_index
import tasks_verwerkingsrun



def loadAll():
    loadToDatabase.loadAll()


with DAG(
    dag_id='DAG_Load_Only',
    start_date=datetime(2021, 1, 1),
    schedule_interval=None,
    catchup=False,
    max_active_runs=1,
    dagrun_timeout=timedelta(minutes=480),
    template_searchpath="/opt/airflow",
    default_args=tasks_verwerkingsrun.getDefaultArgs(),
) as dag:
    Start_cycle = DummyOperator(
        task_id='Start_cycle',
    )
    End_cycle = DummyOperator(
        task_id='End_cycle',
    )
    Start_Run = tasks_verwerkingsrun.maakStartRun(verwerkingsrun.SOORT_LADEN)
    tg_loadToDatabaseAndIndex = tasks_load_to_database_and_index.getLoadToDatabaseAndIndexTaskGroup()
    Rond_Run_Af = tasks_verwerkingsrun.maakRondRunAf()

    Start_cycle >> Start_Run >> tg_loadToDatabaseAndIndex >> Rond_Run_Af >> End_cycle

    Markeer_Run_Mislukt = tasks_verwerkingsrun.maakMarkeerRunMislukt()
    [Start_Run, tg_loadToDatabaseAndIndex, Rond_Run_Af] >> Markeer_Run_Mislukt

    tasks_verwerkingsrun.voegVerwerkingsrapportToe(dag, End_cycle)
