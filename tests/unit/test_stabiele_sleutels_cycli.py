"""
Simulatie van opeenvolgende volledige cycli met productie-achtige data (issue 88).

Bootst na wat Transform 4 (setStabielePrimaryKeys) en de load (vulLaadKey en
str(brondata) in transformRow) met de sleutels doen, over meer cycli, met
documenten zoals op de Delftse productie-installatie:

- standplaatsen met dezelfde key (meer dozen op één plek), een standplaats
  zonder key en een uit de tabel doosnr zonder autonummer;
- stellingen (tabel zonder autonummer, unieke key);
- sporen met dezelfde key uit twee tabellen en een samengevoegd spoor met
  twee bronrijen; vullingen met dezelfde key;
- artefacten met een natuurlijke key (artefactnr), met alleen key_subnr en
  zonder subnr;
- monsters met de key M<monstercd>ID<Id>;
- brondata met Decimal128, Decimal, datetime, nan en geneste waarden.

Scenario's:

1. Cyclus 0 zoals op 22 oktober (alle keys aanwezig), cyclus 1 zoals op 29
   oktober (de keys van standplaatsen, sporen, vullingen en artefacten met
   artefactnr verloren in Transform 3, de stellingen verdwenen), cyclus 2 en
   3 met de fix: in cyclus 2 en 3 houdt elke rij zijn nummer, de stellingen
   krijgen hun nummers van cyclus 0 terug, en geen enkele rij is hernummerd.
2. Een eerste load zonder hulpsleutel (vóór issue 81: lege key voor rijen
   zonder natuurlijke key), daarna twee cycli: 0 hernummerde rijen.
3. Issue 89: de artefactsoort van een artefact zonder natuurlijke key wisselt
   tussen cycli (de tabel AW1DeterminatiesJohan werd afwisselend door
   Aardewerk en door Artefact geharmoniseerd), en het vondstnummer in de
   bronrij wordt gecorrigeerd: elke rij houdt zijn nummer, 0 nieuw en 0
   hernummerd, en de load schrijft telkens de nieuwe key.
"""
import copy
import datetime
import decimal
import sys
import types

import pytest
from bson import ObjectId
from bson.decimal128 import Decimal128

# Mock shared.image_util (wordt via bronbestanden/opruimen geïmporteerd door image_import.py)
if "shared.image_util" not in sys.modules:
    sys.modules["shared.image_util"] = types.ModuleType("shared.image_util")

import wasstraat.delta_transform as delta_transform
import wasstraat.loadToDatabase_functions as load
import wasstraat.verwerkingsrun as verwerkingsrun
from tests.unit import nep_mongo
from tests.unit.test_bronsleutel import NepCursor
from tests.unit.test_delta_transform import UitgebreideClient, matchtMetRegex


MAGAZIJN = '/input/magazijnlijst/MAGAZIJN.mdb'
DB34 = '/input/projecten/DB034_Koningsveld IV/C Database/opgravingDB34.mdb'
DC24 = '/input/projecten/DC024_Stadskantoor/C Database/DC24_STADSKANTOOR.mdb'
MONSTERS = '/input/monsterdatabase/MONSTERS.accdb'
SOORTEN = ['Standplaats', 'Stelling', 'Spoor', 'Vulling', 'Artefact', 'Monster_Botanie']
# Soorten waarvan de key in de cyclus van 29 oktober verloren ging (Transform 3)
KEY_KWIJT = ['Standplaats', 'Spoor', 'Vulling', 'Artefact']


def rij(tabel, mdbfile, **velden):
    """Een bronrij zoals importMDB.sh hem in de staging zet; _id en loadtime zijn per extractie nieuw."""
    r = {'_id': ObjectId(), 'table': tabel, 'projectcd': 'X', 'bron': 'opgravingX',
         'loadtime': datetime.datetime.now().isoformat(), 'mdbfile': mdbfile}
    r.update(velden)
    return r


