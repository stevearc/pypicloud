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

``redirect`` - Return a 302 to the package at the ``fallback_base_url``.

``cache`` - Download the package from ``fallback_base_url``, store it in the
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
shown with the versions found at the ``fallback_base_url``.

``pypi.fallback_url``
~~~~~~~~~~~~~~~~~~~~~
| **DEPRECATED** see ``pypi.fallback_base_url``
| **Argument:** string, optional

The index server to handle the behavior defined in ``pypi.fallback`` (default
https://pypi.org/simple)

``pypi.fallback_base_url``
~~~~~~~~~~~~~~~~~~~~~~~~~~
**Argument:** string, optional

This takes precendence over ``pypi.fallback`` by causing redirects to go to:
``pypi.fallback_base_url/<simple|pypi>``. (default https://pypi.org)

``pypi.disallow_fallback``
~~~~~~~~~~~~~~~~~~~~~~~~~~
**Argument:** list, optional

List of packages that should not be fetch from ``pypi.fallback_base_url``.
This is useful if private packages have the same name as a package in
``pypi.fallback_base_url`` and you don't want it to be replaced.

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
packages from ``fallback_base_url``.  (default ['authenticated'])

``pypi.allow_overwrite``
~~~~~~~~~~~~~~~~~~~~~~~~
**Argument:** bool, optional

Allow users to upload packages that will overwrite an existing version (default
False)

``pypi.realm``
~~~~~~~~~~~~~~
**Argument:** string, optional

The HTTP Basic Auth realm (default 'pypi')

``pypi.download_url``
~~~~~~~~~~~~~~~~~~~~~
**Argument:** string, optional

Overide for the root server URL displayed in the banner of the homepage.

``pypi.stream_files``
~~~~~~~~~~~~~~~~~~~~~
**Argument:** bool, optional

Whether or not to stream the raw package data from the storage database,
as opposed to returning a redirect link to the storage database. This is useful
for taking advantage of the local `pip` cache, which caches based on the URL
returned. **Note** that this will in most scenarios make fetching a package slower,
since the server will download the full package data before sending it to the client.

``pypi.package_max_age``
~~~~~~~~~~~~~~~~~~~~~~~~
**Argument:** int, optional

The `max-age` parameter (in seconds) to use in the `Cache-Control` header when downloading packages.
If not set, the default will be `0`, which will tell `pip` not to cache any downloaded packages.
In order to take advantage of the local `pip` cache, you should set this value to a relatively
high number.

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

    $ python -c 'import os, base64; print(base64.b64encode(os.urandom(32)))'

``session.validate_key``
~~~~~~~~~~~~~~~~~~~~~~~~
**Argument:** string

Validation key used to sign the AES encrypted data.

``session.secure``
~~~~~~~~~~~~~~~~~~
**Argument:** bool, optional

If True, only set the session cookie for HTTPS connections (default False).
When running a production server, make sure this is always set to ``true``.
