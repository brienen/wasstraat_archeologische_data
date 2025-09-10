#!/usr/bin/env bash

# Wait for DB to be available
echo "Waiting for PostgreSQL at $DB__HOST:$DB__PORT..."
while ! nc -z "$DB__HOST" "$DB__PORT"; do
  sleep 1
done

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

# Run scheduler 
echo "Starting Airflow scheduler in the background..."
airflow scheduler > /dev/null 2>&1 &

# Run webserver
echo "Starting Airflow webserver on port 8080..."
exec airflow webserver