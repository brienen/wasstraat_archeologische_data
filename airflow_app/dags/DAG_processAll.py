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
    dag_id='Process_All_Except_Import',
    start_date=datetime(2021, 1, 1),
    catchup=False,
    dagrun_timeout=timedelta(minutes=60),
    template_searchpath="/opt/airflow"
) as dag:
    start_process = DummyOperator(
        task_id='start_process',
    )

    #def importImages(rootDir, mongo_uri, db_files, db_staging):   
    Drop_Analyse = PythonOperator(
        task_id='Drop_Analyse',
        python_callable=mongoUtils.dropAnalyse,
        op_kwargs={}
    )
    #def importImages(rootDir, mongo_uri, db_files, db_staging):   
    Drop_SingleStore = PythonOperator(
        task_id='Drop_SingleStore',
        python_callable=mongoUtils.dropSingleStore,
        op_kwargs={}
    )
    #def importImages(rootDir, mongo_uri, db_files, db_staging):   
    Drop_SingleStore_Clean = PythonOperator(
        task_id='Drop_SingleStore_Clean',
        python_callable=mongoUtils.dropSingleStoreClean,
        op_kwargs={}
    )
    #def importImages(rootDir, mongo_uri, db_files, db_staging):   
    Clean_function = PythonOperator(
        task_id='Clean_function',
        python_callable=clean.clean,
        op_kwargs={}
    )
    #def importImages(rootDir, mongo_uri, db_files, db_staging):   
    DbLoader_function = PythonOperator(
        task_id='DbLoader_function',
        python_callable=dbloader.loadAll,
        op_kwargs={}
    )

    end_process = DummyOperator(
        task_id='end_process',
    )
    
    tg_collect = tasks_collect.getCollectTaskGroup()
    tg_extract = tasks_extract.getExtractTaskGroup()


    start_process >> Drop_Analyse >> Drop_SingleStore >> Drop_SingleStore_Clean >> tg_collect >> Clean_function >> tg_extract >> DbLoader_function >> end_process 
