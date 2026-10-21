"""Verwijzingen vanuit gebruikerstabellen naar tabellen van de pipeline (issue 73).

Gebruikers voeren in de webapplicatie gegevens in die verwijzen naar rijen die
de pipeline vult: een bruikleen verwijst naar een artefact en een project, een
conserveringsproject naar de artefacten die het behandelde, en een artefact
kan extra ABR-materialen hebben. Verdwijnt zo'n rij bij een incrementele run
uit de brondata, dan bepaalt VERWIJZINGEN wat er met de verwijzende rij
gebeurt (uitgevoerd door wasstraat.loadToDatabase_functions):

- LOSKOPPELEN: de rij blijft staan, de verwijzing wordt leeg (NULL) en de
  markering wordt gevuld: <markering>_key met de key van de verdwenen rij (als
  tekst, zodat de gebruiker ziet waar de rij bij hoorde) en <markering>_op met
  het tijdstip. Keert later een rij met dezelfde key terug, dan wordt de
  verwijzing hersteld en de markering gewist.
- VERWIJDEREN: de rij wordt verwijderd. Alleen voor pure koppelrijen zonder
  eigen gegevens, die zonder hun doel niets betekenen.

Daarvoor moeten de verwijzende kolommen leeg mogen zijn en moeten de kolommen
van de markering bestaan. db.create_all() van de webapplicatie maakt alleen
ontbrekende tabellen aan: het voegt geen kolommen toe aan bestaande tabellen
en versoepelt geen NOT NULL. migreerSchema() doet dat wel, idempotent: de
laadstap roept het aan het begin van elke load aan (loadAll en
loadIncrementeel) en de webapplicatie bij het starten, na db.create_all().

Alleen standaardbibliotheek en een DBAPI-cursor (psycopg2): de module draait
in de Airflow-image (dags/shared) en in de Flask-image (app/shared).
"""
import logging

logger = logging.getLogger(__name__)

LOSKOPPELEN = 'loskoppelen'
VERWIJDEREN = 'verwijderen'

# Per verwijzing: de gebruikerstabel en de verwijzende kolom, de tabel van de pipeline waarnaar
# verwezen wordt (op primary_key), het beleid en bij LOSKOPPELEN het voorvoegsel van de markering.
#
# - Def_Bruikleen.artefactID en .projectID: een bruikleen is een eigen registratie (partij,
#   datums) van een voorwerp dat het depot uit is; die mag niet verdwijnen omdat een
#   bronbestand verandert (besluit van de opdrachtgever bij issue 73). Een project kan
#   verdwijnen als het uit de projectenlijst wordt gehaald; daarvoor geldt hetzelfde.
# - Def_artefact_conservering.artefact_id: de koppeling legt vast welke artefacten een
#   conserveringsproject heeft behandeld. Dat is geschiedenis van het conserveringsproject
#   (dat zelf blijft bestaan) en hoort bij de rij te blijven, net als bij een bruikleen.
# - Def_artefact_abr.artefact_id en .abr_materiaal_id: een extra ABR-materiaal van een
#   artefact is een pure koppelrij zonder eigen gegevens; zonder het artefact (of zonder het
#   ABR-begrip) betekent de rij niets meer en wordt hij verwijderd.
#
# Def_artefact_conservering.conservering_id, Def_Bruikleen.partijID en
# Def_Conserveringsproject.uitvoerderID verwijzen naar gebruikerstabellen, die de pipeline
# niet bijwerkt; die staan hier dus niet in.
VERWIJZINGEN = [
    {'tabel': 'Def_Bruikleen', 'kolom': 'artefactID', 'doel': 'Def_Artefact',
     'beleid': LOSKOPPELEN, 'markering': 'artefact_verdwenen'},
    {'tabel': 'Def_Bruikleen', 'kolom': 'projectID', 'doel': 'Def_Project',
     'beleid': LOSKOPPELEN, 'markering': 'project_verdwenen'},
    {'tabel': 'Def_artefact_conservering', 'kolom': 'artefact_id', 'doel': 'Def_Artefact',
     'beleid': LOSKOPPELEN, 'markering': 'artefact_verdwenen'},
    {'tabel': 'Def_artefact_abr', 'kolom': 'artefact_id', 'doel': 'Def_Artefact',
     'beleid': VERWIJDEREN},
    {'tabel': 'Def_artefact_abr', 'kolom': 'abr_materiaal_id', 'doel': 'Def_ABR',
     'beleid': VERWIJDEREN},
]

