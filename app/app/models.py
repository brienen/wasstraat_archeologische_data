import datetime
from email.policy import default
from flask import url_for, Markup
from flask_appbuilder.models.decorators import renders

from flask_appbuilder import Model
from flask_appbuilder.filemanager import ImageManager
from sqlalchemy import BigInteger, Column, Date, DateTime, Float, ForeignKey, Integer, LargeBinary, String, Table, Text, Boolean, JSON, UniqueConstraint, Enum, Index
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy import select, func
from sqlalchemy.ext.hybrid import hybrid_property, hybrid_method
from flask_appbuilder.models.mixins import ImageColumn
from fab_addon_geoalchemy.views import GeoModelView
from fab_addon_geoalchemy.models import GeoSQLAInterface, Geometry
import enum

from sqlalchemy_utils import observes

from shared import const
from util import isEmpty


mindate = datetime.date(datetime.MINYEAR, 1, 1)
metadata = Model.metadata


class WasstraatModel(Model):
    __abstract__ = True

    herkomst = Column(Text)
    key = Column(Text)
    soort = Column(String(80))
    brondata = Column(Text)
    uuid = Column('_id', String)

class ABR(WasstraatModel):
    __tablename__ = 'Def_ABR'

    primary_key = Column(Integer, primary_key=True, autoincrement=True)
    concept = Column(String(256))
    code = Column(String(80))
    label = Column(String(256))
    note = Column(Text)
    beginjaar = Column(Integer)
    eindjaar = Column(Integer)
    bron = Column(String(256))
    opmerkingen = Column(Text)
    uri = Column(String(256))
    uris = Column(Text)
    parentID = Column(ForeignKey('Def_ABR.primary_key', deferrable=True), index=True)
    parent = relationship('ABR', remote_side=[primary_key], backref="children", lazy="joined", join_depth=1)

    def __repr__(self):
        if isEmpty(self.code) and isEmpty(self.concept):
            return ''
        else:
            code = f'({self.code})' if self.code else ''
            concept = self.concept if self.concept else 'Onbenoemd Concept'
            return f'{concept} {code}'.strip()



class Stelling(WasstraatModel):
    __tablename__ = 'Def_Stelling'

    primary_key = Column(Integer, primary_key=True, autoincrement=True)
    uuid = Column('_id', String)
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
    vindplaats = Column(String(1024))
    xcoor_rd = Column(Float(53))
    ycoor_rd = Column(Float(53))
    


class Observation(WasstraatModel):
    id = Column(Integer, primary_key=True)
    name = Column(String(1024))
    location = Column(Geometry(geometry_type='POINT', srid=4326))

    def __repr__(self):
        if self.name:
            return self.name
        else:
            return 'Person Type %s' % self.id

class Project(Model): # Inherit from Model for cannot use Abstract class Wasstraatmodel, for geo-package gives errors
    __tablename__ = 'Def_Project'

    primary_key = Column(Integer, primary_key=True, autoincrement=True)
    projectcd = Column(String(12), nullable=False, index=True)
    projectnaam = Column(String(1024), index=True)
    jaar = Column(Integer)
    toponiem = Column(String(1024))
    trefwoorden = Column(String(1024))
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
    uuid = Column('_id', String)
    key = Column(Text)

    aantal_artefacten = Column(Integer, default=0)
    @observes('artefacten') # Works only for update events, inserts and deletes via modelevents.py 
    def artefacten_observer(self, artefacten):
        self.aantal_artefacten = len(artefacten)

    @staticmethod
    def getDescription(p):
        return str(p.projectcd) + f' ({p.projectnaam if p.projectnaam and p.projectnaam != "" else "Zonder naam"})'

    def __repr__(self):
        return Project.getDescription(self)


class Doos(WasstraatModel):
    __tablename__ = 'Def_Doos'

    primary_key = Column(Integer, primary_key=True, autoincrement=True)
    doosnr = Column(Integer, index=True)
    inhoud = Column(Text)
    projectcd = Column(String(12))
    projectnaam = Column(Text)
    stelling = Column(Text)
    uitgeleend = Column(Boolean)
    vaknr = Column(Integer)
    volgletter = Column(Text)
    stellingID = Column(ForeignKey('Def_Stelling.primary_key'), index=True)
    stelling = relationship('Stelling', lazy="joined")
    projectID = Column(ForeignKey('Def_Project.primary_key'), index=True)
    project = relationship('Project', lazy="joined")


    @staticmethod
    def getDescription(doos):
        projectcd = doos.project.projectcd if doos.project else "Onbekend Project, "
        stelling = ', Stelling: ' + str(doos.stelling) if doos.stelling else ''
        vaknr = ', Vaknr: ' + str(doos.vaknr) if doos.stelling else ''
        return f'Doosnr: {doos.doosnr} ({projectcd}){stelling}{vaknr}'


    def __repr__(self):
        return Doos.getDescription(self)

    @hybrid_method
    def aantalArtefacten(self):
        return len(self.artefacten)

class Put(WasstraatModel):
    __tablename__ = 'Def_Put'

    primary_key = Column(Integer, primary_key=True, autoincrement=True)
    putnr = Column(Integer, index=True)
    beschrijving = Column(Text)
    aangelegd = Column(Boolean)
    datum_ingevoerd = Column(Text)
    datum_gewijzigd = Column(Text)
    projectID = Column(ForeignKey('Def_Project.primary_key', deferrable=True), index=True)
    project = relationship('Project', lazy="joined")

    @staticmethod
    def getDescription(v):
        projectcd = v.project.projectcd if v.project else "Onbekend Project, "
        beschr = str(v.beschrijving) if v.beschrijving else ""

        return projectcd + ' Put ' + str(v.putnr) + ' ' + beschr


    def __repr__(self):
        projectcd = self.project.projectcd if self.project else "Onbekend Project, "
        beschr = str(self.beschrijving) if self.beschrijving else ""

        return projectcd + ' Put ' + str(self.putnr) + ' ' + beschr



