#FROM python:3.10-slim-bullseye
FROM python:3.9.16-bullseye

# set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1


RUN apt-get update && \
    apt-get -y upgrade && \
    apt-get install -y --no-install-recommends \
      libmagic-dev gdal-bin libgdal-dev g++ poppler-utils netcat && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

RUN pip install --upgrade --no-cache-dir pip
RUN pip install --no-cache-dir gunicorn gevent psycogreen 
COPY ./services/flask/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

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