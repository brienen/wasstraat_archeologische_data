"""Laden van data uit MongoDB naar PostgreSQL.

Gebruikt pymongo voor extractie en psycopg2 voor laden.
Geen pandas of SQLAlchemy afhankelijkheden.

Twee manieren van laden, met dezelfde opbouw van de rijen (leesDocumenten,
transformRow):

- loadAll(): de volledige cyclus. Laadt alles in {tabel}_new-tabellen en
  wisselt die in een 3-fase atomic swap om met de bestaande tabellen.
- loadIncrementeel(): de incrementele cyclus (issue 61, fase 3). Werkt de
  bestaande tabellen bij met een upsert op primary_key en verwijdert rijen
  waarvan de entiteit uit Single_Store_Clean is verdwenen. Tabellen met
  gebruikersdata blijven ongemoeid.

Beide gebruiken dezelfde FK-mechaniek: constraints lezen
(leesFkConstraints), verwijderen (verwijderFkConstraints), herstellen met NOT
VALID (herstelFkConstraints) en daarna valideren (valideerFkConstraints).

Beide herberekenen na het laden de afgeleide velden die de webapplicatie
toont (aantal_fotos, aantal_artefacten en de dateringen van artefacten) met
herberekenAfgeleideVelden (issue 72).
"""
import pymongo
import psycopg2
import psycopg2.extras
from urllib.parse import urlparse, unquote
from datetime import datetime, date

import wasstraat.meta as meta
import wasstraat.archutils as ut
import wasstraat.delta_transform as delta_transform
import wasstraat.verwerkingsrun as verwerkingsrun
import shared.config as config
import shared.const as const
from shared.logutils import maskeerWachtwoord
import logging

logger = logging.getLogger("airflow.task")

# Def_-tabellen die loadAll() vanuit Single_Store_Clean laadt (de tabelnaam is 'Def_' + soort).
# Ook gebruikt door delta_transform.getTabelVoorSoort voor de stabiele sleutels van incrementeel laden.
LOAD_TABELLEN = [
    'Def_ABR', 'Def_Project', 'Def_Put', 'Def_Vondst', 'Def_Spoor',
    'Def_Stelling', 'Def_Doos', 'Def_Standplaats', 'Def_Plaatsing',
    'Def_Vlak', 'Def_Vindplaats', 'Def_Artefact', 'Def_Bestand',
    'Def_Vulling', 'Def_Monster', 'Def_Monster_Botanie',
    'Def_Monster_Schelp', 'Def_DT_Soort_Plant', 'Def_DT_Soort_Schelp',
    'Def_DT_Soort_Deel', 'Def_DT_Soort_Staat',
]

# Tabellen met gebruikersdata (ingevoerd in de webapplicatie). De incrementele cyclus
# laat ze ongemoeid; de volledige cyclus leegt alle behalve Def_Partij (zie loadAll).
GEBRUIKERS_TABELLEN = [
    'Def_artefact_abr', 'Def_Bruikleen',
    'Def_artefact_conservering', 'Def_Conserveringsproject', 'Def_Partij',
]

# Maximale wachttijd op locks bij de incrementele load. ALTER TABLE ... DROP CONSTRAINT
# vraagt een ACCESS EXCLUSIVE-lock; zonder timeout wacht de load eindeloos als de
# webapplicatie een transactie open heeft.
LOCK_TIMEOUT_INCREMENTEEL = '30s'


# ============================================================
# Connectie-helpers
# ============================================================

def parsePgUri(uri):
    """Parse een SQLAlchemy-stijl URI naar psycopg2 connect-parameters.

    Args:
        uri: Database URI (bijv. 'postgresql://user:pass@host:5432/dbname')

    Returns:
        Dict met host, port, dbname, user, password
    """
    parsed = urlparse(uri)
    return {
        'host': parsed.hostname or 'localhost',
        'port': parsed.port or 5432,
        'dbname': parsed.path.lstrip('/'),
        'user': unquote(parsed.username) if parsed.username else None,
        'password': unquote(parsed.password) if parsed.password else None,
    }


def getPgConnection():
    """Maak een psycopg2 connectie naar PostgreSQL."""
    params = parsePgUri(config.SQLALCHEMY_DATABASE_URI)
    return psycopg2.connect(**params)


def getAnalyseCleanCollection():
    """Haal de MongoDB analyse-collectie op (Single_Store_Clean)."""
    myclient = pymongo.MongoClient(str(config.MONGO_URI))
    analyseDb = myclient[str(config.DB_ANALYSE)]
    return analyseDb[config.COLL_ANALYSE_CLEAN]


# ============================================================
# PostgreSQL metadata (vervangt SQLAlchemy inspect)
# ============================================================

def getColumnMetadata(cursor, table_name):
    """Haal kolomdefinities op uit PostgreSQL information_schema.

    Args:
        cursor: psycopg2 cursor
        table_name: Tabelnaam (zonder _new suffix)

    Returns:
        Lijst van dicts met name, data_type, udt_name, max_length, nullable
    """
    cursor.execute("""
        SELECT column_name, data_type, udt_name,
               character_maximum_length, is_nullable
        FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = %s
        ORDER BY ordinal_position
    """, (table_name,))
    return [
        {
            'name': row[0],
            'data_type': row[1],
            'udt_name': row[2],
            'max_length': row[3],
            'nullable': row[4] == 'YES',
        }
        for row in cursor.fetchall()
    ]


def getEnumColumns(cursor, table_name):
    """Bepaal welke kolommen een PostgreSQL ENUM type hebben, inclusief geldige waarden.

    Args:
        cursor: psycopg2 cursor
        table_name: Tabelnaam (zonder _new suffix)

    Returns:
        Dict van kolomnaam -> lijst van geldige ENUM waarden
    """
    cursor.execute("""
        SELECT c.column_name, e.enumlabel
        FROM information_schema.columns c
        JOIN pg_type t ON t.typname = c.udt_name
        JOIN pg_enum e ON e.enumtypid = t.oid
        WHERE c.table_name = %s
          AND c.table_schema = 'public'
          AND c.data_type = 'USER-DEFINED'
          AND t.typtype = 'e'
        ORDER BY c.column_name, e.enumsortorder
    """, (table_name,))
    result = {}
    for col_name, enum_value in cursor.fetchall():
        result.setdefault(col_name, []).append(enum_value)
    return result


# ============================================================
# Type-conversie helpers (pure Python, geen pandas)
# ============================================================

def convertToInt(value):
    """Converteer een waarde naar integer, None bij falen."""
    if value is None:
        return None
    try:
        return int(float(str(value)))
    except (ValueError, TypeError, OverflowError):
        return None


def convertToFloat(value):
    """Converteer een waarde naar float, None bij falen."""
    if value is None:
        return None
    try:
        f = float(str(value))
        if f != f:  # NaN check
            return None
        return f
    except (ValueError, TypeError):
        return None


