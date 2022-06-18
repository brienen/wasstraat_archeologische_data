import logging

from flask import Flask, request
from flask_appbuilder import AppBuilder, SQLA
from flask_migrate import Migrate
from flask_dropzone import Dropzone
from blueprints.gridfs_flask_blueprint import gridfs
from index import MyIndexView
from flask_debugtoolbar import DebugToolbarExtension
import config
from caching import cache
import init

logging.basicConfig(format="%(asctime)s:%(levelname)s:%(name)s:%(message)s")
logging.getLogger().setLevel(logging.INFO)


app = Flask(__name__)
app.config.from_object("config")
dropzone = Dropzone(app)

app.config['CACHE_TYPE'] = 'RedisCache'
cache.init_app(app)

app.config['DEBUG_TB_INTERCEPT_REDIRECTS'] = False
app.config['DEBUG_TB_PROFILER_ENABLED'] = config.DEBUG_TB_PROFILER_ENABLED
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {"pool_pre_ping": True}
toolbar = DebugToolbarExtension(app)

#geo_logger = logging.getLogger('fab_addon_geoalchemy')
#geo_logger.setLevel(logging.INFO)

app.register_blueprint(gridfs)

db = SQLA(app)
appbuilder = AppBuilder(app, db.session, base_template='mybase.html', indexview=MyIndexView)
migrate = Migrate(app, db) # this
#init.init()

import models, modelevents, views, route  # noqa

@app.before_request
def before_request_callback():
    method = request.method 
    path = request.path 

    print(f"before_request executing! {method} en path {path}")


