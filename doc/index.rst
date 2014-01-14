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

API Reference
-------------
.. toctree::
    :maxdepth: 3
    :glob:

    ref/pypicloud

Indices and tables
==================

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`

TODO
====
* Users can edit password (w/mutable access backend)
* Store user/group configuration in S3/Dynamo?
* Cache more metadata for display (last updated, most recent version)
* Support CloudFront
* Release to pypi

* Auto-archive to glacier after X days or X versions
* Directives for cloning parts of pypi (from requirements file or package deps, how to handle permissions?)
