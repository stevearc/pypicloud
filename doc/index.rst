PyPICloud - PyPI backed by S3 or GCS
====================================
This is an implementation of the PyPI server for hosting your own python
packages. It uses a three layer system for storing and serving files::

  +---------+        +-------+        +-----------+
  | Storage | <----> | Cache | <----> | Pypicloud |
  +---------+        +-------+        +-----------+

The **Storage** layer is where the actual package files will be kept and served
from. This can be S3, GCS, Azure Blob Storage or a directory on the server
running pypicloud.

The **Cache** layer stores information about which packages are in stored in
Storage. This can be DynamoDB, Redis, or any SQL database.

The **Pypicloud** webserver itself is stateless, and you can have any number of
them as long as they use the same Cache. (Scaling beyond a single cache requires
:ref:`some additional work <s3_sync>`.)

Pypicloud is designed to be easy to set up for small deploys, and easy to scale
up when you need it. Go :ref:`get started!<getting_started>`

Code lives here: https://github.com/stevearc/pypicloud

User Guide
----------

.. toctree::
    :maxdepth: 2
    :glob:

    topics/getting_started
    topics/getting_started_advanced
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
