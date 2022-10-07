#from gevent import monkey
#monkey.patch_all()

from psycogreen.gevent import patch_psycopg
patch_psycopg()

from app import app  # re-export