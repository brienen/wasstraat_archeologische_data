from sqlalchemy.orm import sessionmaker
from sqlalchemy import create_engine, inspect, MetaData
from sqlalchemy.engine import reflection

import shared.config as config
import logging
logger = logging.getLogger("airflow.task")


#Get all tables in Postgres 
def getAllTables():
    logger.info("Starting retrieving tables names from relational database...")

    engine = create_engine(config.SQLALCHEMY_DATABASE_URI)
    logger.info("Connecting to " + config.SQLALCHEMY_DATABASE_URI)

    metadata = MetaData()
    metadata.reflect(bind=engine)
    dict_tables = metadata.tables.keys()
    lst_tables = [x for x in list(dict_tables) if x.startswith('Def_')]
    
    return lst_tables
