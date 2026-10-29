import os
import logging

logger = logging.getLogger()
basedir = os.path.abspath(os.path.dirname(__file__))


def _leesGetal(naam, standaard, soort=int):
   """Lees een niet-negatief getal uit een omgevingsvariabele.

   Omgevingsvariabelen zijn altijd tekst. Een lege, ongeldige of negatieve
   waarde levert de standaardwaarde op (met een waarschuwing in het log).

   Args:
      naam: naam van de omgevingsvariabele
      standaard: waarde als de variabele ontbreekt of ongeldig is
      soort: int (aantallen) of float (percentages)

   Returns:
      Het getal
   """
   waarde = os.getenv(naam)
   if waarde is None or not str(waarde).strip():
      return standaard
   try:
      getal = soort(str(waarde).strip().replace(',', '.'))
   except ValueError:
      logger.warning(f"Ongeldige waarde '{waarde}' voor {naam}; standaardwaarde {standaard} gebruikt.")
      return standaard
   if getal < 0:
      logger.warning(f"Negatieve waarde '{waarde}' voor {naam}; standaardwaarde {standaard} gebruikt.")
      return standaard
   return getal


# Kleine letters: Flask (app.config.from_object) leest alleen namen in hoofdletters als instelling
_waar = ('true', '1', 'ja', 'yes', 'on')
_onwaar = ('false', '0', 'nee', 'no', 'off')


def _leesBool(naam, standaard):
   """Lees een ja/nee-instelling uit een omgevingsvariabele.

   Omgevingsvariabelen zijn altijd tekst. True, 1, ja, yes en on gelden als
   waar, False, 0, nee, no en off als onwaar (hoofdletters en aanhalingstekens
   maken niet uit). Een lege of ontbrekende waarde levert de standaardwaarde op,
   een ongeldige ook (met een waarschuwing in het log).

   Args:
      naam: naam van de omgevingsvariabele
      standaard: waarde als de variabele ontbreekt of ongeldig is

   Returns:
      True of False
   """
   waarde = os.getenv(naam)
   if waarde is None:
      return standaard
   tekst = str(waarde).strip().strip('\'"').strip().lower()
   if not tekst:
      return standaard
   if tekst in _waar:
      return True
   if tekst in _onwaar:
      return False
   logger.warning(f"Ongeldige waarde '{waarde}' voor {naam}; standaardwaarde {standaard} gebruikt.")
   return standaard


def _leesTekst(naam, standaard=None):
   """Lees een tekst uit een omgevingsvariabele; leeg of ontbrekend geeft de standaardwaarde.

   Args:
      naam: naam van de omgevingsvariabele
      standaard: waarde als de variabele ontbreekt of leeg is

   Returns:
      De tekst of de standaardwaarde
   """
   waarde = os.getenv(naam)
   return waarde if waarde else standaard


# PostgreSQL-gebruiker en -database van Airflow (postgres.env). Elke variabele wordt los
# ingelezen: ontbreekt er een, dan volgt een foutmelding in het log, maar de instellingen
# hieronder worden gewoon ingelezen.
POSTGRES_DB = os.getenv("POSTGRES_DB")
POSTGRES_USER = os.getenv("POSTGRES_USER")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD")
_postgresOntbrekend = [naam for naam in ("POSTGRES_DB", "POSTGRES_USER", "POSTGRES_PASSWORD") if os.getenv(naam) is None]
if _postgresOntbrekend:
   logger.error(f"Omgevingsvariabele(n) {', '.join(_postgresOntbrekend)} ontbreken; voeg ze toe aan config/postgres.env.")

MONGO_SERVER = os.getenv("MONGO_SERVER")
MONGO_INITDB_ROOT_USERNAME = os.getenv("MONGO_INITDB_ROOT_USERNAME")
MONGO_INITDB_ROOT_PASSWORD = os.getenv("MONGO_INITDB_ROOT_PASSWORD")
DB_STAGING = os.getenv("DB_STAGING")
DB_FILES = os.getenv("DB_FILES")
DB_ANALYSE = os.getenv("DB_ANALYSE")
MONGO_URI = (
   f"mongodb://{MONGO_INITDB_ROOT_USERNAME}:{MONGO_INITDB_ROOT_PASSWORD}@{MONGO_SERVER}/?authSource=admin"
)
MONGO_STAGING_URI = (
   f"mongodb://{MONGO_INITDB_ROOT_USERNAME}:{MONGO_INITDB_ROOT_PASSWORD}@{MONGO_SERVER}/{DB_STAGING}?authSource=admin"
)
MONGO_FILES_URI = (
   f"mongodb://{MONGO_INITDB_ROOT_USERNAME}:{MONGO_INITDB_ROOT_PASSWORD}@{MONGO_SERVER}/{DB_FILES}?authSource=admin"
)
MONGO_ANALYSE_URI = (
   f"mongodb://{MONGO_INITDB_ROOT_USERNAME}:{MONGO_INITDB_ROOT_PASSWORD}@{MONGO_SERVER}/{DB_ANALYSE}?authSource=admin"
)

