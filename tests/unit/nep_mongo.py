"""
Minimale in-memory nabootsing van pymongo voor unit tests (geen mongomock nodig).

Ondersteunt alleen wat de modules voor incrementeel laden en de extractie van
afbeeldingen gebruiken: find/find_one (met projectie, sortering en limit),
insert_one/insert_many, update_one met $set, $unset en $push, delete_many,
count_documents, estimated_document_count, create_index (unieke, eventueel
partiële indexen worden gecontroleerd) en aggregate met $match + $group/$sum.

Filters: gelijkheid, een gecompileerde reguliere expressie, $in, $nin, $ne,
$exists, $not, $gt, $gte, $lt, $lte, $or, $and, $nor en veldnamen met punten.
distinct(veld, filter) zoals op een pymongo-collectie.
"""
import copy
import re

from bson import ObjectId
from pymongo.errors import DuplicateKeyError

_ONTBREEKT = object()


def haalOp(doc, pad):
    """Haal een (geneste) waarde op via een pad met punten; _ONTBREEKT als het veld er niet is."""
    deel = doc
    for sleutel in pad.split('.'):
        if isinstance(deel, dict) and sleutel in deel:
            deel = deel[sleutel]
        else:
            return _ONTBREEKT
    return deel


def _zetWaarde(doc, pad, waarde):
    delen = pad.split('.')
    for sleutel in delen[:-1]:
        doc = doc.setdefault(sleutel, {})
    doc[delen[-1]] = waarde


def _verwijderWaarde(doc, pad):
    delen = pad.split('.')
    for sleutel in delen[:-1]:
        doc = doc.get(sleutel)
        if not isinstance(doc, dict):
            return
    doc.pop(delen[-1], None)


_VERGELIJK = {
    '$gt': lambda a, b: a > b,
    '$gte': lambda a, b: a >= b,
    '$lt': lambda a, b: a < b,
    '$lte': lambda a, b: a <= b,
}


def _bevat(waarde, lijst):
    if waarde is _ONTBREEKT:
        return None in lijst
    if isinstance(waarde, list):
        return any(w in lijst for w in waarde)
    return waarde in lijst


def matcht(doc, filt):
    """Bepaal of een document aan een (eenvoudig) MongoDB-filter voldoet."""
    for veld, voorwaarde in (filt or {}).items():
        if veld == '$or':
            if not any(matcht(doc, f) for f in voorwaarde):
                return False
            continue
        if veld == '$and':
            if not all(matcht(doc, f) for f in voorwaarde):
                return False
            continue
        if veld == '$nor':
            if any(matcht(doc, f) for f in voorwaarde):
                return False
            continue
        waarde = haalOp(doc, veld)
        if isinstance(voorwaarde, dict) and voorwaarde and all(k.startswith('$') for k in voorwaarde):
            for op, arg in voorwaarde.items():
                if op == '$in':
                    ok = _bevat(waarde, list(arg))
                elif op == '$nin':
                    ok = not _bevat(waarde, list(arg))
                elif op == '$ne':
                    ok = waarde is _ONTBREEKT or waarde != arg
                elif op == '$exists':
                    ok = (waarde is not _ONTBREEKT) == bool(arg)
                elif op == '$not':
                    # $not met een reguliere expressie of met operatoren (harmonisatie, issue 89)
                    ok = not matcht(doc, {veld: arg})
                elif op in ('$gt', '$gte', '$lt', '$lte'):
                    ok = waarde is not _ONTBREEKT and waarde is not None and _VERGELIJK[op](waarde, arg)
                else:
                    raise NotImplementedError(f"Operator {op} niet ondersteund in nep_mongo")
                if not ok:
                    return False
        elif isinstance(voorwaarde, re.Pattern):
            if not isinstance(waarde, str) or not voorwaarde.search(waarde):
                return False
        else:
            if waarde is _ONTBREEKT:
                if voorwaarde is not None:
                    return False
            elif waarde != voorwaarde:
                return False
    return True


def _projecteer(doc, projectie):
    if not projectie:
        return copy.deepcopy(doc)
    insluiten = [k for k, v in projectie.items() if v and k != '_id']
    if insluiten:
        resultaat = {k: copy.deepcopy(doc[k]) for k in insluiten if k in doc}
        if projectie.get('_id', 1) and '_id' in doc:
            resultaat['_id'] = doc['_id']
        return resultaat
    resultaat = copy.deepcopy(doc)
    for k, v in projectie.items():
        if not v:
            resultaat.pop(k, None)
    return resultaat


class NepCursor(list):
    """Lijst met sort-, limit- en distinct-methoden zoals een pymongo-cursor."""

    def limit(self, aantal):
        return NepCursor(self[:aantal]) if aantal else self

    def sort(self, sleutel, richting=1):
        if isinstance(sleutel, list):
            sleutel, richting = sleutel[0]
        gesorteerd = sorted(self, key=lambda d: d.get(sleutel), reverse=richting < 0)
        return NepCursor(gesorteerd)

    def distinct(self, veld):
        waarden = []
        for d in self:
            waarde = haalOp(d, veld)
            if waarde is not _ONTBREEKT and waarde not in waarden:
                waarden.append(waarde)
        return waarden


