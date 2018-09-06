#!/bin/bash
set -e

ensure-running() {
  local name="$1"; shift
  local port="$1"; shift
  local image="$1"; shift
  local docker_args=()
  while [ "$1" != "--" ] && [ $# -gt 0 ]; do
    docker_args+=("$1"); shift
  done
  [ "$1" == "--" ] && shift
  local image_args=()
  while [ $# -gt 0 ]; do
    image_args+=("$1"); shift
  done
  if [ "$(docker inspect -f "{{.State.Running}}" "$name" 2> /dev/null)" != "true" ]; then
    docker inspect "$name" >/dev/null 2>&1 && docker rm "$name"
    set -x
    docker run -d --name "$name" -p "${port}:${port}" "${docker_args[@]}" "$image" "${image_args[@]}"
    set +x
    echo "Started $name"
  fi
}

main() {
  if [ "$1" = "clean" ] || [ "$1" = "stop" ]; then
    docker rm -f pypi-redis || :
    docker rm -f pypi-postgres || :
    docker rm -f pypi-mysql || :
    docker rm -f pypi-ldap || :
  else
    ensure-running pypi-redis 6379 redis
    ensure-running pypi-postgres 5432 postgres -e POSTGRES_PASSWORD= -e POSTGRES_DB=postgres
    ensure-running pypi-mysql 3306 mysql -e MYSQL_DATABASE=test -e MYSQL_ALLOW_EMPTY_PASSWORD=yes
    ensure-running pypi-ldap 389 osixia/openldap -v "$(readlink -f ./ldap):/container/service/slapd/assets/config/bootstrap/ldif/custom" -- --loglevel debug --copy-service
  fi
}

main "$@"
