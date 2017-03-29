PyPI Cloud
==========
:Build: |build|_ |coverage|_
:Documentation: http://pypicloud.readthedocs.org/
:Downloads: http://pypi.python.org/pypi/pypicloud
:Source: https://github.com/stevearc/pypicloud

.. |build| image:: https://travis-ci.org/stevearc/pypicloud.png?branch=master
.. _build: https://travis-ci.org/stevearc/pypicloud
.. |coverage| image:: https://coveralls.io/repos/stevearc/pypicloud/badge.png?branch=master
.. _coverage: https://coveralls.io/r/stevearc/pypicloud?branch=master

This package is a Pyramid app that runs a simple PyPI server where all the
packages are stored on Amazon's Simple Storage Service (S3) or Google Cloud Storage (GCS).

GCS backend requires gcs-oauth2-boto-plugin and a .boto configuration file.

`LIVE DEMO <http://pypi.stevearc.com>`_

Quick Start
===========
For more detailed step-by-step instructions, check out the `getting started
<http://pypicloud.readthedocs.org/en/latest/topics/getting_started.html>`_
section of the docs.

::

    virtualenv mypypi
    source mypypi/bin/activate
    pip install pypicloud[server]
    pypicloud-make-config -t server.ini
    pserve server.ini

It's running! Go to http://localhost:6543/ to view the web interface.

Docker
------
There is a docker image if you're into that sort of thing. You can find it at:
https://github.com/stevearc/pypicloud-docker