class Vlak(WasstraatModel):
    __tablename__ = 'Def_Vlak'

    primary_key = Column(Integer, primary_key=True, autoincrement=True)
    vlaknr = Column(String(50), index=True)
    beschrijving = Column(Text)
    datum_aanleg = Column(String(50))
    vlaktype = Column(String(50))
    projectID = Column(ForeignKey('Def_Project.primary_key'), index=True)
    project = relationship('Project', lazy="joined")
    putID = Column(ForeignKey('Def_Put.primary_key', deferrable=True), index=True)
    put = relationship('Put', lazy="joined")

    def __repr__(self):
        projectcd = self.project.projectcd if self.project else "Onbekend Project, "        
        put = (' Put ' + str(self.put.putnr)) + " " if self.put else ''
        vlak = (' Vlaknr ' + str(self.vlaknr)) + " " if self.vlaknr else ''

        return projectcd + put + vlak + self.beschrijving if self.beschrijving else ''


class Spoor(WasstraatModel):
    __tablename__ = 'Def_Spoor'

    primary_key = Column(Integer, primary_key=True, autoincrement=True)
    vlaknr = Column(String(1024))
    spoornr = Column(Integer, index=True)
    aard = Column(String(1024))
    beschrijving = Column(Text)
    gecoupeerd =  Column(Text)
    coupnrs =   Column(Text)
    afgewerkt = Column(Text)
    spoordatering_vanaf = Column(Integer, index=True)
    spoordatering_tot = Column(Integer, index=True)
    vorm = Column(String(1024))
    diepte = Column(String(1024))
    breedte_bovenkant= Column(String(1024))
    lengte_bovenkant= Column(String(1024))
    hoogte_bovenkant= Column(String(1024))
    hoogte_onderkant= Column(String(1024))
    breedte_onderkant= Column(String(1024))
    onderkant_NAP = Column(String(1024))
    profiel = Column(String(1024))
    richting = Column(String(1024))
    steenformaat = Column(String(1024))
    metselverband = Column(String(1024))
    steenformaat = Column(String(1024))
    jonger_dan = Column(String(1024))
    ouder_dan = Column(String(1024))
    sporen_zelfde_periode = Column(String(1024))
    projectID = Column(ForeignKey('Def_Project.primary_key', deferrable=True), index=True)
    project = relationship('Project', lazy="joined")
    putID = Column(ForeignKey('Def_Put.primary_key', deferrable=True), index=True)
    put = relationship('Put', lazy="joined")
    vlakID = Column(ForeignKey('Def_Vlak.primary_key', deferrable=True), index=True)
    vlak = relationship('Vlak')

    @staticmethod
    def getDescription(v):
        projectcd = v.project.projectcd if v.project else "Onbekend Project, "
        put = (' Put ' + str(v.put.putnr)) + " " if v.put else ''
        aard = str(v.aard) if str(v.aard) else ""

        return projectcd + put + ' Spoor ' + str(v.spoornr) + ' ' + aard

    def __repr__(self):
        projectcd = self.project.projectcd if self.project else "Onbekend Project, "
        put = (' Put ' + str(self.put.putnr)) + " " if self.put else ''
        aard = str(self.aard) if str(self.aard) else ""

        return projectcd + put + ' Spoor ' + str(self.spoornr) + ' ' + aard


class Vondst(WasstraatModel):
    __tablename__ = 'Def_Vondst'

    primary_key = Column(Integer, primary_key=True, autoincrement=True)
    vlaknr = Column(String(1024))
    vondstnr = Column(Integer, index=True)
    opmerkingen = Column(String(1024))
    omstandigheden = Column(Text)
    datum = Date()
    vondstdatering_vanaf = Column(Integer, index=True)
    vondstdatering_tot = Column(Integer, index=True)
    segment = Column(String(1024))
    vaknummer = Column(String(1024))
    vullingnr = Column(String(1024)) 
    projectID = Column(ForeignKey('Def_Project.primary_key', deferrable=True), index=True)
    project = relationship('Project', lazy="joined")
    putID = Column(ForeignKey('Def_Put.primary_key', deferrable=True), index=True)
    put = relationship('Put', lazy="joined", backref="vondsten")
    spoorID = Column(ForeignKey('Def_Spoor.primary_key', deferrable=True), index=True)
    spoor = relationship('Spoor', backref="vondsten")

    @staticmethod
    def getDescription(v):
        projectcd = v.project.projectcd if v.project else "Onbekend Project"
        vondstnr = ('Vondstnr ' + str(v.vondstnr)) + " " if v.vondstnr else ''
        put = ('Put ' + str(v.put.putnr)) + " " if v.put else ''
        omstandigheden = v.omstandigheden if v.omstandigheden else ''

        return f"{vondstnr} {omstandigheden} {put} {projectcd}"

    def __repr__(self):
        return Vondst.getDescription(self)


    def __repr__(self):
        projectcd = self.project.projectcd if self.project else "Onbekend Project"
        vondstnr = ('Vondstnr ' + str(self.vondstnr)) + " " if self.vondstnr else ''
        put = ('Put ' + str(self.put.putnr)) + " " if self.put else ''
        omstandigheden = self.omstandigheden if self.omstandigheden else ''

        return f"{vondstnr} {omstandigheden} {put} {projectcd}"



class Vulling(WasstraatModel):
    __tablename__ = 'Def_Vulling'

    primary_key = Column(Integer, primary_key=True, autoincrement=True)
    vullingnr = Column(Integer, index=True)
    vlaknr = Column(String(1024))
    vondstnr = Column(Integer)
    spoornr = Column(Integer)
    opmerkingen = Column(String(1024))
    bioturbatie = Column(String(1024))
    textuur = Column(String(1024))
    mediaan = Column(String(1024))
    textuurbijmenging = Column(String(1024))
    sublaag = Column(String(1024))
    kleur = Column(String(1024))
    reductie = Column(String(1024))
    gevlekt = Column(String(1024))
    laaginterpretatie = Column(String(1024))
    schelpenresten = Column(String(1024))
    grondsoort = Column(String(1024))
    lengte_baksteen1 = Column(String(1024))
    lengte_baksteen2 = Column(String(1024))
    lengte_baksteen3 = Column(String(1024))
    hoogte_baksteen1 = Column(String(1024))
    hoogte_baksteen2 = Column(String(1024))
    hoogte_baksteen3 = Column(String(1024))
    breedte_baksteen1 = Column(String(1024))
    breedte_baksteen2 = Column(String(1024))
    breedte_baksteen3 = Column(String(1024))
    projectID = Column(ForeignKey('Def_Project.primary_key', deferrable=True), index=True)
    project = relationship('Project', lazy="joined")
    putID = Column(ForeignKey('Def_Put.primary_key', deferrable=True), index=True)
    put = relationship('Put', lazy="joined")
    spoorID = Column(ForeignKey('Def_Spoor.primary_key', deferrable=True), index=True)
    spoor = relationship('Spoor')

    def __repr__(self):
        projectcd = self.project.projectcd if self.project else "Onbekend Project, "
        vondstnr = (' Vondstnr ' + str(self.vondstnr)) + " " if self.vondstnr else ''
        put = (' Put ' + str(self.put.putnr)) + " " if self.put else ''
        spoornr = (' Spoor ' + str(self.spoornr)) + " " if self.spoornr else ''
        vulnr = self.vullingnr if self.vullingnr else ' Vullingnr onbekend'

        return projectcd + put + vondstnr + spoornr + vulnr



