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

mindate = datetime.date(datetime.MINYEAR, 1, 1)
metadata = Model.metadata


class WasstraatModel(Model):
    __abstract__ = True

    herkomst = Column(Text)
    key = Column(Text)
    soort = Column(String(80))
    brondata = Column(Text)
    uuid = Column('_id', String(200))

class Stelling(WasstraatModel):
    __tablename__ = 'Def_Stelling'

    primary_key = Column(Integer, primary_key=True, autoincrement=True)
    uuid = Column('_id', String(200))
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
    uuid = Column('_id', String(200))
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
        projectcd = self.project.projectcd if self.project else "Onbekend Project, "
        return str(self.doosnr) + ' ('+ str(projectcd) + ')'

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
        projectcd = self.project.projectcd if self.project else "Onbekend Project, "
        beschr = str(self.beschrijving) if self.beschrijving else ""

        return projectcd + ' Put ' + str(self.putnr) + ' ' + beschr


class Spoor(WasstraatModel):
    __tablename__ = 'Def_Spoor'

    primary_key = Column(Integer, primary_key=True, autoincrement=True)
    vlaknr = Column(String(200))
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
        projectcd = self.project.projectcd if self.project else "Onbekend Project, "
        put = (' Put ' + str(self.put.putnr)) + " " if self.put else ''
        beschr = str(self.beschrijving) if str(self.beschrijving) else ""

        return projectcd + put + ' Spoor ' + str(self.spoornr) + ' ' + beschr


class Vondst(WasstraatModel):
    __tablename__ = 'Def_Vondst'

    primary_key = Column(Integer, primary_key=True, autoincrement=True)
    vlaknr = Column(String(200))
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
        projectcd = self.project.projectcd if self.project else "Onbekend Project, "
        vondstnr = (' Vondstnr ' + str(self.vondstnr)) + " " if self.vondstnr else ''
        put = (' Put ' + str(self.put.putnr)) + " " if self.put else ''

        return projectcd + put + vondstnr + self.omstandigheden if self.omstandigheden else ''


class DiscrArtefactsoortEnum(enum.Enum): 
    Aardewerk = "Aardewerk"
    Bot = "Bot"
    Glas = "Glas"
    Hoorn = "Hoorn"
    Hout = "Hout"
    Ivoor = "Ivoor"
    Keramiek = "Keramiek"
    Kleipijp = "Kleipijp"
    Leer = "Leer"
    Menselijk_Materiaal = "Menselijk_Materiaal"
    Metaal = "Metaal"
    Munt = "Munt"
    Onbekend = "Onbekend"
    Schelp = "Schelp"
    Spijker = "Spijker"
    Steen = "Steen"
    Textiel = "Textiel"


class Artefact(WasstraatModel):
    __tablename__ = 'Def_Artefact'

    primary_key = Column(Integer, primary_key=True, autoincrement=True)
    artefactnr = Column(Integer)
    beschrijving = Column(Text)
    opmerkingen = Column(Text)
    typevoorwerp = Column(String(200))
    typecd = Column(String(200))
    functievoorwerp = Column(String(200))
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
    ABRcodering = Column(String(200))
    aantal = Column(Integer)
    afmetingen = Column(String(200))
    bibliografie = Column(String(200))
    catalogus = Column(String(200))
    compleetheid = Column(String(200))
    conservering = Column(String(200))
    diversen = Column(Text)
    gewicht = Column(String(200))
    groep = Column(String(200))
    mai = Column(String(200))
    maten = Column(String(200))
    materiaal = Column(String(200))
    naam_voorwerp = Column(String(200))
    plek = Column(String(200))
    publicatiecode = Column(String(200))
    soortvoorwerp = Column(String(200))
    typenaam = Column(String(200))
    versiering = Column(String(200))
    vondstomstandigheden = Column(String(200))
    weggegooid = Column(Integer)
    projectID = Column(ForeignKey('Def_Project.primary_key', deferrable=True), index=True)
    project = relationship('Project')
    putID = Column(ForeignKey('Def_Put.primary_key', deferrable=True), index=True)
    put = relationship('Put')
    vondstID = Column(ForeignKey('Def_Vondst.primary_key', deferrable=True), index=True)
    vondst = relationship('Vondst')
    doosID = Column(ForeignKey('Def_Doos.primary_key', deferrable=True), index=True)
    doos = relationship('Doos')
    artefactsoort =  Column(Enum(DiscrArtefactsoortEnum))

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

    __mapper_args__ = {
        'polymorphic_on': artefactsoort,
        'polymorphic_identity': DiscrArtefactsoortEnum.Onbekend
    }