def convertToDatePure(value):
    """Converteer een waarde naar date, None bij falen.

    Probeert veelvoorkomende datumformaten (dayfirst).
    Geen pandas-afhankelijkheid.
    """
    if value is None:
        return None
    if isinstance(value, (datetime, date)):
        return value if isinstance(value, date) and not isinstance(value, datetime) else value.date() if isinstance(value, datetime) else value
    s = str(value).strip()
    if not s or s in ('nan', 'NaN', 'None', 'NaT', 'nat'):
        return None
    formats = [
        '%d-%m-%Y', '%d/%m/%Y', '%d.%m.%Y',
        '%d-%m-%y', '%d/%m/%y',
        '%Y-%m-%d', '%Y/%m/%d',
        '%d-%m-%Y %H:%M:%S', '%Y-%m-%d %H:%M:%S',
        '%Y-%m-%dT%H:%M:%S',
    ]
    for fmt in formats:
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    try:
        from dateutil.parser import parse as dateutil_parse
        return dateutil_parse(s, dayfirst=True).date()
    except Exception:
        return None


def isNanOrEmpty(value):
    """Check of een waarde None, nan, of leeg is."""
    if value is None:
        return True
    s = str(value).strip()
    return s in ('', 'nan', 'NaN', 'None', 'NaT')


# ============================================================
# Data-extractie uit MongoDB
# ============================================================

def getFields(col, soort):
    """Haal de volledige veldnamenlijst op voor een entiteitstype.

    Combineert velden uit meta.py met velden gevonden in MongoDB documenten.

    Args:
        col: MongoDB collectie
        soort: Entiteitstype (bijv. 'Project', 'Spoor')

    Returns:
        Gesorteerde lijst van veldnamen
    """
    lst_fields = meta.getVeldnamen(soort)
    logger.info(f'lstfields {lst_fields}')
    set_fields = set(lst_fields)

    # Haal veldnamen op uit een steekproef van documenten
    for doc in col.find({'soort': soort}).limit(10):
        set_fields.update(doc.keys())

    result = list(set_fields)
    result.sort()
    return result


def vulArtefactKey(doc):
    """Vul bij een artefact zonder key de samengestelde sleutel in (key_subnr|artefactsoort).

    De kolom key van Def_Artefact was leeg, omdat artefacten zelden een
    artefactnr (en dus een key) hebben. Met de samengestelde sleutel vindt de
    incrementele cyclus een opnieuw ingelezen artefact terug (zie
    delta_transform.getArtefactKey en setStabielePrimaryKeys).

    Args:
        doc: artefact-document (wordt aangepast)

    Returns:
        Het document
    """
    if isNanOrEmpty(doc.get('key')):
        doc['key'] = delta_transform.getArtefactKey(doc)
    return doc


def leesDocumenten(col, soort, extra_velden=None):
    """Lees de documenten van een soort uit Single_Store_Clean voor het laden naar PostgreSQL.

    De velden komen uit getFields, aangevuld met extra_velden (de kolommen van
    de doeltabel). getFields kijkt behalve naar meta.py alleen naar een
    steekproef van tien documenten; een veld dat pas later in de pipeline
    wordt gezet (zoals artefactID op foto's, door setReferences) en dat in die
    tien documenten ontbreekt, zou anders voor de hele tabel niet gelezen
    worden. Artefacten krijgen zo nodig de samengestelde sleutel in key
    (vulArtefactKey).

    Args:
        col: MongoDB collectie (Single_Store_Clean)
        soort: Entiteitstype (bijv. 'Project', 'Artefact', 'Bestand')
        extra_velden: extra veldnamen om altijd te lezen (meestal de kolomnamen van de doeltabel)

    Returns:
        Tuple (lijst met veldnamen uit getFields, lijst met documenten)
    """
    fields = getFields(col, soort)
    projection = {f: 1 for f in fields}
    for veld in (extra_velden or []):
        projection[veld] = 1
    projection['_id'] = 1
    projection['ID'] = 1
    if soort == 'Artefact':
        projection.update({'key': 1, 'key_subnr': 1, 'artefactsoort': 1})
    documents = list(col.find({'soort': soort}, projection=projection))
    if soort == 'Artefact':
        for doc in documents:
            vulArtefactKey(doc)
    return fields, documents


def getDocumentKolommen(documents):
    """Bepaal de veldnamen van alle documenten, met ID hernoemd naar primary_key.

    Args:
        documents: lijst met MongoDB-documenten

    Returns:
        Set met veldnamen
    """
    all_doc_keys = set()
    for doc in documents:
        keys = set(doc.keys())
        if 'ID' in keys:
            keys.discard('ID')
            keys.add('primary_key')
        all_doc_keys.update(keys)
    return all_doc_keys


# ============================================================
# Rij-transformatie (pure Python)
# ============================================================

def transformRow(doc, columns, col_lookup, enum_columns):
    """Transformeer een MongoDB document naar een dict klaar voor PostgreSQL.

    Args:
        doc: MongoDB document (dict)
        columns: Lijst van te laden kolomnamen
        col_lookup: Dict van kolomnaam -> metadata dict
        enum_columns: Dict van kolomnaam -> lijst geldige ENUM waarden

    Returns:
        Dict met getransformeerde waarden per kolom
    """
    row = dict(doc)

    # Rename ID -> primary_key
    if 'ID' in row:
        row['primary_key'] = row.pop('ID')

    # String conversies
    for field in ('_id', 'imageID', 'herkomst', 'brondata'):
        if field in row and row[field] is not None:
            row[field] = str(row[field])

    # Per kolom type-coercie
    result = {}
    for col_name in columns:
        value = row.get(col_name)
        col_def = col_lookup.get(col_name)

        # Normaliseer nan/None/empty
        if isNanOrEmpty(value):
            if col_name in enum_columns:
                valid = enum_columns[col_name]
                result[col_name] = const.ARTF_ONBEKEND if const.ARTF_ONBEKEND in valid else valid[0]
            else:
                result[col_name] = None
            continue

        if col_def is None:
            result[col_name] = value
            continue

        data_type = col_def['data_type']
        max_length = col_def['max_length']

        # Type-coercie op basis van PostgreSQL data_type
        if data_type == 'character varying' and max_length:
            result[col_name] = str(value)[:max_length]
        elif data_type in ('character varying', 'text'):
            result[col_name] = str(value)
        elif data_type in ('integer', 'bigint', 'smallint'):
            result[col_name] = convertToInt(value)
        elif data_type in ('double precision', 'real', 'numeric'):
            result[col_name] = convertToFloat(value)
        elif data_type == 'boolean':
            # convertToBool retourneert 0/1; psycopg2 vereist Python bool
            result[col_name] = bool(ut.convertToBool(value))
        elif data_type in ('date', 'timestamp without time zone', 'timestamp with time zone'):
            result[col_name] = convertToDatePure(value)
        elif col_name in enum_columns:
            s = str(value).strip()
            if s == '':
                valid = enum_columns[col_name]
                result[col_name] = const.ARTF_ONBEKEND if const.ARTF_ONBEKEND in valid else valid[0]
            else:
                result[col_name] = value
        else:
            result[col_name] = value

    return result


