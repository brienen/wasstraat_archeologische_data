from flask import url_for, Markup

from flask_appbuilder import ModelView, RestCRUDView
from flask_appbuilder.baseviews import BaseCRUDView, BaseView
from flask_appbuilder.widgets import ShowWidget, FormWidget, ListWidget
from fab_addon_geoalchemy.views import GeoModelView
from flask_appbuilder.fieldwidgets import Select2AJAXWidget, Select2SlaveAJAXWidget, Select2ManyWidget
from flask_appbuilder.fields import AJAXSelectField


from flask_appbuilder.actions import action
from flask import redirect
from inspect import isclass
import copy




def fotoFormatter(fotos):
    indicators = ""
    slides = ""
    i = 0
    for foto in fotos:
        indicators = indicators + f'<li data-target="#fotoCarousel" data-slide-to="{i}"{ "class=""active""" if i==0 else ""}></li>'
        slides = slides + f'<div class="item{" active" if i==0 else ""}"><img class="d-block w-100" src="/archeomedia{foto.imageMiddleUUID}"></div>'
        i = i+1

    return f'''<div id="fotoCarousel" class="carousel slide" data-ride="carousel" data-interval="false">
                <ol class="carousel-indicators">
                {indicators}
                </ol>
                <div class="carousel-inner">
                {slides}
                </div>
                <!-- Left and right controls -->
                <a class="left carousel-control" href="#fotoCarousel" data-slide="prev">
                <span class="glyphicon glyphicon-chevron-left"></span>
                <span class="sr-only">Vorige</span>
                </a>
                <a class="right carousel-control" href="#fotoCarousel" data-slide="next">
                <span class="glyphicon glyphicon-chevron-right"></span>
                <span class="sr-only">Volgende</span>
                </a>
            </div>'''


# <a href="#" data-toggle="tooltip" title="" data-original-title="Another tooltip">have a</a>
def abrFormatter(abr):
    return f'<a href="#" data-toggle="tooltip" title="{str(abr.note if abr.note else "<Geen beschrijving>")}">{str(abr)}</a>'

formatters_columns = {
    'project': lambda x: Markup(f'<a href="/archprojectview/show/{str(x.primary_key)}">{str(x)}</a>') if x and not type(x) == str else x,
    'put': lambda x: Markup(f'<a href="/archputview/show/{str(x.primary_key)}">{str(x)}</a>') if x and not type(x) == str else x,
    'vondst': lambda x: Markup(f'<a href="/archvondstview/show/{str(x.primary_key)}">{str(x)}</a>') if x and not type(x) == str else x,
    'spoor': lambda x: Markup(f'<a href="/archspoorview/show/{str(x.primary_key)}">{str(x)}</a>') if x and not type(x) == str else x,
    'artefact': lambda x: Markup(f'<a href="/archartefactview/show/{str(x.primary_key)}">{str(x)}</a>') if x and not type(x) == str else x,
    'doos': lambda x: Markup(f'<a href="/archdoosview/show/{str(x.primary_key)}">{str(x)}</a>') if x and not type(x) == str else x,
    'foto': lambda x: Markup(f'<a href="/archfotoview/show/{str(x.primary_key)}">{str(x)}</a>') if x and not type(x) == str else x,
    'stelling': lambda x: Markup(f'<a href="/archstellingview/show/{str(x.primary_key)}">{str(x)}</a>') if x and not type(x) == str else x,
    'monster': lambda x: Markup(f'<a href="/archmonsterview/show/{str(x.primary_key)}">{str(x)}</a>') if x and not type(x) == str else x,
    'abr_materiaal': lambda x: Markup(abrFormatter(x)) if x and not type(x) == str else x,
    'abr_submateriaal': lambda x: Markup(abrFormatter(x)) if x and not type(x) == str else x,
    'abr_extras': lambda x: Markup([abrFormatter(item) for item in x]) if x and not type(x) == str else x,
    'uri': lambda x: Markup(f'<a href="{str(x)}">{str(x)}</a>'),
    'fotos': lambda x: Markup(fotoFormatter(x)) if x else ''
}


