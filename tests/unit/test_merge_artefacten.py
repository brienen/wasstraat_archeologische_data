"""
Unit tests voor het verplaatsen en samenvoegen van artefacten in Transform 5 (issue 83).

Een artefact uit Single_Store gaat naar precies één document in
Single_Store_Clean: het wordt samengevoegd (merge op key_subnr en
artefactsoort) of verplaatst (move), nooit allebei. Tot issue 83 verplaatste
de move ook de artefacten uit tabellen waarvan de naam niet met ARTEFACT
begint en de artefacten zonder artefactsoort, terwijl de merge ze ook
samenvoegde; bij een groep met meer dan één bronrij bleven de verplaatste
exemplaren naast het samengevoegde document staan (dezelfde key).

De voorwaarden worden getoetst met de nagebootste MongoDB-filters uit
tests/unit/nep_mongo.py. De klasse TestSimulatie bootst de move en de merge na
($match, $group met $mergeObjects en $addToSet, $merge op _id) en controleert
de uitkomst in Single_Store_Clean.
"""
import copy
import sys
import types

import pytest
from bson import ObjectId

# Mock shared.image_util (wordt via bronbestanden/opruimen geïmporteerd door image_import.py)
if "shared.image_util" not in sys.modules:
    sys.modules["shared.image_util"] = types.ModuleType("shared.image_util")

import wasstraat.delta_transform as delta_transform
import wasstraat.merge_functions as merge_functions
from tests.unit import nep_mongo


SY002_MDB = '/input/projecten/SY002/C Database/opgravingSY002.mdb'
KOPIE_MDB = '/input/projecten/SY002/C Database/kopieSY002.mdb'


def artefact(tabel, subnr=None, artefactsoort='Aardewerk', projectcd='SY002', putnr=1, vondstnr=1,
             mdbfile=SY002_MDB, bron_id=1, **extra):
    """Een artefact zoals het na Transform 3 in Single_Store staat."""
    brondata = {'table': tabel, 'mdbfile': mdbfile, 'projectcd': projectcd, 'ID': bron_id}
    brondata.update(extra.pop('brondata_extra', {}))
    doc = {'_id': ObjectId(), 'soort': 'Artefact', 'projectcd': projectcd, 'putnr': putnr, 'vondstnr': vondstnr,
           'brondata': brondata}
    if subnr is not None:
        doc['subnr'] = subnr
        doc['key_subnr'] = f"P{projectcd}P{putnr}V{vondstnr}A{subnr}"
    if artefactsoort is not None:
        doc['artefactsoort'] = artefactsoort
    doc.update(extra)
    return doc


def verplaatst(doc):
    """Bepaal of de move-pipeline van Artefact het document meeneemt (eerste twee $match-fasen)."""
    pipeline = merge_functions.getMoveAggregate('Artefact')
    return all(nep_mongo.matcht(doc, fase['$match']) for fase in pipeline[:2])


def samengevoegd(doc):
    """Bepaal of de merge-pipeline van Artefact het document meeneemt (eerste twee $match-fasen)."""
    pipeline = merge_functions.getMergeAggregate('Artefact', key='key_subnr')
    return all(nep_mongo.matcht(doc, fase['$match']) for fase in pipeline[:2])


@pytest.fixture
def nietMergenProjecten(monkeypatch):
    """Zet artefact_niet_mergen (correcties.yml) op DC112, zoals in de Delftse configuratie."""
    monkeypatch.setattr(merge_functions, 'ARTEFACT_NOT_MERGE_PROJECTS', ['DC112'])


# ============================================================
# Voorwaarden van move en merge
# ============================================================

