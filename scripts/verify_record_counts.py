"""
Vergelijk record-aantallen tussen MongoDB (analyse_clean) en PostgreSQL.

Draait in de Airflow-container waar de environment variables beschikbaar zijn:
    docker exec -it <airflow-container> python /opt/airflow/scripts/verify_record_counts.py

Of vanuit de host met de juiste .env geladen.
"""

import os
import sys

# Voeg het dags-pad toe zodat shared.config importeerbaar is
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'airflow_app', 'dags'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import pymongo
import sqlalchemy
from sqlalchemy import create_engine, text

import shared.config as config


def get_mongo_counts():
    """Tel per soort hoeveel documenten er in de analyse_clean collection staan."""
    client = pymongo.MongoClient(str(config.MONGO_URI))
    db = client[str(config.DB_ANALYSE)]
    collection = db[config.COLL_ANALYSE_CLEAN]

    pipeline = [
        {"$group": {"_id": "$soort", "count": {"$sum": 1}}},
        {"$sort": {"_id": 1}}
    ]
    results = {}
    for doc in collection.aggregate(pipeline):
        results[doc["_id"]] = doc["count"]

    client.close()
    return results


def get_postgres_counts(engine):
    """Tel per Def_-tabel hoeveel rijen er in PostgreSQL staan."""
    results = {}
    with engine.connect() as conn:
        # Haal alle Def_-tabellen op uit information_schema
        rows = conn.execute(text(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'public' AND table_name LIKE 'Def\\_%' ESCAPE '\\'"
        ))
        for (table_name,) in rows:
            try:
                count = conn.execute(text(f'SELECT COUNT(*) FROM "{table_name}"')).scalar()
                results[table_name] = count
            except Exception as e:
                results[table_name] = f"FOUT: {e}"
    return results


def main():
    # De tabellen die loadAll() laadt, en hun soort-mapping
    lst_tables = [
        'Def_ABR', 'Def_Project', 'Def_Put', 'Def_Vondst', 'Def_Spoor',
        'Def_Stelling', 'Def_Doos', 'Def_Standplaats', 'Def_Plaatsing',
        'Def_Vlak', 'Def_Vindplaats', 'Def_Artefact', 'Def_Bestand',
        'Def_Vulling', 'Def_Monster', 'Def_Monster_Botanie',
        'Def_Monster_Schelp', 'Def_DT_Soort_Plant', 'Def_DT_Soort_Schelp',
        'Def_DT_Soort_Deel', 'Def_DT_Soort_Staat'
    ]

    print("=" * 72)
    print("  VERGELIJKING RECORD-AANTALLEN: MongoDB vs PostgreSQL")
    print("=" * 72)

    # --- MongoDB ---
    print("\nMongoDB analyse_clean collection ophalen...")
    mongo_counts = get_mongo_counts()

    # --- PostgreSQL ---
    print("PostgreSQL tabellen ophalen...")
    engine = create_engine(config.SQLALCHEMY_DATABASE_URI)
    pg_counts = get_postgres_counts(engine)
    engine.dispose()

    # --- Vergelijking ---
    print(f"\n{'Soort':<25} {'MongoDB':>10} {'PG Tabel':<25} {'PostgreSQL':>10} {'Verschil':>10}")
    print("-" * 82)

    totaal_mongo = 0
    totaal_pg = 0
    waarschuwingen = []

    for table in lst_tables:
        soort = table[4:]  # Def_Project -> Project
        m_count = mongo_counts.get(soort, 0)
        p_count = pg_counts.get(table, 0)

        if isinstance(p_count, str):  # Foutmelding
            verschil_str = p_count
        else:
            verschil = p_count - m_count
            verschil_str = f"{verschil:+d}" if verschil != 0 else "OK"
            totaal_mongo += m_count
            totaal_pg += p_count

            if verschil != 0:
                waarschuwingen.append((soort, table, m_count, p_count, verschil))

        print(f"{soort:<25} {m_count:>10,} {table:<25} {str(p_count):>10} {verschil_str:>10}")

    print("-" * 82)
    print(f"{'TOTAAL':<25} {totaal_mongo:>10,} {'':<25} {totaal_pg:>10,} {totaal_pg - totaal_mongo:>+10,}")

    # --- Soorten in MongoDB die NIET in lst_tables zitten ---
    bekende_soorten = {t[4:] for t in lst_tables}
    onbekend = {s: c for s, c in mongo_counts.items() if s not in bekende_soorten}
    if onbekend:
        print(f"\n{'NIET-GELADEN soorten in MongoDB':}")
        print(f"{'Soort':<25} {'Aantal':>10}")
        print("-" * 36)
        for soort, count in sorted(onbekend.items(), key=lambda x: -x[1]):
            print(f"{soort:<25} {count:>10,}")

    # --- Extra PG tabellen die niet in lst_tables zitten ---
    bekende_tabellen = set(lst_tables)
    extra_pg = {t: c for t, c in pg_counts.items() if t not in bekende_tabellen}
    if extra_pg:
        print(f"\n{'EXTRA PostgreSQL tabellen (niet in lst_tables)':}")
        print(f"{'Tabel':<35} {'Aantal':>10}")
        print("-" * 46)
        for table, count in sorted(extra_pg.items()):
            print(f"{table:<35} {str(count):>10}")

    # --- Samenvatting ---
    if waarschuwingen:
        print(f"\n⚠  {len(waarschuwingen)} tabel(len) met afwijkende aantallen:")
        for soort, table, m, p, diff in waarschuwingen:
            richting = "MEER in PG" if diff > 0 else "MINDER in PG"
            print(f"   {soort}: MongoDB={m:,}, PostgreSQL={p:,} ({richting}: {abs(diff):,})")
    else:
        print("\n✓  Alle aantallen komen overeen.")

    print()


if __name__ == "__main__":
    main()
