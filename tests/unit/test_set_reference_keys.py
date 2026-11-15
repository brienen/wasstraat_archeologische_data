"""
Unit tests voor setReferenceKeys (Transform 3) na issue 88.

In de volledige cyclus van 29 oktober 2026 op de productie-installatie
kregen standplaatsen, sporen, vullingen, stellingen, putten, vlakken en
tekeningen een nieuwe primary_key, en raakten de stellingen en ruim 900
tekeningen zelfs uit PostgreSQL. Oorzaak: de Set_ReferenceKeys-taken van
Transform 3 draaien parallel, en setReferenceKeys schreef elk document
volledig terug zoals het was gelezen. De lege sleutelpipeline van Fotokoppel
las zo de hele Single_Store (circa 130.000 documenten, 15 seconden) en
schreef alles terug met key None (keep_fields) en de oude soort: de keys die
de andere taken intussen hadden berekend, gingen verloren. Welke documenten
het trof hing af van de timing; met ``airflow dags test`` (de
integratietests) draaien de taken na elkaar en gebeurt het niet.

Getest:

- een lege pipeline leest en schrijft niets;
- alleen de velden die de pipeline berekent ($addFields en $set) worden
  geschreven; key en soort ook als ze leeg zijn, andere lege velden niet;
- het oude scenario: een taak die een verouderde uitkomst schrijft,
  overschrijft de key van een andere taak niet meer;
- alle sleutelpipelines in meta.py beginnen met $match en hebben alleen
  $addFields-fasen (anders schrijft setReferenceKeys het hele document).
"""
import copy
import sys
import types

import pytest
from bson import ObjectId
from pymongo import UpdateOne

# Mock shared.image_util (wordt via bronbestanden/opruimen geïmporteerd door image_import.py)
if "shared.image_util" not in sys.modules:
    sys.modules["shared.image_util"] = types.ModuleType("shared.image_util")

import wasstraat.meta as meta
import wasstraat.references_functions as references_functions


class SleutelCollectie:
    """Nagebootste Single_Store: aggregate geeft een vooraf bepaalde uitkomst, bulk_write past $set toe."""

    def __init__(self, docs, uitkomst=None):
        self.docs = {d['_id']: copy.deepcopy(d) for d in docs}
        self.uitkomst = uitkomst
        self.pipelines = []
        self.writes = []
        self.database = types.SimpleNamespace(client=types.SimpleNamespace(close=lambda: None))

    def aggregate(self, pipeline, **kwargs):
        self.pipelines.append(copy.deepcopy(pipeline))
        return iter(copy.deepcopy(self.uitkomst if self.uitkomst is not None else list(self.docs.values())))

    def bulk_write(self, operaties, ordered=True):
        for op in operaties:
            assert isinstance(op, UpdateOne)
            assert not op._upsert, "setReferenceKeys mag geen documenten aanmaken (upsert)"
            self.writes.append(copy.deepcopy(op._doc))
            doc = self.docs[op._filter['_id']]
            for veld, waarde in op._doc['$set'].items():
                doc[veld] = waarde


def draai(monkeypatch, collectie, pipeline, soort):
    monkeypatch.setattr(references_functions, 'getAnalyseCollection', lambda: collectie)
    references_functions.setReferenceKeys(pipeline, soort)


SPOOR = [{'$match': {'soort': 'Spoor'}},
         {'$addFields': {'key': {'$concat': ['P', '$projectcd', 'S', {'$toString': '$spoornr'}]}}},
         {'$addFields': {'key_put': {'$concat': ['P', '$projectcd']}}}]