class DiscrArtefactsoortEnum(enum.Enum): 
    Aardewerk = "Aardewerk"
    Dierlijk_Bot = "Dierlijk_Bot"
    Glas = "Glas"
    Hout = "Hout"
    Bouwaardewerk = "Bouwaardewerk"
    Kleipijp = "Kleipijp"
    Leer = "Leer"
    Menselijk_Bot = "Menselijk_Bot"
    Metaal = "Metaal"
    Munt = "Munt"
    Onbekend = "Onbekend"
    Schelp = "Schelp"
    Steen = "Steen"
    Textiel = "Textiel"



assoc_artefact_abr = Table('Def_artefact_abr', Model.metadata,
                                      Column('id', Integer, primary_key=True),
                                      Column('abr_materiaal_id', Integer, ForeignKey('Def_ABR.primary_key')),
                                      Column('artefact_id', Integer, ForeignKey('Def_Artefact.primary_key'))
)


class Artefact(WasstraatModel):
    __tablename__ = 'Def_Artefact'

    primary_key = Column(Integer, primary_key=True, autoincrement=True)
    artefactnr = Column(Integer, index=True)
    beschrijving = Column(Text)
    opmerkingen = Column(Text)
    typevoorwerp = Column(String(1024))
    typecd = Column(String(1024))
    functievoorwerp = Column(String(1024))
    origine = Column(String(1024))
    artefactdatering_vanaf = Column(Integer)
    artefactdatering_tot = Column(Integer)
    conserveren = Column(Integer)
    exposabel = Column(Boolean)
    literatuur = Column(String(1024))
    putnr = Column(Integer)
    subnr = Column(Integer) 
    restauratie = Column(Boolean)
    abrcode_materiaal = Column(String(1024))
    aantal = Column(Integer)
    afmetingen = Column(String(1024))
    catalogus = Column(String(1024))
    compleetheid = Column(String(1024))
    conservering = Column(Boolean)
    diversen = Column(Text)
    gewicht = Column(String(1024))
    groep = Column(String(1024))
    mai = Column(String(1024), comment="MAI, minimum aantal individuen, 0 = onbekend, meer dan 1")
    materiaal = Column(String(1024))
    formaat_horizontaal = Column(String(1024))
    formaat_vericaal = Column(String(1024))
    naam_voorwerp = Column(String(1024))
    plek = Column(String(1024))
    publicatiecode = Column(String(1024))
    typenaam = Column(String(1024))
    versiering = Column(String(1024))
    vondstomstandigheden = Column(String(1024))
    weggegooid = Column(Integer)
    projectID = Column(ForeignKey('Def_Project.primary_key', deferrable=True), index=True)
    project = relationship('Project', lazy="joined", back_populates="artefacten")
    putID = Column(ForeignKey('Def_Put.primary_key', deferrable=True), index=True)
    put = relationship('Put', backref="artefacten")
    vondstID = Column(ForeignKey('Def_Vondst.primary_key', deferrable=True), index=True)
    vondst = relationship('Vondst', backref="artefacten")
    doosID = Column(ForeignKey('Def_Doos.primary_key', deferrable=True), index=True)
    doos = relationship('Doos', backref="artefacten")
    abr_materiaalID = Column(Integer, ForeignKey('Def_ABR.primary_key', deferrable=True), index=True)
    abr_materiaal = relationship("ABR", foreign_keys=[abr_materiaalID])
    abr_submateriaalID = Column(Integer, ForeignKey('Def_ABR.primary_key', deferrable=True), index=True)
    abr_submateriaal = relationship("ABR", foreign_keys=[abr_submateriaalID])

    artefactsoort =  Column(Enum(DiscrArtefactsoortEnum), index=True)
    abr_extras = relationship('ABR', secondary=assoc_artefact_abr, backref='artefacten')

    datering_vanaf = Column(Integer, default=None, index=True)
    datering_tot = Column(Integer, default=None, index=True)
    @observes('artefactdatering_vanaf', 'artefactdatering_tot')  # Works only for update events, inserts and deletes via modelevents.py 
    def arttefactdatering_observer(self, artefactdatering_vanaf, artefactdatering_tot):
        if artefactdatering_vanaf:
            self.datering_vanaf = artefactdatering_vanaf
        elif self.vondstdatering_vanaf:
            self.datering_vanaf = self.vondstdatering_vanaf
        else:
            self.datering_vanaf = self.spoordatering_vanaf

        if artefactdatering_tot:
            self.datering_tot = artefactdatering_tot
        elif self.vondstdatering_tot:
            self.datering_tot = self.vondstdatering_tot
        else:
            self.datering_tot = self.spoordatering_tot


    vondstdatering_vanaf = Column(Integer, default=None, index=True)
    @observes('vondst.vondstdatering_vanaf')  # Works only for update events, inserts and deletes via modelevents.py 
    def vondstdatvanaf_observer(self, vondstdatering_vanaf):
        self.vondstdatering_vanaf = vondstdatering_vanaf
        if not self.artefactdatering_vanaf:
            self.datering_vanaf = self.vondstdatering_vanaf

    vondstdatering_tot = Column(Integer, default=None, index=True)
    @observes('vondst.vondstdatering_tot')  # Works only for update events, inserts and deletes via modelevents.py 
    def vondstdatatot_observer(self, vondstdatering_tot):
        self.vondstdatering_tot = vondstdatering_tot
        if not self.artefactdatering_tot:
            self.datering_tot = self.vondstdatering_tot



    spoordatering_tot = Column(Integer, default=None, index=True)
    @observes('vondst.spoor.spoordatering_tot')  # Works only for update events, inserts and deletes via modelevents.py 
    def spoor_observer(self, spoordatering_tot):
        self.spoordatering_tot = spoordatering_tot
        if not self.vondstdatering_tot and not self.artefactdatering_tot:
            self.datering_tot = self.spoordatering_tot


    spoordatering_vanaf = Column(Integer, default=None, index=True)
    @observes('vondst.spoor.spoordatering_vanaf')  # Works only for update events, inserts and deletes via modelevents.py 
    def spoor_observer(self, spoordatering_vanaf):
        self.spoordatering_vanaf = spoordatering_vanaf
        if not self.vondstdatering_vanaf and not self.artefactdatering_vanaf:
            self.datering_vanaf = self.spoordatering_vanaf



    #fotos = relationship('Foto', backref="artefact")
    aantal_fotos = Column(Integer, default=0)
    @observes('fotos')  # Works only for update events, inserts and deletes via modelevents.py 
    def fotos_observer(self, fotos):
        self.aantal_fotos = len(fotos)

    def __repr__(self):
        if self.project:
            projectcd = self.project.projectcd if self.project and self.project.projectcd else "Onbekend Project, "
            subnr = str(self.subnr) if self.subnr else ''
            artefactsoort = (str(self.artefactsoort.value)) if self.artefactsoort else ''
            return f"{artefactsoort} {self.typevoorwerp} {subnr} {projectcd}"
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

    @hybrid_method
    def spoor(self):
        if self.vondst and self.vondst.spoor:
            return self.vondst.spoor
        else:
            return ""

    @hybrid_method
    def datering(self):
        if self.datering_vanaf and self.datering_tot:
            return f"{self.datering_vanaf} - {self.datering_tot}"
        elif self.datering_vanaf:
            return f"{self.datering_vanaf} -"
        elif self.datering_tot:
            return f"- {self.datering_tot}"
        else: 
            return ""


    __mapper_args__ = {
        'polymorphic_on': artefactsoort,
        'polymorphic_identity': DiscrArtefactsoortEnum.Onbekend
    }





