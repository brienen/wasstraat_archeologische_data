FROM jupyter/tensorflow-notebook

USER root 
RUN ACCEPT_EULA=Y apt update && ACCEPT_EULA=Y apt -y upgrade && apt -y install libmagic-dev
USER jovyan

RUN python -m pip install --upgrade pip
RUN pip install --upgrade setuptools
RUN pip install python-magic altair vincent geopandas folium mongoengine psycopg2-binary pymongo sqlacodegen pandas_profiling openpyxl simplejson xeus-python notebook opencv-python python-magic
RUN pip install deepface --use-feature=2020-resolver

# For development, Jupyter remote kernel, Hydrogen
# Using inside the container:
# jupyter notebook --ip=0.0.0.0 --allow-root
#ARG env=prod
#RUN bash -c "if [ $env == 'dev' ] ; then pip install jupyter plotly jupyter-tabnine; jupyter nbextension install --py jupyter_tabnine; jupyter nbextension enable --py jupyter_tabnine; jupyter serverextension enable --py jupyter_tabnine; fi"
#EXPOSE 8888