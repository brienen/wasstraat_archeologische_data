from datetime import datetime as dt

import pandas_datareader as pdr

from dash.dependencies import Input
from dash.dependencies import Output
import dash_core_components as dcc
import dash_html_components as html

# Import required libraries
import pickle
import datetime
import copy
import pathlib
import dash
import math
import datetime as dt
import pandas as pd
from dash.dependencies import Input, Output, State, ClientsideFunction
import dash_core_components as dcc
import dash_html_components as html
import dash_bootstrap_components as dbc


# Multi-dropdown options
from app.cockpit.controls import COUNTIES, WELL_STATUSES, WELL_TYPES, WELL_COLORS

#external_stylesheets = ['/static/css/s1.css','/static/css/style.css']
external_stylesheets = [dbc.themes.BOOTSTRAP, '/static/css/s1.css','/static/css/style.css']
external_scripts = ['/static/js/resizing_script.js', '/static/js/draggable.js']


# Create controls
county_options = [
    {"label": str(COUNTIES[county]), "value": str(county)} for county in COUNTIES
]

well_status_options = [
    {"label": str(WELL_STATUSES[well_status]), "value": str(well_status)}
    for well_status in WELL_STATUSES
]

well_type_options = [
    {"label": str(WELL_TYPES[well_type]), "value": str(well_type)}
    for well_type in WELL_TYPES
]




us_cities = pd.read_csv("https://raw.githubusercontent.com/plotly/datasets/master/us-cities-top-1k.csv")

import plotly.express as px

figure = px.scatter_mapbox(us_cities, lat="lat", lon="lon", hover_name="City", hover_data=["State", "Population"],
                color_discrete_sequence=["fuchsia"], zoom=3)    
figure.update_layout(mapbox_style="open-street-map", autosize=True)
figure.update_layout(margin={"r":0,"t":0,"l":0,"b":0})

min_year=1950
max_year=datetime.date.today().year

layout = html.Div([
    html.Div(children=[
        dcc.Graph(id='graph', figure=figure, style={"height": "inherit"})
    ],
    style={"height": "inherit"}),
    html.Div([
            html.P("Selecteer periode dat opgraving is uitgevoerd:", className="control_label"),
            html.P(f'Periode selectie: "[{str(min_year)}, {str(max_year)}]"', id='output-container-year-slider', className="control_label"),
            html.P(' '),
            dcc.RangeSlider(
                id="year_slider",
                min=min_year,
                max=max_year,
                value=[min_year, max_year],
                className="dcc_control",
                tooltip={'always_visible': False},
            ),
            html.P("Filteren op materiaal:", className="control_label"),
            dcc.RadioItems(
                id="radio_materiaal",
                options=[
                    {"label": "Alles ", "value": "all"},
                    {"label": "Selectie ", "value": "custom"},
                ],
                value="active",
                labelStyle={"display": "inline-block"},
                className="dcc_control",
            ),
            dcc.Dropdown(
                id="well_statuses",
                options=well_status_options,
                multi=True,
                value=list(WELL_STATUSES.keys()),
                className="dcc_control",
            ),
            dcc.Checklist(
                id="lock_selector",
                options=[{"label": "Lock camera", "value": "locked"}],
                className="dcc_control",
                value=[],
            ),
            html.P("Filter by well type:", className="control_label"),
            dcc.RadioItems(
                id="well_type_selector",
                options=[
                    {"label": "All ", "value": "all"},
                    {"label": "Productive only ", "value": "productive"},
                    {"label": "Customize ", "value": "custom"},
                ],
                value="productive",
                labelStyle={"display": "inline-block"},
                className="dcc_control",
            ),
            dcc.Dropdown(
                id="well_types",
                options=well_type_options,
                multi=True,
                value=list(WELL_TYPES.keys()),
                className="dcc_control",
            ),
        ],
        className="pretty_container three columns",
        id="cross-filter-options",
        style={"position": "absolute", "right": "20px", "top": "20px"},
    ),
    #html.Script('dragElement(document.getElementById("cross-filter-options"));', type='application/javascript')
],
style={'height': '90vh'})








def register_callbacks(dashapp):


    @dashapp.callback(
        dash.dependencies.Output('output-container-year-slider', 'children'),
        [dash.dependencies.Input('year_slider', 'value')])
    def update_output(value):
        return 'Periode selectie: "{}"'.format(value)
   
    # Radio -> multi
    @dashapp.callback(Output("well_types", "value"), [Input("well_type_selector", "value")])
    def display_type(selector):
        if selector == "all":
            return list(WELL_TYPES.keys())
        elif selector == "productive":
            return ["GD", "GE", "GW", "IG", "IW", "OD", "OE", "OW"]
        return []


    # Slider -> count graph
    @dashapp.callback(Output("year_slider", "value"), [Input("count_graph", "selectedData")])
    def update_year_slider(count_graph_selected):

        return None

    # Selectors -> main graph
    @dashapp.callback(
        Output("main_graph", "figure"),
        [
            Input("well_statuses", "value"),
            Input("well_types", "value"),
            Input("year_slider", "value"),
        ],
        [State("lock_selector", "value"), State("main_graph", "relayoutData")],
    )
    def make_main_figure(
        well_statuses, well_types, year_slider, selector, main_graph_layout
    ):

        dff = filter_dataframe(df, well_statuses, well_types, year_slider)

        traces = []
        for well_type, dfff in dff.groupby("Well_Type"):
            trace = dict(
                type="scattermapbox",
                lon=dfff["Surface_Longitude"],
                lat=dfff["Surface_latitude"],
                text=dfff["Well_Name"],
                customdata=dfff["API_WellNo"],
                name=WELL_TYPES[well_type],
                marker=dict(size=4, opacity=0.6),
            )
            traces.append(trace)

        # relayoutData is None by default, and {'autosize': True} without relayout action
        if main_graph_layout is not None and selector is not None and "locked" in selector:
            if "mapbox.center" in main_graph_layout.keys():
                lon = float(main_graph_layout["mapbox.center"]["lon"])
                lat = float(main_graph_layout["mapbox.center"]["lat"])
                zoom = float(main_graph_layout["mapbox.zoom"])
                dict_layout["mapbox"]["center"]["lon"] = lon
                dict_layout["mapbox"]["center"]["lat"] = lat
                dict_layout["mapbox"]["zoom"] = zoom

        figure = dict(data=traces, layout=dict_layout)

        us_cities = pd.read_csv("https://raw.githubusercontent.com/plotly/datasets/master/us-cities-top-1k.csv")

        import plotly.express as px

        figure = px.scatter_mapbox(us_cities, lat="lat", lon="lon", hover_name="City", hover_data=["State", "Population"],
                        color_discrete_sequence=["fuchsia"], zoom=3)    
        figure.update_layout(mapbox_style="open-street-map", autosize=True)
        figure.update_layout(margin={"r":0,"t":0,"l":0,"b":0})
        #figure.update_layout(style={"height": "90vh"})
        return figure

