import sqlalchemy as db
import pymongo
import pandas as pd
import numpy as np
import sqlalchemy
import wasstraat.meta as meta
import wasstraat.archutils as ut


from sqlalchemy.orm import sessionmaker
from sqlalchemy import create_engine, inspect
from sqlalchemy.engine import reflection
from geoalchemy2 import Geometry, WKTElement
from shapely.geometry import Point
from sqlalchemy.sql import null as sqlnull
from operator import itemgetter 

import shared.config as config
import shared.const as const
import shared.database as database
import logging
logger = logging.getLogger("airflow.task")




def getAnalyseCleanCollection():   
    myclient = pymongo.MongoClient(str(config.MONGO_URI))
    analyseDb = myclient[str(config.DB_ANALYSE)]
    return analyseDb[config.COLL_ANALYSE_CLEAN]


# Set coordinates to WKT to be able to transfer them to the database 
def setWKT(x,y):  
    # Check for empty coordinates so not to get errors
    if x is np.nan or y is np.nan or not(x>1):
        return None
    try:
        point = Point(x,y)
        return WKTElement(point.wkt, srid=4326)
    except:
        return None

def getFields(col, soort):
    lst_fields = meta.getVeldnamen(soort)
    logger.info(f'lstfields {lst_fields}')
    set_fields = set(lst_fields)

    df = pd.DataFrame(list(col.find({'soort': soort})))
    set_fields.update(df.columns)
    result = list(set_fields)
    result.sort()
    return result



def transferToDB(objecttype, soort, table, connection):
    try:
        insp = inspect(connection)
        db_columns = insp.get_columns(table)

        col = getAnalyseCleanCollection()
        lst_fields = getFields(col, soort)

        df = pd.DataFrame(list(col.find({'soort': soort}, projection=lst_fields)), columns=lst_fields)
        df_load = df.rename(columns={'ID':'primary_key'})
        if '_id' in df_load.columns:
            df_load['_id'] = df_load['_id'].astype(str)
        if 'imageID' in df_load.columns:
            df_load['imageID'] = df_load['imageID'].astype(str)
        if 'herkomst' in df_load.columns:
            df_load['herkomst'] = df_load['herkomst'].astype(str)
        if 'brondata' in df_load.columns:
            df_load['brondata'] = df_load['brondata'].astype(str)
        if 'latitude' in df_load.columns and 'longitude' in df_load.columns:
            df_load['location'] = df_load.apply(lambda x: setWKT(x['longitude'], x['latitude']),axis=1)

        
        df_columnnames = df_load.columns
        db_columnnames = list(map(itemgetter('name'), db_columns))
        lst_intersect_columnnames = list((x) for x in db_columnnames if x in df_columnnames)
        
        # Get list of columnsnames that are not in intersection
        df_columnnames_nomatch = list(set(df_columnnames) - set(lst_intersect_columnnames))
        if len(df_columnnames_nomatch) > 0:
            logger.warning("Bij het laden van data van " + soort + ' naar tabel ' + table + ' werd volgende data aangeboden die de tabel niet ondersteunt: ' + str(df_columnnames_nomatch))
        db_columnnames_nomatch = list(set(db_columnnames) - set(lst_intersect_columnnames))
        if len(df_columnnames_nomatch) > 0:
            logger.warning("Bij het laden van data van " + soort + ' naar tabel ' + table + ' verwachtte de tabel de volgende data die niet werd aangeboden: ' + str(db_columnnames_nomatch))
        
        lst = list(map(itemgetter('name', 'type'), db_columns))
        # Pandas 2.x vereist SQLAlchemy type instances in dtype dict.
        # Geometry kolommen worden uitgesloten: die worden door GeoAlchemy2 afgehandeld.
        dict_intersect_columns = {}
        for name, col_type in lst:
            if name in df_columnnames:
                dict_intersect_columns[name] = col_type
        df_load = df_load[lst_intersect_columnnames]

        # Bepaal welke kolommen een ENUM type hebben via PostgreSQL
        # information_schema. SQLAlchemy reflecteert custom enum types
        # als de typenaam (bijv. 'discrartefactsoortenum'), niet als 'ENUM',
        # dus str()-detectie is onbetrouwbaar. De originele tabel wordt
        # bevraagd (zonder _new suffix) omdat _new via LIKE is aangemaakt.
        base_table = table.replace('_new', '') if table.endswith('_new') else table
        enum_cols_result = connection.execute(
            f"""SELECT c.column_name
                FROM information_schema.columns c
                JOIN pg_type t ON t.typname = c.udt_name
                WHERE c.table_name = '{base_table}'
                  AND c.table_schema = 'public'
                  AND c.data_type = 'USER-DEFINED'
                  AND t.typtype = 'e'"""
        )
        enum_columns = set(row[0] for row in enum_cols_result)
        if enum_columns:
            logger.info(f"ENUM kolommen gevonden voor {base_table}: {enum_columns}")

        # Truncate columns that are too long and set numeric values if required
        for column in df_load.columns:
            lst_columns = [col for col in db_columns if col['name'] == column]
            if len(lst_columns) > 0:
                column_def = lst_columns[0]
            else:
                continue
            if 'VARCHAR' in str(column_def['type']) and column_def['type'].length:
                df_load[column] = df_load[column].apply(lambda x: str(x)[0:column_def['type'].length] if x and str(x) != 'nan' else "")
            if 'INTEGER' in str(column_def['type']):
                df_load[column] = df_load[column].apply(lambda x: pd.to_numeric(x, errors='coerce', downcast='integer'))
            if 'DOUBLE' in str(column_def['type']):
                df_load[column] = df_load[column].apply(lambda x: pd.to_numeric(x, errors='coerce', downcast='float'))
            if 'BOOL' in str(column_def['type']):
                df_load[column] = df_load[column].apply(lambda x: ut.convertToBool(x))
            if 'DATE' in str(column_def['type']):
                df_load[column] = df_load[column].apply(lambda x: ut.convertToDate(x, True))
            # ENUM kolommen: lege strings zijn niet toegestaan in PostgreSQL enums.
            # Converteer lege strings naar de standaardwaarde 'Onbekend'.
            if column in enum_columns:
                df_load[column] = df_load[column].apply(
                    lambda x: const.ARTF_ONBEKEND if (x is None or str(x).strip() == '' or str(x) == 'nan') else x
                )

        # df_load.fillna(sqlnull(), inplace=True) #@ Returns Error
        logger.info(f"Transfering: {soort} with {len(df_load)} records")
        df_load.to_sql(table, con=connection, if_exists='append', index=False, dtype=dict_intersect_columns)

    except Exception as err:
        msg = "Onbekende fout bij laden van soort: "+soort+" in tabel "+table+" van database met melding: " + str(err)
        logger.error(msg)
        raise Exception(msg) from err