def documenten():
    """De documenten van Single_Store_Clean na Transform 5, zoals bij een nieuwe extractie (nieuwe _id's)."""
    nested = {'maten': {'lengte': Decimal128('12.50'), 'eenheid': 'cm'}, 'codes': [1, 'b', None]}
    docs = [
        # Standplaatsen: twee dozen op dezelfde plek, een unieke, een uit doosnr zonder autonummer, een zonder key
        {'soort': 'Standplaats', 'key': 'SAV1L1', 'brondata': [rij('magazijnlijst', MAGAZIJN, ID=1, STELLING='A', VAKNO=1)]},
        {'soort': 'Standplaats', 'key': 'SAV1L1', 'brondata': [rij('magazijnlijst', MAGAZIJN, ID=2, STELLING='A', VAKNO=1)]},
        {'soort': 'Standplaats', 'key': 'SBV2', 'brondata': [rij('magazijnlijst', MAGAZIJN, ID=3, STELLING='B', VAKNO=2,
                                                              PRIJS=decimal.Decimal('4.20'))]},
        {'soort': 'Standplaats', 'key': 'SH', 'brondata': [rij('doosnr', MAGAZIJN, CODE='DB04', DOOSNO=506, UIT=0.0,
                                                            STELLING='H', INHOUD='Bot sus, "gedet",', extra=nested)]},
        {'soort': 'Standplaats', 'brondata': [rij('magazijnlijst', MAGAZIJN, ID=5, UIT=float('nan'))]},
        # Stellingen: tabel zonder autonummer
        {'soort': 'Stelling', 'key': 'SA', 'brondata': rij('stellingen', MAGAZIJN, stelling='A', inhoud='AARDEWERK')},
        {'soort': 'Stelling', 'key': 'SB', 'brondata': rij('stellingen', MAGAZIJN, stelling='B', inhoud='GLAS')},
        # Sporen: dezelfde key uit SPOREN en Sporen2, een samengevoegd spoor met twee bronrijen
        {'soort': 'Spoor', 'key': 'PDB034P10S1', 'brondata': [rij('SPOREN', DB34, ID=248, PUTNO=10, SPOORNO=1,
                                                                   DATUM=datetime.datetime(2003, 5, 5))]},
        {'soort': 'Spoor', 'key': 'PDB034P10S1', 'brondata': [rij('Sporen2', DB34, PUTNO=10, SPOORNO=1, HB='68 ÷ NAP',
                                                                   LB=Decimal128('300.0'))]},
        {'soort': 'Spoor', 'key': 'PDB034P10S2', 'brondata_count': 2,
         'brondata': [rij('SPOREN', DB34, ID=249, PUTNO=10, SPOORNO=2), rij('SPOOR', DC24, SPOOR=2, PUT=10, DIEPTE=0)]},
        # Vullingen met dezelfde key
        {'soort': 'Vulling', 'key': 'PDB034P10S1V0', 'brondata': [rij('VULLINGEN', DB34, ID=295, VULLINGNO=0)]},
        {'soort': 'Vulling', 'key': 'PDB034P10S1V0', 'brondata': [rij('VULLING', DC24, VULLING=0, nan_veld=float('nan'))]},
        # Artefacten: met artefactnr (natuurlijke key), alleen key_subnr, zonder subnr
        {'soort': 'Artefact', 'key': 'PDC024V32A14S0', 'key_subnr': 'PDC024V32A0S0', 'artefactsoort': 'Glas',
         'projectcd': 'DC024', 'vondstnr': 32.0,
         'brondata': [rij('ARTF_GLS', DC24, ARTEFACT=14, SUBNO=0, GEWICHT=0.0, RANDDIA=Decimal128('7.5'))]},
        {'soort': 'Artefact', 'key': 'PDC024V32A15S0', 'key_subnr': 'PDC024V32A0S0', 'artefactsoort': 'Glas',
         'projectcd': 'DC024', 'vondstnr': 32.0, 'brondata': [rij('ARTF_GLS', DC24, ARTEFACT=15, SUBNO=0, extra=nested)]},
        {'soort': 'Artefact', 'key_subnr': 'PDB034P10V460A1', 'artefactsoort': 'Aardewerk', 'projectcd': 'DB034',
         'putnr': 10.0, 'vondstnr': 460.0, 'brondata': [rij('AARDEWERK 1', DB34, ID=4, SUBNO=1)]},
        {'soort': 'Artefact', 'artefactsoort': 'Aardewerk', 'projectcd': 'DB034', 'putnr': 10.0, 'vondstnr': 460.0,
         'brondata': [rij('AW1DeterminatiesJohan', DB34, ID=4, DATUM=datetime.datetime(2011, 10, 25))]},
        # Monsters
        {'soort': 'Monster_Botanie', 'key': 'MALT_p62_v26ID1', 'brondata': [rij('Monster_botanie_determinatie', MONSTERS,
                                                                               Id=1, AANTAL=50, SOORT='ATRIPP/P')]},
    ]
    for d in docs:
        d['_id'] = ObjectId()
    return docs