@pytest.mark.unit
class TestVoorwaarden:
    """Elk artefact wordt verplaatst óf samengevoegd, sinds issue 86 ook uit de RAAP-tabel ARTEFACT."""

    @pytest.mark.parametrize("doc", [
        artefact('AARDEWERK 1', subnr=2),
        artefact('AARDEWERK 1'),
        artefact('AARDEWERK 3', subnr=2),
        artefact('MUNTEN EN PENNINGEN', subnr=1, artefactsoort='Munt'),
        artefact('GLAS', subnr=1, artefactsoort='Glas'),
        artefact('ARTF_AW', artefactsoort='Aardewerk'),
        artefact('AARDEWERK 1', subnr=3, artefactsoort=None),
        artefact('AARDEWERK 1', subnr=3, artefactsoort=''),
        artefact('AARDEWERK 1', subnr=3, artefactsoort='onbekend'),
        artefact('ROMEINS AARDEWERK', subnr=4),
        artefact('AARDEWERK 1', subnr=5, projectcd='DC112'),
        artefact('ARTF_MET', subnr=1, artefactsoort='Metaal', brondata_extra={'ARTEFACT': 12}),
        artefact('ARTEFACTEN', subnr=6),
        artefact('ARTEFACT', artefactsoort=None, brondata_extra={'ARTEFACT': 1, 'MATERIAAL': 'OPH'}),
        artefact('ARTEFACT', subnr=1),
    ], ids=['specifieke tabel met subnr', 'zonder subnr', 'tweede tabel met subnr', 'munt', 'glas',
            'raap-tabel zonder subnr', 'zonder artefactsoort', 'lege artefactsoort', 'artefactsoort onbekend',
            'romeins aardewerk', 'artefact_niet_mergen', 'kolom ARTEFACT', 'tabel begint met ARTEFACT',
            'raap-tabel ARTEFACT', 'tabel ARTEFACT met subnr'])
    def test_precies_een_van_beide(self, doc, nietMergenProjecten):
        assert verplaatst(doc) != samengevoegd(doc), (
            f"{doc['brondata']['table']}: verplaatst={verplaatst(doc)}, samengevoegd={samengevoegd(doc)}")

    def test_specifieke_tabel_met_subnr_alleen_samengevoegd(self):
        """Tot issue 83 werd zo'n rij ook verplaatst (tabel begint niet met ARTEFACT)."""
        doc = artefact('AARDEWERK 1', subnr=2)
        assert samengevoegd(doc)
        assert not verplaatst(doc)

    def test_zonder_artefactsoort_met_subnr_alleen_samengevoegd(self):
        """Tot issue 83 werd zo'n rij ook verplaatst; de merge zet de artefactsoort op Onbekend."""
        for artefactsoort in [None, '', ' onbekend ', '-']:
            doc = artefact('AARDEWERK 1', subnr=3, artefactsoort=artefactsoort)
            assert samengevoegd(doc) and not verplaatst(doc), artefactsoort

    def test_zonder_subnr_alleen_verplaatst(self):
        doc = artefact('AARDEWERK 1')
        assert verplaatst(doc)
        assert not samengevoegd(doc)

    def test_artefact_niet_mergen_alleen_verplaatst(self, nietMergenProjecten):
        """Artefacten van een project uit artefact_niet_mergen blijven apart, ook met hetzelfde subnummer."""
        doc = artefact('AARDEWERK 1', subnr=5, projectcd='DC112')
        assert verplaatst(doc)
        assert not samengevoegd(doc)

    def test_artefact_niet_mergen_wordt_bij_aanroep_gelezen(self, monkeypatch):
        doc = artefact('AARDEWERK 1', subnr=5, projectcd='DC050')
        assert samengevoegd(doc)
        monkeypatch.setattr(merge_functions, 'ARTEFACT_NOT_MERGE_PROJECTS', ['DC050'])
        assert verplaatst(doc) and not samengevoegd(doc)

    def test_romeins_aardewerk_alleen_verplaatst(self):
        doc = artefact('ROMEINS AARDEWERK', subnr=4)
        assert verplaatst(doc)
        assert not samengevoegd(doc)

    def test_kolom_artefact_alleen_verplaatst(self):
        doc = artefact('ARTF_MET', subnr=1, artefactsoort='Metaal', brondata_extra={'ARTEFACT': 12})
        assert verplaatst(doc)
        assert not samengevoegd(doc)

    def test_raap_tabel_artefact_verplaatst(self, nietMergenProjecten):
        """Issue 86: de RAAP-tabel ARTEFACT wordt verplaatst zoals elke rij met een kolom ARTEFACT.

        Tot dan werd hij nooit verplaatst (ontwerp van 2022) en kwamen zijn rijen niet in
        Single_Store_Clean (Delft: 132 rijen in DC008, DC024 en DC112).
        """
        for doc in [artefact('ARTEFACT', artefactsoort=None, brondata_extra={'ARTEFACT': 1}),
                    artefact('ARTEFACT', subnr=1, projectcd='DC112'),
                    artefact('ARTEFACT', subnr=1, brondata_extra={'ARTEFACT': 1})]:
            assert verplaatst(doc) and not samengevoegd(doc)
        # Met subnummer en zonder kolom ARTEFACT (komt in RAAP niet voor): samengevoegd, zoals elke tabel
        assert samengevoegd(artefact('ARTEFACT', subnr=1)) and not verplaatst(artefact('ARTEFACT', subnr=1))

    def test_andere_soort_niet_verplaatst_als_artefact(self):
        doc = artefact('AARDEWERK 1')
        doc['soort'] = 'Spoor'
        assert not verplaatst(doc)


