#!/usr/bin/env bash

# Wait for db
while ! nc $DB__HOST $DB__PORT; do
  >&2 echo "Waiting for postgres to be up and running..."
  sleep 1
done

# Not working
#export PGPASSWORD=${DB__PASSWORD}
#export AIRFLOW__CORE__SQL_ALCHEMY_CONN="postgresql+psycopg2://${DB__USERNAME}:${DB__PASSWORD}@${DB__HOST}:${DB__PORT}/${DB__NAME}"

# check on db if admin exists
echo "Check if Admin exists.."
SECURITY_ALREADY_INITIALIZED=$(cat /opt/airflow/extra/check_init.sql | psql -h ${DB__HOST} -p ${DB__PORT} -U ${DB__USERNAME} ${DB__NAME} -t | xargs | head -c 1)

# Initialize db
echo "Upgrading database.."
airflow db upgrade

if [ "${SECURITY_ALREADY_INITIALIZED}" == "0" ]; then
  echo "Creating admin user.."
	airflow users create -r Admin -u "$SECURITY__ADMIN_USERNAME" -e "$SECURITY__ADMIN_EMAIL" -f "$SECURITY__ADMIN_FIRSTNAME" -l "$SECURITY__ADMIN_LASTNAME" -p "$SECURITY__ADMIN_PASSWORD"
	cat /opt/airflow/extra/set_init.sql | psql -h ${DB__HOST} -p ${DB__PORT} -U ${DB__USERNAME} ${DB__NAME} -t
fi

# Run scheduler 
echo "Running scheduler.."
airflow scheduler &

# Run webserver
echo "Running webserver.."
exec airflow webserver