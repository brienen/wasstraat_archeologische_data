import os
from datetime import datetime, timedelta

from airflow.utils.task_group import TaskGroup
from airflow.operators.bash import BashOperator
from airflow.operators.dummy import DummyOperator
from airflow.operators.python import PythonOperator

import config
import wasstraat.mongoUtils as mongoUtils
import wasstraat.extract_functions as extract_functions
import wasstraat.meta as meta


def getExtractTaskGroup():

    tg1 = TaskGroup(group_id='Extract_Group')
    with tg1:
        Extract_Stellingen = PythonOperator(
            task_id='Extract_Stellingen',
            python_callable=extract_functions.extractGeneric,
            op_kwargs={'pipeline': meta.getExtractPipeline('Stelling'), 'soort': 'Stelling'}
        )
        Extract_Magazijnlijst = PythonOperator(
            task_id='Extract_Magazijnlijst',
            python_callable=extract_functions.extractGeneric,
            op_kwargs={'pipeline': meta.getExtractPipeline('Magazijnlocatie'), 'soort': 'Magazijnlocatie'}
        )
        Extract_Plaatsing = PythonOperator(
            task_id='Extract_Plaatsing',
            python_callable=extract_functions.extractGeneric,
            op_kwargs={'pipeline': meta.getExtractPipeline('Plaatsing'), 'soort': 'Plaatsing'}
        )
        Extract_Dozen = PythonOperator(
            task_id='Extract_Dozen',
            python_callable=extract_functions.extractDozen,
        )
        Extract_Putten = PythonOperator(
            task_id='Extract_Putten',
            python_callable=extract_functions.extractGeneric,
            op_kwargs={'pipeline': meta.getExtractPipeline('Put'), 'soort': 'Put'}
        )
        Extract_Vlakken = PythonOperator(
            task_id='Extract_Vlakken',
            python_callable=extract_functions.extractGeneric,
            op_kwargs={'pipeline': meta.getExtractPipeline('Vlak'), 'soort': 'Vlak'}
        )
        Extract_Sporen = PythonOperator(
            task_id='Extract_Sporen',
            python_callable=extract_functions.extractGeneric,
            op_kwargs={'pipeline': meta.getExtractPipeline('Spoor'), 'soort': 'Spoor'}
        )
        Extract_Vondsten = PythonOperator(
            task_id='Extract_Vondsten',
            python_callable=extract_functions.extractGeneric,
            op_kwargs={'pipeline': meta.getExtractPipeline('Vondst'), 'soort': 'Vondst'}
        )
        Extract_Projecten = PythonOperator(
            task_id='Extract_Projecten',
            python_callable=extract_functions.extractGeneric,
            op_kwargs={'pipeline': meta.getExtractPipeline('Project'), 'soort': 'Project'}
        )
        Extract_Vindplaatsen = PythonOperator(
            task_id='Extract_Vindplaatsen',
            python_callable=extract_functions.extractGeneric,
            op_kwargs={'pipeline': meta.getExtractPipeline('Vindplaats'), 'soort': 'Vindplaats'}
        )
        Extract_Artefacts = PythonOperator(
            task_id='Extract_Artefacts',
            python_callable=extract_functions.extractGeneric,
            op_kwargs={'pipeline': meta.getExtractPipeline('Artefact'), 'soort': 'Artefact'}
        )
        Extract_Fotos = PythonOperator(
            task_id='Extract_Fotos',
            python_callable=extract_functions.extractGeneric,
            op_kwargs={'pipeline': meta.getExtractPipeline('Foto'), 'soort': 'Foto'}
        )
        Extract_Imagedata_FromFile_Names = PythonOperator(
            task_id='Extract_Imagedata_FromFile_Names',
            python_callable=extract_functions.extractImagedataFromFileNames,
        )
        Set_Artefactnr_Unique = PythonOperator(
            task_id='Set_Artefactnr_Unique',
            python_callable=extract_functions.setArtefactnrUnique,
        )
        Set_AllReferences = PythonOperator(
            task_id='Set_AllReferences',
            python_callable=extract_functions.setAllReferences,
        )

        
        Extract_Imagedata_FromFile_Names >> Set_Artefactnr_Unique >> [Extract_Stellingen, Extract_Magazijnlijst, Extract_Plaatsing, Extract_Dozen, Extract_Putten, Extract_Vlakken, Extract_Sporen, Extract_Vondsten, Extract_Projecten, Extract_Vindplaatsen, Extract_Artefacts, Extract_Fotos] >> Set_AllReferences 
        
    return tg1