class Aardewerk(Artefact):
    __tablename__ = 'Def_Artefact'
    __table_args__ = {'extend_existing': True}
    __mapper_args__ = {'polymorphic_identity': DiscrArtefactsoortEnum.Aardewerk}

    baksel = Column(String(1024), comment="soort AW")
    bakseltype = Column(String(1024), comment="bakseltype")
    bodem = Column(String(1024), comment="vorm van de bodem/voet")
    categorie = Column(String(1024), comment="categorie")
    codes = Column(String(1024), comment="codes van type")
    decoratie = Column(String(1024), comment="decoratie")
    diameter = Column(String(1024), comment="")
    fragment = Column(String(1024), comment="fragment: rand, wand, bodem, oor etc")
    glazuur = Column(String(1024), comment="glazuur")
    grootste_diameter = Column(String(1024), comment="grootste diameter in millimeters, 0 = niet gemeten")
    hoogte = Column(String(1024), comment="hoogte in millimeters, 0 = niet gemeten")
    kleur = Column(String(1024), comment="kleur")
    materiaalsoort = Column(String(1024), comment="materiaalsoort")
    max_diameter = Column(String(1024), comment="")
    oor = Column(String(1024), comment="vorm en versiering van oor")
    past_aan = Column(String(1024), comment="vondstnummer waar scherf aan past")
    percentage = Column(String(1024), comment="aanwezig percentage van een pot")
    productiewijze = Column(String(1024), comment="produktiewijze")
    rand = Column(String(1024), comment="vorm en versiering van rand")
    rand_bodem = Column(String(1024), comment="diameter bodem in millimeters, 0 = niet gemeten")
    rand_diameter = Column(String(1024), comment="diameter rand in millimeters, 0 = niet gemeten")
    vorm = Column(String(1024), comment="vorm")


#van Artefact afgeleide class Dierlijk_Bot
class Dierlijk_Bot(Artefact):
    __tablename__ = 'Def_Artefact'
    __table_args__ = {'extend_existing': True}
    __mapper_args__ = {'polymorphic_identity': DiscrArtefactsoortEnum.Dierlijk_Bot}

    aantal_puzzelen = Column(String(1024), comment="Aantal voor puzzelen")
    associatie = Column(String(1024), comment="Associatie")
    bewerkingssporen = Column(String(1024), comment="Bewerkingssporen")
    brandsporen = Column(String(1024), comment="Brandsporen")
    diersoort = Column(String(1024), comment="Diersoort")
    geconserveerd = Column(String(1024), comment="geconserveerd")
    graf = Column(String(1024), comment="Soort graf")
    individunr = Column(String(1024), comment="Individunummer")
    knaagsporen = Column(String(1024), comment="Knaagsporen")
    leeftijd = Column(String(1024), comment="Leeftijd individu")
    lengte = Column(String(1024), comment="Lengte in cm")
    maat1 = Column(String(1024), comment="Maat 1 in mm")
    maat2 = Column(String(1024), comment="Maat 2 in mm")
    maat3 = Column(String(1024), comment="Maat 3 in mm")
    maat4 = Column(String(1024), comment="Maat 4 in mm")
    oriëntatie = Column(String(1024), comment="Oriëntatie (Links - Rechts)")
    pathologie = Column(String(1024), comment="Pathologie")
    percentage = Column(String(1024), comment="Percentage")
    skeletdeel = Column(String(1024), comment="Skeletdeel")
    slijtage = Column(String(1024), comment="Slijtage onderkaaks P4, Grant 1982")
    slijtage_onderkaaks_DP4 = Column(String(1024), comment="Slijtage onderkaaks DP4, Grant 1982")
    slijtage_onderkaaks_M1 = Column(String(1024), comment="Slijtage onderkaaks M1, Grant 1982")
    slijtage_onderkaaks_M2 = Column(String(1024), comment="Slijtage onderkaaks M2, Grant 1982")
    slijtage_onderkaaks_M3 = Column(String(1024), comment="Slijtage onderkaaks M3, Grant 1982")
    symmetrie = Column(String(1024), comment="Symmetrie")
    vergroeiing = Column(String(1024), comment="Vergroeiing")


