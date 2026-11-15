"""Laden van data uit MongoDB naar PostgreSQL.

Gebruikt pymongo voor extractie en psycopg2 voor laden.
Geen pandas of SQLAlchemy afhankelijkheden.

Twee manieren van laden, met dezelfde opbouw van de rijen (leesDocumenten,
transformRow):

- loadAll(): de volledige cyclus. Laadt alles in {tabel}_new-tabellen en
  wisselt die in een 3-fase atomic swap om met de bestaande tabellen.
  Tabellen met gebruikersdata blijven staan (issue 71): Transform 4 kent ook in
  de volledige cyclus stabiele sleutels toe, en verwijzingen naar rijen die
  bij de swap hun primary_key verliezen worden losgekoppeld (bruikleen,
  conservering) of verwijderd (koppelrijen) en waar mogelijk op key weer
  gekoppeld.
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

Beide beginnen met de schemamigratie van de gebruikerstabellen
(migreerSchemaGebruikersdata, issue 73), in een eigen transactie. Beide
koppelen verwijzingen vanuit gebruikerstabellen naar verdwenen rijen los
(bruikleen, conservering) of verwijderen ze (pure koppelrijen), volgens
shared/gebruikersdata.VERWIJZINGEN, met dezelfde helpers
(koppelVerwijzingenLos, ruimVerwijzingenOp, koppelVerwijzingenTerug).
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
import wasstraat.foutbeleid as foutbeleid
import shared.config as config
import shared.const as const
import shared.gebruikersdata as gebruikersdata
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

# Tabellen met gebruikersdata (ingevoerd in de webapplicatie). Geen van beide cycli laadt of
# leegt ze; ze werken alleen verwijzingen naar verdwenen rijen bij volgens
# shared/gebruikersdata.VERWIJZINGEN (issue 73, in de volledige cyclus sinds issue 71).
GEBRUIKERS_TABELLEN = [
    'Def_artefact_abr', 'Def_Bruikleen',
    'Def_artefact_conservering', 'Def_Conserveringsproject', 'Def_Partij',
]

# Tabellen waarvan de primary_key uit de bron komt (de ABR-thesaurus, zie
# delta_transform.getBronPrimaryKey). Daar is de primary_key zelf de identiteit: een andere
# key bij dezelfde primary_key (bijv. een gewijzigde uri in een nieuwe ABR-versie) is geen
# hernummering (issue 71, bepaalVervallenSleutels).
TABELLEN_MET_BRON_PRIMARY_KEY = ['Def_ABR']

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


def vulLaadKey(soort, doc):
    """Vul bij een document zonder key de key in waarmee het in PostgreSQL wordt teruggevonden.

    Artefacten zonder key krijgen de samengestelde sleutel key_subnr|artefactsoort
    (de kolom key van Def_Artefact was leeg, omdat artefacten zelden een
    artefactnr hebben). Documenten zonder natuurlijke key, zoals artefacten
    zonder subnr, monsters, plaatsingen en vindplaatsen, krijgen de hulpsleutel
    uit hun bronrij (issue 81). Zie delta_transform.getLaadKey; Transform 4
    (setStabielePrimaryKeys) vergelijkt op dezelfde key.

    Args:
        soort: soort van het document
        doc: document uit Single_Store_Clean (wordt aangepast)

    Returns:
        Het document
    """
    if isNanOrEmpty(doc.get('key')):
        doc['key'] = delta_transform.getLaadKey(soort, doc)
    return doc


def vulArtefactKey(doc):
    """Vul bij een artefact zonder key de key in (vulLaadKey voor soort Artefact)."""
    return vulLaadKey('Artefact', doc)


def leesDocumenten(col, soort, extra_velden=None):
    """Lees de documenten van een soort uit Single_Store_Clean voor het laden naar PostgreSQL.

    De velden komen uit getFields, aangevuld met extra_velden (de kolommen van
    de doeltabel). getFields kijkt behalve naar meta.py alleen naar een
    steekproef van tien documenten; een veld dat pas later in de pipeline
    wordt gezet (zoals artefactID op foto's, door setReferences) en dat in die
    tien documenten ontbreekt, zou anders voor de hele tabel niet gelezen
    worden. Documenten zonder key krijgen zo nodig de samengestelde sleutel
    (artefacten) of de hulpsleutel uit hun bronrij (vulLaadKey, issue 81).

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
    projection['key'] = 1
    if soort not in delta_transform.SOORTEN_ZONDER_BRONSLEUTEL:
        projection['brondata'] = 1
    if soort == 'Artefact':
        projection.update({'key_subnr': 1, 'artefactsoort': 1, 'projectcd': 1, 'putnr': 1, 'vondstnr': 1})
    documents = list(col.find({'soort': soort}, projection=projection))
    for doc in documents:
        vulLaadKey(soort, doc)
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
# - datering_tot: de artefactdatering, anders de vondstdatering, anders de spoordatering.
# - aantal_artefacten: het aantal artefacten met een projectID naar het project; 0 zonder.
#
# 'Anders' betekent leeg of 0: init.init() zet zelf alleen datering_vanaf/_tot uit de
# artefactdatering, maar elke flush van een gewijzigd artefact roept de observers van
# models.py aan (@observes van sqlalchemy_utils), die 'if not ...' gebruiken en zo de
# vondst- en spoordatering invullen. Tot oktober 2026 viel datering_tot niet terug op de
# spoordatering, omdat in models.py twee observers dezelfde naam spoor_observer hadden en de
# tweede (spoordatering_vanaf) de eerste (spoordatering_tot) overschreef; dat is hersteld en
# de pipeline en init.init() geven nu voor vanaf en tot dezelfde voorrang.
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
                        WHEN COALESCE(v.vondstdatering_tot, 0) <> 0 THEN v.vondstdatering_tot
                        ELSE s.spoordatering_tot END AS datering_tot
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
# Schemamigratie van de gebruikerstabellen (issue 73, gedeeld door loadAll en loadIncrementeel)
# ============================================================

def migreerSchemaGebruikersdata(conn, lock_timeout=LOCK_TIMEOUT_INCREMENTEEL):
    """Breng het schema van de gebruikerstabellen in orde, in een eigen transactie (issue 73).

    Maakt de verwijzingen die losgekoppeld kunnen worden nullable en voegt de
    kolommen van de markering toe (zie shared/gebruikersdata.migreerSchema).
    db.create_all() van de webapplicatie doet dat niet bij bestaande tabellen;
    zo gaan bestaande installaties (ook die uit deploy/) zonder handwerk mee.
    Idempotent: als het schema al klopt wordt er alleen gelezen. De webapplicatie
    voert dezelfde migratie uit bij het starten.

    Args:
        conn: psycopg2-verbinding zonder openstaande transactie (wordt gecommit)
        lock_timeout: maximale wachttijd op een lock (ALTER TABLE vraagt een ACCESS EXCLUSIVE-lock)

    Returns:
        Lijst met de uitgevoerde ALTER TABLE-statements
    """
    uitgevoerd = gebruikersdata.migreerSchemaInTransactie(conn, lock_timeout)
    if uitgevoerd:
        logger.info(f"Schemamigratie gebruikerstabellen: {len(uitgevoerd)} wijziging(en) uitgevoerd.")
    else:
        logger.info("Schemamigratie gebruikerstabellen: schema is al bijgewerkt.")
    return uitgevoerd


# ============================================================
# Volledige cyclus: gebruikersdata bij de atomic swap (issue 71)
# ============================================================

def bepaalVervallenRijen(cursor, tabel, nieuwe_tabel, vergelijk_key=True):
    """Bepaal welke rijen van een Def_-tabel bij de atomic swap hun primary_key verliezen.

    Vergelijkt de huidige tabel met de nieuw geladen tabel op primary_key:

    - verdwenen: de primary_key komt in de nieuwe tabel niet meer voor (de
      entiteit is weg, of heeft een nieuw nummer gekregen omdat zijn key niet
      uniek is);
    - hernummerd (alleen met vergelijk_key): de primary_key komt wel voor, maar
      bij een rij met een andere key. Dan zijn de sleutels in
      Single_Store_Clean niet stabiel toegekend (bijv. DAG_Load_Only op
      MongoDB-data uit een andere backup dan PostgreSQL) en wijst hetzelfde
      nummer naar een andere entiteit. Een rij zonder key in de huidige tabel
      telt niet als hernummerd, en ook geen rij met dezelfde bronsleutel in de
      oude en de nieuwe tabel (issue 88): dat is dezelfde bronrij, die
      Transform 4 op een vervangende key heeft teruggevonden, bijvoorbeeld een
      artefact dat zijn natuurlijke key terugkrijgt.

    Args:
        cursor: psycopg2 cursor
        tabel: de huidige tabel (bijv. 'Def_Artefact')
        nieuwe_tabel: de nieuw geladen tabel (bijv. 'Def_Artefact_new')
        vergelijk_key: False voor tabellen waarin de key niet de identiteit is
            (zie getTabellenMetKeyControle); dan alleen verdwenen rijen

    Returns:
        Dict met gesorteerde lijsten 'verdwenen' en 'hernummerd'
    """
    kolommen = {c['name'] for c in getColumnMetadata(cursor, tabel)}
    vervallen = {'verdwenen': [], 'hernummerd': []}
    if 'primary_key' not in kolommen:
        return vervallen
    andere_key = ('o.key IS NOT NULL AND o.key IS DISTINCT FROM n.key'
                  if vergelijk_key and 'key' in kolommen else 'FALSE')
    cursor.execute(f'SELECT o.primary_key, n.primary_key IS NULL FROM "{tabel}" AS o '
                   f'LEFT JOIN "{nieuwe_tabel}" AS n ON n.primary_key = o.primary_key '
                   f'WHERE n.primary_key IS NULL OR ({andere_key})')
    for primary_key, verdwenen in cursor.fetchall():
        vervallen['verdwenen' if verdwenen else 'hernummerd'].append(int(primary_key))
    if vervallen['hernummerd'] and 'brondata' in kolommen:
        vervallen['hernummerd'] = _zonderZelfdeBronrij(cursor, tabel, nieuwe_tabel, vervallen['hernummerd'])
    vervallen['verdwenen'].sort()
    vervallen['hernummerd'].sort()
    return vervallen


def _zonderZelfdeBronrij(cursor, tabel, nieuwe_tabel, primary_keys):
    """Laat de primary_keys weg waarvan de oude en de nieuwe rij dezelfde bronsleutel hebben (issue 88).

    Args:
        cursor: psycopg2 cursor
        tabel: de huidige tabel
        nieuwe_tabel: de nieuw geladen tabel
        primary_keys: primary_keys met een andere key in de nieuwe tabel

    Returns:
        Lijst met de primary_keys die echt bij een andere bronrij horen
    """
    cursor.execute(f'SELECT o.primary_key, o.brondata, n.brondata FROM "{tabel}" AS o '
                   f'JOIN "{nieuwe_tabel}" AS n ON n.primary_key = o.primary_key '
                   f'WHERE o.primary_key = ANY(%s)', (list(primary_keys),))
    zelfde = set()
    for primary_key, oud, nieuw in cursor.fetchall():
        bron_oud = delta_transform.getBronsleutel(delta_transform.leesBrondataTekst(oud))
        if bron_oud is not None and bron_oud == delta_transform.getBronsleutel(delta_transform.leesBrondataTekst(nieuw)):
            zelfde.add(int(primary_key))
    if zelfde:
        logger.info(f"{len(zelfde)} rijen in {tabel} houden hun primary_key met een andere key maar dezelfde bronrij "
                    f"(teruggevonden op een vervangende key); die tellen niet als hernummerd.")
    return [pk for pk in primary_keys if pk not in zelfde]


def getTabellenMetKeyControle():
    """Retourneer de tabellen waarin bepaalVervallenSleutels ook op hernummerde rijen controleert.

    Dat zijn de tabellen waarnaar gebruikersdata verwijst (shared/gebruikersdata.VERWIJZINGEN:
    Def_Artefact en Def_Project) en waarin de key de identiteit is: Transform 4
    koppelt daar in de volledige cyclus alleen op een unieke key, dus bij
    stabiele sleutels hoort bij dezelfde primary_key altijd dezelfde key. Niet
    in TABELLEN_MET_BRON_PRIMARY_KEY (Def_ABR) en niet in andere tabellen: daar
    kan een entiteit zijn primary_key houden terwijl zijn key verandert (een
    bestand op map en bestandsnaam), en geen gebruikersdata verwijst ernaar.

    Returns:
        Gesorteerde lijst met tabelnamen
    """
    return sorted({v['doel'] for v in gebruikersdata.VERWIJZINGEN} - set(TABELLEN_MET_BRON_PRIMARY_KEY))


def bepaalVervallenSleutels(cursor, tabellen):
    """Bepaal per tabel de vervallen primary_keys (bepaalVervallenRijen) en meld ze in het log.

    Op hernummerde rijen wordt alleen gecontroleerd in de tabellen van
    getTabellenMetKeyControle. Een waarschuwing volgt als er rijen hernummerd
    zijn: dan zijn de sleutels in Single_Store_Clean niet stabiel en worden
    verwijzingen vanuit gebruikerstabellen naar die rijen losgekoppeld (en waar
    de key uniek is weer gekoppeld) of verwijderd (koppelrijen).

    Args:
        cursor: psycopg2 cursor
        tabellen: lijst met (tabel, nieuwe_tabel)

    Returns:
        Dict per tabel met de lijsten 'verdwenen' en 'hernummerd'
    """
    met_key_controle = set(getTabellenMetKeyControle())
    vervallen = {}
    for tabel, nieuwe_tabel in tabellen:
        vervallen[tabel] = bepaalVervallenRijen(cursor, tabel, nieuwe_tabel, tabel in met_key_controle)
    aantallen = {t: {k: len(v) for k, v in rijen.items()} for t, rijen in vervallen.items()
                 if rijen['verdwenen'] or rijen['hernummerd']}
    logger.info(f"Rijen die bij de swap hun primary_key verliezen (verdwenen, of met een nieuw nummer omdat hun "
                f"key niet uniek is): {aantallen or 'geen'}")
    hernummerd = {t: a['hernummerd'] for t, a in aantallen.items() if a['hernummerd']}
    if hernummerd:
        logger.warning(f"Sleutels niet stabiel: bij {hernummerd} rijen hoort dezelfde primary_key na het laden bij "
                       f"een andere key. Single_Store_Clean heeft geen stabiele sleutels gekregen (bijv. "
                       f"DAG_Load_Only op MongoDB-data die niet bij deze PostgreSQL-database hoort, zoals na een "
                       f"restore van een andere backup). Gebruikersdata die naar die rijen "
                       f"verwijst wordt losgekoppeld (met markering) en alleen bij een unieke key weer gekoppeld; "
                       f"koppelrijen worden verwijderd. Draai de volledige cyclus om dit te voorkomen.")
        foutbeleid.meld(foutbeleid.NIVEAU_WAARSCHUWING, foutbeleid.SOORT_SLEUTELS_NIET_STABIEL,
                        f"Sleutels niet stabiel: rijen die na het laden een primary_key hebben die eerder bij een "
                        f"andere key hoorde: {hernummerd}. Gebruikersdata die ernaar verwees is losgekoppeld en waar "
                        f"mogelijk op key teruggekoppeld. Draai de volledige cyclus.",
                        aantal=sum(hernummerd.values()), details=hernummerd)
    return vervallen


def _telRijen(cursor, tabel):
    """Tel de rijen van een tabel (0 als de telling niets oplevert)."""
    cursor.execute(f'SELECT COUNT(*) FROM "{tabel}"')
    rij = cursor.fetchone()
    return int(rij[0]) if rij and rij[0] is not None else 0


def telLaadRijen(cursor, tabellen, vervallen):
    """Tel per tabel de rijen vóór en na de volledige load (issue 54/62, voor het run-document).

    Vergelijkt de huidige tabel met de nieuw geladen {tabel}_new-tabel:
    ingevoegd zijn de rijen met een primary_key die er nog niet was,
    verwijderd de rijen waarvan de primary_key verdwijnt (bepaalVervallenRijen).

    Args:
        cursor: psycopg2 cursor
        tabellen: lijst met (tabel, nieuwe_tabel)
        vervallen: dict uit bepaalVervallenSleutels

    Returns:
        Dict per tabel met rijen_voor, rijen, ingevoegd, verwijderd en hernummerd, plus 'totaal'
    """
    tellingen = {}
    for tabel, nieuwe_tabel in tabellen:
        voor = _telRijen(cursor, tabel)
        na = _telRijen(cursor, nieuwe_tabel)
        rijen = vervallen.get(tabel) or {}
        verwijderd = len(rijen.get('verdwenen', []))
        tellingen[tabel] = {'rijen_voor': voor, 'rijen': na, 'ingevoegd': max(na - voor + verwijderd, 0),
                            'verwijderd': verwijderd, 'hernummerd': len(rijen.get('hernummerd', []))}
    velden = ['rijen_voor', 'rijen', 'ingevoegd', 'verwijderd', 'hernummerd']
    tellingen['totaal'] = {k: sum(t[k] for t in tellingen.values()) for k in velden}
    return tellingen


def koppelGebruikersdataLos(cursor, vervallen, verwijzingen, tellingen):
    """Koppel gebruikersdata los van rijen die bij de swap hun primary_key verliezen (vóór de rename).

    Moet vóór de rename draaien: koppelVerwijzingenLos haalt de key voor de
    markering uit de huidige (oude) tabel. Per doeltabel van een verwijzing:
    verwijzingen met beleid LOSKOPPELEN worden losgekoppeld met markering,
    koppelrijen (VERWIJDEREN) worden verwijderd. Verdwenen en hernummerde rijen
    worden gelijk behandeld.

    Args:
        cursor: psycopg2 cursor, binnen de swap-transactie (FK-constraints verwijderd)
        vervallen: dict uit bepaalVervallenSleutels
        verwijzingen: lijst uit bepaalVerwijzingen
        tellingen: dict uit bepaalVerwijzingen, wordt bijgewerkt
    """
    for doel in sorted({v['doel'] for v in verwijzingen}):
        rijen = vervallen.get(doel, {})
        primary_keys = sorted(set(rijen.get('verdwenen', [])) | set(rijen.get('hernummerd', [])))
        koppelVerwijzingenLos(cursor, doel, primary_keys, verwijzingen, tellingen)
        verwijderKoppelrijen(cursor, doel, primary_keys, verwijzingen, tellingen)


def werkGebruikersdataBijNaSwap(cursor, verwijzingen, tellingen):
    """Ruim na de rename verwijzingen zonder doel op en koppel losgekoppelde rijen terug op key.

    ruimVerwijzingenOp is het vangnet voor verwijzingen naar een rij die niet
    (meer) bestaat, bijvoorbeeld van vóór issue 73; koppelVerwijzingenTerug
    koppelt losgekoppelde rijen (ook uit eerdere runs) aan de rij met dezelfde,
    unieke key in de nieuwe tabel.

    Args:
        cursor: psycopg2 cursor, binnen de swap-transactie (na de rename)
        verwijzingen: lijst uit bepaalVerwijzingen
        tellingen: dict uit bepaalVerwijzingen, wordt bijgewerkt
    """
    for doel in sorted({v['doel'] for v in verwijzingen}):
        ruimVerwijzingenOp(cursor, doel, verwijzingen, tellingen)
    koppelVerwijzingenTerug(cursor, verwijzingen, tellingen)
    logger.info(f"Verwijzingen vanuit gebruikerstabellen bijgewerkt: {tellingen}")


def schrijfLoadTellingen(laadtellingen, gebruikers, afgeleid):
    """Schrijf de tellingen van de volledige load in het run-document van de lopende run (als die er is).

    Zelfde velden als de incrementele load: tellingen.load (per tabel
    rijen_voor, rijen, ingevoegd, verwijderd en hernummerd, plus totaal,
    fk_niet_hersteld en fk_niet_gevalideerd), tellingen.gebruikersdata en
    tellingen.afgeleide_velden (alleen als de herberekening slaagde). Een fout
    bij het schrijven wordt gelogd: de data is dan al geladen.

    Args:
        laadtellingen: dict uit telLaadRijen, aangevuld met de FK-tellingen
        gebruikers: tellingen van de verwijzingen vanuit gebruikerstabellen
        afgeleid: tellingen van herberekenAfgeleideVelden, of None
    """
    try:
        run = verwerkingsrun.runVanTaak()
        if run is None:
            return
        velden = {'tellingen.load': laadtellingen, 'tellingen.gebruikersdata': gebruikers}
        if afgeleid is not None:
            velden['tellingen.afgeleide_velden'] = afgeleid
        verwerkingsrun.werkRunBij(velden, run_id=run['run_id'])
    except Exception as err:
        logger.warning(f"Tellingen van de load niet in het run-document geschreven: {err}")


# ============================================================
# Hoofdfunctie: 3-fase atomic swap
# ============================================================

def loadAll():
    """Laad alle data uit MongoDB naar PostgreSQL via een 3-fase atomic swap.

    Fase 1: Laad data in tijdelijke {tabel}_new tabellen en bepaal per tabel
            welke rijen hun primary_key verliezen (bepaalVervallenSleutels)
    Fase 2a: Atomic rename swap: drop FK → gebruikersdata loskoppelen van
            vervallen rijen (koppelGebruikersdataLos) → rename → verwijzingen
            opruimen en op key terugkoppelen (werkGebruikersdataBijNaSwap)
    Fase 2b: Herstel FK constraints met NOT VALID + SAVEPOINTs
    Fase 3: Opruimen _old tabellen, herstel de sequences van primary_key
            (zetSequence) en valideer FK constraints
    Fase 4: Herbereken de afgeleide velden van de webapplicatie
            (herberekenAfgeleideVelden, issue 72), zodat ze na een volledige
            cyclus gevuld zijn zonder Flask te herstarten. Een fout hierin is
            sinds issue 54 een waarschuwing: de data is dan al geladen.

    Foutbeleid (issue 54): een fout bij het laden of de swap laat de taak
    falen. Een FK-constraint die na de swap niet hersteld of niet gevalideerd
    kan worden, hernummerde sleutels en een fout in de afgeleide velden zijn
    waarschuwingen in de meldingen van het run-document. De tellingen komen,
    als er een run actief is (volledige cyclus, DAG_Load_Only), in het
    run-document (schrijfLoadTellingen).

    Vooraf, in een eigen transactie: de schemamigratie van de
    gebruikerstabellen (migreerSchemaGebruikersdata, issue 73).

    De tabellen met gebruikersdata (GEBRUIKERS_TABELLEN) worden niet geladen,
    niet geswapt en niet geleegd (issue 71). Transform 4 kent stabiele
    sleutels toe, dus een entiteit houdt zijn primary_key; verwijzingen naar
    rijen die toch hun primary_key verliezen worden volgens
    shared/gebruikersdata.VERWIJZINGEN losgekoppeld of verwijderd, zodat de
    FK-constraints valideren. De sequences van de gebruikerstabellen blijven
    ongemoeid.

    Returns:
        Dict met 'vervallen' (per tabel het aantal verdwenen en hernummerde
        rijen), 'gebruikersdata' (tellingen per gebruikerstabel en kolom),
        'load' (telLaadRijen plus de FK-tellingen) en 'afgeleide_velden'
        (None als de herberekening mislukte)
    """
    logger.info("Starting Loading data to relational database...")

    logger.info(f"Connecting to {maskeerWachtwoord(config.SQLALCHEMY_DATABASE_URI)}")
    conn = getPgConnection()

    lst_tables = list(LOAD_TABELLEN)

    temp_tables_created = []

    try:
        # Schemamigratie van de gebruikerstabellen (issue 73), vóór de rest en in een eigen transactie
        migreerSchemaGebruikersdata(conn)

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

            # Welke rijen verliezen bij de swap hun primary_key (issue 71)? Hier, buiten de
            # swap-transactie: de vergelijking leest alleen en houdt geen exclusieve locks.
            vervallen = bepaalVervallenSleutels(cursor, temp_tables_created)
            # Rijen per tabel vóór en na de load (run-document en verwerkingsrapport, issues 54 en 62)
            laadtellingen = telLaadRijen(cursor, temp_tables_created, vervallen)

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
        # FK constraints worden hier gedropt en de tabellen hernoemd. De
        # gebruikerstabellen blijven staan (issue 71); hun verwijzingen naar
        # vervallen rijen worden in dezelfde transactie bijgewerkt.
        # ============================================================
        logger.info("FASE 2a: Atomic swap van tabellen...")

        # Stel een lock-timeout in: wacht maximaal 5 seconden op locks.
        cursor.execute("SET lock_timeout = '5s'")

        # Bewaar FK-constraint definities (alleen Def_-tabellen) zodat we ze
        # na de swap kunnen herstellen, en drop ze.
        fk_constraints = leesFkConstraints(cursor)
        logger.info(f"Gevonden: {len(fk_constraints)} FK constraints om tijdelijk te verwijderen")
        verwijderFkConstraints(cursor, fk_constraints)

        # Gebruikersdata loskoppelen van rijen die hun primary_key verliezen, vóór de rename
        # (de key voor de markering komt uit de huidige tabel)
        verwijzingen, gebruikers = bepaalVerwijzingen(cursor, lst_tables)
        koppelGebruikersdataLos(cursor, vervallen, verwijzingen, gebruikers)

        # Rename is instant (PostgreSQL past alleen de systeemcatalogus aan)
        for orig, temp in temp_tables_created:
            old_table = f"{orig}_old"
            cursor.execute(f'DROP TABLE IF EXISTS "{old_table}" CASCADE')
            cursor.execute(f'ALTER TABLE "{orig}" RENAME TO "{old_table}"')
            cursor.execute(f'ALTER TABLE "{temp}" RENAME TO "{orig}"')

        # Verwijzingen zonder doel opruimen en losgekoppelde rijen op key terugkoppelen
        werkGebruikersdataBijNaSwap(cursor, verwijzingen, gebruikers)

        conn.commit()
        logger.info("Swap voltooid.")

        # ============================================================
        # FASE 2b: Herstel FK constraints in een aparte transactie.
        # Gebruik een SAVEPOINT per constraint zodat één fout niet
        # alle overige constraints blokkeert (poisoned transaction).
        # ============================================================
        logger.info("FASE 2b: Herstel FK constraints met NOT VALID...")
        niet_hersteld = []
        fk_restored, fk_failed = herstelFkConstraints(cursor, fk_constraints, niet_hersteld)

        conn.commit()
        logger.info(f"FK constraints hersteld: {fk_restored} OK, {fk_failed} mislukt.")
        if fk_failed:
            # De swap is al gecommit; de load gaat door, maar de constraints ontbreken nu (issue 54: waarschuwing)
            foutbeleid.meld(foutbeleid.NIVEAU_WAARSCHUWING, foutbeleid.SOORT_FK_NIET_HERSTELD,
                            f"{fk_failed} FK-constraint(s) konden na de swap niet hersteld worden en ontbreken: "
                            f"{niet_hersteld}. Zie de waarschuwingen in het log van LoadToDatabase_postgres.",
                            aantal=fk_failed, details=niet_hersteld)

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
        niet_gevalideerd = valideerFkConstraints(cursor, fk_constraints)

        conn.commit()
        if niet_gevalideerd:
            foutbeleid.meld(foutbeleid.NIVEAU_WAARSCHUWING, foutbeleid.SOORT_FK_NIET_GEVALIDEERD,
                            f"{len(niet_gevalideerd)} FK-constraint(s) konden niet gevalideerd worden en blijven NOT VALID "
                            f"(er zijn rijen die naar een niet-bestaande rij verwijzen): {niet_gevalideerd}.",
                            aantal=len(niet_gevalideerd), details=niet_gevalideerd)

        # ============================================================
        # FASE 4: Afgeleide velden van de webapplicatie (issue 72), in een
        # eigen transactie. De nieuwe tabellen hebben ze leeg; voorheen vulde
        # alleen init.init() van Flask ze, en alleen bij het (her)starten.
        # ============================================================
        logger.info("FASE 4: Afgeleide velden herberekenen...")
        afgeleid = None
        try:
            afgeleid = herberekenAfgeleideVelden(cursor)
            conn.commit()
        except Exception as err:
            # De data is geladen; verouderde afgeleide velden zijn een waarschuwing (issue 54).
            # init.init() van de webapplicatie is het vangnet en de volgende load herstelt ze.
            conn.rollback()
            msg = (f"De afgeleide velden (aantal_fotos, aantal_artefacten, dateringen) konden niet herberekend "
                   f"worden: {err}. De data is wel geladen; de velden zijn tot de volgende load leeg of verouderd.")
            logger.error(msg)
            foutbeleid.meld(foutbeleid.NIVEAU_WAARSCHUWING, foutbeleid.SOORT_AFGELEIDE_VELDEN, msg)
        logger.info("Laden naar database succesvol afgerond.")

        laadtellingen.update({'fk_niet_hersteld': fk_failed, 'fk_niet_hersteld_namen': niet_hersteld,
                              'fk_niet_gevalideerd': niet_gevalideerd})
        schrijfLoadTellingen(laadtellingen, gebruikers, afgeleid)
        return {
            'vervallen': {t: {k: len(v) for k, v in rijen.items()} for t, rijen in vervallen.items()},
            'gebruikersdata': gebruikers,
            'load': laadtellingen,
            'afgeleide_velden': afgeleid,
        }

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


# ------------------------------------------------------------
# Verwijzingen vanuit gebruikerstabellen naar verdwenen rijen (issue 73)
# ------------------------------------------------------------

def bepaalVerwijzingen(cursor, tabellen):
    """Selecteer de verwijzingen uit gebruikersdata.VERWIJZINGEN naar de tabellen die worden bijgewerkt.

    Alleen verwijzingen waarvan de gebruikerstabel bestaat en de nodige kolommen
    heeft: de verwijzende kolom en bij LOSKOPPELEN de markering (die maakt
    migreerSchemaGebruikersdata aan het begin van de load aan).

    Args:
        cursor: psycopg2 cursor
        tabellen: de Def_-tabellen die de load bijwerkt

    Returns:
        Tuple (lijst met verwijzingen, dict met de beginstand van de tellingen per
        gebruikerstabel en kolom: bij LOSKOPPELEN 'losgekoppeld', 'teruggekoppeld' en
        'dubbele_key', bij VERWIJDEREN 'verwijderd')
    """
    verwijzingen = []
    tellingen = {}
    kolommen_per_tabel = {}
    for verwijzing in gebruikersdata.VERWIJZINGEN:
        if verwijzing['doel'] not in tabellen:
            continue
        tabel = verwijzing['tabel']
        if tabel not in kolommen_per_tabel:
            kolommen_per_tabel[tabel] = {c['name'] for c in getColumnMetadata(cursor, tabel)}
        nodig = {verwijzing['kolom']} | {naam for naam, _ in gebruikersdata.getMarkeringKolommen(verwijzing)}
        ontbrekend = nodig - kolommen_per_tabel[tabel]
        if ontbrekend:
            if kolommen_per_tabel[tabel]:
                logger.warning(f"Tabel {tabel} mist de kolommen {sorted(ontbrekend)}; verwijzingen in "
                               f"{tabel}.{verwijzing['kolom']} naar verdwenen rijen worden niet bijgewerkt.")
            continue
        verwijzingen.append(verwijzing)
        if verwijzing['beleid'] == gebruikersdata.LOSKOPPELEN:
            telling = {'losgekoppeld': 0, 'teruggekoppeld': 0, 'dubbele_key': 0}
        else:
            telling = {'verwijderd': 0}
        tellingen.setdefault(tabel, {})[verwijzing['kolom']] = telling
    return verwijzingen, tellingen


def _markering(verwijzing):
    """Kolomnamen (key, tijdstip) van de markering van een verwijzing met beleid LOSKOPPELEN."""
    key_kolom, op_kolom = [naam for naam, _ in gebruikersdata.getMarkeringKolommen(verwijzing)]
    return key_kolom, op_kolom


def koppelVerwijzingenLos(cursor, doel, primary_keys, verwijzingen, tellingen):
    """Koppel rijen in gebruikerstabellen los van rijen die uit doel verwijderd gaan worden.

    Moet vóór het verwijderen draaien: de key van de verdwijnende rij komt uit
    doel. Voor elke verwijzing met beleid LOSKOPPELEN naar doel wordt de
    verwijzing NULL en krijgt de markering de key van de verdwijnende rij en het
    tijdstip (CURRENT_TIMESTAMP: het begin van de transactie, voor alle rijen
    van een run hetzelfde). Verwijzingen met beleid VERWIJDEREN ruimt
    ruimVerwijzingenOp na het verwijderen op.

    Args:
        cursor: psycopg2 cursor
        doel: Def_-tabel waaruit rijen verdwijnen
        primary_keys: de primary_keys die verdwijnen
        verwijzingen: lijst uit bepaalVerwijzingen
        tellingen: dict uit bepaalVerwijzingen; 'losgekoppeld' wordt opgehoogd

    Returns:
        Aantal losgekoppelde rijen
    """
    totaal = 0
    if not primary_keys:
        return totaal
    for verwijzing in verwijzingen:
        if verwijzing['doel'] != doel or verwijzing['beleid'] != gebruikersdata.LOSKOPPELEN:
            continue
        tabel, kolom = verwijzing['tabel'], verwijzing['kolom']
        key_kolom, op_kolom = _markering(verwijzing)
        keys = []
        for batch in delta_transform.inBatches(primary_keys):
            cursor.execute(f'UPDATE "{tabel}" AS g SET "{kolom}" = NULL, "{key_kolom}" = d.key, '
                           f'"{op_kolom}" = CURRENT_TIMESTAMP FROM "{doel}" AS d '
                           f'WHERE d.primary_key = g."{kolom}" AND d.primary_key = ANY(%s) '
                           f'RETURNING g."{key_kolom}"', (list(batch),))
            keys.extend(rij[0] for rij in cursor.fetchall())
        if keys:
            tellingen[tabel][kolom]['losgekoppeld'] += len(keys)
            totaal += len(keys)
            logger.info(f"{len(keys)} rij(en) in {tabel} losgekoppeld van verdwenen rijen in {doel} "
                        f"({kolom} leeg, key in {key_kolom}): {sorted(str(k) for k in keys)[:20]}")
    return totaal


def verwijderKoppelrijen(cursor, doel, primary_keys, verwijzingen, tellingen):
    """Verwijder koppelrijen (beleid VERWIJDEREN) die verwijzen naar rijen van doel die hun primary_key verliezen.

    Voor de volledige cyclus (issue 71): een koppelrij naar een rij die in de
    nieuwe tabel niet meer bestaat ruimt ruimVerwijzingenOp na de swap ook op,
    maar een rij waarvan de primary_key bij een andere entiteit terechtkomt
    (hernummerd) niet. Deze functie verwijdert beide vóór de swap.

    Args:
        cursor: psycopg2 cursor
        doel: Def_-tabel waarvan rijen hun primary_key verliezen
        primary_keys: de primary_keys die vervallen
        verwijzingen: lijst uit bepaalVerwijzingen
        tellingen: dict uit bepaalVerwijzingen; 'verwijderd' wordt opgehoogd

    Returns:
        Aantal verwijderde koppelrijen
    """
    totaal = 0
    if not primary_keys:
        return totaal
    for verwijzing in verwijzingen:
        if verwijzing['doel'] != doel or verwijzing['beleid'] != gebruikersdata.VERWIJDEREN:
            continue
        tabel, kolom = verwijzing['tabel'], verwijzing['kolom']
        aantal = 0
        for batch in delta_transform.inBatches(primary_keys):
            cursor.execute(f'DELETE FROM "{tabel}" AS g WHERE g."{kolom}" = ANY(%s)', (list(batch),))
            aantal += cursor.rowcount
        if aantal:
            tellingen[tabel][kolom]['verwijderd'] += aantal
            totaal += aantal
            logger.info(f"{aantal} koppelrij(en) in {tabel} verwijderd: {kolom} verwees naar een rij in {doel} "
                        f"die bij de volledige load zijn primary_key verliest.")
    return totaal


def ruimVerwijzingenOp(cursor, doel, verwijzingen, tellingen):
    """Werk verwijzingen vanuit gebruikerstabellen bij die naar een niet-bestaande rij in doel wijzen.

    Na het verwijderen van rijen uit doel:

    - VERWIJDEREN (pure koppelrijen): de rijen worden verwijderd;
    - LOSKOPPELEN: vangnet voor verwijzingen die koppelVerwijzingenLos niet
      heeft gezien, bijvoorbeeld uit een incrementele run van vóór issue 73,
      waardoor de FK-constraint NOT VALID bleef. De verwijzing wordt NULL en het
      tijdstip wordt gezet; de key van de verdwenen rij is niet meer bekend en
      blijft leeg.

    Args:
        cursor: psycopg2 cursor
        doel: Def_-tabel die is bijgewerkt
        verwijzingen: lijst uit bepaalVerwijzingen
        tellingen: dict uit bepaalVerwijzingen; 'verwijderd' of 'losgekoppeld' wordt opgehoogd
    """
    for verwijzing in verwijzingen:
        if verwijzing['doel'] != doel:
            continue
        tabel, kolom = verwijzing['tabel'], verwijzing['kolom']
        zonder_doel = (f'g."{kolom}" IS NOT NULL AND NOT EXISTS '
                       f'(SELECT 1 FROM "{doel}" AS d WHERE d.primary_key = g."{kolom}")')
        if verwijzing['beleid'] == gebruikersdata.VERWIJDEREN:
            cursor.execute(f'DELETE FROM "{tabel}" AS g WHERE {zonder_doel}')
            if cursor.rowcount:
                tellingen[tabel][kolom]['verwijderd'] += cursor.rowcount
                logger.info(f"{cursor.rowcount} koppelrij(en) in {tabel} verwijderd: {kolom} verwees naar een "
                            f"verdwenen rij in {doel}.")
        else:
            key_kolom, op_kolom = _markering(verwijzing)
            cursor.execute(f'UPDATE "{tabel}" AS g SET "{kolom}" = NULL, "{key_kolom}" = NULL, '
                           f'"{op_kolom}" = CURRENT_TIMESTAMP WHERE {zonder_doel}')
            if cursor.rowcount:
                tellingen[tabel][kolom]['losgekoppeld'] += cursor.rowcount
                logger.warning(f"{cursor.rowcount} rij(en) in {tabel} verwezen via {kolom} naar een niet-bestaande "
                               f"rij in {doel} (achtergebleven uit een eerdere run); losgekoppeld zonder key.")


def koppelVerwijzingenTerug(cursor, verwijzingen, tellingen):
    """Koppel losgekoppelde rijen weer aan een teruggekeerde rij met dezelfde key.

    Voor elke verwijzing met beleid LOSKOPPELEN: rijen met een lege verwijzing en
    een markering waarvan de key nu precies één keer in de doeltabel voorkomt,
    krijgen de primary_key van die rij en de markering wordt gewist. Komt de key
    vaker voor, dan is niet te zeggen welke rij bedoeld is (dezelfde regel als
    delta_transform.bepaalStabieleIds); die rijen blijven losgekoppeld en worden
    geteld als 'dubbele_key'.

    Args:
        cursor: psycopg2 cursor
        verwijzingen: lijst uit bepaalVerwijzingen
        tellingen: dict uit bepaalVerwijzingen; 'teruggekoppeld' en 'dubbele_key' worden gezet
    """
    for verwijzing in verwijzingen:
        if verwijzing['beleid'] != gebruikersdata.LOSKOPPELEN:
            continue
        tabel, kolom, doel = verwijzing['tabel'], verwijzing['kolom'], verwijzing['doel']
        key_kolom, op_kolom = _markering(verwijzing)
        cursor.execute(f'UPDATE "{tabel}" AS g SET "{kolom}" = d.primary_key, "{key_kolom}" = NULL, '
                       f'"{op_kolom}" = NULL FROM (SELECT key, MIN(primary_key) AS primary_key FROM "{doel}" '
                       f'WHERE key IS NOT NULL GROUP BY key HAVING COUNT(*) = 1) AS d '
                       f'WHERE g."{kolom}" IS NULL AND g."{key_kolom}" = d.key')
        if cursor.rowcount:
            tellingen[tabel][kolom]['teruggekoppeld'] += cursor.rowcount
            logger.info(f"{cursor.rowcount} rij(en) in {tabel} weer gekoppeld aan een teruggekeerde rij in {doel} "
                        f"(zelfde key als in {key_kolom}).")
        cursor.execute(f'SELECT COUNT(*) FROM "{tabel}" AS g WHERE g."{kolom}" IS NULL AND g."{key_kolom}" IN '
                       f'(SELECT key FROM "{doel}" WHERE key IS NOT NULL GROUP BY key HAVING COUNT(*) > 1)')
        rij = cursor.fetchone()
        dubbel = int(rij[0]) if rij and rij[0] else 0
        tellingen[tabel][kolom]['dubbele_key'] = dubbel
        if dubbel:
            logger.warning(f"{dubbel} losgekoppelde rij(en) in {tabel} niet teruggekoppeld: hun key ({key_kolom}) "
                           f"komt meer dan één keer voor in {doel}.")


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


def werkTabelBij(cursor, col, table, verwijzingen=None, tellingen_verwijzingen=None):
    """Werk één Def_-tabel bij: upsert, verwijderen van verdwenen rijen, geometrie en sequence.

    Moet draaien binnen een transactie waarin de betrokken FK-constraints
    verwijderd zijn (zie loadIncrementeel). Rijen in gebruikerstabellen die naar
    een verdwijnende rij verwijzen worden vóór het verwijderen losgekoppeld
    (koppelVerwijzingenLos) en daarna worden verwijzingen zonder doel opgeruimd
    (ruimVerwijzingenOp), volgens shared/gebruikersdata.VERWIJZINGEN (issue 73).

    Args:
        cursor: psycopg2 cursor
        col: Single_Store_Clean-collectie
        table: Def_-tabel uit LOAD_TABELLEN
        verwijzingen: lijst uit bepaalVerwijzingen (None: geen)
        tellingen_verwijzingen: dict uit bepaalVerwijzingen, wordt bijgewerkt

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
    verwijzingen = verwijzingen or []
    koppelVerwijzingenLos(cursor, table, verdwenen, verwijzingen, tellingen_verwijzingen)
    verwijderd = verwijderRijen(cursor, table, verdwenen)
    ruimVerwijzingenOp(cursor, table, verwijzingen, tellingen_verwijzingen)

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


def herberekenAfgeleideVeldenInSavepoint(cursor):
    """Herbereken de afgeleide velden binnen de upsert-transactie, in een SAVEPOINT (issue 54).

    Een fout in de herberekening draait alleen de herberekening terug: de
    upsert gaat door en de fout wordt een waarschuwing in het run-document. De
    webapplicatie ziet dan tot de volgende run verouderde afgeleide velden;
    de upsert zelf is belangrijker dan die velden. Tot issue 54 draaide een
    fout hier de hele upsert terug.

    Args:
        cursor: psycopg2 cursor binnen de transactie van de upsert

    Returns:
        Tellingen van herberekenAfgeleideVelden, of None bij een fout
    """
    cursor.execute('SAVEPOINT afgeleide_velden_sp')
    try:
        tellingen = herberekenAfgeleideVelden(cursor)
    except Exception as err:
        cursor.execute('ROLLBACK TO SAVEPOINT afgeleide_velden_sp')
        msg = (f"De afgeleide velden (aantal_fotos, aantal_artefacten, dateringen) konden niet herberekend "
               f"worden: {err}. De upsert gaat door; de velden zijn tot de volgende run verouderd.")
        logger.error(msg)
        foutbeleid.meld(foutbeleid.NIVEAU_WAARSCHUWING, foutbeleid.SOORT_AFGELEIDE_VELDEN, msg)
        return None
    cursor.execute('RELEASE SAVEPOINT afgeleide_velden_sp')
    return tellingen


def telDocumenten(col, tabellen):
    """Tel de documenten in Single_Store_Clean van de soorten van de tabellen."""
    return col.count_documents({'soort': {'$in': [t[4:] for t in tabellen]}})


def loadIncrementeel():
    """Taak Load_Upsert: werk de Def_-tabellen bij vanuit Single_Store_Clean (incrementele cyclus).

    Per tabel uit LOAD_TABELLEN (soort = tabelnaam zonder Def_; Def_Bestand is
    soort Bestand):

    1. alle documenten van de soort upserten op primary_key (werkTabelBij);
    2. rijen in gebruikerstabellen loskoppelen die verwijzen naar rijen die
       gaan verdwijnen (koppelVerwijzingenLos, issue 73);
    3. rijen verwijderen waarvan de primary_key niet meer als ID in
       Single_Store_Clean voorkomt (delta_transform.bepaalVerdwenenPrimaryKeys),
       en daarna koppelrijen zonder doel verwijderen (ruimVerwijzingenOp);
    4. de geometrie (location) bijwerken;
    5. de sequence van primary_key op max + 1 zetten.

    Daarna worden losgekoppelde rijen weer gekoppeld aan een teruggekeerde rij
    met dezelfde key (koppelVerwijzingenTerug, issue 73) en worden de afgeleide
    velden van de webapplicatie (aantal_fotos, aantal_artefacten, dateringen)
    voor alle rijen herberekend (herberekenAfgeleideVelden, issue 72).

    Alles gebeurt in één transactie, binnen de FK-mechaniek van loadAll: de
    betrokken FK-constraints worden eerst verwijderd, na het bijwerken
    hersteld met NOT VALID en na de commit gevalideerd. SET CONSTRAINTS ALL
    DEFERRED is geen optie: niet alle FK's zijn deferrable (bijv.
    Def_Bestand.artefactID, Def_Doos.projectID, Def_artefact_abr.artefact_id).
    Verwijzingen vanuit gebruikerstabellen naar verdwenen rijen worden volgens
    shared/gebruikersdata.VERWIJZINGEN losgekoppeld of verwijderd, zodat hun
    constraints valideren; blijft een constraint toch NOT VALID (bijv. door een
    verwijzing tussen Def_-tabellen van de pipeline), dan staat hij in
    tellingen.load.fk_niet_gevalideerd. Kan een constraint niet hersteld worden,
    dan wordt de hele transactie teruggedraaid en faalt de taak (anders zou de
    constraint na de commit definitief ontbreken).

    Vooraf, in een eigen transactie, draait de schemamigratie van de
    gebruikerstabellen (migreerSchemaGebruikersdata). Tabellen met
    gebruikersdata (GEBRUIKERS_TABELLEN) en Def_Bronbestand worden verder niet
    geleegd en niet bijgewerkt. De tellingen per tabel komen in het
    run-document onder tellingen.load, die van de afgeleide velden onder
    tellingen.afgeleide_velden en die van de verwijzingen vanuit
    gebruikerstabellen onder tellingen.gebruikersdata.

    Returns:
        Dict met de tellingen per tabel, plus 'afgeleide_velden' en 'gebruikersdata'
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
        # Schemamigratie van de gebruikerstabellen (issue 73), vóór de rest en in een eigen transactie
        migreerSchemaGebruikersdata(conn, LOCK_TIMEOUT_INCREMENTEEL)

        cursor = conn.cursor()
        cursor.execute(f"SET lock_timeout = '{LOCK_TIMEOUT_INCREMENTEEL}'")
        fk_constraints = getBetrokkenFkConstraints(leesFkConstraints(cursor), tabellen)
        logger.info(f"Gevonden: {len(fk_constraints)} betrokken FK constraints om tijdelijk te verwijderen")
        verwijderFkConstraints(cursor, fk_constraints)
        verwijzingen, gebruikers = bepaalVerwijzingen(cursor, tabellen)

        tellingen = {}
        for table in tabellen:
            telling = werkTabelBij(cursor, col, table, verwijzingen, gebruikers)
            if telling is not None:
                tellingen[table] = telling

        # Losgekoppelde gebruikersdata weer koppelen aan teruggekeerde rijen (issue 73), na alle tabellen
        koppelVerwijzingenTerug(cursor, verwijzingen, gebruikers)
        logger.info(f"Verwijzingen vanuit gebruikerstabellen bijgewerkt: {gebruikers}")

        # Afgeleide velden (issue 72) in dezelfde transactie, zodat de webapplicatie ze nooit
        # verouderd ziet, en vóór het herstel van de FK's: na een ADD CONSTRAINT ... NOT VALID
        # controleert PostgreSQL bij een UPDATE van een rij die deze transactie heeft ingevoegd
        # alle FK's van die rij opnieuw, ook als de verwijzende kolommen niet veranderen.
        afgeleid = herberekenAfgeleideVeldenInSavepoint(cursor)

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
        if niet_gevalideerd:
            foutbeleid.meld(foutbeleid.NIVEAU_WAARSCHUWING, foutbeleid.SOORT_FK_NIET_GEVALIDEERD,
                            f"{len(niet_gevalideerd)} FK-constraint(s) konden niet gevalideerd worden en blijven NOT VALID "
                            f"(verwijzingen naar verdwenen rijen tussen Def_-tabellen): {niet_gevalideerd}.",
                            aantal=len(niet_gevalideerd), details=niet_gevalideerd)
        run = verwerkingsrun.huidigeRun(verplicht=False)
        if run is not None:
            velden = {'tellingen.load': resultaat, 'tellingen.gebruikersdata': gebruikers}
            if afgeleid is not None:
                velden['tellingen.afgeleide_velden'] = afgeleid
            verwerkingsrun.werkRunBij(velden, run_id=run['run_id'])
        logger.info(f"Incrementele load afgerond: {totaal}; niet gevalideerde FK's: {niet_gevalideerd}.")
        return dict(resultaat, afgeleide_velden=afgeleid, gebruikersdata=gebruikers)

    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        raise
    finally:
        conn.close()
