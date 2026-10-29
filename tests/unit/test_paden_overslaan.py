"""
Unit tests voor paden_overslaan in correcties.yml (issue 84).

De sectie paden_overslaan is een lijst met glob-patronen, relatief aan de
invoermap, hoofdletterongevoelig. Eén instelling geldt voor alle brontypen:

- de Access-databases van importMDB.sh (via airflow_app/scripts/paden_overslaan.py);
- de registratie van bronbestanden voor de incrementele cyclus
  (bronbestanden.zoekMdbBestanden, zoekAfbeeldingen en scanBronbestanden);
- de afbeeldingen en rapporten (image_import.getImageFilenames).

Getest worden de vertaling van de patronen, het laden met foutieve waarden,
het filter met de logregels, het script en importMDB.sh (met nep-MDB's, zoals
test_importMDB_lijstbestand.py), de selecties in bronbestanden en image_import
en de drie configuraties in de repo.
"""
import logging
import os
import subprocess
import sys
import types

import pandas as pd
import pytest
import yaml

# Mock shared.image_util (wordt via bronbestanden/opruimen geïmporteerd door image_import.py)
if "shared.image_util" not in sys.modules:
    sys.modules["shared.image_util"] = types.ModuleType("shared.image_util")

import shared.config as config
import wasstraat.bronbestanden as bronbestanden
import wasstraat.image_import as image_import
import wasstraat.paden_overslaan as paden_overslaan

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SCRIPT = os.path.join(PROJECT_ROOT, "airflow_app", "scripts", "paden_overslaan.py")
IMPORT_SCRIPT = os.path.join(PROJECT_ROOT, "airflow_app", "scripts", "importMDB.sh")
WERKMAP_DC024 = "DC024_Stadskantoor/K Overig/werkmap joris"
# De vijf Access-databases in de werkmap van DC024 (gemeten op 2026-10-29, data/delft/data/projecten)
DC024_KOPIEEN = [
    "DC024_Stadskantoor/K Overig/werkmap joris/opgravingDC24.mdb",
    "DC024_Stadskantoor/K Overig/werkmap joris/opgravingDC241.mdb",
    "DC024_Stadskantoor/K Overig/werkmap joris/raapimport.accdb",
    "DC024_Stadskantoor/K Overig/werkmap joris/test.mdb",
    "DC024_Stadskantoor/K Overig/werkmap joris/C Database/DC24_STADSKANTOOR.mdb",
]
DC024_HOUDEN = [
    "DC024_Stadskantoor/C Database/DC24_STADSKANTOOR.mdb",
    "DC024_Stadskantoor/B Arcview/opgravingDC24.mdb",
    "DC024_Stadskantoor/K Overig/temp/info/x.mdb",
]


def patronen(*teksten):
    """Patronen zoals laadPatronen ze teruggeeft."""
    return paden_overslaan.laadPatronen({'paden_overslaan': list(teksten)})


def schrijf(pad, inhoud=b''):
    os.makedirs(os.path.dirname(pad), exist_ok=True)
    with open(pad, 'wb') as f:
        f.write(inhoud)
    return str(pad)


@pytest.fixture
def metPatronen(monkeypatch):
    """Zet de patronen die de pipeline uit correcties.yml leest (paden_overslaan.laadPatronenUitConfig)."""
    def zet(*teksten):
        monkeypatch.setattr(paden_overslaan, 'laadPatronenUitConfig', lambda: patronen(*teksten))
    return zet


# ============================================================
# Patronen
# ============================================================