def zonderKey(doc):
    """Het document zoals Transform 3 het op 29 oktober achterliet: zonder natuurlijke key."""
    doc = copy.deepcopy(doc)
    doc.pop('key', None)
    return doc


@pytest.fixture
def omgeving(monkeypatch):
    """Nagebootste MongoDB en PostgreSQL; PostgreSQL bevat per tabel de rijen van de vorige load."""
    client = UitgebreideClient()
    monkeypatch.setattr(nep_mongo, 'matcht', matchtMetRegex)
    monkeypatch.setattr(verwerkingsrun, '_getClient', lambda: client)
    monkeypatch.setattr(delta_transform, '_getClient', lambda: client)
    pg = {delta_transform.getTabelVoorSoort(s): [] for s in SOORTEN}
    origineel = delta_transform.leesPgBronsleutels
    monkeypatch.setattr(delta_transform, 'leesPgSleutels',
                        lambda tabel, cursor=None: [{k: r[k] for k in ('primary_key', '_id', 'key')} for r in pg[tabel]])
    monkeypatch.setattr(delta_transform, 'leesPgBronsleutels', lambda tabel, pks, cursor=None: origineel(
        tabel, pks, NepCursor([(r['primary_key'], r['brondata']) for r in pg[tabel]])))
    return types.SimpleNamespace(client=client, pg=pg)


def cyclus(omgeving, docs, oude_load=False):
    """Transform 4 en de load van één volledige cyclus.

    Args:
        omgeving: fixture
        docs: documenten van Single_Store_Clean (zonder ID)
        oude_load: als True de load van vóór issue 81 (lege key voor rijen zonder natuurlijke key)

    Returns:
        Tuple (dict soort -> tellingen van Transform 4, dict tabel -> {primary_key: (key, bronsleutel)})
    """
    col = omgeving.client['Arch_Analyse']['Single_Store_Clean']
    col.drop()
    col.insert_many(copy.deepcopy(docs))
    tellingen = {}
    for soort in SOORTEN:
        if col.count_documents({'soort': soort}):
            assert delta_transform.setStabielePrimaryKeys(soort, col) is True
            tellingen[soort] = verwerkingsrun.huidigeRun()['tellingen']['transform']['primary_keys'][soort]
    # De load: key zoals vulLaadKey, brondata als str() zoals transformRow
    for soort in SOORTEN:
        tabel = delta_transform.getTabelVoorSoort(soort)
        rijen = []
        for doc in col.find({'soort': soort}):
            if oude_load:
                key = delta_transform.getArtefactKey(doc) if soort == 'Artefact' else doc.get('key')
            else:
                key = load.vulLaadKey(soort, dict(doc))['key']
            rijen.append({'primary_key': doc['ID'], '_id': str(doc['_id']), 'key': key, 'brondata': str(doc['brondata'])})
        omgeving.pg[tabel] = rijen
    tabellen = {tabel: {r['primary_key']: (r['key'], delta_transform.getBronsleutel(
        delta_transform.leesBrondataTekst(r['brondata']))) for r in rijen} for tabel, rijen in omgeving.pg.items()}
    return tellingen, tabellen


def vergelijk(voor, na):
    """Per tabel: verdwenen en nieuwe primary_keys, en hernummerde (zelfde nummer, andere key én andere bronrij)."""
    uit = {}
    for tabel in voor:
        a, b = voor[tabel], na[tabel]
        hernummerd = [pk for pk in set(a) & set(b) if a[pk][0] != b[pk][0] and a[pk][1] != b[pk][1]]
        uit[tabel] = {'verdwenen': sorted(set(a) - set(b)), 'nieuw': sorted(set(b) - set(a)), 'hernummerd': hernummerd}
    return uit


