
from flask_appbuilder.models.sqla.filters import BaseFilter, SQLAFilterConverter, __all__
from sqlalchemy import Column, Integer, String, Text, ForeignKey, Float
from sqlalchemy.orm import relationship, Session, declarative_base
from sqlalchemy.sql import column, text
from sqlalchemy import select, func
from sqlalchemy.sql.expression import literal
from flask_babel import lazy_gettext
from app import appbuilder, db
from models import ABR, Bestand
from search import query_index
import shared.const as const
import logging

logger = logging.getLogger()


__all__ = [
    #"SQLAFilterConverter",
    "WSFilterConverter",
    "FilterEqual",
    "FilterNotStartsWith",
    "FilterStartsWith",
    "FilterContains",
    "FilterNotEqual",
    "FilterEndsWith",
    "FilterEqualFunction",
    "FilterGreater",
    "FilterNotEndsWith",
    "FilterRelationManyToManyEqual",
    "FilterRelationOneToManyEqual",
    "FilterRelationOneToManyNotEqual",
    "FilterSmaller",
    "FulltextFilter"
]



class FilterBestandIN(BaseFilter):
    name = lazy_gettext("IN")

    def apply(self, query, value):
        #flt = {"%s_%s" % (self.column_name, "in"): value}
        return query.filter(Bestand.bestandsoort.in_(value))


class HierarchicalABRFilter(BaseFilter):
    name = "Hierarchical ABR-Filter"
    arg_name = "opr"

    def apply(self, query, value):

        topq = db.session.query(ABR.primary_key)
        topq = topq.filter(ABR.uri == value)
        topq = topq.cte('cte', recursive=True)

        bottomq = db.session.query(ABR.primary_key)
        bottomq = bottomq.join(topq, ABR.parentID == topq.c.primary_key)

        recursive_q = topq.union(bottomq)
        q = db.session.query(recursive_q)

        return query.filter(ABR.primary_key.in_(q)).order_by(ABR.concept.asc())


class FulltextFilter(BaseFilter):
    name = 'Fulltext Zoeken'
    arg_name = "flt"

    def apply(self, query, value):

        if not hasattr(self.model, 'primary_key'):
            logger.error(f"Cannot apply fulltext filter for model {self.model} does not have fierld primary_key.")
            return query

        if self.column_name == const.FULLTEXT_SEARCH_FIELD: # Serach all fields
            ft_result, aantal_hits = query_index(self.model, value)
        else:
            ft_result, aantal_hits = query_index(self.model, value, fields=[self.column_name])


        # Create subquery that joins elastic results
        subquery = db.session.query(func.json_to_recordset(ft_result).\
                                    table_valued(column("primary_key", Integer), column(const.FULLTEXT_SCORE_FIELD, Float), column(const.FULLTEXT_HIGHLIGHT_FIELD, String)).\
                                    render_derived(name="t", with_types=True)).\
                                    subquery()

        result = query.join(subquery, self.model.primary_key == subquery.c.primary_key)\
                .add_columns(subquery.c[const.FULLTEXT_SCORE_FIELD].label(const.FULLTEXT_SCORE_FIELD))\
                .add_columns(subquery.c[const.FULLTEXT_HIGHLIGHT_FIELD].label(const.FULLTEXT_HIGHLIGHT_FIELD))\
                .order_by(subquery.c[const.FULLTEXT_SCORE_FIELD].desc())
        return result




class WSFilterConverter(SQLAFilterConverter):
    """
        Class to add fulltext filter to text fields.

    """
    conversion_table = SQLAFilterConverter.conversion_table
    conversion_table = dict(conversion_table)
    conversion_table['is_text'] = [FulltextFilter] + conversion_table['is_text']
    conversion_table['is_string'] = [FulltextFilter] + conversion_table['is_string']   
    conversion_table = tuple([(k, v) for k, v in conversion_table.items()])
    