.. _cache:

Caching Backends
================
PyPICloud stores the packages in a storage backend (typically S3), but that backend
is not necessarily efficient for frequently reading metadata. So instead of
hitting S3 every time we need to find a list of package versions, we store all
that metadata in a cache. The cache does not have to be backed up because it is
only a local cache of data that is permanently stored in the storage backend.

SQLAlchemy
----------
Set ``pypi.db = sql`` OR ``pypi.db = pypicloud.cache.SQLCache`` OR leave it out
completely since this is the default.

``db.url``
~~~~~~~~~~
**Argument:** string

The database url to use for the caching database. Should be a `SQLAlchemy url
<http://docs.sqlalchemy.org/en/rel_0_9/core/engines.html>`_

* sqlite: ``sqlite:///%(here)s/db.sqlite``
* mysql: ``mysql://root@127.0.0.1:3306/pypi?charset=utf8mb4``
* postgres: ``postgresql://postgres@127.0.0.1:5432/postgres``

.. warning::

  You must specify the ``charset=`` parameter if you're using MySQL, otherwise
  it will choke on unicode package names. If you're using 5.5.3 or greater you
  can specify the ``utf8mb4`` charset, otherwise use ``utf8``.

``db.graceful_reload``
~~~~~~~~~~~~~~~~~~~~~~
**Argument:** bool, optional

When reloading the cache from storage, keep the cache in a usable state while
adding and removing the necessary packages. Note that this may take longer
because multiple passes will be made to ensure correctness. (default ``False``)

Redis
-----
Set ``pypi.db = redis`` OR ``pypi.db = pypicloud.cache.RedisCache``

You will need to ``pip install redis`` before running the server.

``db.url``
~~~~~~~~~~
**Argument:** string

The database url to use for the caching database. The format looks like this:
``redis://username:password@localhost:6379/0``

``db.graceful_reload``
~~~~~~~~~~~~~~~~~~~~~~
**Argument:** bool, optional

When reloading the cache from storage, keep the cache in a usable state while
adding and removing the necessary packages. Note that this may take longer
because multiple passes will be made to ensure correctness. (default ``False``)

DynamoDB
--------
Set ``pypi.db = dynamo`` OR ``pypi.db = pypicloud.cache.dynamo.DynamoCache``

.. note::

  Make sure to ``pip install pypicloud[dynamo]`` before running the server to
  install the necessary DynamoDB libraries. Also, be sure you have set the
  correct :ref:`dynamodb_policy`.

.. note::

   Pypicloud will create the DynamoDB tables if none exist. By default the
   tables will be named ``pypicloud-DynamoPackage`` and
   ``pypicloud-PackageSummary`` (this can be configured with ``db.namespace``
   and ``db.tablenames``). You may create and configure these tables yourself as
   long as they have the same schema.

.. warning::

   When you reload the cache from the admin interface, the default behavior will
   drop the DynamoDB tables and re-create them. If you have configured the
   tables to have server-side encryption, or customized the throughput, you may
   find this undesirable. To avoid this, set ``db.graceful_reload = true``

``db.region_name``
~~~~~~~~~~~~~~~~~~
**Argument:** string

The AWS region to use for the cache tables.

.. _dynamo_credentials:

``db.aws_access_key_id``, ``db.aws_secret_access_key``
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
**Argument:** string, optional

Your AWS access key id and secret access key. If they are not specified then
pypicloud will attempt to get the values from the environment variables
``AWS_ACCESS_KEY_ID`` and ``AWS_SECRET_ACCESS_KEY`` or any other `credentials
source
<http://boto3.readthedocs.io/en/latest/guide/configuration.html#configuring-credentials>`__.

``db.namespace``
~~~~~~~~~~~~~~~~
**Argument:** string, optional

If specified, all of the created Dynamo tables will have this as a prefix in
their name. Useful to avoid name collisions.

``db.tablenames``
~~~~~~~~~~~~~~~~~
**Argument:** list<string>, optional

If specified, these will be the names of the two DynamoDB tables. Must be a
2-element whitespace-delimited list. Note that these names will still be
prefixed by the ``db.namespace``. (default ``DynamoPackage PackageSummary``)

``db.host``
~~~~~~~~~~~
**Argument:** string, optional

The hostname to connect to. This is normally used to connect to a DynamoDB
Local instance.

``db.port``
~~~~~~~~~~~
**Argument:** int, optional

The port to connect to when using ``db.host`` (default 8000)

``db.secure``
~~~~~~~~~~~~~
**Argument:** bool, optional

Force https connection when using ``db.host`` (default False)

``db.graceful_reload``
~~~~~~~~~~~~~~~~~~~~~~
**Argument:** bool, optional

When reloading the cache from storage, keep the cache in a usable state while
adding and removing the necessary packages. Note that this may take longer
because multiple passes will be made to ensure correctness. (default ``False``)
