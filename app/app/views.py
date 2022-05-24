import copy
#from PIL import Image

#from flask import url_for, Markup

from flask_appbuilder import GroupByChartView, MultipleView
from flask_appbuilder.models.group import aggregate_count
from flask_appbuilder.models.sqla.interface import SQLAInterface
#from flask_appbuilder.widgets import (
#    ListBlock, ListItem, ListLinkWidget, ListThumbnail, ShowBlockWidget, ListCarousel, ShowWidget
#)
#from flask_appbuilder.fieldwidgets import BS3TextFieldWidget
from flask_appbuilder.models.group import aggregate_count
from flask_appbuilder.models.sqla.filters import FilterEqual
#from fab_addon_geoalchemy.views import GeoModelView
from fab_addon_geoalchemy.models import GeoSQLAInterface

#from wtforms.fields import StringField

from . import db, appbuilder
from .models import Aardewerk, Stelling, Doos, Artefact, Foto, Spoor, Project,Put, Vondst, Vlak, DiscrArtefactsoortEnum, Dierlijk_Bot, Glas, Hout, Bouwaardewerk, Kleipijp, Leer, Menselijk_Bot, Metaal, Munt, Schelp, Steen, Textiel, Vulling
from .widgets import MediaListWidget
from .baseviews import WSModelView, WSGeoModelView
import app.util as util
#import sqlalchemy as sa

from flask_appbuilder.actions import action
from flask import redirect


flds_migratie_info = ("Migratie-informatie", {"fields": ["soort","brondata","herkomst"],"expanded": False})

class ArtefactChartView(GroupByChartView):
    datamodel = SQLAInterface(Artefact)
    chart_title = 'Telling Artefacten'

    definitions = [
    {
        'label': 'Soorten Artefact',
        'group': 'artefactsoort',
        'series': [(aggregate_count,'primary_key')],
        'group_by_label': 'Telling'
    },
    {
        'label': 'Origine Artefact',
        'group': 'origine',
        'series': [(aggregate_count,'primary_key')],
        'group_by_label': 'Telling'
    }
]

class ArtefactLineChartView(GroupByChartView):
    datamodel = SQLAInterface(Artefact)
    chart_title = 'Datering Artefacten'
    chart_type = 'LineChart'

    definitions = [
    {
        'label': 'Datering Vanaf',
        'group': 'dateringvanaf',
        'series': [(aggregate_count,'primary_key')],
        'group_by_label': 'Datum vanaf'
    },
    {
        'label': 'Datering Tot',
        'group': 'dateringtot',
        'series': [(aggregate_count,'primary_key')],
        'group_by_label': 'Datum tot'
    }
]


class ArchFotoView(WSModelView):
    datamodel = SQLAInterface(Foto)
    list_widget = MediaListWidget
    list_title = "Foto's"
    # base_permissions = ['can_add', 'can_show']
    list_columns = ["fileName", 'koppeling', 'photo_img_thumbnail']
    show_columns = ["project", "fototype", 'omschrijving', 'materiaal', 'richting', 'datum', "vondstnr", "subnr", "fotonr", "artefact", "fileName", 'directory', 'photo_img', 'photo']
    add_template = 'widgets/add_photo.html'
    #edit_form_extra_fields = {
    #    'photo': StringField('Foto', render_kw={'readonly': True})
    #}
    fieldsets = [
        ("Projectvelden", {"fields": ["project", "artefact"]}),
        ("Fotovelden", {"fields": ["fileName", "directory", "fotonr", "fileType", 'mime_type', 'photo']}),
        (
            "Migratie-informatie",
            {
                "fields": [
                    "imageUUID",
                    "imageMiddleUUID",
                    "imageThumbUUID",
                    "soort",
                ],
                "expanded": False,
            },
        ),
    ]
    #show_fieldsets = fieldsets
    edit_fieldsets = fieldsets
    base_order = ('fileName','asc')
 
    @action("5linkskantelen", "Kantelen Linksom", "Geselecteerde foto's linksom kantelen?", "fa-rocket")
    def linkskantelen(self, items):
        if isinstance(items, list):
            for foto in items:
                foto = util.rotateImage(foto, 90)
                self.datamodel.edit(foto, raise_exception=True)

            self.update_redirect()
        else:
            foto = util.rotateImage(items, 90)
            self.datamodel.edit(foto)
        return redirect(self.get_redirect())

    @action("6rechtskantelen", "Kantelen Rechtsom", "Geselecteerde foto's rechtsom kantelen?", "fa-rocket")
    def rechtskantelen(self, items):
        if isinstance(items, list):
            for foto in items:
                foto = util.rotateImage(foto, -90)
                self.datamodel.edit(foto, raise_exception=True)

            self.update_redirect()
        else:
            foto = util.rotateImage(items, -90)
            self.datamodel.edit(foto)
        return redirect(self.get_redirect())



