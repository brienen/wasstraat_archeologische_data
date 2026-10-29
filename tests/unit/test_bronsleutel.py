"""
Unit tests voor de hulpsleutel uit de bronrij (issue 81).

Rijen zonder (unieke) natuurlijke key kregen bij elke volledige cyclus een
nieuw nummer: artefacten zonder subnr, monsters, plaatsingen, vindplaatsen en
rijen waarvan de key vaker voorkomt (standplaatsen, sporen, dozen, artefacten
die zowel verplaatst als samengevoegd zijn). De hulpsleutel komt uit de
bronrij (bestand, tabel en autonummer, of een hash van de inhoud) en wordt
afgeleid uit ``brondata``, in MongoDB en in de kolom brondata van PostgreSQL.

Test wasstraat/delta_transform.py:

- getBronrijId en getBronsleutel: autonummer, hash zonder autonummer,
  onafhankelijk van _id, loadtime en de volgorde van samengevoegde bronrijen
- leesBrondataTekst: str() van brondata uit MongoDB terug lezen (ObjectId,
  Int64, datetime, nan), zonder eval
- getLaadKey: natuurlijke key heeft voorrang, leesbare hulpsleutel zonder key
- bepaalStabieleIds: koppeling op bronsleutel bij dubbele keys, de overgang
  voor rijen zonder key, identieke bronrijen, een bronrij met twee
  artefactsoorten, voorrang van de unieke key
- leesPgBronsleutels en setStabielePrimaryKeys met een nagebootste PostgreSQL
  en MongoDB

en de load (vulLaadKey, leesDocumenten) en meta.py (key van Monster_Botanie en
Monster_Schelp uit het autonummer Id).

Issue 88: leesBrondataTekst op echte teksten uit de productie-installatie
(tests/unit/fixtures/brondata_delft.json) en op Decimal128, Decimal,
Timestamp, geneste waarden en lange teksten; getVervangendeKeys en de
koppeling op een vervangende key in bepaalStabieleIds (stap 3b), plus de
telling van documenten die een nieuw nummer krijgen terwijl hun bronrij met
een andere key in de tabel staat.
"""
import datetime
import decimal
import json
import os
import sys
import types

import pytest
from bson import ObjectId
from bson.decimal128 import Decimal128
from bson.int64 import Int64
from bson.timestamp import Timestamp as BsonTimestamp

# Mock shared.image_util (wordt via bronbestanden/opruimen geïmporteerd door image_import.py)
if "shared.image_util" not in sys.modules:
    sys.modules["shared.image_util"] = types.ModuleType("shared.image_util")

import wasstraat.delta_transform as delta_transform
import wasstraat.loadToDatabase_functions as load
import wasstraat.meta as meta
import wasstraat.verwerkingsrun as verwerkingsrun
from tests.unit.test_delta_transform import UitgebreideClient, matchtMetRegex
from tests.unit import nep_mongo


DB34 = '/input/projecten/DB034_Koningsveld IV/C Database/opgravingDB34.mdb'
DB34_RELATIEF = 'projecten/DB034_Koningsveld IV/C Database/opgravingDB34.mdb'
MAGAZIJN = '/input/magazijnlijst/MAGAZIJN.mdb'


def bronrij(tabel='AW1DeterminatiesJohan', mdbfile=DB34, **velden):
    """Een bronrij zoals importMDB.sh hem in de staging zet."""
    rij = {'_id': ObjectId(), 'table': tabel, 'projectcd': 'DB034', 'bron': 'opgravingDB034',
           'loadtime': '2026-10-21T08:25:59+00:00', 'mdbfile': mdbfile}
    rij.update(velden)
    return rij


# ============================================================
# Identiteit van een bronrij
# ============================================================

@pytest.mark.unit
class TestBronrijId:
    """getBronrijId: bestand, tabel en autonummer, of een hash van de inhoud."""

    @pytest.mark.parametrize('kolom', ['ID', 'Id', 'id'])
    def test_autonummer(self, kolom):
        assert delta_transform.getBronrijId(bronrij(**{kolom: 4, 'VONDSTNO': 460})) == \
            f'{DB34_RELATIEF}:AW1DeterminatiesJohan:4'

    def test_autonummer_als_float_en_int64(self):
        assert delta_transform.getBronrijId(bronrij(ID=4.0)).endswith(':4')
        assert delta_transform.getBronrijId(bronrij(ID=Int64(7))).endswith(':7')

    def test_voorkeur_voor_ID_boven_Id(self):
        assert delta_transform.getBronrijId(bronrij(ID=1, Id=2)).endswith(':1')

    def test_geen_autonummer_bij_tekst_bool_of_breuk(self):
        for waarde in ('4', True, 4.5, float('nan')):
            assert ':#' in delta_transform.getBronrijId(bronrij(ID=waarde))

    def test_hash_zonder_autonummer_is_stabiel_per_extractie(self):
        """Een nieuwe extractie geeft een nieuw _id en loadtime; de identiteit blijft gelijk."""
        a = bronrij(tabel='ARTF_AW1', VONDSTaw=8, type='r-pot')
        b = bronrij(tabel='ARTF_AW1', VONDSTaw=8, type='r-pot', loadtime='2026-10-22T09:00:00+00:00',
                    bron='iets anders', projectcd='DB34')
        assert delta_transform.getBronrijId(a) == delta_transform.getBronrijId(b)
        assert delta_transform.getBronrijId(a).startswith(f'{DB34_RELATIEF}:ARTF_AW1:#')

    def test_hash_hangt_af_van_inhoud_niet_van_volgorde(self):
        a = bronrij(tabel='ARTF_AW1', VONDSTaw=8, type='r-pot')
        b = bronrij(tabel='ARTF_AW1', type='r-pot', VONDSTaw=8)
        c = bronrij(tabel='ARTF_AW1', VONDSTaw=9, type='r-pot')
        assert delta_transform.getBronrijId(a) == delta_transform.getBronrijId(b)
        assert delta_transform.getBronrijId(a) != delta_transform.getBronrijId(c)

    def test_bestand_en_tabel_horen_bij_de_identiteit(self):
        """Kopieën van een database in een andere map (werkmap) zijn andere bronrijen."""
        a = bronrij(ID=4)
        b = bronrij(ID=4, mdbfile='/input/projecten/DB034_Koningsveld IV/K Overig/opgravingDB34.mdb')
        c = bronrij(ID=4, tabel='AARDEWERK 1')
        assert len({delta_transform.getBronrijId(r) for r in (a, b, c)}) == 3

    def test_pad_buiten_de_invoermap_blijft_volledig(self):
        assert delta_transform.getBronrijId(bronrij(ID=1, mdbfile='/elders/x.mdb')) == '/elders/x.mdb:AW1DeterminatiesJohan:1'

    @pytest.mark.parametrize('element', [
        None, 'tekst', {'table': 'generated_put', 'projectcd': 'DB034'}, {'mdbfile': DB34}, {'mdbfile': '', 'table': 'X'},
    ])
    def test_geen_bronrij(self, element):
        assert delta_transform.getBronrijId(element) is None