#van Artefact afgeleide class Glas
class Glas(Artefact):
    __tablename__ = 'Def_Artefact'
    __table_args__ = {'extend_existing': True}
    __mapper_args__ = {'polymorphic_identity': DiscrArtefactsoortEnum.Glas}

    decoratie = Column(String(1024), comment="decoratie")
    diameter_bodem = Column(String(1024), comment="diameter bodem in millimeters, 0 = niet gemeten")
    diameter_rand = Column(String(1024), comment="diameter rand in millimeters, 0 = niet gemeten")
    glassoort = Column(String(1024), comment="Soort glas")
    grootste = Column(String(1024), comment="grootste diameter in millimeters, 0 = niet gemeten")
    hoogte = Column(String(1024), comment="hoogte in millimeters, 0 = niet gemeten")
    kleur = Column(String(1024), comment="kleur")
    past_aan = Column(String(1024), comment="Past aan")
    past_aan_andere_nummers = Column(String(1024), comment="past aan andere nummers:")
    percentage_rand = Column(String(1024), comment="Randpercentage")
    vorm_bodem_voet = Column(String(1024), comment="vorm van de bodem/voet + eventuele merkjes")
    vorm_versiering_cuppa = Column(String(1024), comment="vorm en versiering van cuppa")
    vorm_versiering_oor_stam = Column(String(1024), comment="vorm en versiering van oor/stam")



#van Artefact afgeleide class Hout
class Hout(Artefact):
    __tablename__ = 'Def_Artefact'
    __table_args__ = {'extend_existing': True}
    __mapper_args__ = {'polymorphic_identity': DiscrArtefactsoortEnum.Hout}

    C14_datering = Column(String(1024), comment="C14 datering mogelijk ja of nee")
    bewerkingssporen = Column(String(1024), comment="bewerkingssporen")
    decoratie = Column(String(1024), comment="decoratie")
    dendrodatering = Column(String(1024), comment="dendrodatering mogelijk ja of nee")
    determinatieniveau = Column(String(1024), comment="het determinatieniveau; bv. cf. = onzekere determinatie")
    diameter = Column(String(1024), comment="diameter in cm van de stam/tak")
    gebruikssporen = Column(String(1024), comment="gebruikssporen")
    houtsoort = Column(String(1024), comment="code voor de houtsoort")
    houtsoortcd = Column(String(1024), comment="code voor de houtsoort")
    jaarring_bast_spint = Column(String(1024), comment="jaarring, spint, bast")
    puntlengte = Column(String(1024), comment="puntlengte : de lengte  in cm van de punt gemeten van hoogste kapvlak")
    puntvorm = Column(String(1024), comment="puntvorm : het aantal vlakken warrmee de punt is gemaakt halverwege de punt")
    stamcode = Column(String(1024), comment="stamcode : 0 =onbekend")




#van Artefact afgeleide class Bouwaardewerk
class Bouwaardewerk(Artefact):
    __tablename__ = 'Def_Artefact'
    __table_args__ = {'extend_existing': True}
    __mapper_args__ = {'polymorphic_identity': DiscrArtefactsoortEnum.Bouwaardewerk}

    baksel = Column(String(1024), comment="Baksel")
    bodem = Column(String(1024), comment="Bodem")
    brandsporen = Column(String(1024), comment="Brandsporen")
    diameter_bodem = Column(String(1024), comment="Diameter van bodem")
    gedraaid = Column(String(1024), comment="")
    glazuur = Column(String(1024), comment="Glazuur")
    grootste_diameter = Column(String(1024), comment="Grootste diameter")
    handgevormd = Column(String(1024), comment="")
    hoogte = Column(String(1024), comment="Hoogte van voorwerp")
    kleur = Column(String(1024), comment="Kleur van voorwerp")
    magering = Column(String(1024), comment="magering")
    maker = Column(String(1024), comment="Maker (vnl. i.g.v. kleipijpen)")
    oor_steel = Column(String(1024), comment="Oor steel")
    oppervlakte = Column(String(1024), comment="oppervlakte behandeling")
    past_aan = Column(String(1024), comment="Past aan")
    productiewijze = Column(String(1024), comment="Productie wijze")
    randdiameter = Column(String(1024), comment="Randdiameter in cm")
    randindex = Column(String(1024), comment="Randindex (RANDPER / 100)")
    randpercentage = Column(String(1024), comment="Randpercentage")
    subbaksel = Column(String(1024), comment="Subbaksel")
    type_rand = Column(String(1024), comment="type rand")
    vorm = Column(String(1024), comment="Vorm")
    wanddikte = Column(String(1024), comment="wanddikte")


#van Artefact afgeleide class Kleipijp
class Kleipijp(Artefact):
    __tablename__ = 'Def_Artefact'
    __table_args__ = {'extend_existing': True}
    __mapper_args__ = {'polymorphic_identity': DiscrArtefactsoortEnum.Kleipijp}



#van Artefact afgeleide class Leer
class Leer(Artefact):
    __tablename__ = 'Def_Artefact'
    __table_args__ = {'extend_existing': True}
    __mapper_args__ = {'polymorphic_identity': DiscrArtefactsoortEnum.Leer}

    beschrijving_zool = Column(String(1024), comment="Verder beschrijving van de zool")
    bewerking = Column(String(1024), comment="bewerking")
    bewerkingssporen = Column(String(1024), comment="Bewerkinssporen")
    bovenleer = Column(String(1024), comment="bovenleer: bv. wreef, hiel, tong, etc.")
    decoratie = Column(String(1024), comment="decoratie")
    kwaliteit = Column(String(1024), comment="kwaliteit: goed, redelijk, matig, slecht")
    leersoort = Column(String(1024), comment="Leersoort (Naam dier)")
    past_aan = Column(String(1024), comment="past aan andere nummers:")
    sluiting = Column(String(1024), comment="sluiting: bv. veter, gesp, riem, etc.")
    soort_sluiting = Column(String(1024), comment="Soort sluiting")
    toestand = Column(String(1024), comment="toestand: nat of droog")
    type_bovenleer = Column(String(1024), comment="Type bovenleer")
    verbinding = Column(String(1024), comment="verbinding tussen zool en bovenleer")
    zool = Column(String(1024), comment="zool: dubbel, enkel, etc.")
    zoolvorm = Column(String(1024), comment="zoolvorm: code volgens Goubitz, Stepping through time (bladzijde 82)")


