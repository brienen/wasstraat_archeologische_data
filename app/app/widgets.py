from flask_appbuilder.widgets import ListWidget, FormWidget, ShowWidget
from flask_appbuilder._compat import as_unicode
from filters import FulltextFilter
import shared.const as const


class ColumnShowWidget(ShowWidget):
    template = 'widgets/column_show.html'

class ColumnFormWidget(FormWidget):
    template = 'widgets/column_form.html'
class MyListWidget(ListWidget):
    template = 'widgets/list.html'

class MediaListWidget(ListWidget):
    template = 'widgets/medialist.html'


class SearchWidget(FormWidget):
    template = "widgets/search.html"
    filters = None

    def __init__(self, **kwargs):
        self.filters = kwargs.get("filters")
        return super(SearchWidget, self).__init__(**kwargs)

    def __call__(self, **kwargs):
        """ create dict labels based on form """
        """ create dict of form widgets """
        """ create dict of possible filters """
        """ create list of active filters """
        label_columns = {}
        form_fields = {}
        search_filters = {}
        dict_filters = self.filters.get_search_filters()

        # The field 'ft_search' is meany only for fulltext search on all fields of a type, remove all other search methods
        if const.FULLTEXT_SEARCH_FIELD in dict_filters.keys():
            dict_filters[const.FULLTEXT_SEARCH_FIELD] = [FulltextFilter]
        for col in self.template_args["include_cols"]:
            label_columns[col] = as_unicode(self.template_args["form"][col].label.text)
            form_fields[col] = self.template_args["form"][col]()
            search_filters[col] = [as_unicode(flt.name) for flt in dict_filters[col]]

        kwargs["label_columns"] = label_columns
        kwargs["form_fields"] = form_fields
        kwargs["search_filters"] = search_filters
        kwargs["active_filters"] = self.filters.get_filters_values_tojson()
        return super(SearchWidget, self).__call__(**kwargs)


