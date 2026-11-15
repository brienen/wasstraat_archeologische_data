#!/usr/bin/env python3
"""
MongoDB snapshot tool voor regressietests.

Gebruik:
    python snapshot_mongodb.py save baseline.json    # Sla huidige staat op
    python snapshot_mongodb.py compare baseline.json  # Vergelijk met huidige staat

Referentie-uitkomst van de Delftse testdata (tests/integration/fixtures/delft_golden_snapshot.json,
gelezen door tests/integration/test_delft_referentie.py), na ``make integration-delft-pipeline``
of met de Delftse testomgeving nog actief:
    python tests/integration/snapshot_mongodb.py vergelijk-referentie tests/integration/fixtures/delft_golden_snapshot.json
    python tests/integration/snapshot_mongodb.py referentie tests/integration/fixtures/delft_golden_snapshot.json "<verklaring>"

``referentie`` schrijft de aantallen per soort in Single_Store en Single_Store_Clean, de
artefactsoorten en de voorbeeldsleutels; de verklaring komt in het veld ``beschrijving``
(zonder verklaring blijft de bestaande beschrijving staan). ``referentie`` en
``vergelijk-referentie`` lezen de MongoDB van de Delftse testomgeving (hostpoort 27118,
MONGO_TEST_URI_DELFT); ``save`` en ``compare`` die van MONGO_URI (standaard de synthetische, 27117).
"""
import json
import sys
import os
import pymongo

MONGO_URI = os.getenv("MONGO_URI", "mongodb://testroot:testpass@localhost:27117/?authSource=admin")
# MongoDB van de Delftse testomgeving (docker-compose.delft-test.yml, hostpoort 27118)
MONGO_URI_DELFT = os.getenv("MONGO_TEST_URI_DELFT", "mongodb://testroot:testpass@localhost:27118/?authSource=admin")
DB_STAGING = os.getenv("DB_STAGING", "Arch_Staging_Test")
DB_ANALYSE = os.getenv("DB_ANALYSE", "Arch_Analyse_Test")
DB_FILES = os.getenv("DB_FILES", "Arch_Files_Test")

DATABASES = [DB_STAGING, DB_ANALYSE, DB_FILES]

# Referentie-uitkomst: soorten met voorbeeldsleutels en het aantal voorbeelden per soort
REFERENTIE_SLEUTELSOORTEN = ["Project", "Put", "Vlak", "Spoor", "Vondst", "Monster", "Doos", "Standplaats", "Bestand"]
AANTAL_VOORBEELDSLEUTELS = 5
# Secties van de referentie-uitkomst met hun omschrijving in meldingen
REFERENTIE_TELLINGEN = {
    "soort_counts_store": "Single_Store, soort",
    "soort_counts_clean": "Single_Store_Clean, soort",
    "artefact_subtypes": "Single_Store_Clean, artefactsoort",
}
REFERENTIE_SECTIES = list(REFERENTIE_TELLINGEN) + ["key_samples"]


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


# ============================================================
# Referentie-uitkomst (Delftse testdata)
# ============================================================

def _telPer(coll, veld, match=None):
    """Tel documenten per waarde van een veld, de grootste eerst (sleutels zoals JSON ze schrijft)."""
    pipeline = ([{"$match": match}] if match else []) + [{"$group": {"_id": f"${veld}", "count": {"$sum": 1}}}]
    tellingen = sorted(((d["_id"], d["count"]) for d in coll.aggregate(pipeline)), key=lambda x: (-x[1], str(x[0])))
    # Via JSON: een ontbrekende waarde (None) wordt de sleutel "null", zoals in het fixture
    return json.loads(json.dumps(dict(tellingen), default=str))


def getVoorbeeldsleutels(coll, soort, aantal=AANTAL_VOORBEELDSLEUTELS):
    """Retourneer de eerste sleutels (op key) van een soort met hun projectcode."""
    docs = coll.find({"soort": soort, "key": {"$exists": True, "$ne": None}}, {"_id": 0, "key": 1, "projectcd": 1})
    return [{"key": d.get("key"), "projectcd": d.get("projectcd")}
            for d in docs.sort([("key", 1), ("projectcd", 1)]).limit(aantal)]


def maakReferentie(client=None, db_name=None):
    """Bepaal de uitkomst in de opbouw van de referentie-uitkomst.

    Args:
        client: pymongo-client (standaard een nieuwe op MONGO_URI_DELFT)
        db_name: analysedatabase (standaard DB_ANALYSE)

    Returns:
        Dict met soort_counts_clean, soort_counts_store, artefact_subtypes en key_samples
    """
    eigen = client is None
    client = pymongo.MongoClient(MONGO_URI_DELFT) if eigen else client
    try:
        db = client[db_name or DB_ANALYSE]
        clean, store = db["Single_Store_Clean"], db["Single_Store"]
        return {
            "soort_counts_clean": _telPer(clean, "soort"),
            "soort_counts_store": _telPer(store, "soort"),
            "artefact_subtypes": _telPer(clean, "artefactsoort", {"soort": "Artefact"}),
            "key_samples": {soort: getVoorbeeldsleutels(clean, soort) for soort in REFERENTIE_SLEUTELSOORTEN},
        }
    finally:
        if eigen:
            client.close()


