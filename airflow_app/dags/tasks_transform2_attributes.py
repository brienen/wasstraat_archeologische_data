from airflow.utils.task_group import TaskGroup
from airflow.operators.python import PythonOperator

import wasstraat.setAttributes_functions as setAttributes_functions
import wasstraat.delta_transform as delta_transform


def getEnhanceAttributesGroup(incrementeel=False):
    """Maak de taakgroep voor Transform 2 (attributen normaliseren).

    Args:
        incrementeel: als True bewerken de taken alleen de documenten met
            delta_run van de actieve verwerkingsrun en werkt een extra taak aan
            het eind de geraakte projecten bij (incrementele cyclus)
    """
    delta_kwargs = {'incrementeel': True} if incrementeel else {}

    tg = TaskGroup(group_id='Transform2_Enhance_Attributes_Group')
    with tg:
        extract_Imagedata_From_FileNames = PythonOperator(
            task_id='extract_Imagedata_From_FileNames',
            python_callable=setAttributes_functions.extractImagedataFromFileNames,
            op_kwargs=delta_kwargs,
        )
        enhance_All_Attributes = PythonOperator(
            task_id='Enhance_All_Attributes',
            python_callable=setAttributes_functions.enhanceAllAttributes,
            op_kwargs=delta_kwargs,
        )


        enhance_All_Attributes >> extract_Imagedata_From_FileNames

        if incrementeel:
            # Transform 2 kan projectcodes aanpassen (gemeenteprofiel, map van foto's)
            Werk_Geraakte_Projecten_Bij = PythonOperator(
                task_id='Werk_Geraakte_Projecten_Bij',
                python_callable=delta_transform.werkGeraakteProjectenBij,
            )
            extract_Imagedata_From_FileNames >> Werk_Geraakte_Projecten_Bij

    return tg