@pytest.mark.unit
class TestBronsleutel:
    """getBronsleutel: één of meer bronrijen van een document."""

    def test_verplaatst_document(self):
        assert delta_transform.getBronsleutel([bronrij(ID=4)]) == f'{DB34_RELATIEF}:AW1DeterminatiesJohan:4'

    def test_samengevoegd_document_onafhankelijk_van_volgorde(self):
        """$addToSet in de merge garandeert geen volgorde van brondata."""
        a, b = bronrij(tabel='AARDEWERK 1', ID=384), bronrij(tabel='CATALOGUS AW1', CODE='x')
        sleutel = delta_transform.getBronsleutel([a, b])
        assert sleutel == delta_transform.getBronsleutel([b, a])
        assert sleutel.count(delta_transform.SCHEIDING_BRONRIJEN) == 1
        assert sleutel.split(';')[0] < sleutel.split(';')[1]

    def test_samengevoegd_document_verschilt_van_zijn_bronrijen(self):
        """Een samengevoegd document botst niet met het verplaatste document van een van zijn bronrijen."""
        a, b = bronrij(tabel='AARDEWERK 1', ID=384), bronrij(tabel='AW1DeterminatiesJohan', ID=761)
        assert delta_transform.getBronsleutel([a, b]) != delta_transform.getBronsleutel([a])

    def test_dubbele_bronrij_telt_een_keer(self):
        a = bronrij(ID=4)
        assert delta_transform.getBronsleutel([a, dict(a)]) == delta_transform.getBronsleutel([a])

    def test_lange_sleutel_wordt_hash(self):
        rijen = [bronrij(ID=i) for i in range(20)]
        sleutel = delta_transform.getBronsleutel(rijen)
        assert sleutel.startswith('20 bronrijen #') and len(sleutel) < 40
        assert sleutel == delta_transform.getBronsleutel(list(reversed(rijen)))

    @pytest.mark.parametrize('brondata', [None, [], {'table': 'generated_vondst', 'projectcd': 'DB034'}, [None, 4.0]])
    def test_geen_bronsleutel(self, brondata):
        assert delta_transform.getBronsleutel(brondata) is None

    def test_een_element_als_dict(self):
        assert delta_transform.getBronsleutel(bronrij(ID=4)) == delta_transform.getBronsleutel([bronrij(ID=4)])


# ============================================================
# brondata uit PostgreSQL terug lezen
# ============================================================

@pytest.mark.unit
class TestLeesBrondataTekst:
    """leesBrondataTekst leest str() van brondata zoals transformRow het in PostgreSQL zet."""

    def test_rondgang_geeft_dezelfde_bronsleutel(self):
        brondata = [
            bronrij(ID=Int64(4), VONDSTNO=460, gewicht=12.5, leeg=None, vlag=True,
                    opmerking="Rand met 'oor' en \"tuit\"\nen een regeleinde", datum=datetime.datetime(2020, 5, 1, 13, 5)),
            bronrij(tabel='CATALOGUS AW1', nan_veld=float('nan'), negatief=-3, tekst='ë ü ß €'),
        ]
        tekst = str(brondata)
        assert 'ObjectId(' in tekst and 'datetime.datetime(' in tekst and 'nan' in tekst
        terug = delta_transform.leesBrondataTekst(tekst)
        assert terug[0]['ID'] == 4 and terug[0]['_id'] == str(brondata[0]['_id'])
        assert terug[0]['datum'] == datetime.datetime(2020, 5, 1, 13, 5)
        assert delta_transform.getBronsleutel(terug) == delta_transform.getBronsleutel(brondata)

    def test_int64_en_datum_als_tekst(self):
        """Oudere versies van bson schrijven Int64(5); ook datetime.date wordt gelezen."""
        terug = delta_transform.leesBrondataTekst("[{'ID': Int64(5), 'd': datetime.date(2020, 1, 2), 'x': -1.5}]")
        assert terug == [{'ID': 5, 'd': datetime.date(2020, 1, 2), 'x': -1.5}]

    def test_gegenereerd_document(self):
        tekst = str({'table': 'generated_put', 'projectcd': 'DB034'})
        assert delta_transform.leesBrondataTekst(tekst) == {'table': 'generated_put', 'projectcd': 'DB034'}

    @pytest.mark.parametrize('tekst', [
        None, '', '   ', 'geen python', "[{'a': 1}", '42', "'tekst'",
        "__import__('os').system('echo fout')", "[{'a': open('/etc/passwd')}]", "[{'a': (lambda: 1)()}]",
        "[{**{'a': 1}}]", "[{'a': -'x'}]",
    ])
    def test_onleesbaar_of_onveilig_geeft_none(self, tekst):
        assert delta_transform.leesBrondataTekst(tekst) is None