# Kolomtypen van de markering; in app/app/models.py Text en DateTime
MARKERING_KOLOMMEN = [('_key', 'TEXT'), ('_op', 'TIMESTAMP')]


def getMarkeringKolommen(verwijzing):
    """Geef de kolommen van de markering van een verwijzing met beleid LOSKOPPELEN.

    Args:
        verwijzing: een element van VERWIJZINGEN

    Returns:
        Lijst met (kolomnaam, SQL-type), bijv. [('artefact_verdwenen_key', 'TEXT'),
        ('artefact_verdwenen_op', 'TIMESTAMP')]; leeg bij een ander beleid
    """
    if verwijzing['beleid'] != LOSKOPPELEN:
        return []
    return [(verwijzing['markering'] + achtervoegsel, sql_type) for achtervoegsel, sql_type in MARKERING_KOLOMMEN]


def bepaalSchemawijzigingen(tabel, kolommen):
    """Bepaal de ALTER TABLE-statements die een gebruikerstabel nodig heeft.

    Args:
        tabel: naam van de gebruikerstabel
        kolommen: dict met de bestaande kolommen van de tabel: kolomnaam -> is_nullable
            ('YES' of 'NO', zoals information_schema.columns); leeg als de tabel niet bestaat

    Returns:
        Lijst met SQL-statements; leeg als het schema al klopt of de tabel niet bestaat
    """
    if not kolommen:
        return []
    statements = []
    for verwijzing in VERWIJZINGEN:
        if verwijzing['tabel'] != tabel or verwijzing['beleid'] != LOSKOPPELEN:
            continue
        if kolommen.get(verwijzing['kolom']) == 'NO':
            statements.append(f'ALTER TABLE "{tabel}" ALTER COLUMN "{verwijzing["kolom"]}" DROP NOT NULL')
        for naam, sql_type in getMarkeringKolommen(verwijzing):
            if naam not in kolommen:
                statements.append(f'ALTER TABLE "{tabel}" ADD COLUMN IF NOT EXISTS "{naam}" {sql_type}')
    return statements


def migreerSchema(cursor):
    """Breng het schema van de gebruikerstabellen in orde voor VERWIJZINGEN (idempotent).

    Maakt de verwijzende kolommen met beleid LOSKOPPELEN nullable (DROP NOT
    NULL) en voegt de kolommen van de markering toe. Leest eerst de kolommen
    uit information_schema en voert alleen de ALTER TABLE-statements uit die
    nodig zijn: als het schema al klopt gebeurt er niets (en wordt er geen
    lock gevraagd). Een tabel die nog niet bestaat wordt overgeslagen: de
    webapplicatie maakt hem aan met het schema uit models.py, dat de kolommen
    al heeft.

    Args:
        cursor: DBAPI-cursor (psycopg2); de aanroeper doet commit of rollback

    Returns:
        Lijst met de uitgevoerde statements
    """
    uitgevoerd = []
    for tabel in sorted({v['tabel'] for v in VERWIJZINGEN if v['beleid'] == LOSKOPPELEN}):
        cursor.execute("""
            SELECT column_name, is_nullable FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = %s
        """, (tabel,))
        kolommen = {rij[0]: rij[1] for rij in cursor.fetchall()}
        if not kolommen:
            logger.info(f"Schemamigratie gebruikersdata: tabel {tabel} bestaat (nog) niet; overgeslagen.")
            continue
        for statement in bepaalSchemawijzigingen(tabel, kolommen):
            cursor.execute(statement)
            uitgevoerd.append(statement)
            logger.info(f"Schemamigratie gebruikersdata: {statement}")
    return uitgevoerd


def migreerSchemaInTransactie(conn, lock_timeout='30s'):
    """Voer migreerSchema uit in een eigen transactie op een DBAPI-verbinding.

    De lock_timeout geldt alleen binnen deze transactie (SET LOCAL), zodat een
    verbinding uit een pool er niet mee blijft zitten. Bij een fout volgt een
    rollback en wordt de fout doorgegeven. De verbinding wordt niet gesloten.

    Args:
        conn: DBAPI-verbinding (psycopg2) zonder openstaande transactie
        lock_timeout: maximale wachttijd op een lock, als PostgreSQL-interval

    Returns:
        Lijst met de uitgevoerde statements
    """
    cursor = conn.cursor()
    try:
        cursor.execute(f"SET LOCAL lock_timeout = '{lock_timeout}'")
        uitgevoerd = migreerSchema(cursor)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return uitgevoerd