@pytest.mark.unit
class TestLegePipeline:
    """De lege pipeline van Fotokoppel berekent niets en raakt de collectie niet aan."""

    def test_lege_pipeline_leest_en_schrijft_niets(self, monkeypatch):
        collectie = SleutelCollectie([{'_id': 1, 'soort': 'Spoor', 'key': 'PDB034P10S1'}])
        draai(monkeypatch, collectie, [], 'Fotokoppel')
        assert collectie.pipelines == [] and collectie.writes == []
        assert collectie.docs[1]['key'] == 'PDB034P10S1'

    def test_fotokoppel_heeft_een_lege_pipeline(self):
        assert meta.getReferenceKeysPipeline('Fotokoppel') == []

    def test_lege_pipeline_ook_incrementeel_niets(self, monkeypatch):
        """Ook met incrementeel=True: geen $match met alleen de delta van alle soorten."""
        collectie = SleutelCollectie([{'_id': 1, 'soort': 'Spoor'}])
        monkeypatch.setattr(references_functions, 'getAnalyseCollection', lambda: collectie)
        references_functions.setReferenceKeys([], 'Fotokoppel', incrementeel=True)
        assert collectie.pipelines == []


@pytest.mark.unit
class TestAlleenBerekendeVelden:
    """setReferenceKeys schrijft alleen de velden uit de $addFields-fasen."""

    def test_alleen_de_velden_van_de_pipeline(self, monkeypatch):
        doc = {'_id': 1, 'soort': 'Spoor', 'projectcd': 'DB034', 'spoornr': 1, 'putnr': 10, 'datum': None}
        uitkomst = [dict(doc, key='PDB034S1', key_put='PDB034', putnr=10.0)]
        collectie = SleutelCollectie([doc], uitkomst)
        draai(monkeypatch, collectie, SPOOR, 'Spoor')
        assert collectie.writes == [{'$set': {'key': 'PDB034S1', 'key_put': 'PDB034'}}]

    def test_lege_key_en_soort_worden_geschreven_andere_lege_velden_niet(self, monkeypatch):
        """Zoals safe_row_to_dict(keep_fields=['_id', 'key', 'soort']) vóór issue 88."""
        uitkomst = [{'_id': 1, 'soort': 'Vondst', 'key': None, 'key_put': float('nan'), 'key_vlak': 'PDB034P1'}]
        collectie = SleutelCollectie([{'_id': 1, 'soort': 'Vondst', 'key': 'oud'}], uitkomst)
        pipeline = [{'$match': {'soort': 'Vondst'}}, {'$addFields': {'key': 'x', 'key_put': 'y', 'key_vlak': 'z'}}]
        draai(monkeypatch, collectie, pipeline, 'Vondst')
        assert collectie.writes == [{'$set': {'key': None, 'key_vlak': 'PDB034P1'}}]
        assert collectie.docs[1]['key'] is None

    def test_stelling_krijgt_soort_en_key(self, monkeypatch):
        doc = {'_id': 1, 'soort': 'stelling', 'stelling': 'A', 'brondata': {'stelling': 'A'}}
        uitkomst = [dict(doc, soort='Stelling', herkomst=['stellingen'], key='SA')]
        collectie = SleutelCollectie([doc], uitkomst)
        draai(monkeypatch, collectie, meta.getReferenceKeysPipeline('Stelling'), 'Stelling')
        assert collectie.writes == [{'$set': {'herkomst': ['stellingen'], 'soort': 'Stelling', 'key': 'SA'}}]
        assert collectie.docs[1]['brondata'] == {'stelling': 'A'}

    def test_pipeline_zonder_match_bewerkt_alleen_de_eigen_soort(self, monkeypatch):
        collectie = SleutelCollectie([], [])
        draai(monkeypatch, collectie, [{'$addFields': {'key': 'x'}}], 'Spoor')
        assert collectie.pipelines[0][0] == {'$match': {'soort': 'Spoor'}}

    def test_andere_fasen_schrijven_het_hele_document(self, monkeypatch):
        """Onbekende fasen: niet vast te stellen welke velden veranderen, dus alles (behalve lege velden)."""
        uitkomst = [{'_id': 1, 'soort': 'Spoor', 'key': 'K', 'extra': 2, 'leeg': None}]
        collectie = SleutelCollectie([{'_id': 1, 'soort': 'Spoor'}], uitkomst)
        pipeline = [{'$match': {'soort': 'Spoor'}}, {'$project': {'key': 1, 'extra': 1, 'soort': 1}}]
        draai(monkeypatch, collectie, pipeline, 'Spoor')
        assert collectie.writes == [{'$set': {'soort': 'Spoor', 'key': 'K', 'extra': 2}}]

    def test_geneste_velden(self):
        update = references_functions.maakSleutelUpdate(
            {'_id': 1, 'brondata': {'table': 'generated_put'}, 'key': 'K'}, ['brondata.table', 'key', '_id'])
        assert update == {'brondata.table': 'generated_put', 'key': 'K'}


