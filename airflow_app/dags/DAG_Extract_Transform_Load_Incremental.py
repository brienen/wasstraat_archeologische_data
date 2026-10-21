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

"""Incrementeel laden (issue 61): verwerk alleen nieuwe, gewijzigde en verwijderde bronbestanden.

Zie docs/componenten/incrementeel-laden.md voor het ontwerp. Verloop:
Start_Run → Bepaal_Delta → Opruimen_Oude_Records → Extract (delta) →
Transform 1 → 2 → 3 → 5 (move/merge) → 4 (stabiele sleutels en referenties) →
Load_Upsert (upsert naar PostgreSQL) → Index_<tabel> (parallel, Elasticsearch-delta)
→ Index_Klaar → Registreer_Run.

De taken gebruiken het run-document (wasstraat.verwerkingsrun) in plaats van
XCom, zodat 'airflow dags test' en handmatige aanroepen hetzelfde werken.
Registreer_Run zet de run pas op 'afgerond' als Load_Upsert is geslaagd én alle
Index-taken klaar zijn (Index_Klaar, trigger rule all_done), zodat een volgende
run niet kan starten terwijl de indexering nog loopt. Markeer_Run_Mislukt
bewaakt alle taken tot en met Registreer_Run, maar niet de Index-taken: een
haperende Elasticsearch maakt de run niet ongeldig, want de data in PostgreSQL
klopt dan al (de Airflow-run wordt wel rood via End_ETL_incremental). Een
mislukte indexering herstel je door de Index-taak opnieuw te draaien; de
volgende incrementele run indexeert ook alle rijen opnieuw.
"""
from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.dummy import DummyOperator
from airflow.operators.python import PythonOperator
from airflow.utils.trigger_rule import TriggerRule

import shared.config as config
import shared.fulltext as fulltext
import tasks_extract
import tasks_transform1_harmonize
import tasks_transform2_attributes
import tasks_transform3_keys
import tasks_transform4_references
import tasks_transform5_moveAndMerge
import wasstraat.verwerkingsrun as verwerkingsrun
import wasstraat.bronbestanden as bronbestanden
import wasstraat.opruimen as opruimen
import wasstraat.loadToDatabase_functions as loadToDatabase


with DAG(
    dag_id='Extract_Transform_Load_Incremental',
    start_date=datetime(2021, 1, 1),
    schedule_interval=None,
    catchup=False,
    max_active_runs=1,
    dagrun_timeout=timedelta(minutes=480),
    template_searchpath="/opt/airflow"
) as dag:
    Start_ETL_incremental = DummyOperator(
        task_id='Start_ETL_incremental',
    )

    # Stap 0: run-document aanmaken (faalt als er al een actieve run is)
    Start_Run = PythonOperator(
        task_id='Start_Run',
        python_callable=verwerkingsrun.startRun,
        op_kwargs={'soort': verwerkingsrun.SOORT_INCREMENTEEL, 'airflow_run_id': '{{ run_id }}'}
    )

    # Stap 1: bronbestanden scannen en vergelijken met Def_Bronbestand
    Bepaal_Delta = PythonOperator(
        task_id='Bepaal_Delta',
        python_callable=bronbestanden.bepaalDelta
    )

    # Stap 2: records van gewijzigde en verwijderde bestanden verwijderen
    Opruimen_Oude_Records = PythonOperator(
        task_id='Opruimen_Oude_Records',
        python_callable=opruimen.verwijderOudeRecords
    )

    # Stap 3: extractie van alleen de delta
    tg_import = tasks_extract.getExtractTaskGroup(incrementeel=True)

    # Stap 4 t/m 7: transformaties van alleen de delta (fase 2)
    tg_harmonize = tasks_transform1_harmonize.getHarmonizeTaskGroup(incrementeel=True)
    tg_enhanceAttrs = tasks_transform2_attributes.getEnhanceAttributesGroup(incrementeel=True)
    tg_keys = tasks_transform3_keys.getSetKeysTaskGroup(incrementeel=True)
    tg_moveAndMerge = tasks_transform5_moveAndMerge.getMoveAndMergeTaskGroup(incrementeel=True)
    # Transform 4 kent in elke DAG stabiele sleutels toe (issue 71); geen delta-variant nodig
    tg_references = tasks_transform4_references.getSetReferencesTaskGroup()

    # Stap 8: upsert van Single_Store_Clean naar de Def_-tabellen in PostgreSQL, in dezelfde
    # transactie gevolgd door de herberekening van de afgeleide velden (issue 72)
    Load_Upsert = PythonOperator(
        task_id='Load_Upsert',
        python_callable=loadToDatabase.loadIncrementeel
    )

    # Stap 9: Elasticsearch-delta per tabel (parallel). Niet bewaakt door Markeer_Run_Mislukt.
    index_taken = []
    for table in loadToDatabase.LOAD_TABELLEN:
        index_taken.append(PythonOperator(
            task_id=f'Index_{table}',
            python_callable=fulltext.indexTableIncrementeel,
            op_kwargs={'table': table}
        ))

    # Wacht tot alle Index-taken klaar zijn, ook als er een mislukt: de run blijft actief
    # tot de indexering klaar is, maar een mislukte indexering maakt de run niet 'mislukt'
    Index_Klaar = DummyOperator(
        task_id='Index_Klaar',
        trigger_rule=TriggerRule.ALL_DONE
    )

    # Stap 10: registratie bijwerken en run afronden; draait alleen als Load_Upsert (en alles
    # ervoor) slaagde en de Index-taken klaar zijn
    Registreer_Run = PythonOperator(
        task_id='Registreer_Run',
        python_callable=bronbestanden.registreerBronbestanden
    )

    # Bij een mislukte taak: run-document op 'mislukt', zodat een volgende run kan starten.
    # De registratie wordt dan niet bijgewerkt; de volgende run pakt dezelfde bestanden opnieuw op.
    Markeer_Run_Mislukt = PythonOperator(
        task_id='Markeer_Run_Mislukt',
        python_callable=verwerkingsrun.markeerRunMislukt,
        op_kwargs={'airflow_run_id': '{{ run_id }}'},
        trigger_rule=TriggerRule.ONE_FAILED
    )

    End_ETL_incremental = DummyOperator(
        task_id='End_ETL_incremental',
    )

    Start_ETL_incremental >> Start_Run >> Bepaal_Delta >> Opruimen_Oude_Records >> tg_import
    tg_import >> tg_harmonize >> tg_enhanceAttrs >> tg_keys >> tg_moveAndMerge >> tg_references
    tg_references >> Load_Upsert >> index_taken >> Index_Klaar
    [Load_Upsert, Index_Klaar] >> Registreer_Run >> End_ETL_incremental
    # Een mislukte Index-taak maakt de Airflow-run rood (End_ETL_incremental upstream_failed)
    index_taken >> End_ETL_incremental

    # De Index-taken staan bewust niet in deze lijst: een mislukte indexering zet de run niet op 'mislukt'
    bewaakt = [Start_Run, Bepaal_Delta, Opruimen_Oude_Records, tg_import, tg_harmonize, tg_enhanceAttrs,
               tg_keys, tg_moveAndMerge, tg_references, Load_Upsert, Registreer_Run]
    bewaakt >> Markeer_Run_Mislukt
