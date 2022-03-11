import calendar
import copy

from flask import url_for, Markup

from flask_appbuilder import GroupByChartView, ModelView, DirectByChartView, MultipleView, MasterDetailView
from flask_appbuilder.models.group import aggregate_count
from flask_appbuilder.models.sqla.interface import SQLAInterface
from flask_appbuilder.widgets import (
    ListBlock, ListItem, ListLinkWidget, ListThumbnail, ShowBlockWidget, ListCarousel, ShowWidget
)
from flask_appbuilder.fieldwidgets import BS3TextFieldWidget
from flask_appbuilder.models.group import aggregate_count, aggregate_sum, aggregate_avg
from flask_appbuilder.models.sqla.filters import FilterEqual, FilterStartsWith
from fab_addon_geoalchemy.views import GeoModelView
from fab_addon_geoalchemy.models import GeoSQLAInterface, Geometry

from wtforms.fields import StringField

from . import appbuilder, db
from .models import Aardewerk, Stelling, Doos, Artefact, Foto, Spoor, Project,Put, Vondst, Vlak, DiscrArtefactsoortEnum, Bot, Glas
from .widgets import MediaListWidget
from .baseviews import WSModelView, WSGeoModelView, ColumnShowWidget, ColumnFormWidget
import app.util as util

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
    show_columns = ["project", "fototype", "artefactnr", "fotonr", "artefact", "fileName", 'directory', 'photo_img', 'photo']
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


class ArchOpgravingFotoView(ArchFotoView):
    base_filters = [['fototype', FilterStartsWith, 'G']]
    list_title = "Opgravingsfoto's"

class ArchSfeerFotoView(ArchFotoView):
    base_filters = [['fototype', FilterStartsWith, 'F']]
    list_title = "Sfeerfoto's"

class ArchArtefactFotoView(ArchFotoView):
    base_filters = [['fototype', FilterStartsWith, 'H']]
    list_title = "Artefactfoto's"

class ArchNietFotoView(ArchFotoView):
    base_filters = [['fototype', FilterStartsWith, 'N']]
    list_title = "Foto's zonder duiding"