class ArchOpgravingFotoView(ArchFotoView):
    base_filters = [['fototype', FilterEqual, 'G']]
    list_title = "Opgravingsfoto's"

class ArchSfeerFotoView(ArchFotoView):
    base_filters = [['fototype', FilterEqual, 'F']]
    list_title = "Sfeerfoto's"

class ArchArtefactFotoView(ArchFotoView):
    base_filters = [['fototype', FilterEqual, 'H']]
    list_title = "Artefactfoto's"

class ArchNietFotoView(ArchFotoView):
    base_filters = [['fototype', FilterEqual, 'N']]
    list_title = "Foto's zonder duiding"





class ArchArtefactView(WSModelView):
    datamodel = SQLAInterface(Artefact)
    # base_permissions = ['can_add', 'can_show']
    list_columns = ["vondst", "subnr", "artefactsoort", "datering", 'typevoorwerp']
    #list_widget = ListThumbnail
    list_title = "Artefacten"
    related_views = [ArchArtefactFotoView]
    show_fieldsets = [
        ("Projectvelden", {"columns": [
            {"fields": ["project", "vondst", "subnr", "aantal", "abr_materiaal", "artefactsoort", "typevoorwerp", "typecd", "functievoorwerp", "versiering", "beschrijving", "opmerkingen", "doos"], "grid":6},        
            {"fields": ["fotos"], "grid":6, "fulldisplay": True},        
        ]}),        
        ("Algemene Artefactvelden", {"columns": [
            {"fields": ["origine", "dateringvanaf", "dateringtot", "datering", "conservering", "exposabel", "restauratie", "literatuur", "publicatiecode", "catalogus", "weggegooid"], "grid":6},        
            {"fields": ["aantal", "gewicht", "afmetingen", "formaat_horizontaal", "formaat_vericaal", "compleetheid", "mai", "diversen"], "grid":6},        
        ]}),
    flds_migratie_info]
    edit_fieldsets = show_fieldsets
    add_fieldsets = util.removeFieldFromFieldset(show_fieldsets, "artefactsoort")
 
'''
Nog niet
    groep = Column(String(200))
    materiaal = Column(String(200))
    naam_voorwerp = Column(String(200))
    plek = Column(String(200))
    vondstomstandigheden = Column(String(200))
    '''
class ArchAardewerkView(ArchArtefactView):
    datamodel = SQLAInterface(Aardewerk)
    base_filters = [['artefactsoort', FilterEqual, DiscrArtefactsoortEnum.Aardewerk.value]]

    list_title = "Aardewerk"
    related_views = []
    aardewerk_fieldset = [("Aardewerkvelden", {"columns": [
            {"fields": ["baksel", "bakseltype", "categorie", "decoratie", "glazuur", "kleur", "oor", "productiewijze"], "grid":6},        
            {"fields": ["bodem", "diameter", "grootste_diameter", "max_diameter", "rand", "rand_bodem", "rand_diameter", "vorm"], "grid":6},        
        ]},     
        )]
    show_fieldsets = copy.deepcopy(ArchArtefactView.show_fieldsets)    
    show_fieldsets[len(show_fieldsets)-1:len(show_fieldsets)-1] = aardewerk_fieldset
    add_fieldsets = util.removeFieldFromFieldset(show_fieldsets, "artefactsoort")
    edit_fieldsets = show_fieldsets

'''
Nog niet
    codes = Column(String(200), comment="codes van type")
    materiaal = Column(String(200), comment="materiaal")
    materiaalsoort = Column(String(200), comment="materiaalsoort")
    past_aan = Column(String(200), comment="vondstnummer waar scherf aan past")
    percentage = Column(String(200), comment="aanwezig percentage van een pot")

'''