# ============================================================
# Key voor PostgreSQL
# ============================================================

@pytest.mark.unit
class TestLaadKey:
    """getLaadKey: natuurlijke key, anders de leesbare hulpsleutel."""

    def test_natuurlijke_key_heeft_voorrang(self):
        assert delta_transform.getLaadKey('Spoor', {'key': 'PDB034P10S5', 'brondata': [bronrij(ID=1)]}) == 'PDB034P10S5'
        doc = {'key_subnr': 'PDB034P10V460A1', 'artefactsoort': 'Glas', 'brondata': [bronrij(ID=1)]}
        assert delta_transform.getLaadKey('Artefact', doc) == 'PDB034P10V460A1|Glas'

    def test_artefact_zonder_subnr(self):
        doc = {'projectcd': 'DB034', 'putnr': 10.0, 'vondstnr': 460.0, 'artefactsoort': 'Aardewerk',
               'brondata': [bronrij(ID=4)]}
        assert delta_transform.getLaadKey('Artefact', doc) == \
            f'PDB034P10V460|Aardewerk|bron:{DB34_RELATIEF}:AW1DeterminatiesJohan:4'

    def test_artefact_zonder_put_en_vondst(self):
        doc = {'projectcd': 'DB034', 'artefactsoort': 'Glas', 'brondata': [bronrij(tabel='GLAS VOORWERP', ID=2)]}
        assert delta_transform.getLaadKey('Artefact', doc) == f'PDB034|Glas|bron:{DB34_RELATIEF}:GLAS VOORWERP:2'

    def test_andere_soort_zonder_key(self):
        doc = {'brondata': [bronrij(tabel='magazijnlijst', mdbfile=MAGAZIJN, ID=1)]}
        assert delta_transform.getLaadKey('Plaatsing', doc) == 'bron:magazijnlijst/MAGAZIJN.mdb:magazijnlijst:1'

    @pytest.mark.parametrize('soort', ['Bestand', 'Foto', 'Tekening', 'Rapport', 'ABR'])
    def test_geen_hulpsleutel_voor_bestanden_en_abr(self, soort):
        assert delta_transform.getLaadKey(soort, {'brondata': [bronrij(ID=1)]}) is None

    def test_zonder_bronrij_geen_key(self):
        assert delta_transform.getLaadKey('Plaatsing', {'brondata': {'table': 'generated_x'}}) is None
        assert delta_transform.getLaadKey('Artefact', {'artefactsoort': 'Glas'}) is None

    def test_vul_laad_key_in_de_load(self):
        doc = {'key': float('nan'), 'brondata': [bronrij(tabel='magazijnlijst', mdbfile=MAGAZIJN, ID=3)]}
        assert load.vulLaadKey('Plaatsing', doc)['key'] == 'bron:magazijnlijst/MAGAZIJN.mdb:magazijnlijst:3'
        assert load.vulLaadKey('Spoor', {'key': 'S1'})['key'] == 'S1'
        assert load.vulArtefactKey({'key_subnr': 'PSY001P1V1A1', 'artefactsoort': 'Glas'})['key'] == 'PSY001P1V1A1|Glas'


@pytest.mark.unit
class TestLeesDocumentenHulpsleutel:
    """De load leest brondata mee en vult de key voor elke soort (niet alleen artefacten)."""

    class _Col:
        def __init__(self, docs):
            self.docs = docs
            self.projecties = []

        def find(self, filt, projection=None, **kwargs):
            self.projecties.append(projection)
            return [dict(d) for d in self.docs if d.get('soort') == filt.get('soort')]

    def test_plaatsing_krijgt_hulpsleutel(self, monkeypatch):
        monkeypatch.setattr(load, 'getFields', lambda col, soort: ['doosnr'])
        col = self._Col([{'_id': 1, 'soort': 'Plaatsing', 'brondata': [bronrij(tabel='magazijnlijst', mdbfile=MAGAZIJN, ID=9)]}])
        _, docs = load.leesDocumenten(col, 'Plaatsing')
        assert docs[0]['key'] == 'bron:magazijnlijst/MAGAZIJN.mdb:magazijnlijst:9'
        assert col.projecties[0]['brondata'] == 1 and col.projecties[0]['key'] == 1

    def test_bestand_leest_geen_brondata_extra(self, monkeypatch):
        monkeypatch.setattr(load, 'getFields', lambda col, soort: ['fileName'])
        col = self._Col([{'_id': 1, 'soort': 'Bestand', 'key': None}])
        _, docs = load.leesDocumenten(col, 'Bestand')
        assert docs[0]['key'] is None
        assert 'brondata' not in col.projecties[0]


@pytest.mark.unit
class TestMetaMonsterKey:
    """De key van Monster_Botanie en Monster_Schelp gebruikt het autonummer Id uit de bronrij."""

    @pytest.mark.parametrize('soort', ['Monster_Botanie', 'Monster_Schelp'])
    def test_key_valt_terug_op_brondata_id(self, soort):
        stappen = [s for s in meta.getReferenceKeysPipeline(soort) if 'key' in s.get('$addFields', {})]
        assert len(stappen) == 1
        delen = stappen[0]['$addFields']['key']['$concat']
        assert delen[0] == 'M' and delen[2] == 'ID'
        assert delen[3] == {'$toString': {'$ifNull': ['$Id', '$brondata.Id', '$brondata.ID']}}


