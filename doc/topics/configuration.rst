Configuration Options
=====================
This is a list of all configuration parameters for pypicloud

PyPICloud
^^^^^^^^^

.. _fallback:

``pypi.fallback``
~~~~~~~~~~~~~~~~~
**Argument:** {'redirect', 'cache', 'none'}, optional

This option defines what the behavior is when a requested package is not found
in the database. (default 'redirect')

``redirect`` - Return a 302 to the package at the ``fallback_url``.

``cache`` - Download the package from ``fallback_url``, store it in the
backend, and serve it. User must have ``cache_update`` permissions.

``none`` - Return a 404

See also :ref:`always_show_upstream` below.

See :ref:`fallback_detail` for more detail on exactly how each fallback option will
function.

.. _always_show_upstream:

``pypi.always_show_upstream``
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
**Argument:** bool, optional

Default ``False``.

This adjusts the fallback behavior when one or more versions of the requested
package are stored in pypicloud. If ``False``, pypicloud will only show the
client the versions that are stored. If ``True``, the local versions will be
shown with the versions found at the ``fallback_url``.

``pypi.fallback_url``
~~~~~~~~~~~~~~~~~~~~~
**Argument:** string, optional

The index server to handle the behavior defined in ``pypi.fallback`` (default
https://pypi.python.org/simple)

``pypi.default_read``
~~~~~~~~~~~~~~~~~~~~~
**Argument:** list, optional

List of groups that are allowed to read packages that have no explicit user or
group permissions (default ['authenticated'])

``pypi.default_write``
~~~~~~~~~~~~~~~~~~~~~~
**Argument:** list, optional

List of groups that are allowed to write packages that have no explicit user or
group permissions (default no groups, only admin users)

``pypi.cache_update``
~~~~~~~~~~~~~~~~~~~~~
**Argument:** list, optional

Only used when ``pypi.fallback = cache``. This is
the list of groups that are allowed to trigger the operation that fetches
packages from ``fallback_url``.  (default ['authenticated'])

``pypi.allow_overwrite``
~~~~~~~~~~~~~~~~~~~~~~~~
**Argument:** bool, optional

Allow users to upload packages that will overwrite an existing version (default
False)

``pypi.realm``
~~~~~~~~~~~~~~
**Argument:** string, optional

The HTTP Basic Auth realm (default 'pypi')

``pypi.use_fallback`` (deprecated)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
**Argument:** bool, optional

Replaced by ``pypi.fallback``. Setting to ``True`` has no effect. Setting to
``False`` will set ``pypi.fallback = none``.

Storage
^^^^^^^
``pypi.storage``
~~~~~~~~~~~~~~~~
**Argument:** string, optional

A dotted path to a subclass of :class:`~pypicloud.storage.base.IStorage`. The
default is :class:`~pypicloud.storage.files.FileStorage`. Each storage option may
have additional configuration options. Documentation for the built-in storage
backends can be found at :ref:`storage`.


Cache
^^^^^
``pypi.db``
~~~~~~~~~~~
**Argument:** string, optional

A dotted path to a subclass of :class:`~pypicloud.cache.base.ICache`. The
default is :class:`~pypicloud.cache.sql.SQLCache`. Each cache option
may have additional configuration options. Documentation for the built-in
cache backends can be found at :ref:`cache`.

Access Control
^^^^^^^^^^^^^^

``pypi.auth``
~~~~~~~~~~~~~
**Argument:** string, optional

A dotted path to a subclass of :class:`~pypicloud.access.base.IAccessBackend`. The
default is :class:`~pypicloud.access.config.ConfigAccessBackend`. Each backend option
may have additional configuration options. Documentation for the built-in
backends can be found at :ref:`access_control`.

Beaker
^^^^^^
Beaker is the session manager that handles user auth for the web interface.
There are many configuration options, but these are the only ones you need to
know about.

``session.encrypt_key``
~~~~~~~~~~~~~~~~~~~~~~~
**Argument:** string

Encryption key to use for the AES cipher. Here is a reasonable way to generate one:

.. code-block:: bash

    $ python -c 'import os, base64; print base64.b64encode(os.urandom(32))'

``session.validate_key``
~~~~~~~~~~~~~~~~~~~~~~~~
**Argument:** string

Validation key used to sign the AES encrypted data.

``session.secure``
~~~~~~~~~~~~~~~~~~
**Argument:** bool, optional

If True, only set the session cookie for HTTPS connections (default False).
When running a production server, make sure this is always set to ``true``.
