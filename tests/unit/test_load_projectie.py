"""
Unit tests voor de veldselectie van de load (loadToDatabase_functions.leesDocumenten).

getFields bepaalt de te lezen velden uit meta.py plus een steekproef van tien
documenten. Een veld dat pas later in de pipeline wordt gezet (artefactID op
foto's, door setReferences) en dat in die tien documenten ontbreekt, werd
daardoor voor de hele tabel niet gelezen: in de Delftse data had geen enkele
Def_Bestand-rij een artefactID, terwijl 1232 foto's in Single_Store_Clean er
een hadden. leesDocumenten leest daarom ook de kolommen van de doeltabel.
"""
import pytest

import wasstraat.loadToDatabase_functions as load


class NepCollectieMetProjectie:
    """Minimale collectie die find() met een projectie nabootst, in invoegvolgorde."""

    def __init__(self, docs):
        self.docs = docs

    def find(self, filt=None, projection=None):
        soort = (filt or {}).get('soort')
        resultaat = []
        for doc in self.docs:
            if soort is not None and doc.get('soort') != soort:
                continue
            if projection:
                resultaat.append({k: v for k, v in doc.items() if projection.get(k)})
            else:
                resultaat.append(dict(doc))
        return NepCursor(resultaat)


class NepCursor(list):
    """Cursor met limit(), zoals getFields die gebruikt."""

    def limit(self, n):
        return NepCursor(self[:n])


def maakBestanden():
    """Tien 'overige' bestanden zonder artefactID, daarna een foto met artefactID."""
    docs = [{'_id': f'o{i}', 'soort': 'Bestand', 'fileName': f'overig{i}.jpg', 'ID': i} for i in range(10)]
    docs.append({'_id': 'f1', 'soort': 'Bestand', 'fileName': 'DB34_P10_H1023_1_1.jpg', 'ID': 10,
                 'artefactID': 77, 'projectID': 3})
    return docs


@pytest.mark.unit
class TestLeesDocumentenProjectie:
    """De projectie bevat de kolommen van de doeltabel, ook als de steekproef ze mist."""

    @pytest.fixture(autouse=True)
    def veldnamen(self, monkeypatch):
        monkeypatch.setattr(load.meta, 'getVeldnamen', lambda soort: ['fileName'])

    def test_zonder_extra_velden_ontbreekt_artefactID(self):
        """Het oude gedrag: de steekproef van tien bepaalt de velden en artefactID valt weg."""
        _, docs = load.leesDocumenten(NepCollectieMetProjectie(maakBestanden()), 'Bestand')
        assert 'artefactID' not in docs[-1]

    def test_met_tabelkolommen_wordt_artefactID_gelezen(self):
        kolommen = {'primary_key', 'fileName', 'artefactID', 'projectID'}
        _, docs = load.leesDocumenten(NepCollectieMetProjectie(maakBestanden()), 'Bestand', extra_velden=kolommen)
        assert docs[-1]['artefactID'] == 77
        assert docs[-1]['projectID'] == 3

    def test_id_en_object_id_altijd_in_projectie(self):
        _, docs = load.leesDocumenten(NepCollectieMetProjectie(maakBestanden()), 'Bestand', extra_velden={'fileName'})
        assert docs[0]['_id'] == 'o0'
        assert docs[0]['ID'] == 0

    def test_veldnamen_uit_getfields_blijven_ongewijzigd(self):
        """extra_velden beinvloedt alleen de projectie, niet de lijst uit getFields (die bepaalt welke lege kolommen de upsert leegmaakt)."""
        fields, _ = load.leesDocumenten(NepCollectieMetProjectie(maakBestanden()), 'Bestand', extra_velden={'aantal_fotos', 'ft_search'})
        assert 'aantal_fotos' not in fields
        assert 'ft_search' not in fields
