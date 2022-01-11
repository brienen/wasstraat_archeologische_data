FROM apache/airflow:2.2.3-python3.7

USER root
# INSTALL TOOLS
RUN apt update && apt -y upgrade && apt -y install software-properties-common mdbtools vim curl gnupg wget libmagic-dev
RUN wget -qO - https://www.mongodb.org/static/pgp/server-4.2.asc | apt-key add -
#RUN wget -qO - https://www.mongodb.org/static/pgp/server-4.4.asc | apt-key add -
RUN echo "deb [ arch=amd64 ] https://repo.mongodb.org/apt/ubuntu bionic/mongodb-org/4.2 multiverse" | tee /etc/apt/sources.list.d/mongodb-org-4.2.list
#RUN echo "deb [ arch=amd64 ] https://repo.mongodb.org/apt/ubuntu focal/mongodb-org/4.4 multiverse" | tee /etc/apt/sources.list.d/mongodb-org-4.4.list
RUN apt-get update && apt-get -y upgrade && apt-get install -y mongodb-org-shell mongodb-org-tools

RUN apt-get update && apt-get -y install libaio-dev && apt-get install postgresql-client
RUN mkdir extra

USER airflow
RUN pip install --upgrade pip
#RUN pip install matplotlib altair shapely geopandas psycopg2 flask_appbuilder fab-addon-geoalchemy psycopg2-binary==2.7.7 raven celery[redis] SQLAlchemy==1.3.0 passlib[bcrypt]==1.7.1 tenacity==5.0.3 pymongo Pillow Flask python-magic roman pandas opentelemetry-api
RUN pip install matplotlib altair shapely geopandas fab-addon-geoalchemy raven passlib[bcrypt] tenacity pymongo Pillow python-magic roman pandas opentelemetry-api
RUN mkdir tmp
# COPY SQL SCRIPT
COPY scripts/airflow/check_init.sql ./extra/check_init.sql
COPY scripts/airflow/set_init.sql ./extra/set_init.sql
# ENTRYPOINT SCRIPT
COPY scripts/airflow/*.sh .

USER root
RUN chmod 744 ./*.sh && chown airflow *.sh

USER airflow
ENTRYPOINT ["./init.sh"]