@pytest.mark.unit
class TestVertaalPatroon:
    """Glob-patronen relatief aan de invoermap, hoofdletterongevoelig; een map geldt voor alles daaronder."""

    @pytest.mark.parametrize("patroon,pad,verwacht", [
        (WERKMAP_DC024, WERKMAP_DC024 + "/opgravingDC24.mdb", True),
        (WERKMAP_DC024, WERKMAP_DC024 + "/C Database/DC24_STADSKANTOOR.mdb", True),
        (WERKMAP_DC024, WERKMAP_DC024, True),
        (WERKMAP_DC024, "DC024_Stadskantoor/C Database/DC24_STADSKANTOOR.mdb", False),
        (WERKMAP_DC024, "XDC024_Stadskantoor/K Overig/werkmap joris/a.mdb", False),
        ("dc024_stadskantoor/k overig/WERKMAP JORIS", WERKMAP_DC024 + "/a.mdb", True),
        ("DC024_Stadskantoor/K Overig/werkmap", WERKMAP_DC024 + "/a.mdb", False),
        ("DC024*/K Overig/werkmap*", WERKMAP_DC024 + "/a.mdb", True),
        ("*/werkmap*", "DC024_Stadskantoor/K Overig/werkmap joris/a.mdb", False),
        ("**/werkmap*", "DC024_Stadskantoor/K Overig/werkmap joris/a.mdb", True),
        ("**/werkmap*", "werkmap/a.mdb", True),
        ("**/*.accdb", "DC024_Stadskantoor/B Arcview/Database1.accdb", True),
        ("**/*.accdb", "DC024_Stadskantoor/B Arcview/opgravingDC24.mdb", False),
        ("SY001/**/kopie.mdb", "SY001/kopie.mdb", True),
        ("SY001/**/kopie.mdb", "SY001/a/b/kopie.mdb", True),
        ("SY001/**", "SY001/a.mdb", True),
        ("SY001/**", "SY0011/a.mdb", False),
        ("SY00?/K Overig", "SY003/K Overig/a.mdb", True),
        ("SY00[12]/K Overig", "SY002/K Overig/a.mdb", True),
        ("SY00[!12]/K Overig", "SY002/K Overig/a.mdb", False),
        ("SY00[!12]/K Overig", "SY003/K Overig/a.mdb", True),
        ("L Fotos/G (Opgravingsfoto's)", "L Fotos/G (Opgravingsfoto's)/DB34_G0001.jpg", True),
        ("a+b/c.d", "a+b/c.d", True),
        ("a+b/c.d", "aab/cxd", False),
        ("/SY001/K Overig/", "SY001/K Overig/a.mdb", True),
        ("./SY001\\K Overig", "SY001/K Overig/a.mdb", True),
    ])
    def test_patroon(self, patroon, pad, verwacht):
        assert bool(paden_overslaan.vertaalPatroon(patroon).match(pad)) is verwacht

    @pytest.mark.parametrize("patroon", ["", "   ", "/", "./"])
    def test_leeg_patroon_is_ongeldig(self, patroon):
        with pytest.raises(ValueError):
            paden_overslaan.vertaalPatroon(patroon)


@pytest.mark.unit
class TestLaadPatronen:
    """De sectie wordt robuust gelezen: foutieve waarden worden gelogd en overgeslagen."""

    def test_geldige_lijst(self):
        resultaat = patronen(WERKMAP_DC024, "**/werkmap*")
        assert [tekst for tekst, _ in resultaat] == [WERKMAP_DC024, "**/werkmap*"]

    @pytest.mark.parametrize("correcties", [None, {}, {'paden_overslaan': None}, {'paden_overslaan': []}, []])
    def test_geen_patronen(self, correcties):
        assert paden_overslaan.laadPatronen(correcties) == []

    @pytest.mark.parametrize("waarde", ["DC024/werkmap", {'patroon': 'x'}, 12])
    def test_geen_lijst_geeft_fout_en_geen_patronen(self, waarde, caplog):
        with caplog.at_level(logging.ERROR, logger="airflow.task"):
            assert paden_overslaan.laadPatronen({'paden_overslaan': waarde}) == []
        assert "paden_overslaan in correcties.yml is geen lijst" in caplog.text

    def test_ongeldige_elementen_worden_overgeslagen(self, caplog):
        with caplog.at_level(logging.WARNING, logger="airflow.task"):
            resultaat = paden_overslaan.laadPatronen(
                {'paden_overslaan': [None, 12, '', '  ', {'patroon': 'x'}, '[]', 'SY001/K Overig']})
        assert [tekst for tekst, _ in resultaat] == ['SY001/K Overig']
        assert caplog.text.count("Ongeldig patroon in paden_overslaan") == 6

    def test_spaties_rond_patroon_vallen_weg(self):
        assert patronen("  SY001/K Overig  ")[0][0] == "SY001/K Overig"


