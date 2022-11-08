from flask_appbuilder import ModelRestApi
from flask_appbuilder.api import BaseApi, expose, rison
from flask import make_response
from flask_appbuilder.security.decorators import protect, has_access
from caching import cache

from app import db, appbuilder
from models import ABR, Project, Vondst, Spoor, Put, Doos, Vlak


def outputABR(row):
    return str(row.concept).capitalize() + f" ({row.code})" if row.code else ""

class ABRMaterialenApi(BaseApi):
    resource_name = "abrmaterialen"

    @expose('/hoofdmateriaal')
    @rison()
    @has_access
    @cache.cached()
    def getabr(self, **kwargs):
        result = db.session.query(ABR).filter_by(parentID='31').all()
        return make_response([{"id": row.primary_key, "text": outputABR(row)} for row in result], 200)

@cache.memoize()        
def queryabr(parentid):
    topq = db.session.query(ABR)
    topq = topq.filter(ABR.primary_key == parentid)
    topq = topq.cte('cte', recursive=True)

    bottomq = db.session.query(ABR)
    bottomq = bottomq.join(topq, ABR.parentID == topq.c.primary_key)

    recursive_q = topq.union(bottomq)
    return make_response([{"id": row.primary_key, "text": outputABR(row)} for row in db.session.query(recursive_q)], 200)


class ABRSubmaterialenApi(BaseApi):
    resource_name = "abrmaterialen"

    @expose('/submateriaal')
    @rison()
    @has_access
    def getabr(self, **kwargs):
        if 'parentid' in kwargs['rison']:
            parentid = int(kwargs['rison']['parentid'])
            return queryabr(parentid)
            
        return self.response_400(message="Please put parentid")

appbuilder.add_api(ABRMaterialenApi)
appbuilder.add_api(ABRSubmaterialenApi)


class ProjectenApi(BaseApi):
    resource_name = "projecten"

    @expose('/')
    @rison()
    @has_access
    @cache.cached()
    def getprojecten(self, **kwargs):
        result = db.session.query(Project).order_by(Project.projectcd.asc())
        return make_response([{"id": row.primary_key, "text": Project.getDescription(row)} for row in result], 200)

appbuilder.add_api(ProjectenApi)


class PutApi(BaseApi):
    resource_name = "putten"

    @expose('/')
    @rison()
    @has_access
    def getPutten(self, **kwargs):
        if 'projectid' in kwargs['rison']:
            projectid = int(kwargs['rison']['projectid'])
            result = db.session.query(Put).filter(Put.projectID == projectid).order_by(Put.primary_key.asc())
            return make_response([{"id": row.primary_key, "text": Put.getDescription(row)} for row in result], 200)
            
        return self.response_400(message="Please put projectid")

appbuilder.add_api(PutApi)


class SpoorApi(BaseApi):
    resource_name = "sporen"

    @expose('/')
    @rison()
    @has_access
    def getSporen(self, **kwargs):
        if 'projectid' in kwargs['rison']:
            projectid = int(kwargs['rison']['projectid'])
            result = db.session.query(Spoor).filter(Spoor.projectID == projectid).order_by(Spoor.putID.asc(), Spoor.spoornr.asc())
            return make_response([{"id": row.primary_key, "text": Spoor.getDescription(row)} for row in result], 200)
            
        return self.response_400(message="Please put projectid")

appbuilder.add_api(SpoorApi)


class VondstApi(BaseApi):
    resource_name = "vondsten"

    @expose('/')
    @rison()
    @has_access
    def getVondsten(self, **kwargs):
        if 'projectid' in kwargs['rison']:
            projectid = int(kwargs['rison']['projectid'])
            result = db.session.query(Vondst).filter(Vondst.projectID == projectid).order_by(Vondst.vondstnr.asc())
            return make_response([{"id": row.primary_key, "text": Vondst.getDescription(row)} for row in result], 200)
            
        return self.response_400(message="Please put projectid")

appbuilder.add_api(VondstApi)

class DoosApi(BaseApi):
    resource_name = "dozen"

    @expose('/')
    @rison()
    @has_access
    def getDozen(self, **kwargs):
        if 'projectid' in kwargs['rison']:
            projectid = int(kwargs['rison']['projectid'])
            result = db.session.query(Doos).filter(Doos.projectID == projectid).order_by(Doos.doosnr.asc())
            return make_response([{"id": row.primary_key, "text": Doos.getDescription(row)} for row in result], 200)
            
        return self.response_400(message="Please put projectid")

appbuilder.add_api(DoosApi)

