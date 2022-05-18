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

acc)
echo "Starting in accept mode"
docker-compose -f docker-compose.yml -f docker-compose.acc.yml up -d
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
docker-compose build postgres flask airflow
docker tag wasstraat_flask:latest wasstraat_flask:$2 
docker tag wasstraat_flask:latest brienen/wasstraat_flask:$2 
docker push brienen/wasstraat_flask:$2

docker tag wasstraat_postgres:latest wasstraat_postgres:$2 
docker tag wasstraat_postgres:latest brienen/wasstraat_postgres:$2 
docker push brienen/wasstraat_postgres:$2

docker tag wasstraat_airflow:latest wasstraat_airflow:$2 
docker tag wasstraat_airflow:latest brienen/wasstraat_airflow:$2 
docker push brienen/wasstraat_airflow:$2
;;


*)
echo "Sorry, onbekend commando. Gebruik: release, dev, app, acc, prod, start of stop" ;;
esac