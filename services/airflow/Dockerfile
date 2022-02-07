FROM apache/airflow:2.2.3

USER root
# INSTALL TOOLS
RUN apt update && apt -y upgrade && apt -y install software-properties-common mdbtools vim curl gnupg wget libmagic-dev file libaio-dev 
RUN wget -qO - https://www.mongodb.org/static/pgp/server-4.2.asc | apt-key add -
#RUN wget -qO - https://www.mongodb.org/static/pgp/server-4.4.asc | apt-key add -
RUN echo "deb [ arch=amd64 ] https://repo.mongodb.org/apt/ubuntu bionic/mongodb-org/4.2 multiverse" | tee /etc/apt/sources.list.d/mongodb-org-4.2.list
#RUN echo "deb [ arch=amd64 ] https://repo.mongodb.org/apt/ubuntu focal/mongodb-org/4.4 multiverse" | tee /etc/apt/sources.list.d/mongodb-org-4.4.list
RUN apt-get update && apt-get -y upgrade && apt-get install -y mongodb-org-shell mongodb-org-tools
RUN mkdir extra

USER airflow
RUN pip install --upgrade pip
RUN pip install psycopg2-binary
RUN pip install matplotlib altair shapely geopandas raven passlib[bcrypt] tenacity pymongo Pillow python-magic roman pandas opentelemetry-api openpyxl geoalchemy2
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