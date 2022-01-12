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
import tasks_extract
import tasks_transform3_references
import tasks_transform1_harmonize
import tasks_transform2_attributes
import wasstraat.mongoUtils as mongoUtils
import wasstraat.setAttributes_functions as setAttributes_functions
import wasstraat.loadToDatabase_functions as loadToDatabase


rootDir = str(config.AIRFLOW_INPUTDIR)
tmpDir = str(config.AIRFLOW_TEMPDIR)

with DAG(
    dag_id='Extract_Transform_Load_Full_Cycle',
    start_date=datetime(2021, 1, 1),
    catchup=False,
    dagrun_timeout=timedelta(minutes=60),
    template_searchpath="/opt/airflow"
) as dag:
    Start_ETL_full_cycle = DummyOperator(
        task_id='Start_ETL_full_cycle',
    )

    #def importImages(rootDir, mongo_uri, db_files, db_staging):   
    Drop_All_Databases = PythonOperator(
        task_id='Drop_All_Databases',
        python_callable=mongoUtils.dropAll,
        op_kwargs={}
    )
    #def importImages(rootDir, mongo_uri, db_files, db_staging):   
    LoadToDatabase_postgres = PythonOperator(
        task_id='LoadToDatabase_postgres',
        python_callable=loadToDatabase.loadAll,
        op_kwargs={}
    )

    End_ETL_full_cycle = DummyOperator(
        task_id='End_ETL_full_cycle',
    )
    
    tg_import = tasks_extract.getExtractTaskGroup()
    tg_harmonize = tasks_transform1_harmonize.getHarmonizeTaskGroup()
    tg_enhanceAttrs = tasks_transform2_attributes.getEnhanceAttributesGroup()
    tg_references = tasks_transform3_references.getSetReferencesTaskGroup()


    Start_ETL_full_cycle >> Drop_All_Databases >> tg_import >> tg_harmonize >> tg_enhanceAttrs >> tg_references >> LoadToDatabase_postgres >> End_ETL_full_cycle 
