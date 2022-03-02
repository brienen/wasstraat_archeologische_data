from flask import url_for, Markup

from flask_appbuilder import ModelView, RestCRUDView
from flask_appbuilder.baseviews import BaseCRUDView
from flask_appbuilder.widgets import ShowWidget, FormWidget
from fab_addon_geoalchemy.views import GeoModelView



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

def flatten(t):
    return [item for sublist in t for item in sublist]

class WSGeoModelView(GeoModelView):
    formatters_columns = formatters_columns

class ColumnShowWidget(ShowWidget):
    template = 'widgets/column_show.html'

class ColumnFormWidget(FormWidget):
    template = 'widgets/column_form.html'


class WSModelView(ModelView):
    formatters_columns = formatters_columns

    show_widget = ColumnShowWidget
    edit_widget = ColumnFormWidget
    add_widget = ColumnFormWidget


    def _init_properties(self):
        """
            Init Properties with extension to be able to show columns
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