def _verschilTellingen(omschrijving, referentie, uitkomst):
    """Leesbare meldingen voor de verschillen tussen twee tellingen per waarde."""
    meldingen = []
    for waarde in sorted(set(referentie) | set(uitkomst), key=str):
        oud, nieuw = referentie.get(waarde), uitkomst.get(waarde)
        if oud == nieuw:
            continue
        if oud is None:
            meldingen.append(f"{omschrijving} {waarde}: {nieuw}, niet in de referentie")
        elif nieuw is None:
            meldingen.append(f"{omschrijving} {waarde}: ontbreekt (referentie {oud})")
        else:
            meldingen.append(f"{omschrijving} {waarde}: referentie {oud}, nu {nieuw} ({nieuw - oud:+d})")
    return meldingen


def vergelijkReferentie(referentie, uitkomst, client=None, db_name=None):
    """Vergelijk een uitkomst (maakReferentie) met de referentie-uitkomst.

    Tellingen worden per waarde vergeleken. Van de voorbeeldsleutels moet per
    soort de lijst van sleutels gelijk zijn; met een client wordt ook nagegaan
    of elk voorbeeld (sleutel en projectcode) in Single_Store_Clean staat.

    Args:
        referentie: dict uit het fixture
        uitkomst: dict uit maakReferentie
        client: optioneel een pymongo-client voor de controle van de voorbeelden
        db_name: analysedatabase (standaard DB_ANALYSE)

    Returns:
        Dict sectie -> lijst met leesbare meldingen (leeg als er geen verschil is)
    """
    verschillen = {}
    for sectie, omschrijving in REFERENTIE_TELLINGEN.items():
        verschillen[sectie] = _verschilTellingen(omschrijving, referentie.get(sectie) or {}, uitkomst.get(sectie) or {})

    meldingen = []
    clean = client[db_name or DB_ANALYSE]["Single_Store_Clean"] if client is not None else None
    voorbeelden_ref = referentie.get("key_samples") or {}
    voorbeelden_nu = uitkomst.get("key_samples") or {}
    for soort in sorted(set(voorbeelden_ref) | set(voorbeelden_nu)):
        ref, nu = voorbeelden_ref.get(soort) or [], voorbeelden_nu.get(soort) or []
        sleutels_ref, sleutels_nu = sorted(str(v.get("key")) for v in ref), sorted(str(v.get("key")) for v in nu)
        if sleutels_ref != sleutels_nu:
            meldingen.append(f"Voorbeeldsleutels {soort}: referentie {sleutels_ref}, nu {sleutels_nu}")
        if clean is not None:
            for voorbeeld in ref:
                if not clean.count_documents({"soort": soort, "key": voorbeeld.get("key"),
                                              "projectcd": voorbeeld.get("projectcd")}, limit=1):
                    meldingen.append(f"Voorbeeldsleutel {soort} {voorbeeld.get('key')} met projectcd "
                                     f"{voorbeeld.get('projectcd')} staat niet in Single_Store_Clean")
    verschillen["key_samples"] = meldingen
    return verschillen


def schrijfReferentie(filepath, beschrijving=None):
    """Leg de huidige uitkomst vast als referentie; beschrijving en testdata blijven staan als ze er zijn."""
    bestaand = {}
    if os.path.exists(filepath):
        with open(filepath, encoding="utf-8") as f:
            bestaand = json.load(f)
    uitkomst = maakReferentie()
    referentie = {
        "beschrijving": beschrijving if beschrijving else bestaand.get("beschrijving", ""),
        "testdata": bestaand.get("testdata", "data/test/ (project DB034 Koningsveld IV)"),
    }
    referentie.update(uitkomst)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(referentie, f, indent=2, ensure_ascii=False)
        f.write("\n")
    print(f"Referentie-uitkomst geschreven: {filepath}")
    for sectie in REFERENTIE_TELLINGEN:
        print(f"  {sectie}: {len(uitkomst[sectie])} waarden, {sum(uitkomst[sectie].values())} documenten")


def toonVerschillenReferentie(filepath):
    """Vergelijk de huidige uitkomst met een referentie-uitkomst en druk de verschillen af."""
    with open(filepath, encoding="utf-8") as f:
        referentie = json.load(f)
    client = pymongo.MongoClient(MONGO_URI_DELFT)
    try:
        verschillen = vergelijkReferentie(referentie, maakReferentie(client), client)
    finally:
        client.close()
    totaal = 0
    for sectie in REFERENTIE_SECTIES:
        for melding in verschillen[sectie]:
            print(f"  VERSCHIL {melding}")
            totaal += 1
    print("\n✓ Gelijk aan de referentie-uitkomst" if not totaal else f"\n✗ {totaal} verschil(len) met de referentie-uitkomst")
    return totaal == 0


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
    elif action == "referentie":
        schrijfReferentie(filepath, sys.argv[3] if len(sys.argv) > 3 else None)
    elif action == "vergelijk-referentie":
        sys.exit(0 if toonVerschillenReferentie(filepath) else 1)
    else:
        print(f"Onbekende actie: {action}")
        sys.exit(1)
