PyPICloud - PyPI backed by S3
=============================
This is an implementation of the PyPI server for hosting your own python
packages. It stores the packages in S3 and dynamically generates links to them
for pip.

After generating the S3 urls, pypicloud caches them in a database. Subsequent
requests to download packages will use the already-generated urls in the db.
Pypicloud supports using SQLAlchemy or Redis as the cache.

Pypicloud was designed to be fast and easy to replace in the case of server
failure. Simply copy your config.ini file to a new server and run pypicloud
there. The only data that needs to be persisted is in S3, which handles the
redundancy requirements for you.

User Guide
----------

.. toctree::
    :maxdepth: 2
    :glob:

    topics/getting_started
    topics/configuration
    topics/access_control
    topics/cache
    topics/deploy
    topics/developing

Versions
--------
=========  ===============  ========
Version    Build            Coverage
=========  ===============  ========
master_    |build-master|_  |coverage-master|_
=========  ===============  ========

.. _master: ../latest/
.. |build-master| image:: https://travis-ci.org/mathcamp/pypicloud.png?branch=master
.. _build-master: https://travis-ci.org/mathcamp/pypicloud
.. |coverage-master| image:: https://coveralls.io/repos/mathcamp/pypicloud/badge.png?branch=master
.. _coverage-master: https://coveralls.io/r/mathcamp/pypicloud?branch=master

API Reference
-------------
.. toctree::
    :maxdepth: 3
    :glob:

    ref/pypicloud

Changelog
---------

.. toctree::
    :maxdepth: 1
    :glob:

    changes

Indices and tables
------------------

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`

TODO
----
* Auto-rebuild cache from S3 if empty
* More test coverage
* Document HTTP API
* Release to pypi

* Support CloudFront
* Access backend that stores data in DynamoDB
* Auto-archive to glacier after X days or X versions
* Directives for cloning parts of pypi (from requirements file or package deps, how to handle permissions?)
* Hooks for using celery to make a write-through cache
* Optional captcha on user registration
