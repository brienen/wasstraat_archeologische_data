FROM python:3.11-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
      libmagic-dev gdal-bin libgdal-dev g++ poppler-utils netcat-openbsd && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Alle pakketversies (ook afgeleide) liggen vast in constraints.txt, zodat een verse
# build dezelfde versies oplevert. De build stopt als de geïnstalleerde versies afwijken.
# 'make constraints' bouwt met VASTE_VERSIES=0: pip kiest dan de nieuwste versies binnen
# de grenzen van requirements.txt en die worden opnieuw vastgelegd.
ARG VASTE_VERSIES=1
COPY ./services/flask/requirements.txt ./services/flask/constraints.txt /tmp/
RUN if [ "$VASTE_VERSIES" = "0" ]; then VERSIES=/dev/null; else VERSIES=/tmp/constraints.txt; fi && \
    pip install --no-cache-dir -c $VERSIES --upgrade pip setuptools wheel && \
    pip install --no-cache-dir -c $VERSIES -r /tmp/requirements.txt && \
    pip check && \
    if [ "$VERSIES" != "/dev/null" ]; then \
      grep -v -e '^#' -e '^$' /tmp/constraints.txt | sort -f > /tmp/vastgelegd.txt && \
      pip list --format=freeze | sort -f > /tmp/geinstalleerd.txt && \
      diff /tmp/vastgelegd.txt /tmp/geinstalleerd.txt || \
      { echo "Geïnstalleerde versies wijken af van services/flask/constraints.txt; draai 'make constraints'." >&2; exit 1; }; \
    fi

ENV PYTHONPATH=/app:/app/app
WORKDIR /app/
COPY ./app /app
COPY ./shared /app/app/shared
COPY ./scripts/flask/init.sh /opt/init.sh
RUN chmod +x /opt/init.sh

ENV STATIC_PATH=/app/app/static
ENV STATIC_INDEX=1
EXPOSE 5051

CMD ["/opt/init.sh"]
