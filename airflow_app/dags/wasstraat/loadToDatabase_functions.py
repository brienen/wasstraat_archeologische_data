import sqlalchemy as db
import pymongo
import pandas as pd
import numpy as np
import wasstraat.meta as meta


from sqlalchemy.orm import sessionmaker
from sqlalchemy import create_engine, inspect
from sqlalchemy.engine import reflection
from geoalchemy2 import Geometry, WKTElement
from shapely.geometry import Point

from operator import itemgetter 

import config
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
        df_load.to_sql(table, con=connection, if_exists='append', index=False, dtype=dict_intersect_columns)

    except Exception as err:
        msg = "Onbekende fout bij laden van soort: "+soort+" in tabel "+table+" van database met melding: " + str(err)
        logger.error(msg)
        raise Exception(msg) from err




def loadAll():
    logger.info("Starting Loading data to relational database...")

    engine = create_engine(config.SQLALCHEMY_DATABASE_URI)
    logger.info("Connecting to " + config.SQLALCHEMY_DATABASE_URI)

    with engine.connect() as connection:
        connection = connection.execution_options( 
            isolation_level="SERIALIZABLE",
            postgresql_deferrable=True # Does not seem to work. Work imn progress 
        )
        with connection.begin():
            connection.execute('SET CONSTRAINTS ALL DEFERRED') # Does not seem to work. Work in progress https://stackoverflow.com/questions/48038807/sqlalchemy-orm-deferring-constraint-checking 
            #  ... work with transaction
            metadata = db.MetaData(bind=engine)
            db.MetaData.reflect(metadata)

            #get the table list
            dict_tables = metadata.tables.keys()
            lst_tables = [x for x in list(dict_tables) if x.startswith('Def_')]
            logger.info("Loading all data for " + str(lst_tables))
            
            # To make a comma separated string with substrings between double quotes
            f = lambda x: "\""+str(x)+"\""
            lst = map(f,lst_tables)

            # Truncate all tables
            logger.info("Deleting all data from " + str(lst_tables))
            connection.execute('TRUNCATE ' + ','.join(lst) + ';')

            # Load table to avoid relational integrity issues
            transferToDB('Def_Project', 'Project', 'Def_Project', connection)
            transferToDB('Def_Put', 'Put', 'Def_Put', connection)
            transferToDB('Def_Stelling', 'Stelling', 'Def_Stelling', connection)
            transferToDB('Def_Doos', 'Doos', 'Def_Doos', connection)
            lst_tables.remove('Def_Project')
            lst_tables.remove('Def_Put')
            lst_tables.remove('Def_Stelling')
            lst_tables.remove('Def_Doos')

            # Then load new data
            for table in lst_tables:            
                if table.startswith('Def_'):
                    soort = table[4:] # Remove Def_ 
                    tablename = table
                    logger.info("Transfering: " + soort)
                    transferToDB(table, soort, tablename, connection)
        