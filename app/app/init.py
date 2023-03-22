from models import Project, Artefact, Spoor, Vondst, Objectfoto
import shared.config as config
import shared.database as database
import shared.fulltext as fulltext
from sqlalchemy.orm import sessionmaker
from sqlalchemy import create_engine, func, update, inspect, MetaData
from sqlalchemy import and_, or_
from elasticsearch import Elasticsearch
from flask import current_app


import logging
logger = logging.getLogger(__name__)

    
    
def initSequences():
    logger.info("Initializing Sequences of flask database...")
    try:
        engine = create_engine(config.SQLALCHEMY_DATABASE_URI)
        inspector = inspect(engine)
        seqs = inspector.get_sequence_names()

        for table_name in database.getAllTables():
            try:
                with engine.connect() as con:
                    rs = con.execute(f'SELECT MAX(primary_key) FROM public."{table_name}"')
                    max_value = rs.first()
                    max_value = max_value[0]+1 if max_value[0] else 1
    
                    seq = f"{table_name}_primary_key_seq"
                    if seq in seqs:
                        logger.info(f"Setting sequence {seq} to value {max_value}...")
                        rs = con.execute(f'alter sequence public."{seq}" restart with {max_value};')
                    else:
                        logger.warning(f"Could not set sequence {seq} to value {max_value}...")
            except Exception as e:
                logger.error(f"Error while Initializing Sequences for table {table} with message {e}")

    except Exception as e:
        logger.error("Error while Initializing Sequences of flask database with message " + str(e))



def init():
    logger.info("Initializing Redundant Data in 6 phases (might take a few minutes)...")
    db = create_engine(config.SQLALCHEMY_DATABASE_URI)
    try: 
        Session = sessionmaker(bind=db)
        session = Session()

        # Set aantal foto's per artefact
        session.execute(update(Artefact).values(aantal_fotos=0))
        rs = session.query(Artefact.primary_key, func.count(Objectfoto.primary_key)).select_from(Objectfoto).join(Objectfoto.artefact).group_by(Artefact)        
        for row in rs:
            artf = session.query(Artefact).get(row[0])
            artf.aantal_fotos = row[1] if row[1] else 0
        logger.info("Initializing Redundant Data phase 1 finished.")

        # Set aantal artefacten per project
        session.execute(update(Project).values(aantal_artefacten=0))
        rs = session.query(Project.primary_key, func.count(Artefact.primary_key)).select_from(Artefact).join(Artefact.project).group_by(Project)        
        for row in rs:
            proj = session.query(Project).get(row[0])
            proj.aantal_artefacten = row[1] if row[1] else 0
        logger.info("Initializing Redundant Data phase 2 finished.")

        # Set aantal spoor- en vondstdatering
        session.execute(update(Artefact).values(spoordatering_vanaf=None, spoordatering_tot=None, vondstdatering_vanaf=None, vondstdatering_tot=None, datering_vanaf=None, datering_tot=None))
        logger.info("Initializing Redundant Data phase 3 finished.")

        # First set artefactdatering
        rs = (session.query(Artefact.primary_key, Artefact.artefactdatering_vanaf, Artefact.artefactdatering_tot)
            .filter(or_(Artefact.artefactdatering_vanaf != None, Artefact.artefactdatering_tot != None))
        )
        for row in rs:
            artf = session.query(Artefact).get(row[0])
            artf.datering_vanaf = row[1] 
            artf.datering_tot = row[2]
        logger.info("Initializing Redundant Data phase 4 finished.")


        # First set vondstdatering
        rs = (session.query(Artefact.primary_key, Vondst.vondstdatering_vanaf, Vondst.vondstdatering_tot)
            .join(Vondst, Vondst.primary_key==Artefact.vondstID)
            .filter(or_(Vondst.vondstdatering_vanaf != None, Vondst.vondstdatering_tot != None))
        )
        for row in rs:
            artf = session.query(Artefact).get(row[0])
            artf.vondstdatering_vanaf = row[1] 
            artf.vondstdatering_tot = row[2]
        logger.info("Initializing Redundant Data phase 5 finished.")


        # Set spoordatering
        rs = (session.query(Artefact.primary_key, Spoor.spoordatering_vanaf, Spoor.spoordatering_tot)
            .join(Vondst, Vondst.primary_key==Artefact.vondstID)
            .join(Spoor, Spoor.primary_key==Vondst.spoorID)
            .filter(or_(Spoor.spoordatering_vanaf != None, Spoor.spoordatering_tot != None))
        )
        for row in rs:
            artf = session.query(Artefact).get(row[0])
            artf.spoordatering_vanaf = row[1]
            artf.spoordatering_tot = row[2]
        logger.info("Initializing Redundant Data phase 6 finished.")

        session.commit()
        logger.info("Initializing Redundant Data finished.")

    except Exception as e:
        session.rollback()
        logger.error("Error while Initializing Redundant with message " + str(e))
    finally:
        session.close()
        logger.info("Initializing Redundant Data ended...")


def indexAll() :
    tables = database.getAllTables()        
    logger.info(f"Indexing all table {tables}")
    for table in tables:
        try:
            logger.info(f'Indexing table {table}...')
            fulltext.indexTable(table)
        except Exception as e:
            logger.error(f"Error while Indexing table {table} with message {e}")
    logger.info(f"Indexing all table finished.")


def initIfNotInit():
    logger.info("Initializing if...")
    db = create_engine(config.SQLALCHEMY_DATABASE_URI)
    try: 
        Session = sessionmaker(bind=db)
        session = Session()

        # Set aantal foto's per artefact
        logger.info(f"Setting redundant data, first check...")
        cnt = session.query(Artefact).filter(Artefact.aantal_fotos > 0).count()
        if cnt == 0:
            logger.info(f"No count of aantal foto's found: initializing count aantal foto's")
            init()
        else:
            logger.info(f"Count of aantal foto's found: not initializing.")

    except Exception as e:
        session.rollback()
        logger.error("Error while Initializing with message " + str(e))
    finally:
        session.close()
        logger.info("Initializing Redundant Data ended...")

    try:
        # Index tables with elastic
        logger.info(f"Indexing tables, first check...")
        es = Elasticsearch(config.ES_HOST)
        if not es.indices.exists(index="def_artefact"):
            logger.info(f"No index def_artefact found: indexing all tables")
            indexAll()
        else:
            logger.info(f"index def_artefact found: not indexing")
    except Exception as e:
        logger.error(f"Error while indexing tables with message {e}")

    logger.info("Initializing if finished.")