class ArchDierlijk_BotView(ArchArtefactView):
    datamodel = SQLAInterface(Dierlijk_Bot)
    base_filters = [['artefactsoort', FilterEqual, DiscrArtefactsoortEnum.Dierlijk_Bot.value]]

    list_title = "Dierlijk Bot"
    related_views = []
    aardewerk_fieldset = [("Botvelden", {"columns": [
            {"fields": ["diersoort", "bewerkingssporen", "brandsporen", "knaagsporen", "graf", "leeftijd", "pathologie", "symmetrie", "vergroeiing", "oriëntatie"], "grid":6},        
            {"fields": ["lengte", "maat1", "maat2", "maat3", "maat4", "skeletdeel", "slijtage", "slijtage_onderkaaks_DP4", "slijtage_onderkaaks_M1", "slijtage_onderkaaks_M2", "slijtage_onderkaaks_M3"], "grid":6},        
        ]},     
        )]
    show_fieldsets = copy.deepcopy(ArchArtefactView.show_fieldsets)    
    show_fieldsets[len(show_fieldsets)-1:len(show_fieldsets)-1] = aardewerk_fieldset
    add_fieldsets = util.removeFieldFromFieldset(show_fieldsets, "artefactsoort")
    edit_fieldsets = show_fieldsets



class ArchGlasView(ArchArtefactView):
    datamodel = SQLAInterface(Glas)
    base_filters = [['artefactsoort', FilterEqual, DiscrArtefactsoortEnum.Glas.value]]

    list_title = "Glas"
    related_views = []
    aardewerk_fieldset = [("Glasvelden", {"columns": [
            {"fields": ["decoratie", "glassoort", "kleur", "vorm_bodem_voet", "vorm_versiering_cuppa", "vorm_versiering_oor_stam"], "grid":6},        
            {"fields": ["diameter_bodem", "diameter_rand", "grootste", "hoogte", "percentage_rand"], "grid":6},        
        ]},     
        )]
    show_fieldsets = copy.deepcopy(ArchArtefactView.show_fieldsets)    
    show_fieldsets[len(show_fieldsets)-1:len(show_fieldsets)-1] = aardewerk_fieldset
    add_fieldsets = util.removeFieldFromFieldset(show_fieldsets, "artefactsoort")
    edit_fieldsets = show_fieldsets



class ArchHoutView(ArchArtefactView):
    datamodel = SQLAInterface(Hout)
    base_filters = [['artefactsoort', FilterEqual, DiscrArtefactsoortEnum.Hout.value]]

    list_title = "Hout"
    related_views = []
    hout_fieldset = [("Houtvelden", {"columns": [
            {"fields": ["bewerkingssporen", "decoratie", "determinatieniveau", "gebruikssporen", "houtsoort", "houtsoortcd"], "grid":6},        
            {"fields": ["C14_datering", "dendrodatering", "jaarring_bast_spint", "puntlengte", "puntvorm", "stamcode"], "grid":6},        
        ]},     
        )]
    show_fieldsets = copy.deepcopy(ArchArtefactView.show_fieldsets)    
    show_fieldsets[len(show_fieldsets)-1:len(show_fieldsets)-1] = hout_fieldset
    add_fieldsets = util.removeFieldFromFieldset(show_fieldsets, "artefactsoort")
    edit_fieldsets = show_fieldsets



class ArchBouwaardewerkView(ArchArtefactView):
    datamodel = SQLAInterface(Bouwaardewerk)
    base_filters = [['artefactsoort', FilterEqual, DiscrArtefactsoortEnum.Bouwaardewerk.value]]

    list_title = "Bouwaardewerk"
    related_views = []
    Bouwaardewerk_fieldset = [("Bouwaardewerkvelden", {"columns": [
            {"fields": ["baksel", "brandsporen", "gedraaid", "glazuur", "handgevormd", "kleur", "magering", "maker", "oor_steel", "productiewijze", "vorm"], "grid":6},        
            {"fields": ["bodem", "diameter_bodem", "grootste_diameter", "hoogte", "oppervlakte", "past_aan", "randdiameter", "randindex", "randpercentage", "subbaksel", "type_rand", "wanddikte"], "grid":6},        
        ]},     
        )]
    show_fieldsets = copy.deepcopy(ArchArtefactView.show_fieldsets)    
    show_fieldsets[len(show_fieldsets)-1:len(show_fieldsets)-1] = Bouwaardewerk_fieldset
    add_fieldsets = util.removeFieldFromFieldset(show_fieldsets, "artefactsoort")
    edit_fieldsets = show_fieldsets