def flatten(t):
    return [item for sublist in t for item in sublist]

class ColumnShowWidget(ShowWidget):
    template = 'widgets/column_show.html'

class ColumnFormWidget(FormWidget):
    template = 'widgets/column_form.html'
class MyListWidget(ListWidget):
    template = 'widgets/list.html'


select2_style = "width:400px"
def fieldDefinitionFactory(field, datamodel, validators=[]):
    extra_field_definitions = {
        "abr_materiaal": AJAXSelectField(
            "ABR-materiaal",
            description="Kies materiaal uit ABR-hoofdcategorieën",
            datamodel=datamodel,
            col_name="abr_materiaal",
            validators=validators,
            widget=Select2AJAXWidget(
                endpoint="/api/v1/abrmaterialen/hoofdmateriaal",
                style=select2_style
            ),
        ),
        "abr_extras": AJAXSelectField(
            "ABR-materiaal",
            description="Kies materiaal uit ABR-hoofdcategorieën",
            datamodel=datamodel,
            col_name="abr_extras",
            validators=validators,
            widget=Select2AJAXWidget(
                endpoint="/api/v1/abrmaterialen/hoofdmateriaal",
                style=select2_style
            ),
        ),
        "abr_submateriaal": AJAXSelectField(
            "ABR-submateriaal",
            description="Kies materiaal uit subcategorie van ABR-hoofdcategorie",
            datamodel=datamodel,
            col_name="abr_submateriaal",
            validators=validators,
            widget=Select2SlaveAJAXWidget(
                master_id="abr_materiaal",
                endpoint="/api/v1/abrmaterialen/submateriaal?q=(parentid:{{ID}})",
                style=select2_style
            )),
        "project": AJAXSelectField(
            "Project",
            description="Kies project",
            datamodel=datamodel,
            col_name="project",
            validators=validators,
            widget=Select2AJAXWidget(
                endpoint="/api/v1/projecten",
                style=select2_style
            ),
        ),
        "put": AJAXSelectField(
            "Put",
            description="kies put binnen project",
            datamodel=datamodel,
            col_name="put",
            validators=validators,
            widget=Select2SlaveAJAXWidget(
                master_id="project",
                endpoint="/api/v1/putten?q=(projectid:{{ID}})",
                style=select2_style
            )),
        "vondst": AJAXSelectField(
            "Vondst",
            description="kies vondst binnen project",
            datamodel=datamodel,
            col_name="vondst",
            validators=validators,
            widget=Select2SlaveAJAXWidget(
                master_id="project",
                endpoint="/api/v1/vondsten?q=(projectid:{{ID}})",
                style=select2_style
            )),
        "spoor": AJAXSelectField(
            "Spoor",
            description="kies spoor binnen project",
            datamodel=datamodel,
            col_name="spoor",
            validators=validators,
            widget=Select2SlaveAJAXWidget(
                master_id="project",
                endpoint="/api/v1/sporen?q=(projectid:{{ID}})",
                style=select2_style
            )),
        "doos": AJAXSelectField(
            "doos",
            description="kies doos binnen project",
            datamodel=datamodel,
            col_name="doos",
            validators=validators,
            widget=Select2SlaveAJAXWidget(
                master_id="project",
                endpoint="/api/v1/dozen?q=(projectid:{{ID}})",
                style=select2_style
            )),
        }
    defintion = copy.copy(extra_field_definitions[field])
    return defintion 


class Select2Many400Widget(Select2ManyWidget):

    def __call__(self, field, **kwargs):
        kwargs['style'] = select2_style
        return super(Select2Many400Widget, self).__call__(field, **kwargs)