# ============================================================
# Batch insert via psycopg2
# ============================================================

def insertBatch(cursor, table, columns, rows, page_size=1000):
    """Voeg rijen in via psycopg2.extras.execute_values.

    Args:
        cursor: psycopg2 cursor
        table: Doeltabel
        columns: Lijst van kolomnamen
        rows: Lijst van tuples met waarden
        page_size: Aantal rijen per batch

    Returns:
        Aantal ingevoegde rijen
    """
    if not rows:
        return 0
    cols_str = ', '.join(f'"{c}"' for c in columns)
    sql = f'INSERT INTO "{table}" ({cols_str}) VALUES %s'
    psycopg2.extras.execute_values(cursor, sql, rows, page_size=page_size)
    return len(rows)


# ============================================================
# Transfer per entiteitstype
# ============================================================

def transferToDB(soort, table, cursor):
    """Transfereer documenten van een soort uit MongoDB naar een PostgreSQL tabel.

    Args:
        soort: Entiteitstype (bijv. 'Project', 'Spoor')
        table: Doeltabel in PostgreSQL (bijv. 'Def_Project_new')
        cursor: psycopg2 cursor
    """
    try:
        # 1. Haal PostgreSQL kolom-metadata op
        base_table = table.replace('_new', '') if table.endswith('_new') else table
        db_columns = getColumnMetadata(cursor, base_table)
        if not db_columns:
            logger.warning(f"Geen kolommen gevonden voor tabel {base_table}")
            return

        db_colnames = set(col['name'] for col in db_columns)
        col_lookup = {c['name']: c for c in db_columns}
        enum_columns = getEnumColumns(cursor, base_table)
        if enum_columns:
            logger.info(f"ENUM kolommen gevonden voor {base_table}: {set(enum_columns.keys())}")

        # 2. Haal MongoDB documenten op (artefacten: key zo nodig samengesteld)
        col = getAnalyseCleanCollection()
        fields, documents = leesDocumenten(col, soort, extra_velden=db_colnames)

        if not documents:
            logger.info(f"Geen documenten gevonden voor soort: {soort}")
            return

        # 3. Bepaal veldnamen uit alle documenten (na rename ID -> primary_key)
        all_doc_keys = getDocumentKolommen(documents)

        # 4. Kolom-intersectie, exclusief 'location' (wordt apart afgehandeld)
        has_geometry = ('location' in db_colnames
                        and 'longitude' in all_doc_keys
                        and 'latitude' in all_doc_keys)
        intersect_cols = sorted(all_doc_keys & db_colnames - {'location'})

        # Log mismatches
        data_only = all_doc_keys - db_colnames
        if data_only:
            logger.warning(
                f"Bij het laden van data van {soort} naar tabel {table} "
                f"werd volgende data aangeboden die de tabel niet ondersteunt: {data_only}"
            )
        db_only = db_colnames - all_doc_keys - {'location'}
        if db_only:
            logger.warning(
                f"Bij het laden van data van {soort} naar tabel {table} "
                f"verwachtte de tabel de volgende data die niet werd aangeboden: {db_only}"
            )

        # 5. Transformeer alle documenten
        rows = []
        for doc in documents:
            transformed = transformRow(doc, intersect_cols, col_lookup, enum_columns)
            rows.append(tuple(transformed.get(c) for c in intersect_cols))

        # 6. Batch insert
        count = insertBatch(cursor, table, intersect_cols, rows)
        logger.info(f"Transfering: {soort} with {count} records")

        # 7. Update geometry kolom (PostGIS) indien van toepassing
        if has_geometry:
            cursor.execute(f'''
                UPDATE "{table}"
                SET location = ST_SetSRID(ST_MakePoint(longitude, latitude), 4326)
                WHERE longitude IS NOT NULL
                  AND latitude IS NOT NULL
                  AND longitude > 1
            ''')
            logger.info(f"Geometry bijgewerkt voor {table}")

    except Exception as err:
        msg = (f"Onbekende fout bij laden van soort: {soort} "
               f"in tabel {table} van database met melding: {err}")
        logger.error(msg)
        raise Exception(msg) from err


# ============================================================
# FK-mechaniek (gedeeld door loadAll en loadIncrementeel)
# ============================================================

def leesFkConstraints(cursor):
    """Lees de definities van alle FK-constraints op Def_-tabellen.

    Alleen Def_-tabellen: systeemtabellen (ab_user e.d.) zijn in gebruik door
    de webapplicatie en zouden lock timeouts veroorzaken.

    Args:
        cursor: psycopg2 cursor

    Returns:
        Lijst met dicts {'table', 'name', 'definition', 'referenced_table'}
    """
    cursor.execute("""
        SELECT tc.table_name, tc.constraint_name,
               pg_get_constraintdef(pgc.oid) AS constraint_def,
               pgc.confrelid::regclass::text AS referenced_table
        FROM information_schema.table_constraints tc
        JOIN pg_constraint pgc ON pgc.conname = tc.constraint_name
        WHERE tc.constraint_type = 'FOREIGN KEY'
          AND tc.table_schema = 'public'
          AND tc.table_name LIKE 'Def\\_%%' ESCAPE '\\'
    """)
    fk_constraints = []
    for row in cursor.fetchall():
        fk_constraints.append({
            'table': row[0],
            'name': row[1],
            'definition': row[2],
            # regclass als tekst: "Def_Project" of public."Def_Project"
            'referenced_table': row[3].split('.')[-1].strip('"') if row[3] else None,
        })
    return fk_constraints


def verwijderFkConstraints(cursor, fk_constraints):
    """Verwijder FK-constraints tijdelijk (snel: alleen metadata-operaties).

    Args:
        cursor: psycopg2 cursor
        fk_constraints: lijst uit leesFkConstraints
    """
    for fk in fk_constraints:
        cursor.execute(
            f'ALTER TABLE "{fk["table"]}" DROP CONSTRAINT IF EXISTS "{fk["name"]}"'
        )