COLL_ANALYSE = os.getenv("COLL_ANALYSE")
COLL_ANALYSE_CLEAN = os.getenv("COLL_ANALYSE_CLEAN")
COLL_PLAATJES = os.getenv("COLL_PLAATJES")
COLL_FILENAMES = os.getenv("COLL_FILENAMES")

COLL_STAGING_METAINFO = os.getenv("COLL_STAGING_METAINFO")
COLL_STAGING_OUD = os.getenv("COLL_STAGING_OUD")
COLL_STAGING_MAGAZIJNLIJST = os.getenv("COLL_STAGING_MAGAZIJNLIJST")
COLL_STAGING_PROJECTENLIJST = os.getenv("COLL_STAGING_PROJECTENLIJST")
COLL_STAGING_MONSTER = os.getenv("COLL_STAGING_MONSTER")
COLL_STAGING_FOTOLIJST = os.getenv("COLL_STAGING_FOTOLIJST")
COLL_STAGING_REFERENTIETABELLEN = _leesTekst("COLL_STAGING_REFERENTIETABELLEN", 'Staging_Referentietabellen')
COLL_STAGING_RAPPORTEN = _leesTekst("COLL_STAGING_RAPPORTEN", 'Staging_Rapporten')
# Oude staging-collectie waar geen taak meer in schrijft; alleen nog gebruikt door de notebooks
COLL_STAGING_NIEUW = _leesTekst("COLL_STAGING_NIEUW", 'Staging_Projecten_Nieuw')
# Oude collectie in DB_ANALYSE; Drop_SingleStoreClean ruimt hem op als hij nog bestaat
COLL_ANALYSE_DOOS = _leesTekst("COLL_ANALYSE_DOOS", 'Def_Doos')

FLASK_PGPASSWORD = os.getenv("FLASK_PGPASSWORD")
FLASK_PGUSER = os.getenv("FLASK_PGUSER")
FLASK_PGDATABASE = os.getenv("FLASK_PGDATABASE")

MAIL_SERVER = os.getenv("MAIL_SERVER")
MAIL_USE_TLS = _leesBool("MAIL_USE_TLS", True)
MAIL_USERNAME = os.getenv("MAIL_USERNAME")
MAIL_PASSWORD = os.getenv("MAIL_PASSWORD")
MAIL_DEFAULT_SENDER = os.getenv("MAIL_DEFAULT_SENDER")

DEBUG_TB_PROFILER_ENABLED= True if os.getenv("DEBUG_TB_PROFILER_ENABLED") == 'True' else False

# Omgevingsvariabelen zijn altijd tekst; Flask-Caching (cachelib >= 0.14) eist getallen
CACHE_DEFAULT_TIMEOUT=int(os.getenv("CACHE_DEFAULT_TIMEOUT")) if os.getenv("CACHE_DEFAULT_TIMEOUT") else 300
CACHE_KEY_PREFIX=os.getenv("CACHE_KEY_PREFIX") if os.getenv("CACHE_KEY_PREFIX") else ''
CACHE_REDIS_HOST=os.getenv("CACHE_REDIS_HOST")
CACHE_REDIS_PASSWORD=os.getenv("CACHE_REDIS_PASSWORD")
REDIS_PASSWORD=os.getenv("REDIS_PASSWORD")
CACHE_REDIS_PORT=int(os.getenv("CACHE_REDIS_PORT")) if os.getenv("CACHE_REDIS_PORT") else 6379
CACHE_REDIS_DB=int(os.getenv("CACHE_REDIS_DB")) if os.getenv("CACHE_REDIS_DB") else 0

# Werkmap, logmap en harmonisatie-Excel van de pipeline; de standaardwaarden zijn de paden
# in de Airflow-image (de image maakt /opt/airflow/tmp aan) en in alle compose-bestanden.
# importMDB.sh leest AIRFLOW_TEMPDIR en AIRFLOW_LOGDIR zelf uit de omgeving, met dezelfde
# standaardwaarden.
AIRFLOW_TEMPDIR = _leesTekst("AIRFLOW_TEMPDIR", "/opt/airflow/tmp")
AIRFLOW_LOGDIR = _leesTekst("AIRFLOW_LOGDIR", "/opt/airflow/logs")
AIRFLOW_WASSTRAAT_CONFIG = _leesTekst("AIRFLOW_WASSTRAAT_CONFIG", "/opt/airflow/config/Wasstraat_Config_HarmonizeV3.xlsx")

