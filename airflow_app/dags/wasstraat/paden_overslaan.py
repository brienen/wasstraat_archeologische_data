"""Bestanden en mappen die de extractie overslaat (sectie paden_overslaan in correcties.yml, issue 84).

In de brondata staan soms kopieën van databases of afbeeldingen die niet als
aparte bron mogen tellen, zoals de werkmap van Joris in DC024
(``DC024_Stadskantoor/K Overig/werkmap joris``): vijf Access-databases die
grotendeels kopieën zijn van de opgravingsdatabase. Zonder filter leest de
extractie ze in als aparte bron en geven ze dubbele artefacten, sporen en
vondsten.

De sectie ``paden_overslaan`` in correcties.yml is een lijst met
glob-patronen. Eén instelling geldt voor alle brontypen: de Access-databases
van importMDB.sh (via het script ``airflow_app/scripts/paden_overslaan.py``),
de registratie van bronbestanden voor de incrementele cyclus
(``bronbestanden.zoekMdbBestanden`` en ``zoekAfbeeldingen``) en de afbeeldingen
en rapporten (``image_import.getImageFilenames``).

Vorm van een patroon:

- relatief aan de invoermap van het bestand: de projectmap
  (``AIRFLOW_INPUT_PROJECTEN``), de map met afbeeldingen, de map met rapporten,
  enzovoort. In de standaardopzet is de map met afbeeldingen dezelfde als de
  projectmap, zodat ``DC024_Stadskantoor/K Overig/werkmap joris`` zowel de
  databases als de afbeeldingen in die map dekt;
- ``/`` scheidt mappen; ``*`` staat voor een willekeurig deel van één naam (niet
  over een ``/`` heen), ``?`` voor één teken, ``[abc]`` en ``[!abc]`` voor een
  teken uit (of buiten) een reeks, en ``**`` als hele naam voor nul of meer
  mappen (``**/werkmap*`` is een map die met werkmap begint, op elk niveau);
- hoofdletterongevoelig;
- een patroon dat een map aanwijst, geldt voor alles daaronder.

Elk overgeslagen bestand krijgt een regel in het log, gevolgd door een telling.
"""
import logging
import os
import re

logger = logging.getLogger("airflow.task")

# Naam van de sectie in correcties.yml
SECTIE = 'paden_overslaan'

# Standaardpad van het correctiebestand (zoals AIRFLOW_CORRECTIES_CONFIG in shared/config.py)
STANDAARD_CORRECTIES = '/opt/airflow/config/correcties.yml'


def _vertaalNaam(naam):
    """Vertaal één naam uit een glob-patroon (zonder /) naar een reguliere expressie."""
    regex = ''
    i = 0
    while i < len(naam):
        teken = naam[i]
        if teken == '*':
            regex += '[^/]*'
        elif teken == '?':
            regex += '[^/]'
        elif teken == '[':
            einde = naam.find(']', i + 2 if naam[i + 1:i + 2] in ('!', '^') else i + 1)
            if einde == -1:
                regex += re.escape(teken)
            else:
                inhoud = naam[i + 1:einde].replace('\\', '\\\\')
                if inhoud[:1] in ('!', '^'):
                    # Een teken buiten de reeks, maar nooit de scheiding tussen mappen
                    inhoud = '^/' + inhoud[1:]
                regex += '[' + inhoud + ']'
                i = einde
        else:
            regex += re.escape(teken)
        i += 1
    return regex


def vertaalPatroon(patroon):
    """Vertaal een glob-patroon uit paden_overslaan naar een gecompileerde reguliere expressie.

    Het patroon wordt vergeleken met het hele pad relatief aan de invoermap;
    een patroon dat een map aanwijst geldt ook voor alles daaronder.

    Args:
        patroon: tekst, bijv. 'DC024_Stadskantoor/K Overig/werkmap joris' of '**/werkmap*'

    Returns:
        re.Pattern (hoofdletterongevoelig)

    Raises:
        ValueError: als het patroon leeg is of geen geldige expressie oplevert
    """
    tekst = str(patroon).strip().replace('\\', '/')
    while tekst.startswith('./'):
        tekst = tekst[2:]
    tekst = tekst.strip('/')
    if not tekst:
        raise ValueError("leeg patroon")
    namen = [naam for naam in tekst.split('/') if naam]
    regex = ''
    for i, naam in enumerate(namen):
        eerste, laatste = i == 0, i == len(namen) - 1
        if naam == '**':
            if eerste and laatste:
                regex += '.*'
            elif eerste:
                regex += '(?:[^/]*/)*'
            elif laatste:
                regex += '(?:/.*)?'
            elif namen[i - 1] == '**':
                continue
            else:
                regex += '/(?:[^/]*/)*'
            continue
        if not eerste and namen[i - 1] != '**':
            regex += '/'
        regex += _vertaalNaam(naam)
    try:
        return re.compile('^' + regex + '(?:/.*)?$', re.IGNORECASE)
    except re.error as err:
        raise ValueError(str(err)) from err


