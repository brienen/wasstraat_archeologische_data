import os
from datetime import datetime, timedelta

from airflow.utils.task_group import TaskGroup
from airflow.operators.bash import BashOperator
from airflow.operators.dummy import DummyOperator
from airflow.operators.python import PythonOperator

import config
import wasstraat.mongoUtils as mongoUtils
import wasstraat.references_functions as references_functions
import wasstraat.setAttributes_functions as setAttributes_functions
import wasstraat.meta as meta


def getSetReferencesTaskGroup():

    tg1 = TaskGroup(group_id='Transform3_Set_References_Group')
    with tg1:
        Set_Reference_Keys_Stellingen = PythonOperator(
            task_id='Set_Reference_Keys_Stellingen',
            python_callable=references_functions.setReferenceKeys,
            op_kwargs={'pipeline': meta.getReferenceKeysPipeline('Stelling'), 'soort': 'Stelling'}
        )
        Set_Reference_Keys_Magazijnlijst = PythonOperator(
            task_id='Set_Reference_Keys_Magazijnlijst',
            python_callable=references_functions.setReferenceKeys,
            op_kwargs={'pipeline': meta.getReferenceKeysPipeline('Magazijnlocatie'), 'soort': 'Magazijnlocatie'}
        )
        Set_Reference_Keys_Plaatsing = PythonOperator(
            task_id='Set_Reference_Keys_Plaatsing',
            python_callable=references_functions.setReferenceKeys,
            op_kwargs={'pipeline': meta.getReferenceKeysPipeline('Plaatsing'), 'soort': 'Plaatsing'}
        )
        Set_Reference_Keys_Dozen = PythonOperator(
            task_id='Set_Reference_Keys_Dozen',
            python_callable=references_functions.setReferenceKeysDozen,
        )
        Set_Reference_Keys_Putten = PythonOperator(
            task_id='Set_Reference_Keys_Putten',
            python_callable=references_functions.setReferenceKeys,
            op_kwargs={'pipeline': meta.getReferenceKeysPipeline('Put'), 'soort': 'Put'}
        )
        Set_Reference_Keys_Vlakken = PythonOperator(
            task_id='Set_Reference_Keys_Vlakken',
            python_callable=references_functions.setReferenceKeys,
            op_kwargs={'pipeline': meta.getReferenceKeysPipeline('Vlak'), 'soort': 'Vlak'}
        )
        Set_Reference_Keys_Sporen = PythonOperator(
            task_id='Set_Reference_Keys_Sporen',
            python_callable=references_functions.setReferenceKeys,
            op_kwargs={'pipeline': meta.getReferenceKeysPipeline('Spoor'), 'soort': 'Spoor'}
        )
        Set_Reference_Keys_Vondsten = PythonOperator(
            task_id='Set_Reference_Keys_Vondsten',
            python_callable=references_functions.setReferenceKeys,
            op_kwargs={'pipeline': meta.getReferenceKeysPipeline('Vondst'), 'soort': 'Vondst'}
        )
        Set_Reference_Keys_Projecten = PythonOperator(
            task_id='Set_Reference_Keys_Projecten',
            python_callable=references_functions.setReferenceKeys,
            op_kwargs={'pipeline': meta.getReferenceKeysPipeline('Project'), 'soort': 'Project'}
        )
        Set_Reference_Keys_Vindplaatsen = PythonOperator(
            task_id='Set_Reference_Keys_Vindplaatsen',
            python_callable=references_functions.setReferenceKeys,
            op_kwargs={'pipeline': meta.getReferenceKeysPipeline('Vindplaats'), 'soort': 'Vindplaats'}
        )
        Set_Reference_Keys_Artefacts = PythonOperator(
            task_id='Set_Reference_Keys_Artefacts',
            python_callable=references_functions.setReferenceKeys,
            op_kwargs={'pipeline': meta.getReferenceKeysPipeline('Artefact'), 'soort': 'Artefact'}
        )
        Set_Reference_Keys_Fotos = PythonOperator(
            task_id='Set_Reference_Keys_Fotos',
            python_callable=references_functions.setReferenceKeys,
            op_kwargs={'pipeline': meta.getReferenceKeysPipeline('Foto'), 'soort': 'Foto'}
        )
        Set_Artefactnr_Unique = PythonOperator(
            task_id='Set_Artefactnr_Unique',
            python_callable=references_functions.setArtefactnrUnique,
        )
        Set_AllReferences = PythonOperator(
            task_id='Set_AllReferences',
            python_callable=references_functions.setAllReferences,
        )

        
        Set_Artefactnr_Unique >> [Set_Reference_Keys_Stellingen, Set_Reference_Keys_Magazijnlijst, Set_Reference_Keys_Plaatsing, Set_Reference_Keys_Dozen, Set_Reference_Keys_Putten, Set_Reference_Keys_Vlakken, Set_Reference_Keys_Sporen, Set_Reference_Keys_Vondsten, Set_Reference_Keys_Projecten, Set_Reference_Keys_Vindplaatsen, Set_Reference_Keys_Artefacts, Set_Reference_Keys_Fotos] >> Set_AllReferences 
        
    return tg1