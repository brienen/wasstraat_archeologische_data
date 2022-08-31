FROM python:3.10-slim-bullseye

# set environment variables
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1


RUN apt-get update && apt-get -y upgrade && apt-get clean
RUN apt-get install -y libmagic-dev gdal-bin libgdal-dev g++ poppler-utils

#ARG UNAME=flask
#ARG UID=1000
#ARG GID=1000
#RUN groupadd -g $GID -o $UNAME
#RUN useradd -m -u $UID -g $GID -o -s /bin/bash $UNAME

#USER $UNAME
#ENV VIRTUAL_ENV=/home/$UNAME/venv
#RUN python -m venv $VIRTUAL_ENV
#ENV PATH="$VIRTUAL_ENV/bin:$PATH"

RUN pip install --upgrade --no-cache-dir pip
RUN pip install --no-cache-dir gunicorn gevent psycogreen 
COPY ./services/flask/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

ENV PYTHONPATH=/app:/app/app

WORKDIR /app/
COPY ./app /app
COPY ./shared /app/app/shared
ENV STATIC_PATH /app/app/static
ENV STATIC_INDEX 1

EXPOSE 5000

CMD gunicorn --worker-class gevent \
  --bind 0.0.0.0:5000 \ 
  --config ./gunicorn.conf.py \
  patched_app:app
