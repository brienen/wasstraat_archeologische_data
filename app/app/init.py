from models import Project, Artefact, Foto
import config
from sqlalchemy.orm import sessionmaker
from sqlalchemy import create_engine, func, update

import logging
logger = logging.getLogger()
    
    
def init():
    logger.info("Initializing Data...")
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

        # Set aantal artefacten per projecy
        session.execute(update(Project).values(aantal_artefacten=0))
        rs = session.query(Project.primary_key, func.count(Artefact.primary_key)).select_from(Artefact).join(Artefact.project).group_by(Project)        
        for row in rs:
            proj = session.query(Project).get(row[0])
            proj.aantal_artefacten = row[1] if row[1] else 0

        session.commit()
    except:
        session.rollback()
    finally:
        session.close()
        logger.info("Initializing Data ended...")
