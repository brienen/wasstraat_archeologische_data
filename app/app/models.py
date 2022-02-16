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


class WasstraatModel(Model):
    __abstract__ = True

    herkomst = Column(Text)
    key = Column(Text)
    soort = Column(String(80))
    brondata = Column(Text)
    uuid = Column('_id', String(40))

class Stelling(WasstraatModel):
    __tablename__ = 'Def_Stelling'

    primary_key = Column(Integer, primary_key=True, autoincrement=True)
    uuid = Column('_id', String(40))
    inhoud = Column(Text)
    stelling = Column(String(1))
    
    def __repr__(self):
        return str(self.stelling) + ' ('+ str(self.inhoud) + ')'


class Vindplaats(WasstraatModel):
    __tablename__ = 'Def_Vindplaats'

    primary_key = Column(Integer, primary_key=True, autoincrement=True)
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
    vindplaats = Column(String(200))
    xcoor_rd = Column(Float(53))
    ycoor_rd = Column(Float(53))
    


class Observation(WasstraatModel):
    id = Column(Integer, primary_key=True)
    name = Column(String)
    location = Column(Geometry(geometry_type='POINT', srid=4326))

    def __repr__(self):
        if self.name:
            return self.name
        else:
            return 'Person Type %s' % self.id

class Project(Model): # Inherit from Model for cannot use Abstract class Wasstraatmodel, for geo-package gives errors
    __tablename__ = 'Def_Project'

    primary_key = Column(Integer, primary_key=True, autoincrement=True)
    projectcd = Column(String(12), nullable=False)
    projectnaam = Column(String(200))
    jaar = Column(Integer)
    toponiem = Column(String(200))
    trefwoorden = Column(String(200))
    location = Column(Geometry('POINT', srid=4326), default=(52.00667, 4.35556)) # 52.00667, 4.35556.
    xcoor_rd = Column(Float)
    ycoor_rd = Column(Float)
    longitude = Column(Float)
    latitude = Column(Float)
    artefacten = relationship("Artefact", back_populates="project")

    # Explicit defined for cannot use Abstract class Wasstraatmodel, for geo-package gives errors
    herkomst = Column(Text)
    soort = Column(String(80))
    brondata = Column(Text)
    uuid = Column('_id', String(40))
    key = Column(Text)

    @hybrid_method
    def aantalArtefacten(self):
        return len(self.artefacten)

    def __repr__(self):
        if self.projectcd:
            return str(self.projectcd) + ' (' + str(self.projectnaam) + ')'
        else:
            return None

class Doos(WasstraatModel):
    __tablename__ = 'Def_Doos'

    primary_key = Column(Integer, primary_key=True, autoincrement=True)
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

class Put(WasstraatModel):
    __tablename__ = 'Def_Put'

    primary_key = Column(Integer, primary_key=True, autoincrement=True)
    putnr = Column(Integer)
    beschrijving = Column(Text)
    aangelegd = Column(Boolean)
    datum_ingevoerd = Column(Text)
    datum_gewijzigd = Column(Text)
    projectID = Column(ForeignKey('Def_Project.primary_key', deferrable=True), index=True)
    project = relationship('Project')

    def __repr__(self):
        beschr = str(self.beschrijving) if self.beschrijving else ""

        return self.project.projectcd + ' Put ' + str(self.putnr) + ' ' + beschr


class Spoor(WasstraatModel):
    __tablename__ = 'Def_Spoor'

    primary_key = Column(Integer, primary_key=True, autoincrement=True)
    vlaknr = Column(String(40))
    spoornr = Column(Integer)
    aard = Column(String(200))
    beschrijving = Column(Text)
    gecoupeerd =  Column(Text)
    coupnrs =   Column(Text)
    afgewerkt = Column(Text)
    dateringvanaf = Column(Integer)
    dateringtot = Column(Integer)
    datering = Column(String(200))
    vorm = Column(String(200))
    diepte = Column(String(200))
    breedte_bovenkant= Column(String(200))
    lengte_bovenkant= Column(String(200))
    hoogte_bovenkant= Column(String(200))
    hoogte_onderkant= Column(String(200))
    breedte_onderkant= Column(String(200))
    onderkant_NAP = Column(String(200))
    profiel = Column(String(200))
    richting = Column(String(200))
    steenformaat = Column(String(200))
    metselverband = Column(String(200))
    steenformaat = Column(String(200))
    jonger_dan = Column(String(200))
    ouder_dan = Column(String(200))
    sporen_zelfde_periode = Column(String(200))
    projectID = Column(ForeignKey('Def_Project.primary_key', deferrable=True), index=True)
    project = relationship('Project')
    putID = Column(ForeignKey('Def_Put.primary_key', deferrable=True), index=True)
    put = relationship('Put')
    vlakID = Column(ForeignKey('Def_Vlak.primary_key', deferrable=True), index=True)
    vlak = relationship('Vlak')

    def __repr__(self):
        put = (' Put ' + str(self.put.putnr)) + " " if self.put else ''
        beschr = str(self.beschrijving) if str(self.beschrijving) else ""

        return self.project.projectcd + put + ' Spoor ' + str(self.spoornr) + ' ' + beschr


