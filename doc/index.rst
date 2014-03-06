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
    topics/storage
    topics/cache
    topics/access_control
    topics/deploy
    topics/upgrade
    topics/extensions
    topics/api
    topics/developing

Versions
--------
=========  ===============  ========
Version    Build            Coverage
=========  ===============  ========
master_    |build-master|_  |coverage-master|_
0.1.0_     |build-0.1.0|_   |coverage-0.1.0|_
=========  ===============  ========

.. _master: ../latest/
.. |build-master| image:: https://travis-ci.org/mathcamp/pypicloud.png?branch=master
.. _build-master: https://travis-ci.org/mathcamp/pypicloud
.. |coverage-master| image:: https://coveralls.io/repos/mathcamp/pypicloud/badge.png?branch=master
.. _coverage-master: https://coveralls.io/r/mathcamp/pypicloud?branch=master

.. _0.1.0: ../0.1.0/
.. |build-0.1.0| image:: https://travis-ci.org/mathcamp/pypicloud.png?branch=0.1.0
.. _build-0.1.0: https://travis-ci.org/mathcamp/pypicloud
.. |coverage-0.1.0| image:: https://coveralls.io/repos/mathcamp/pypicloud/badge.png?branch=0.1.0
.. _coverage-0.1.0: https://coveralls.io/r/mathcamp/pypicloud?branch=0.1.0

Code lives here: https://github.com/mathcamp/pypicloud

API Reference
-------------
.. toctree::
    :maxdepth: 3
    :glob:

    ref/pypicloud

Changelog
---------

.. toctree::
    :maxdepth: 2
    :glob:

    changes

Indices and tables
------------------

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`
