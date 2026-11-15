"""Harmonisatie-Excel (Transform 1): per object de MongoDB-pipeline van staging naar Single_Store.

Het blad ``Objecten`` noemt per object de tabelpatronen (``Tabellen``), het
object waarvan het de velden overerft (``Overerven``) en de ABR-codes; per
object geeft een eigen blad de veldtoewijzing (``Attribute`` en ``Kolommen``).
``loadHarmonizer`` leest de Excel en bouwt de pipelines; ``getHarmonizer`` en
``getHarmonizeAggr`` gebruiken een cache per Excel-pad, zodat een taak die de
pipelines van veel soorten nodig heeft (de load via meta.getVeldnamen, de
voorrang bij de harmonisatie) de Excel één keer leest.
"""
import os

import shared.config as config
import pandas as pd
import re
import copy
import ast
import wasstraat.util as util
import wasstraat.meta as meta
import wasstraat.foutbeleid as foutbeleid

import logging
logger = logging.getLogger("airflow.task")


AIRFLOW_WASSTRAAT_CONFIG = config.AIRFLOW_WASSTRAAT_CONFIG
HARMONIZE_AGGR = [
    {'$match': {"table": {"$in" : ["XXX","YYY"]}}},
    {"$match": {"table": {"$in" : ["XXX","YYY"]}}},
    {"$replaceRoot" : {"newRoot" : {"_id" : "$_id", "brondata" : "$$ROOT"}}},
    {"$addFields" : { 
        "projectcd" : "$brondata.projectcd"}}
    ,{ "$merge": { "into": { "db": config.DB_ANALYSE, "coll": config.COLL_ANALYSE }, "on": "_id",  "whenMatched": "replace", "whenNotMatched": "insert"}}
]
# Object in het blad Objecten met de tabelpatronen die geen enkele pipeline harmoniseert
OBJECT_IGNORE = 'Ignore'
# Cache van de gelezen Excel: pad -> (tijdstip van laatste wijziging, DataFrame uit loadHarmonizer)
_HARMONIZER_CACHE = {}


def getAggrTables(root, tabellen, include): 
    lst_tabellen = ast.literal_eval(tabellen)
    if len(lst_tabellen) == 0:
        root["table"] = {"$in" : []} if include else {"$not": {"$in" : []}}
    elif len(lst_tabellen) == 1:
        regx = re.compile(lst_tabellen[0], re.IGNORECASE)
        #root["table"] = {'$regex': lst_tabellen[0], '$options': 'i'} if include else {"$not": {'$regex': lst_tabellen[0], '$options': 'i'}}
        root["table"] = regx if include else {"$not": regx}
    else:
        or_lst = []
        for tabel in lst_tabellen:
            regx = re.compile(tabel, re.IGNORECASE)
            #or_lst.append({"table": {'$regex': tabel, '$options': 'i'}} if include else {"table": {"$not": {'$regex': tabel, '$options': 'i'}}})
            or_lst.append({"table": regx} if include else {"table": {"$not": regx}})
        root = {"$or": or_lst} if include else {"$and": or_lst}
    return root


def getKolomValues(kolommen):
    if len(kolommen) == 0:
        return None
    elif len(kolommen) == 1:
        return "$brondata." + kolommen[0]
    else:
        val = kolommen.pop(0)
        return {'$ifNull': ["$brondata." + val, getKolomValues(kolommen)]}

    
def getAttributes(root, df_attributes):
    for index, row in df_attributes.iterrows():        
        kolommen = row['Kolommen']
        if re.match(r"\[.*\]", str(kolommen)):
            kolommen = ast.literal_eval(kolommen)
            root[row['Attribute']] = getKolomValues(kolommen)
        else:
            root[row['Attribute']] = kolommen
        
    return root