def herstelFkConstraints(cursor, fk_constraints, mislukt=None):
    """Herstel FK-constraints met NOT VALID, elk in een eigen SAVEPOINT.

    Met NOT VALID controleert PostgreSQL de bestaande rijen niet (dat kan
    minuten duren); nieuwe en gewijzigde rijen wel. De SAVEPOINT per
    constraint voorkomt dat één fout alle overige constraints blokkeert
    (poisoned transaction).

    Args:
        cursor: psycopg2 cursor
        fk_constraints: lijst uit leesFkConstraints
        mislukt: optionele lijst waaraan de namen (tabel.constraint) van de
            constraints die niet hersteld konden worden worden toegevoegd

    Returns:
        Tuple (aantal hersteld, aantal mislukt)
    """
    fk_restored = 0
    fk_failed = 0
    for fk in fk_constraints:
        try:
            cursor.execute('SAVEPOINT fk_restore_sp')
            cursor.execute(
                f'ALTER TABLE "{fk["table"]}" ADD CONSTRAINT "{fk["name"]}" '
                f'{fk["definition"]} NOT VALID'
            )
            cursor.execute('RELEASE SAVEPOINT fk_restore_sp')
            fk_restored += 1
        except Exception as fk_err:
            cursor.execute('ROLLBACK TO SAVEPOINT fk_restore_sp')
            fk_failed += 1
            if mislukt is not None:
                mislukt.append(f'{fk["table"]}.{fk["name"]}')
            logger.warning(
                f"Kon FK constraint {fk['name']} niet herstellen op "
                f"{fk['table']}: {fk_err}. Definitie was: {fk['definition']}"
            )
    return fk_restored, fk_failed


def valideerFkConstraints(cursor, fk_constraints):
    """Valideer FK-constraints die met NOT VALID zijn hersteld, elk in een eigen SAVEPOINT.

    Een constraint die niet valideert (er zijn rijen die naar een niet
    bestaande rij verwijzen) blijft NOT VALID staan: nieuwe en gewijzigde
    rijen worden wel gecontroleerd.

    Args:
        cursor: psycopg2 cursor
        fk_constraints: lijst uit leesFkConstraints

    Returns:
        Lijst met namen van constraints die niet gevalideerd konden worden
    """
    niet_gevalideerd = []
    for fk in fk_constraints:
        try:
            cursor.execute('SAVEPOINT fk_validate_sp')
            cursor.execute(
                f'ALTER TABLE "{fk["table"]}" VALIDATE CONSTRAINT "{fk["name"]}"'
            )
            cursor.execute('RELEASE SAVEPOINT fk_validate_sp')
        except Exception as fk_err:
            cursor.execute('ROLLBACK TO SAVEPOINT fk_validate_sp')
            niet_gevalideerd.append(fk['name'])
            logger.warning(f"FK constraint {fk['name']} op {fk['table']} kon niet gevalideerd worden "
                           f"en blijft NOT VALID: {fk_err}")
    return niet_gevalideerd


# ============================================================
# Afgeleide velden (issue 72, gedeeld door loadAll en loadIncrementeel)
# ============================================================

# Kolommen die de webapplicatie toont maar die niet uit de brondata komen, per tabel met
# een query die per primary_key de nieuwe waarden geeft. De uitkomst is dezelfde als die van
# init.init() in de webapplicatie (app/app/init.py), die deze velden voorheen alleen bij het
# starten van Flask vulde:
#
# - aantal_fotos: het aantal objectfoto's (Def_Bestand met bestandsoort Objectfoto, het model
#   Objectfoto) met een artefactID naar het artefact; 0 zonder foto's.
# - vondstdatering_vanaf/_tot: de datering van de vondst (vondstID); NULL zonder vondst.
# - spoordatering_vanaf/_tot: de datering van het spoor (spoorID) van die vondst; NULL zonder.
# - datering_vanaf: de artefactdatering, anders de vondstdatering, anders de spoordatering.
# - datering_tot: de artefactdatering, anders de vondstdatering (zonder spoordatering).
# - aantal_artefacten: het aantal artefacten met een projectID naar het project; 0 zonder.
#
# 'Anders' betekent leeg of 0: init.init() zet zelf alleen datering_vanaf/_tot uit de
# artefactdatering, maar elke flush van een gewijzigd artefact roept de observers van
# models.py aan (@observes van sqlalchemy_utils), die 'if not ...' gebruiken en zo de
# vondst- en spoordatering invullen. Voor datering_tot ontbreekt de spoordatering, omdat in
# models.py de tweede methode spoor_observer (voor spoordatering_vanaf) de eerste (voor
# spoordatering_tot) overschrijft; de pipeline volgt init.init() daarin.
AFGELEIDE_VELDEN = {
    'Def_Artefact': {
        'kolommen': ['aantal_fotos', 'vondstdatering_vanaf', 'vondstdatering_tot', 'spoordatering_vanaf',
                     'spoordatering_tot', 'datering_vanaf', 'datering_tot'],
        'bron': f'''
            SELECT a.primary_key,
                   COALESCE(f.aantal, 0) AS aantal_fotos,
                   v.vondstdatering_vanaf, v.vondstdatering_tot,
                   s.spoordatering_vanaf, s.spoordatering_tot,
                   CASE WHEN COALESCE(a.artefactdatering_vanaf, 0) <> 0 THEN a.artefactdatering_vanaf
                        WHEN COALESCE(v.vondstdatering_vanaf, 0) <> 0 THEN v.vondstdatering_vanaf
                        ELSE s.spoordatering_vanaf END AS datering_vanaf,
                   CASE WHEN COALESCE(a.artefactdatering_tot, 0) <> 0 THEN a.artefactdatering_tot
                        ELSE v.vondstdatering_tot END AS datering_tot
            FROM "Def_Artefact" a
            LEFT JOIN (SELECT b."artefactID", COUNT(*) AS aantal
                       FROM "Def_Bestand" b
                       WHERE CAST(b.bestandsoort AS TEXT) = '{const.FOTO_OBJECTFOTO}'
                       GROUP BY b."artefactID") f ON f."artefactID" = a.primary_key
            LEFT JOIN "Def_Vondst" v ON v.primary_key = a."vondstID"
            LEFT JOIN "Def_Spoor" s ON s.primary_key = v."spoorID"''',
    },
    'Def_Project': {
        'kolommen': ['aantal_artefacten'],
        'bron': '''
            SELECT p.primary_key, COUNT(a.primary_key) AS aantal_artefacten
            FROM "Def_Project" p
            LEFT JOIN "Def_Artefact" a ON a."projectID" = p.primary_key
            GROUP BY p.primary_key''',
    },
}


