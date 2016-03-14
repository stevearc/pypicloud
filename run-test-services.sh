#!/bin/bash
set -e

docker run --name pypicloud-postgres -p 5432:5432 -d postgres
docker run --name pypicloud-redis -p 6379:6379 -d redis
docker run --name pypicloud-mysql -p 3306:3306 -e MYSQL_ROOT_PASSWORD= -e MYSQL_DATABASE=test -e MYSQL_ALLOW_EMPTY_PASSWORD=yes -d mysql
