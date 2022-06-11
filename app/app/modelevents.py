from sqlalchemy import event
from sqlalchemy.orm import Session
from models import Artefact, Foto



@event.listens_for(Session, "before_flush")
def before_flush(session, flush_context, instances):
    print("Before flush")
    for obj in session.new:
        if isinstance(obj, Artefact):
            project = obj.project
            if project:            
                project.aantal_artefacten =  project.aantal_artefacten + 1 if project.aantal_artefacten else 1
        if isinstance(obj, Foto):
            artf = obj.artefact
            if artf:            
                artf.aantal_fotos =  artf.aantal_fotos + 1 if artf.aantal_fotos else 1

    for obj in session.deleted:
        if isinstance(obj, Artefact):
            project = obj.project
            if project:            
                obj.project.aantal_artefacten =  obj.project.aantal_artefacten - 1 if obj.project.aantal_artefacten else 0
        if isinstance(obj, Foto):
            artf = obj.artefact
            if artf:            
                artf.aantal_fotos =  artf.aantal_fotos - 1 if artf.aantal_fotos else 0



