PyPI Cloud
==========
:Master Build: |build|_ |coverage|_
:0.1 Build: |build-0.1|_ |coverage-0.1|_
:Documentation: http://pypicloud.readthedocs.org/
:Downloads: http://pypi.python.org/pypi/pypicloud
:Source: https://github.com/mathcamp/pypicloud

.. |build| image:: https://travis-ci.org/mathcamp/pypicloud.png?branch=master
.. _build: https://travis-ci.org/mathcamp/pypicloud
.. |coverage| image:: https://coveralls.io/repos/mathcamp/pypicloud/badge.png?branch=master
.. _coverage: https://coveralls.io/r/mathcamp/pypicloud?branch=master

.. |build-0.1| image:: https://travis-ci.org/mathcamp/pypicloud.png?branch=0.1
.. _build-0.1: https://travis-ci.org/mathcamp/pypicloud
.. |coverage-0.1| image:: https://coveralls.io/repos/mathcamp/pypicloud/badge.png?branch=0.1
.. _coverage-0.1: https://coveralls.io/r/mathcamp/pypicloud?branch=0.1

This package is a Pyramid app that runs a simple PyPI server where all the
packages are stored on Amazon's Simple Storage Service (S3).

`LIVE DEMO <http://pypi.stevearc.com>`_

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

It's running! Go to http://localhost:6543/ to view the web interface.
