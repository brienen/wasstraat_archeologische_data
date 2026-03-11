-- Initialisatiescript voor de test-PostgreSQL container.
-- Maakt twee databases aan:
--   1. airflow_test  – Airflow metadata (scheduler, DAG runs)
--   2. flask         – pipeline-doeldata (Def_* tabellen)
--
-- Wordt automatisch uitgevoerd bij eerste start via
-- /docker-entrypoint-initdb.d/

-- De flask-database voor de wasstraat-pipeline output
CREATE DATABASE flask;

-- PostGIS extensie in de flask-database
\c flask
CREATE EXTENSION IF NOT EXISTS postgis;
