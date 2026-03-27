FROM quay.io/jupyter/datascience-notebook:python-3.11

USER root
RUN apt-get update && \
    apt-get install -y --no-install-recommends libmagic-dev gdal-bin libgdal-dev g++ poppler-utils && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*
USER jovyan

RUN pip install --no-cache-dir \
    python-magic altair geopandas folium mongoengine \
    psycopg2-binary pymongo sqlacodegen openpyxl \
    simplejson opencv-python pdf2image elasticsearch