#van Artefact afgeleide class Menselijk_Bot
class Menselijk_Bot(Artefact):
    __tablename__ = 'Def_Artefact'
    __table_args__ = {'extend_existing': True}
    __mapper_args__ = {'polymorphic_identity': DiscrArtefactsoortEnum.Menselijk_Bot}

    breedte_kist_hoofdeinde = Column(String(1024), comment="in cm")
    breedte_kist_voeteinde = Column(String(1024), comment="in cm")
    doos_delft = Column(String(1024), comment="")
    doos_lumc = Column(String(1024), comment="")
    kist_waargenomen = Column(String(1024), comment="")
    lengte_kist = Column(String(1024), comment="in cm")
    linkerarm = Column(String(1024), comment="")
    linkerbeen = Column(String(1024), comment="")
    plaats = Column(String(1024), comment="")
    primair_graf = Column(String(1024), comment="")
    rechterarm = Column(String(1024), comment="")
    rechterbeen = Column(String(1024), comment="")
    schedel = Column(String(1024), comment="")
    secundair_graf = Column(String(1024), comment="")
    skeletelementen = Column(String(1024), comment="")
    wervelkolom = Column(String(1024), comment="")


#van Artefact afgeleide class Metaal
class Metaal(Artefact):
    __tablename__ = 'Def_Artefact'
    __table_args__ = {'extend_existing': True}
    __mapper_args__ = {'polymorphic_identity': DiscrArtefactsoortEnum.Metaal}

    bewerking = Column(String(1024), comment="bewerking")
    decoratie = Column(String(1024), comment="decoratie")
    diverse = Column(String(1024), comment="diverse: aangetast, licht aangetast, zwaar aangetast en/of geirriseerd")
    metaalsoort = Column(String(1024), comment="Metaal soort")
    oppervlak = Column(String(1024), comment="oppervlak")
    percentage = Column(String(1024), comment="")


#van Artefact afgeleide class Munt
class Munt(Artefact):
    __tablename__ = 'Def_Artefact'
    __table_args__ = {'extend_existing': True}
    __mapper_args__ = {'polymorphic_identity': DiscrArtefactsoortEnum.Munt}

    aard_verwerving = Column(String(1024), comment="koop, schenking, legaat, bruikleen etc.")
    autoriteit = Column(String(1024), comment="naam van vorst (met jaartallen), instantie, opdrachtgever")
    conditie = Column(String(1024), comment="alleen invullen in uitzonderlijke situatie, restauratie nodig ?")
    eenheid = Column(String(1024), comment="bv : kwart, halve, dubbele, 1, 10, 25")
    gelegenheid = Column(String(1024), comment="korte aanduiding")
    inventaris = Column(String(1024), comment="huidig inventarisnummer (eventueel oude inv. nrs)")
    jaartal = Column(String(1024), comment="jaartal op voorwerp (of periode)")
    keerzijde_tekst = Column(String(1024), comment="volledige teks")
    kwaliteit = Column(String(1024), comment="numismatische kwaliteitsaanduiding : goed, f.d.c.")
    land = Column(String(1024), comment="land van uitgifte (politieke eenheid)")
    muntplaats = Column(String(1024), comment="plaats van aanmunting")
    muntsoort = Column(String(1024), comment="in enkelvoud, bv daalder, gulden, cent")
    ontwerper = Column(String(1024), comment="naam (met jaartallen)")
    plaats = Column(String(1024), comment="plaats van bewaring")
    produktiewijze = Column(String(1024), comment="alleen invullen indien nodig")
    randafwerking = Column(String(1024), comment="alleen invullen indien niet glad")
    randschrift = Column(String(1024), comment="volldedige tekst")
    rubriek = Column(String(1024), comment="grove indeling in gebied, periode of politieke eenheid")
    signalement = Column(String(1024), comment="korte beschrijving, signalement")
    verworven_van = Column(String(1024), comment="verworven van wie en wanneer")
    vindplaats = Column(String(1024), comment="allleen voor(bodem)vondsten, waar en wanneer")
    voorwaarden_verwerving = Column(String(1024), comment="eventueel aan de verwerving verbonden voorwaarden")
    voorzijde_tekst = Column(String(1024), comment="volledige teks")
    vorm = Column(String(1024), comment="alleen invullen als voorwerp niet rond is")



#van Artefact afgeleide class Schelp
class Schelp(Artefact):
    __tablename__ = 'Def_Artefact'
    __table_args__ = {'extend_existing': True}
    __mapper_args__ = {'polymorphic_identity': DiscrArtefactsoortEnum.Schelp}




#van Artefact afgeleide class Steen
class Steen(Artefact):
    __tablename__ = 'Def_Artefact'
    __table_args__ = {'extend_existing': True}
    __mapper_args__ = {'polymorphic_identity': DiscrArtefactsoortEnum.Steen}

    decoratie = Column(String(1024), comment="decoratie")
    diameter = Column(String(1024), comment="diameter in mm")
    dikte = Column(String(1024), comment="dikte in mm")
    grootste_diameter = Column(String(1024), comment="Grootste diameter in cm")
    kleur = Column(String(1024), comment="kleur")
    lengte = Column(String(1024), comment="Lengte in cm")
    past_aan = Column(String(1024), comment="past aan andere nummers:")
    steengroep = Column(String(1024), comment="Steengroep")
    steensoort = Column(String(1024), comment="steensoort")
    subsoort = Column(String(1024), comment="subsoort")


#van Artefact afgeleide class Textiel
class Textiel(Artefact):
    __tablename__ = 'Def_Artefact'
    __table_args__ = {'extend_existing': True}
    __mapper_args__ = {'polymorphic_identity': DiscrArtefactsoortEnum.Textiel}





class DiscrFotosoortEnum(enum.Enum): 
    Objectfoto = const.OBJECTFOTO
    Opgravingsfoto = const.OPGRAVINGSFOTO
    Velddocument = const.VELDDOCUMENT
    Overige_afbeelding = const.OVERIGE_AFBEELDING
    Afbeelding = const.AFBEELDING
    Tekening = const.TEKENING
    Objecttekening = const.OBJECTTEKENING
    Overige_tekening = const.OVERIGE_TEKENING


