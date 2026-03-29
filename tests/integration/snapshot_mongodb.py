#!/usr/bin/env python3
"""
MongoDB snapshot tool voor regressietests.

Gebruik:
    python snapshot_mongodb.py save baseline.json    # Sla huidige staat op
    python snapshot_mongodb.py compare baseline.json  # Vergelijk met huidige staat
"""
import json
import sys
import os
import pymongo

MONGO_URI = os.getenv("MONGO_URI", "mongodb://testroot:testpass@localhost:27117/?authSource=admin")
DB_STAGING = os.getenv("DB_STAGING", "Arch_Staging_Test")
DB_ANALYSE = os.getenv("DB_ANALYSE", "Arch_Analyse_Test")
DB_FILES = os.getenv("DB_FILES", "Arch_Files_Test")

DATABASES = [DB_STAGING, DB_ANALYSE, DB_FILES]


def getSnapshot():
    """Maak een snapshot van alle collecties: counts + steekproef van 5 documenten per collectie."""
    client = pymongo.MongoClient(MONGO_URI)
    snapshot = {}
    for db_name in DATABASES:
        db = client[db_name]
        db_snap = {}
        for coll_name in sorted(db.list_collection_names()):
            if coll_name.startswith("system."):
                continue
            coll = db[coll_name]
            count = coll.count_documents({})
            # Steekproef: eerste 5 documenten, gesorteerd op _id voor reproduceerbaarheid
            sample = []
            for doc in coll.find().sort("_id", 1).limit(5):
                doc["_id"] = str(doc["_id"])
                sample.append(doc)
            db_snap[coll_name] = {"count": count, "sample_size": len(sample)}
        snapshot[db_name] = db_snap
    client.close()
    return snapshot


def save(filepath):
    """Sla snapshot op als JSON."""
    snapshot = getSnapshot()
    with open(filepath, "w") as f:
        json.dump(snapshot, f, indent=2, default=str)
    total = sum(v["count"] for db in snapshot.values() for v in db.values())
    print(f"Snapshot opgeslagen: {filepath}")
    print(f"  Databases: {len(snapshot)}")
    for db_name, colls in snapshot.items():
        coll_total = sum(v["count"] for v in colls.values())
        print(f"  {db_name}: {len(colls)} collecties, {coll_total} documenten")
    print(f"  Totaal: {total} documenten")


def compare(filepath):
    """Vergelijk huidige staat met een opgeslagen snapshot."""
    with open(filepath) as f:
        baseline = json.load(f)
    current = getSnapshot()

    ok = True
    for db_name in set(list(baseline.keys()) + list(current.keys())):
        base_db = baseline.get(db_name, {})
        curr_db = current.get(db_name, {})

        all_colls = sorted(set(list(base_db.keys()) + list(curr_db.keys())))
        for coll_name in all_colls:
            base = base_db.get(coll_name, {})
            curr = curr_db.get(coll_name, {})
            base_count = base.get("count", 0)
            curr_count = curr.get("count", 0)

            if coll_name not in base_db:
                print(f"  NIEUW   {db_name}.{coll_name}: {curr_count} docs")
                ok = False
            elif coll_name not in curr_db:
                print(f"  WEG     {db_name}.{coll_name}: was {base_count} docs")
                ok = False
            elif base_count != curr_count:
                diff = curr_count - base_count
                sign = "+" if diff > 0 else ""
                print(f"  VERSCHIL {db_name}.{coll_name}: {base_count} → {curr_count} ({sign}{diff})")
                ok = False
            else:
                print(f"  OK      {db_name}.{coll_name}: {curr_count} docs")

    if ok:
        print("\n✓ Alle collecties identiek aan baseline")
    else:
        print("\n✗ Afwijkingen gevonden — controleer bovenstaande regels")
    return ok


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)

    action = sys.argv[1]
    filepath = sys.argv[2]

    if action == "save":
        save(filepath)
    elif action == "compare":
        ok = compare(filepath)
        sys.exit(0 if ok else 1)
    else:
        print(f"Onbekende actie: {action}")
        sys.exit(1)
