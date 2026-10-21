import os
import numpy as np
from datetime import timedelta

from airflow.utils.task_group import TaskGroup
from airflow.operators.bash import BashOperator
from airflow.operators.dummy import DummyOperator
from airflow.operators.python import PythonOperator

import shared.config as config
from wasstraat.image_import import importImages, getAndStoreImageFilenames, controleerAfbeeldingen
from wasstraat.extract_referentietabellen import extractAllRefs
from wasstraat.extract_extra_projects import extractExtraProjects
from wasstraat.bronbestanden import getLijstbestandPad

NUM_PROCESSOR = 8


def getImportMDBCommand(invoermap, collectie, categorie, incrementeel=False):
    """Bouw het bash-commando voor importMDB.sh.

    Args:
        invoermap: map met de Access-databases
        collectie: staging-collectie
        categorie: invoercategorie (bepaalt het lijstbestand bij incrementeel laden)
        incrementeel: als True alleen de bestanden uit het lijstbestand van Bepaal_Delta verwerken

    Returns:
        Bash-commando (met afsluitende spatie, zodat Airflow het niet als template-bestand leest)
    """
    if incrementeel:
        return "${AIRFLOW_HOME}/scripts/importMDB.sh %s %s %s " % (invoermap, collectie, getLijstbestandPad(categorie))
    return "${AIRFLOW_HOME}/scripts/importMDB.sh %s %s " % (invoermap, collectie)


def getExtractTaskGroup(incrementeel=False):
    """Maak de taakgroep voor de extractie.

    Args:
        incrementeel: als True verwerken de BashOperators alleen de lijstbestanden
            van Bepaal_Delta en lezen de Python-taken alleen de delta uit de
            actieve verwerkingsrun (incrementele cyclus)
    """
    tg1 = TaskGroup(group_id='Extract_Group')
    with tg1:
        first = DummyOperator(task_id="first")
        last = DummyOperator(task_id="last")

        # [START howto_operator_bash]
        Extract_Data_From_Projecten = BashOperator(
            task_id='Extract_Data_From_Projecten',
            bash_command=getImportMDBCommand(config.AIRFLOW_INPUT_PROJECTEN, config.COLL_STAGING_OUD, 'projecten', incrementeel)
        )
        # [START howto_operator_bash]
        Extract_Data_From_Projectenlijst = BashOperator(
            task_id='Extract_Data_From_Projectenlijst',
            bash_command=getImportMDBCommand(config.AIRFLOW_INPUT_PROJECTENLIJST, config.COLL_STAGING_PROJECTENLIJST, 'projectenlijst', incrementeel)
        )
        # [START howto_operator_bash]
        Extract_Data_From_Magazijnlijst = BashOperator(
            task_id='Extract_Data_From_Magazijnlijst',
            bash_command=getImportMDBCommand(config.AIRFLOW_INPUT_MAGAZIJNLIJST, config.COLL_STAGING_MAGAZIJNLIJST, 'magazijnlijst', incrementeel)
        )
        # [START howto_operator_bash]
        Extract_Data_From_Fotolijst = BashOperator(
            task_id='Extract_Data_From_Fotolijst',
            bash_command=getImportMDBCommand(config.AIRFLOW_INPUT_FOTOLIJST, config.COLL_STAGING_FOTOLIJST, 'fotolijst', incrementeel)
        )
        Extract_Data_From_MonsterDB = BashOperator(
            task_id='Extract_Data_From_MonsterDB',
            bash_command=getImportMDBCommand(config.AIRFLOW_INPUT_MONSTER, config.COLL_STAGING_MONSTER, 'monsterdatabase', incrementeel)
        )
        Extract_Data_From_RapportaneDBs = BashOperator(
            task_id='Extract_Data_From_RapportaneDBs',
            bash_command=getImportMDBCommand(config.AIRFLOW_INPUT_RAPPORTEN, config.COLL_STAGING_RAPPORTEN, 'rapporten', incrementeel)
        )
        GetAndStoreImageFilenames = PythonOperator(
            task_id='GetAndStoreImageFilenames',
            python_callable=getAndStoreImageFilenames,
            op_kwargs={'incrementeel': incrementeel},
        )
        Extract_Referentietabellen = PythonOperator(
            task_id='Extract_Referentietabellen',
            python_callable=extractAllRefs,
            op_kwargs={'incrementeel': incrementeel},
        )
        Extract_ExtraProjecten = PythonOperator(
            task_id='Extract_ExtraProjecten',
            python_callable=extractExtraProjects,
            op_kwargs={'incrementeel': incrementeel},
        )
        # Na alle import-taken: tel verwerkte, overgeslagen en mislukte bestanden en faal
        # boven de drempel (issue 70). Zit vóór 'last', dus vóór de transformatie; in de
        # incrementele cyclus valt de taak daarmee onder Markeer_Run_Mislukt.
        Controleer_Afbeeldingen = PythonOperator(
            task_id='Controleer_Afbeeldingen',
            python_callable=controleerAfbeeldingen,
            op_kwargs={'incrementeel': incrementeel},
        )
        first >> GetAndStoreImageFilenames
        i=0
        while i < NUM_PROCESSOR:
            tsk = PythonOperator(
                task_id='Extract_Data_From_Fotos_' + str(i),
                python_callable=importImages,
                op_kwargs={'index': i, 'of': NUM_PROCESSOR},
                retries=5,
                retry_delay=timedelta(minutes=1)

            )
            GetAndStoreImageFilenames >> tsk >> Controleer_Afbeeldingen
            i += 1
        Controleer_Afbeeldingen >> last
        
        
        first >> [Extract_Data_From_Projecten, Extract_Data_From_Projectenlijst, Extract_Data_From_Magazijnlijst, Extract_Data_From_Fotolijst, Extract_Data_From_MonsterDB, Extract_Data_From_RapportaneDBs, Extract_Referentietabellen] >> Extract_ExtraProjecten >> last
        
    return tg1