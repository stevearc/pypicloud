pypicloud
=========

This is a docker container for running pypicloud. To test pypicloud and see it
working, run this command:

```
docker run -p 8080:8080 -name pypi stevearc/pypicloud
```

This will start pypicloud with default settings inside the docker container.
You can visit the site by going to http://localhost:8080. The default settings
are sufficient to play with, but they should not be used in production. The
image ships with a working config file, but you should replace it with your own
before running in production.  See the [list of configuration
options](http://pypicloud.readthedocs.org/en/latest/topics/configuration.html)
for details about the config file.

You can access the `pypicloud-make-config` command by passing `make` in as an
argument to the container:

```
docker run -name pypi -i -t stevearc/pypicloud make
```

The config files in the container are located at `/etc/pypicloud/config.ini`
and `/etc/nginx/sites-enabled/pypi`. To overwrite these, mount a volume with
replacement files. For example, if you have config files on your host located at:

* /var/lib/containers/pypicloud/config/config.ini
* /var/lib/containers/pypicloud/nginx/pypi

The command to run pypicloud would be

```
docker run -p 8080:8080
    -v /var/lib/containers/pypicloud/config:/etc/pypicloud:ro
    -v /var/lib/containers/pypicloud/nginx:/etc/nginx/sites-enabled:ro
    -name pypi stevearc/pypicloud
```
