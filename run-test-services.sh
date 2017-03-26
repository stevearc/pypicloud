#!/bin/bash
set -e

ensure-running() {
  local name="$1"; shift
  local port="$1"; shift
  local image="$1"; shift
  if [ "$(docker inspect -f "{{.State.Running}}" "$name" 2> /dev/null)" != "true" ]; then
    docker inspect "$name" >/dev/null 2>&1 && docker rm "$name"
    set -x
    docker run -d --name "$name" -p "${port}:${port}" $* "$image"
    set +x
    echo "Started $name"
  fi
}

main() {
  if [ "$1" = "clean" ] || [ "$1" = "stop" ]; then
    docker rm -f pypi-redis || :
    docker rm -f pypi-postgres || :
    docker rm -f pypi-mysql || :
  else
    ensure-running pypi-redis 6379 redis
    ensure-running pypi-postgres 5432 postgres -e POSTGRES_PASSWORD= -e POSTGRES_DB=postgres
    ensure-running pypi-mysql 3306 mysql -e MYSQL_DATABASE=test -e MYSQL_ALLOW_EMPTY_PASSWORD=yes
  fi
}

main "$@"