@pytest.mark.unit
class TestPijplijnen:
    """De move- en merge-pipeline gebruiken dezelfde voorwaarde, op de plek waar moveSoort en mergeSoort die verwachten."""

    def test_move_pipeline(self):
        pipeline = merge_functions.getMoveAggregate('Artefact')
        assert pipeline[0] == {'$match': {'soort': 'Artefact'}}
        assert pipeline[1] == merge_functions.getInverseMatchArtefact()
        # Precies het complement van de merge-voorwaarde, zonder uitgezonderde tabellen (issue 86)
        assert pipeline[1]['$match'] == {'$and': [{'soort': 'Artefact'},
                                                  {'$nor': [merge_functions.getArtefactMergeVoorwaarde()]}]}
        assert pipeline[2] == merge_functions.AGGR_PHASE_CLEAN_EMPTY
        assert '$merge' in pipeline[-1]

    def test_merge_pipeline(self):
        pipeline = merge_functions.getMergeAggregate('Artefact', key='key_subnr')
        assert pipeline[0] == {'$match': {'soort': 'Artefact'}}
        assert pipeline[1] == {'$match': merge_functions.getArtefactMergeVoorwaarde()}
        assert pipeline[2] == merge_functions.AGGR_PHASE_CLEAN_EMPTY
        # De artefactsoort wordt vóór de $group genormaliseerd: varianten van 'onbekend' vormen één groep
        assert pipeline[3] == merge_functions.AGGR_PHASE_ARTEFACTSOORT
        assert pipeline[4]['$group']['_id'] == {'key_subnr': '$key_subnr', 'artefactsoort': '$artefactsoort'}
        assert '$merge' in pipeline[-1]

    def test_andere_soorten_ongewijzigd(self):
        assert merge_functions.getMoveAggregate('Spoor')[1] == merge_functions.AGGR_PHASE_CLEAN_EMPTY
        assert merge_functions.getMergeAggregate('Vondst')[1] == merge_functions.AGGR_PHASE_CLEAN_EMPTY

    def test_geen_gedeelde_lijsten(self, monkeypatch):
        """Een aangepaste pipeline (bijv. de delta-variant) verandert de voorwaarde niet."""
        pipeline = merge_functions.getMoveAggregate('Artefact')
        pipeline[1]['$match']['$and'][1]['$nor'][0]['$and'][2]['brondata.table']['$nin'].append('X')
        assert 'X' not in merge_functions.ARTEFACT_NOT_MERGE_TABLES
        assert 'X' not in merge_functions.getMoveAggregate('Artefact')[1]['$match']['$and'][1]['$nor'][0]['$and'][2]['brondata.table']['$nin']


