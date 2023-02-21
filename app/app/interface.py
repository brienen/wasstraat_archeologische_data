from flask_appbuilder.models.sqla.interface import SQLAInterface
from fab_addon_geoalchemy.models import GeoSQLAInterface
from typing import Any, Dict, List, Optional, Tuple, Type, Union
from flask_appbuilder.models.sqla import Model
from flask_appbuilder.models.filters import Filters
from flask_appbuilder.exceptions import InterfaceQueryWithoutSession
from sqlalchemy import select, func
from filters import WSFilterConverter
import shared.const as const
import search
from sqlalchemy.dialects import postgresql

import logging
logger = logging.getLogger()



class WSSQLAInterfaceMixin(object):

    filter_converter_class = WSFilterConverter

    def query(
        self,
        filters: Optional[Filters] = None,
        order_column: str = "",
        order_direction: str = "",
        page: Optional[int] = None,
        page_size: Optional[int] = None,
        select_columns: Optional[List[str]] = None,
    ) -> Tuple[int, List[Model]]:
        """
        Returns the results for a model query, applies filters, sorting and pagination

        :param filters: A Filter class that contains all filters to apply
        :param order_column: name of the column to order
        :param order_direction: the direction to order <'asc'|'desc'>
        :param page: the current page
        :param page_size: the current page size
        :param select_columns: A List of columns to be specifically selected
        on the query. Supports dotted notation.
        :return: A tuple with the query count (non paginated) and the results
        """
        if not self.session:
            raise InterfaceQueryWithoutSession()
        query = self.session.query(self.obj)

        count = self.query_count(query, filters, select_columns)
        query = self.apply_all(
            query,
            filters,
            order_column,
            order_direction,
            page,
            page_size,
            select_columns,
        )
        query_results = query.all()

        result = list()
        for item in query_results:
            if hasattr(item, self.obj.__name__):
                tobj = getattr(item, self.obj.__name__)
                if hasattr(item, const.FULLTEXT_SCORE_FIELD) and hasattr(tobj, const.FULLTEXT_SCORE_FIELD):
                    setattr(tobj, const.FULLTEXT_SCORE_FIELD, getattr(item, const.FULLTEXT_SCORE_FIELD))
                if hasattr(item, const.FULLTEXT_HIGHLIGHT_FIELD) and hasattr(tobj, const.FULLTEXT_HIGHLIGHT_FIELD):
                    setattr(tobj, const.FULLTEXT_HIGHLIGHT_FIELD, getattr(item, const.FULLTEXT_HIGHLIGHT_FIELD))
                result.append(tobj)
            else:
                return count, query_results

        return count, result




    def get_related_fk(self, model: Type[Model]) -> Optional[str]:
        for col_name in self.list_properties.keys():
            if self.is_relation(col_name):
                if issubclass(model, self.get_related_model(col_name)):
                    return col_name
        return None


    def add(self, item: Model, raise_exception: bool = False) -> bool:
        result = super(WSSQLAInterfaceMixin, self).add(item)
        if result: search.add_to_index(item)
        return result


    def edit(self, item: Model, raise_exception: bool = False) -> bool:
        result = super(WSSQLAInterfaceMixin, self).edit(item)
        if result: search.add_to_index(item)
        return result

    def delete(self, item: Model, raise_exception: bool = False) -> bool:
        result = super(WSSQLAInterfaceMixin, self).delete(item)
        if result: search.remove_from_index(item)
        return result




class WSSQLAInterface(WSSQLAInterfaceMixin, SQLAInterface):

    filter_converter_class = WSFilterConverter

class WSGeoSQLAInterface(WSSQLAInterfaceMixin, GeoSQLAInterface):
    
    filter_converter_class = WSFilterConverter    