def laadPatronen(correcties):
    """Lees de patronen uit de sectie paden_overslaan van de geladen correcties.

    Ongeldige waarden worden gelogd en overgeslagen, zoals bij de andere
    secties van correcties.yml: een sectie die geen lijst is levert geen
    patronen op, een element dat geen (niet-lege) tekst of geen geldig patroon
    is wordt weggelaten.

    Args:
        correcties: dict uit correcties.yml (harmonize_functions.laadCorrecties), of None

    Returns:
        Lijst met tuples (patroon als tekst, re.Pattern)
    """
    if not isinstance(correcties, dict):
        return []
    waarde = correcties.get(SECTIE)
    if waarde is None:
        return []
    if not isinstance(waarde, list):
        logger.error(f"{SECTIE} in correcties.yml is geen lijst (type={type(waarde).__name__}) — "
                     f"er worden geen bestanden overgeslagen.")
        return []
    patronen = []
    for element in waarde:
        if not isinstance(element, str) or not element.strip():
            logger.warning(f"Ongeldig patroon in {SECTIE}: {element!r} (verwacht een niet-lege tekst) — overgeslagen.")
            continue
        try:
            patronen.append((element.strip(), vertaalPatroon(element)))
        except ValueError as err:
            logger.warning(f"Ongeldig patroon in {SECTIE}: {element!r} ({err}) — overgeslagen.")
    return patronen


def leesCorrectiebestand(pad):
    """Lees correcties.yml buiten Airflow (voor het script van importMDB.sh).

    Binnen Airflow gebruikt de pipeline harmonize_functions.laadCorrecties();
    deze functie doet hetzelfde zonder shared.config: een ontbrekend bestand
    geeft een lege dict, ongeldige YAML een foutmelding en een lege dict.

    Args:
        pad: pad van het correctiebestand

    Returns:
        dict met de correcties (leeg als het bestand ontbreekt of ongeldig is)
    """
    if not pad or not os.path.isfile(pad):
        return {}
    try:
        import yaml
    except ImportError:
        logger.warning(f"PyYAML ontbreekt: {pad} kan niet worden gelezen — er worden geen bestanden overgeslagen.")
        return {}
    try:
        with open(pad, 'r', encoding='utf-8') as f:
            correcties = yaml.safe_load(f)
    except (OSError, yaml.YAMLError) as err:
        logger.error(f"Ongeldig correctiebestand {pad}: {err} — er worden geen bestanden overgeslagen.")
        return {}
    if not isinstance(correcties, dict):
        logger.error(f"Correctiebestand {pad} bevat geen YAML-dictionary — er worden geen bestanden overgeslagen.")
        return {}
    return correcties


def laadPatronenUitConfig():
    """Laad de patronen uit het correctiebestand van de pipeline (harmonize_functions.laadCorrecties, gecachet)."""
    from wasstraat.harmonize_functions import laadCorrecties
    return laadPatronen(laadCorrecties())


def relatiefPad(pad, invoermap):
    """Retourneer een pad relatief aan de invoermap, met / als scheiding.

    Ligt het pad niet in de invoermap (of is er geen invoermap), dan is het
    resultaat het pad zonder / aan het begin.
    """
    pad = str(pad).replace('\\', '/')
    if invoermap:
        basis = str(invoermap).replace('\\', '/').rstrip('/') + '/'
        if pad.startswith(basis):
            return pad[len(basis):]
    return pad.lstrip('/')


def zoekPatroon(pad, invoermap, patronen):
    """Retourneer het eerste patroon (als tekst) waaronder het pad valt, of None."""
    relatief = relatiefPad(pad, invoermap)
    for tekst, regex in patronen:
        if regex.match(relatief):
            return tekst
    return None


def filterPaden(paden, invoermap, patronen=None, overgeslagen=None, omschrijving='bestanden'):
    """Laat de paden weg die onder een patroon uit paden_overslaan vallen.

    Logt per overgeslagen bestand een regel en daarna een telling (alleen als
    er patronen zijn).

    Args:
        paden: lijst met volledige paden
        invoermap: map waartegen de patronen relatief zijn (de invoermap van de categorie)
        patronen: lijst uit laadPatronen; None = uit het correctiebestand van de pipeline
        overgeslagen: optionele lijst die met de overgeslagen paden wordt aangevuld
        omschrijving: soort bestanden voor het log, bijv. 'Access-databases'

    Returns:
        Lijst met de paden die niet worden overgeslagen (in dezelfde volgorde)
    """
    paden = list(paden)
    if patronen is None:
        patronen = laadPatronenUitConfig()
    if not patronen or not paden:
        return paden
    behouden = []
    aantal = 0
    for pad in paden:
        patroon = zoekPatroon(pad, invoermap, patronen)
        if patroon is None:
            behouden.append(pad)
            continue
        aantal += 1
        logger.info(f"Overgeslagen volgens {SECTIE} (patroon '{patroon}'): {pad}")
        if overgeslagen is not None:
            overgeslagen.append(pad)
    logger.info(f"{aantal} van {len(paden)} {omschrijving} in {invoermap} overgeslagen volgens {SECTIE}.")
    return behouden