class ArchArtefactView(WSModelView):
    datamodel = SQLAInterface(Artefact)
    # base_permissions = ['can_add', 'can_show']
    list_columns = ["project", "artefactnr", "artefactsoort", "typecd", "datering", 'typevoorwerp']
    list_widget = ListThumbnail
    list_title = "Artefacten"
    related_views = [ArchArtefactFotoView]
    show_fieldsets = [
        ("Projectvelden", {"columns": [
            {"fields": ["project", "vondst", "artefactnr", "subnr", "aantal", "ABRcodering", "artefactsoort", "typevoorwerp", "typecd", "functievoorwerp", "versiering", "beschrijving", "opmerkingen", "doos"], "grid":6},        
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

class ArchBotView(ArchArtefactView):
    datamodel = SQLAInterface(Bot)
    base_filters = [['artefactsoort', FilterEqual, DiscrArtefactsoortEnum.Bot.value]]

    list_title = "Bot"
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


'''
    decoratie = Column(String(200), comment="decoratie")
    diameter_bodem = Column(String(200), comment="diameter bodem in millimeters, 0 = niet gemeten")
    diameter_rand = Column(String(200), comment="diameter rand in millimeters, 0 = niet gemeten")
    glassoort = Column(String(200), comment="Soort glas")
    grootste = Column(String(200), comment="grootste diameter in millimeters, 0 = niet gemeten")
    hoogte = Column(String(200), comment="hoogte in millimeters, 0 = niet gemeten")
    kleur = Column(String(200), comment="kleur")
    past_aan = Column(String(200), comment="Past aan")
    past_aan_andere_nummers = Column(String(200), comment="past aan andere nummers:")
    percentage_rand = Column(String(200), comment="Randpercentage")
    vorm_bodem_voet = Column(String(200), comment="vorm van de bodem/voet + eventuele merkjes")
    vorm_versiering_cuppa = Column(String(200), comment="vorm en versiering van cuppa")
    vorm_versiering_oor_stam = Column(String(200), comment="vorm en versiering van oor/stam")

'''

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
    list_columns = ["stelling", "soort", "inhoud"]
    base_order = ("stelling", "asc")
    list_title = "Stellingen"
    related_views = [ArchDoosView]
    show_fieldsets = [
        ("Hoofdvelden", {"fields": ["stelling", "inhoud"]}),
        flds_migratie_info]


class ArchSpoorView(WSModelView):
    datamodel = SQLAInterface(Spoor)
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

class ArchVondstView(WSModelView):
    datamodel = SQLAInterface(Vondst)
    # base_permissions = ['can_add', 'can_show']
    list_title = "Vondsten"
    list_columns = ["project", "put", 'spoor', 'vondstnr', 'inhoud', 'omstandigheden', 'vullingnr']


    show_fieldsets = [
        ("Projectvelden", {"columns": [
            {"fields": ["project", "put", "vlaknr", "spoor", "vondstnr"], 'grid':12},
        ]}),
        ("Projectvelden", {"fields": ["project", "put", "vlaknr", "spoor", "vondstnr"]}),
        ("inhoudvelden", {"fields": ["inhoud", "omstandigheden", "segment", "vaknummer", "verzamelwijze"]}),
        ("Datering", {"fields": ["dateringvanaf", "dateringtot", "datering"]}),
        flds_migratie_info]
    edit_fieldsets = show_fieldsets
    add_fieldsets = show_fieldsets
    related_views = [ArchArtefactView]


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
    list_columns = ["projectcd", "projectnaam", "jaar", "aantalArtefacten"]
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
appbuilder.add_view(
    ArchProjectView,
    "Projecten",
    icon="fa-dashboard",
    category="Projecten",
)
appbuilder.add_view(
    ArchPutView,
    "Putten",
    icon="fa-dashboard",
    category="Projecten",
)
appbuilder.add_view(
    ArchVlakView,
    "Vlakken",
    icon="fa-dashboard",
    category="Projecten",
)
appbuilder.add_view(
    ArchVondstView,
    "Vondsten",
    icon="fa-dashboard",
    category="Projecten",
)
appbuilder.add_view(
    ArchSpoorView,
    "Sporen",
    icon="fa-dashboard",
    category="Projecten",
)
appbuilder.add_view(
    ArchArtefactView,
    "Artefacten",
    icon="fa-dashboard",
    category="Projecten",
)
appbuilder.add_view(
    ArchAardewerkView,
    "Aardewerk",
    icon="fa-dashboard",
    category="Projecten",
)
appbuilder.add_view(
    ArchBotView,
    "Bot",
    icon="fa-dashboard",
    category="Projecten",
)
appbuilder.add_view(
    ArchGlasView,
    "Glas",
    icon="fa-dashboard",
    category="Projecten",
)
appbuilder.add_view(
    ArchDoosView,
    "Dozen",
    icon="fa-dashboard",
    category="Depot",
)
appbuilder.add_view(
    ArchStellingView,
    "Stellingen",
    icon="fa-dashboard",
    category="Depot",
)
appbuilder.add_view(
    ArchFotoView,
    "Alle Foto's",
    icon="fa-dashboard",
    category="Media",
)
appbuilder.add_view(
    ArchArtefactFotoView,
    "Artefactfoto's",
    icon="fa-dashboard",
    category="Media",
)
appbuilder.add_view(
    ArchOpgravingFotoView,
    "Opgravingsfoto's",
    icon="fa-dashboard",
    category="Media",
)
appbuilder.add_view(
    ArchSfeerFotoView,
    "Sfeerfoto's",
    icon="fa-dashboard",
    category="Media",
)
appbuilder.add_view(
    ArchNietFotoView,
    "Foto's zonder duiding",
    icon="fa-dashboard",
    category="Media",
)
appbuilder.add_view(
    MasterView,
    "Mappen Foto's",
    icon="fa-dashboard",
    category="Media",
)

appbuilder.add_view(
    ArtefactChartView,
    "Telling Artefacten",
    icon="fa-dashboard",
    category="Statistieken",
)
appbuilder.add_view(
    ArtefactLineChartView,
    "Datering Artefacten",
    icon="fa-dashboard",
    category="Statistieken",
)
