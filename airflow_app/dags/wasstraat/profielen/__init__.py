"""
Profielensysteem voor gemeente-specifieke sleutelafleiding.

Elke gemeente kan een eigen profiel definiëren dat bepaalt hoe
bestandsnamen worden geparsed, projectcodes worden genormaliseerd,
en rapportnummers worden afgeleid. Het standaardprofiel (conventie)
neemt velden direct over uit de brondata zonder transformatie.

Profielselectie via environment variable WASSTRAAT_GEMEENTE (default: delft).
Een onbekende waarde geeft een ValueError met de bekende profielen; de taak
Start_Run van de cycli en DAG_Load_Only laadt het profiel al, zodat de run
dan direct stopt (issue 87).
"""
import importlib

import shared.config as config
import logging

logger = logging.getLogger("airflow.task")

# Bekende profielen: waarde van WASSTRAAT_GEMEENTE -> (module, klasse)
PROFIELEN = {
    'delft': ('wasstraat.profielen.delft', 'DelftProfiel'),
    'voorbeeld': ('wasstraat.profielen.voorbeeld', 'VoorbeeldProfiel'),
}
STANDAARD_GEMEENTE = 'delft'

_profiel_cache = None


def getGemeente():
    """Retourneer de ingestelde gemeente (WASSTRAAT_GEMEENTE), in kleine letters en zonder spaties eromheen.

    Returns:
        De naam van het profiel; 'delft' als de variabele niet is ingesteld of leeg is
    """
    gemeente = getattr(config, 'WASSTRAAT_GEMEENTE', STANDAARD_GEMEENTE) or STANDAARD_GEMEENTE
    return str(gemeente).lower().strip() or STANDAARD_GEMEENTE


def get_profiel():
    """Geeft het actieve gemeenteprofiel terug.

    Leest WASSTRAAT_GEMEENTE uit de configuratie. Default: 'delft'
    voor backwards compatibility.

    Returns:
        GemeenteProfiel-instantie voor de geconfigureerde gemeente.

    Raises:
        ValueError: als de gemeente niet bekend is; de melding noemt de bekende profielen.
    """
    global _profiel_cache
    if _profiel_cache is not None:
        return _profiel_cache

    gemeente = getGemeente()
    if gemeente not in PROFIELEN:
        raise ValueError(
            f"Onbekend gemeenteprofiel: '{gemeente}' (WASSTRAAT_GEMEENTE). "
            f"Bekende profielen: {', '.join(PROFIELEN)}."
        )

    module, klasse = PROFIELEN[gemeente]
    _profiel_cache = getattr(importlib.import_module(module), klasse)()

    logger.info(f"Gemeenteprofiel geladen: {_profiel_cache.naam}")
    return _profiel_cache


def reset_profiel():
    """Reset de cache zodat het profiel opnieuw geladen wordt.

    Nuttig voor tests die met verschillende profielen willen werken.
    """
    global _profiel_cache
    _profiel_cache = None
