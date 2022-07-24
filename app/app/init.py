from models import Project, Artefact, Foto, Spoor, Vondst
import shared.config as config
from sqlalchemy.orm import sessionmaker
from sqlalchemy import create_engine, func, update, inspect, MetaData
from sqlalchemy import and_, or_

import logging
logger = logging.getLogger()
    
    
def initSequences():
    logger.info("Initializing Sequences of flask database...")
    try:
        engine = create_engine(config.SQLALCHEMY_DATABASE_URI)
        inspector = inspect(engine)
        seqs = inspector.get_sequence_names()

        for table_name in inspector.get_table_names():
            if 'Def_' in table_name:
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
        logger.error("Error while Initializing Sequences of flask database with message " + str(e))



def init():
    logger.info("Initializing Redundant Data...")
    db = create_engine(config.SQLALCHEMY_DATABASE_URI)
    try: 
        Session = sessionmaker(bind=db)
        session = Session()

        # Set aantal foto's per artefact
        session.execute(update(Artefact).values(aantal_fotos=0))
        rs = session.query(Artefact.primary_key, func.count(Foto.primary_key)).select_from(Foto).join(Foto.artefact).group_by(Artefact)        
        for row in rs:
            artf = session.query(Artefact).get(row[0])
            artf.aantal_fotos = row[1] if row[1] else 0

        # Set aantal artefacten per project
        session.execute(update(Project).values(aantal_artefacten=0))
        rs = session.query(Project.primary_key, func.count(Artefact.primary_key)).select_from(Artefact).join(Artefact.project).group_by(Project)        
        for row in rs:
            proj = session.query(Project).get(row[0])
            proj.aantal_artefacten = row[1] if row[1] else 0

        # Set aantal spoor- en vondstdatering
        session.execute(update(Artefact).values(spoordatering_vanaf=None, spoordatering_tot=None, vondstdatering_vanaf=None, vondstdatering_tot=None, datering_vanaf=None, datering_tot=None))

        # First set artefactdatering
        rs = (session.query(Artefact.primary_key, Artefact.artefactdatering_vanaf, Artefact.artefactdatering_tot)
            .filter(or_(Artefact.artefactdatering_vanaf != None, Artefact.artefactdatering_tot != None))
        )
        for row in rs:
            artf = session.query(Artefact).get(row[0])
            artf.datering_vanaf = row[1] 
            artf.datering_tot = row[2]


        # First set vondstdatering
        rs = (session.query(Artefact.primary_key, Vondst.vondstdatering_vanaf, Vondst.vondstdatering_tot)
            .join(Vondst, Vondst.primary_key==Artefact.vondstID)
            .filter(or_(Vondst.vondstdatering_vanaf != None, Vondst.vondstdatering_tot != None))
        )
        for row in rs:
            artf = session.query(Artefact).get(row[0])
            artf.vondstdatering_vanaf = row[1] 
            artf.vondstdatering_tot = row[2]


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

        session.commit()
    except Exception as e:
        session.rollback()
        logger.error("Error while Initializing Redundant with message " + str(e))
    finally:
        session.close()
        logger.info("Initializing Redundant Data ended...")
