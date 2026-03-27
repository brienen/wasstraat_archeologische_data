#!/usr/bin/env python3
"""
Debug script: test pandas to_sql() met SQLAlchemy in de Airflow container.
Draai in de container: docker exec wasstraat_airflow python /opt/airflow/dags/tests/debug_to_sql.py
Of lokaal (als postgres bereikbaar is): python tests/debug_to_sql.py
"""
import sys

# Stap 1: Check versies
print("=== VERSIES ===")
import pandas as pd
print(f"pandas: {pd.__version__}")

import sqlalchemy
print(f"sqlalchemy: {sqlalchemy.__version__}")

# Check of pandas sqlalchemy kan vinden via import_optional_dependency
try:
    from pandas.compat._optional import import_optional_dependency
    sa = import_optional_dependency("sqlalchemy", errors="raise")
    print(f"pandas vindt sqlalchemy: {sa.__version__}")
except Exception as e:
    print(f"pandas KAN sqlalchemy NIET vinden: {e}")

# Stap 2: Maak een simpel DataFrame
import numpy as np
df = pd.DataFrame({
    'key': ['a', 'b', 'c'],
    'value': [1, 2, 3],
    'label': ['alpha', 'beta', 'gamma']
})
print(f"\n=== TEST DataFrame ===\n{df}")

# Stap 3: Connectie naar postgres
DB_URI = "postgresql://flask:466eWsLYlfKP675wegDEnYjP@localhost:5432/flask"
# Binnen container:
# DB_URI = "postgresql://flask:466eWsLYlfKP675wegDEnYjP@postgres/flask"

print(f"\n=== CONNECTIE TEST ===")
print(f"URI: {DB_URI}")

engine = sqlalchemy.create_engine(DB_URI)
print(f"Engine type: {type(engine)}")
print(f"Is Connectable: {isinstance(engine, sqlalchemy.engine.Connectable)}")

# Test 1: to_sql met engine (zou moeten werken)
print("\n--- Test 1: to_sql met engine ---")
try:
    df.to_sql('_test_pandas', con=engine, if_exists='replace', index=False)
    print("OK: to_sql met engine werkt!")
except Exception as e:
    print(f"FOUT: {e}")

# Test 2: to_sql met connection uit engine.connect()
print("\n--- Test 2: to_sql met connection ---")
try:
    with engine.connect() as conn:
        print(f"Connection type: {type(conn)}")
        print(f"Is Connectable: {isinstance(conn, sqlalchemy.engine.Connectable)}")
        df.to_sql('_test_pandas2', con=conn, if_exists='replace', index=False)
        print("OK: to_sql met connection werkt!")
except Exception as e:
    print(f"FOUT: {e}")

# Test 3: to_sql met URI string
print("\n--- Test 3: to_sql met URI string ---")
try:
    df.to_sql('_test_pandas3', con=DB_URI, if_exists='replace', index=False)
    print("OK: to_sql met URI string werkt!")
except Exception as e:
    print(f"FOUT: {e}")

# Test 4: to_sql met dtype dict (SQLAlchemy types)
print("\n--- Test 4: to_sql met dtype dict ---")
try:
    from sqlalchemy import TEXT, INTEGER
    dtype = {'key': TEXT(), 'value': INTEGER(), 'label': TEXT()}
    df.to_sql('_test_pandas4', con=engine, if_exists='replace', index=False, dtype=dtype)
    print("OK: to_sql met dtype dict werkt!")
except Exception as e:
    print(f"FOUT: {e}")

# Opruimen
print("\n=== OPRUIMEN ===")
try:
    with engine.connect() as conn:
        for t in ['_test_pandas', '_test_pandas2', '_test_pandas3', '_test_pandas4']:
            conn.execute(f'DROP TABLE IF EXISTS "{t}"')
        # Commit in SQLAlchemy 1.4 autocommit mode
        try:
            conn.commit()
        except:
            pass
    print("Test tabellen opgeruimd.")
except Exception as e:
    print(f"Opruimen mislukt (niet erg): {e}")

print("\n=== KLAAR ===")