@pytest.mark.unit
class TestLeesCorrectiebestand:
    """Het script van importMDB.sh leest correcties.yml zonder shared.config."""

    def test_ontbrekend_bestand(self, tmp_path):
        assert paden_overslaan.leesCorrectiebestand(str(tmp_path / "bestaat_niet.yml")) == {}
        assert paden_overslaan.leesCorrectiebestand(None) == {}

    def test_geldig_bestand(self, tmp_path):
        pad = tmp_path / "correcties.yml"
        pad.write_text("paden_overslaan:\n  - \"SY001/K Overig\"\n", encoding="utf-8")
        assert paden_overslaan.leesCorrectiebestand(str(pad)) == {'paden_overslaan': ['SY001/K Overig']}

    def test_ongeldige_yaml(self, tmp_path, caplog):
        pad = tmp_path / "correcties.yml"
        pad.write_text("paden_overslaan: [\n  - kapot", encoding="utf-8")
        with caplog.at_level(logging.ERROR, logger="airflow.task"):
            assert paden_overslaan.leesCorrectiebestand(str(pad)) == {}
        assert "Ongeldig correctiebestand" in caplog.text

    def test_geen_dictionary(self, tmp_path):
        pad = tmp_path / "correcties.yml"
        pad.write_text("- a\n- b\n", encoding="utf-8")
        assert paden_overslaan.leesCorrectiebestand(str(pad)) == {}


@pytest.mark.unit
class TestFilterPaden:
    """filterPaden laat paden weg die onder een patroon vallen, met een logregel per bestand en een telling."""

    def test_relatief_pad(self):
        assert paden_overslaan.relatiefPad("/input/projecten/SY001/a.mdb", "/input/projecten") == "SY001/a.mdb"
        assert paden_overslaan.relatiefPad("/input/projecten/SY001/a.mdb", "/input/projecten/") == "SY001/a.mdb"
        assert paden_overslaan.relatiefPad("/input/images/SY001/a.jpg", "/input/projecten") == "input/images/SY001/a.jpg"
        assert paden_overslaan.relatiefPad("/input/projectenlijst/a.mdb", "/input/projecten") == "input/projectenlijst/a.mdb"
        assert paden_overslaan.relatiefPad("/input/x.mdb", None) == "input/x.mdb"

    def test_filter_met_log_en_telling(self, caplog):
        invoermap = "/input/projecten"
        paden = [f"{invoermap}/{p}" for p in DC024_HOUDEN[:1] + DC024_KOPIEEN + DC024_HOUDEN[1:]]
        overgeslagen = []
        with caplog.at_level(logging.INFO, logger="airflow.task"):
            behouden = paden_overslaan.filterPaden(paden, invoermap, patronen=patronen(WERKMAP_DC024),
                                                   overgeslagen=overgeslagen, omschrijving='Access-databases')
        assert behouden == [f"{invoermap}/{p}" for p in DC024_HOUDEN]
        assert overgeslagen == [f"{invoermap}/{p}" for p in DC024_KOPIEEN]
        for pad in overgeslagen:
            assert f"Overgeslagen volgens paden_overslaan (patroon '{WERKMAP_DC024}'): {pad}" in caplog.text
        assert "5 van 8 Access-databases in /input/projecten overgeslagen volgens paden_overslaan." in caplog.text

    def test_zonder_patronen_ongewijzigd_en_geen_log(self, caplog):
        paden = ["/input/projecten/" + p for p in DC024_KOPIEEN]
        with caplog.at_level(logging.INFO, logger="airflow.task"):
            assert paden_overslaan.filterPaden(paden, "/input/projecten", patronen=[]) == paden
        assert "paden_overslaan" not in caplog.text

    def test_patronen_uit_config(self, metPatronen):
        metPatronen("SY001/K Overig")
        assert paden_overslaan.filterPaden(["/in/SY001/K Overig/a.mdb", "/in/SY001/C/a.mdb"], "/in") == ["/in/SY001/C/a.mdb"]

    def test_patronen_uit_correcties_yml(self, tmp_path, monkeypatch):
        """laadPatronenUitConfig leest de sectie via harmonize_functions.laadCorrecties (gecachet)."""
        import wasstraat.harmonize_functions as hf
        pad = tmp_path / "correcties.yml"
        pad.write_text("paden_overslaan:\n  - \"**/werkmap*\"\n", encoding="utf-8")
        monkeypatch.setattr(hf, '_correcties_cache', None)
        monkeypatch.setattr(hf.config, 'AIRFLOW_CORRECTIES_CONFIG', str(pad))
        try:
            assert [tekst for tekst, _ in paden_overslaan.laadPatronenUitConfig()] == ["**/werkmap*"]
        finally:
            hf._correcties_cache = None


