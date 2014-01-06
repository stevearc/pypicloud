PyPI Cloud
==========
:Build: |build|_ |coverage|_
:Documentation: http://pypicloud.readthedocs.org/en/latest/
:Source: https://github.com/mathcamp/pypicloud

.. |build| image:: https://travis-ci.org/mathcamp/pypicloud.png?branch=master
.. _build: https://travis-ci.org/mathcamp/pypicloud
.. |coverage| image:: https://coveralls.io/repos/mathcamp/pypicloud/badge.png?branch=master
.. _coverage: https://coveralls.io/r/mathcamp/pypicloud?branch=master

This package is a Pyramid app that runs a simple PyPI server where all the
packages are stored on Amazon's Simple Storage Service (S3).

Quick Start
===========
For more detailed step-by-step instructions, check out the `getting started
<http://pypicloud.readthedocs.org/en/latest/topics/getting_started.html>`_
section of the docs.

::

    virtualenv mypypi
    source mypypi/bin/activate
    pip install pypicloud waitress
    pypicloud-make-config -t server.ini
    pserve server.ini

It's running on port 6543! Go to `http://localhost:6543/`_ to view the web interface.
