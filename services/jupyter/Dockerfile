FROM jupyter/datascience-notebook:aarch64-ubuntu-22.04

USER root 
RUN apt-get update && apt-get upgrade -y && apt-get install -y libmagic-dev gdal-bin libgdal-dev g++
USER jovyan

RUN python -m pip install --upgrade pip
RUN pip install --upgrade setuptools
RUN pip install python-magic altair vincent geopandas folium mongoengine psycopg2-binary pymongo sqlacodegen pandas_profiling openpyxl simplejson notebook opencv-python python-magic
#RUN pip install tensorflow deepface --use-feature=2020-resolver