def loadAll():
    logger.info("Starting Loading data to relational database...")

    engine = create_engine(config.SQLALCHEMY_DATABASE_URI)
    logger.info("Connecting to " + config.SQLALCHEMY_DATABASE_URI)

    lst_tables = ['Def_ABR', 'Def_Project', 'Def_Put', 'Def_Vondst', 'Def_Spoor', 'Def_Stelling', 'Def_Doos', 'Def_Standplaats', 'Def_Plaatsing', 'Def_Vlak', 'Def_Vindplaats', 'Def_Artefact', 'Def_Bestand', 'Def_Vulling', 'Def_Monster', 'Def_Monster_Botanie', 'Def_Monster_Schelp', 'Def_DT_Soort_Plant', 'Def_DT_Soort_Schelp', 'Def_DT_Soort_Deel', 'Def_DT_Soort_Staat']

    # Extra tabellen die ook getruncated worden (niet in de hoofdlijst)
    extra_truncate_tables = ['Def_artefact_abr', 'Def_Bruikleen', 'Def_artefact_conservering', 'Def_Conserveringsproject']

    with engine.connect() as connection:
        # ============================================================
        # PRE-CLEANUP: Ruim restanten op van een eerder afgebroken run.
        # Dit voorkomt "duplicate key in pg_type" fouten als _new of _old
        # tabellen zijn achtergebleven na een crash of timeout.
        # ============================================================
        with connection.begin():
            logger.info("Pre-cleanup: verwijder eventuele restanten van vorige run...")
            for table in lst_tables:
                for suffix in ('_new', '_old'):
                    leftover = f"{table}{suffix}"
                    connection.execute(f'DROP TABLE IF EXISTS "{leftover}" CASCADE')
            logger.info("Pre-cleanup afgerond.")

        # ============================================================
        # FASE 1: Laden naar tijdelijke tabellen (buiten de swap-transactie)
        # Dit kan lang duren, maar blokkeert niets.
        # ============================================================
        with connection.begin():
            logger.info("FASE 1: Laden naar tijdelijke tabellen...")
            logger.info("Loading all data for " + str(lst_tables))

            temp_tables_created = []

            try:
                for table in lst_tables:
                    if table.startswith('Def_'):
                        soort = table[4:]  # Remove Def_
                        temp_table = f"{table}_new"

                        # CASCADE verwijdert ook orphan pg_type entries
                        connection.execute(f'DROP TABLE IF EXISTS "{temp_table}" CASCADE')
                        # EXCLUDING CONSTRAINTS: voorkomt dat FK-refs naar oude
                        # tabellen worden gekopieerd. Indexes WEL kopiëren.
                        connection.execute(
                            f'CREATE TABLE "{temp_table}" (LIKE "{table}" INCLUDING INDEXES INCLUDING DEFAULTS)'
                        )
                        temp_tables_created.append((table, temp_table))

                        transferToDB(table, soort, temp_table, connection)
                        logger.info(f"Geladen: {soort} -> {temp_table}")

            except Exception as err:
                logger.error(f"Laden naar temp-tabellen mislukt: {err}. Opruimen...")
                for orig, temp in temp_tables_created:
                    try:
                        connection.execute(f'DROP TABLE IF EXISTS "{temp}" CASCADE')
                    except Exception:
                        pass
                raise

        # ============================================================
        # FASE 2: Snelle swap in een aparte, korte transactie.
        # FK constraints worden hier gedropt en de tabellen hernoemd.
        # FK-restore gebeurt in een APARTE transactie (Fase 2b) zodat
        # een falende constraint niet de hele swap vergiftigt.
        # ============================================================
        fk_constraints = []

        with connection.begin():
            logger.info("FASE 2a: Atomic swap van tabellen...")

            # Stel een lock-timeout in: wacht maximaal 5 seconden op locks.
            connection.execute("SET lock_timeout = '5s'")

            # Bewaar FK-constraint definities zodat we ze na de swap kunnen herstellen.
            # Filter op Def_-tabellen: systeemtabellen (ab_user, ab_role etc.)
            # mogen niet aangeraakt worden — die zijn in gebruik door de webapplicatie.
            fk_query = """
                SELECT tc.table_name, tc.constraint_name,
                       pg_get_constraintdef(pgc.oid) AS constraint_def
                FROM information_schema.table_constraints tc
                JOIN pg_constraint pgc ON pgc.conname = tc.constraint_name
                WHERE tc.constraint_type = 'FOREIGN KEY'
                  AND tc.table_schema = 'public'
                  AND tc.table_name LIKE 'Def\\_%%' ESCAPE '\\'
            """
            result = connection.execute(fk_query)
            for row in result:
                fk_constraints.append({
                    'table': row[0],
                    'name': row[1],
                    'definition': row[2]
                })
            logger.info(f"Gevonden: {len(fk_constraints)} FK constraints om tijdelijk te verwijderen")

            # Drop FK constraints (snel: alleen metadata-operaties)
            for fk in fk_constraints:
                connection.execute(
                    f'ALTER TABLE "{fk["table"]}" DROP CONSTRAINT IF EXISTS "{fk["name"]}"'
                )

            # Rename is instant (PostgreSQL past alleen de systeemcatalogus aan)
            for orig, temp in temp_tables_created:
                old_table = f"{orig}_old"
                connection.execute(f'DROP TABLE IF EXISTS "{old_table}" CASCADE')
                connection.execute(f'ALTER TABLE "{orig}" RENAME TO "{old_table}"')
                connection.execute(f'ALTER TABLE "{temp}" RENAME TO "{orig}"')

            # Truncate de extra tabellen (CASCADE voorkomt FK-conflicten
            # met tabellen die niet in de hoofdlijst staan, zoals Def_Partij)
            f = lambda x: '"' + str(x) + '"'
            lst_extra = list(map(f, extra_truncate_tables))
            connection.execute('TRUNCATE ' + ','.join(lst_extra) + ' CASCADE;')

            logger.info("Swap voltooid.")

        # ============================================================
        # FASE 2b: Herstel FK constraints in een aparte transactie.
        # Gebruik een SAVEPOINT per constraint zodat één fout niet
        # alle overige constraints blokkeert (poisoned transaction).
        # ============================================================
        with connection.begin():
            logger.info("FASE 2b: Herstel FK constraints met NOT VALID...")
            fk_restored = 0
            fk_failed = 0

            for fk in fk_constraints:
                try:
                    # SAVEPOINT zodat een falende ADD CONSTRAINT niet
                    # de hele transactie vergiftigt
                    connection.execute('SAVEPOINT fk_restore_sp')
                    connection.execute(
                        f'ALTER TABLE "{fk["table"]}" ADD CONSTRAINT "{fk["name"]}" {fk["definition"]} NOT VALID'
                    )
                    connection.execute('RELEASE SAVEPOINT fk_restore_sp')
                    fk_restored += 1
                except Exception as fk_err:
                    connection.execute('ROLLBACK TO SAVEPOINT fk_restore_sp')
                    fk_failed += 1
                    logger.warning(
                        f"Kon FK constraint {fk['name']} niet herstellen op {fk['table']}: {fk_err}. "
                        f"Definitie was: {fk['definition']}"
                    )

            logger.info(f"FK constraints hersteld: {fk_restored} OK, {fk_failed} mislukt.")

        # ============================================================
        # FASE 3: Opruimen (buiten de swap-transactie)
        # ============================================================
        with connection.begin():
            logger.info("FASE 3: Opruimen oude tabellen en validatie...")
            for orig, temp in temp_tables_created:
                old_table = f"{orig}_old"
                connection.execute(f'DROP TABLE IF EXISTS "{old_table}" CASCADE')

            # Valideer de FK constraints alsnog. Gebruik ook hier een
            # SAVEPOINT per constraint voor robuustheid.
            for fk in fk_constraints:
                try:
                    connection.execute('SAVEPOINT fk_validate_sp')
                    connection.execute(
                        f'ALTER TABLE "{fk["table"]}" VALIDATE CONSTRAINT "{fk["name"]}"'
                    )
                    connection.execute('RELEASE SAVEPOINT fk_validate_sp')
                except Exception:
                    connection.execute('ROLLBACK TO SAVEPOINT fk_validate_sp')

            logger.info("Laden naar database succesvol afgerond.")