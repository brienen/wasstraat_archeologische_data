FROM tiangolo/meinheld-gunicorn-flask:python3.8

RUN apt-get update && apt-get -y upgrade
RUN pip install --upgrade setuptools
RUN pip install flask_dropzone python-magic vega_datasets altair vincent geopandas pandas numpy folium mongoengine flask_mongoengine flask-appbuilder fab-addon-geoalchemy Pillow Flask-Migrate flask-mysql psycopg2-binary panel pymongo sqlacodegen flask_debugtoolbar dash pandas_datareader dash_bootstrap_components
RUN pip install Flask-WTF==0.14.3

# Fix for Github: https://github.com/tiangolo/meinheld-gunicorn-docker/issues/22 Error: class uri 'egg:meinheld#gunicorn_worker' invalid or not found #22
RUN pip install greenlet==0.4.16

WORKDIR /app/
COPY ./app /app
ADD ./app/lib /app/lib
RUN cd /app/lib; git clone https://github.com/mihxen/Flask-ImageManager; python setup.py install; cd /app 
#ENV STATIC_PATH /app/app/static
#ENV STATIC_INDEX 1

EXPOSE 5000
