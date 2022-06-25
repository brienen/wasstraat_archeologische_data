import os
import logging

logger = logging.getLogger()
basedir = os.path.abspath(os.path.dirname(__file__))

try:  
   POSTGRES_DB= os.environ["POSTGRES_DB"]
   POSTGRES_USER= os.environ["POSTGRES_USER"]
   POSTGRES_PASSWORD= os.environ["POSTGRES_PASSWORD"]

   MONGO_SERVER = os.getenv("MONGO_SERVER")
   MONGO_INITDB_ROOT_USERNAME = os.getenv("MONGO_INITDB_ROOT_USERNAME")
   MONGO_INITDB_ROOT_PASSWORD = os.getenv("MONGO_INITDB_ROOT_PASSWORD")
   DB_STAGING = os.getenv("DB_STAGING")
   DB_FILES = os.getenv("DB_FILES")
   DB_ANALYSE = os.getenv("DB_ANALYSE")
   MONGO_URI = (
      f"mongodb://{MONGO_INITDB_ROOT_USERNAME}:{MONGO_INITDB_ROOT_PASSWORD}@{MONGO_SERVER}/"
   )
   MONGO_STAGING_URI = (
      f"mongodb://{MONGO_INITDB_ROOT_USERNAME}:{MONGO_INITDB_ROOT_PASSWORD}@{MONGO_SERVER}/{DB_STAGING}"
   )
   MONGO_FILES_URI = (
      f"mongodb://{MONGO_INITDB_ROOT_USERNAME}:{MONGO_INITDB_ROOT_PASSWORD}@{MONGO_SERVER}/{DB_FILES}"
   )
   MONGO_ANALYSE_URI = (
      f"mongodb://{MONGO_INITDB_ROOT_USERNAME}:{MONGO_INITDB_ROOT_PASSWORD}@{MONGO_SERVER}/{DB_ANALYSE}"
   )
   MONGO_MINPOOLSIZE = 50 if not os.getenv("MONGO_MINPOOLSIZE") else os.getenv("MONGO_MINPOOLSIZE")

   COLL_ANALYSE = os.getenv("COLL_ANALYSE")
   COLL_ANALYSE_CLEAN = os.getenv("COLL_ANALYSE_CLEAN") 
   COLL_PLAATJES = os.getenv("COLL_PLAATJES")

   COLL_STAGING_METAINFO = os.getenv("COLL_STAGING_METAINFO")
   COLL_STAGING_OUD = os.getenv("COLL_STAGING_OUD")
   COLL_STAGING_NIEUW = os.getenv("COLL_STAGING_NIEUW")
   COLL_STAGING_MAGAZIJNLIJST = os.getenv("COLL_STAGING_MAGAZIJNLIJST")
   COLL_STAGING_DELFIT = os.getenv("COLL_STAGING_DELFIT")
   COLL_STAGING_DIGIFOTOS = os.getenv("COLL_STAGING_DIGIFOTOS")
   COLL_ANALYSE_FOTO = os.getenv("COLL_ANALYSE_FOTO")
   COLL_ANALYSE_ARTEFACT = os.getenv("COLL_ANALYSE_ARTEFACT")
   COLL_ANALYSE_PROJECT = os.getenv("COLL_ANALYSE_PROJECT")
   COLL_ANALYSE_VONDST = os.getenv("COLL_ANALYSE_VONDST")
   COLL_ANALYSE_SPOOR = os.getenv("COLL_ANALYSE_SPOOR")
   COLL_ANALYSE_VLAK = os.getenv("COLL_ANALYSE_VLAK")
   COLL_ANALYSE_PUT = os.getenv("COLL_ANALYSE_PUT")
   COLL_ANALYSE_DOOS = os.getenv("COLL_ANALYSE_DOOS")
   COLL_ANALYSE_STANDPLAATS = os.getenv("COLL_ANALYSE_STANDPLAATS")
   COLL_ANALYSE_STELLING = os.getenv("COLL_ANALYSE_STELLING")
   COLL_ANALYSE_PLAATSING = os.getenv("COLL_ANALYSE_PLAATSING")
   COLL_ANALYSE_VINDPLAATS = os.getenv("COLL_ANALYSE_VINDPLAATS")

   FLASK_PGPASSWORD = os.getenv("FLASK_PGPASSWORD")
   FLASK_PGUSER = os.getenv("FLASK_PGUSER")
   FLASK_PGDATABASE = os.getenv("FLASK_PGDATABASE")

   MAIL_SERVER = os.getenv("MAIL_SERVER")
   MAIL_USE_TLS= True
   MAIL_USERNAME = os.getenv("MAIL_USERNAME")
   MAIL_PASSWORD = os.getenv("MAIL_PASSWORD")
   MAIL_DEFAULT_SENDER = os.getenv("MAIL_DEFAULT_SENDER")

   DEBUG_TB_PROFILER_ENABLED= True if os.getenv("DEBUG_TB_PROFILER_ENABLED") == 'True' else False

   CACHE_DEFAULT_TIMEOUT=os.getenv("CACHE_DEFAULT_TIMEOUT") if os.getenv("CACHE_DEFAULT_TIMEOUT") else 300
   CACHE_KEY_PREFIX=os.getenv("CACHE_KEY_PREFIX") if os.getenv("CACHE_KEY_PREFIX") else ''
   CACHE_REDIS_HOST=os.getenv("CACHE_REDIS_HOST")
   CACHE_REDIS_PASSWORD=os.getenv("CACHE_REDIS_PASSWORD")   
   REDIS_PASSWORD=os.getenv("REDIS_PASSWORD")
   CACHE_REDIS_PORT=os.getenv("CACHE_REDIS_PORT") if os.getenv("CACHE_REDIS_PORT") else 6379
   CACHE_REDIS_DB=os.getenv("CACHE_REDIS_DB") if os.getenv("CACHE_REDIS_DB") else 0


except KeyError: 
   logger.error("Cannot read environment variables (ie. POSTGRES_DB, POSTGRES_USER, POSTGRES_PASSWORD) needed to connect to the database. Add them to your .env files")



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
IMAGE_SIZE_THUMB = (300, 200)
IMAGE_SIZE_MIDDLE = (500, 500)
IMAGE_SIZE_BIGGEST = (5000, 5000)
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
