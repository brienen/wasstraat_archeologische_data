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

"""Volledige cyclus: leeg MongoDB en verwerk alle bronbestanden opnieuw.

Verloop: Start_Run → Drop_All_Databases → Extract → Transform 1 → 2 → 3 → 5 → 4 →
LoadToDatabase_postgres → Index_<tabel> (parallel) → Index_Klaar → Registreer_Bronbestanden.

Foutbeleid (issue 54, zie wasstraat/foutbeleid.py): de run heeft vanaf het begin een
run-document (soort volledig). Faalt een cruciale taak, dan zet Markeer_Run_Mislukt de run
op 'mislukt' en faalt de DAG. Een mislukte Index-taak is een waarschuwing: de load is dan
al gelukt, de registratie gaat door en de DAG slaagt; de waarschuwing staat in het
run-document en het verwerkingsrapport. Elke taak legt bij een fout de foutmelding vast in
de meldingen van het run-document (on_failure_callback).

Verwerkingsrapport (issue 62): na alle andere taken, ook na een fout, schrijft de taak
Verwerkingsrapport een rapport (JSON en Markdown) in AIRFLOW_OUTPUT_RAPPORTEN.
"""
from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.dummy import DummyOperator
from airflow.operators.python import PythonOperator

import shared.config as config
import tasks_extract
import tasks_transform3_keys
import tasks_transform1_harmonize
import tasks_transform2_attributes
import tasks_transform4_references
import tasks_transform5_moveAndMerge
import tasks_verwerkingsrun
import wasstraat.mongoUtils as mongoUtils
import wasstraat.bronbestanden as bronbestanden
import wasstraat.verwerkingsrun as verwerkingsrun
import tasks_load_to_database_and_index



with DAG(
    dag_id='Extract_Transform_Load_Full_Cycle',
    start_date=datetime(2021, 1, 1),
    schedule_interval=None,
    catchup=False,
    max_active_runs=1,
    dagrun_timeout=timedelta(minutes=480),
    template_searchpath="/opt/airflow",
    default_args=tasks_verwerkingsrun.getDefaultArgs(),
) as dag:
    Start_ETL_full_cycle = DummyOperator(
        task_id='Start_ETL_full_cycle',
    )

    # Run-document (soort volledig) vóór het legen van de databases; dropAll laat de
    # collectie Verwerkingsruns staan. Faalt als er al een run actief is.
    Start_Run = tasks_verwerkingsrun.maakStartRun(verwerkingsrun.SOORT_VOLLEDIG)

    Drop_All_Databases = PythonOperator(
        task_id='Drop_All_Databases',
        python_callable=mongoUtils.dropAll,
        op_kwargs={}
    )
    End_ETL_full_cycle = DummyOperator(
        task_id='End_ETL_full_cycle',
    )
    
    tg_import = tasks_extract.getExtractTaskGroup()
    tg_harmonize = tasks_transform1_harmonize.getHarmonizeTaskGroup()
    tg_enhanceAttrs = tasks_transform2_attributes.getEnhanceAttributesGroup()
    tg_keys = tasks_transform3_keys.getSetKeysTaskGroup()
    tg_references = tasks_transform4_references.getSetReferencesTaskGroup()
    tg_moveAndMerge = tasks_transform5_moveAndMerge.getMoveAndMergeTaskGroup()
    tg_loadToDatabaseAndIndex = tasks_load_to_database_and_index.getLoadToDatabaseAndIndexTaskGroup()


    Start_ETL_full_cycle >> Start_Run >> Drop_All_Databases >> tg_import >> tg_harmonize >> tg_enhanceAttrs >> tg_keys >> tg_moveAndMerge >> tg_references >> tg_loadToDatabaseAndIndex

    # Registreer aan het eind alle bronbestanden als verwerkt (incrementeel laden, issue 61),
    # zodat een volgende incrementele run weet wat al verwerkt is, en rond de run af. De
    # registratie hangt aan de load naar PostgreSQL en wacht op de Elasticsearch-indexering
    # (Index_Klaar, all_done), maar hangt niet af van het slagen ervan: een mislukte index kan
    # los opnieuw (DAG_Load_Only) zonder de bronbestanden opnieuw te verwerken.
    Registreer_Bronbestanden = PythonOperator(
        task_id='Registreer_Bronbestanden',
        python_callable=bronbestanden.registreerVolledigeCyclus
    )
    tg_loadToDatabaseAndIndex >> Registreer_Bronbestanden >> End_ETL_full_cycle

    # Bij een mislukte cruciale taak: run-document op 'mislukt'. De Index-taken zijn niet bewaakt.
    Markeer_Run_Mislukt = tasks_verwerkingsrun.maakMarkeerRunMislukt()
    bewaakt = [Start_Run, Drop_All_Databases, tg_import, tg_harmonize, tg_enhanceAttrs, tg_keys,
               tg_moveAndMerge, tg_references, tg_loadToDatabaseAndIndex, Registreer_Bronbestanden]
    bewaakt >> Markeer_Run_Mislukt

    # Verwerkingsrapport na alle andere taken, vóór de eindtaak (die de eindstatus van de DAG bepaalt)
    tasks_verwerkingsrun.voegVerwerkingsrapportToe(dag, End_ETL_full_cycle)