from sqlalchemy import event
from sqlalchemy.orm import object_mapper

class Aardewerk(Artefact):
    __tablename__ = 'Def_Artefact'
    __table_args__ = {'extend_existing': True}
    __mapper_args__ = {'polymorphic_identity': DiscrArtefactsoortEnum.Aardewerk}

    baksel = Column(String(200), comment="soort AW")
    bakseltype = Column(String(200), comment="bakseltype")
    bodem = Column(String(200), comment="vorm van de bodem/voet")
    categorie = Column(String(200), comment="categorie")
    codes = Column(String(200), comment="codes van type")
    decoratie = Column(String(200), comment="decoratie")
    diameter = Column(String(200), comment="")
    fragment = Column(String(200), comment="fragment: rand, wand, bodem, oor etc")
    glazuur = Column(String(200), comment="glazuur")
    grootste_diameter = Column(String(200), comment="grootste diameter in millimeters, 0 = niet gemeten")
    hoogte = Column(String(200), comment="hoogte in millimeters, 0 = niet gemeten")
    kleur = Column(String(200), comment="kleur")
    materiaal = Column(String(200), comment="materiaal")
    materiaalsoort = Column(String(200), comment="materiaalsoort")
    max_diameter = Column(String(200), comment="")
    oor = Column(String(200), comment="vorm en versiering van oor")
    past_aan = Column(String(200), comment="vondstnummer waar scherf aan past")
    percentage = Column(String(200), comment="aanwezig percentage van een pot")
    productiewijze = Column(String(200), comment="produktiewijze")
    rand = Column(String(200), comment="vorm en versiering van rand")
    rand_bodem = Column(String(200), comment="diameter bodem in millimeters, 0 = niet gemeten")
    rand_diameter = Column(String(200), comment="diameter rand in millimeters, 0 = niet gemeten")
    vorm = Column(String(200), comment="vorm")


#van Artefact afgeleide class Bot
class Bot(Artefact):
    __tablename__ = 'Def_Artefact'
    __table_args__ = {'extend_existing': True}
    __mapper_args__ = {'polymorphic_identity': DiscrArtefactsoortEnum.Bot}

    aantal_puzzelen = Column(String(200), comment="Aantal voor puzzelen")
    associatie = Column(String(200), comment="Associatie")
    bewerkingssporen = Column(String(200), comment="Bewerkingssporen")
    brandsporen = Column(String(200), comment="Brandsporen")
    diersoort = Column(String(200), comment="Diersoort")
    geconserveerd = Column(String(200), comment="geconserveerd")
    graf = Column(String(200), comment="Soort graf")
    individunr = Column(String(200), comment="Individunummer")
    knaagsporen = Column(String(200), comment="Knaagsporen")
    leeftijd = Column(String(200), comment="Leeftijd individu")
    lengte = Column(String(200), comment="Lengte in cm")
    maat1 = Column(String(200), comment="Maat 1 in mm")
    maat2 = Column(String(200), comment="Maat 2 in mm")
    maat3 = Column(String(200), comment="Maat 3 in mm")
    maat4 = Column(String(200), comment="Maat 4 in mm")
    materiaal = Column(String(200), comment="Materiaal")
    oriëntatie = Column(String(200), comment="Oriëntatie (Links - Rechts)")
    pathologie = Column(String(200), comment="Pathologie")
    percentage = Column(String(200), comment="Percentage")
    skeletdeel = Column(String(200), comment="Skeletdeel")
    slijtage = Column(String(200), comment="Slijtage onderkaaks P4, Grant 1982")
    slijtage_onderkaaks_DP4 = Column(String(200), comment="Slijtage onderkaaks DP4, Grant 1982")
    slijtage_onderkaaks_M1 = Column(String(200), comment="Slijtage onderkaaks M1, Grant 1982")
    slijtage_onderkaaks_M2 = Column(String(200), comment="Slijtage onderkaaks M2, Grant 1982")
    slijtage_onderkaaks_M3 = Column(String(200), comment="Slijtage onderkaaks M3, Grant 1982")
    symmetrie = Column(String(200), comment="Symmetrie")
    vergroeiing = Column(String(200), comment="Vergroeiing")


