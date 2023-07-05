#!/bin/bash

echo "killing old docker processes"
docker-compose rm -fs

echo "building docker containers"
docker-compose up --build -d

docker logs -f flask_app