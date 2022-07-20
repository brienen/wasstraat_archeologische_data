from jinja2 import TemplateNotFound
from flask import Flask, request, redirect, url_for, make_response, abort, Blueprint, render_template, current_app
#from werkzeug import secure_filename
from werkzeug.utils import secure_filename
from werkzeug.datastructures import  FileStorage
from werkzeug import Response

from pymongo import MongoClient
from bson.objectid import ObjectId

from gridfs import GridFS
from gridfs.errors import NoFile

import shared.config as config


gridfs = Blueprint('gridfs', __name__, url_prefix='/gridfs')

ALLOWED_EXTENSIONS = set(['txt', 'pdf', 'png', 'jpg', 'jpeg', 'gif'])
#DB = MongoClient(co.MONGO_URI).Arch_Files  # DB Name
#FS = GridFS(DB)

client = MongoClient(config.MONGO_URI, minPoolSize=config.MONGO_MINPOOLSIZE)


def allowed_file(filename):
    return '.' in filename and \
            filename.rsplit('.', 1)[1] in ALLOWED_EXTENSIONS




@gridfs.route('/getimage/<oid>')
def getimage(oid):
    try:
        FS = GridFS(client[config.DB_FILES])
        # Convert the string to an ObjectId instance
        #file_object = FS.get(ObjectId(oid))
        file = FS.get(ObjectId(oid))
        return Response(file, mimetype=file.content_type, direct_passthrough=True)
    except NoFile:
        abort(404)