class ArchKleipijpView(ArchArtefactView):
    datamodel = SQLAInterface(Kleipijp)
    base_filters = [['artefactsoort', FilterEqual, DiscrArtefactsoortEnum.Kleipijp.value]]

    list_title = "Kleipijp"
    related_views = []
    kleipijp_fieldset = []
    show_fieldsets = copy.deepcopy(ArchArtefactView.show_fieldsets)    
    #show_fieldsets[len(show_fieldsets)-1:len(show_fieldsets)-1] = kleipijp_fieldset
    add_fieldsets = util.removeFieldFromFieldset(show_fieldsets, "artefactsoort")
    edit_fieldsets = show_fieldsets



class ArchLeerView(ArchArtefactView):
    datamodel = SQLAInterface(Leer)
    base_filters = [['artefactsoort', FilterEqual, DiscrArtefactsoortEnum.Leer.value]]

    list_title = "Leer"
    related_views = []
    leer_fieldset = [("Leervelden", {"columns": [
            {"fields": ["bewerkingssporen", "bewerking", "bovenleer", "decoratie", "kwaliteit", "leersoort", "toestand"], "grid":6},        
            {"fields": ["beschrijving_zool", "past_aan", "sluiting", "soort_sluiting", "type_bovenleer", "verbinding", "zool", "zoolvorm"], "grid":6},        
        ]},     
        )]
    show_fieldsets = copy.deepcopy(ArchArtefactView.show_fieldsets)    
    show_fieldsets[len(show_fieldsets)-1:len(show_fieldsets)-1] = leer_fieldset
    add_fieldsets = util.removeFieldFromFieldset(show_fieldsets, "artefactsoort")
    edit_fieldsets = show_fieldsets


class ArchMenselijk_BotView(ArchArtefactView):
    datamodel = SQLAInterface(Menselijk_Bot)
    base_filters = [['artefactsoort', FilterEqual, DiscrArtefactsoortEnum.Menselijk_Bot.value]]

    list_title = "Menselijk Bot"
    related_views = []
    menselijk_materiaal_fieldset = [("Leervelden", {"columns": [
            {"fields": ["doos_delft", "doos_lumc", "linkerarm", "linkerbeen", "rechterarm", "rechterbeen", "schedel", "wervelkolom", "skeletelementen"], "grid":6},        
            {"fields": ["breedte_kist_hoofdeinde", "breedte_kist_voeteinde", "lengte_kist", "kist_waargenomen", "primair_graf", "secundair_graf", "plaats"], "grid":6},        
        ]},     
        )]
    show_fieldsets = copy.deepcopy(ArchArtefactView.show_fieldsets)    
    show_fieldsets[len(show_fieldsets)-1:len(show_fieldsets)-1] = menselijk_materiaal_fieldset
    add_fieldsets = util.removeFieldFromFieldset(show_fieldsets, "artefactsoort")
    edit_fieldsets = show_fieldsets



class ArchMetaalView(ArchArtefactView):
    datamodel = SQLAInterface(Metaal)
    base_filters = [['artefactsoort', FilterEqual, DiscrArtefactsoortEnum.Metaal.value]]

    list_title = "Metaal"
    related_views = []
    metaal_fieldset = [("Metaalvelden", {"columns": [
            {"fields": ["bewerking", "decoratie", "diverse"], "grid":6},        
            {"fields": ["metaalsoort", "oppervlak", "percentage"], "grid":6},        
        ]},     
        )]
    show_fieldsets = copy.deepcopy(ArchArtefactView.show_fieldsets)    
    show_fieldsets[len(show_fieldsets)-1:len(show_fieldsets)-1] = metaal_fieldset
    add_fieldsets = util.removeFieldFromFieldset(show_fieldsets, "artefactsoort")
    edit_fieldsets = show_fieldsets


