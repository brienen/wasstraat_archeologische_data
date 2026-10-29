"""
Integratietest: de uitkomst van de pipeline met de Delftse testdata (DB034) tegen de referentie-uitkomst.

Leest ``tests/integration/fixtures/delft_golden_snapshot.json`` en vergelijkt per
soort de aantallen in Single_Store en Single_Store_Clean, de artefactsoorten en
de voorbeeldsleutels met de werkelijke uitkomst in de test-MongoDB. Elk verschil
komt als leesbare regel in de foutmelding.

De test draait in ``make integration-delft`` (en ``make integration-delft-pipeline``)
na de pipeline-tests: ``tests/integration/conftest.py`` zet hem achteraan, omdat
pytest de bestanden op alfabet verzamelt. Zonder uitkomst (Single_Store_Clean
leeg of MongoDB niet bereikbaar) wordt hij overgeslagen.

Raakt een wijziging de Delftse uitkomst, verklaar dan elk verschil en leg de
referentie opnieuw vast (met de Delftse testomgeving nog actief):

    python tests/integration/snapshot_mongodb.py referentie \\
        tests/integration/fixtures/delft_golden_snapshot.json "<verklaring van de verschillen>"
"""
import json
import os

import pytest

pymongo = pytest.importorskip("pymongo")

from tests.integration import snapshot_mongodb

# Hostpoort 27118: de MongoDB van docker-compose.delft-test.yml (zoals test_full_pipeline_delft_data.py;
# make integration-delft zet MONGO_TEST_URI daarop)
MONGO_TEST_URI = os.getenv("MONGO_TEST_URI", "mongodb://testroot:testpass@localhost:27118/")
DB_ANALYSE = "Arch_Analyse_Test"
REFERENTIE = os.path.join(os.path.dirname(__file__), "fixtures", "delft_golden_snapshot.json")
VASTLEGGEN = ("python tests/integration/snapshot_mongodb.py referentie "
              "tests/integration/fixtures/delft_golden_snapshot.json \"<verklaring>\"")

pytestmark = pytest.mark.delft


@pytest.fixture(scope="module")
def mongo_client():
    client = pymongo.MongoClient(MONGO_TEST_URI, serverSelectionTimeoutMS=5000)
    try:
        client.admin.command("ping")
    except pymongo.errors.ConnectionFailure:
        pytest.skip("MongoDB niet bereikbaar op " + MONGO_TEST_URI)
    yield client
    client.close()


@pytest.fixture(scope="module")
def referentie():
    with open(REFERENTIE, encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture(scope="module")
def verschillen(mongo_client, referentie):
    """Verschillen per sectie tussen de referentie en de uitkomst in de test-MongoDB."""
    if not mongo_client[DB_ANALYSE]["Single_Store_Clean"].estimated_document_count():
        pytest.skip("Single_Store_Clean is leeg: de pipeline met de Delftse testdata heeft niet gedraaid "
                    "(make integration-delft)")
    uitkomst = snapshot_mongodb.maakReferentie(mongo_client, DB_ANALYSE)
    return snapshot_mongodb.vergelijkReferentie(referentie, uitkomst, mongo_client, DB_ANALYSE)


def controleer(verschillen, sectie, onderwerp):
    """Laat de test falen met één regel per verschil in de sectie."""
    meldingen = verschillen[sectie]
    if meldingen:
        regels = "\n".join(f"  - {melding}" for melding in meldingen)
        pytest.fail(f"{onderwerp}: {len(meldingen)} verschil(len) met de referentie-uitkomst "
                    f"({os.path.relpath(REFERENTIE)}):\n{regels}\n"
                    f"Verklaar elk verschil. Is het verwacht, leg de referentie dan opnieuw vast: {VASTLEGGEN}",
                    pytrace=False)


class TestDelftReferentie:
    """De uitkomst van Extract en Transform met de Delftse testdata is gelijk aan de referentie."""

    def test_referentie_compleet(self, referentie):
        ontbrekend = [sectie for sectie in snapshot_mongodb.REFERENTIE_SECTIES if not referentie.get(sectie)]
        assert not ontbrekend, f"Secties ontbreken of zijn leeg in {REFERENTIE}: {ontbrekend}"

    def test_aantallen_single_store(self, verschillen):
        controleer(verschillen, "soort_counts_store", "Aantallen per soort in Single_Store")

    def test_aantallen_single_store_clean(self, verschillen):
        controleer(verschillen, "soort_counts_clean", "Aantallen per soort in Single_Store_Clean")

    def test_artefactsoorten(self, verschillen):
        controleer(verschillen, "artefact_subtypes", "Artefactsoorten in Single_Store_Clean")

    def test_voorbeeldsleutels(self, verschillen):
        controleer(verschillen, "key_samples", "Voorbeeldsleutels in Single_Store_Clean")