class Foto(WasstraatModel):
    __tablename__ = 'Def_Foto'

    primary_key = Column(Integer, primary_key=True, autoincrement=True)
    directory = Column(Text)
    fileName = Column(String(1024), index=True)
    fileSize = Column(Integer)
    fileType = Column(String(32))
    imageUUID = Column(String(1024))
    imageMiddleUUID = Column(String(1024))
    imageThumbUUID = Column(String(1024))
    mime_type = Column(String(20))
    fototype = Column(String(1))
    projectcd = Column(String(12))
    photo = Column(ImageColumn(size=(1500, 1000, True), thumbnail_size=(300, 200, True)))
    fotosoort =  Column(Enum(DiscrFotosoortEnum), index=True)
 
    @renders('custom')
    def photo_img(self):
        if self.imageUUID:
            return Markup('<a href="/archeomedia' + self.imageUUID +\
             '"><img src="/archeomedia' + self.imageMiddleUUID +\
              '" alt="Photo" class="img-rounded img-responsive"></a>')
        else:
            return Markup('<a href="' + url_for('ArchFotoView.show',pk=str(self.primary_key)) +\
             '" class="thumbnail"><img src="//:0" alt="Photo" class="img-responsive"></a>')


    @renders('custom')
    def photo_img_middle(self):
        if self.imageMiddleUUID:
            return Markup('<a href="' + url_for('ArchFotoView.show',pk=str(self.primary_key)) +\
             '"><img src="/archeomedia' + self.imageMiddleUUID +\
              '" alt="Photo" class="img-rounded img-responsive" style="max-height:50vh"></a>')
        else:
            return Markup('<a href="' + url_for('ArchFotoView.show',pk=str(self.primary_key)) +\
             '" class="thumbnail"><img src="//:0" alt="Photo" class="img-responsive"></a>')


    @renders('custom')
    def photo_img_thumbnail(self):
        if self.imageThumbUUID:
            return Markup('<a href="' + url_for('ArchFotoView.show',pk=str(self.primary_key)) +\
             '" class="thumbnail"><img src="/archeomedia' + self.imageThumbUUID +\
              '" alt="Photo" class="img-rounded img-responsive"></a>')
        else:
            return Markup('<a href="' + url_for('ArchFotoView.show',pk=str(self.primary_key)) +\
             '" class="thumbnail"><img src="//:0" alt="Photo" class="img-responsive"></a>')


    projectID = Column(ForeignKey('Def_Project.primary_key'), index=True)
    project = relationship('Project', backref="fotos", lazy="joined")
    __table_args__ = (Index('ix_Foto_fototype_fileName', "fototype", "fileName"), )

    __mapper_args__ = {
        'polymorphic_on': fotosoort,
        'polymorphic_identity': DiscrFotosoortEnum.Afbeelding
    }

    @renders('custom')
    def koppeling(self): 
        if self.project:
            return Markup('<a href="' + url_for('ArchProjectView.show',pk=str(self.project.primary_key)) + '">Project: '+self.project.projectcd+'</a>')
        else:
            return 'Onbekend'

    def __repr__(self):
        if self.imageThumbUUID:
            return Markup('<a href="' + url_for('ArchFotoView.show',pk=str(self.primary_key)) +\
             '" class="thumbnail"><img src="/archeomedia' + self.imageThumbUUID +\
              '" alt="Photo" class="img-rounded img-responsive"></a>')
        else:
            return Markup('<a href="' + url_for('ArchFotoView.show',pk=str(self.primary_key)) +\
             '" class="thumbnail"><img src="//:0" alt="Photo" class="img-responsive"></a>')


class Objectfoto(Foto):
    __tablename__ = 'Def_Foto'
    __table_args__ = {'extend_existing': True}
    __mapper_args__ = {'polymorphic_identity': DiscrFotosoortEnum.Objectfoto}

    putnr = Column(Integer)
    vondstnr = Column(Integer)
    subnr = Column(Integer)
    fotonr = Column(Integer)
    materiaal = Column(String(1024))
    omschrijving = Column(Text)
    datum = Column(Date)
    richting = Column(String(20))
    artefactID = Column(ForeignKey('Def_Artefact.primary_key'), index=True)
    artefact = relationship('Artefact', backref="fotos", lazy="joined")

    @renders('custom')
    def koppeling(self): 
        project = self.projectcd if self.projectcd else 'Onbekend Project'
        put = (', Put ' + str(self.putnr)) if self.putnr else ''
        sub = (', Art. ' + str(self.subnr)) if self.subnr else ''
        desc = project + put + sub
        if self.artefact:
            return Markup('<a href="' + url_for('ArchArtefactView.show',pk=str(self.artefact.primary_key)) + '">Artefact: '+desc+'</a>')
        else:
            return 'Onbekend'


class Opgravingsfoto(Foto):
    __tablename__ = 'Def_Foto'
    __table_args__ = {'extend_existing': True}
    __mapper_args__ = {'polymorphic_identity': DiscrFotosoortEnum.Opgravingsfoto}
class Velddocument(Foto):
    __tablename__ = 'Def_Foto'
    __table_args__ = {'extend_existing': True}
    __mapper_args__ = {'polymorphic_identity': DiscrFotosoortEnum.Velddocument}
class Overige_afbeelding(Foto):
    __tablename__ = 'Def_Foto'
    __table_args__ = {'extend_existing': True}
    __mapper_args__ = {'polymorphic_identity': DiscrFotosoortEnum.Overige_afbeelding}


class Tekening(Foto):
    __tablename__ = 'Def_Foto'
    __table_args__ = {'extend_existing': True}
    __mapper_args__ = {'polymorphic_identity': DiscrFotosoortEnum.Tekening}

    #putID = Column(ForeignKey('Def_Put.primary_key', deferrable=True), index=True)
    #put = relationship('Put', lazy="joined", backref="tekeningen")
    #spoorID = Column(ForeignKey('Def_Spoor.primary_key', deferrable=True), index=True)
    #spoor = relationship('Spoor', backref="tekeningen")
    #vondstID = Column(ForeignKey('Def_Vondst.primary_key', deferrable=True), index=True)
    #vondst = relationship('Vondst', backref="tekeningen")
    materiaal = Column(String(1024))
    omschrijving = Column(Text)
    datum = Column(Date)
    coupe = Column(Boolean)
    details = Column(String(1024))
    microfilm = Column(String(1024))
    periode = Column(String(1024))
    profiel = Column(String(1024))
    schaal = Column(Integer)
    volgnr = Column(Integer)


class Objecttekening(Tekening):
    __tablename__ = 'Def_Foto'
    __table_args__ = {'extend_existing': True}
    __mapper_args__ = {'polymorphic_identity': DiscrFotosoortEnum.Objecttekening}
class Overige_tekening(Tekening):
    __tablename__ = 'Def_Foto'
    __table_args__ = {'extend_existing': True}
    __mapper_args__ = {'polymorphic_identity': DiscrFotosoortEnum.Overige_tekening}





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
    

