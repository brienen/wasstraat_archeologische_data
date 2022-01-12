CREATE TABLE airflow__extra_conf(
  conf_name  VARCHAR (255) PRIMARY KEY,
  conf_value VARCHAR (255) NOT NULL
);

CREATE USER flask WITH
    LOGIN
    NOSUPERUSER
    NOCREATEDB
    NOCREATEROLE
    NOINHERIT
    NOREPLICATION
    PASSWORD 'kjehbv687697bdasd33masnkj';

CREATE DATABASE flask OWNER flask;
GRANT ALL PRIVILEGES ON DATABASE flask TO flask;

\c flask
CREATE EXTENSION postgis;
CREATE EXTENSION postgis_raster;
CREATE EXTENSION postgis_topology;
CREATE EXTENSION postgis_sfcgal;
CREATE EXTENSION fuzzystrmatch;
CREATE EXTENSION address_standardizer;
CREATE EXTENSION address_standardizer_data_us;
CREATE EXTENSION postgis_tiger_geocoder;
