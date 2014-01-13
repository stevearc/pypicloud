.. _cache:

Caching Backends
================
PyPICloud stores the packages in S3, but S3 doesn't support efficient listing
operations. So instead of hitting S3 every time we need to find a list of
package versions, we store all that metadata in a cache. The cache does not
have to be backed up because it is only a local cache of data that is
permanently stored in S3.

SQLAlchemy
----------
Set ``pypi.access_backend = pypicloud.cache.SQLCache``, or leave it out
completely since this is the default.

``db.url``
~~~~~~~~~~
**Argument:** string

The database url to use for the caching database. Should be a `SQLAlchemy url
<http://docs.sqlalchemy.org/en/rel_0_9/core/engines.html>`_

Redis
-----
Set ``pypi.db = pypicloud.cache.RedisCache``

``db.url``
~~~~~~~~~~
**Argument:** string

The database url to use for the caching database. The format looks like this:
``redis://username:password@localhost:6379/0``