class Vondst(WasstraatModel):
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
    segment = Column(String(200))
    vaknummer = Column(String(200))
    verzamelwijze = Column(String(200))
    vullingnr = Column(String(200)) 
    projectID = Column(ForeignKey('Def_Project.primary_key', deferrable=True), index=True)
    project = relationship('Project')
    putID = Column(ForeignKey('Def_Put.primary_key', deferrable=True), index=True)
    put = relationship('Put')
    spoorID = Column(ForeignKey('Def_Spoor.primary_key', deferrable=True), index=True)
    spoor = relationship('Spoor')

    def __repr__(self):
        vondstnr = (' Vondstnr ' + str(self.vondstnr)) + " " if self.vondstnr else ''
        put = (' Put ' + str(self.put.putnr)) + " " if self.put else ''

        return self.project.projectcd + put + vondstnr + self.omstandigheden if self.omstandigheden else ''

class Artefact(WasstraatModel):
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
    subnr = Column(Integer) 
    restauratie = Column(Integer)
    projectID = Column(ForeignKey('Def_Project.primary_key'), index=True)
    project = relationship('Project')
    putID = Column(ForeignKey('Def_Put.primary_key'), index=True)
    put = relationship('Put')
    vondstID = Column(ForeignKey('Def_Vondst.primary_key'), index=True)
    vondst = relationship('Vondst')
    doosID = Column(ForeignKey('Def_Doos.primary_key'), index=True)
    doos = relationship('Doos')
    artefactsoort = Column(String(40))
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



class Foto(WasstraatModel):
    __tablename__ = 'Def_Foto'

    primary_key = Column(Integer, primary_key=True, autoincrement=True)
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
#class Foto_Ongekoppeld(WasstraatModel):
#    __table__ = select_foto_zonder


class Standplaats(WasstraatModel):
    __tablename__ = 'Def_Standplaats'

    primary_key = Column(Integer, primary_key=True, autoincrement=True)
    doosnr = Column(Integer)
    inhoud = Column(Text)
    projectcd = Column(String(12))
    projectnaam = Column(Text)
    stelling = Column(Text)
    uitgeleend = Column(Integer)
    vaknr = Column(Integer)
    volgletter = Column(Text)


class Plaatsing(WasstraatModel):
    __tablename__ = 'Def_Plaatsing'

    primary_key = Column(Integer, primary_key=True, autoincrement=True)
    doosnr = Column(Integer)
    inhoud = Column(Text)
    projectcd = Column(String(12))
    projectnaam = Column(Text)
    stelling = Column(Text)
    uitgeleend = Column(Integer)
    vaknr = Column(Integer)
    volgletter = Column(Text)
    

class Vlak(WasstraatModel):
    __tablename__ = 'Def_Vlak'

    primary_key = Column(Integer, primary_key=True, autoincrement=True)
    vlaknr = Column(String(50))
    beschrijving = Column(Text)
    datum_aanleg = Column(String(50))
    vlaktype = Column(String(50))
    projectID = Column(ForeignKey('Def_Project.primary_key'), index=True)
    project = relationship('Project')
    putID = Column(ForeignKey('Def_Put.primary_key', deferrable=True), index=True)
    put = relationship('Put')

    def __repr__(self):
        put = (' Put ' + str(self.put.putnr)) + " " if self.put else ''
        vlak = (' Vlaknr ' + str(self.vlaknr)) + " " if self.vlaknr else ''

        return self.project.projectcd + put + vlak + self.beschrijving if self.beschrijving else ''


class Person(WasstraatModel):
    id = Column(Integer, primary_key=True)
    name = Column(String(150), unique = True, nullable=False)


class ContactGroup(WasstraatModel):
    id = Column(Integer, primary_key=True)
    name = Column(String(50), unique=True, nullable=False)

    def __repr__(self):
        return self.name


class Gender(WasstraatModel):
    id = Column(Integer, primary_key=True)
    name = Column(String(50), unique=True, nullable=False)

    def __repr__(self):
        return self.name


class Contact(WasstraatModel):
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


