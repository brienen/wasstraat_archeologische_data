import os
import pymongo
import gridfs

from urllib.parse import urlparse
from flask_appbuilder import BaseView, expose, has_access
from flask import abort, Blueprint, flash, render_template, request, session, url_for
from app import appbuilder
from app import db
from .models import Foto, Artefact, Project
from app.util import shrinkAndSaveImage

import logging
logger = logging.getLogger()

from flask import current_app as app

class UploadView(BaseView):

    @expose("/fotos", methods=('POST', 'GET'))
    @has_access
    def uploads(self):

        strReq = str(request)
        logger.debug(f'Request: {strReq}')

        if request.method == 'POST':
            myclient = pymongo.MongoClient(str(app.config['MONGO_URI']))
            filesdb = myclient[str(app.config['DB_FILES'])]
            fs = gridfs.GridFS(filesdb)

            try:
                valid_images = [".jpg",".gif",".png",".tga", ".jpeg"]
                for key, f in request.files.items():
                    if key.startswith('file'):

                        #f.save(os.path.join('the/path/to/save', f.filename))
                        f = request.files.get('file')
                        filename, file_extension = os.path.splitext(f.filename)
                        if file_extension.lower() not in valid_images:
                            continue

                        
                        #Create new picture
                        foto = Foto()

                        #get info on last session
                        try:
                            page_hist = session['page_history']
                            if page_hist:
                                last_url = page_hist[-1]
                                urlp = urlparse(last_url)
                                if 'artefact' in urlp.query:
                                    foto.fototype = 'H'
                                    foto.artefactID = int(urlp.query.split("=")[1])
                                    try:
                                        artefact = db.session.query(Artefact).get(foto.artefactID)
                                        foto.artefact = artefact
                                        foto.projectID = artefact.projectID
                                        foto.project = artefact.project
                                    except Exception as err:
                                        logger.warning("Could not connect Artefact and/or project to photo while saving to artefactID " + foto.artefactID + " with message: " + err)
                                    
                                elif 'project' in urlp.query:
                                    foto.fototype = 'G' if 'opgraving' in urlp.path else 'F'                                    
                                    foto.projectID = int(urlp.query.split("=")[1])
                                    try:
                                        project = db.session.query(Project).get(foto.projectID)
                                        foto.project = project
                                    except Exception as err:
                                        logger.warning("Could not connect Artefact and/or project to photo while saving to projectid " + foto.projectID + " with message: " + err)

                                else:
                                    foto.fototype = 'N'
                        except:
                            foto.fototype = 'N'


                        imageUUID = shrinkAndSaveImage(f, filename, (5000,5000), fs)
                        imageMiddleUUID = shrinkAndSaveImage(f, f.filename, app.config['IMAGE_MIDDLE_SIZE'], fs)
                        imageThumbUUID = shrinkAndSaveImage(f, f.filename, app.config['IMAGE_THUMB_SIZE'], fs)

                        foto.fileName = f.filename
                        foto.fileType = file_extension
                        foto.directory = 'Handmatige Upload'
                        foto.directory = request.path
                        foto.imageUUID = str(imageUUID)
                        foto.imageMiddleUUID = str(imageMiddleUUID)
                        foto.imageThumbUUID = str(imageThumbUUID)
                        db.session.add(foto)
                        db.session.commit()

            except Exception as err:
                print(err)
                logger.error('Error while saving image with message: ' + str(err))
                db.session.rollback()
                raise
            finally:                
                #db.session.close()
                myclient.close()


        return 'upload template'


appbuilder.add_view_no_menu(UploadView)

