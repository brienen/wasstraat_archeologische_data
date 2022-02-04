import datetime
from flask import url_for, Markup
from flask_appbuilder.models.decorators import renders

from flask_appbuilder import Model
from flask_appbuilder.filemanager import ImageManager
from sqlalchemy import BigInteger, Column, Date, DateTime, Float, ForeignKey, Integer, LargeBinary, String, Table, Text, Boolean, JSON, UniqueConstraint, text
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy import select, func
from sqlalchemy.ext.hybrid import hybrid_property, hybrid_method
from flask_appbuilder.models.mixins import ImageColumn
from fab_addon_geoalchemy.views import GeoModelView
from fab_addon_geoalchemy.models import GeoSQLAInterface, Geometry

from sqlalchemy.schema import CreateColumn
from sqlalchemy.ext.compiler import compiles


mindate = datetime.date(datetime.MINYEAR, 1, 1)
metadata = Model.metadata


class Stelling(Model):
    __tablename__ = 'Def_Stelling'

    primary_key = Column(Integer, primary_key=True, autoincrement=True)
    uuid = Column('_id', String(40))
    herkomst = Column(Text)
    inhoud = Column(Text)
    soort = Column(String(80))
    stelling = Column(String(1))
    brondata = Column(Text)
    herkomst = Column(Text)

    def __repr__(self):
        return str(self.stelling) + ' ('+ str(self.inhoud) + ')'


class Vindplaats(Model):
    __tablename__ = 'Def_Vindplaats'

    primary_key = Column(Integer, primary_key=True, autoincrement=True)
    uuid = Column('_id', String(40))
    aard = Column(Text)
    begindatering = Column(Text)
    datering = Column(Text)
    depot = Column(Text)
    documentatie = Column(Text)
    einddatering = Column(Text)
    gemeente = Column(Text)
    mobilia = Column(Text)
    onderzoek = Column(Text)
    projectcd = Column(String(12))
    soort = Column(String(80))
    table = Column(String(40))
    vindplaats = Column(String(200))
    xcoor_rd = Column(Float(53))
    ycoor_rd = Column(Float(53))
    brondata = Column(Text)


class Observation(Model):
    id = Column(Integer, primary_key=True)
    name = Column(String)
    location = Column(Geometry(geometry_type='POINT', srid=4326))

    def __repr__(self):
        if self.name:
            return self.name
        else:
            return 'Person Type %s' % self.id

class Project(Model):
    __tablename__ = 'Def_Project'

    primary_key = Column(Integer, primary_key=True, autoincrement=True)
    projectcd = Column(String(12), nullable=False)
    projectnaam = Column(String(200))
    jaar = Column(Integer)
    toponiem = Column(String(200))
    trefwoorden = Column(String(200))
    location = Column(Geometry('POINT', srid=4326), default=(52.00667, 4.35556)) # 52.00667, 4.35556.
    uuid = Column('_id', String(40))
    soort = Column(String(80))
    xcoor_rd = Column(Float)
    ycoor_rd = Column(Float)
    longitude = Column(Float)
    latitude = Column(Float)
    brondata = Column(Text)
    herkomst = Column(String(200))
    artefacten = relationship("Artefact", back_populates="project")

    @hybrid_method
    def aantalArtefacten(self):
        return len(self.artefacten)

    def __repr__(self):
        if self.projectcd:
            return str(self.projectcd) + ' (' + str(self.projectnaam) + ')'
        else:
            return None

class Doos(Model):
    __tablename__ = 'Def_Doos'

    primary_key = Column(Integer, primary_key=True, autoincrement=True)
    uuid = Column('_id', String(40))
    doosnr = Column(Integer)
    inhoud = Column(Text)
    projectcd = Column(String(12))
    projectnaam = Column(Text)
    stelling = Column(Text)
    uitgeleend = Column(Integer)
    vaknr = Column(Integer)
    volgletter = Column(Text)
    stellingID = Column(ForeignKey('Def_Stelling.primary_key'), index=True)
    stelling = relationship('Stelling')
    projectID = Column(ForeignKey('Def_Project.primary_key'), index=True)
    project = relationship('Project')
    stellingID = Column(ForeignKey('Def_Stelling.primary_key'), index=True)
    stelling = relationship('Stelling')
    artefacten = relationship("Artefact", back_populates="doos")

    def __repr__(self):
        return str(self.doosnr) + ' ('+ str(self.projectcd) + ')'

    @hybrid_method
    def aantalArtefacten(self):
        return len(self.artefacten)

class Put(Model):
    __tablename__ = 'Def_Put'

    primary_key = Column(Integer, primary_key=True, autoincrement=True)
    putnr = Column(Integer)
    projectID = Column(ForeignKey('Def_Project.primary_key'), index=True)
    project = relationship('Project')

    def __repr__(self):
        return self.project.projectcd + ' Put ' + str(self.putnr)


