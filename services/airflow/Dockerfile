FROM apache/airflow:2.10.5-python3.11

USER root

# System tools + GDAL + mdbtools
RUN apt-get -o Acquire::Retries=3 update && \
    apt-get -o Acquire::Retries=3 install -y --no-install-recommends \
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
    curl -fsSL --retry 3 "https://fastdl.mongodb.org/tools/db/mongodb-database-tools-${TOOLS_PLATFORM}-${MONGO_TOOLS_VERSION}.deb" \
        -o /tmp/mongodb-database-tools.deb && \
    apt-get -o Acquire::Retries=3 update && \
    apt-get -o Acquire::Retries=3 install -y --no-install-recommends /tmp/mongodb-database-tools.deb && \
    rm /tmp/mongodb-database-tools.deb && \
    curl -fsSL --retry 3 "https://downloads.mongodb.com/compass/mongodb-mongosh_${MONGOSH_VERSION}_${ARCH}.deb" \
        -o /tmp/mongosh.deb && \
    apt-get -o Acquire::Retries=3 install -y --no-install-recommends /tmp/mongosh.deb && \
    rm /tmp/mongosh.deb && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Python dependencies
# De basisimage legt Airflow en al zijn pakketten vast (gebouwd met de constraints van Airflow
# 2.10.5). Die versies gelden hier als constraints (basisimage.txt): pip mag ze niet wijzigen,
# alleen pakketten toevoegen. Vraagt requirements.txt een andere versie van een pakket uit de
# basisimage, dan stopt de build. Wat requirements.txt toevoegt, ligt vast in constraints.txt,
# zodat een verse build dezelfde versies oplevert; de build stopt als een vastgelegde versie
# niet geïnstalleerd is. 'make constraints' bouwt met VASTE_VERSIES=0: pip kiest dan de nieuwste
# versies binnen de grenzen van requirements.txt en de basisimage, en die worden vastgelegd.
USER airflow
ARG VASTE_VERSIES=1
COPY ./services/airflow/requirements.txt ./services/airflow/constraints.txt /tmp/
RUN if [ "$VASTE_VERSIES" = "0" ]; then VERSIES=/dev/null; else VERSIES=/tmp/constraints.txt; fi && \
    pip list --format=freeze > /tmp/basisimage.txt && \
    pip install --no-cache-dir -c /tmp/basisimage.txt -c $VERSIES \
      "apache-airflow==${AIRFLOW_VERSION}" -r /tmp/requirements.txt && \
    pip check && \
    if [ "$VERSIES" != "/dev/null" ]; then \
      grep -v -e '^#' -e '^$' /tmp/constraints.txt | sort -f > /tmp/vastgelegd.txt && \
      pip list --format=freeze | sort -f > /tmp/geinstalleerd.txt && \
      if grep -v -x -F -f /tmp/geinstalleerd.txt /tmp/vastgelegd.txt; then \
        echo "Bovenstaande versies uit services/airflow/constraints.txt zijn niet geïnstalleerd; draai 'make constraints'." >&2; \
        exit 1; \
      fi; \
    fi
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
# Standaard uitvoermappen voor media (AIRFLOW_OUTPUT_MEDIA) en verwerkingsrapporten
# (AIRFLOW_OUTPUT_RAPPORTEN, issue 62). De compose-bestanden mounten hier een map of volume
# overheen; een leeg named volume neemt eigenaar en rechten van deze map over, zodat de
# airflow-gebruiker er zonder bind mount of tmpfs in kan schrijven.
RUN mkdir -p /output/archeomedia && chown airflow:root /output/archeomedia
RUN mkdir -p /output/rapporten && chown airflow:root /output/rapporten

USER airflow
ENTRYPOINT ["./init.sh"]