AIRFLOW_INPUT_PROJECTEN = os.getenv("AIRFLOW_INPUT_PROJECTEN") if os.getenv("AIRFLOW_INPUT_PROJECTEN") else "/input/projecten"
AIRFLOW_INPUT_IMAGES = os.getenv("AIRFLOW_INPUT_IMAGES") if os.getenv("AIRFLOW_INPUT_IMAGES") else "/input/images"
AIRFLOW_INPUT_PROJECTENLIJST = os.getenv("AIRFLOW_INPUT_PROJECTENLIJST") if os.getenv("AIRFLOW_INPUT_PROJECTENLIJST") else "/input/projectenlijst"
AIRFLOW_INPUT_MAGAZIJNLIJST = os.getenv("AIRFLOW_INPUT_MAGAZIJNLIJST") if os.getenv("AIRFLOW_INPUT_MAGAZIJNLIJST") else "/input/magazijnlijst"
AIRFLOW_INPUT_FOTOLIJST = os.getenv("AIRFLOW_INPUT_FOTOLIJST") if os.getenv("AIRFLOW_INPUT_FOTOLIJST") else "/input/fotolijst"
AIRFLOW_INPUT_MONSTER = os.getenv("AIRFLOW_INPUT_MONSTER") if os.getenv("AIRFLOW_INPUT_MONSTER") else "/input/monsterdatabase"
AIRFLOW_INPUT_RAPPORTEN = os.getenv("AIRFLOW_INPUT_RAPPORTEN") if os.getenv("AIRFLOW_INPUT_RAPPORTEN") else "/input/rapporten"
AIRFLOW_CORRECTIES_CONFIG = os.getenv("AIRFLOW_CORRECTIES_CONFIG") if os.getenv("AIRFLOW_CORRECTIES_CONFIG") else "/opt/airflow/config/correcties.yml"


AIRFLOW_OUTPUT_MEDIA = os.getenv("AIRFLOW_OUTPUT_MEDIA") if os.getenv("AIRFLOW_OUTPUT_MEDIA") else "/output/archeomedia"

FILE_ABREXCEL = os.getenv("FILE_ABREXCEL") if os.getenv("FILE_ABREXCEL") else '/input/referentietabellen/abr_versie_01122018.xlsx'
FILE_EXTRA_PROJECTS = os.getenv("FILE_EXTRA_PROJECTS") if os.getenv("FILE_EXTRA_PROJECTS") else '/input/projectenlijst/Extra_projecten_tabel_OPGRAVINGEN.xlsx'
FILE_IMPORT_FILES_EXCEL = os.getenv("FILE_IMPORT_FILES_EXCEL") if os.getenv("FILE_IMPORT_FILES_EXCEL") else '/input/referentietabellen/Alle Bestanden Archeologisch Depot.xlsx'
ES_HOST = os.getenv("ES_HOST") if os.getenv("ES_HOST") else 'http://elasticsearch:9200'


# Drempels waarboven een reeks losse fouten de run alsnog stopt. Drempel = max(aantal,
# percentage van het totaal): het vaste aantal beschermt kleine verzamelingen, het
# percentage grote. Mislukte en onverwerkte afbeeldingen en rapporten (issue 70, taak
# Controleer_Afbeeldingen):
AIRFLOW_MAX_MISLUKTE_AFBEELDINGEN = _leesGetal("AIRFLOW_MAX_MISLUKTE_AFBEELDINGEN", 10, int)
AIRFLOW_MAX_MISLUKTE_AFBEELDINGEN_PCT = _leesGetal("AIRFLOW_MAX_MISLUKTE_AFBEELDINGEN_PCT", 1.0, float)
# Foutbeleid (issue 54). Onleesbare Access-databases (taak Controleer_Databases):
AIRFLOW_MAX_MISLUKTE_DATABASES = _leesGetal("AIRFLOW_MAX_MISLUKTE_DATABASES", 2, int)
AIRFLOW_MAX_MISLUKTE_DATABASES_PCT = _leesGetal("AIRFLOW_MAX_MISLUKTE_DATABASES_PCT", 5.0, float)
# Records die Transform 2 niet kon verwerken (collectie _processing_errors), per taak:
AIRFLOW_MAX_VERWERKINGSFOUTEN = _leesGetal("AIRFLOW_MAX_VERWERKINGSFOUTEN", 100, int)
AIRFLOW_MAX_VERWERKINGSFOUTEN_PCT = _leesGetal("AIRFLOW_MAX_VERWERKINGSFOUTEN_PCT", 1.0, float)