def werkAfgeleideKolommenBij(cursor, tabel, kolommen, bron_sql):
    """Werk kolommen van een tabel bij met de waarden uit een query, alleen waar ze veranderen.

    Telt eerst per kolom hoeveel rijen een andere waarde krijgen en werkt dan in
    één UPDATE ... FROM alle rijen bij waarin minstens één kolom verandert (IS
    DISTINCT FROM, dus ook NULL tegenover een waarde). Een rij zonder wijziging
    wordt niet herschreven.

    Args:
        cursor: psycopg2 cursor
        tabel: tabelnaam
        kolommen: de bij te werken kolommen; bron_sql levert ze onder dezelfde naam
        bron_sql: SELECT met primary_key en de kolommen

    Returns:
        Dict met per kolom het aantal rijen met een nieuwe waarde, plus 'rijen'
        (het aantal herschreven rijen)
    """
    verschillen = [f't."{k}" IS DISTINCT FROM n."{k}"' for k in kolommen]
    tellers = ', '.join(f'COUNT(*) FILTER (WHERE {v})' for v in verschillen)
    cursor.execute(f'SELECT {tellers} FROM "{tabel}" AS t '
                   f'JOIN ({bron_sql}) AS n ON n.primary_key = t.primary_key')
    tellingen = {k: int(aantal) for k, aantal in zip(kolommen, cursor.fetchone())}

    set_str = ', '.join(f'"{k}" = n."{k}"' for k in kolommen)
    cursor.execute(f'UPDATE "{tabel}" AS t SET {set_str} FROM ({bron_sql}) AS n '
                   f'WHERE n.primary_key = t.primary_key AND ({" OR ".join(verschillen)})')
    tellingen['rijen'] = cursor.rowcount
    return tellingen


def herberekenAfgeleideVelden(cursor):
    """Herbereken de afgeleide velden van de webapplicatie met set-based SQL (issue 72).

    Zet aantal_fotos en de dateringen van Def_Artefact en aantal_artefacten van
    Def_Project voor alle rijen, met dezelfde uitkomst als init.init() in de
    webapplicatie (zie AFGELEIDE_VELDEN). Alleen rijen waarvan een waarde
    verandert worden herschreven; een tweede aanroep schrijft dus niets.
    loadAll roept dit aan na de swap (eigen transactie), loadIncrementeel in de
    transactie van de upsert, vóór het herstel van de FK-constraints.

    Args:
        cursor: psycopg2 cursor; de aanroeper doet commit of rollback

    Returns:
        Dict per tabel met per kolom het aantal rijen met een nieuwe waarde en 'rijen'
    """
    tellingen = {}
    for tabel, afgeleid in AFGELEIDE_VELDEN.items():
        tellingen[tabel] = werkAfgeleideKolommenBij(cursor, tabel, afgeleid['kolommen'], afgeleid['bron'])
        logger.info(f"Afgeleide velden van {tabel} herberekend (rijen met een nieuwe waarde per veld): "
                    f"{tellingen[tabel]}")
    return tellingen


# ============================================================
# Hoofdfunctie: 3-fase atomic swap
# ============================================================

def loadAll():
    """Laad alle data uit MongoDB naar PostgreSQL via een 3-fase atomic swap.

    Fase 1: Laad data in tijdelijke {tabel}_new tabellen
    Fase 2a: Atomic rename swap (drop FK → rename → truncate extra)
    Fase 2b: Herstel FK constraints met NOT VALID + SAVEPOINTs
    Fase 3: Opruimen _old tabellen, herstel de sequences van primary_key
            (zetSequence) en valideer FK constraints
    Fase 4: Herbereken de afgeleide velden van de webapplicatie
            (herberekenAfgeleideVelden, issue 72), zodat ze na een volledige
            cyclus gevuld zijn zonder Flask te herstarten
    """
    logger.info("Starting Loading data to relational database...")

    logger.info(f"Connecting to {maskeerWachtwoord(config.SQLALCHEMY_DATABASE_URI)}")
    conn = getPgConnection()

    lst_tables = list(LOAD_TABELLEN)

    # Extra tabellen die ook getruncated worden (niet in de hoofdlijst)
    extra_truncate_tables = [
        'Def_artefact_abr', 'Def_Bruikleen',
        'Def_artefact_conservering', 'Def_Conserveringsproject',
    ]

    temp_tables_created = []

    try:
        cursor = conn.cursor()

        # ============================================================
        # PRE-CLEANUP: Ruim restanten op van een eerder afgebroken run.
        # Dit voorkomt "duplicate key in pg_type" fouten als _new of _old
        # tabellen zijn achtergebleven na een crash of timeout.
        # ============================================================
        logger.info("Pre-cleanup: verwijder eventuele restanten van vorige run...")
        for table in lst_tables:
            for suffix in ('_new', '_old'):
                cursor.execute(f'DROP TABLE IF EXISTS "{table}{suffix}" CASCADE')
        conn.commit()
        logger.info("Pre-cleanup afgerond.")

        # ============================================================
        # FASE 1: Laden naar tijdelijke tabellen (buiten de swap-transactie)
        # Dit kan lang duren, maar blokkeert niets.
        # ============================================================
        logger.info("FASE 1: Laden naar tijdelijke tabellen...")
        logger.info(f"Loading all data for {lst_tables}")

        try:
            for table in lst_tables:
                if table.startswith('Def_'):
                    soort = table[4:]  # Remove Def_
                    temp_table = f"{table}_new"

                    # CASCADE verwijdert ook orphan pg_type entries
                    cursor.execute(f'DROP TABLE IF EXISTS "{temp_table}" CASCADE')
                    # EXCLUDING CONSTRAINTS: voorkomt dat FK-refs naar oude
                    # tabellen worden gekopieerd. Indexes WEL kopiëren.
                    cursor.execute(
                        f'CREATE TABLE "{temp_table}" '
                        f'(LIKE "{table}" INCLUDING INDEXES INCLUDING DEFAULTS)'
                    )
                    temp_tables_created.append((table, temp_table))

                    transferToDB(soort, temp_table, cursor)
                    logger.info(f"Geladen: {soort} -> {temp_table}")

            conn.commit()

        except Exception as err:
            conn.rollback()
            logger.error(f"Laden naar temp-tabellen mislukt: {err}. Opruimen...")
            cursor = conn.cursor()
            for orig, temp in temp_tables_created:
                try:
                    cursor.execute(f'DROP TABLE IF EXISTS "{temp}" CASCADE')
                except Exception:
                    pass
            conn.commit()
            raise

        # ============================================================
        # FASE 2a: Snelle swap in een aparte, korte transactie.
        # FK constraints worden hier gedropt en de tabellen hernoemd.
        # ============================================================
        logger.info("FASE 2a: Atomic swap van tabellen...")

        # Stel een lock-timeout in: wacht maximaal 5 seconden op locks.
        cursor.execute("SET lock_timeout = '5s'")

        # Bewaar FK-constraint definities (alleen Def_-tabellen) zodat we ze
        # na de swap kunnen herstellen, en drop ze.
        fk_constraints = leesFkConstraints(cursor)
        logger.info(f"Gevonden: {len(fk_constraints)} FK constraints om tijdelijk te verwijderen")
        verwijderFkConstraints(cursor, fk_constraints)

        # Rename is instant (PostgreSQL past alleen de systeemcatalogus aan)
        for orig, temp in temp_tables_created:
            old_table = f"{orig}_old"
            cursor.execute(f'DROP TABLE IF EXISTS "{old_table}" CASCADE')
            cursor.execute(f'ALTER TABLE "{orig}" RENAME TO "{old_table}"')
            cursor.execute(f'ALTER TABLE "{temp}" RENAME TO "{orig}"')

        # Truncate de extra tabellen (CASCADE voorkomt FK-conflicten)
        lst_extra = ', '.join(f'"{t}"' for t in extra_truncate_tables)
        cursor.execute(f'TRUNCATE {lst_extra} CASCADE')

        conn.commit()
        logger.info("Swap voltooid.")

        # ============================================================
        # FASE 2b: Herstel FK constraints in een aparte transactie.
        # Gebruik een SAVEPOINT per constraint zodat één fout niet
        # alle overige constraints blokkeert (poisoned transaction).
        # ============================================================
        logger.info("FASE 2b: Herstel FK constraints met NOT VALID...")
        fk_restored, fk_failed = herstelFkConstraints(cursor, fk_constraints)

        conn.commit()
        logger.info(f"FK constraints hersteld: {fk_restored} OK, {fk_failed} mislukt.")

        # ============================================================
        # FASE 3: Opruimen (buiten de swap-transactie)
        # ============================================================
        logger.info("FASE 3: Opruimen oude tabellen en validatie...")
        for orig, temp in temp_tables_created:
            old_table = f"{orig}_old"
            cursor.execute(f'DROP TABLE IF EXISTS "{old_table}" CASCADE')

        # Herstel de sequence en default van primary_key. CREATE TABLE ... LIKE
        # INCLUDING DEFAULTS kopieert de default nextval(...) van de oude tabel;
        # die sequence hoort bij de oude tabel en is met DROP ... CASCADE
        # verdwenen, en de default dus ook. Zonder sequence kan de webapplicatie
        # geen rijen aanmaken.
        for table in lst_tables:
            volgende = zetSequence(cursor, table)
            logger.info(f"Sequence van {table}.primary_key hersteld (volgende primary_key {volgende}).")

        # Valideer de FK constraints alsnog
        valideerFkConstraints(cursor, fk_constraints)

        conn.commit()

        # ============================================================
        # FASE 4: Afgeleide velden van de webapplicatie (issue 72), in een
        # eigen transactie. De nieuwe tabellen hebben ze leeg; voorheen vulde
        # alleen init.init() van Flask ze, en alleen bij het (her)starten.
        # ============================================================
        logger.info("FASE 4: Afgeleide velden herberekenen...")
        herberekenAfgeleideVelden(cursor)
        conn.commit()
        logger.info("Laden naar database succesvol afgerond.")

    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        raise
    finally:
        conn.close()


