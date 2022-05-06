FROM tiangolo/meinheld-gunicorn-flask:python3.8

RUN apt-get update && apt-get -y upgrade

RUN pip install --upgrade setuptools
RUN pip install flask_dropzone python-magic vega_datasets altair vincent geopandas pandas numpy folium mongoengine flask_mongoengine flask-appbuilder fab-addon-geoalchemy Pillow Flask-Migrate flask-mysql psycopg2-binary panel pymongo sqlacodegen flask_debugtoolbar dash pandas_datareader dash_bootstrap_components
RUN pip install Flask-WTF==0.14.3

# For development, Jupyter remote kernel, Hydrogen
# Using inside the container:
# jupyter notebook --ip=0.0.0.0 --allow-root
#ARG env=prod
#RUN bash -c "if [ $env == 'dev' ] ; then pip install jupyter plotly jupyter-tabnine; jupyter nbextension install --py jupyter_tabnine; jupyter nbextension enable --py jupyter_tabnine; jupyter serverextension enable --py jupyter_tabnine; fi"
#EXPOSE 8888

WORKDIR /app/
COPY ./app /app
ADD ./app/lib /app/lib
#RUN cd /app/lib/Flask-ImageManager; python setup.py install; cd /app 
RUN cd /app/lib; git clone https://github.com/mihxen/Flask-ImageManager; python setup.py install; cd /app 
#ENV STATIC_PATH /app/app/static
#ENV STATIC_INDEX 1

EXPOSE 5000
