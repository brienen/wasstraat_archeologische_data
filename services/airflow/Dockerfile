FROM apache/airflow:2.3.3

USER root

# --- CONFIGURABLE BUILD ARGS ---
ARG OS_FAMILY=debian         # "ubuntu" or "debian"
ARG OS_CODENAME=buster       # e.g., bionic, focal, buster
ARG MONGO_VERSION=4.2        # e.g., 4.2, 4.4

# INSTALL TOOLS
# Install general tools and dependencies
RUN ACCEPT_EULA=Y apt update && \
    ACCEPT_EULA=Y apt -y upgrade && \
    apt -y install \
        software-properties-common \
        mdbtools \
        vim \
        curl \
        gnupg \
        wget \
        libmagic-dev \
        file \
        libaio-dev \
        poppler-utils
        
# Install MongoDB tools
RUN wget -qO - https://www.mongodb.org/static/pgp/server-${MONGO_VERSION}.asc | apt-key add -
RUN echo "deb [arch=amd64] https://repo.mongodb.org/apt/${OS_FAMILY} ${OS_CODENAME}/mongodb-org/${MONGO_VERSION} main" \
    | tee /etc/apt/sources.list.d/mongodb-org-${MONGO_VERSION}.list
RUN apt-get update && \
    apt-get -y upgrade && \
    apt-get install -y \
        mongodb-org-shell \
        mongodb-org-tools

# Install GDAL
RUN apt-get install -y gdal-bin libgdal-dev g++

# INSTALL PYTHON DEPENDENCIES
USER airflow
COPY ./services/airflow/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt
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