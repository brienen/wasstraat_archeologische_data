from airflow.utils.task_group import TaskGroup
from airflow.operators.python import PythonOperator

import wasstraat.setAttributes_functions as setAttributes_functions


def getEnhanceAttributesGroup():

    tg = TaskGroup(group_id='Transform2_Enhance_Attributes_Group')
    with tg:
        extract_Imagedata_From_FileNames = PythonOperator(
            task_id='extract_Imagedata_From_FileNames',
            python_callable=setAttributes_functions.extractImagedataFromFileNames,
        )
        enhance_All_Attributes = PythonOperator(
            task_id='Enhance_All_Attributes',
            python_callable=setAttributes_functions.enhanceAllAttributes
        )

        
        enhance_All_Attributes >> extract_Imagedata_From_FileNames
        
    return tg