# ============================================================
# Incrementele load (issue 61, fase 3): upsert op primary_key
# ============================================================

def _getClient():
    """Maak een MongoClient op basis van de configuratie (vervangbaar in tests)."""
    return pymongo.MongoClient(str(config.MONGO_URI))


def getBetrokkenFkConstraints(fk_constraints, tabellen):
    """Selecteer de FK-constraints die op een van de tabellen staan of naar een van de tabellen verwijzen.

    Bij de incrementele load zijn dat de constraints tussen de Def_-tabellen
    van de pipeline en de verwijzingen vanuit de gebruikerstabellen naar die
    tabellen (bijv. Def_Bruikleen.artefactID). Constraints tussen
    gebruikerstabellen onderling (bijv. Def_Bruikleen.partijID) blijven staan.

    Args:
        fk_constraints: lijst uit leesFkConstraints
        tabellen: tabelnamen die worden bijgewerkt

    Returns:
        Lijst met de betrokken constraints
    """
    tabellen = set(tabellen)
    return [fk for fk in fk_constraints if fk['table'] in tabellen or fk.get('referenced_table') in tabellen]


def bepaalUpsertKolommen(fields, all_doc_keys, db_colnames):
    """Bepaal de kolommen voor de upsert van een tabel.

    Dat zijn de kolommen van de tabel die als veld in de documenten voorkomen
    (zoals transferToDB), aangevuld met de velden uit getFields die de tabel
    kent maar die geen enkel document (meer) heeft: die worden bij bestaande
    rijen leeggemaakt, net als bij een volledige load. Kolommen die de pipeline
    niet kent (bijv. velden die de webapplicatie zelf berekent of invult)
    blijven buiten de upsert en behouden bij bestaande rijen hun waarde. De
    geometriekolom location wordt apart bijgewerkt (werkGeometrieBij).

    Args:
        fields: veldnamen uit getFields
        all_doc_keys: veldnamen van de documenten (uit getDocumentKolommen)
        db_colnames: kolomnamen van de tabel

    Returns:
        Gesorteerde lijst met kolomnamen
    """
    velden = {'primary_key' if f == 'ID' else f for f in fields}
    return sorted(((set(all_doc_keys) | velden) & set(db_colnames)) - {'location'})


def upsertRijen(cursor, table, columns, rows, page_size=1000):
    """Voeg rijen in of werk ze bij op primary_key via psycopg2.extras.execute_values.

    ``INSERT ... ON CONFLICT (primary_key) DO UPDATE SET kolom = EXCLUDED.kolom``
    voor alle kolommen (ook ``_id``, dat bij gelijke primary_key kan wijzigen).
    Een bestaande rij wordt alleen herschreven als een waarde echt verschilt
    (vergelijking als tekst, zodat ook typen zonder =-operator werken).

    Args:
        cursor: psycopg2 cursor
        table: Doeltabel
        columns: Lijst van kolomnamen (met primary_key)
        rows: Lijst van tuples met waarden
        page_size: Aantal rijen per batch

    Returns:
        Set met de primary_keys van de ingevoegde en de bijgewerkte rijen
    """
    if not rows:
        return set()
    cols_str = ', '.join(f'"{c}"' for c in columns)
    bij_te_werken = [c for c in columns if c != 'primary_key']
    if bij_te_werken:
        set_str = ', '.join(f'"{c}" = EXCLUDED."{c}"' for c in bij_te_werken)
        oud = ', '.join(f'"{table}"."{c}"::text' for c in bij_te_werken)
        nieuw = ', '.join(f'EXCLUDED."{c}"::text' for c in bij_te_werken)
        conflict = (f'DO UPDATE SET {set_str} '
                    f'WHERE ROW({oud}) IS DISTINCT FROM ROW({nieuw})')
    else:
        conflict = 'DO NOTHING'
    sql = (f'INSERT INTO "{table}" ({cols_str}) VALUES %s '
           f'ON CONFLICT (primary_key) {conflict} RETURNING primary_key')
    resultaat = psycopg2.extras.execute_values(cursor, sql, rows, page_size=page_size, fetch=True)
    return {rij[0] for rij in resultaat}


def verwijderRijen(cursor, table, primary_keys):
    """Verwijder rijen op primary_key (in batches).

    Returns:
        Aantal verwijderde rijen
    """
    aantal = 0
    for batch in delta_transform.inBatches(primary_keys):
        cursor.execute(f'DELETE FROM "{table}" WHERE primary_key = ANY(%s)', (list(batch),))
        aantal += cursor.rowcount
    return aantal


