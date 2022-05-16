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

*)
echo "Sorry, onbekend commando. Gebruik: dev, app, acc, prod, start of stop" ;;
esac