@pytest.mark.unit
class TestGeenVerlorenKeys:
    """Het scenario van 29 oktober 2026, nu zonder verlies."""

    def test_verouderde_uitkomst_overschrijft_de_key_van_een_andere_taak_niet(self, monkeypatch):
        """Taak B las de documenten vóór taak A zijn keys schreef, en schrijft daarna.

        Vóór issue 88 schreef B het hele document terug met key None: de key van A was weg.
        """
        spoor = {'_id': ObjectId(), 'soort': 'Spoor', 'projectcd': 'DB034', 'spoornr': 1}
        collectie = SleutelCollectie([spoor])
        verouderd = [copy.deepcopy(spoor)]

        # Taak A berekent de key van het spoor
        collectie.uitkomst = [dict(spoor, key='PDB034S1', key_put='PDB034')]
        draai(monkeypatch, collectie, SPOOR, 'Spoor')
        # Taak B (een andere pipeline over hetzelfde document) schrijft zijn verouderde uitkomst
        collectie.uitkomst = [dict(verouderd[0], key_extra='E')]
        draai(monkeypatch, collectie, [{'$match': {'projectcd': 'DB034'}}, {'$addFields': {'key_extra': 'E'}}], 'Spoor')

        assert collectie.docs[spoor['_id']]['key'] == 'PDB034S1'
        assert collectie.docs[spoor['_id']]['key_extra'] == 'E'

    def test_soort_van_stellingen_blijft(self, monkeypatch):
        stelling = {'_id': 1, 'soort': 'stelling', 'stelling': 'A'}
        collectie = SleutelCollectie([stelling])
        collectie.uitkomst = [dict(stelling, soort='Stelling', herkomst=['stellingen'], key='SA')]
        draai(monkeypatch, collectie, meta.getReferenceKeysPipeline('Stelling'), 'Stelling')
        # De lege pipeline van Fotokoppel draait daarna (of tegelijk): geen verouderde soort meer
        collectie.uitkomst = [copy.deepcopy(stelling)]
        draai(monkeypatch, collectie, meta.getReferenceKeysPipeline('Fotokoppel'), 'Fotokoppel')
        assert collectie.docs[1]['soort'] == 'Stelling' and collectie.docs[1]['key'] == 'SA'


@pytest.mark.unit
class TestSleutelpipelinesInMeta:
    """Alle sleutelpipelines zijn bruikbaar met alleen de berekende velden."""

    @pytest.mark.parametrize('soort', [s for s in meta.getKeys(meta.SET_KEYS_PIPELINES)
                                       if meta.getReferenceKeysPipeline(s)])
    def test_begint_met_match_en_bekende_velden(self, soort):
        pipeline = meta.getReferenceKeysPipeline(soort)
        assert '$match' in pipeline[0], f"De sleutelpipeline van {soort} begint niet met $match"
        velden = references_functions.getPipelineVelden(pipeline)
        assert velden, f"De sleutelpipeline van {soort} heeft andere fasen dan $match en $addFields"

    def test_velden_in_volgorde_zonder_dubbelen(self):
        pipeline = [{'$match': {}}, {'$addFields': {'a': 1, 'b': 2}}, {'$set': {'a': 3, 'c': 4}}]
        assert references_functions.getPipelineVelden(pipeline) == ['a', 'b', 'c']
        assert references_functions.getPipelineVelden([{'$match': {}}, {'$unwind': '$x'}]) is None

    def test_key_van_spoor_en_standplaats_wordt_berekend(self):
        for soort in ('Spoor', 'Vulling', 'Standplaats', 'Put', 'Vlak', 'Stelling', 'Tekening', 'Monster_Botanie'):
            assert 'key' in references_functions.getPipelineVelden(meta.getReferenceKeysPipeline(soort))