class NepResultaat:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


class NepCollectie:
    def __init__(self, naam):
        self.name = naam
        self.docs = []
        self.indexen = []

    # --- lezen ---
    def find(self, filt=None, projectie=None):
        return NepCursor(_projecteer(d, projectie) for d in self.docs if matcht(d, filt))

    def find_one(self, filt=None, projectie=None, sort=None):
        cursor = self.find(filt, projectie)
        if sort:
            cursor = cursor.sort(sort)
        return cursor[0] if cursor else None

    def count_documents(self, filt):
        return len([d for d in self.docs if matcht(d, filt)])

    def distinct(self, veld, filt=None):
        return self.find(filt).distinct(veld)

    def estimated_document_count(self):
        return len(self.docs)

    def aggregate(self, pipeline):
        docs = [copy.deepcopy(d) for d in self.docs]
        for fase in pipeline:
            if '$match' in fase:
                docs = [d for d in docs if matcht(d, fase['$match'])]
            elif '$group' in fase:
                groep = fase['$group']
                veld = groep['_id'].lstrip('$')
                resultaat = {}
                for d in docs:
                    sleutel = haalOp(d, veld)
                    sleutel = None if sleutel is _ONTBREEKT else sleutel
                    rij = resultaat.setdefault(sleutel, {'_id': sleutel})
                    for naam, expr in groep.items():
                        if naam != '_id':
                            rij[naam] = rij.get(naam, 0) + expr['$sum']
                docs = list(resultaat.values())
            else:
                raise NotImplementedError(f"Fase {list(fase)} niet ondersteund in nep_mongo")
        return iter(docs)

    # --- schrijven ---
    def create_index(self, sleutels, unique=False, partialFilterExpression=None, name=None, **kwargs):
        if unique:
            self.indexen.append(([k for k, _ in sleutels], partialFilterExpression or {}))
        return name or '_'.join(k for k, _ in sleutels)

    def _controleerUniek(self, doc):
        if any(d['_id'] == doc['_id'] for d in self.docs):
            raise DuplicateKeyError(f"dubbele _id {doc['_id']}")
        for velden, partieel in self.indexen:
            if not matcht(doc, partieel):
                continue
            for d in self.docs:
                if matcht(d, partieel) and all(haalOp(d, v) == haalOp(doc, v) for v in velden):
                    raise DuplicateKeyError(f"dubbele waarde voor unieke index {velden}")

    def insert_one(self, doc):
        doc.setdefault('_id', ObjectId())
        self._controleerUniek(doc)
        self.docs.append(copy.deepcopy(doc))
        return NepResultaat(inserted_id=doc['_id'])

    def insert_many(self, docs):
        ids = [self.insert_one(doc).inserted_id for doc in docs]
        return NepResultaat(inserted_ids=ids)

    def bulk_write(self, operaties):
        for op in operaties:
            self.insert_one(op._doc)
        return NepResultaat(inserted_count=len(operaties))

    def update_one(self, filt, update):
        for d in self.docs:
            if matcht(d, filt):
                for pad, waarde in update.get('$set', {}).items():
                    _zetWaarde(d, pad, copy.deepcopy(waarde))
                for pad in update.get('$unset', {}):
                    _verwijderWaarde(d, pad)
                # $push met een waarde of met {$each, $slice} (meldingen in het run-document, issue 54)
                for pad, waarde in update.get('$push', {}).items():
                    lijst = haalOp(d, pad)
                    lijst = [] if lijst is _ONTBREEKT else lijst
                    if isinstance(waarde, dict) and '$each' in waarde:
                        lijst = lijst + copy.deepcopy(list(waarde['$each']))
                        if '$slice' in waarde:
                            lijst = lijst[:waarde['$slice']] if waarde['$slice'] >= 0 else lijst[waarde['$slice']:]
                    else:
                        lijst = lijst + [copy.deepcopy(waarde)]
                    _zetWaarde(d, pad, lijst)
                return NepResultaat(matched_count=1, modified_count=1)
        return NepResultaat(matched_count=0, modified_count=0)

    def delete_many(self, filt):
        voor = len(self.docs)
        self.docs = [d for d in self.docs if not matcht(d, filt)]
        return NepResultaat(deleted_count=voor - len(self.docs))

    def drop(self):
        self.docs = []


class NepDatabase:
    def __init__(self, naam):
        self.name = naam
        self.collecties = {}

    def __getitem__(self, naam):
        return self.collecties.setdefault(naam, NepCollectie(naam))

    def list_collection_names(self):
        return [naam for naam, col in self.collecties.items() if col.docs]


class NepClient:
    """Nabootsing van pymongo.MongoClient; close() laat de gegevens staan."""

    def __init__(self):
        self.databases = {}

    def __getitem__(self, naam):
        return self.databases.setdefault(naam, NepDatabase(naam))

    def close(self):
        pass


class NepGridFS:
    """Nabootsing van gridfs.GridFS met alleen exists en delete."""

    def __init__(self, ids=None):
        self.ids = set(ids or [])
        self.verwijderd = []

    def exists(self, file_id):
        return file_id in self.ids

    def delete(self, file_id):
        self.ids.discard(file_id)
        self.verwijderd.append(file_id)
