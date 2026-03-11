"""
Conftest voor de Wasstraat testsuite.

Zorgt ervoor dat shared.config geïmporteerd kan worden zonder dat
environment variabelen (POSTGRES_DB, etc.) gezet zijn, door een mock-module
te registreren voordat de echte modules geladen worden.

Mockt ook externe dependencies die niet standaard beschikbaar zijn
(roman, timeperiod2daterange) zodat unit tests zonder pip install draaien.
"""
import sys
import types
import os

# ============================================================
# Mock externe libraries die niet altijd beschikbaar zijn
# ============================================================

# --- roman (Romeinse cijfers) ---
if "roman" not in sys.modules:
    roman_mod = types.ModuleType("roman")

    def _toRoman(n):
        vals = [
            (1000, "M"), (900, "CM"), (500, "D"), (400, "CD"),
            (100, "C"), (90, "XC"), (50, "L"), (40, "XL"),
            (10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I"),
        ]
        result = ""
        for value, numeral in vals:
            while n >= value:
                result += numeral
                n -= value
        return result

    def _fromRoman(s):
        mapping = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100, "D": 500, "M": 1000}
        result = 0
        s = s.upper()
        for i in range(len(s)):
            if i + 1 < len(s) and mapping.get(s[i], 0) < mapping.get(s[i + 1], 0):
                result -= mapping.get(s[i], 0)
            else:
                result += mapping.get(s[i], 0)
        return result

    roman_mod.toRoman = _toRoman
    roman_mod.fromRoman = _fromRoman
    sys.modules["roman"] = roman_mod

# --- timeperiod2daterange (PHD daterange fixer) ---
if "timeperiod2daterange" not in sys.modules:
    tp_mod = types.ModuleType("timeperiod2daterange")

    def _detection2daterange(text):
        """Stub: retourneert None (fallback in fixDatering)."""
        return None

    tp_mod.detection2daterange = _detection2daterange
    sys.modules["timeperiod2daterange"] = tp_mod


# ============================================================
# Mock shared.config
# ============================================================
mock_config = types.ModuleType("shared.config")

# MongoDB
mock_config.MONGO_URI = "mongodb://test:test@localhost:27017/"
mock_config.MONGO_STAGING_URI = "mongodb://test:test@localhost:27017/test_staging"
mock_config.MONGO_FILES_URI = "mongodb://test:test@localhost:27017/test_files"
mock_config.MONGO_ANALYSE_URI = "mongodb://test:test@localhost:27017/test_analyse"
mock_config.MONGO_SERVER = "localhost"
mock_config.MONGO_INITDB_ROOT_USERNAME = "test"
mock_config.MONGO_INITDB_ROOT_PASSWORD = "test"
mock_config.MONGO_MINPOOLSIZE = 50
mock_config.DB_STAGING = "test_staging"
mock_config.DB_FILES = "test_files"
mock_config.DB_ANALYSE = "test_analyse"

# Collections
mock_config.COLL_ANALYSE = "Single_Store"
mock_config.COLL_ANALYSE_CLEAN = "Single_Store_Clean"
mock_config.COLL_PLAATJES = "Plaatjes"
mock_config.COLL_FILENAMES = "Filenames"
mock_config.COLL_STAGING_METAINFO = "Kolominformatie"
mock_config.COLL_STAGING_OUD = "Staging_Projecten_Oud"
mock_config.COLL_STAGING_NIEUW = "Staging_Projecten_Nieuw"
mock_config.COLL_STAGING_MAGAZIJNLIJST = "Staging_Projecten_Magazijnlijst"
mock_config.COLL_STAGING_DELFIT = "Staging_Projecten_DelfIT"
mock_config.COLL_STAGING_DIGIFOTOS = "Staging_Projecten_Digifotos"
mock_config.COLL_STAGING_MONSTER = "Staging_Projecten_Monster"
mock_config.COLL_STAGING_REFERENTIETABELLEN = "Staging_Referentietabellen"
mock_config.COLL_STAGING_RAPPORTEN = "Staging_Rapporten"
mock_config.COLL_ANALYSE_FOTO = "Def_Fotos"
mock_config.COLL_ANALYSE_ARTEFACT = "Def_Artefact"
mock_config.COLL_ANALYSE_PROJECT = "Def_Project"
mock_config.COLL_ANALYSE_VONDST = "Def_Vondst"
mock_config.COLL_ANALYSE_SPOOR = "Def_Spoor"
mock_config.COLL_ANALYSE_VLAK = "Def_Vlak"
mock_config.COLL_ANALYSE_PUT = "Def_Put"
mock_config.COLL_ANALYSE_DOOS = "Def_Doos"
mock_config.COLL_ANALYSE_STANDPLAATS = "Def_Standplaats"
mock_config.COLL_ANALYSE_STELLING = "Def_Stelling"
mock_config.COLL_ANALYSE_PLAATSING = "Def_Plaatsing"
mock_config.COLL_ANALYSE_VINDPLAATS = "Def_Vindplaats"