class Spoor(Model):
    __tablename__ = 'Def_Spoor'

    primary_key = Column(Integer, primary_key=True, autoincrement=True)
    vlaknr = Column(String(40))
    spoornr = Column(Integer)
    projectID = Column(ForeignKey('Def_Project.primary_key'), index=True)
    project = relationship('Project')
    putID = Column(ForeignKey('Def_Put.primary_key'), index=True)
    put = relationship('Put')


class Vondst(Model):
    __tablename__ = 'Def_Vondst'

    primary_key = Column(Integer, primary_key=True, autoincrement=True)
    vlaknr = Column(String(40))
    vondstnr = Column(Integer)
    inhoud = Column(String(200))
    omstandigheden = Column(Text)
    datum = Date()
    dateringvanaf = Column(Integer)
    dateringtot = Column(Integer)
    datering = Column(String(200))
    uuid = Column('_id', String(40), nullable=False, unique=True)
    brondata = Column(Text)
    herkomst = Column(String(200))

    projectID = Column(ForeignKey('Def_Project.primary_key'), index=True)
    project = relationship('Project')
    putID = Column(ForeignKey('Def_Put.primary_key'), index=True)
    put = relationship('Put')

    def __repr__(self):
        vondstnr = (' Vondstnr ' + str(self.vondstnr)) if self.vondstnr else ''
        put = (' Put ' + str(self.put.putnr)) if self.put else ''

        return self.project.projectcd + put + vondstnr

class Artefact(Model):
    __tablename__ = 'Def_Artefact'

    primary_key = Column(Integer, primary_key=True, autoincrement=True)
    artefactnr = Column(Integer)
    beschrijving = Column(Text)
    opmerkingen = Column(Text)
    typevoorwerp = Column(String(200))
    typecd = Column(String(40))
    functievoorwerp = Column(String(40))
    origine = Column(String(200))
    dateringvanaf = Column(Integer)
    dateringtot = Column(Integer)
    datering = Column(String(200))
    conserveren = Column(Integer)
    exposabel = Column(Integer)
    literatuur = Column(String(200))
    putnr = Column(Integer)
    restauratie = Column(Integer)
    soort = Column(String(80))
    uuid = Column('_id', String(40))
    brondata = Column(Text)
    herkomst = Column(Text)
    projectID = Column(ForeignKey('Def_Project.primary_key'), index=True)
    project = relationship('Project')
    putID = Column(ForeignKey('Def_Put.primary_key'), index=True)
    put = relationship('Put')
    vondstID = Column(ForeignKey('Def_Vondst.primary_key'), index=True)
    vondst = relationship('Vondst')
    doosID = Column(ForeignKey('Def_Doos.primary_key'), index=True)
    doos = relationship('Doos')
    #fotos = relationship("Foto", back_populates="artefact")

    def __repr__(self):
        if self.project:
            artefactnr = (' Artf. ' + str(self.artefactnr)) if self.artefactnr else ''
            put = (' Put ' + str(self.put.putnr)) if self.put else ''
            typecd = (' Typecd. ' + str(self.typecd)) if self.typecd else ''
            return self.project.projectcd + put + artefactnr +  typecd
        else:
            return ''

    @hybrid_method
    def vindplaats(self):
        if self.doos:
            stelling = (str(self.doos.stelling)) if self.doos else ''
            vaknr = (str(self.doos.vaknr)) if self.doos else ''
            doosnr = (str(self.doos.doosnr)) if self.doos else ''

            return f'Stelling: {stelling}, Vaknr.{vaknr}, Doosnr.{doosnr}'
        else:
            return ''



