from flask import request
from flask_appbuilder.api import BaseApi, expose, rison, safe
from flask_appbuilder.security.decorators import protect

from . import appbuilder

from app.models import Project, Artefact
import config
import pandas as pd
import geopandas
import numpy as np
import json
import requests

from sqlalchemy.orm import sessionmaker
from sqlalchemy.engine import reflection
from sqlalchemy import inspect, create_engine, func

from flask_appbuilder import IndexView
from flask_appbuilder import BaseView, expose, has_access
import folium
from vega_datasets import data
from altair import Chart, X, Y, Axis, Data, DataFormat
import vincent

import logging
logger = logging.getLogger()


greeting_schema = {"type": "object", "properties": {"name": {"type": "string"}}}


class ExampleApi(BaseApi):

    resource_name = "example"
    apispec_parameter_schemas = {"greeting_schema": greeting_schema}

    @expose("/greeting")
    def greeting(self):
        cars = data.cars()
        chart = Chart(
            data=cars, height=700, width=700).mark_point().encode(
                x='Horsepower',
                y='Miles_per_Gallon',
                color='Origin',
            ).interactive()
        return chart.to_json()
        #return self.response(200, message="Hello")

    #@expose("/data/cars.json", methods=["GET"])
    #@has_access    
    #def cars_demo(this):

    #    cars = data.cars()
    #    chart = Chart(
    #        data=cars, height=700, width=700).mark_point().encode(
    #            x='Horsepower',
    #            y='Miles_per_Gallon',
    #            color='Origin',
    #        ).interactive()


    #    scatter_points = {
    #        'x': np.random.uniform(size=(100,)),
    #        'y': np.random.uniform(size=(100,)),
    #    }

        # Let's create the vincent chart.
    #    scatter_chart = vincent.Scatter(scatter_points,
    #                                    iter_idx='x',
    #                                    width=600,
    #                                    height=300)
    #    return scatter_chart.to_json()




appbuilder.add_api(ExampleApi)