class ArchMuntView(ArchArtefactView):
    datamodel = SQLAInterface(Munt)
    base_filters = [['artefactsoort', FilterEqual, DiscrArtefactsoortEnum.Munt.value]]

    list_title = "Munt"
    related_views = []
    munt_fieldset = [("Muntvelden", {"columns": [
            {"fields": ["aard_verwerving", "verworven_van", "voorwaarden_verwerving", "ontwerper", "conditie", "inventaris", "kwaliteit", "plaats", "produktiewijze", "randafwerking", "rubriek", "signalement", "vindplaats", "vorm"], "grid":6},        
            {"fields": ["eenheid", "gelegenheid", "jaartal", "voorzijde_tekst", "keerzijde_tekst", "autoriteit", "land", "muntplaats", "muntsoort", "randschrift"], "grid":6},        
        ]},     
        )]
    show_fieldsets = copy.deepcopy(ArchArtefactView.show_fieldsets)    
    show_fieldsets[len(show_fieldsets)-1:len(show_fieldsets)-1] = munt_fieldset
    add_fieldsets = util.removeFieldFromFieldset(show_fieldsets, "artefactsoort")
    edit_fieldsets = show_fieldsets


class ArchSchelpView(ArchArtefactView):
    datamodel = SQLAInterface(Schelp)
    base_filters = [['artefactsoort', FilterEqual, DiscrArtefactsoortEnum.Schelp.value]]

    list_title = "Schelp"
    related_views = []
    schelp_fieldset = []
    show_fieldsets = copy.deepcopy(ArchArtefactView.show_fieldsets)    
    #show_fieldsets[len(show_fieldsets)-1:len(show_fieldsets)-1] = schelp_fieldset
    add_fieldsets = util.removeFieldFromFieldset(show_fieldsets, "artefactsoort")
    edit_fieldsets = show_fieldsets


class ArchSteenlView(ArchArtefactView):
    datamodel = SQLAInterface(Steen)
    base_filters = [['artefactsoort', FilterEqual, DiscrArtefactsoortEnum.Steen.value]]

    list_title = "Steen"
    related_views = []
    steen_fieldset = [("Steenvelden", {"columns": [
            {"fields": ["decoratie", "decoratie", "kleur", "steengroep", "steensoort", "subsoort"], "grid":6},        
            {"fields": ["diameter", "dikte", "grootste_diameter", "lengte", "past_aan"], "grid":6},        
        ]},     
        )]
    show_fieldsets = copy.deepcopy(ArchArtefactView.show_fieldsets)    
    show_fieldsets[len(show_fieldsets)-1:len(show_fieldsets)-1] = steen_fieldset
    add_fieldsets = util.removeFieldFromFieldset(show_fieldsets, "artefactsoort")
    edit_fieldsets = show_fieldsets


class ArchTextielView(ArchArtefactView):
    datamodel = SQLAInterface(Textiel)
    base_filters = [['artefactsoort', FilterEqual, DiscrArtefactsoortEnum.Textiel.value]]

    list_title = "Textiel"
    related_views = []
    textiel_fieldset = []
    show_fieldsets = copy.deepcopy(ArchArtefactView.show_fieldsets)    
    #show_fieldsets[len(show_fieldsets)-1:len(show_fieldsets)-1] = textiel_fieldset
    add_fieldsets = util.removeFieldFromFieldset(show_fieldsets, "artefactsoort")
    edit_fieldsets = show_fieldsets


class ArchDoosView(WSModelView):
    datamodel = SQLAInterface(Doos)
    # base_permissions = ['can_add', 'can_show']
    list_columns = ["project", "doosnr", "inhoud", 'stelling', 'vaknr', "aantalArtefacten"]
    base_order = ("doosnr", "asc")
    related_views = [ArchArtefactView]
    list_title = "Dozen"
    show_fieldsets = [
        ("Hoofdvelden", {"fields": ["project", "doosnr", "inhoud", "aantalArtefacten"]}),
        ("Locatie", {"fields": ["stelling", "vaknr", "volgletter", "uitgeleend"]}),
        flds_migratie_info]

class ArchStellingView(WSModelView):
    datamodel = SQLAInterface(Stelling)
    # base_permissions = ['can_add', 'can_show']
    list_columns = ["stelling", "inhoud"]
    base_order = ("stelling", "asc")
    list_title = "Stellingen"
    related_views = [ArchDoosView]
    show_fieldsets = [
        ("Hoofdvelden", {"fields": ["stelling", "inhoud"]}),
        flds_migratie_info]
    add_fieldsets = show_fieldsets
    edit_fieldsets = show_fieldsets