# ============================================================
# Stabiele ID's met de bronsleutel
# ============================================================

OID = [ObjectId() for _ in range(8)]


def doc(i, key, bronsleutel, **velden):
    d = {'_id': OID[i], 'key': key, 'bronsleutel': bronsleutel}
    d.update(velden)
    return d


@pytest.mark.unit
class TestStabieleIdsMetBronsleutel:
    """bepaalStabieleIds met bronsleutels, na een nieuwe extractie (alle _id's nieuw)."""

    def test_dubbele_key_terug_op_bronsleutel(self):
        """Twee standplaatsen met dezelfde key houden elk hun eigen nummer, ook in omgekeerde volgorde."""
        pg = [{'primary_key': 10, '_id': 'x', 'key': 'SA', 'bronsleutel': 'm:1'},
              {'primary_key': 11, '_id': 'y', 'key': 'SA', 'bronsleutel': 'm:2'}]
        for volgorde in ([0, 1], [1, 0]):
            docs = [[doc(0, 'SA', 'm:1'), doc(1, 'SA', 'm:2')][i] for i in volgorde]
            toewijzing, tellingen = delta_transform.bepaalStabieleIds(docs, pg)
            assert dict(toewijzing) == {OID[0]: 10, OID[1]: 11}
            assert tellingen['op_bronsleutel'] == 2 and tellingen['nieuw'] == 0

    def test_nieuwe_dubbele_key_kiest_op_bronsleutel_niet_op_volgorde(self):
        """Een key die uniek was komt er een tweede keer bij: het bestaande document houdt zijn nummer."""
        pg = [{'primary_key': 5, '_id': 'x', 'key': 'PSY001P1V1A1|Glas', 'bronsleutel': 'b:oud'}]
        docs = [doc(0, 'PSY001P1V1A1|Glas', 'b:nieuw'), doc(1, 'PSY001P1V1A1|Glas', 'b:oud')]
        toewijzing, tellingen = delta_transform.bepaalStabieleIds(docs, pg)
        assert dict(toewijzing) == {OID[1]: 5, OID[0]: 6}
        assert tellingen['op_key'] == 0 and tellingen['op_bronsleutel'] == 1

    def test_unieke_key_heeft_voorrang_op_bronsleutel(self):
        """Een document met een unieke key koppelt op die key, ook als zijn bronsleutel bij een andere rij hoort."""
        pg = [{'primary_key': 1, '_id': 'x', 'key': 'K1', 'bronsleutel': 'b:2'},
              {'primary_key': 2, '_id': 'y', 'key': 'K2', 'bronsleutel': 'b:1'}]
        toewijzing, tellingen = delta_transform.bepaalStabieleIds([doc(0, 'K1', 'b:1'), doc(1, 'K2', 'b:2')], pg)
        assert dict(toewijzing) == {OID[0]: 1, OID[1]: 2}
        assert tellingen['op_key'] == 2

    def test_overgang_rij_zonder_key_op_bronsleutel(self):
        """Rijen geladen vóór de hulpsleutel hebben geen key; de bronsleutel komt uit de kolom brondata."""
        pg = [{'primary_key': 30, '_id': 'x', 'key': None}, {'primary_key': 31, '_id': 'y', 'key': None},
              {'primary_key': 32, '_id': 'z', 'key': 'P1|Glas'}]
        gelezen = []

        def lees(pks):
            gelezen.append(sorted(pks))
            return {30: 'b:1', 31: 'b:2'}

        docs = [doc(0, 'P1|Aardewerk|bron:b:2', 'b:2'), doc(1, 'P1|Aardewerk|bron:b:1', 'b:1'), doc(2, 'P1|Glas', 'b:3')]
        toewijzing, tellingen = delta_transform.bepaalStabieleIds(docs, pg, lees)
        assert dict(toewijzing) == {OID[0]: 31, OID[1]: 30, OID[2]: 32}
        assert gelezen == [[30, 31]], "Alleen de rijen die na de unieke key nog vrij zijn worden gelezen"
        assert tellingen['op_key'] == 1 and tellingen['op_bronsleutel_overgang'] == 2

    def test_bronsleutels_niet_gelezen_als_alles_al_gekoppeld_is(self):
        def lees(pks):
            raise AssertionError('niet nodig')

        pg = [{'primary_key': 1, '_id': 'x', 'key': 'K1'}]
        toewijzing, _ = delta_transform.bepaalStabieleIds([doc(0, 'K1', 'b:1')], pg, lees)
        assert dict(toewijzing) == {OID[0]: 1}

    def test_identieke_bronrijen_paarsgewijs(self):
        """Een tabel zonder autonummer met drie gelijke rijen: de nummers blijven, één komt erbij."""
        pg = [{'primary_key': p, '_id': str(p), 'key': 'P1|Aardewerk|bron:t:#h', 'bronsleutel': 't:#h'} for p in (7, 8)]
        docs = [doc(i, 'P1|Aardewerk|bron:t:#h', 't:#h') for i in range(3)]
        toewijzing, tellingen = delta_transform.bepaalStabieleIds(docs, pg)
        assert sorted(pk for _, pk in toewijzing) == [7, 8, 9]
        assert tellingen['op_bronsleutel'] == 2 and tellingen['nieuw'] == 1

    def test_een_bronrij_met_twee_artefactsoorten(self):
        """Dezelfde bronrij als Aardewerk en als Glas: koppelen op bronsleutel én key houdt ze uit elkaar."""
        pg = [{'primary_key': 1, '_id': 'x', 'key': 'A', 'bronsleutel': 'b:1'},
              {'primary_key': 2, '_id': 'y', 'key': 'A', 'bronsleutel': 'b:2'},
              {'primary_key': 3, '_id': 'z', 'key': 'G', 'bronsleutel': 'b:1'},
              {'primary_key': 4, '_id': 'w', 'key': 'G', 'bronsleutel': 'b:2'}]
        docs = [doc(0, 'G', 'b:1'), doc(1, 'A', 'b:2'), doc(2, 'A', 'b:1'), doc(3, 'G', 'b:2')]
        toewijzing, _ = delta_transform.bepaalStabieleIds(docs, pg)
        assert dict(toewijzing) == {OID[0]: 3, OID[1]: 2, OID[2]: 1, OID[3]: 4}

    def test_overgang_twee_artefactsoorten_zonder_key_niet_gekoppeld(self):
        """Zonder key in PostgreSQL is niet te zeggen welke rij welke artefactsoort was: nieuwe nummers."""
        pg = [{'primary_key': 1, '_id': 'x', 'key': None, 'bronsleutel': 'b:1'},
              {'primary_key': 2, '_id': 'y', 'key': None, 'bronsleutel': 'b:1'}]
        docs = [doc(0, 'P|Glas|bron:b:1', 'b:1'), doc(1, 'P|Aardewerk|bron:b:1', 'b:1')]
        toewijzing, tellingen = delta_transform.bepaalStabieleIds(docs, pg)
        assert sorted(pk for _, pk in toewijzing) == [3, 4] and tellingen['nieuw'] == 2

    def test_rest_valt_terug_op_unieke_key(self):
        """Gewijzigde bronrij bij een dubbele key in de documenten: de regel van vóór issue 81."""
        pg = [{'primary_key': 5, '_id': 'x', 'key': 'K', 'bronsleutel': 'b:oud'}]
        docs = [doc(0, 'K', 'b:x'), doc(1, 'K', 'b:y')]
        toewijzing, tellingen = delta_transform.bepaalStabieleIds(docs, pg)
        assert dict(toewijzing) == {OID[0]: 5, OID[1]: 6}
        assert tellingen['op_key'] == 1 and tellingen['op_bronsleutel'] == 0

    def test_verdwenen_bronrij_geeft_nieuw_nummer_voor_samengevoegd_document_met_dubbele_key(self):
        """Een samengevoegd document waarvan een bronrij verdwijnt heeft een andere bronsleutel."""
        pg = [{'primary_key': 1, '_id': 'x', 'key': 'K', 'bronsleutel': 'b:1;b:2'},
              {'primary_key': 2, '_id': 'y', 'key': 'K', 'bronsleutel': 'b:3'}]
        docs = [doc(0, 'K', 'b:1'), doc(1, 'K', 'b:3')]
        toewijzing, _ = delta_transform.bepaalStabieleIds(docs, pg)
        assert dict(toewijzing) == {OID[0]: 3, OID[1]: 2}


