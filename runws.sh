#!/usr/bin/env bash

case $1 in
dev)
echo "Starting in development mode"
docker-compose -f docker-compose.yml -f docker-compose.develop.yml up -d
;;

app)
echo "Starting in local mode"
docker-compose up -d 
;;

example)
echo "Starting example"
docker-compose -f docker-compose.yml -f docker-compose.example.yml up -d
;;

acc)
echo "Starting in accept mode"
docker-compose -f docker-compose.yml -f docker-compose.acc.yml up -d
;;

uwsgi)
echo "Starting in uwsgi mode"
docker-compose -f docker-compose.yml -f docker-compose.acc-uwsgi.yml up -d
;;

prod)
echo "Starting in production mode"
docker-compose -f docker-compose.yml -f docker-compose.prod.yml up -d
;;

stop)
echo "Stopping containers"
docker-compose stop
;;

start)
echo "Starting containers"
docker-compose start
;;

release)
echo "Releasing this build..."
echo "VERSION=$2" > config/version.env
git tag -a $2 -m "$3"
git stage .
git commit -m "$3"
git push --all
git push --tags
#docker-compose build postgres flask airflow
docker login
docker buildx build --no-cache --platform linux/amd64,linux/arm64 --builder mybuilder -f ./services/flask/Dockerfile -t brienen/wasstraat_flask:$2 --push .
#docker buildx build --no-cache --platform linux/amd64,linux/arm64 --builder mybuilder -f ./services/flask/Dockerfile-uwsgi -t brienen/wasstraat_flask-uwsgi:$2 --push .
#docker tag brienen/wasstraat_flask:$2 wasstraat_flask:$2 
#docker tag brienen/wasstraat_flask:$2 wasstraat_flask:latest
#docker push brienen/wasstraat_flask:$2

#docker buildx build --platform linux/amd64,linux/arm64 --builder mybuilder -f ./services/postgres/Dockerfile -t brienen/wasstraat_postgres:$2 --push .
#docker tag wasstraat_postgres:latest wasstraat_postgres:$2 
#docker tag wasstraat_postgres:latest brienen/wasstraat_postgres:$2 
#docker push brienen/wasstraat_postgres:$2

#docker buildx build --platform linux/amd64,linux/arm64 --builder mybuilder -f ./services/airflow/Dockerfile -t brienen/wasstraat_airflow:$2 --push .
#docker tag wasstraat_airflow:latest wasstraat_airflow:$2 
#docker tag wasstraat_airflow:latest brienen/wasstraat_airflow:$2 
#docker push brienen/wasstraat_airflow:$2

#docker buildx build --no-cache --platform linux/amd64,linux/arm64 --builder mybuilder -f ./services/apache/Dockerfile -t brienen/wasstraat_apache:$2 --push .
;;

backup)
DT=$(date +"%Y-%m-%d_%H-%M-%S")
echo "Backing up Postgres and Mongo with timestamp $DT"
docker-compose stop flask airflow

docker exec -u airflow -w /backup wasstraat_postgres bash -c "pg_dump -v -F t -f postgres_$DT.tar flask"
docker exec -w /backup wasstraat_mongo bash -c "mongodump --uri mongodb://\$MONGO_INITDB_ROOT_USERNAME:\$MONGO_INITDB_ROOT_PASSWORD@localhost:27017/\$DB_STAGING?authSource=admin --out mongo_$DT"
docker exec -w /backup wasstraat_mongo bash -c "mongodump --uri mongodb://\$MONGO_INITDB_ROOT_USERNAME:\$MONGO_INITDB_ROOT_PASSWORD@localhost:27017/\$DB_FILES?authSource=admin --out mongo_$DT"
docker exec -w /backup wasstraat_mongo bash -c "mongodump --uri mongodb://\$MONGO_INITDB_ROOT_USERNAME:\$MONGO_INITDB_ROOT_PASSWORD@localhost:27017/\$DB_ANALYSE?authSource=admin --out mongo_$DT"
;;

restore)
echo "Restoring Postgres and Mongo with timestamp $2"
docker-compose stop flask airflow
docker exec -u postgres -w /backup wasstraat_postgres bash -c "pg_restore -Ft -c -v -d flask < postgres_$2.tar"
docker exec -w /backup wasstraat_mongo bash -c "mongorestore --drop --uri mongodb://\$MONGO_INITDB_ROOT_USERNAME:\$MONGO_INITDB_ROOT_PASSWORD@localhost:27017/?authSource=admin mongo_$2"
;;

export)
DT=$(date +"%Y-%m-%d_%H-%M-%S")
TABLES="Def_Vulling Def_Conserveringsproject Def_artefact_conservering Def_DT_Soort_Plant Def_Project Def_Put Def_Spoor Def_Vondst Def_Plaatsing Def_Vlak Def_artefact_abr Def_Doos Def_Standplaats Def_Bruikleen Def_Partij Def_Vindplaats Def_Artefact Def_ABR Def_Stelling Def_DT_Soort_Schelp Def_Bestand Def_DT_Soort_Deel Def_DT_Soort_Staat Def_Monster Def_Monster_Botanie Def_Monster_Schelp"
echo "Exporting Postgres data to CSV with timestamp $DT"
docker-compose stop flask airflow

docker exec -u airflow -w /backup wasstraat_postgres bash -c "mkdir postgres_$DT"
for table in $TABLES
do
   echo Exporting table $table
   tb="public.\"$table\""
   docker exec -u airflow wasstraat_postgres bash -c "psql -t -d flask -c 'COPY $tb TO \$\$/backup/postgres_$DT/$table.csv\$\$ DELIMITER \$\$;\$\$ CSV HEADER QUOTE \$\$\"\$\$ ESCAPE \$\$\"\$\$; '"
done
;;



*)
echo "Sorry, onbekend commando. Gebruik: release, dev, app, acc, uwsg, prod, start, backup, restore of stop" ;;
esac