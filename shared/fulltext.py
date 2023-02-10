from elasticsearch import Elasticsearch, helpers

import shared.config as config
import shared.const as const
import logging

import sqlalchemy as db
from sqlalchemy.orm import sessionmaker
from sqlalchemy import create_engine, inspect
from sqlalchemy.engine import reflection

logger = logging.getLogger()


def generate_docs(resultset, db_col_names, index_name):
    for row in resultset:
        doc = {
            "_index": index_name,
            "_id": int(row["primary_key"]),
            "doc": {col.lower(): str(row[col] if str(row[col]) != 'None' else '') for col in db_col_names}
        }
        doc['doc']['id'] = int(row["primary_key"])
        yield doc


def indexTable(table):
    logger.info(f"Starting indexing table {table} for fulltext indexing...")

    engine = create_engine(config.SQLALCHEMY_DATABASE_URI)
    logger.info("Connecting to " + config.SQLALCHEMY_DATABASE_URI)
    es = Elasticsearch(config.ES_HOST)
    
    index_name = table.lower()

    with engine.connect() as connection:
        connection = connection.execution_options( 
            isolation_level="SERIALIZABLE",
            postgresql_deferrable=True # Does not seem to work. Work imn progress 
        )
        with connection.begin():
            metadata = db.MetaData(bind=engine)
            db.MetaData.reflect(metadata)

            #get the table list
            dict_tables = metadata.tables.keys()
            lst_tables = [x for x in list(dict_tables) if x.startswith('Def_')]
            logger.info("Indexing all string fields for " + str(lst_tables))

            if table in lst_tables:
                insp = inspect(connection)
                db_cols = insp.get_columns(table)
                db_cols = [col for col in db_cols if (col['name'] == 'primary_key' or 'text' in str(col['type']).lower() or 'varchar' in str(col['type']).lower()) and col['name'] not in const.SKIP_FULLTEXT]
                sql_col_names = ['"'+col['name']+ '"' for col in db_cols]
                db_col_names = [col['name'] for col in db_cols]
                
                sql = f'SELECT {", ".join(sql_col_names)} FROM public."{table}"'
                logger.info(f"Indexing index {index_name} with columns {db_col_names} ")
                rs = connection.execute(sql)
                
                resp = es.indices.delete(index=index_name, ignore=[400,404])
                logger.info(f"Deleted index {index_name} with response {resp} ")
                logger.info(f"Indexing index {index_name} with columns {db_col_names} ")
                es.indices.create(index = index_name, ignore=400)
                helpers.bulk(es, generate_docs(rs, db_col_names, index_name))
                logger.info(f"Indexed {es.count(index=index_name)} records")                
            else:
                logger.error(f"Trying to index table {table}, but table not available in {lst_tables}")