def werkGeometrieBij(cursor, table):
    """Werk de geometriekolom location bij uit longitude en latitude, zoals transferToDB.

    Zelfde voorwaarde als transferToDB (longitude en latitude gevuld en
    longitude > 1); rijen die daar niet (meer) aan voldoen krijgen location
    NULL, net als bij een volledige load. Alleen rijen waarvan de geometrie
    verandert worden herschreven.

    Returns:
        Aantal bijgewerkte rijen
    """
    punt = ('CASE WHEN longitude IS NOT NULL AND latitude IS NOT NULL AND longitude > 1 '
            'THEN ST_SetSRID(ST_MakePoint(longitude, latitude), 4326) END')
    cursor.execute(f'''
        UPDATE "{table}"
        SET location = {punt}
        WHERE ST_AsEWKB(location) IS DISTINCT FROM ST_AsEWKB({punt})
    ''')
    return cursor.rowcount


def zetSequence(cursor, table):
    """Zet de sequence van primary_key op max(primary_key) + 1.

    Zo botsen rijen die de webapplicatie zelf aanmaakt niet met de rijen van
    de pipeline. De atomic swap van de volledige cyclus verliest de sequence
    (die hoort bij de oude tabel en verdwijnt met DROP ... CASCADE, net als de
    default van primary_key). Ontbreekt de sequence, dan wordt hij opnieuw
    aangemaakt met de standaardnaam (<tabel>_primary_key_seq) als default van
    primary_key, zoals de webapplicatie de tabel oorspronkelijk aanmaakt.

    Args:
        cursor: psycopg2 cursor
        table: tabelnaam

    Returns:
        De waarde die nextval() nu teruggeeft
    """
    cursor.execute("SELECT pg_get_serial_sequence(%s, 'primary_key')", (f'"{table}"',))
    rij = cursor.fetchone()
    sequence = rij[0] if rij else None
    if not sequence:
        naam = f'{table}_primary_key_seq'
        cursor.execute(f'CREATE SEQUENCE IF NOT EXISTS "{naam}" OWNED BY "{table}".primary_key')
        cursor.execute(f'ALTER TABLE "{table}" ALTER COLUMN primary_key SET DEFAULT nextval(%s::regclass)',
                       (f'"{naam}"',))
        sequence = f'"{naam}"'
        logger.info(f"Sequence {naam} voor {table}.primary_key opnieuw aangemaakt.")
    # Een lege tabel geeft 1 (de ondergrens van een sequence); de pipeline nummert vanaf 0
    cursor.execute(f'SELECT setval(%s, COALESCE((SELECT MAX(primary_key) FROM "{table}"), 0) + 1, false)',
                   (sequence,))
    return cursor.fetchone()[0]


def bereidTabelVoor(cursor, col, soort, table):
    """Lees de documenten van een soort en bouw de rijen voor de upsert van één tabel.

    Args:
        cursor: psycopg2 cursor
        col: Single_Store_Clean-collectie
        soort: Entiteitstype (tabelnaam zonder Def_; Def_Bestand: Bestand)
        table: Doeltabel

    Returns:
        Dict met 'kolommen', 'rijen', 'ids' en 'geometrie', of None als de tabel niet bestaat

    Raises:
        Exception: bij documenten zonder ID of met een dubbel ID
    """
    db_columns = getColumnMetadata(cursor, table)
    if not db_columns:
        logger.warning(f"Geen kolommen gevonden voor tabel {table}; tabel overgeslagen.")
        return None

    db_colnames = set(c['name'] for c in db_columns)
    col_lookup = {c['name']: c for c in db_columns}
    enum_columns = getEnumColumns(cursor, table)

    fields, documents = leesDocumenten(col, soort, extra_velden=db_colnames)
    all_doc_keys = getDocumentKolommen(documents)
    kolommen = bepaalUpsertKolommen(fields, all_doc_keys, db_colnames)
    if 'primary_key' not in kolommen:
        kolommen = sorted(set(kolommen) | {'primary_key'})

    data_only = all_doc_keys - db_colnames
    if data_only:
        logger.warning(
            f"Bij het laden van data van {soort} naar tabel {table} "
            f"werd volgende data aangeboden die de tabel niet ondersteunt: {data_only}"
        )

    rijen = []
    for doc in documents:
        transformed = transformRow(doc, kolommen, col_lookup, enum_columns)
        rijen.append(tuple(transformed.get(c) for c in kolommen))

    pk_index = kolommen.index('primary_key')
    ids = [rij[pk_index] for rij in rijen]
    zonder_id = sum(1 for i in ids if i is None)
    if zonder_id:
        msg = (f"{zonder_id} documenten van soort {soort} in Single_Store_Clean hebben geen ID; "
               f"tabel {table} kan niet worden bijgewerkt. Controleer Transform 4 (Set_PrimaryKey_{soort}).")
        logger.error(msg)
        raise Exception(msg)
    dubbel = len(ids) - len(set(ids))
    if dubbel:
        msg = f"{dubbel} dubbele ID's bij soort {soort} in Single_Store_Clean; tabel {table} kan niet worden bijgewerkt."
        logger.error(msg)
        raise Exception(msg)

    geometrie = {'location', 'longitude', 'latitude'} <= db_colnames
    return {'kolommen': kolommen, 'rijen': rijen, 'ids': ids, 'geometrie': geometrie}


def werkTabelBij(cursor, col, table):
    """Werk één Def_-tabel bij: upsert, verwijderen van verdwenen rijen, geometrie en sequence.

    Moet draaien binnen een transactie waarin de betrokken FK-constraints
    verwijderd zijn (zie loadIncrementeel).

    Args:
        cursor: psycopg2 cursor
        col: Single_Store_Clean-collectie
        table: Def_-tabel uit LOAD_TABELLEN

    Returns:
        Dict met tellingen ('upsert': aangeboden rijen, 'ingevoegd', 'bijgewerkt'
        (alleen rijen met een echte wijziging) en 'verwijderd'), of None als de
        tabel niet bestaat
    """
    soort = table[4:]  # Def_ eraf; Def_Bestand hoort bij soort Bestand
    voorbereid = bereidTabelVoor(cursor, col, soort, table)
    if voorbereid is None:
        return None

    # Bestaande primary_keys via dezelfde cursor: deze transactie houdt locks op de tabellen
    pg_rijen = delta_transform.leesPgSleutels(table, cursor=cursor) or []
    bestaand = {int(r['primary_key']) for r in pg_rijen if r.get('primary_key') is not None}

    gewijzigd = upsertRijen(cursor, table, voorbereid['kolommen'], voorbereid['rijen'])
    nieuw = {int(i) for i in voorbereid['ids']} - bestaand
    verdwenen = delta_transform.bepaalVerdwenenPrimaryKeys(pg_rijen, voorbereid['ids'])
    verwijderd = verwijderRijen(cursor, table, verdwenen)

    if voorbereid['geometrie']:
        werkGeometrieBij(cursor, table)
    volgende = zetSequence(cursor, table)

    tellingen = {
        'upsert': len(voorbereid['rijen']),
        'ingevoegd': len(nieuw),
        'bijgewerkt': len({int(i) for i in gewijzigd} - nieuw),
        'verwijderd': verwijderd,
    }
    logger.info(f"Upsert {table}: {tellingen} (volgende primary_key {volgende}).")
    return tellingen


