.. _upgrade:

Upgrading
=========
New versions of PyPICloud may require action in up to two locations:

1. The cache database
2. The access control backend

Cache Database
--------------
This storage system is designed to be ephemeral. After an upgrade, all you need
to do is rebuild the cache from the storage backend and that will apply any
schema changes needed. You can use the "rebuild" button in the admin interface,
or you can hit the :ref:`REST endpoint <rest-rebuild>` (note that this will not
work if you have ``db.graceful_reload = true``).

.. _change_access:

Access Control
--------------
If something has changed in the formatting of the access control between
versions, there should be a note inside the changelog. If so, you will need to
export your current data and import it to the new version.

.. code-block:: bash

    $ ppc-export config.ini -o acl.json.gz
    $ pip install --upgrade pypicloud
    $ # Make any necessary changes to the config.ini file
    $ ppc-import config.ini -i acl.json.gz

Note that this system also allows you to migrate your access rules from one
backend to another.

.. code-block:: bash

    $ ppc-export old_config.ini | ppc-import new_config.ini

Changing Storage
----------------
If you would like to change your storage backend, you will need to migrate your
existing packages to the new location. Create a config file that uses the new
storage backend, and then run::

    ppc-migrate old_config.ini new_config.ini

This will find all packages stored in the old storage backend and upload them
to the new storage backend.
