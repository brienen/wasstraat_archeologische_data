from elasticsearch import Elasticsearch, helpers

import shared.config as config
import shared.const as const
from shared.logutils import maskeerWachtwoord
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
    logger.info(f"Connecting to {maskeerWachtwoord(config.SQLALCHEMY_DATABASE_URI)}")
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

                # Stap 2: Migratie - als er een fysieke index bestaat met de
                # alias-naam (oude situatie vóór de upgrade naar aliassen),
                # moet die EERST verwijderd worden. Anders blokkeert
                # Elasticsearch het aanmaken van een alias met dezelfde naam.
                if es.indices.exists(index=alias_name):
                    is_alias = es.indices.exists_alias(name=alias_name)
                    if not is_alias:
                        logger.info(
                            f"Migratie: fysieke index '{alias_name}' gevonden "
                            f"(geen alias). Verwijderen om alias mogelijk te maken..."
                        )
                        es.indices.delete(index=alias_name, ignore=[400, 404])

                # Stap 3: Zoek bestaande indexen onder de alias
                old_indices = []
                if es.indices.exists_alias(name=alias_name):
                    old_indices = list(
                        es.indices.get_alias(name=alias_name).keys()
                    )

                # Stap 4: Atomic alias swap
                actions = [{"add": {"index": new_index, "alias": alias_name}}]
                for old_idx in old_indices:
                    actions.append({"remove": {"index": old_idx, "alias": alias_name}})

                es.indices.update_aliases(body={"actions": actions})
                logger.info(f"Alias {alias_name} now points to {new_index}")

                # Stap 5: Ruim oude indexen op
                for old_idx in old_indices:
                    es.indices.delete(index=old_idx, ignore=[400, 404])
                    logger.info(f"Deleted old index {old_idx}")

            else:
                logger.error(f"Trying to index table {table}, but table not available in {lst_tables}")


def getIndexenVanAlias(es, alias_name):
    """Retourneer de namen van de indexen achter een alias (lege lijst als de alias niet bestaat)."""
    if not es.indices.exists_alias(name=alias_name):
        return []
    return sorted(es.indices.get_alias(name=alias_name).keys())


def leesIdsUitIndex(es, index):
    """Lees alle document-id's uit een index (helpers.scan zonder _source).

    Returns:
        Set met de id's als integer (de primary_key)
    """
    query = {'query': {'match_all': {}}, '_source': False}
    return {int(hit['_id']) for hit in helpers.scan(es, index=index, query=query)}


def indexTableIncrementeel(table):
    """Werk de Elasticsearch-index van een tabel bij na een incrementele load (issue 61, fase 3).

    Bestaat er een alias voor de tabel (zoals indexTable die aanmaakt), dan
    worden alle rijen van de tabel in de index achter de alias geïndexeerd
    (dezelfde documenten als generate_docs, _id = primary_key; een bestaand
    document wordt overschreven) en daarna de documenten verwijderd waarvan
    de _id niet meer in de tabel staat. Bestaat er geen alias (of wijst die
    naar meer dan één index), dan volgt een volledige indexering met indexTable.

    Args:
        table: tabelnaam, bijv. 'Def_Artefact'

    Returns:
        Dict met 'index', 'geindexeerd' en 'verwijderd' (of 'volledig': True)
    """
    logger.info(f"Starting incremental indexing of table {table}...")
    es = Elasticsearch(config.ES_HOST)
    alias_name = table.lower()

    indexen = getIndexenVanAlias(es, alias_name)
    if len(indexen) != 1:
        if indexen:
            logger.warning(f"Alias {alias_name} wijst naar {len(indexen)} indexen ({indexen}); volledige indexering.")
        else:
            logger.info(f"Geen alias {alias_name} gevonden; volledige indexering van {table}.")
        indexTable(table)
        return {'index': alias_name, 'volledig': True}
    index = indexen[0]

    engine = create_engine(config.SQLALCHEMY_DATABASE_URI)
    ids_tabel = set()
    try:
        with engine.connect() as connection:
            if not inspect(connection).has_table(table, schema='public'):
                logger.error(f"Trying to index table {table}, but table not available")
                return None
            db_cols = getCols(connection, table)
            sql_col_names = ['"' + col['name'] + '"' for col in db_cols]
            db_col_names = [col['name'] for col in db_cols]
            sql = f'SELECT {", ".join(sql_col_names)} FROM public."{table}"'
            logger.info(f"Indexing existing index {index} (alias {alias_name}) with columns {db_col_names}")
            rs = connection.execute(sql)

            def docsMetIds():
                for doc in generate_docs(rs, db_col_names, index):
                    ids_tabel.add(doc['_id'])
                    yield doc

            geindexeerd, _ = helpers.bulk(es, docsMetIds())
    finally:
        engine.dispose()

    weg = sorted(leesIdsUitIndex(es, index) - ids_tabel)
    verwijderd = 0
    if weg:
        verwijderd, _ = helpers.bulk(es, ({'_op_type': 'delete', '_index': index, '_id': i} for i in weg))
    es.indices.refresh(index=index)

    resultaat = {'index': index, 'geindexeerd': geindexeerd, 'verwijderd': verwijderd}
    logger.info(f"Incremental indexing of {table} finished: {resultaat}")
    return resultaat
