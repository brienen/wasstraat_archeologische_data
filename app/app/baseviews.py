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
import ast
from widgets import SearchWidget, ColumnFormWidget, ColumnShowWidget, MyListWidget
import shared.const as const


def fotoFormatter(fotos):
    indicators = ""
    slides = ""
    i = 0
    for foto in fotos:
        indicators = indicators + f'<li data-target="#fotoCarousel" data-slide-to="{i}"{ "class=""active""" if i==0 else ""}></li>'
        slides = slides + f'<div class="item{" active" if i==0 else ""}"><img class="d-block w-100" src="/archeomedia{foto.imageMiddleID}"></div>'
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

def highlightFormatter(highlight):
    try:
        dct = ast.literal_eval(dct)
        lst = [item.replace("doc.", "") + ": " + ",".join(dct[item]) for item in dct.keys()]
        return "; ".join(lst)
    except:
        return str(highlight)


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
    'partij': lambda x: Markup(f'<a href="/archpartijview/show/{str(x.primary_key)}">{str(x)}</a>') if x and not type(x) == str else x,
    'abr_materiaal': lambda x: Markup(abrFormatter(x)) if x and not type(x) == str else x,
    'abr_submateriaal': lambda x: Markup(abrFormatter(x)) if x and not type(x) == str else x,
    'abr_extras': lambda x: Markup([abrFormatter(item) for item in x]) if x and not type(x) == str else x,
    'uri': lambda x: Markup(f'<a href="{str(x)}">{str(x)}</a>'),
    'fotos': lambda x: Markup(fotoFormatter(x)) if x else '',
    const.FULLTEXT_HIGHLIGHT_FIELD: lambda x: Markup(highlightFormatter(x)) if x else ''
}


def flatten(t):
    return [item for sublist in t for item in sublist]



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
            description="Kies put binnen project",
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
            description="Kies vondst binnen project",
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
            description="Kies spoor binnen project",
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
            description="Kies doos binnen project",
            datamodel=datamodel,
            col_name="doos",
            validators=validators,
            widget=Select2SlaveAJAXWidget(
                master_id="project",
                endpoint="/api/v1/dozen?q=(projectid:{{ID}})",
                style=select2_style
            )),
        "artefact": AJAXSelectField(
            "artefact",
            description="Kies artefact binnen project",
            datamodel=datamodel,
            col_name="artefact",
            validators=validators,
            widget=Select2SlaveAJAXWidget(
                master_id="project",
                endpoint="/api/v1/artefacten?q=(projectid:{{ID}})",
                style=select2_style
            )),
        #"artefact": AJAXSelectField(
        #    "Artefact",
        #    description="Kies artefact",
        #    datamodel=datamodel,
        #    col_name="artefact",
        #    validators=validators,
        #    widget=Select2AJAXWidget(
        #        endpoint="/api/v1/artefacten",
        #        style=select2_style
        #    )),

        }
    defintion = copy.copy(extra_field_definitions[field])
    return defintion 


class Select2Many400Widget(Select2ManyWidget):

    def __call__(self, field, **kwargs):
        kwargs['style'] = select2_style
        return super(Select2Many400Widget, self).__call__(field, **kwargs)


class WSModelViewMixin(object):
    formatters_columns = formatters_columns

    show_widget = ColumnShowWidget
    edit_widget = ColumnFormWidget
    add_widget = ColumnFormWidget
    list_widget = MyListWidget
    search_widget = SearchWidget
    label_columns = {const.FULLTEXT_SEARCH_FIELD:'Zoeken in alle velden', 
        const.FULLTEXT_SCORE_FIELD:'Score Fulltext', 
        const.FULLTEXT_HIGHLIGHT_FIELD:'Highlight Fulltext'}

    main_search_cols = []

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
        self.search_columns = self.search_columns or []
        if not const.FULLTEXT_SEARCH_FIELD in self.search_columns:
            self.search_columns = self.search_columns + [const.FULLTEXT_SEARCH_FIELD]

        self.main_search_cols = self.main_search_cols if self.main_search_cols and len(self.main_search_cols)>0 else self.list_columns


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

        api_lst = ['project', 'put', 'vondst', 'spoor', 'doos', 'artefact']
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

    def _get_search_widget(self, form=None, exclude_cols=None, widgets=None):
        include_cols = self.search_columns
        migration_cols = [item for item in const.MIGRATION_COLUMNS if item in include_cols] 
        fulltext_search_cols = [item for item in include_cols if item == const.FULLTEXT_SEARCH_FIELD]
        main_search_cols = self.main_search_cols if self.main_search_cols else []
        main_search_cols = [item for item in main_search_cols if item in include_cols]
        exclude_cols = exclude_cols or []
        sub_search_cols = [item for item in include_cols if item not in main_search_cols and item not in exclude_cols and item not in migration_cols and item not in fulltext_search_cols]
        sub_search_cols.sort()

        widgets = widgets or {}
        widgets["search"] = self.search_widget(
            route_base=self.route_base,
            form=form,
            include_cols=include_cols,
            exclude_cols=exclude_cols,
            filters=self._filters,
            main_search_cols = main_search_cols,
            sub_search_cols = sub_search_cols,
            migration_cols = migration_cols,
            fulltext_search_cols = fulltext_search_cols        
            )
        return widgets


    def _get_list_widget(
        self,
        filters,
        actions=None,
        order_column="",
        order_direction="",
        page=None,
        page_size=None,
        widgets=None,
        **args,
    ):

        """ get joined base filter and current active filter for query """
        widgets = widgets or {}
        actions = actions or self.actions
        page_size = page_size or self.page_size
        if not order_column and self.base_order:
            order_column, order_direction = self.base_order
        joined_filters = filters.get_joined_filters(self._base_filters)
        count, lst = self.datamodel.query(
            joined_filters,
            order_column,
            order_direction,
            page=page,
            page_size=page_size,
        )
        pks = self.datamodel.get_keys(lst)

        # serialize composite pks
        pks = [self._serialize_pk_if_composite(pk) for pk in pks]

        list_columns=self.list_columns
        if count > 0 and hasattr(lst[0], const.FULLTEXT_SCORE_FIELD) and getattr(lst[0], const.FULLTEXT_SCORE_FIELD) > -1:
            list_columns = list_columns + [const.FULLTEXT_SCORE_FIELD]
            if hasattr(lst[0], const.FULLTEXT_HIGHLIGHT_FIELD):
                list_columns = list_columns + [const.FULLTEXT_HIGHLIGHT_FIELD]


        widgets["list"] = self.list_widget(
            label_columns=self.label_columns,
            include_columns=list_columns,
            value_columns=self.datamodel.get_values(lst, list_columns),
            order_columns=self.order_columns,
            formatters_columns=self.formatters_columns,
            page=page,
            page_size=page_size,
            count=count,
            pks=pks,
            actions=actions,
            filters=filters,
            modelview_name=self.__class__.__name__,
        )
        return widgets




class WSModelView(WSModelViewMixin, ModelView):
    formatters_columns = formatters_columns

class WSGeoModelView(WSModelViewMixin, GeoModelView):
    formatters_columns = formatters_columns