#van Artefact afgeleide class Glas
class Glas(Artefact):
    __tablename__ = 'Def_Artefact'
    __table_args__ = {'extend_existing': True}
    __mapper_args__ = {'polymorphic_identity': DiscrArtefactsoortEnum.Glas}

    decoratie = Column(String(200), comment="decoratie")
    diameter_bodem = Column(String(200), comment="diameter bodem in millimeters, 0 = niet gemeten")
    diameter_rand = Column(String(200), comment="diameter rand in millimeters, 0 = niet gemeten")
    glassoort = Column(String(200), comment="Soort glas")
    grootste = Column(String(200), comment="grootste diameter in millimeters, 0 = niet gemeten")
    hoogte = Column(String(200), comment="hoogte in millimeters, 0 = niet gemeten")
    kleur = Column(String(200), comment="kleur")
    minimum_aantal_individuen = Column(String(200), comment="MAI, minimum aantal individuen, 0 = onbekend, meer dan 1")
    past_aan = Column(String(200), comment="Past aan")
    past_aan_andere_nummers = Column(String(200), comment="past aan andere nummers:")
    percentage_rand = Column(String(200), comment="Randpercentage")
    vorm_bodem_voet = Column(String(200), comment="vorm van de bodem/voet + eventuele merkjes")
    vorm_versiering_cuppa = Column(String(200), comment="vorm en versiering van cuppa")
    vorm_versiering_oor_stam = Column(String(200), comment="vorm en versiering van oor/stam")


#van Artefact afgeleide class Hoorn
class Hoorn(Artefact):
    __tablename__ = 'Def_Artefact'
    __table_args__ = {'extend_existing': True}
    __mapper_args__ = {'polymorphic_identity': DiscrArtefactsoortEnum.Hoorn}



#van Artefact afgeleide class Hout
class Hout(Artefact):
    __tablename__ = 'Def_Artefact'
    __table_args__ = {'extend_existing': True}
    __mapper_args__ = {'polymorphic_identity': DiscrArtefactsoortEnum.Hout}

    C14_datering = Column(String(200), comment="C14 datering mogelijk ja of nee")
    bewerkingssporen = Column(String(200), comment="bewerkingssporen")
    decoratie = Column(String(200), comment="decoratie")
    dendrodatering = Column(String(200), comment="dendrodatering mogelijk ja of nee")
    determinatieniveau = Column(String(200), comment="het determinatieniveau; bv. cf. = onzekere determinatie")
    diameter = Column(String(200), comment="diameter in cm van de stam/tak")
    gebruikssporen = Column(String(200), comment="gebruikssporen")
    houtsoort = Column(String(200), comment="code voor de houtsoort")
    houtsoortcd = Column(String(200), comment="code voor de houtsoort")
    jaarring_bast_spint = Column(String(200), comment="jaarring, spint, bast")
    puntlengte = Column(String(200), comment="puntlengte : de lengte  in cm van de punt gemeten van hoogste kapvlak")
    puntvorm = Column(String(200), comment="puntvorm : het aantal vlakken warrmee de punt is gemaakt halverwege de punt")
    stamcode = Column(String(200), comment="stamcode : 0 =onbekend")


#van Artefact afgeleide class Ivoor
class Ivoor(Artefact):
    __tablename__ = 'Def_Artefact'
    __table_args__ = {'extend_existing': True}
    __mapper_args__ = {'polymorphic_identity': DiscrArtefactsoortEnum.Ivoor}



