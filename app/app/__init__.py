import logging

from werkzeug.middleware.dispatcher import DispatcherMiddleware
from flask import Flask
from flask_appbuilder import AppBuilder, SQLA
from flask_migrate import Migrate
from flask_dropzone import Dropzone
from app.blueprints.gridfs_flask_blueprint import gridfs
from app.index import MyIndexView
from flask_debugtoolbar import DebugToolbarExtension
import dash
from app.cockpit.dash_cockpit import layout
from app.cockpit.dash_cockpit import register_callbacks
from app.cockpit.dash_cockpit import external_stylesheets, external_scripts

logging.basicConfig(format="%(asctime)s:%(levelname)s:%(name)s:%(message)s")
logging.getLogger().setLevel(logging.INFO)

app = Flask(__name__)
app.config.from_object("config")
dropzone = Dropzone(app)

#dashapp = dash.Dash(
#    __name__,
#    server=app,
#    external_stylesheets=external_stylesheets,
#    external_scripts=external_scripts,
#    routes_pathname_prefix='/cockpit/'
#)
#dashapp.layout = layout
#register_callbacks(dashapp)


app.config['DEBUG_TB_INTERCEPT_REDIRECTS'] = False
toolbar = DebugToolbarExtension(app)

geo_logger = logging.getLogger('fab_addon_geoalchemy')
geo_logger.setLevel(logging.INFO)

app.register_blueprint(gridfs)

db = SQLA(app)
appbuilder = AppBuilder(app, db.session, base_template='mybase.html', indexview=MyIndexView)
migrate = Migrate(app, db) # this

from . import models, views, api, route  # noqa


