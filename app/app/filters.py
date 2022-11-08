
from flask_appbuilder.models.filters import BaseFilter
from app import appbuilder, db
from models import ABR


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