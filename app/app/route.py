import os
from urllib.parse import urlparse
from flask_appbuilder import BaseView, expose, has_access
from flask import request, session
from app import appbuilder
from app import db
from models import Bestand, Artefact, Project, Objectfoto, Veldtekening , Opgravingsfoto, Overige_foto, Overige_tekening, Objecttekening
from shared import const
import shared.config as config
import shared.image_util as image_util
from PIL import Image
from flask import redirect
import pdf2image
from flask import current_app


def makeRelative(path: str):
    if path.startswith(os.sep):
        return path[1:]
    else:
        return path 



class UploadView(BaseView):

    @expose("/fotos", methods=('POST', 'GET'))
    @has_access
    def uploads(self):

        strReq = str(request)
        current_app.logger.info(f'Request: {strReq}')
        dir = os.sep + "Onbekend Project" + os.sep

        if request.method == 'POST':
            try:
                valid_images = config.IMAGE_EXTENSIONS
                for key, f in request.files.items():
                    if key.startswith('file'):

                        filename = f.filename
                        filename_noext, file_extension = os.path.splitext(filename)
                        if file_extension.lower() not in valid_images:
                            continue
                    
                        #get info on last session
                        page_hist = session['page_history']
                        if page_hist:
                            last_url = page_hist[-1]
                            urlp = urlparse(last_url)
                            current_app.logger.info(f"Page history: {urlp}")
                            if 'project' in urlp.query:
                                projectID = int(urlp.query.split("=")[1])
                                project = db.session.query(Project).get(projectID)
                                dir = os.sep + project.projectcd + '_' + project.projectnaam + os.sep 

                                if 'objectfoto' in urlp.path.lower():
                                    foto = Objectfoto()
                                    dir = dir + 'objectfoto' + os.sep 
                                elif 'opgravingfoto' in urlp.path.lower():
                                    foto = Opgravingsfoto()
                                    dir = dir + 'opgravingfoto' + os.sep 
                                elif 'velddocument' in urlp.path.lower():
                                    foto = Veldtekening ()
                                    dir = dir + 'velddocument' + os.sep 
                                elif 'objecttekening' in urlp.path.lower():
                                    foto = Objecttekening()
                                    dir = dir + 'objecttekening' + os.sep 
                                elif 'overigetekening' in urlp.path.lower():
                                    foto = Overige_tekening()
                                    dir = dir + 'overigetekening' + os.sep 
                                elif 'overige' in urlp.path.lower():
                                    foto = Overige_foto()                                        
                                    dir = dir + 'overige' + os.sep 
                                else:
                                    foto = Bestand()
                                    dir = dir + 'overige' + os.sep 

                                foto.project = project
                            elif 'artefact' in urlp.query:
                                foto = Objectfoto()
                                foto.artefactID = int(urlp.query.split("=")[1])
                                foto.artefact = db.session.query(Artefact).get(foto.artefactID)
                                foto.project = foto.artefact.project                                    
                                dir = dir + 'objectfoto' + os.sep 
                            else:
                                foto = Bestand()
                                dir = dir + 'overige' + os.sep 

                        else:
                            foto = Bestand()
                            dir = dir + 'overige' + os.sep 


                        mime_type = 'image/jpeg'
                        filetype = '.jpg'
                        fullfilename = os.path.join(config.AIRFLOW_OUTPUT_MEDIA, makeRelative(dir), filename)
                        if 'pdf' in file_extension.lower():
                            mime_type = 'application/pdf'
                            filetype = '.pdf'
                            f.save(fullfilename)
                            images = pdf2image.convert_from_path(fullfilename)
                            image = images[0]
                            imageThumbID, imageMiddleID, imageID = image_util.putImageInGrid(image, fullfilename, None, dir, "project", filetype='.pdf')
                        elif file_extension.lower() == '.docx':
                            image = Image.open(config.FILE_WORD_ICON)
                            imageThumbID, imageMiddleID, imageID = image_util.putImageInGrid(image, fullfilename, None, dir, "project", filetype='.docx')    
                            mime_type = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
                            filetype = '.docx'
                            f.save(fullfilename)
                        elif file_extension.lower() == '.doc':
                            image = Image.open(config.FILE_WORD_ICON)
                            imageThumbID, imageMiddleID, imageID = image_util.putImageInGrid(image, fullfilename, None, dir, "project", filetype='.doc')    
                            mime_type = 'application/msword'
                            filetype = '.doc'
                            f.save(fullfilename)
                        else:
                            image = Image.open(request.files['file'].stream)
                            imageThumbID, imageMiddleID, imageID = image_util.putImageInGrid(image, fullfilename, None, dir, "project")

                        foto.fileName = f.filename
                        foto.mime_type = mime_type
                        foto.fileType = filetype
                        foto.directory = dir
                        foto.imageID = str(imageID)
                        foto.imageMiddleID = str(imageMiddleID)
                        foto.imageThumbID = str(imageThumbID)
                        db.session.add(foto)
                        db.session.commit()

            except Exception as err:
                print(err)
                current_app.logger.error('Error while saving image with message: ' + str(err))
                db.session.rollback()
                raise

        redirect_page = page_hist[-3]
        return redirect(redirect_page, code=302)


appbuilder.add_view_no_menu(UploadView)

