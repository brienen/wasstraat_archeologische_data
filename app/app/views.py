import calendar

from flask import url_for, Markup

from flask_appbuilder import GroupByChartView, ModelView, DirectByChartView, MultipleView, MasterDetailView
from flask_appbuilder.models.group import aggregate_count
from flask_appbuilder.models.sqla.interface import SQLAInterface
from flask_appbuilder.widgets import (
    ListBlock, ListItem, ListLinkWidget, ListThumbnail, ShowBlockWidget, ListCarousel, ShowWidget
)
from flask_appbuilder.fieldwidgets import BS3TextFieldWidget
from flask_appbuilder.models.group import aggregate_count, aggregate_sum, aggregate_avg
from flask_appbuilder.models.sqla.filters import FilterEqualFunction, FilterStartsWith
from fab_addon_geoalchemy.views import GeoModelView
from fab_addon_geoalchemy.models import GeoSQLAInterface, Geometry

from wtforms.fields import StringField

from . import appbuilder, db
from .models import Stelling, Doos, Artefact, Foto, Spoor, Project,Put, Vondst, Vlak
from .widgets import MediaListWidget
from .baseviews import WSModelView, WSGeoModelView, ColumnShowWidget, ColumnFormWidget


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
            {"fields": ["project", "put", "vondst", "artefactnr", "subnr", "artefactsoort"], "grid":6},        
            {"fields": ["fotos"], "grid":6, "fulldisplay": True},        
        ]}),        
        ("Artefactvelden", {"fields": ["typevoorwerp", "typecd", "functievoorwerp", "origine", "dateringvanaf", "dateringtot", "datering", "conserveren", "exposabel", "literatuur", "gewicht", "maten", "doos"]}),
    flds_migratie_info]
    edit_fieldsets = show_fieldsets
    add_fieldsets = show_fieldsets


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
            {"fields": ["project", "put", "vlaknr", "spoor", "vondstnr"], 'grid':4},
            {"fields": ["project", "put", "vlaknr", "spoor", "vondstnr"], 'grid':4},
            {"fields": ["project", "put", "vlaknr", "spoor", "vondstnr"], 'grid':4},
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