# Verwerkingsrapport (issue 62): map voor de rapporten (JSON en Markdown) per run. Is de map
# niet schrijfbaar, dan schrijft de taak Verwerkingsrapport in AIRFLOW_LOGDIR/rapporten.
AIRFLOW_OUTPUT_RAPPORTEN = os.getenv("AIRFLOW_OUTPUT_RAPPORTEN") if os.getenv("AIRFLOW_OUTPUT_RAPPORTEN") else "/output/rapporten"

# Gemeenteprofiel: bepaalt hoe bestandsnamen worden geparsed,
# projectcodes genormaliseerd, en rapportnummers afgeleid.
# Default: 'delft' voor backwards compatibility.
WASSTRAAT_GEMEENTE = os.getenv("WASSTRAAT_GEMEENTE") if os.getenv("WASSTRAAT_GEMEENTE") else "delft"

# Voorbeeldafbeelding (documenticoon) voor Word-documenten. Het icoon hoort bij de code,
# niet bij de brondata: standaard shared/afbeeldingen/document.png naast dit bestand, dus
# /opt/airflow/dags/shared/... in de Airflow-image en /app/app/shared/... in de Flask-image.
# De omgevingsvariabele FILE_WORD_ICON overschrijft het pad.
FILE_WORD_ICON = os.getenv("FILE_WORD_ICON") if os.getenv("FILE_WORD_ICON") else os.path.join(basedir, "afbeeldingen", "document.png")


CSRF_ENABLED = True
SECRET_KEY = os.getenv("SECRET_KEY")

# SQLALCHEMY_DATABASE_URI = "sqlite:///" + os.path.join(basedir, "app.db")
# SQLALCHEMY_DATABASE_URI = f'mysql://{MYSQL_USER}:{MYSQL_PASSWORD}@db/{MYSQL_DATABASE}'
# SQLALCHEMY_DATABASE_URI = 'mysql://myapp@localhost/myapp'
SQLALCHEMY_DATABASE_URI = f'postgresql://{FLASK_PGUSER}:{FLASK_PGPASSWORD}@postgres/{FLASK_PGDATABASE}'
SQLALCHEMY_TRACK_MODIFICATIONS = False
# SQLALCHEMY_ECHO = True

BABEL_DEFAULT_LOCALE = "en"

LANGUAGES = {
    "en": {"flag": "gb", "name": "English"},
    "pt": {"flag": "pt", "name": "Portuguese"},
    "es": {"flag": "es", "name": "Spanish"},
    "de": {"flag": "de", "name": "German"},
    "zh": {"flag": "cn", "name": "Chinese"},
    "ru": {"flag": "ru", "name": "Russian"},
}

# ------------------------------
# GLOBALS FOR GENERAL APP's
# ------------------------------
UPLOAD_FOLDER = basedir + "/app/static/uploads/"
IMG_UPLOAD_FOLDER = basedir + "/app/static/uploads/"
IMG_UPLOAD_URL = "/static/uploads/"
IMG_SIZE = (300, 200, True)
IMAGE_BIG_SIZE = (5000, 5000)

IMAGE_EXTENSIONS = [".jpg",".jpeg", ".gif",".png",".tif", ".psd", ".pdf", ".jp2", ".doc", ".docx"]
IMAGE_SIZE_THUMB = (300, 200)
IMAGE_SIZE_MIDDLE = (1500, 1000)
IMAGE_SIZE_BIGGEST = (7000, 7000)
IMAGE_SIZE_LZW = (15000, 15000)

AUTH_TYPE = 1
AUTH_ROLE_ADMIN = "Admin"
AUTH_ROLE_PUBLIC = "Public"
APP_NAME = "Wasstraat Archeologische Data"
APP_THEME = ""  # default
#APP_THEME = "cerulean.css"      # COOL
# APP_THEME = "amelia.css"
# APP_THEME = "cosmo.css"
# APP_THEME = "cyborg.css"       # COOL
# APP_THEME = "flatly.css"
# APP_THEME = "journal.css"
# APP_THEME = "readable.css"
# APP_THEME = "simplex.css"
# APP_THEME = "slate.css"          # COOL
# APP_THEME = "spacelab.css"      # NICE
# APP_THEME = "united.css"
