from elasticsearch import Elasticsearch, helpers

import shared.config as config
import shared.const as const
import logging

import sqlalchemy as db
from sqlalchemy.orm import sessionmaker
from sqlalchemy import create_engine, inspect
from sqlalchemy.engine import reflection

logger = logging.getLogger()

def getCols(connection, table):
    insp = inspect(connection)
    db_cols = insp.get_columns(table)
    db_cols = [col for col in db_cols if (col['name'] == 'primary_key' 
        or 'text' in str(col['type']).lower() 
        or 'varchar' in str(col['type']).lower() 
        or 'enum' in str(col['type']).lower()) and col['name'] not in const.SKIP_FULLTEXT]
    return db_cols


def generate_docs(resultset, db_col_names, index_name):
    for row in resultset:
        doc = {
            "_index": index_name,
            "_id": int(row["primary_key"]),
        }
        for col in db_col_names:
            doc[col.lower()] = str(row[col] if str(row[col]) != 'None' else '')
        yield doc


def indexTable(table):
    logger.info(f"Starting indexing table {table} for fulltext indexing...")

    engine = create_engine(config.SQLALCHEMY_DATABASE_URI)
    logger.info("Connecting to " + config.SQLALCHEMY_DATABASE_URI)
    es = Elasticsearch(config.ES_HOST)

    alias_name = table.lower()
    # Maak een timestamped index-naam voor zero-downtime indexering
    import time
    new_index = f"{alias_name}_{int(time.time())}"

    with engine.connect() as connection:
        connection = connection.execution_options(
            isolation_level="SERIALIZABLE",
            postgresql_deferrable=True
        )
        with connection.begin():
            metadata = db.MetaData(bind=engine)
            db.MetaData.reflect(metadata)

            #get the table list
            dict_tables = metadata.tables.keys()
            lst_tables = [x for x in list(dict_tables) if x.startswith('Def_')]
            logger.info("Indexing all string fields for " + str(lst_tables))

            if table in lst_tables:
                db_cols = getCols(connection, table)
                sql_col_names = ['"'+col['name']+ '"' for col in db_cols]
                db_col_names = [col['name'] for col in db_cols]

                sql = f'SELECT {", ".join(sql_col_names)} FROM public."{table}"'
                logger.info(f"Indexing new index {new_index} with columns {db_col_names}")
                rs = connection.execute(sql)

                # Stap 1: Maak nieuwe index aan en vul met data
                es.indices.create(index=new_index, ignore=400)
                try:
                    helpers.bulk(es, generate_docs(rs, db_col_names, new_index))
                    new_count = es.count(index=new_index)['count']
                    logger.info(f"New index {new_index} has {new_count} records")
                except Exception as bulk_err:
                    # Bij falen: verwijder de nieuwe index, de oude blijft intact
                    logger.error(f"Bulk indexing failed for {new_index}: {bulk_err}")
                    es.indices.delete(index=new_index, ignore=[400, 404])
                    raise

                # Stap 2: Zoek bestaande indexen onder de alias
                old_indices = []
                if es.indices.exists_alias(name=alias_name):
                    old_indices = list(
                        es.indices.get_alias(name=alias_name).keys()
                    )

                # Stap 3: Atomic alias swap
                actions = [{"add": {"index": new_index, "alias": alias_name}}]
                for old_idx in old_indices:
                    actions.append({"remove": {"index": old_idx, "alias": alias_name}})

                es.indices.update_aliases(body={"actions": actions})
                logger.info(f"Alias {alias_name} now points to {new_index}")

                # Stap 4: Ruim oude indexen op
                for old_idx in old_indices:
                    es.indices.delete(index=old_idx, ignore=[400, 404])
                    logger.info(f"Deleted old index {old_idx}")

                # Stap 5: Migratie - als de alias nog niet bestond maar de oude
                # index wel (eerste keer na upgrade), verwijder de oude index
                if not old_indices and es.indices.exists(index=alias_name):
                    # Er is een fysieke index met de alias-naam: rename scenario
                    # Dit treedt alleen op bij de eerste run na de upgrade
                    logger.info(f"Migratie: oude index {alias_name} gevonden zonder alias, opruimen...")
                    es.indices.delete(index=alias_name, ignore=[400, 404])

            else:
                logger.error(f"Trying to index table {table}, but table not available in {lst_tables}")
