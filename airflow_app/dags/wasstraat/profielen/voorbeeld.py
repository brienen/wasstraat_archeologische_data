"""
Voorbeeld-profiel: proof of concept voor een gemeente met directe referenties.

Dit profiel demonstreert dat een gemeente die al gestructureerde data
aanlevert (met expliciete kolommen als projectcode, putcode, etc.)
het standaard ConventieProfiel kan gebruiken zonder overrides.

Gebruik: WASSTRAAT_GEMEENTE=voorbeeld
"""
from wasstraat.profielen.conventie import ConventieProfiel


class VoorbeeldProfiel(ConventieProfiel):
    """PoC profiel: alles via standaard-conventie, geen overrides."""

    naam = "voorbeeld"
