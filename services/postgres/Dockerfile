FROM postgres:12-bullseye

LABEL maintainer="PostGIS Project - https://postgis.net"

ENV POSTGIS_MAJOR 3

RUN apt-get update \
      && apt-get -y upgrade \
      && apt-cache showpkg postgresql-$PG_MAJOR-postgis-$POSTGIS_MAJOR \
      && apt-get install -y --no-install-recommends \
           postgresql-$PG_MAJOR-postgis-$POSTGIS_MAJOR \
           postgresql-$PG_MAJOR-postgis-$POSTGIS_MAJOR-scripts \
      && rm -rf /var/lib/apt/lists/*

RUN mkdir -p /docker-entrypoint-initdb.d
COPY ./services/postgres/initdb-postgis.sh /docker-entrypoint-initdb.d/10_postgis.sh
COPY ./services/postgres/update-postgis.sh /usr/local/bin

COPY ./scripts/postgres/* /docker-entrypoint-initdb.d/