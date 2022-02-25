import calendar

from flask import url_for, Markup

from flask_appbuilder import GroupByChartView, ModelView, DirectByChartView, MultipleView, MasterDetailView
from flask_appbuilder.models.group import aggregate_count
from flask_appbuilder.models.sqla.interface import SQLAInterface
from flask_appbuilder.widgets import (
    ListBlock, ListItem, ListLinkWidget, ListThumbnail, ShowBlockWidget, ListCarousel
)
from flask_appbuilder.fieldwidgets import BS3TextFieldWidget
from flask_appbuilder.models.group import aggregate_count, aggregate_sum, aggregate_avg
from flask_appbuilder.models.sqla.filters import FilterEqualFunction, FilterStartsWith
from fab_addon_geoalchemy.views import GeoModelView
from fab_addon_geoalchemy.models import GeoSQLAInterface, Geometry

from wtforms.fields import StringField

from . import appbuilder, db
from .models import Stelling, Doos, Artefact, Foto, Spoor, Project, Contact, ContactGroup, Gender, Put, Vondst, Vlak
from .widgets import MediaListWidget


formatters_columns = {
    'project': lambda x: Markup(f'<a href="/archprojectview/show/{str(x.primary_key)}">{str(x)}</a>') if x and not type(x) == str else '',
    'put': lambda x: Markup(f'<a href="/archputview/show/{str(x.primary_key)}">{str(x)}</a>') if x and not type(x) == str else '',
    'vondst': lambda x: Markup(f'<a href="/archvondstview/show/{str(x.primary_key)}">{str(x)}</a>') if x and not type(x) == str else '',
    'spoor': lambda x: Markup(f'<a href="/archspoorview/show/{str(x.primary_key)}">{str(x)}</a>') if x and not type(x) == str else '',
    'artefact': lambda x: Markup(f'<a href="/archartefactview/show/{str(x.primary_key)}">{str(x)}</a>') if x and not type(x) == str else '',
    'doos': lambda x: Markup(f'<a href="/archdoosview/show/{str(x.primary_key)}">{str(x)}</a>') if x and not type(x) == str else '',
    'foto': lambda x: Markup(f'<a href="/archfotoview/show/{str(x.primary_key)}">{str(x)}</a>') if x and not type(x) == str else '',
    'stelling': lambda x: Markup(f'<a href="/archstellingview/show/{str(x.primary_key)}">{str(x)}</a>') if x and not type(x) == str else ''
}


flds_migratie_info = ("Migratie-informatie", {"fields": ["soort","brondata","herkomst"],"expanded": False})

class MyModelView(ModelView):
    formatters_columns = formatters_columns

class MyGeoModelView(GeoModelView):
    formatters_columns = formatters_columns


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


class ArchFotoView(MyModelView):
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


class ArchArtefactView(MyModelView):
    datamodel = SQLAInterface(Artefact)
    # base_permissions = ['can_add', 'can_show']
    list_columns = ["project", "artefactnr", "artefactsoort", "typecd", "datering", 'typevoorwerp']
    list_widget = ListThumbnail
    list_title = "Artefacten"
    related_views = [ArchArtefactFotoView]

    show_fieldsets = [
        ("Projectvelden", {"fields": ["project", "put", "vondst", "artefactnr", "subnr", "artefactsoort"]}),
        ("Artefactvelden", {"fields": ["typevoorwerp", "typecd", "functievoorwerp", "origine", "dateringvanaf", "dateringtot", "datering", "conserveren", "exposabel", "literatuur", "gewicht", "maten", "doos"]}),
    flds_migratie_info]
    edit_fieldsets = show_fieldsets
    add_fieldsets = show_fieldsets


class ArchDoosView(MyModelView):
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

class ArchStellingView(MyModelView):
    datamodel = SQLAInterface(Stelling)
    # base_permissions = ['can_add', 'can_show']
    list_columns = ["stelling", "soort", "inhoud"]
    base_order = ("stelling", "asc")
    list_title = "Stellingen"
    related_views = [ArchDoosView]
    show_fieldsets = [
        ("Hoofdvelden", {"fields": ["stelling", "inhoud"]}),
        flds_migratie_info]


