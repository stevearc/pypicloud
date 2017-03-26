PyPICloud - PyPI backed by S3
=============================
This is an implementation of the PyPI server for hosting your own python
packages. It stores the packages in S3 and dynamically generates links to them
for pip.

After generating the S3 urls, pypicloud caches them in a database. Subsequent
requests to download packages will use the already-generated urls in the db.
Pypicloud supports using SQLAlchemy, Redis, or DynamoDB as the cache.

Pypicloud was designed to be fast and easy to replace in the case of server
failure. Simply copy your config.ini file to a new server and run pypicloud
there. The only data that needs to be persisted is in S3, which handles the
redundancy requirements for you.

Code lives here: https://github.com/stevearc/pypicloud

User Guide
----------

.. toctree::
    :maxdepth: 2
    :glob:

    topics/getting_started
    topics/configuration
    topics/storage
    topics/cache
    topics/access_control
    topics/deploy
    topics/upgrade
    topics/extensions
    topics/api
    topics/developing
    changes

API Reference
-------------
.. toctree::
    :maxdepth: 3
    :glob:

    ref/pypicloud

Indices and tables
------------------

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`
