from jinja2 import TemplateNotFound
from flask import Flask, request, redirect, url_for, make_response, abort, Blueprint, render_template, current_app
#from werkzeug import secure_filename
from werkzeug.utils import secure_filename
from werkzeug.datastructures import  FileStorage

from pymongo import MongoClient
from bson.objectid import ObjectId

from gridfs import GridFS
from gridfs.errors import NoFile

import config as co


gridfs = Blueprint('gridfs', __name__, url_prefix='/gridfs')

ALLOWED_EXTENSIONS = set(['txt', 'pdf', 'png', 'jpg', 'jpeg', 'gif'])
DB = MongoClient(co.MONGO_URI).Arch_Files  # DB Name
FS = GridFS(DB)


def allowed_file(filename):
    return '.' in filename and \
            filename.rsplit('.', 1)[1] in ALLOWED_EXTENSIONS




@gridfs.route('/getimage/<oid>')
def getimage(oid):
    try:
        # Convert the string to an ObjectId instance
        file_object = FS.get(ObjectId(oid))
        response = make_response(file_object.read())
        response.mimetype = file_object.content_type
        return response
    except NoFile:
        abort(404)

