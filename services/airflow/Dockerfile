FROM apache/airflow:2.10.5-python3.11

USER root

# System tools + GDAL + mdbtools
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        mdbtools \
        curl \
        gnupg \
        libmagic-dev \
        file \
        libaio-dev \
        poppler-utils \
        gdal-bin \
        libgdal-dev \
        g++ && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# MongoDB database tools + mongosh (multi-arch, directe .deb download)
# MongoDB biedt geen Debian 12 arm64 packages, maar Ubuntu 22.04 arm64 is compatibel.
# Voor x86_64 gebruiken we het Debian 12 pakket.
ARG MONGO_TOOLS_VERSION=100.10.0
ARG MONGOSH_VERSION=2.3.8
RUN ARCH=$(dpkg --print-architecture) && \
    if [ "$ARCH" = "arm64" ]; then TOOLS_PLATFORM="ubuntu2204-arm64"; \
    else TOOLS_PLATFORM="debian12-x86_64"; fi && \
    curl -fsSL "https://fastdl.mongodb.org/tools/db/mongodb-database-tools-${TOOLS_PLATFORM}-${MONGO_TOOLS_VERSION}.deb" \
        -o /tmp/mongodb-database-tools.deb && \
    apt-get update && \
    apt-get install -y --no-install-recommends /tmp/mongodb-database-tools.deb && \
    rm /tmp/mongodb-database-tools.deb && \
    curl -fsSL "https://downloads.mongodb.com/compass/mongodb-mongosh_${MONGOSH_VERSION}_${ARCH}.deb" \
        -o /tmp/mongosh.deb && \
    apt-get install -y --no-install-recommends /tmp/mongosh.deb && \
    rm /tmp/mongosh.deb && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Python dependencies
USER airflow
COPY ./services/airflow/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt
RUN mkdir -p tmp

# SQL en entrypoint scripts
COPY scripts/airflow/check_init.sql ./extra/check_init.sql
COPY scripts/airflow/set_init.sql ./extra/set_init.sql
COPY scripts/airflow/*.sh .

# Pipelinecode, importscripts en gedeelde modules in de image, zodat de gepubliceerde
# image zonder broncode-volumes draait (deploy/docker-compose.yml). De ontwikkelomgeving
# (docker-compose.yml) mount airflow_app/dags, airflow_app/scripts en shared/ hieroverheen.
COPY --chown=airflow:root ./airflow_app/dags ./dags
COPY --chown=airflow:root ./airflow_app/scripts ./scripts
COPY --chown=airflow:root ./shared ./dags/shared

USER root
RUN chmod 744 ./*.sh && chown airflow *.sh && chmod +x ./scripts/*.sh
# Standaard uitvoermap voor media (AIRFLOW_OUTPUT_MEDIA). De compose-bestanden mounten hier
# een map of volume overheen; een leeg named volume neemt eigenaar en rechten van deze map
# over, zodat de airflow-gebruiker er zonder bind mount of tmpfs in kan schrijven.
RUN mkdir -p /output/archeomedia && chown airflow:root /output/archeomedia

USER airflow
ENTRYPOINT ["./init.sh"]
