FROM jupyter/datascience-notebook:aarch64-ubuntu-22.04

USER root 
RUN apt-get update && apt-get upgrade -y && apt-get install -y libmagic-dev gdal-bin libgdal-dev g++ poppler-utils
USER jovyan

RUN python -m pip install --upgrade pip
RUN pip install --upgrade setuptools
RUN pip install backports.tarfile
RUN pip install python-magic altair geopandas folium mongoengine psycopg2-binary pymongo sqlacodegen pandas_profiling openpyxl simplejson notebook opencv-python pdf2image elasticsearch