# initialize all attributes so that they can be used for inheritenace
def initAttributes(xl):
    aggr = copy.deepcopy(HARMONIZE_AGGR)
    lst_objecten = xl['Objecten']['Object'].unique()
    aggr = aggr[3]['$addFields']
    return { obj:getAttributes(copy.deepcopy(aggr), xl[obj]) for obj in lst_objecten if obj in xl.keys() }


def createAggr(soort, tabellen, tabellen_Ignore, xl, attrs, abr_materiaal, abr_submateriaal):
    aggr = copy.deepcopy(HARMONIZE_AGGR)

    idx_addfields = 3
    # Fase Negative match
    aggr[0]["$match"] = getAggrTables(aggr[0]["$match"], tabellen_Ignore, False)
    # Fase Positive match
    aggr[1]["$match"] = getAggrTables(aggr[1]["$match"], tabellen, True)
    # Fase create addFields from inherited Class
    overerven_van = xl['Objecten'][xl['Objecten']['Object'] == soort]['Overerven'].values[0]

    # Fase create inherited fields
    if overerven_van != "" and pd.notna(overerven_van):
        idx_addfields += 1
        aggr_flds = copy.deepcopy(aggr[3])
        aggr_flds['$addFields'] = attrs[overerven_van]
        aggr.insert(idx_addfields-1, aggr_flds)

    # Fase create addFields
    if soort in xl.keys():
        aggr[idx_addfields]['$addFields'] = attrs[soort]
    aggr[idx_addfields]['$addFields']['soort'] = soort

    # Add ABR if available
    if util.not_empty(abr_materiaal):
        aggr[idx_addfields]['$addFields']['abr_materiaal'] = abr_materiaal
    if util.not_empty(abr_submateriaal):
        aggr[idx_addfields]['$addFields']['abr_submateriaal'] = abr_submateriaal

    return aggr
   
    
def loadHarmonizer():
    """Lees de harmonisatie-Excel en bouw per object de pipeline (altijd opnieuw, zonder cache).

    Returns:
        DataFrame met de rijen van het blad Objecten en per rij de pipeline in de kolom ``aggr``
    """
    xl = pd.read_excel(AIRFLOW_WASSTRAAT_CONFIG, sheet_name=None)
    attrs = initAttributes(xl)

    df = xl['Objecten']
    df['Object'] = df['Object'].apply(lambda x: x.strip())
    df['aggr'] = df.apply(lambda x: createAggr(x['Object'], x['Tabellen'], df[df.Object == OBJECT_IGNORE]['Tabellen'].values[0], xl, attrs, x['ABR-materiaal'], x['ABR-submateriaal']), axis=1)

    return df


def _laatstGewijzigd(pad):
    """Tijdstip van de laatste wijziging van een bestand, of None als het niet te bepalen is."""
    try:
        return os.path.getmtime(pad)
    except (OSError, TypeError):
        return None


def getHarmonizer(reload=False):
    """Retourneer de gelezen harmonisatie-Excel (loadHarmonizer) uit de cache.

    De cache houdt per Excel-pad (AIRFLOW_WASSTRAAT_CONFIG) het DataFrame bij.
    De Excel wordt opnieuw gelezen bij ``reload=True``, bij een ander pad en
    als het bestand sinds het lezen is gewijzigd. Wie het DataFrame krijgt,
    mag het niet wijzigen: het is gedeeld (getHarmonizeAggr geeft kopieën).

    Args:
        reload: als True de Excel altijd opnieuw lezen

    Returns:
        DataFrame zoals loadHarmonizer het oplevert
    """
    pad = AIRFLOW_WASSTRAAT_CONFIG
    gewijzigd = _laatstGewijzigd(pad)
    gecached = _HARMONIZER_CACHE.get(pad)
    if reload or gecached is None or gecached[0] != gewijzigd:
        _HARMONIZER_CACHE[pad] = (gewijzigd, loadHarmonizer())
        logger.info(f"Harmonisatie-Excel gelezen: {pad}")
    return _HARMONIZER_CACHE[pad][1]


