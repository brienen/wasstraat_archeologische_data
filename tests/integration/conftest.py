"""
Conftest voor de integratietests.

Volgorde: pytest verzamelt de testbestanden op alfabet. De vergelijking met de
Delftse referentie-uitkomst (test_delft_referentie.py) leest de uitkomst van de
pipeline uit de test-MongoDB en moet daarom na de pipeline-tests draaien; deze
hook zet de tests uit NA_DE_PIPELINE achteraan, in hun eigen volgorde.
"""

# Testbestanden die de uitkomst van de pipeline lezen en daarom als laatste draaien
NA_DE_PIPELINE = ("test_delft_referentie.py",)


def pytest_collection_modifyitems(session, config, items):
    """Zet de tests uit NA_DE_PIPELINE achter alle andere tests van de sessie."""
    achteraan = [item for item in items if item.path.name in NA_DE_PIPELINE]
    if achteraan:
        items[:] = [item for item in items if item.path.name not in NA_DE_PIPELINE] + achteraan