# PostgreSQL
mock_config.POSTGRES_DB = "test_db"
mock_config.POSTGRES_USER = "test"
mock_config.POSTGRES_PASSWORD = "test"
mock_config.FLASK_PGUSER = "test"
mock_config.FLASK_PGPASSWORD = "test"
mock_config.FLASK_PGDATABASE = "test_db"
mock_config.SQLALCHEMY_DATABASE_URI = "postgresql://test:test@localhost/test_db"

# Airflow paden — gebruik environment variabelen als die gezet zijn (container),
# anders fallback naar host-paden relatief aan de project root.
_project_root = os.path.dirname(os.path.dirname(__file__))
mock_config.AIRFLOW_WASSTRAAT_CONFIG = os.getenv(
    "AIRFLOW_WASSTRAAT_CONFIG",
    os.path.join(_project_root, "data", "wasstraat_config", "Wasstraat_Config_HarmonizeV3.xlsx")
)
mock_config.AIRFLOW_TEMPDIR = os.getenv("AIRFLOW_TEMPDIR", "/tmp/wasstraat_test")
mock_config.AIRFLOW_LOGDIR = os.getenv("AIRFLOW_LOGDIR", "/tmp/wasstraat_test/logs")
mock_config.AIRFLOW_INPUT_PROJECTEN = os.getenv("AIRFLOW_INPUT_PROJECTEN", "/input/projecten")
mock_config.AIRFLOW_INPUT_IMAGES = os.getenv("AIRFLOW_INPUT_IMAGES", "/input/images")
mock_config.AIRFLOW_INPUT_DELFIT = os.getenv("AIRFLOW_INPUT_DELFIT", "/input/delfit")
mock_config.AIRFLOW_INPUT_MAGAZIJNLIJST = "/input/magazijnlijst"
mock_config.AIRFLOW_INPUT_DIGIFOTOS = "/input/digifotos"
mock_config.AIRFLOW_INPUT_MONSTER = "/input/monsterdatabase"
mock_config.AIRFLOW_INPUT_RAPPORTEN = "/input/rapporten"
mock_config.AIRFLOW_OUTPUT_MEDIA = "/output/archeomedia"

# Elasticsearch
mock_config.ES_HOST = "http://localhost:9200"

# Overige
mock_config.IMAGE_EXTENSIONS = [".jpg", ".jpeg", ".gif", ".png", ".tif", ".psd", ".pdf", ".jp2", ".doc", ".docx"]
mock_config.FILE_WORD_ICON = "/input/digifotos/microsoft-word-logo.jpg"
mock_config.FILE_ABREXCEL = "/input/referentietabellen/abr_versie_01122018_input.xlsx"
mock_config.FILE_EXTRA_PROJECTS = "/input/delfit/Extra_projecten_tabel_OPGRAVINGEN.xlsx"
mock_config.FILE_IMPORT_FILES_EXCEL = "/input/referentietabellen/Alle Bestanden Archeologisch Depot.xlsx"

# Registreer mock voordat echte imports plaatsvinden
mock_shared = types.ModuleType("shared")
sys.modules["shared"] = mock_shared
sys.modules["shared.config"] = mock_config

# Laad echte const waarden (die hebben geen env vars nodig)
_const_mod = types.ModuleType("shared.const")
_const_path = os.path.join(_project_root, "shared", "const.py")
with open(_const_path) as f:
    exec(f.read(), _const_mod.__dict__)
sys.modules["shared.const"] = _const_mod
