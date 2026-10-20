# De tag python-3.11 wordt sinds oktober 2024 niet meer bijgewerkt; de digest zet hem
# definitief vast, zodat een verse build dezelfde basis krijgt.
FROM quay.io/jupyter/datascience-notebook:python-3.11@sha256:14379f24c840f27375e3a4b29a9fa55e449633ac85c9cf3806ca62d11e5603ec

USER root
RUN apt-get update && \
    apt-get install -y --no-install-recommends libmagic-dev gdal-bin libgdal-dev g++ poppler-utils && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*
USER jovyan

# De versies van wat pip bovenop de basisimage installeert liggen vast in constraints.txt.
# 'make constraints' bouwt met VASTE_VERSIES=0 en legt de nieuwste versies opnieuw vast.
ARG VASTE_VERSIES=1
COPY ./services/jupyter/constraints.txt /tmp/constraints.txt
RUN if [ "$VASTE_VERSIES" = "0" ]; then VERSIES=/dev/null; else VERSIES=/tmp/constraints.txt; fi && \
    pip install --no-cache-dir -c $VERSIES \
    python-magic altair geopandas folium mongoengine \
    psycopg2-binary pymongo sqlacodegen openpyxl \
    simplejson opencv-python pdf2image elasticsearch