def resetHarmonizer():
    """Leeg de cache van de harmonisatie-Excel (voor tests en notebooks)."""
    _HARMONIZER_CACHE.clear()


def getHarmonizeAggr(soort, reload=False, df=None):
    """Retourneer de harmonisatie-pipeline van een soort uit de harmonisatie-Excel.

    Args:
        soort: naam van het object in het blad Objecten
        reload: als True de Excel opnieuw lezen (anders uit de cache, getHarmonizer)
        df: optioneel een al gelezen harmonizer (loadHarmonizer of getHarmonizer),
            zodat wie de pipelines van veel soorten nodig heeft de Excel één
            keer leest (voorrang bij de harmonisatie, issue 89); dan wordt de
            cache niet gebruikt

    Returns:
        Lijst met aggregatiefasen (een kopie: aanpassen raakt de cache niet)

    Raises:
        Exception: als het object niet in het blad Objecten staat
    """
    if df is None:
        df = getHarmonizer(reload=reload)

    if not soort in df['Object'].unique():
        msg = 'Error while loading harmonizer, ' + soort + ' does not exist in Excel.'
        logger.error(msg)
        raise Exception(msg)

    # Kopie: de lijst in het (gecachete) DataFrame mag niet bij elke aanroep een fase bijkrijgen
    aggr = copy.deepcopy(df[df.Object == soort]['aggr'].values[0])
    if soort in meta.lst_artefactsoort:
        aggr.insert(-1, { '$addFields': {"artefactsoort": soort, 'soort': 'Artefact'}})
    return aggr


def getOnbekendeObjecten(df=None):
    """Retourneer de objecten in het blad Objecten die geen soort in meta.wasstraat_model zijn.

    Zo'n rij gebruikt de pipeline niet: alleen de soorten uit meta.py krijgen
    een taak Harmonize_<soort>. De rij ``Ignore`` (tabellen die geen enkele
    pipeline harmoniseert) telt niet mee.

    Args:
        df: optioneel een al gelezen harmonizer; standaard getHarmonizer()

    Returns:
        Lijst met objectnamen in de volgorde van het blad
    """
    df = getHarmonizer() if df is None else df
    onbekend = []
    for obj in df['Object']:
        if obj != OBJECT_IGNORE and obj not in meta.wasstraat_model and obj not in onbekend:
            onbekend.append(obj)
    return onbekend


def controleerObjecten():
    """Taak Controleer_Harmonisatie_Excel van Transform 1: meld rijen in het blad Objecten die niet gebruikt worden.

    Een object dat geen soort in meta.wasstraat_model is (bijvoorbeeld een
    verouderde rij), harmoniseert niets. Elke zo'n rij geeft een waarschuwing
    in het log en in het run-document (foutbeleid.SOORT_CONFIGURATIE_ONGELDIG);
    de verwerking gaat door.

    Returns:
        Lijst met de gemelde objecten
    """
    onbekend = getOnbekendeObjecten()
    for obj in onbekend:
        msg = (f"Object {obj} in het blad Objecten van de harmonisatie-Excel ({AIRFLOW_WASSTRAAT_CONFIG}) is geen "
               f"soort van de Wasstraat (meta.wasstraat_model) en wordt niet gebruikt. Verwijder de rij, of "
               f"voeg de soort toe aan meta.py.")
        logger.warning(msg)
        foutbeleid.meld(foutbeleid.NIVEAU_WAARSCHUWING, foutbeleid.SOORT_CONFIGURATIE_ONGELDIG, msg,
                        details={'bestand': os.path.basename(str(AIRFLOW_WASSTRAAT_CONFIG)), 'blad': 'Objecten',
                                 'object': obj})
    if not onbekend:
        logger.info("Alle objecten in het blad Objecten van de harmonisatie-Excel zijn soorten van de Wasstraat.")
    return onbekend
