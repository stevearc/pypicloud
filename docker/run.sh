#!/bin/bash -e

run-server() {
    if [ ! -e /etc/pypicloud/config.ini ]; then
        echo "You must create a config.ini file and mount it under /etc/pypicloud/"
        exit 1
    fi
    service nginx start
    /env/bin/uwsgi --die-on-term /etc/pypicloud/config.ini
}

make-config() {
    /env/bin/pypicloud-make-config -p /tmp/out.ini
    echo "----------Config File-----------"
    cat /tmp/out.ini
    echo
}

main() {
    if [ "$1" == "make" ]; then
        make-config
    else
        run-server
    fi
}

main "$@"
