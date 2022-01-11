#!/bin/bash
set -e # exit immediately if a command exits with a non-zero status.

POSTGRES="psql --username postgres"

# create database for superset
echo "Creating database: '$FLASK_PGDATABASE'"
$POSTGRES <<EOSQL
CREATE DATABASE '$FLASK_PGDATABASE' OWNER '$FLASK_PGUSER';
EOSQL
