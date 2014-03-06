FROM ubuntu:12.04
MAINTAINER Steven Arcangeli <stevearc@stevearc.com>

# Install packages required
ENV DEBIAN_FRONTEND noninteractive
RUN apt-get update -qq
RUN apt-get install -y python-pip python2.7-dev nginx-full
RUN pip install virtualenv
RUN virtualenv /env
RUN /env/bin/pip install pypicloud uwsgi pastescript redis flywheel

# Get rid of the default nginx site
RUN rm -f /etc/nginx/sites-enabled/default

# Create a working directory for pypicloud
RUN mkdir -p /var/lib/pypicloud

# Add the default nginx site for pypicloud
ADD pypi.nginx /etc/nginx/sites-enabled/pypi

# Add the default config file for pypicloud
ADD config.ini /etc/pypicloud/config.ini

# These volumes allow the nginx and pypicloud configs to be overwritten
VOLUME ["/etc/pypicloud"]
VOLUME ["/etc/nginx/sites-enabled"]

EXPOSE 8080

ADD run.sh /run.sh
ENTRYPOINT ["/run.sh"]