# ============================================================
# Met nagebootste PostgreSQL en MongoDB
# ============================================================

class NepCursor:
    """Nagebootste psycopg2-cursor voor leesPgBronsleutels."""

    def __init__(self, rijen, met_kolom=True):
        self.rijen = rijen
        self.met_kolom = met_kolom
        self.statements = []
        self._uitkomst = []

    def execute(self, sql, params=None):
        self.statements.append((sql, params))
        if 'information_schema' in sql:
            self._uitkomst = [('brondata',)] if self.met_kolom else []
        else:
            gevraagd = set(params[0])
            self._uitkomst = [(pk, tekst) for pk, tekst in self.rijen if pk in gevraagd]

    def fetchall(self):
        return self._uitkomst


@pytest.mark.unit
class TestLeesPgBronsleutels:

    def test_leest_alleen_gevraagde_rijen_in_batches(self, monkeypatch):
        monkeypatch.setattr(delta_transform, 'BATCH_GROOTTE', 2)
        rijen = [(1, str([bronrij(ID=1)])), (2, str([bronrij(ID=2)])), (3, 'onleesbaar'), (4, None),
                 (5, str({'table': 'generated_put'}))]
        cursor = NepCursor(rijen)
        sleutels = delta_transform.leesPgBronsleutels('Def_Artefact', [5, 4, 3, 2, 1, 1], cursor)
        assert sleutels == {1: f'{DB34_RELATIEF}:AW1DeterminatiesJohan:1', 2: f'{DB34_RELATIEF}:AW1DeterminatiesJohan:2'}
        selects = [p for s, p in cursor.statements if 'ANY' in s]
        assert selects == [([1, 2],), ([3, 4],), ([5],)]

    def test_tabel_zonder_brondata_of_zonder_rijen(self):
        assert delta_transform.leesPgBronsleutels('Def_X', [1], NepCursor([], met_kolom=False)) == {}
        cursor = NepCursor([])
        assert delta_transform.leesPgBronsleutels('Def_X', [], cursor) == {} and cursor.statements == []


@pytest.fixture
def nep_client(monkeypatch):
    client = UitgebreideClient()
    monkeypatch.setattr(nep_mongo, 'matcht', matchtMetRegex)
    monkeypatch.setattr(verwerkingsrun, '_getClient', lambda: client)
    monkeypatch.setattr(delta_transform, '_getClient', lambda: client)
    return client


