from flask import request
from flask_appbuilder.api import BaseApi, expose, rison, safe
from flask_appbuilder.security.decorators import protect

from . import appbuilder

import pandas as pd
import numpy as np
from sqlalchemy import inspect, create_engine, func

from flask_appbuilder import BaseView, expose, has_access

import logging
logger = logging.getLogger()


greeting_schema = {"type": "object", "properties": {"name": {"type": "string"}}}


class ExampleApi(BaseApi):

    resource_name = "example"
    apispec_parameter_schemas = {"greeting_schema": greeting_schema}

    @expose("/greeting")
    def greeting(self):
        return greeting_schema




appbuilder.add_api(ExampleApi)
