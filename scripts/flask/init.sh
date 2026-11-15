#!/bin/bash

set -e

echo "==> Waiting for database at postgres:5432..."

# Wachten tot de database bereikbaar is
until nc -z "postgres" "5432"; do
  sleep 1
done

echo "==> Database is up"

# Zet de Flask-app context
export FLASK_APP=patched_app

# Ga naar de app directory
cd /app

# Eventueel: migraties uitvoeren
#if [ -f "migrations/env.py" ]; then
#  echo "==> Running DB migrations"
#  flask db upgrade
#fi

# Maak de beheerder aan als die nog niet bestaat. Het wachtwoord komt uit
# FLASK_ADMIN_PASSWORD (config/flask.env); zie app/app/beheerder.py.
echo "==> Checking if admin user exists"
python <<'EOF'
import os
from app import appbuilder
from beheerder import maakBeheerder
with appbuilder.app.app_context():
    maakBeheerder(appbuilder.sm, os.environ)
EOF

# Start de Flask-app met gunicorn
echo "==> Starting Flask app"
exec gunicorn --worker-class gevent \
  --bind 0.0.0.0:5051 \
  --config ./gunicorn.conf.py \
  $FLASK_APP:app