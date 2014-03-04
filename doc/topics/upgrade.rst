.. _upgrade:

Upgrading
=========
New versions of PyPICloud may require schema changes in up to two locations:

1. The cache database
2. The access control backend

Cache Database
--------------
This storage system is designed to be ephemeral. After an upgrade, all you need
to do is rebuild the cache from the storage backend and that will apply any
schema changes needed. You can use the "rebuild" button in the admin interface,
or you can hit the :ref:`REST endpoint <rest-rebuild>`.

Access Control
--------------
TODO: (stevearc 2014-03-03) add migration support

Migrating Packages
==================
If you would like to change your storage backend, you will need to migrate your
existing packages to the new location. Create a config file that uses the new
storage backend, and then run::

    pypi-migrate-packages old_config.ini new_config.ini

This will find all packages stored in the old storage backend and upload them
to the new storage backend.
