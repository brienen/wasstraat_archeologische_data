import pandas as pd
import numpy as np


def keys_exists(element, *keys):
    '''
    Check if *keys (nested) exists in `element` (dict).
    '''
    if not isinstance(element, dict):
        raise AttributeError('keys_exists() expects dict as first argument.')
    if len(keys) == 0:
        raise AttributeError('keys_exists() expects at least two arguments, one given.')

    _element = element
    for key in keys:
        try:
            _element = _element[key]
        except KeyError:
            return False
    return True


def is_empty(item):
    if not item or item is None or pd.isna(item) or item == "":
        return True
    else: 
        return False

def not_empty(item):
    return not is_empty(item)

'''
Return first non empty value
'''
def firstValue(*kargs):
    for x in kargs:
        if not_empty(x):
            return x
    return None


def safe_row_to_dict(row, keep_fields=None):
    """Converteer DataFrame-rij naar dict, verwijder NaN maar behoud essenti\u00eble velden."""
    d = row.dropna().to_dict()
    if keep_fields:
        for field in keep_fields:
            if field in row.index and field not in d:
                d[field] = None  # Behoud veld met None i.p.v. het te verwijderen
    return d