@pytest.mark.unit
class TestSetStabielePrimaryKeysMetBronsleutel:
    """setStabielePrimaryKeys na een volledige extractie: rijen zonder (unieke) key houden hun nummer."""

    def test_plaatsingen_en_dubbele_standplaatsen(self, nep_client, monkeypatch):
        col = nep_client['Arch_Analyse']['Single_Store_Clean']
        plaats = lambda i: [bronrij(tabel='magazijnlijst', mdbfile=MAGAZIJN, ID=i, STELLING='A')]
        col.insert_many([
            {'_id': OID[0], 'soort': 'Plaatsing', 'brondata': plaats(1)},
            {'_id': OID[1], 'soort': 'Plaatsing', 'brondata': plaats(2)},
        ])
        # Na de load van vóór issue 81: geen key; de bronsleutel komt uit de kolom brondata
        monkeypatch.setattr(delta_transform, 'leesPgSleutels', lambda tabel: [
            {'primary_key': 40, '_id': 'oud1', 'key': None}, {'primary_key': 41, '_id': 'oud2', 'key': None}])
        monkeypatch.setattr(delta_transform, 'leesPgBronsleutels', lambda tabel, pks: {
            40: 'magazijnlijst/MAGAZIJN.mdb:magazijnlijst:2', 41: 'magazijnlijst/MAGAZIJN.mdb:magazijnlijst:1'})
        verwerkingsrun.startRun('incrementeel')
        assert delta_transform.setStabielePrimaryKeys('Plaatsing', col) is True
        ids = {d['_id']: d['ID'] for d in col.find({})}
        assert ids == {OID[0]: 41, OID[1]: 40}
        # Alleen ID wordt geschreven; key en bronsleutel blijven in het geheugen
        assert all(set(d) == {'_id', 'soort', 'brondata', 'ID'} for d in col.find({}))
        telling = verwerkingsrun.huidigeRun()['tellingen']['transform']['primary_keys']['Plaatsing']
        assert telling['op_bronsleutel_overgang'] == 2 and telling['nieuw'] == 0

    def test_artefact_zonder_subnr_op_leesbare_key(self, nep_client, monkeypatch):
        col = nep_client['Arch_Analyse']['Single_Store_Clean']
        col.insert_many([{'_id': OID[0], 'soort': 'Artefact', 'projectcd': 'DB034', 'vondstnr': 460.0,
                          'artefactsoort': 'Aardewerk', 'brondata': [bronrij(ID=4)]}])
        key = f'PDB034V460|Aardewerk|bron:{DB34_RELATIEF}:AW1DeterminatiesJohan:4'
        monkeypatch.setattr(delta_transform, 'leesPgSleutels', lambda tabel: [{'primary_key': 9, '_id': 'oud', 'key': key}])
        monkeypatch.setattr(delta_transform, 'leesPgBronsleutels', lambda tabel, pks: pytest.fail('niet nodig'))
        verwerkingsrun.startRun('incrementeel')
        assert delta_transform.setStabielePrimaryKeys('Artefact', col) is True
        assert col.find_one({'_id': OID[0]})['ID'] == 9

    def test_soort_zonder_tabel_leest_geen_brondata(self, nep_client, monkeypatch):
        col = nep_client['Arch_Analyse']['Single_Store_Clean']
        col.insert_many([{'_id': OID[0], 'soort': 'Fotokoppel', 'brondata': [bronrij(ID=1)]}])
        monkeypatch.setattr(delta_transform, 'leesPgBronsleutels', lambda tabel, pks: pytest.fail('geen tabel'))
        verwerkingsrun.startRun('incrementeel')
        assert delta_transform.setStabielePrimaryKeys('Fotokoppel', col) is True
        assert col.find_one({'_id': OID[0]})['ID'] == 0


# ============================================================
# Issue 88: echte brondata-teksten, vervangende keys
# ============================================================

FIXTURE_BRONDATA = json.load(open(os.path.join(os.path.dirname(__file__), 'fixtures', 'brondata_delft.json'),
                                  encoding='utf-8'))['teksten']