class Foto(Model):
    __tablename__ = 'Def_Foto'

    primary_key = Column(Integer, primary_key=True, autoincrement=True)
    uuid = Column('_id', String(40))
    artefactnr = Column(Text)
    directory = Column(Text)
    fileName = Column(Text)
    fileSize = Column(Integer)
    fileType = Column(String(32))
    fotonr = Column(Text)
    fotosubnr = Column(Text)
    fototype = Column(Text)
    imageUUID = Column(String(40))
    imageMiddleUUID = Column(String(40))
    imageThumbUUID = Column(String(40))
    mime_type = Column(String(20))
    projectcd = Column(String(12))
    putnr = Column(Text)
    soort = Column(String(80))
    vondstnr = Column(Text)
    photo = Column(ImageColumn(size=(1500, 1000, True), thumbnail_size=(300, 200, True)))

    @renders('custom')
    def photo_img(self):
        if self.imageMiddleUUID:
            return Markup('<a href=/gridfs/getimage/' + self.imageUUID +\
             '><img src="/gridfs/getimage/' + self.imageMiddleUUID +\
              '" alt="Photo" class="img-rounded img-responsive"></a>')
        else:
            return Markup('<a href="' + url_for('ArchFotoView.show',pk=str(self.primary_key)) +\
             '" class="thumbnail"><img src="//:0" alt="Photo" class="img-responsive"></a>')


    @renders('custom')
    def photo_img_middle(self):
        if self.imageMiddleUUID:
            return Markup('<a href="' + url_for('ArchFotoView.show',pk=str(self.primary_key)) +\
             '"><img src="/gridfs/getimage/' + self.imageMiddleUUID +\
              '" alt="Photo" class="img-rounded img-responsive" style="max-height:70vh"></a>')
        else:
            return Markup('<a href="' + url_for('ArchFotoView.show',pk=str(self.primary_key)) +\
             '" class="thumbnail"><img src="//:0" alt="Photo" class="img-responsive"></a>')


    @renders('custom')
    def photo_img_thumbnail(self):
        if self.imageThumbUUID:
            return Markup('<a href="' + url_for('ArchFotoView.show',pk=str(self.primary_key)) +\
             '" class="thumbnail"><img src="/gridfs/getimage/' + self.imageThumbUUID +\
              '" alt="Photo" class="img-rounded img-responsive"></a>')
        else:
            return Markup('<a href="' + url_for('ArchFotoView.show',pk=str(self.primary_key)) +\
             '" class="thumbnail"><img src="//:0" alt="Photo" class="img-responsive"></a>')

    @renders('custom')
    def koppeling(self): 
        project = self.projectcd if self.projectcd else ''
        put = (', Put ' + str(self.putnr)) if self.putnr else ''
        art = (', Art. ' + str(self.artefactnr)) if self.artefactnr else ''
        desc = project + put + art
        if self.artefact:
            return Markup('<a href="' + url_for('ArchArtefactView.show',pk=str(self.artefact.primary_key)) + '">Artefact: '+desc+'</a>')
        else:
            return desc

    projectID = Column(ForeignKey('Def_Project.primary_key'), index=True)
    project = relationship('Project')
    artefactID = Column(ForeignKey('Def_Artefact.primary_key'), index=True)
    artefact = relationship('Artefact', backref="fotos")



table_foto = metadata.tables['Def_Foto']
#select_foto_zonder = select([table_foto]).where(table_foto.c.artefact == None).alias()
#select_foto_zonder = select([table_foto.c.primary_key]).alias()
#class Foto_Ongekoppeld(Model):
#    __table__ = select_foto_zonder


class Standplaats(Model):
    __tablename__ = 'Def_Standplaats'

    primary_key = Column(Integer, primary_key=True, autoincrement=True)
    uuid = Column('_id', String(40))
    doosnr = Column(Integer)
    herkomst_0 = Column('herkomst.0', Text)
    inhoud = Column(Text)
    projectcd = Column(String(12))
    projectnaam = Column(Text)
    stelling = Column(Text)
    uitgeleend = Column(Integer)
    vaknr = Column(Integer)
    volgletter = Column(Text)


class Plaatsing(Model):
    __tablename__ = 'Def_Plaatsing'

    primary_key = Column(Integer, primary_key=True, autoincrement=True)
    uuid = Column('_id', String(40))
    doosnr = Column(Integer)
    herkomst_0 = Column('herkomst.0', Text)
    inhoud = Column(Text)
    projectcd = Column(String(12))
    projectnaam = Column(Text)
    stelling = Column(Text)
    table = Column(String(40))
    uitgeleend = Column(Integer)
    vaknr = Column(Integer)
    volgletter = Column(Text)
    brondata = Column(Text)










class Vlak(Model):
    __tablename__ = 'Def_Vlak'

    primary_key = Column(Integer, primary_key=True, autoincrement=True)
    uuid = Column('_id', String(40))
    putnr = Column(Integer)
    vlaknr = Column(Text)


class Person(Model):
    id = Column(Integer, primary_key=True)
    name = Column(String(150), unique = True, nullable=False)


class ContactGroup(Model):
    id = Column(Integer, primary_key=True)
    name = Column(String(50), unique=True, nullable=False)

    def __repr__(self):
        return self.name


class Gender(Model):
    id = Column(Integer, primary_key=True)
    name = Column(String(50), unique=True, nullable=False)

    def __repr__(self):
        return self.name


class Contact(Model):
    id = Column(Integer, primary_key=True)
    name = Column(String(150), unique=True, nullable=False)
    address = Column(String(564))
    birthday = Column(Date, nullable=True)
    personal_phone = Column(String(20))
    personal_celphone = Column(String(20))
    contact_group_id = Column(Integer, ForeignKey("contact_group.id"), nullable=False)
    contact_group = relationship("ContactGroup")
    gender_id = Column(Integer, ForeignKey("gender.id"), nullable=False)
    gender = relationship("Gender")

    def __repr__(self):
        return self.name

    def month_year(self):
        date = self.birthday or mindate
        return datetime.datetime(date.year, date.month, 1) or mindate

    def year(self):
        date = self.birthday or mindate
        return datetime.datetime(date.year, 1, 1)


