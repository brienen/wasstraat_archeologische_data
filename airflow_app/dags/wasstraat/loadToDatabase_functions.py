import sqlalchemy as db
import pymongo
import pandas as pd
import numpy as np
import sqlalchemy
import wasstraat.meta as meta
import wasstraat.archutils as ut


from sqlalchemy.orm import sessionmaker
from sqlalchemy import create_engine, inspect
from sqlalchemy.engine import reflection
from geoalchemy2 import Geometry, WKTElement
from shapely.geometry import Point
from sqlalchemy.sql import null as sqlnull
from operator import itemgetter 

import shared.config as config
import shared.database as database 
import logging
logger = logging.getLogger("airflow.task")




def getAnalyseCleanCollection():   
    myclient = pymongo.MongoClient(str(config.MONGO_URI))
    analyseDb = myclient[str(config.DB_ANALYSE)]
    return analyseDb[config.COLL_ANALYSE_CLEAN]


# Set coordinates to WKT to be able to transfer them to the database 
def setWKT(x,y):  
    # Check for empty coordinates so not to get errors
    if x is np.nan or y is np.nan or not(x>1):
        return None
    try:
        point = Point(x,y)
        return WKTElement(point.wkt, srid=4326)
    except:
        return None

def getFields(col, soort):
    lst_fields = meta.getVeldnamen(soort)
    logger.info(f'lstfields {lst_fields}')
    set_fields = set(lst_fields)

    df = pd.DataFrame(list(col.find({'soort': soort})))
    set_fields.update(df.columns)
    result = list(set_fields)
    result.sort()
    return result



def transferToDB(objecttype, soort, table, connection):
    try:
        insp = inspect(connection)
        db_columns = insp.get_columns(table)

        col = getAnalyseCleanCollection()
        lst_fields = getFields(col, soort)

        df = pd.DataFrame(list(col.find({'soort': soort}, projection=lst_fields)), columns=lst_fields)
        df_load = df.rename(columns={'ID':'primary_key'})
        if '_id' in df_load.columns:
            df_load['_id'] = df_load['_id'].astype(str)
        if 'imageID' in df_load.columns:
            df_load['imageID'] = df_load['imageID'].astype(str)
        if 'herkomst' in df_load.columns:
            df_load['herkomst'] = df_load['herkomst'].astype(str)
        if 'brondata' in df_load.columns:
            df_load['brondata'] = df_load['brondata'].astype(str)
        if 'latitude' in df_load.columns and 'longitude' in df_load.columns:
            df_load['location'] = df_load.apply(lambda x: setWKT(x['longitude'], x['latitude']),axis=1)

        
        df_columnnames = df_load.columns
        db_columnnames = list(map(itemgetter('name'), db_columns))
        lst_intersect_columnnames = list((x) for x in db_columnnames if x in df_columnnames)
        
        # Get list of columnsnames that are not in intersection
        df_columnnames_nomatch = list(set(df_columnnames) - set(lst_intersect_columnnames))
        if len(df_columnnames_nomatch) > 0:
            logger.warning("Bij het laden van data van " + soort + ' naar tabel ' + table + ' werd volgende data aangeboden die de tabel niet ondersteunt: ' + str(df_columnnames_nomatch))
        db_columnnames_nomatch = list(set(db_columnnames) - set(lst_intersect_columnnames))
        if len(df_columnnames_nomatch) > 0:
            logger.warning("Bij het laden van data van " + soort + ' naar tabel ' + table + ' verwachtte de tabel de volgende data die niet werd aangeboden: ' + str(db_columnnames_nomatch))
        
        lst = list(map(itemgetter('name', 'type'), db_columns))
        dict_intersect_columns = dict((x) for x in lst if x[0] in df_columnnames)
        df_load = df_load[lst_intersect_columnnames]

        # Truncate columns that are too long and set numeric values if required
        for column in df_load.columns:
            lst_columns = [col for col in db_columns if col['name'] == column]
            if len(lst_columns) > 0:
                column_def = lst_columns[0]
            else:
                continue
            if 'VARCHAR' in str(column_def['type']) and column_def['type'].length:
                df_load[column] = df_load[column].apply(lambda x: str(x)[0:column_def['type'].length] if x and str(x) != 'nan' else "")
            if 'INTEGER' in str(column_def['type']):
                df_load[column] = df_load[column].apply(lambda x: pd.to_numeric(x, errors='coerce', downcast='integer'))
            if 'DOUBLE' in str(column_def['type']):
                df_load[column] = df_load[column].apply(lambda x: pd.to_numeric(x, errors='coerce', downcast='float'))
            if 'BOOL' in str(column_def['type']):
                df_load[column] = df_load[column].apply(lambda x: ut.convertToBool(x))
            if 'DATE' in str(column_def['type']):
                df_load[column] = df_load[column].apply(lambda x: ut.convertToDate(x, True))

            

        # df_load.fillna(sqlnull(), inplace=True) #@ Returns Error
        logger.info(f"Transfering: {soort} with {len(df_load)} records")
        df_load.to_sql(table, con=connection, if_exists='append', index=False, dtype=dict_intersect_columns)

    except Exception as err:
        msg = "Onbekende fout bij laden van soort: "+soort+" in tabel "+table+" van database met melding: " + str(err)
        logger.error(msg)
        raise Exception(msg) from err