@pytest.mark.unit
class TestLeesBrondataTekstProductie:
    """leesBrondataTekst op echte teksten uit de kolom brondata van de Delftse productie-installatie.

    De teksten komen uit de backup van 22 oktober 2026 (tests/unit/fixtures/brondata_delft.json).
    Op die backup en op de tabellen na de cyclus van 29 oktober gaf de parser voor geen enkele rij
    None; de hernummering van issue 88 kwam niet van de parser.
    """

    @pytest.mark.parametrize('fixture', FIXTURE_BRONDATA, ids=[f['naam'] for f in FIXTURE_BRONDATA])
    def test_echte_tekst_geeft_de_bronsleutel(self, fixture):
        bronrijen = delta_transform.leesBrondataTekst(fixture['tekst'])
        assert isinstance(bronrijen, list) and len(bronrijen) == fixture['aantal_bronrijen']
        assert delta_transform.getBronsleutel(bronrijen) == fixture['bronsleutel']

    @pytest.mark.parametrize('fixture', FIXTURE_BRONDATA, ids=[f['naam'] for f in FIXTURE_BRONDATA])
    def test_rondgang_via_str_is_stabiel(self, fixture):
        """Wat de load opnieuw schrijft (str van de teruggelezen rijen) geeft dezelfde bronsleutel."""
        bronrijen = delta_transform.leesBrondataTekst(fixture['tekst'])
        opnieuw = delta_transform.leesBrondataTekst(str(bronrijen))
        assert delta_transform.getBronsleutel(opnieuw) == fixture['bronsleutel']

    def test_alle_soorten_waarden_uit_de_fixture(self):
        """De fixture dekt nan, False, een backslash, aanhalingstekens, \\r en een regeleinde."""
        teksten = ' '.join(f['tekst'] for f in FIXTURE_BRONDATA)
        for teken in (': nan', ': False', '\\\\', '\\r', '\\n', "\"", 'ObjectId('):
            assert teken in teksten, teken

    def test_lange_samengevoegde_tekst(self):
        """Het grootste samengevoegde document op productie had 81.909 tekens (Def_Vondst)."""
        rijen = [bronrij(tabel='VONDSTENLIJST', ID=i, INHOUD='aw, bot', OPMERKING="o'k \"x\"\n" * 5) for i in range(600)]
        tekst = str(rijen)
        assert len(tekst) > 80000
        assert delta_transform.getBronsleutel(delta_transform.leesBrondataTekst(tekst)) == \
            delta_transform.getBronsleutel(rijen)

    @pytest.mark.parametrize('waarde', [
        Decimal128('12.50'), decimal.Decimal('3.14'), datetime.datetime(2003, 5, 5, 0, 0),
        float('nan'), {'genest': {'lijst': [1, 'twee', None, True], 'getal': -2.5}}, [1, [2, [3]]],
        BsonTimestamp(1700000000, 1),
    ], ids=['Decimal128', 'Decimal', 'datetime', 'nan', 'geneste_dict', 'geneste_lijst', 'bson_Timestamp'])
    def test_bijzondere_waarden_zonder_autonummer(self, waarde):
        """Zonder autonummer hangt de hash van de inhoud af: teruggelezen moet die hetzelfde zijn."""
        brondata = [bronrij(tabel='ARTF_GLS', VELD=waarde, ANDER='x')]
        terug = delta_transform.leesBrondataTekst(str(brondata))
        assert terug is not None
        assert delta_transform.getBronsleutel(terug) == delta_transform.getBronsleutel(brondata)

    def test_pandas_timestamp_als_tekst(self):
        terug = delta_transform.leesBrondataTekst("[{'d': Timestamp('2020-01-02 03:04:05')}]")
        assert terug == [{'d': datetime.datetime(2020, 1, 2, 3, 4, 5)}]

    @pytest.mark.parametrize('tekst', ["[{'a': Decimal128('geen getal')}]", "[{'a': Timestamp('morgen')}]"])
    def test_onleesbare_bijzondere_waarde_geeft_none(self, tekst):
        assert delta_transform.leesBrondataTekst(tekst) is None


@pytest.mark.unit
class TestVervangendeKeys:
    """getVervangendeKeys: keys waarmee een document geladen kan zijn toen zijn natuurlijke key ontbrak."""

    def test_standplaats_met_natuurlijke_key(self):
        doc = {'key': 'SAV1L2'}
        assert delta_transform.getVervangendeKeys('Standplaats', doc, 'm:1') == ['bron:m:1']

    def test_zonder_natuurlijke_key_geen_vervanging(self):
        """De laadkey is dan zelf de hulpsleutel-key."""
        assert delta_transform.getVervangendeKeys('Plaatsing', {}, 'm:1') == []

    def test_artefact_met_natuurlijke_key(self):
        doc = {'key': 'PDC024V32A14S0', 'key_subnr': 'PDC024V32A0S0', 'artefactsoort': 'Glas',
               'projectcd': 'DC024', 'vondstnr': 32.0}
        assert delta_transform.getVervangendeKeys('Artefact', doc, 'g:#1') == [
            'PDC024V32|Glas|bron:g:#1', 'PDC024V32A0S0|Glas']

    def test_artefact_met_alleen_key_subnr(self):
        doc = {'key_subnr': 'PDC024V32A0S0', 'artefactsoort': 'Glas', 'projectcd': 'DC024', 'vondstnr': 32.0}
        assert delta_transform.getVervangendeKeys('Artefact', doc, 'g:#1') == ['PDC024V32|Glas|bron:g:#1']

    @pytest.mark.parametrize('soort', ['Bestand', 'Foto', 'ABR'])
    def test_geen_vervanging_voor_bestanden_en_abr(self, soort):
        assert delta_transform.getVervangendeKeys(soort, {'key': 'K'}, 'b:1') == []

    def test_zonder_bronsleutel_geen_vervanging(self):
        assert delta_transform.getVervangendeKeys('Spoor', {'key': 'K'}, None) == []

    def test_hulpsleutel_key_herkennen(self):
        assert delta_transform.isHulpsleutelKey('bron:m:1')
        assert delta_transform.isHulpsleutelKey('PDB034V460|Aardewerk|bron:x:4')
        assert not delta_transform.isHulpsleutelKey('PDB034V460A1|Glas')
        assert not delta_transform.isHulpsleutelKey(None)


def docV(i, key, bronsleutel, vervangend=(), **velden):
    d = doc(i, key, bronsleutel, vervangende_keys=list(vervangend))
    d.update(velden)
    return d


