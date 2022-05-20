import logging

from werkzeug.middleware.dispatcher import DispatcherMiddleware
from flask import Flask
from flask_appbuilder import AppBuilder, SQLA
from flask_migrate import Migrate
from flask_dropzone import Dropzone
from app.blueprints.gridfs_flask_blueprint import gridfs
from app.index import MyIndexView
from flask_debugtoolbar import DebugToolbarExtension
import config

logging.basicConfig(format="%(asctime)s:%(levelname)s:%(name)s:%(message)s")
logging.getLogger().setLevel(logging.WARNING)

app = Flask(__name__)
app.config.from_object("config")
dropzone = Dropzone(app)

app.config['DEBUG_TB_INTERCEPT_REDIRECTS'] = False
app.config['DEBUG_TB_PROFILER_ENABLED'] = config.DEBUG_TB_PROFILER_ENABLED
toolbar = DebugToolbarExtension(app)

geo_logger = logging.getLogger('fab_addon_geoalchemy')
geo_logger.setLevel(logging.INFO)

app.register_blueprint(gridfs)

db = SQLA(app)
appbuilder = AppBuilder(app, db.session, base_template='mybase.html', indexview=MyIndexView)
migrate = Migrate(app, db) # this

from . import models, views, api, route  # noqa


