import datetime
from flask import url_for, Markup
from flask_appbuilder.models.decorators import renders

from flask_appbuilder import Model
from flask_appbuilder.filemanager import ImageManager
from sqlalchemy import BigInteger, Column, Date, DateTime, Float, ForeignKey, Integer, LargeBinary, String, Table, Text, Boolean, JSON, UniqueConstraint, Enum
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy import select, func
from sqlalchemy.ext.hybrid import hybrid_property, hybrid_method
from flask_appbuilder.models.mixins import ImageColumn
from fab_addon_geoalchemy.views import GeoModelView
from fab_addon_geoalchemy.models import GeoSQLAInterface, Geometry

from sqlalchemy.schema import CreateColumn
from sqlalchemy.ext.compiler import compiles
import enum
from sqlalchemy import event
from sqlalchemy.orm import object_mapper



mindate = datetime.date(datetime.MINYEAR, 1, 1)
metadata = Model.metadata


class WasstraatModel(Model):
    __abstract__ = True

    herkomst = Column(Text)
    key = Column(Text)
    soort = Column(String(80))
    brondata = Column(Text)
    uuid = Column('_id', String)

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
    doosnr = Column(Integer, index=True)
    inhoud = Column(Text)
    projectcd = Column(String(12))
    projectnaam = Column(Text)
    stelling = Column(Text)
    uitgeleend = Column(Boolean)
    vaknr = Column(Integer)
    volgletter = Column(Text)
    stellingID = Column(ForeignKey('Def_Stelling.primary_key'), index=True)
    stelling = relationship('Stelling')
    projectID = Column(ForeignKey('Def_Project.primary_key'), index=True)
    project = relationship('Project')
    artefacten = relationship("Artefact", back_populates="doos")

    def __repr__(self):
        projectcd = self.project.projectcd if self.project else "Onbekend Project, "
        stelling = ', Stelling: ' + str(self.stelling) if self.stelling else ''
        vaknr = ', Vaknr: ' + str(self.vaknr) if self.stelling else ''
        return str(self.doosnr) + ' ('+ str(projectcd) + ') ' + stelling + vaknr

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
    project = relationship('Project')

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
    project = relationship('Project')
    putID = Column(ForeignKey('Def_Put.primary_key', deferrable=True), index=True)
    put = relationship('Put')

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
    dateringvanaf = Column(Integer)
    dateringtot = Column(Integer)
    datering = Column(String(1024))
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
    project = relationship('Project')
    putID = Column(ForeignKey('Def_Put.primary_key', deferrable=True), index=True)
    put = relationship('Put')
    vlakID = Column(ForeignKey('Def_Vlak.primary_key', deferrable=True), index=True)
    vlak = relationship('Vlak')

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
    dateringvanaf = Column(Integer)
    dateringtot = Column(Integer)
    datering = Column(String(1024))
    segment = Column(String(1024))
    vaknummer = Column(String(1024))
    vullingnr = Column(String(1024)) 
    projectID = Column(ForeignKey('Def_Project.primary_key', deferrable=True), index=True)
    project = relationship('Project')
    putID = Column(ForeignKey('Def_Put.primary_key', deferrable=True), index=True)
    put = relationship('Put')
    spoorID = Column(ForeignKey('Def_Spoor.primary_key', deferrable=True), index=True)
    spoor = relationship('Spoor')

    def __repr__(self):
        projectcd = self.project.projectcd if self.project else "Onbekend Project, "
        vondstnr = (' Vondstnr ' + str(self.vondstnr)) + " " if self.vondstnr else ''
        put = (' Put ' + str(self.put.putnr)) + " " if self.put else ''

        return projectcd + put + vondstnr + self.omstandigheden if self.omstandigheden else ''



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
    project = relationship('Project')
    putID = Column(ForeignKey('Def_Put.primary_key', deferrable=True), index=True)
    put = relationship('Put')
    spoorID = Column(ForeignKey('Def_Spoor.primary_key', deferrable=True), index=True)
    spoor = relationship('Spoor')

    def __repr__(self):
        projectcd = self.project.projectcd if self.project else "Onbekend Project, "
        vondstnr = (' Vondstnr ' + str(self.vondstnr)) + " " if self.vondstnr else ''
        put = (' Put ' + str(self.put.putnr)) + " " if self.put else ''
        spoornr = (' Spoor ' + str(self.spoor.spoornr)) + " " if self.spoor else ''
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
    dateringvanaf = Column(Integer)
    dateringtot = Column(Integer)
    datering = Column(String(1024))
    conserveren = Column(Integer)
    exposabel = Column(Boolean)
    literatuur = Column(String(1024))
    putnr = Column(Integer)
    subnr = Column(Integer) 
    restauratie = Column(Boolean)
    abr_materiaal = Column(String(1024))
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
    project = relationship('Project')
    putID = Column(ForeignKey('Def_Put.primary_key', deferrable=True), index=True)
    put = relationship('Put')
    vondstID = Column(ForeignKey('Def_Vondst.primary_key', deferrable=True), index=True)
    vondst = relationship('Vondst')
    doosID = Column(ForeignKey('Def_Doos.primary_key', deferrable=True), index=True)
    doos = relationship('Doos')
    artefactsoort =  Column(Enum(DiscrArtefactsoortEnum), index=True)

    def __repr__(self):
        if self.project:
            projectcd = self.project.projectcd if self.project else "Onbekend Project, "
            artefactnr = (' Artf. ' + str(self.artefactnr)) if self.artefactnr else ''
            put = (' Put ' + str(self.put.putnr)) if self.put else ''
            artefactsoort = (str(self.artefactsoort)) if self.artefactsoort else ''
            return projectcd + put + artefactnr +  artefactsoort
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



class Foto(WasstraatModel):
    __tablename__ = 'Def_Foto'

    primary_key = Column(Integer, primary_key=True, autoincrement=True)
    directory = Column(Text)
    fileName = Column(Text, index=True)
    fileSize = Column(Integer)
    fileType = Column(String(32))
    imageUUID = Column(String(1024))
    imageMiddleUUID = Column(String(1024))
    imageThumbUUID = Column(String(1024))
    mime_type = Column(String(20))
    fototype = Column(String(1))
    projectcd = Column(String(12))
    putnr = Column(Integer)
    vondstnr = Column(Integer)
    subnr = Column(Integer)
    fotonr = Column(Integer)
    photo = Column(ImageColumn(size=(1500, 1000, True), thumbnail_size=(300, 200, True)))
    materiaal = Column(String(1024))
    omschrijving = Column(Text)
    datum = Column(Date)
    richting = Column(String(20))
 
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
        project = self.projectcd if self.projectcd else 'Onbekend Project'
        put = (', Put ' + str(self.putnr)) if self.putnr else ''
        sub = (', Art. ' + str(self.subnr)) if self.subnr else ''
        desc = project + put + sub
        if self.artefact:
            return Markup('<a href="' + url_for('ArchArtefactView.show',pk=str(self.artefact.primary_key)) + '">Artefact: '+desc+'</a>')
        else:
            return 'Onbekend'

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
    