def zelfdeNummerPerBronrij(voor, na):
    """Elke bronsleutel heeft na de cyclus hetzelfde nummer als ervoor."""
    for tabel in voor:
        a = {bs: pk for pk, (_, bs) in voor[tabel].items()}
        b = {bs: pk for pk, (_, bs) in na[tabel].items()}
        assert a == b, f"{tabel}: andere nummers per bronrij"


@pytest.mark.unit
class TestCycliNaVerlorenKeys:
    """Het productiegeval van 29 oktober 2026 en de cycli daarna."""

    def test_eerste_cyclus_met_de_fix_houdt_de_nummers(self, omgeving):
        verwerkingsrun.startRun('incrementeel')
        tellingen0, pg0 = cyclus(omgeving, documenten())

        # Cyclus 1 (29 oktober): keys kwijt, stellingen verdwenen
        docs1 = [zonderKey(d) if d['soort'] in KEY_KWIJT and 'key' in d else d for d in documenten()]
        docs1 = [d for d in docs1 if d['soort'] != 'Stelling']
        tellingen1, pg1 = cyclus(omgeving, docs1)
        # Zo ging het mis: nieuwe nummers voor alle rijen waarvan de key ontbrak, nu met een melding
        assert tellingen1['Standplaats']['nieuw'] == 4 and tellingen1['Standplaats']['nieuw_bronrij_bekend'] == 4
        assert tellingen1['Spoor']['nieuw'] == 3 and tellingen1['Vulling']['nieuw'] == 2
        assert tellingen1['Artefact']['nieuw'] == 2 and tellingen1['Monster_Botanie']['nieuw'] == 0
        assert pg1['Def_Stelling'] == {}

        # Cyclus 2 (met de fix): de keys zijn er weer
        tellingen2, pg2 = cyclus(omgeving, documenten())
        assert all(t['nieuw'] == 0 for s, t in tellingen2.items() if s != 'Stelling'), tellingen2
        assert tellingen2['Standplaats']['op_vervangende_key'] == 4
        assert tellingen2['Spoor']['op_vervangende_key'] == 3 and tellingen2['Vulling']['op_vervangende_key'] == 2
        assert tellingen2['Artefact']['op_vervangende_key'] == 2
        verschil = vergelijk(pg1, pg2)
        assert all(not v['verdwenen'] and not v['hernummerd'] for t, v in verschil.items() if t != 'Def_Stelling'), verschil
        zelfdeNummerPerBronrij({t: r for t, r in pg1.items() if t != 'Def_Stelling'},
                               {t: r for t, r in pg2.items() if t != 'Def_Stelling'})
        # De stellingen krijgen in een lege tabel hun nummers van vóór 29 oktober terug (op volgorde van key)
        assert pg2['Def_Stelling'] == pg0['Def_Stelling']
        # De natuurlijke keys staan weer in PostgreSQL
        assert {k for k, _ in pg2['Def_Standplaats'].values()} == {'SAV1L1', 'SBV2', 'SH', 'bron:magazijnlijst/MAGAZIJN.mdb:magazijnlijst:5'}

        # Cyclus 3: alles stabiel, ook de keys
        tellingen3, pg3 = cyclus(omgeving, documenten())
        assert all(t['nieuw'] == 0 and t['nieuw_bronrij_bekend'] == 0 for t in tellingen3.values()), tellingen3
        assert pg3 == pg2

    def test_twee_cycli_zonder_verlies_zijn_stabiel(self, omgeving):
        verwerkingsrun.startRun('incrementeel')
        _, pg0 = cyclus(omgeving, documenten())
        tellingen1, pg1 = cyclus(omgeving, documenten())
        assert all(t['nieuw'] == 0 and t['op_vervangende_key'] == 0 for t in tellingen1.values()), tellingen1
        assert pg1 == pg0


