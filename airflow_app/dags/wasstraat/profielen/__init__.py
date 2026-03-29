"""
Profielensysteem voor gemeente-specifieke sleutelafleiding.

Elke gemeente kan een eigen profiel definiëren dat bepaalt hoe
bestandsnamen worden geparsed, projectcodes worden genormaliseerd,
en rapportnummers worden afgeleid. Het standaardprofiel (conventie)
neemt velden direct over uit de brondata zonder transformatie.

Profielselectie via environment variable WASSTRAAT_GEMEENTE (default: delft).
"""
import shared.config as config
import logging

logger = logging.getLogger("airflow.task")

_profiel_cache = None


def get_profiel():
    """Geeft het actieve gemeenteprofiel terug.

    Leest WASSTRAAT_GEMEENTE uit de configuratie. Default: 'delft'
    voor backwards compatibility.

    Returns:
        GemeenteProfiel-instantie voor de geconfigureerde gemeente.

    Raises:
        ValueError: als de gemeente niet bekend is.
    """
    global _profiel_cache
    if _profiel_cache is not None:
        return _profiel_cache

    gemeente = getattr(config, 'WASSTRAAT_GEMEENTE', 'delft') or 'delft'
    gemeente = gemeente.lower().strip()

    if gemeente == 'delft':
        from wasstraat.profielen.delft import DelftProfiel
        _profiel_cache = DelftProfiel()
    elif gemeente == 'voorbeeld':
        from wasstraat.profielen.voorbeeld import VoorbeeldProfiel
        _profiel_cache = VoorbeeldProfiel()
    else:
        raise ValueError(
            f"Onbekend gemeenteprofiel: '{gemeente}'. "
            f"Bekende profielen: delft, voorbeeld."
        )

    logger.info(f"Gemeenteprofiel geladen: {_profiel_cache.naam}")
    return _profiel_cache


def reset_profiel():
    """Reset de cache zodat het profiel opnieuw geladen wordt.

    Nuttig voor tests die met verschillende profielen willen werken.
    """
    global _profiel_cache
    _profiel_cache = None
