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
echo "Releasing this build (werkt nog niet)"
git stage .
git commit -m "$3"
git push
git tag -a $2 -m "$3"
docker-compose build postgres flask airflow
docker commit wasstraat_flask:latest brienen/wasstraat_flask:$2 
docker commit wasstraat_flask:latest brienen/wasstraat_flask:latest 
docker commit wasstraat_postges:latest brienen/wasstraat_postgres:$2 
docker commit wasstraat_postgres:latest brienen/wasstraat_postgres:latest 
docker commit wasstraat_airflow:latest brienen/wasstraat_airflow:$2 
docker commit wasstraat_airflow:latest brienen/wasstraat_airflow:latest 
;;


*)
echo "Sorry, onbekend commando. Gebruik: dev, app, acc, prod, start of stop" ;;
esac