@pytest.mark.unit
class TestCycliNaOudeLoad:
    """Een eerste load zonder hulpsleutel (vóór issue 81), daarna twee volledige cycli."""

    def test_nul_hernummerde_rijen(self, omgeving):
        verwerkingsrun.startRun('incrementeel')
        _, pg0 = cyclus(omgeving, documenten(), oude_load=True)
        assert pg0['Def_Monster_Botanie'][0][0] == 'MALT_p62_v26ID1'
        assert sum(1 for k, _ in pg0['Def_Standplaats'].values() if k is None) == 1

        tellingen1, pg1 = cyclus(omgeving, documenten())
        assert all(t['nieuw'] == 0 for t in tellingen1.values()), tellingen1
        assert tellingen1['Standplaats']['op_bronsleutel_overgang'] == 1
        zelfdeNummerPerBronrij(pg0, pg1)

        tellingen2, pg2 = cyclus(omgeving, documenten())
        assert all(t['nieuw'] == 0 for t in tellingen2.values()), tellingen2
        assert pg2 == pg1
        assert not any(v['verdwenen'] or v['hernummerd'] for v in vergelijk(pg0, pg2).values())


def metAndereArtefactsoort(docs, artefactsoort, vondstnr=None):
    """De documenten waarin de artefacten van DB034 een andere artefactsoort (of vondstnr) hebben.

    Het artefact uit AW1DeterminatiesJohan heeft geen subnr (hulpsleutel-key), dat uit AARDEWERK 1 alleen
    key_subnr (key key_subnr|artefactsoort).
    """
    docs = copy.deepcopy(docs)
    for d in docs:
        if d['soort'] == 'Artefact' and d.get('projectcd') == 'DB034':
            if artefactsoort is None:
                d.pop('artefactsoort', None)
            else:
                d['artefactsoort'] = artefactsoort
            if vondstnr is not None:
                d['vondstnr'] = vondstnr
    return docs


@pytest.mark.unit
class TestCycliMetAndereArtefactsoort:
    """Issue 89: een andere artefactsoort of vondstnummer van een rij zonder natuurlijke key geeft geen nieuw nummer."""

    def test_wisselende_artefactsoort_houdt_het_nummer(self, omgeving):
        verwerkingsrun.startRun('incrementeel')
        # Elke cyclus een nieuwe extractie: nieuwe _id's, dezelfde bronrijen
        _, pg0 = cyclus(omgeving, documenten())
        artefacten = pg0['Def_Artefact']
        pk = next(p for p, (k, _) in artefacten.items() if k and k.startswith('PDB034P10V460|Aardewerk|bron:'))

        # Cyclus 1: Artefact won de harmonisatie (geen artefactsoort), zoals op 29 oktober om 17:49
        tellingen1, pg1 = cyclus(omgeving, metAndereArtefactsoort(documenten(), None))
        assert tellingen1['Artefact']['nieuw'] == 0 and tellingen1['Artefact']['nieuw_bronrij_bekend'] == 0
        assert tellingen1['Artefact']['op_bronsleutel_andere_key'] == 2
        assert pg1['Def_Artefact'][pk][0].startswith('PDB034P10V460||bron:')
        assert 'PDB034P10V460A1|' in {k for k, _ in pg1['Def_Artefact'].values()}

        # Cyclus 2: met de voorrang uit correcties.yml weer Aardewerk; cyclus 3: vondstnummer gecorrigeerd
        tellingen2, pg2 = cyclus(omgeving, documenten())
        tellingen3, pg3 = cyclus(omgeving, metAndereArtefactsoort(documenten(), 'Aardewerk', vondstnr=461.0))
        for tellingen in (tellingen2, tellingen3):
            assert all(t['nieuw'] == 0 and t['nieuw_bronrij_bekend'] == 0 for t in tellingen.values()), tellingen
        assert pg2['Def_Artefact'][pk][0].startswith('PDB034P10V460|Aardewerk|bron:')
        assert pg3['Def_Artefact'][pk][0].startswith('PDB034P10V461|Aardewerk|bron:')
        for voor, na in ((pg0, pg1), (pg1, pg2), (pg2, pg3)):
            assert not any(v['verdwenen'] or v['nieuw'] or v['hernummerd'] for v in vergelijk(voor, na).values())
            zelfdeNummerPerBronrij(voor, na)
        assert pg2 == pg0
