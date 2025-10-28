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

# Check of admin-user al bestaat
echo "==> Checking if admin user exists"
python <<EOF
from flask_appbuilder.security.sqla.models import User
from app import appbuilder
with appbuilder.app.app_context():
    if not appbuilder.sm.find_user(username="admin"):
        print("==> Creating admin user")
        appbuilder.sm.add_user(
            username="admin",
            first_name="Admin",
            last_name="User",
            email="admin@local",
            role=appbuilder.sm.find_role("Admin"),
            password="admin"
        )
    else:
        print("==> Admin user already exists")
EOF

# Start de Flask-app met gunicorn
echo "==> Starting Flask app"
exec gunicorn --worker-class gevent \
  --bind 0.0.0.0:5051 \
  --config ./gunicorn.conf.py \
  $FLASK_APP:app