# ============================================================
# Nabootsing van Transform 5 voor artefacten
# ============================================================

def _zonderLegeVelden(doc):
    """AGGR_PHASE_CLEAN_EMPTY: velden met None, '-' of de onbekende projectcode vallen weg."""
    return {k: v for k, v in doc.items() if v is not None and v != '-'}


def simuleerTransform5(single_store):
    """Boots move en merge van artefacten na en retourneer Single_Store_Clean.

    Move: elk document dat aan de move-voorwaarde voldoet, met brondata als
    lijst, op zijn eigen _id. Merge (daarna, zoals in de taakgroep): per
    (key_subnr, genormaliseerde artefactsoort) één document met de velden van de laatste
    bronrij ($mergeObjects, dus ook diens _id), alle bronrijen in brondata en
    brondata_count; $merge op _id vervangt een verplaatst document met hetzelfde _id.
    """
    clean = {}
    for doc in single_store:
        if verplaatst(doc):
            nieuw = _zonderLegeVelden(copy.deepcopy(doc))
            nieuw['brondata'] = [nieuw['brondata']]
            clean[nieuw['_id']] = nieuw
    groepen = {}
    for doc in single_store:
        if samengevoegd(doc):
            doc = _zonderLegeVelden(copy.deepcopy(doc))
            # AGGR_PHASE_ARTEFACTSOORT, vóór de $group
            soort = str(doc.get('artefactsoort', '')).strip()
            doc['artefactsoort'] = 'Onbekend' if soort.lower() in ('', '-', 'onbekend') else soort
            groepen.setdefault((doc.get('key_subnr'), doc.get('artefactsoort')), []).append(doc)
    for docs in groepen.values():
        nieuw = {}
        for doc in docs:
            nieuw.update(doc)
        nieuw['brondata'] = [doc['brondata'] for doc in docs]
        nieuw['brondata_count'] = len(docs)
        clean[nieuw['_id']] = nieuw
    return list(clean.values())