#van Artefact afgeleide class Keramiek
class Keramiek(Artefact):
    __tablename__ = 'Def_Artefact'
    __table_args__ = {'extend_existing': True}
    __mapper_args__ = {'polymorphic_identity': DiscrArtefactsoortEnum.Keramiek}

    baksel = Column(String(200), comment="Baksel")
    bodem = Column(String(200), comment="Bodem")
    brandsporen = Column(String(200), comment="Brandsporen")
    diameter_bodem = Column(String(200), comment="Diameter van bodem")
    gedraaid = Column(String(200), comment="")
    glazuur = Column(String(200), comment="Glazuur")
    grootste_diameter = Column(String(200), comment="Grootste diameter")
    handgevormd = Column(String(200), comment="")
    hoogte = Column(String(200), comment="Hoogte van voorwerp")
    kleur = Column(String(200), comment="Kleur van voorwerp")
    magering = Column(String(200), comment="magering")
    maker = Column(String(200), comment="Maker (vnl. i.g.v. kleipijpen)")
    oor_steel = Column(String(200), comment="Oor steel")
    oppervlakte = Column(String(200), comment="oppervlakte behandeling")
    past_aan = Column(String(200), comment="Past aan")
    productiewijze = Column(String(200), comment="Productie wijze")
    randdiameter = Column(String(200), comment="Randdiameter in cm")
    randindex = Column(String(200), comment="Randindex (RANDPER / 100)")
    randpercentage = Column(String(200), comment="Randpercentage")
    subbaksel = Column(String(200), comment="Subbaksel")
    type_rand = Column(String(200), comment="type rand")
    vorm = Column(String(200), comment="Vorm")
    wanddikte = Column(String(200), comment="wanddikte")


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

    beschrijving_zool = Column(String(200), comment="Verder beschrijving van de zool")
    bewerking = Column(String(200), comment="bewerking")
    bewerkinssporen = Column(String(200), comment="Bewerkinssporen")
    bovenleer = Column(String(200), comment="bovenleer: bv. wreef, hiel, tong, etc.")
    decoratie = Column(String(200), comment="decoratie")
    kwaliteit = Column(String(200), comment="kwaliteit: goed, redelijk, matig, slecht")
    leersoort = Column(String(200), comment="Leersoort (Naam dier)")
    past_aan = Column(String(200), comment="past aan andere nummers:")
    sluiting = Column(String(200), comment="sluiting: bv. veter, gesp, riem, etc.")
    soort_sluiting = Column(String(200), comment="Soort sluiting")
    toestand = Column(String(200), comment="toestand: nat of droog")
    type_bovenleer = Column(String(200), comment="Type bovenleer")
    verbinding = Column(String(200), comment="verbinding tussen zool en bovenleer")
    zool = Column(String(200), comment="zool: dubbel, enkel, etc.")
    zoolvorm = Column(String(200), comment="zoolvorm: code volgens Goubitz, Stepping through time (bladzijde 82)")


#van Artefact afgeleide class Menselijk_Materiaal
class Menselijk_Materiaal(Artefact):
    __tablename__ = 'Def_Artefact'
    __table_args__ = {'extend_existing': True}
    __mapper_args__ = {'polymorphic_identity': DiscrArtefactsoortEnum.Menselijk_Materiaal}

    breedte_kist_hoofdeinde = Column(String(200), comment="in cm")
    breedte_kist_voeteinde = Column(String(200), comment="in cm")
    doos_delft = Column(String(200), comment="")
    doos_lumc = Column(String(200), comment="")
    kist_waargenomen = Column(String(200), comment="")
    lengte_kist = Column(String(200), comment="in cm")
    linkerarm = Column(String(200), comment="")
    linkerbeen = Column(String(200), comment="")
    plaats = Column(String(200), comment="")
    primair_graf = Column(String(200), comment="")
    rechterarm = Column(String(200), comment="")
    rechterbeen = Column(String(200), comment="")
    schedel = Column(String(200), comment="")
    secundair_graf = Column(String(200), comment="")
    skeletelementen = Column(String(200), comment="")
    wervelkolom = Column(String(200), comment="")


#van Artefact afgeleide class Metaal
class Metaal(Artefact):
    __tablename__ = 'Def_Artefact'
    __table_args__ = {'extend_existing': True}
    __mapper_args__ = {'polymorphic_identity': DiscrArtefactsoortEnum.Metaal}

    bewerking = Column(String(200), comment="bewerking")
    decoratie = Column(String(200), comment="decoratie")
    diverse = Column(String(200), comment="diverse: aangetast, licht aangetast, zwaar aangetast en/of geirriseerd")
    materiaalsoort = Column(String(200), comment="")
    metaalsoort = Column(String(200), comment="Metaal soort")
    oppervlak = Column(String(200), comment="oppervlak")
    percentage = Column(String(200), comment="")