def telDocumenten(col, tabellen):
    """Tel de documenten in Single_Store_Clean van de soorten van de tabellen."""
    return col.count_documents({'soort': {'$in': [t[4:] for t in tabellen]}})


def loadIncrementeel():
    """Taak Load_Upsert: werk de Def_-tabellen bij vanuit Single_Store_Clean (incrementele cyclus).

    Per tabel uit LOAD_TABELLEN (soort = tabelnaam zonder Def_; Def_Bestand is
    soort Bestand):

    1. alle documenten van de soort upserten op primary_key (werkTabelBij);
    2. rijen verwijderen waarvan de primary_key niet meer als ID in
       Single_Store_Clean voorkomt (delta_transform.bepaalVerdwenenPrimaryKeys);
    3. de geometrie (location) bijwerken;
    4. de sequence van primary_key op max + 1 zetten.

    Daarna worden de afgeleide velden van de webapplicatie (aantal_fotos,
    aantal_artefacten, dateringen) voor alle rijen herberekend
    (herberekenAfgeleideVelden, issue 72).

    Alles gebeurt in één transactie, binnen de FK-mechaniek van loadAll: de
    betrokken FK-constraints worden eerst verwijderd, na het bijwerken
    hersteld met NOT VALID en na de commit gevalideerd. SET CONSTRAINTS ALL
    DEFERRED is geen optie: niet alle FK's zijn deferrable (bijv.
    Def_Bestand.artefactID, Def_Doos.projectID, Def_artefact_abr.artefact_id).
    Een verwijzing vanuit een gebruikerstabel naar een verdwenen rij blijft
    staan; de constraint blijft dan NOT VALID (zie tellingen.load.fk_niet_gevalideerd).
    Kan een constraint niet hersteld worden, dan wordt de hele transactie
    teruggedraaid en faalt de taak (anders zou de constraint na de commit
    definitief ontbreken).

    Tabellen met gebruikersdata (GEBRUIKERS_TABELLEN) en Def_Bronbestand
    worden niet geleegd en niet bijgewerkt. De tellingen per tabel komen in het
    run-document onder tellingen.load, die van de afgeleide velden onder
    tellingen.afgeleide_velden.

    Returns:
        Dict met de tellingen per tabel, plus 'afgeleide_velden'
    """
    logger.info("Starten met de incrementele load (upsert) naar PostgreSQL...")
    tabellen = [t for t in LOAD_TABELLEN if t not in GEBRUIKERS_TABELLEN and t not in const.PIPELINE_TABELLEN]

    client = _getClient()
    try:
        col = client[str(config.DB_ANALYSE)][config.COLL_ANALYSE_CLEAN]
        # Vangnet: een lege Single_Store_Clean zou alle Def_-tabellen leegmaken
        if telDocumenten(col, tabellen) == 0:
            msg = ("Single_Store_Clean bevat geen documenten van de te laden soorten; de incrementele load "
                   "zou alle Def_-tabellen leegmaken. Draai de volledige cyclus (Extract_Transform_Load_Full_Cycle).")
            logger.error(msg)
            raise Exception(msg)
        return _upsertAlleTabellen(col, tabellen)
    finally:
        client.close()


def _upsertAlleTabellen(col, tabellen):
    """Voer de upsert van alle tabellen uit in één transactie (zie loadIncrementeel)."""
    conn = getPgConnection()
    try:
        cursor = conn.cursor()
        cursor.execute(f"SET lock_timeout = '{LOCK_TIMEOUT_INCREMENTEEL}'")
        fk_constraints = getBetrokkenFkConstraints(leesFkConstraints(cursor), tabellen)
        logger.info(f"Gevonden: {len(fk_constraints)} betrokken FK constraints om tijdelijk te verwijderen")
        verwijderFkConstraints(cursor, fk_constraints)

        tellingen = {}
        for table in tabellen:
            telling = werkTabelBij(cursor, col, table)
            if telling is not None:
                tellingen[table] = telling

        # Afgeleide velden (issue 72) in dezelfde transactie, zodat de webapplicatie ze nooit
        # verouderd ziet, en vóór het herstel van de FK's: na een ADD CONSTRAINT ... NOT VALID
        # controleert PostgreSQL bij een UPDATE van een rij die deze transactie heeft ingevoegd
        # alle FK's van die rij opnieuw, ook als de verwijzende kolommen niet veranderen.
        afgeleid = herberekenAfgeleideVelden(cursor)

        niet_hersteld = []
        fk_restored, fk_failed = herstelFkConstraints(cursor, fk_constraints, niet_hersteld)
        logger.info(f"FK constraints hersteld: {fk_restored} OK, {fk_failed} mislukt.")
        if fk_failed > 0:
            # Na een commit zou de constraint definitief verdwenen zijn: alles terugdraaien
            msg = (f"Incrementele load afgebroken: {fk_failed} FK constraint(s) konden niet hersteld worden "
                   f"({', '.join(niet_hersteld)}). De transactie wordt teruggedraaid; de constraints en de "
                   f"Def_-tabellen blijven zoals ze vóór de load waren. Zie de waarschuwingen hierboven voor de oorzaak.")
            logger.error(msg)
            raise Exception(msg)
        conn.commit()
        logger.info("Upsert gecommit; FK constraints valideren...")

        niet_gevalideerd = valideerFkConstraints(cursor, fk_constraints)
        conn.commit()

        totaal = {k: sum(t[k] for t in tellingen.values()) for k in ('upsert', 'ingevoegd', 'bijgewerkt', 'verwijderd')}
        resultaat = dict(tellingen, totaal=totaal, fk_niet_hersteld=fk_failed, fk_niet_gevalideerd=niet_gevalideerd)
        run = verwerkingsrun.huidigeRun(verplicht=False)
        if run is not None:
            verwerkingsrun.werkRunBij({'tellingen.load': resultaat, 'tellingen.afgeleide_velden': afgeleid},
                                      run_id=run['run_id'])
        logger.info(f"Incrementele load afgerond: {totaal}; niet gevalideerde FK's: {niet_gevalideerd}.")
        return dict(resultaat, afgeleide_velden=afgeleid)

    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        raise
    finally:
        conn.close()