@pytest.mark.unit
class TestSimulatie:
    """Single_Store_Clean na move en merge: geen verplaatst exemplaar naast een samengevoegd document."""

    def test_groep_met_twee_bronrijen_wordt_een_document(self):
        """SY002: twee rijen in AARDEWERK 1 met put 1, vondst 1, subnr 2 (zoals in de synthetische data)."""
        eerste = artefact('AARDEWERK 1', subnr=2, bron_id=2, vorm='Kogelpot')
        tweede = artefact('AARDEWERK 1', subnr=2, bron_id=11, decoratie='Radstempel')
        clean = simuleerTransform5([eerste, tweede])
        assert len(clean) == 1
        doc = clean[0]
        assert doc['brondata_count'] == 2
        assert doc['_id'] == tweede['_id']
        assert doc['vorm'] == 'Kogelpot' and doc['decoratie'] == 'Radstempel'
        assert delta_transform.getBronsleutel(doc['brondata']) == (
            'projecten/SY002/C Database/opgravingSY002.mdb:AARDEWERK 1:11;'
            'projecten/SY002/C Database/opgravingSY002.mdb:AARDEWERK 1:2')

    def test_bronrijen_uit_meer_tabellen_en_databases(self):
        """Dezelfde scherf in AARDEWERK 1 en AARDEWERK 3 en in een kopie van de database (Delft: DC026, DC097)."""
        docs = [artefact('AARDEWERK 1', subnr=7), artefact('AARDEWERK 3', subnr=7),
                artefact('AARDEWERK 1', subnr=7, mdbfile=KOPIE_MDB)]
        clean = simuleerTransform5(docs)
        assert len(clean) == 1
        assert clean[0]['brondata_count'] == 3

    def test_elke_key_een_keer(self, nietMergenProjecten):
        """Alle artefacten met een key_subnr hebben een unieke key in PostgreSQL, behalve artefact_niet_mergen."""
        docs = [
            artefact('AARDEWERK 1', subnr=2, bron_id=2), artefact('AARDEWERK 1', subnr=2, bron_id=11),
            artefact('AARDEWERK 1', subnr=1, bron_id=1), artefact('GLAS', subnr=1, artefactsoort='Glas'),
            artefact('AARDEWERK 1', subnr=3, artefactsoort=None, bron_id=3),
            artefact('AARDEWERK 1', subnr=3, artefactsoort='', bron_id=4),
            artefact('AARDEWERK 1', bron_id=5), artefact('AARDEWERK 1', bron_id=6),
            artefact('AARDEWERK 1', subnr=5, projectcd='DC112', bron_id=7),
            artefact('AARDEWERK 1', subnr=5, projectcd='DC112', bron_id=8),
        ]
        clean = simuleerTransform5(docs)
        # Elke bronrij precies één keer in Single_Store_Clean
        bronrijen = [delta_transform.getBronrijId(b) for d in clean for b in d['brondata']]
        assert sorted(bronrijen) == sorted(delta_transform.getBronrijId(d['brondata']) for d in docs)
        keys = [delta_transform.getArtefactKey(d) for d in clean if d.get('projectcd') != 'DC112']
        keys = [k for k in keys if k]
        assert len(keys) == len(set(keys)), keys
        # artefact_niet_mergen: twee losse documenten met dezelfde key
        dc112 = [d for d in clean if d.get('projectcd') == 'DC112']
        assert len(dc112) == 2
        assert all('brondata_count' not in d for d in dc112)

    def test_zonder_subnr_blijven_rijen_apart(self):
        docs = [artefact('AARDEWERK 1', bron_id=1), artefact('AARDEWERK 1', bron_id=2)]
        clean = simuleerTransform5(docs)
        assert len(clean) == 2
        assert all(len(d['brondata']) == 1 for d in clean)

    def test_raap_kop_en_detailrijen_elk_een_document(self, nietMergenProjecten):
        """Issue 86: de rij uit de RAAP-tabel ARTEFACT komt naast zijn detailrijen in Single_Store_Clean.

        In een RAAP-database is ARTEFACT de kop (artefactnummer, materiaal, totaal aantal en gewicht) en
        staan de stukken in een tabel per materiaal (ARTF_OPH, ARTF_MET ...) met hetzelfde artefactnummer
        en een SPLIT_ID. mergeRAAPArtefacts (Transform 3) neemt aantal, gewicht en materiaal van de kop
        over in de detailrijen. Sinds issue 86 wordt ook de kop geladen, met een eigen key zonder S.
        """
        kop = artefact('ARTEFACT', artefactsoort='Hout', projectcd='DC112', vondstnr=13, putnr=None,
                       brondata_extra={'ARTEFACT': 2, 'MATERIAAL': 'OPH'}, artefactnr=2, key='PDC112V13A2')
        details = [artefact('ARTF_OPH', subnr=701 + i, artefactsoort='Hout', projectcd='DC112', vondstnr=13,
                            putnr=None, bron_id=10 + i, brondata_extra={'ARTEFACT': 2, 'SPLIT_ID': i},
                            artefactnr=2, splitid=i, key=f'PDC112V13A2S{i}') for i in range(2)]
        clean = simuleerTransform5([kop] + details)
        assert sorted(delta_transform.getArtefactKey(d) for d in clean) == ['PDC112V13A2', 'PDC112V13A2S0',
                                                                            'PDC112V13A2S1']
        assert all(len(d['brondata']) == 1 for d in clean)