@pytest.mark.unit
class TestStabieleIdsMetVervangendeKey:
    """bepaalStabieleIds stap 3b (issue 88): rijen die met een vervangende key zijn geladen."""

    def test_standplaats_krijgt_natuurlijke_key_terug(self):
        """29 oktober: de key ontbrak, de load schreef bron:<bronsleutel>; nu is de key er weer."""
        pg = [{'primary_key': 50, '_id': 'x', 'key': 'bron:m:1'}, {'primary_key': 51, '_id': 'y', 'key': 'bron:m:2'},
              {'primary_key': 52, '_id': 'z', 'key': 'SA', 'bronsleutel': 'm:3'}]
        docs = [docV(0, 'SA', 'm:2', ['bron:m:2']), docV(1, 'SA', 'm:1', ['bron:m:1']), docV(2, 'SA', 'm:3', ['bron:m:3'])]
        toewijzing, tellingen = delta_transform.bepaalStabieleIds(docs, pg, lambda pks: pytest.fail('niet nodig'))
        assert dict(toewijzing) == {OID[0]: 51, OID[1]: 50, OID[2]: 52}
        assert tellingen['op_vervangende_key'] == 2 and tellingen['op_bronsleutel'] == 1 and tellingen['nieuw'] == 0

    def test_eigen_rij_gaat_voor_gegenereerde_rij_met_dezelfde_key(self):
        """Een spoor zonder key liet Transform 5 een spoor genereren; het echte spoor houdt zijn eigen nummer."""
        pg = [{'primary_key': 5, '_id': 'x', 'key': 'bron:s:1'}, {'primary_key': 9, '_id': 'y', 'key': 'PDB034P1S1'}]
        toewijzing, tellingen = delta_transform.bepaalStabieleIds([docV(0, 'PDB034P1S1', 's:1', ['bron:s:1'])], pg)
        assert dict(toewijzing) == {OID[0]: 5}
        assert tellingen['op_vervangende_key'] == 1 and tellingen['op_key'] == 0

    def test_artefact_op_key_subnr_en_bronsleutel(self):
        """Twee artefacten met dezelfde key_subnr|artefactsoort in PostgreSQL: de bronsleutel beslist."""
        pg = [{'primary_key': 25113, '_id': 'x', 'key': 'PDC024V32A0S0|Glas'},
              {'primary_key': 25114, '_id': 'y', 'key': 'PDC024V32A0S0|Glas'},
              {'primary_key': 7, '_id': 'z', 'key': 'PDC024V31A0S0|Glas'}]
        gelezen = []

        def lees(pks):
            gelezen.append(sorted(pks))
            return {25113: 'g:#b', 25114: 'g:#a', 7: 'g:#c'}

        docs = [docV(0, 'PDC024V32A14S0', 'g:#a', ['PDC024V32|Glas|bron:g:#a', 'PDC024V32A0S0|Glas']),
                docV(1, 'PDC024V32A15S0', 'g:#b', ['PDC024V32|Glas|bron:g:#b', 'PDC024V32A0S0|Glas'])]
        toewijzing, tellingen = delta_transform.bepaalStabieleIds(docs, pg, lees)
        assert dict(toewijzing) == {OID[0]: 25114, OID[1]: 25113}
        assert gelezen[0] == [25113, 25114], "Alleen de rijen met een vervangende key worden gelezen"
        assert tellingen['op_vervangende_key'] == 2

    def test_vervangende_key_neemt_geen_rij_van_een_ander_artefact(self):
        """Een artefact zonder artefactnr heeft key_subnr|artefactsoort als natuurlijke key: andere bronsleutel."""
        pg = [{'primary_key': 3, '_id': 'x', 'key': 'S|Glas', 'bronsleutel': 'b:2'},
              {'primary_key': 4, '_id': 'y', 'key': 'K'}]
        docs = [docV(0, 'K', 'b:1', ['P|Glas|bron:b:1', 'S|Glas']), docV(1, 'S|Glas', 'b:2', ['P|Glas|bron:b:2'])]
        toewijzing, tellingen = delta_transform.bepaalStabieleIds(docs, pg)
        assert dict(toewijzing) == {OID[0]: 4, OID[1]: 3}
        assert tellingen['op_vervangende_key'] == 0 and tellingen['op_key'] == 2

    def test_monster_krijgt_key_met_autonummer(self):
        """Na issue 81 kreeg Monster_Botanie de key M<monstercd>ID<Id>; eerder geladen als bron:<bronsleutel>."""
        pg = [{'primary_key': 0, '_id': 'x', 'key': 'bron:mon:1'}]
        toewijzing, _ = delta_transform.bepaalStabieleIds([docV(0, 'MALT_p62_v26ID1', 'mon:1', ['bron:mon:1'])], pg)
        assert dict(toewijzing) == {OID[0]: 0}

    def test_identieke_rijen_paarsgewijs_op_vervangende_key(self):
        pg = [{'primary_key': p, '_id': str(p), 'key': 'bron:t:#h'} for p in (7, 8)]
        docs = [docV(i, 'PDC024P1S1', 't:#h', ['bron:t:#h']) for i in range(2)]
        toewijzing, tellingen = delta_transform.bepaalStabieleIds(docs, pg)
        assert sorted(pk for _, pk in toewijzing) == [7, 8] and tellingen['op_vervangende_key'] == 2

    def test_verloren_key_wordt_gemeld(self):
        """Ontbreekt de natuurlijke key (zoals op 29 oktober), dan een nieuw nummer en een telling met voorbeeld."""
        pg = [{'primary_key': 10, '_id': 'x', 'key': 'SA', 'bronsleutel': 'm:1'},
              {'primary_key': 11, '_id': 'y', 'key': 'SA', 'bronsleutel': 'm:2'}]
        docs = [docV(0, 'bron:m:1', 'm:1'), docV(1, 'SA', 'm:2', ['bron:m:2'])]
        toewijzing, tellingen = delta_transform.bepaalStabieleIds(docs, pg)
        assert dict(toewijzing) == {OID[0]: 12, OID[1]: 11}
        assert tellingen['nieuw'] == 1 and tellingen['nieuw_bronrij_bekend'] == 1
        assert tellingen['voorbeelden'] == [{'key': 'bron:m:1', 'primary_key': 10, 'key_in_tabel': 'SA'}]

    def test_geen_melding_bij_stabiele_sleutels(self):
        pg = [{'primary_key': 10, '_id': 'x', 'key': 'SA', 'bronsleutel': 'm:1'}]
        _, tellingen = delta_transform.bepaalStabieleIds([docV(0, 'SA', 'm:1', ['bron:m:1'])], pg)
        assert tellingen['nieuw_bronrij_bekend'] == 0 and 'voorbeelden' not in tellingen