class ArchVondstView(WSModelView):
    datamodel = SQLAInterface(Vondst)
    # base_permissions = ['can_add', 'can_show']
    list_title = "Vondsten"
    list_columns = ["project", "put", 'spoor', 'vondstnr', 'inhoud', 'omstandigheden', 'vullingnr']


    show_fieldsets = [
        ("Projectvelden", {"fields": ["project", "put", "vlaknr", "spoor", "vondstnr"]}),
        ("inhoudvelden", {"fields": ["opmerkingen", "omstandigheden", "segment", "vaknummer"]}),
        ("Datering", {"fields": ["dateringvanaf", "dateringtot", "datering"]}),
        flds_migratie_info]
    edit_fieldsets = show_fieldsets
    add_fieldsets = show_fieldsets
    related_views = [ArchArtefactView]




class ArchVullingView(WSModelView):
    datamodel = SQLAInterface(Vulling)
    # base_permissions = ['can_add', 'can_show']
    related_views = []
    list_title = "Vullingen"
    list_columns = ["project", "put", 'vlaknr', 'spoor', "vullingnr"]
    show_fieldsets = [
        ("Hoofdvelden", {"fields": list_columns + ["opmerkingen"]}),
        ("Vullingvelden", {"fields": ["bioturbatie", "textuur", "mediaan", "textuurbijmenging", "sublaag", "kleur", "reductie", "gevlekt", "laaginterpretatie", "schelpenresten", "grondsoort"]}),
        ("Muurvelden", {"fields": ["lengte_baksteen1", "lengte_baksteen2", "lengte_baksteen3", "hoogte_baksteen1", "hoogte_baksteen2", "hoogte_baksteen3", "breedte_baksteen1", "breedte_baksteen2", "breedte_baksteen3"]}),
        flds_migratie_info
    ]
    edit_fieldsets = show_fieldsets
    add_fieldsets = show_fieldsets

class ArchSpoorView(WSModelView):
    datamodel = SQLAInterface(Spoor)
    related_views = [ArchVullingView, ArchVondstView]
    list_columns = ["project", "put", "vlaknr", "spoornr", 'beschrijving']
    list_title = "Sporen"
    show_fieldsets = [
        ("Hoofdvelden", {"fields": ["project", "put", "vlaknr", "spoornr"]}),
        ("Spoorvelden", {"fields": ["aard", "beschrijving", "vorm", "richting", "gecoupeerd", "coupnrs", "afgewerkt"]}),
        ("Stenen", {"fields": ["steenformaat", "metselverband"]}),
        ("Maten", {"fields": ["hoogte_bovenkant", "breedte_bovenkant", "lengte_bovenkant", "hoogte_onderkant", "breedte_onderkant", "diepte"]}),
        ("Andere sporen", {"fields": ["jonger_dan", "ouder_dan", "sporen_zelfde_periode"]}),
        ("Datering", {"fields": ["dateringvanaf", "dateringtot", "datering"]}),
        flds_migratie_info
    ]
    edit_fieldsets = show_fieldsets
    add_fieldsets = show_fieldsets




class ArchVlakView(WSModelView):
    datamodel = SQLAInterface(Vlak)
    # base_permissions = ['can_add', 'can_show']
    related_views = [ArchSpoorView, ArchVondstView, ArchArtefactView]
    list_title = "Vlakken"
    list_columns = ["project", "put", 'vlaknr', 'beschrijving']
    show_fieldsets = [
        ("Hoofdvelden", {"fields": list_columns}),
        ("Vlakvelden", {"fields": ["datum_aanleg", "vlaktype"]}),
        flds_migratie_info
    ]
    edit_fieldsets = show_fieldsets
    add_fieldsets = show_fieldsets

class ArchPutView(WSModelView):
    datamodel = SQLAInterface(Put)
    # base_permissions = ['can_add', 'can_show']
    related_views = [ArchVlakView, ArchSpoorView, ArchVondstView, ArchArtefactView]
    list_title = "Putten"
    list_columns = ["project", "putnr", 'beschrijving']
    show_fieldsets = [
        ("Hoofdvelden", {"fields": ["project", "putnr", "beschrijving"]}),
        ("Putvelden", {"fields": ["beschrijving", "aangelegd", "datum_ingevoerd", "datum_gewijzigd"]}),
        flds_migratie_info
    ]
    edit_fieldsets = show_fieldsets
    add_fieldsets = show_fieldsets