#van Artefact afgeleide class Munt
class Munt(Artefact):
    __tablename__ = 'Def_Artefact'
    __table_args__ = {'extend_existing': True}
    __mapper_args__ = {'polymorphic_identity': DiscrArtefactsoortEnum.Munt}

    aard_verwerving = Column(String(200), comment="koop, schenking, legaat, bruikleen etc.")
    autoriteit = Column(String(200), comment="naam van vorst (met jaartallen), instantie, opdrachtgever")
    conditie = Column(String(200), comment="alleen invullen in uitzonderlijke situatie, restauratie nodig ?")
    eenheid = Column(String(200), comment="bv : kwart, halve, dubbele, 1, 10, 25")
    gelegenheid = Column(String(200), comment="korte aanduiding")
    inventaris = Column(String(200), comment="huidig inventarisnummer (eventueel oude inv. nrs)")
    jaartal = Column(String(200), comment="jaartal op voorwerp (of periode)")
    keerzijde_tekst = Column(String(200), comment="volledige teks")
    kwaliteit = Column(String(200), comment="numismatische kwaliteitsaanduiding : goed, f.d.c.")
    land = Column(String(200), comment="land van uitgifte (politieke eenheid)")
    materiaal = Column(String(200), comment="bv : goud, zilver")
    muntplaats = Column(String(200), comment="plaats van aanmunting")
    muntsoort = Column(String(200), comment="in enkelvoud, bv daalder, gulden, cent")
    ontwerper = Column(String(200), comment="naam (met jaartallen)")
    plaats = Column(String(200), comment="plaats van bewaring")
    produktiewijze = Column(String(200), comment="alleen invullen indien nodig")
    randafwerking = Column(String(200), comment="alleen invullen indien niet glad")
    randschrift = Column(String(200), comment="volldedige tekst")
    rubriek = Column(String(200), comment="grove indeling in gebied, periode of politieke eenheid")
    signalement = Column(String(200), comment="korte beschrijving, signalement")
    verworven_van = Column(String(200), comment="verworven van wie en wanneer")
    vindplaats = Column(String(200), comment="allleen voor(bodem)vondsten, waar en wanneer")
    voorwaarden_verwerving = Column(String(200), comment="eventueel aan de verwerving verbonden voorwaarden")
    voorzijde_tekst = Column(String(200), comment="volledige teks")
    vorm = Column(String(200), comment="alleen invullen als voorwerp niet rond is")


#van Artefact afgeleide class Onbekend
class Onbekend(Artefact):
    __tablename__ = 'Def_Artefact'
    __table_args__ = {'extend_existing': True}
    __mapper_args__ = {'polymorphic_identity': DiscrArtefactsoortEnum.Onbekend}



#van Artefact afgeleide class Schelp
class Schelp(Artefact):
    __tablename__ = 'Def_Artefact'
    __table_args__ = {'extend_existing': True}
    __mapper_args__ = {'polymorphic_identity': DiscrArtefactsoortEnum.Schelp}



#van Artefact afgeleide class Spijker
class Spijker(Artefact):
    __tablename__ = 'Def_Artefact'
    __table_args__ = {'extend_existing': True}
    __mapper_args__ = {'polymorphic_identity': DiscrArtefactsoortEnum.Spijker}



#van Artefact afgeleide class Steen
class Steen(Artefact):
    __tablename__ = 'Def_Artefact'
    __table_args__ = {'extend_existing': True}
    __mapper_args__ = {'polymorphic_identity': DiscrArtefactsoortEnum.Steen}

    decoratie = Column(String(200), comment="decoratie")
    diameter = Column(String(200), comment="diameter in mm")
    dikte = Column(String(200), comment="dikte in mm")
    grootste_diameter = Column(String(200), comment="Grootste diameter in cm")
    kleur = Column(String(200), comment="kleur")
    lengte = Column(String(200), comment="Lengte in cm")
    past_aan = Column(String(200), comment="past aan andere nummers:")
    steengroep = Column(String(200), comment="Steengroep")
    steensoort = Column(String(200), comment="steensoort")
    subsoort = Column(String(200), comment="subsoort")


#van Artefact afgeleide class Textiel
class Textiel(Artefact):
    __tablename__ = 'Def_Artefact'
    __table_args__ = {'extend_existing': True}
    __mapper_args__ = {'polymorphic_identity': DiscrArtefactsoortEnum.Textiel}



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
    imageUUID = Column(String(200))
    imageMiddleUUID = Column(String(200))
    imageThumbUUID = Column(String(200))
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
        project = self.projectcd if self.projectcd else 'Onbekend Project'
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
        projectcd = self.project.projectcd if self.project else "Onbekend Project, "        
        put = (' Put ' + str(self.put.putnr)) + " " if self.put else ''
        vlak = (' Vlaknr ' + str(self.vlaknr)) + " " if self.vlaknr else ''

        return projectcd + put + vlak + self.beschrijving if self.beschrijving else ''





