from flask_appbuilder.models.sqla.interface import SQLAInterface
from fab_addon_geoalchemy.models import GeoSQLAInterface
from typing import Optional, Type
from flask_appbuilder.models.sqla import Model

import logging
logger = logging.getLogger()

class WSSQLAInterface(SQLAInterface):

    def get_related_fk(self, model: Type[Model]) -> Optional[str]:
        for col_name in self.list_properties.keys():
            if self.is_relation(col_name):
                if issubclass(model, self.get_related_model(col_name)):
                    return col_name
        return None


class WSGeoSQLAInterface(GeoSQLAInterface):

    def get_related_fk(self, model: Type[Model]) -> Optional[str]:
        for col_name in self.list_properties.keys():
            if self.is_relation(col_name):
                if issubclass(model, self.get_related_model(col_name)):
                    return col_name
        return None