# ============================================================
# Script en importMDB.sh
# ============================================================

def draaiScript(invoermap, paden, correcties=None):
    """Draai airflow_app/scripts/paden_overslaan.py; retourneer (exitcode, behouden paden, stderr)."""
    env = dict(os.environ)
    env.pop('AIRFLOW_CORRECTIES_CONFIG', None)
    if correcties:
        env['AIRFLOW_CORRECTIES_CONFIG'] = str(correcties)
    invoer = b''.join(p.encode('utf-8') + b'\0' for p in paden)
    result = subprocess.run([sys.executable, SCRIPT, str(invoermap)], input=invoer, capture_output=True,
                            timeout=60, env=env)
    behouden = [p.decode('utf-8') for p in result.stdout.split(b'\0') if p]
    return result.returncode, behouden, result.stderr.decode('utf-8')


def draaiImportMDB(tmp_path, correcties, *args):
    """Draai importMDB.sh met nep-MDB's (zie test_importMDB_lijstbestand.py) en een correctiebestand.

    python3 komt uit dezelfde omgeving als pytest, zodat PyYAML beschikbaar is.
    """
    env = dict(os.environ,
               AIRFLOW_TEMPDIR=str(tmp_path), DB_STAGING='testdb', AIRFLOW_LOGDIR=str(tmp_path),
               MONGO_INITDB_ROOT_USERNAME='test', MONGO_INITDB_ROOT_PASSWORD='test',
               MONGO_SERVER='localhost', COLL_STAGING_METAINFO='metainfo',
               AIRFLOW_CORRECTIES_CONFIG=str(correcties),
               PATH=os.path.dirname(sys.executable) + os.pathsep + os.environ.get('PATH', ''))
    result = subprocess.run(["bash", IMPORT_SCRIPT] + [str(a) for a in args],
                            capture_output=True, text=True, timeout=60, env=env)
    return result.returncode, result.stdout


@pytest.fixture
def werkmap(tmp_path):
    """Invoermap met een database en een kopie in een werkmap (zoals SY001 in de synthetische data)."""
    invoer = tmp_path / "projecten"
    origineel = schrijf(invoer / "SY001" / "C Database" / "opgravingSY001.mdb")
    kopie = schrijf(invoer / "SY001" / "K Overig" / "werkmap" / "opgravingSY001.mdb")
    correcties = tmp_path / "correcties.yml"
    correcties.write_text("paden_overslaan:\n  - \"sy001/k overig/WERKMAP\"\n", encoding="utf-8")
    return types.SimpleNamespace(invoer=invoer, origineel=origineel, kopie=kopie, correcties=correcties)


