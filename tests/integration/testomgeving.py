"""
Hulpfuncties voor de integratietests met synthetische data.

Gemeenteprofiel
---------------
De bestandsnamen van de synthetische data (SY002_P2_H4_1_1.jpg, SY001_G001.jpg,
SY002_B001.tif) volgen de Delftse naamconventie. Alleen een profiel dat die
conventie ontleedt (identificeer_foto en identificeer_tekening, zie
profielen/delft.py) deelt bestanden in naar soort en koppelt objectfoto's aan
hun vondst en artefact. Het basisprofiel (ConventieProfiel, ook het
voorbeeldprofiel) verwerkt elk bestand en koppelt het aan zijn project, maar
herkent de soort niet. De pipelinetests lezen hier welk profiel actief is en
kiezen daarmee hun verwachtingen voor bestanden; alle andere verwachtingen
gelden voor elk profiel.

Het profiel van de testomgeving kies je met GEMEENTE:

  make integration GEMEENTE=voorbeeld

Het Makefile geeft die waarde als WASSTRAAT_GEMEENTE door aan de
Airflow-container (docker-compose.test.yml); de standaard is delft.

Uitvoer van psql
----------------
splitsPsqlUitvoer zet de uitvoer van ``psql -t -A -F <tab>`` om in rijen.
"""
import os
import subprocess

AIRFLOW_CONTAINER = os.getenv("AIRFLOW_CONTAINER", "wasstraat_airflow_test")

# Zelfde standaard als shared/config.py en profielen.getGemeente()
STANDAARD_PROFIEL = "delft"

# Profielen die de Delftse bestandsnamen van de synthetische data ontleden. Bewust een vaste lijst
# en geen vraag aan het profiel zelf: valt de herkenning in het Delftse profiel weg, dan moeten de
# tests falen in plaats van stil over te gaan op de verwachtingen van het basisprofiel.
PROFIELEN_MET_DELFTSE_BESTANDSNAMEN = ("delft",)

_profiel_per_container = {}


def actiefProfiel(container=None):
    """Het gemeenteprofiel waarmee de Airflow-container van de testomgeving draait.

    Leest WASSTRAAT_GEMEENTE uit de container zelf, zodat de tests ook kloppen als de
    testomgeving al draaide (make integration-keep) of pytest los wordt gestart.

    Args:
        container: naam van de Airflow-container; standaard die van de synthetische testomgeving

    Returns:
        De naam van het profiel in kleine letters; 'delft' als de variabele leeg is of ontbreekt

    Raises:
        RuntimeError: als de container niet bereikbaar is
    """
    container = container or AIRFLOW_CONTAINER
    if container not in _profiel_per_container:
        resultaat = subprocess.run(
            ["docker", "exec", container, "sh", "-c", 'echo "${WASSTRAAT_GEMEENTE:-}"'],
            capture_output=True, text=True, timeout=30)
        if resultaat.returncode != 0:
            raise RuntimeError(f"Het gemeenteprofiel is niet te lezen uit {container}: {resultaat.stderr.strip()}")
        _profiel_per_container[container] = resultaat.stdout.strip().lower() or STANDAARD_PROFIEL
    return _profiel_per_container[container]


def herkentBestandsnamen(profiel=None):
    """True als het profiel de Delftse bestandsnamen van de synthetische data ontleedt.

    Args:
        profiel: naam van het profiel; standaard het actieve profiel van de testomgeving

    Returns:
        True voor een profiel uit PROFIELEN_MET_DELFTSE_BESTANDSNAMEN, anders False
    """
    return (profiel or actiefProfiel()) in PROFIELEN_MET_DELFTSE_BESTANDSNAMEN


def splitsPsqlUitvoer(uitvoer):
    """Zet de uitvoer van ``psql -t -A -F <tab>`` om in rijen met tekstwaarden.

    Een lege waarde (NULL of lege tekst) blijft een lege tekst op zijn plaats in de rij, ook als
    eerste kolom van de eerste rij of als laatste kolom van de laatste rij. Tot 16 november 2026
    werd de hele uitvoer eerst met strip() ontdaan van witruimte; een lege eerste of laatste
    waarde viel dan samen met zijn tab weg en de rij werd een kolom korter.

    Alleen een geheel lege regel wordt overgeslagen: de afsluitende regel van psql, of een rij
    met één kolom zonder waarde (die is in deze uitvoer niet van 'geen rij' te onderscheiden).

    Args:
        uitvoer: de standaarduitvoer van psql

    Returns:
        Lijst met per rij een lijst tekstwaarden
    """
    return [regel.split("\t") for regel in uitvoer.split("\n") if regel != ""]