class WSModelView(ModelView):
    formatters_columns = formatters_columns

    show_widget = ColumnShowWidget
    edit_widget = ColumnFormWidget
    add_widget = ColumnFormWidget
    list_widget = MyListWidget

    @action("0muldelete", "Verwijderen", "Echt alle geselecteerde verwijderen?", "fa-rocket")
    def muldelete(self, items):
        if isinstance(items, list):
            self.datamodel.delete_all(items)
            self.update_redirect()
        else:
            self.datamodel.delete(items)
        return redirect(self.get_redirect())


    def _init_properties(self):
        """
            Init Properties with extension to be able to show columns

            Extended to allow for multiple grids of columns to be shown. 
        """
        super(BaseCRUDView, self)._init_properties()

        # Reset init props
        self.related_views = self.related_views or []
        self._related_views = self._related_views or []
        self.description_columns = self.description_columns or {}
        self.validators_columns = self.validators_columns or {}
        self.formatters_columns = self.formatters_columns or {}
        self.add_form_extra_fields = self.add_form_extra_fields or {}
        self.edit_form_extra_fields = self.edit_form_extra_fields or {}
        self.show_exclude_columns = self.show_exclude_columns or []
        self.add_exclude_columns = self.add_exclude_columns or []
        self.edit_exclude_columns = self.edit_exclude_columns or []
        # Generate base props
        list_cols = self.datamodel.get_user_columns_list()
        self.list_columns = self.list_columns or [list_cols[0]]
        self._gen_labels_columns(self.list_columns)
        self.order_columns = (
            self.order_columns
            or self.datamodel.get_order_columns_list(list_columns=self.list_columns)
        )
        if self.show_fieldsets:
            self.show_columns = []
            lst_of_lsts = [fieldset_item[1].get("fields") if fieldset_item[1].get("fields") else flatten([col_item.get("fields") for col_item in fieldset_item[1].get("columns")]) for fieldset_item in self.show_fieldsets]
            self.show_columns = self.show_columns + flatten(lst_of_lsts)
        else:
            if not self.show_columns:
                self.show_columns = [
                    x for x in list_cols if x not in self.show_exclude_columns
                ]
        if self.add_fieldsets:
            self.add_columns = []
            lst_of_lsts = [fieldset_item[1].get("fields") if fieldset_item[1].get("fields") else flatten([col_item.get("fields") for col_item in fieldset_item[1].get("columns")]) for fieldset_item in self.add_fieldsets]
            self.add_columns = self.add_columns + flatten(lst_of_lsts)
        else:
            if not self.add_columns:
                self.add_columns = [
                    x for x in list_cols if x not in self.add_exclude_columns
                ]
        if self.edit_fieldsets:
            self.edit_columns = []
            lst_of_lsts = [fieldset_item[1].get("fields") if fieldset_item[1].get("fields") else flatten([col_item.get("fields") for col_item in fieldset_item[1].get("columns")]) for fieldset_item in self.edit_fieldsets]
            self.edit_columns = self.edit_columns + flatten(lst_of_lsts)
        else:
            if not self.edit_columns:
                self.edit_columns = [
                    x for x in list_cols if x not in self.edit_exclude_columns
                ]

        api_lst = ['project', 'put', 'vondst', 'spoor', 'doos']
        if 'project' in self.edit_columns:
            for mytype in [x for x in self.edit_columns if x in api_lst]:
                self.edit_form_extra_fields.update({
                    mytype: fieldDefinitionFactory(mytype, self.datamodel),
                })
        if 'project' in self.add_columns:
            for mytype in [x for x in self.add_columns if x in api_lst]:
                self.add_form_extra_fields.update({
                    mytype: fieldDefinitionFactory(mytype, self.datamodel),
                })
             


class WSGeoModelView(GeoModelView):
    formatters_columns = formatters_columns

    show_widget = ColumnShowWidget
    edit_widget = ColumnFormWidget
    add_widget = ColumnFormWidget

    _init_properties = WSModelView._init_properties

    @action("muldelete", "Verwijderen", "Echt alle geselecteerde verwijderen?", "fa-rocket")
    def muldelete(self, items):
        if isinstance(items, list):
            self.datamodel.delete_all(items)
            self.update_redirect()
        else:
            self.datamodel.delete(items)
        return redirect(self.get_redirect())