class Monster(WasstraatModel):
    __tablename__ = 'Def_Monster'

    primary_key = Column(Integer, primary_key=True, autoincrement=True)
    monstercd = Column(String(40), index=True)
    projectID = Column(ForeignKey('Def_Project.primary_key', deferrable=True), index=True)
    project = relationship('Project', lazy="joined", backref="monsters")
    putID = Column(ForeignKey('Def_Put.primary_key', deferrable=True), index=True)
    put = relationship('Put', backref="monsters")
    vondstID = Column(ForeignKey('Def_Vondst.primary_key', deferrable=True), index=True)
    vondst = relationship('Vondst', backref="monsters")
    spoorID = Column(ForeignKey('Def_Spoor.primary_key', deferrable=True), index=True)
    spoor = relationship('Spoor', backref="monsters")
    doosID = Column(ForeignKey('Def_Doos.primary_key', deferrable=True), index=True)
    doos = relationship('Doos', backref="monsters")
    determinatiedatum = Column(String(40), index=True)
    grondsoort = Column(String(250))
    gezeefd_volume = Column(Float)
    restvolume = Column(Float)
    zeefmaat = Column(Float)
    datum_zeven = Column(String(80))
    opmerkingen = Column(Text)
    karakterisering = Column(Text)
    omstandigheden = Column(Text)
    r_analysewaardig_zo = Column(String(20))
    r_analysewaardig_bo = Column(String(20))
    r_concentratie_zo = Column(String(20))
    r_concentratie_bo = Column(String(20))
    r_conservering_zo = Column(String(20))
    r_conservering_bo = Column(String(20))
    r_diversiteit_zo = Column(String(20))
    r_diversiteit_bo = Column(String(20))
    B_stengel_onverkoold = Column(Integer)
    B_zaden_cultuur_onverkoold = Column(Integer)
    B_zaden_kaf_onverkoold = Column(Integer)
    B_zaden_wild_onverkoold = Column(Integer)
    B_zaden_cultuur_mineraaliseerd = Column(Integer)
    C_aardewerk = Column(Integer)
    C_fabsteen = Column(Integer)
    C_glas = Column(Integer)
    C_leer = Column(Integer)
    C_mortel = Column(Integer)
    C_natsteen = Column(Integer)
    C_steenkool = Column(Integer)
    C_textiel = Column(Integer)
    C_leisteen = Column(Integer)
    D_hout = Column(Integer)
    D_houtskool = Column(Integer)
    Z_amfibiebot_O = Column(Integer)
    Z_bot_groot_O = Column(Integer)
    Z_bot_klein_O = Column(Integer)
    Z_eierschaal_of_vel_O = Column(Integer)
    Z_insekten_O = Column(Integer)
    Z_visgraat_of_bot_O = Column(Integer)
    Z_viswervel_O = Column(Integer)
    Z_vliegepop_O = Column(Integer)
    Z_watervlo_ei_O = Column(Integer)
    Z_wormei_O = Column(Integer)
    Z_visschub_O = Column(Integer)
    S_mollusk_zout = Column(Integer)
    S_mossel = Column(Integer)
    B_stengel_mineraaliseerd = Column(Integer)
    B_stengel_recent = Column(Integer)
    B_stengel_verkoold = Column(Integer)
    B_wortel_mineraaliseerd = Column(Integer)
    B_wortel_onverkoold = Column(Integer)
    B_wortel_recent = Column(Integer)
    B_wortel_verkoold = Column(Integer)
    B_zaden_cultuur_recent = Column(Integer)
    B_zaden_cultuur_verkoold = Column(Integer)
    B_zaden_kaf_mineraaliseerd = Column(Integer)
    B_zaden_kaf_recent = Column(Integer)
    B_zaden_kaf_verkoold = Column(Integer)
    B_zaden_wild_mineraaliseerd = Column(Integer)
    B_zaden_wild_recent = Column(Integer)
    B_zaden_wild_verkoold = Column(Integer)
    C_antraciet = Column(Integer)
    C_bewerkt_hout = Column(Integer)
    C_fosfaat = Column(Integer)
    C_huttenleem = Column(Integer)
    C_kleipijp = Column(Integer)
    C_lakzegel = Column(Integer)
    C_metaal = Column(Integer)
    C_ovenslakken = Column(Integer)
    C_turf = Column(Integer)
    D_C14 = Column(Integer)
    S_kokkel = Column(Integer)
    S_oester = Column(Integer)
    Z_amfibiebot_V = Column(Integer)
    Z_bot_groot_V = Column(Integer)
    Z_bot_klein_V = Column(Integer)
    Z_eierschaal_of_vel_V = Column(Integer)
    Z_insekten_V = Column(Integer)
    Z_visgraat_of_bot_V = Column(Integer)
    Z_visschub_V = Column(Integer)
    Z_viswervel_V = Column(Integer)
    Z_vliegepop_V = Column(Integer)
    Z_vogelbot_O = Column(Integer)
    Z_vogelbot_V = Column(Integer)
    Z_watervlo_ei_V = Column(Integer)
    Z_wormei_V = Column(Integer)
    C_overig = Column(String)
    Z_anders = Column(String)
    S_molzoet_of_land = Column(String)
    D_tak_of_knop = Column(String)
    D_te_determ = Column(String)

    def __repr__(self):
        projectcd = self.project.projectcd if self.project else "Onbekend Project"
        vondstnr = ('Vondstnr ' + str(self.vondst.vondstnr)) + " " if self.vondst else ''
        put = ('Put ' + str(self.put.putnr)) + " " if self.put else ''
        opmerkingen = self.opmerkingen if self.opmerkingen else ''

        return f"{opmerkingen} {vondstnr} {put} {projectcd}"




class Monster_Schelp(WasstraatModel):
    __tablename__ = 'Def_Monster_Schelp'

    primary_key = Column(Integer, primary_key=True, autoincrement=True)
    monsterID = Column(ForeignKey('Def_Monster.primary_key', deferrable=True), index=True)
    monster = relationship('Monster', backref="schelpmateriaal")
    aantal = Column(Integer)
    soort = Column(String(80))

class Monster_Botanie(WasstraatModel):
    __tablename__ = 'Def_Monster_Botanie'

    primary_key = Column(Integer, primary_key=True, autoincrement=True)
    monsterID = Column(ForeignKey('Def_Monster.primary_key', deferrable=True), index=True)
    monster = relationship('Monster', backref="botaniemateriaal")
    aantal = Column(Integer)
    deel = Column(String(40))
    staat = Column(String(40))
    soort = Column(String(80))
    determinatie = Column(String(250))



