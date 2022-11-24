import io
import os
import logging
import copy
import shared.config as config

logger = logging.getLogger()



def removeFieldFromFieldset(fieldsets, field):
    fieldsets = copy.deepcopy(fieldsets)
    
    for fieldset in fieldsets:
        if 'fields' in fieldset[1]:
            lst = list(fieldset[1]['fields'])
            fieldset[1]['fields'] = list(filter(lambda a: a != field, lst))
        else:
            for column in fieldset[1]['columns']:
                lst = list(column['fields'])
                column['fields'] = list(filter(lambda a: a != field, lst))
                
    return fieldsets


def isEmpty(s: str):
    return not s or len(s) == 0