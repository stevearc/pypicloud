PyPI Cloud
==========
:Build: |build|_ |coverage|_
:Documentation: |docs|_
:PyPI: |downloads|_

.. |build| image:: https://travis-ci.org/stevearc/pypicloud.png?branch=master
.. _build: https://travis-ci.org/stevearc/pypicloud
.. |coverage| image:: https://coveralls.io/repos/stevearc/pypicloud/badge.png?branch=master
.. _coverage: https://coveralls.io/r/stevearc/pypicloud?branch=master
.. |docs| image:: https://readthedocs.org/projects/pypicloud/badge/?version=latest
.. _docs: http://pypicloud.readthedocs.org/
.. |downloads| image:: http://pepy.tech/badge/pypicloud
.. _downloads: http://pypi.python.org/pypi/pypicloud

This package is a Pyramid web app that provides a PyPI server where the packages
are stored on Amazon's Simple Storage Service (S3) or Google's Cloud Storage
(GCS).

Quick Start
===========
::

    pip install pypicloud[server]
    pypicloud-make-config -t server.ini
    pserve server.ini

Go to http://localhost:6543/ to view the web interface.

For more detailed step-by-step instructions, check out the `getting started
<http://pypicloud.readthedocs.org/en/latest/topics/getting_started.html>`_
section of the docs.

Docker
------
There is a docker image if you're into that sort of thing:
https://github.com/stevearc/pypicloud-docker
