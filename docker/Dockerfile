FROM ubuntu:20.04
MAINTAINER Steven Arcangeli <stevearc@stevearc.com>

RUN apt-get update -qq \
  && DEBIAN_FRONTEND=noninteractive apt-get install -yqq \
    python3-pip python3-dev libldap2-dev libsasl2-dev \
    libmysqlclient-dev libffi-dev libssl-dev default-jre curl git \
  && pip3 install --upgrade pip \
  && pip3 install --upgrade setuptools tox
RUN curl https://raw.githubusercontent.com/fkrull/docker-multi-python/master/setup.sh -o /setup.sh \
  && bash setup.sh \
  && rm /setup.sh
