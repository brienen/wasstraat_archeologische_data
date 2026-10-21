import datetime

from sqlalchemy import event
from sqlalchemy.orm import Session
from models import Artefact, Objectfoto, Project, Conserveringsproject, assoc_artefact_conservering



@event.listens_for(Session, "before_flush")
def before_flush(session, flush_context, instances):
    print("Before flush")
    for obj in session.new:
        if isinstance(obj, Artefact):
            project = obj.project
            if project:            
                project.aantal_artefacten =  project.aantal_artefacten + 1 if project.aantal_artefacten else 1
        if isinstance(obj, Objectfoto):
            artf = obj.artefact
            if artf:            
                artf.aantal_fotos =  artf.aantal_fotos + 1 if artf.aantal_fotos else 1

    for obj in session.deleted:
        if isinstance(obj, Artefact):
            project = obj.project
            if project:            
                obj.project.aantal_artefacten =  obj.project.aantal_artefacten - 1 if obj.project.aantal_artefacten else 0
        if isinstance(obj, Objectfoto):
            artf = obj.artefact
            if artf:            
                artf.aantal_fotos =  artf.aantal_fotos - 1 if artf.aantal_fotos else 0
        if isinstance(obj, (Artefact, Project)):
            markeerBruiklenen(obj)


def markeerBruiklenen(obj):
    """Vul de markering van de bruiklenen van een artefact of project dat de gebruiker verwijdert (issue 73).

    artefactID en projectID van een bruikleen mogen leeg zijn; de ORM maakt ze bij het
    verwijderen van het artefact of project leeg. Met de markering (key en tijdstip) blijft
    zichtbaar waar de bruikleen bij hoorde, net als wanneer de laadstap een artefact of
    project uit de brondata ziet verdwijnen.
    """
    relatie = 'artefact' if isinstance(obj, Artefact) else 'project'
    for bruikleen in obj.bruiklenen:
        setattr(bruikleen, f'{relatie}_verdwenen_key', obj.key)
        setattr(bruikleen, f'{relatie}_verdwenen_op', datetime.datetime.now())


@event.listens_for(Conserveringsproject, "before_delete")
def verwijderLosgekoppeldeArtefactregels(mapper, connection, target):
    """Verwijder de koppelrijen van een conserveringsproject waarvan het artefact verdwenen is (issue 73).

    De relatie artefacten ziet rijen met een lege artefact_id niet, dus de ORM verwijdert
    ze niet; zonder deze stap zou de verwijzing conservering_id het verwijderen blokkeren.
    """
    connection.execute(assoc_artefact_conservering.delete().where(
        assoc_artefact_conservering.c.conservering_id == target.primary_key,
        assoc_artefact_conservering.c.artefact_id.is_(None)))