class ArchSpoorView(MyModelView):
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

class ArchVondstView(MyModelView):
    datamodel = SQLAInterface(Vondst)
    # base_permissions = ['can_add', 'can_show']
    list_title = "Vondsten"
    list_columns = ["project", "put", 'spoor', 'vondstnr', 'inhoud', 'omstandigheden', 'vullingnr']
    show_fieldsets = [
        ("Projectvelden", {"fields": ["project", "put", "vlaknr", "spoor", "vondstnr"]}),
        ("inhoudvelden", {"fields": ["inhoud", "omstandigheden", "segment", "vaknummer", "verzamelwijze"]}),
        ("Datering", {"fields": ["dateringvanaf", "dateringtot", "datering"]}),
        flds_migratie_info]
    edit_fieldsets = show_fieldsets
    add_fieldsets = show_fieldsets
    related_views = [ArchArtefactView]


class ArchVlakView(MyModelView):
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



class ArchPutView(MyModelView):
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




class ArchProjectView(MyGeoModelView):
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








def fill_gender():
    try:
        db.session.add(Gender(name="Male"))
        db.session.add(Gender(name="Female"))
        db.session.commit()
    except Exception:
        db.session.rollback()


class ContactModelView(ModelView):
    datamodel = SQLAInterface(Contact)

    list_columns = ["name", "personal_celphone", "birthday", "contact_group.name"]

    base_order = ("name", "asc")

    show_fieldsets = [
        ("Summary", {"fields": ["name", "gender", "contact_group"]}),
        (
            "Personal Info",
            {
                "fields": [
                    "address",
                    "birthday",
                    "personal_phone",
                    "personal_celphone",
                ],
                "expanded": False,
            },
        ),
    ]

    add_fieldsets = [
        ("Summary", {"fields": ["name", "gender", "contact_group"]}),
        (
            "Personal Info",
            {
                "fields": [
                    "address",
                    "birthday",
                    "personal_phone",
                    "personal_celphone",
                ],
                "expanded": False,
            },
        ),
    ]

    edit_fieldsets = [
        ("Summary", {"fields": ["name", "gender", "contact_group"]}),
        (
            "Personal Info",
            {
                "fields": [
                    "address",
                    "birthday",
                    "personal_phone",
                    "personal_celphone",
                ],
                "expanded": False,
            },
        ),
    ]


class ContactItemModelView(ContactModelView):
    list_title = "List Contact (Items)"
    list_widget = ListItem


class ContactThumbnailModelView(ContactModelView):
    list_title = "List Contact (Thumbnails)"
    list_widget = ListThumbnail


class ContactBlockModelView(ContactModelView):
    list_title = "List Contact (Blocks)"
    list_widget = ListBlock
    show_widget = ShowBlockWidget


class ContactLinkModelView(ContactModelView):
    list_title = "List Contact (Links)"
    list_widget = ListLinkWidget


class GroupModelView(ModelView):
    datamodel = SQLAInterface(ContactGroup)
    related_views = [
        ContactModelView,
        ContactItemModelView,
        ContactThumbnailModelView,
        ContactBlockModelView,
    ]


class ContactChartView(GroupByChartView):
    datamodel = SQLAInterface(Contact)
    chart_title = "Grouped contacts"
    label_columns = ContactModelView.label_columns
    chart_type = "PieChart"

    definitions = [
        {"group": "contact_group", "series": [(aggregate_count, "contact_group")]},
        {"group": "gender", "series": [(aggregate_count, "contact_group")]},
    ]


def pretty_month_year(value):
    return calendar.month_name[value.month] + " " + str(value.year)


def pretty_year(value):
    return str(value.year)


class ContactTimeChartView(GroupByChartView):
    datamodel = SQLAInterface(Contact)

    chart_title = "Grouped Birth contacts"
    chart_type = "AreaChart"
    label_columns = ContactModelView.label_columns
    definitions = [
        {
            "group": "month_year",
            "formatter": pretty_month_year,
            "series": [(aggregate_count, "group")],
        },
        {
            "group": "year",
            "formatter": pretty_year,
            "series": [(aggregate_count, "group")],
        },
    ]


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