@pytest.mark.unit
class TestScript:
    """Het script filtert NUL-gescheiden paden; de logregels gaan naar stderr."""

    def test_filtert_en_logt(self, werkmap):
        code, behouden, stderr = draaiScript(werkmap.invoer, [werkmap.origineel, werkmap.kopie], werkmap.correcties)
        assert code == 0
        assert behouden == [werkmap.origineel]
        assert f"Overgeslagen volgens paden_overslaan (patroon 'sy001/k overig/WERKMAP'): {werkmap.kopie}" in stderr
        assert "1 van 2 MDB/ACCDB-bestand(en)" in stderr

    def test_zonder_correctiebestand_alles_ongewijzigd(self, werkmap, tmp_path):
        code, behouden, stderr = draaiScript(werkmap.invoer, [werkmap.kopie, werkmap.origineel],
                                             tmp_path / "bestaat_niet.yml")
        assert code == 0
        assert behouden == [werkmap.kopie, werkmap.origineel]
        assert "Overgeslagen" not in stderr

    def test_paden_met_bijzondere_tekens(self, tmp_path):
        correcties = tmp_path / "correcties.yml"
        correcties.write_text("paden_overslaan:\n  - \"G (Opgravingsfoto's)\"\n", encoding="utf-8")
        paden = ["/in/G (Opgravingsfoto's)/a b.mdb", "/in/Aardewerk & glas/c'd.mdb", "/in/é/ü.accdb"]
        code, behouden, _ = draaiScript("/in", paden, correcties)
        assert code == 0
        assert behouden == paden[1:]

    def test_zonder_argument(self):
        result = subprocess.run([sys.executable, SCRIPT], input=b'', capture_output=True, timeout=60)
        assert result.returncode == 2


@pytest.mark.unit
class TestImportMDB:
    """importMDB.sh verwerkt een database onder een uit te sluiten pad niet, in beide modi."""

    def test_map_modus(self, tmp_path, werkmap):
        exitcode, output = draaiImportMDB(tmp_path, werkmap.correcties, werkmap.invoer, 'test_collection')
        assert exitcode == 0
        assert "2 MDB/ACCDB-bestand(en) gevonden" in output
        assert f"Overgeslagen volgens paden_overslaan (patroon 'sy001/k overig/WERKMAP'): {werkmap.kopie}" in output
        assert "1 MDB/ACCDB-bestand(en) overgeslagen volgens paden_overslaan, 1 te verwerken." in output
        assert f"Processing {werkmap.origineel} file for project SY001" in output
        assert f"Processing {werkmap.kopie}" not in output
        # Het tijdelijke lijstbestand wordt opgeruimd
        assert not [f for f in os.listdir(tmp_path) if f.startswith("paden_overslaan_")]

    def test_lijstbestand_modus(self, tmp_path, werkmap):
        lijst = tmp_path / "delta_projecten.txt"
        lijst.write_text(f"{werkmap.kopie}\n{werkmap.origineel}\n", encoding="utf-8")
        exitcode, output = draaiImportMDB(tmp_path, werkmap.correcties, werkmap.invoer, 'test_collection', lijst)
        assert exitcode == 0
        assert f"Processing {werkmap.origineel} file" in output
        assert f"Processing {werkmap.kopie}" not in output

    def test_zonder_patronen_alles_verwerkt(self, tmp_path, werkmap):
        correcties = tmp_path / "leeg.yml"
        correcties.write_text("paden_overslaan: []\n", encoding="utf-8")
        exitcode, output = draaiImportMDB(tmp_path, correcties, werkmap.invoer, 'test_collection')
        assert exitcode == 0
        assert f"Processing {werkmap.kopie} file" in output
        assert "overgeslagen volgens paden_overslaan" not in output

    def test_alles_overgeslagen(self, tmp_path, werkmap):
        correcties = tmp_path / "alles.yml"
        correcties.write_text("paden_overslaan:\n  - \"SY001\"\n", encoding="utf-8")
        exitcode, output = draaiImportMDB(tmp_path, correcties, werkmap.invoer, 'test_collection')
        assert exitcode == 0
        assert "Processing" not in output
        assert "ENCODING RAPPORT" in output


# ============================================================
# Registratie van bronbestanden en afbeeldingen
# ============================================================

