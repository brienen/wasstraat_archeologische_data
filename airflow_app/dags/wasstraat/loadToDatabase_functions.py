"""Laden van data uit MongoDB naar PostgreSQL.

Gebruikt pymongo voor extractie en psycopg2 voor laden.
Geen pandas of SQLAlchemy afhankelijkheden.
"""
import pymongo
import psycopg2
import psycopg2.extras
from urllib.parse import urlparse, unquote
from datetime import datetime, date

import wasstraat.meta as meta
import wasstraat.archutils as ut
import shared.config as config
import shared.const as const
import logging

logger = logging.getLogger("airflow.task")


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

        # 2. Haal MongoDB documenten op
        col = getAnalyseCleanCollection()
        fields = getFields(col, soort)
        projection = {f: 1 for f in fields}
        projection['_id'] = 1
        documents = list(col.find({'soort': soort}, projection=projection))

        if not documents:
            logger.info(f"Geen documenten gevonden voor soort: {soort}")
            return

        # 3. Bepaal veldnamen uit alle documenten (na rename ID -> primary_key)
        all_doc_keys = set()
        for doc in documents:
            keys = set(doc.keys())
            if 'ID' in keys:
                keys.discard('ID')
                keys.add('primary_key')
            all_doc_keys.update(keys)

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
# Hoofdfunctie: 3-fase atomic swap
# ============================================================

def loadAll():
    """Laad alle data uit MongoDB naar PostgreSQL via een 3-fase atomic swap.

    Fase 1: Laad data in tijdelijke {tabel}_new tabellen
    Fase 2a: Atomic rename swap (drop FK → rename → truncate extra)
    Fase 2b: Herstel FK constraints met NOT VALID + SAVEPOINTs
    Fase 3: Opruimen _old tabellen en valideer FK constraints
    """
    logger.info("Starting Loading data to relational database...")

    conn = getPgConnection()
    logger.info(f"Connecting to {config.SQLALCHEMY_DATABASE_URI}")

    lst_tables = [
        'Def_ABR', 'Def_Project', 'Def_Put', 'Def_Vondst', 'Def_Spoor',
        'Def_Stelling', 'Def_Doos', 'Def_Standplaats', 'Def_Plaatsing',
        'Def_Vlak', 'Def_Vindplaats', 'Def_Artefact', 'Def_Bestand',
        'Def_Vulling', 'Def_Monster', 'Def_Monster_Botanie',
        'Def_Monster_Schelp', 'Def_DT_Soort_Plant', 'Def_DT_Soort_Schelp',
        'Def_DT_Soort_Deel', 'Def_DT_Soort_Staat',
    ]

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
        fk_constraints = []

        logger.info("FASE 2a: Atomic swap van tabellen...")

        # Stel een lock-timeout in: wacht maximaal 5 seconden op locks.
        cursor.execute("SET lock_timeout = '5s'")

        # Bewaar FK-constraint definities zodat we ze na de swap
        # kunnen herstellen. Filter op Def_-tabellen.
        cursor.execute("""
            SELECT tc.table_name, tc.constraint_name,
                   pg_get_constraintdef(pgc.oid) AS constraint_def
            FROM information_schema.table_constraints tc
            JOIN pg_constraint pgc ON pgc.conname = tc.constraint_name
            WHERE tc.constraint_type = 'FOREIGN KEY'
              AND tc.table_schema = 'public'
              AND tc.table_name LIKE 'Def\\_%%' ESCAPE '\\'
        """)
        for row in cursor.fetchall():
            fk_constraints.append({
                'table': row[0],
                'name': row[1],
                'definition': row[2],
            })
        logger.info(f"Gevonden: {len(fk_constraints)} FK constraints om tijdelijk te verwijderen")

        # Drop FK constraints (snel: alleen metadata-operaties)
        for fk in fk_constraints:
            cursor.execute(
                f'ALTER TABLE "{fk["table"]}" DROP CONSTRAINT IF EXISTS "{fk["name"]}"'
            )

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
                logger.warning(
                    f"Kon FK constraint {fk['name']} niet herstellen op "
                    f"{fk['table']}: {fk_err}. Definitie was: {fk['definition']}"
                )

        conn.commit()
        logger.info(f"FK constraints hersteld: {fk_restored} OK, {fk_failed} mislukt.")

        # ============================================================
        # FASE 3: Opruimen (buiten de swap-transactie)
        # ============================================================
        logger.info("FASE 3: Opruimen oude tabellen en validatie...")
        for orig, temp in temp_tables_created:
            old_table = f"{orig}_old"
            cursor.execute(f'DROP TABLE IF EXISTS "{old_table}" CASCADE')

        # Valideer de FK constraints alsnog
        for fk in fk_constraints:
            try:
                cursor.execute('SAVEPOINT fk_validate_sp')
                cursor.execute(
                    f'ALTER TABLE "{fk["table"]}" VALIDATE CONSTRAINT "{fk["name"]}"'
                )
                cursor.execute('RELEASE SAVEPOINT fk_validate_sp')
            except Exception:
                cursor.execute('ROLLBACK TO SAVEPOINT fk_validate_sp')

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