class ArchProjectView(WSGeoModelView):
    datamodel = GeoSQLAInterface(Project)
    # base_permissions = ['can_add', 'can_show']
    list_columns = ["projectcd", "projectnaam", "jaar"]
    #related_views = [ArchPutView, ArchVondstView, ArchArtefactView]
    base_order = ("projectcd", "asc")
    list_title = "Projecten"
    related_views = [ArchArtefactView, ArchDoosView, ArchPutView, ArchSpoorView, ArchVondstView, ArchOpgravingFotoView, ArchSfeerFotoView]
    search_exclude_columns = ["location"] 

    show_fieldsets = [
        ("Projectvelden", {"fields": ["projectcd", "projectnaam", "jaar", "toponiem", "trefwoorden", "location"]}),
        flds_migratie_info
    ]
    edit_fieldsets = show_fieldsets
    add_fieldsets = show_fieldsets


class MasterView(MultipleView):
    #datamodel = SQLAInterface(Artefact)
    views = [ArchArtefactView, ArchNietFotoView]



db.create_all()

appbuilder.add_view(ArchProjectView,"Projecten",icon="fa-dashboard",category="Projecten")
appbuilder.add_view(ArchPutView,"Putten",icon="fa-dashboard",category="Projecten")
appbuilder.add_view(ArchVlakView,"Vlakken",icon="fa-dashboard",category="Projecten")
appbuilder.add_view(ArchVondstView,"Vondsten",icon="fa-dashboard",category="Projecten")
appbuilder.add_view(ArchSpoorView,"Sporen",icon="fa-dashboard",category="Projecten")
appbuilder.add_view(ArchVullingView,"Vullingen",icon="fa-dashboard",category="Projecten")
 
#### Artefacten
appbuilder.add_view(ArchArtefactView,"Alle Artefacten",icon="fa-dashboard",category="Artefacten")
appbuilder.add_view(ArchAardewerkView,"Aardewerk",icon="fa-dashboard",category="Artefacten")
appbuilder.add_view(ArchBouwaardewerkView,"Bouwaardewerk",icon="fa-dashboard",category="Artefacten")
appbuilder.add_view(ArchKleipijpView,"Kleipijp",icon="fa-dashboard",category="Artefacten")
appbuilder.add_view(ArchLeerView,"Leer",icon="fa-dashboard",category="Artefacten")
appbuilder.add_view(ArchDierlijk_BotView,"Dierlijk Bot",icon="fa-dashboard",category="Artefacten")
appbuilder.add_view(ArchMenselijk_BotView,"Menselijk Bot",icon="fa-dashboard",category="Artefacten")
appbuilder.add_view(ArchMetaalView,"Metaal",icon="fa-dashboard",category="Artefacten")
appbuilder.add_view(ArchMuntView,"Munt",icon="fa-dashboard",category="Artefacten")
appbuilder.add_view(ArchSchelpView,"Schelp",icon="fa-dashboard",category="Artefacten")
appbuilder.add_view(ArchSteenlView,"Steen",icon="fa-dashboard",category="Artefacten")
appbuilder.add_view(ArchTextielView,"Textiel",icon="fa-dashboard",category="Artefacten")
appbuilder.add_view(ArchGlasView,"Glas",icon="fa-dashboard",category="Artefacten")
appbuilder.add_view(ArchHoutView,"Hout",icon="fa-dashboard",category="Artefacten")


#### Depot
appbuilder.add_view(ArchDoosView, "Dozen", icon="fa-dashboard",category="Depot",)
appbuilder.add_view(ArchStellingView,"Stellingen",icon="fa-dashboard",category="Depot",)
appbuilder.add_view(ArchFotoView,"Alle Foto's",icon="fa-dashboard",category="Media",)
appbuilder.add_view(ArchArtefactFotoView,"Artefactfoto's",icon="fa-dashboard",category="Media")
appbuilder.add_view(ArchOpgravingFotoView,"Opgravingsfoto's",icon="fa-dashboard",category="Media")
appbuilder.add_view(ArchSfeerFotoView,"Sfeerfoto's",icon="fa-dashboard",category="Media")
appbuilder.add_view(ArchNietFotoView,"Foto's zonder duiding",icon="fa-dashboard",category="Media")
appbuilder.add_view(MasterView,"Mappen Foto's",icon="fa-dashboard",category="Media")

appbuilder.add_view(ArtefactChartView,"Telling Artefacten",icon="fa-dashboard",category="Statistieken")
appbuilder.add_view(ArtefactLineChartView,"Datering Artefacten",icon="fa-dashboard",category="Statistieken")