@pytest.mark.unit
class TestBronbestanden:
    """De registratie gebruikt dezelfde selectie als importMDB.sh en de extractie van afbeeldingen."""

    def test_zoek_mdb_bestanden(self, werkmap, metPatronen):
        metPatronen("SY001/K Overig/werkmap")
        overgeslagen = []
        assert bronbestanden.zoekMdbBestanden(str(werkmap.invoer), overgeslagen) == [werkmap.origineel]
        assert overgeslagen == [werkmap.kopie]

    def test_scan_verzamelt_overgeslagen_per_categorie(self, tmp_path, monkeypatch, werkmap, metPatronen):
        metPatronen("SY001/K Overig/werkmap")
        for naam in ['AIRFLOW_INPUT_PROJECTENLIJST', 'AIRFLOW_INPUT_MAGAZIJNLIJST', 'AIRFLOW_INPUT_FOTOLIJST',
                     'AIRFLOW_INPUT_MONSTER', 'AIRFLOW_INPUT_RAPPORTEN']:
            monkeypatch.setattr(config, naam, str(tmp_path / 'leeg' / naam))
        monkeypatch.setattr(config, 'AIRFLOW_INPUT_PROJECTEN', str(werkmap.invoer))
        for naam in ['FILE_ABREXCEL', 'FILE_EXTRA_PROJECTS', 'FILE_IMPORT_FILES_EXCEL']:
            monkeypatch.setattr(config, naam, str(tmp_path / 'leeg' / f'{naam}.xlsx'))
        foto = schrijf(werkmap.invoer / "SY001" / "L Fotos" / "SY001_G001.jpg")
        kopie_foto = os.path.join(str(werkmap.invoer), "SY001", "K Overig", "werkmap", "L Fotos", "SY001_G001.jpg")

        def getImageFilenames(overgeslagen=None):
            if overgeslagen is not None:
                overgeslagen.append(kopie_foto)
            return [foto]
        monkeypatch.setattr(bronbestanden.image_import, 'getImageFilenames', getImageFilenames)

        overgeslagen = {}
        gescand = bronbestanden.scanBronbestanden(overgeslagen)
        assert sorted(gescand) == sorted([werkmap.origineel, foto])
        assert overgeslagen == {'projecten': [werkmap.kopie], 'afbeeldingen': [kopie_foto]}
        velden = bronbestanden.maakOvergeslagenVelden(overgeslagen)
        assert velden['paden_overgeslagen'] == overgeslagen
        assert velden['tellingen.paden_overgeslagen'] == {'afbeeldingen': 1, 'projecten': 1, 'totaal': 2}

    def test_run_document_begrensd(self, monkeypatch):
        monkeypatch.setattr(bronbestanden, 'MAX_OVERGESLAGEN_PADEN', 2)
        velden = bronbestanden.maakOvergeslagenVelden({'projecten': ['/c', '/a', '/b']})
        assert velden['paden_overgeslagen'] == {'projecten': ['/a', '/b']}
        assert velden['tellingen.paden_overgeslagen'] == {'projecten': 3, 'totaal': 3}

    def test_geen_overgeslagen(self):
        assert bronbestanden.maakOvergeslagenVelden({}) == {
            'paden_overgeslagen': {}, 'tellingen.paden_overgeslagen': {'totaal': 0}}


