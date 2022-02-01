FROM jupyter/datascience-notebook

RUN pip install --upgrade setuptools
RUN pip install python-magic vega_datasets altair vincent geopandas folium mongoengine psycopg2-binary pymongo sqlacodegen pandas_profiling
RUN pip install xeus-python notebook

# For development, Jupyter remote kernel, Hydrogen
# Using inside the container:
# jupyter notebook --ip=0.0.0.0 --allow-root
#ARG env=prod
#RUN bash -c "if [ $env == 'dev' ] ; then pip install jupyter plotly jupyter-tabnine; jupyter nbextension install --py jupyter_tabnine; jupyter nbextension enable --py jupyter_tabnine; jupyter serverextension enable --py jupyter_tabnine; fi"
#EXPOSE 8888