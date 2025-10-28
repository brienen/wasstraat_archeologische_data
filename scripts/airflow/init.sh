#!/usr/bin/env bash

# Debugpy toggle via env
#   DEBUGPY=1            -> enable debug server
#   DEBUG_TARGET=webserver|scheduler (default: scheduler)
#   DEBUG_PORT=<port>    (default: 5678)
if [ "${DEBUGPY}" = "1" ]; then
  PORT="${DEBUG_PORT:-5678}"
  TARGET="${DEBUG_TARGET:-scheduler}"
  echo "[init] Debugpy enabled on port ${PORT}; target=${TARGET}"
fi

# === PYTHONPATH configuratie ===
export PYTHONPATH="/opt/airflow:/opt/airflow/dags:/opt/airflow/scripts:/opt/airflow/config:${PYTHONPATH}"
echo "[init] PYTHONPATH set to: $PYTHONPATH"

# Wait for DB to be available
echo "Waiting for PostgreSQL at $DB__HOST:$DB__PORT..."
while ! nc -z "$DB__HOST" "$DB__PORT"; do
  sleep 1
done

# Ensure script is executable
chmod +x /opt/airflow/scripts/importMDB.sh

# check on db if admin exists
echo "Checking if admin user already exists..."
SECURITY_ALREADY_INITIALIZED=$(cat /opt/airflow/extra/check_init.sql | psql -h ${DB__HOST} -p ${DB__PORT} -U ${DB__USERNAME} ${DB__NAME} -t | xargs | head -c 1)

# Initialize db
echo "Upgrading database.."
airflow db upgrade
echo "Database upgraded."

if [ "${SECURITY_ALREADY_INITIALIZED}" == "0" ]; then
  echo "Creating admin user.."
	airflow users create -r Admin -u "$SECURITY__ADMIN_USERNAME" -e "$SECURITY__ADMIN_EMAIL" -f "$SECURITY__ADMIN_FIRSTNAME" -l "$SECURITY__ADMIN_LASTNAME" -p "$SECURITY__ADMIN_PASSWORD"
	cat /opt/airflow/extra/set_init.sql | psql -h ${DB__HOST} -p ${DB__PORT} -U ${DB__USERNAME} ${DB__NAME} -q
fi

# Start Airflow with/without debugpy
if [ "${DEBUGPY}" = "1" ]; then
  if [ "${TARGET}" = "webserver" ]; then
    echo "Starting Airflow scheduler in the background (non-debug)..."
    airflow scheduler > /dev/null 2>&1 &

    echo "Starting Airflow webserver under debugpy on port ${PORT} (waiting for client)..."
    exec python -m debugpy --listen 0.0.0.0:${PORT} --wait-for-client -m airflow webserver --debug
  else
    echo "Starting Airflow webserver on port 8080 (non-debug) in background..."
    airflow webserver > /dev/null 2>&1 &

    echo "Starting Airflow scheduler under debugpy on port ${PORT} (waiting for client)..."
    exec python -m debugpy --listen 0.0.0.0:${PORT} --wait-for-client -m airflow scheduler
  fi
else
  # Default behaviour without debugpy
  echo "Starting Airflow scheduler in the background..."
  airflow scheduler > /dev/null 2>&1 &

  echo "Starting Airflow webserver on port 8080..."
  exec airflow webserver
fi