@pytest.mark.unit
class TestAfbeeldingen:
    """Afbeeldingen en rapporten onder een uit te sluiten pad worden niet geïmporteerd."""

    @pytest.fixture
    def afbeeldingen(self, tmp_path, monkeypatch, metPatronen):
        invoer = tmp_path / "projecten"
        foto = schrijf(invoer / "SY001" / "L Fotos" / "SY001_G001.jpg")
        kopie = schrijf(invoer / "SY001" / "K Overig" / "werkmap" / "L Fotos" / "SY001_G001.jpg")
        # Alleen via de bestandenlijst geselecteerd (geen filterpatroon in het pad)
        lijst_origineel = schrijf(invoer / "SY001" / "Overig" / "SY001_X001.jpg")
        lijst_kopie = schrijf(invoer / "SY001" / "K Overig" / "werkmap" / "SY001_X001.jpg")
        excel = tmp_path / "bestanden.xlsx"
        pd.DataFrame({'Dir': [os.path.dirname(lijst_origineel), os.path.dirname(lijst_kopie)],
                      'Bestand': ['SY001_X001.jpg', 'SY001_X001.jpg'], 'wel/niet': [1, 1]}).to_excel(excel, index=False)
        monkeypatch.setattr(config, 'FILE_IMPORT_FILES_EXCEL', str(excel))
        monkeypatch.setattr(config, 'AIRFLOW_INPUT_IMAGES', str(invoer))
        monkeypatch.setattr(config, 'AIRFLOW_INPUT_RAPPORTEN', str(tmp_path / "rapporten"))
        metPatronen("SY001/K Overig/werkmap")
        return types.SimpleNamespace(invoer=invoer, foto=foto, kopie=kopie, lijst_origineel=lijst_origineel,
                                     lijst_kopie=lijst_kopie)

    def test_uit_map(self, afbeeldingen, caplog):
        overgeslagen = []
        with caplog.at_level(logging.INFO, logger="airflow.task"):
            gevonden = image_import.getImageNamesFromDir(str(afbeeldingen.invoer), overgeslagen)
        assert gevonden == [afbeeldingen.foto]
        assert overgeslagen == [afbeeldingen.kopie]
        assert f"Overgeslagen volgens paden_overslaan (patroon 'SY001/K Overig/werkmap'): {afbeeldingen.kopie}" in caplog.text

    def test_bestandenlijst_brengt_overgeslagen_bestand_niet_terug(self, afbeeldingen):
        """De vergelijking met getImageNamesFromDir gebeurt vóór paden_overslaan."""
        overgeslagen = []
        gevonden = image_import.getImageNamesFromExcelAndDir(str(afbeeldingen.invoer), overgeslagen)
        assert gevonden == [afbeeldingen.lijst_origineel]
        assert overgeslagen == [afbeeldingen.lijst_kopie]

    def test_alle_afbeeldingen(self, afbeeldingen):
        overgeslagen = []
        gevonden = image_import.getImageFilenames(overgeslagen)
        assert sorted(gevonden) == sorted([afbeeldingen.foto, afbeeldingen.lijst_origineel])
        assert sorted(overgeslagen) == sorted([afbeeldingen.kopie, afbeeldingen.lijst_kopie])


# ============================================================
# Configuraties in de repo
# ============================================================

def laadConfig(*delen):
    with open(os.path.join(PROJECT_ROOT, *delen), encoding="utf-8") as f:
        return yaml.safe_load(f)


@pytest.mark.unit
class TestConfiguraties:
    """De patronen in de Delftse, synthetische en test-configuratie."""

    def test_delft_slaat_werkmap_dc024_over(self):
        lijst = patronen(*laadConfig("data", "delft", "wasstraat_config", "correcties.yml")['paden_overslaan'])
        assert lijst, "Geen paden_overslaan in de Delftse correcties.yml"
        for pad in DC024_KOPIEEN:
            assert paden_overslaan.zoekPatroon("/input/projecten/" + pad, "/input/projecten", lijst), pad
            assert paden_overslaan.zoekPatroon("/input/images/" + pad, "/input/images", lijst), pad
        for pad in DC024_HOUDEN:
            assert paden_overslaan.zoekPatroon("/input/projecten/" + pad, "/input/projecten", lijst) is None, pad

    def test_delftse_testdata_slaat_niets_over(self):
        assert laadConfig("data", "test", "wasstraat_config", "correcties.yml")['paden_overslaan'] == []

    def test_synthetisch_slaat_werkmap_sy001_over(self):
        """De kopieën in de werkmap van SY001 (synthetische data) vallen onder het patroon, de rest niet."""
        lijst = patronen(*laadConfig("data", "synthetic", "wasstraat_config", "correcties.yml")['paden_overslaan'])
        invoermap = os.path.join(PROJECT_ROOT, "data", "synthetic", "data", "projecten")
        kopieen = [os.path.join(invoermap, "SY001", "K Overig", "werkmap", "opgravingSY001.mdb"),
                   os.path.join(invoermap, "SY001", "K Overig", "werkmap", "L Fotos", "SY001_G001.jpg")]
        for pad in kopieen:
            assert os.path.isfile(pad), f"{pad} ontbreekt in de synthetische data"
            assert paden_overslaan.zoekPatroon(pad, invoermap, lijst), pad
        overige = [os.path.join(dp, f) for dp, _, namen in os.walk(invoermap) for f in namen
                   if "werkmap" not in dp]
        assert overige
        for pad in overige:
            assert paden_overslaan.zoekPatroon(pad, invoermap, lijst) is None, pad

    def test_deploy_sjabloon_heeft_lege_lijst(self):
        assert laadConfig("deploy", "wasstraat_config", "correcties.yml")['paden_overslaan'] == []
