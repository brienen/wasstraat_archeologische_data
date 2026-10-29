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

"""Losse DAG voor Transform 2 (attributen normaliseren) op de bestaande Single_Store.

Bedoeld voor stapsgewijs debuggen van de configuratie en het gemeenteprofiel:
na DAG_Transform1_Harmonize_Only (die Single_Store opnieuw opbouwt) normaliseert
deze DAG de inhoud (projectcodes, nummers, dateringen, coördinaten, gegevens
uit de bestandsnamen van foto's), zodat je het resultaat in MongoDB kunt
bekijken voordat Transform 3, 5 en 4 en de load volgen. Daarna komen
DAG_Transform3_Keys_Only, DAG_Transform_Move_Only (die Single_Store_Clean
leegt en opnieuw vult) en DAG_Transform4_Refs_Only.

De DAG raakt alleen Single_Store en _processing_errors. Tot issue 87 leegde
hij eerst ook Single_Store_Clean (en Single_Store_Doos), een overblijfsel dat
voor Transform 2 niet nodig is: daarna had DAG_Load_Only niets meer om te
laden. Geen run-document en geen verwerkingsrapport; draai na stapsgewijs
werken weer de volledige cyclus voordat je de incrementele cyclus gebruikt.
"""
from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.dummy import DummyOperator

import tasks_transform2_attributes


with DAG(
    dag_id='DAG_Transform2_Enhance_Attributes_Only',
    start_date=datetime(2021, 1, 1),
    schedule_interval=None,
    catchup=False,
    dagrun_timeout=timedelta(minutes=480),
    template_searchpath="/opt/airflow"
) as dag:
    Start_cycle = DummyOperator(
        task_id='Start_cycle',
    )

    End_cycle = DummyOperator(
        task_id='End_cycle',
    )
    tg_enhanceAttrs = tasks_transform2_attributes.getEnhanceAttributesGroup()


    Start_cycle >> tg_enhanceAttrs >> End_cycle