def loadAll():
    logger.info("Starting Loading data to relational database...")

    engine = create_engine(config.SQLALCHEMY_DATABASE_URI)
    logger.info("Connecting to " + config.SQLALCHEMY_DATABASE_URI)

    lst_tables = ['Def_ABR', 'Def_Project', 'Def_Put', 'Def_Vondst', 'Def_Spoor', 'Def_Stelling', 'Def_Doos', 'Def_Standplaats', 'Def_Plaatsing', 'Def_Vlak', 'Def_Vindplaats', 'Def_Artefact', 'Def_Bestand', 'Def_Vulling', 'Def_Monster', 'Def_Monster_Botanie', 'Def_Monster_Schelp', 'Def_DT_Soort_Plant', 'Def_DT_Soort_Schelp', 'Def_DT_Soort_Deel', 'Def_DT_Soort_Staat']

    # Extra tabellen die ook getruncated worden (niet in de hoofdlijst)
    extra_truncate_tables = ['Def_artefact_abr', 'Def_Bruikleen', 'Def_artefact_conservering', 'Def_Conserveringsproject']

    with engine.connect() as connection:
        with connection.begin():
            logger.info("FASE 1: Laden naar tijdelijke tabellen...")
            logger.info("Loading all data for " + str(lst_tables))

            # Houd bij welke temp-tabellen aangemaakt zijn voor opruiming bij falen
            temp_tables_created = []

            try:
                for table in lst_tables:
                    if table.startswith('Def_'):
                        soort = table[4:]  # Remove Def_
                        temp_table = f"{table}_new"

                        # Drop eventuele oude temp-tabel
                        connection.execute(f'DROP TABLE IF EXISTS "{temp_table}"')

                        # Maak temp-tabel aan met dezelfde structuur (inclusief constraints)
                        connection.execute(
                            f'CREATE TABLE "{temp_table}" (LIKE "{table}" INCLUDING ALL)'
                        )
                        temp_tables_created.append((table, temp_table))

                        # Laad data in de temp-tabel
                        transferToDB(table, soort, temp_table, connection)
                        logger.info(f"Geladen: {soort} -> {temp_table}")

            except Exception as err:
                # Bij falen: ruim temp-tabellen op, bestaande data blijft intact
                logger.error(f"Laden naar temp-tabellen mislukt: {err}. Opruimen...")
                for orig, temp in temp_tables_created:
                    try:
                        connection.execute(f'DROP TABLE IF EXISTS "{temp}"')
                    except Exception:
                        pass
                raise

            logger.info("FASE 2: Atomic swap van tabellen...")

            # Schakel foreign key checks tijdelijk uit voor de swap
            connection.execute('SET session_replication_role = replica;')

            try:
                # Atomic swap: rename old -> _old, rename new -> current
                for orig, temp in temp_tables_created:
                    old_table = f"{orig}_old"
                    connection.execute(f'DROP TABLE IF EXISTS "{old_table}"')
                    connection.execute(f'ALTER TABLE "{orig}" RENAME TO "{old_table}"')
                    connection.execute(f'ALTER TABLE "{temp}" RENAME TO "{orig}"')

                # Truncate de extra tabellen
                f = lambda x: '"' + str(x) + '"'
                lst_extra = list(map(f, extra_truncate_tables))
                connection.execute('TRUNCATE ' + ','.join(lst_extra) + ';')

            finally:
                # Herstel foreign key checks
                connection.execute('SET session_replication_role = DEFAULT;')

            # Ruim oude tabellen op
            logger.info("FASE 3: Opruimen oude tabellen...")
            for orig, temp in temp_tables_created:
                old_table = f"{orig}_old"
                connection.execute(f'DROP TABLE IF EXISTS "{old_table}"')

            logger.info("Laden naar database succesvol afgerond.")