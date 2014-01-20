Configuration Options
=====================
This is an exhaustive list of every configuration parameter for pypicloud

PyPICloud
^^^^^^^^^

.. _use_fallback:

``pypi.use_fallback``
~~~~~~~~~~~~~~~~~~~~~
**Argument:** bool, optional

If a requested package is not found in PyPICloud, forward the request to
another index server (default True)

``pypi.fallback_url``
~~~~~~~~~~~~~~~~~~~~~
**Argument:** string, optional

The index server to forward missing requests to (default
http://pypi.python.org/simple)

``pypi.realm``
~~~~~~~~~~~~~~
**Argument:** string, optional

The HTTP Basic Auth realm (default 'pypi')

``pypi.allow_overwrite``
~~~~~~~~~~~~~~~~~~~~~~~~
**Argument:** bool, optional

Allow users to upload packages that will overwrite an existing version (default
False)


Storage
^^^^^^^
``pypi.storage``
~~~~~~~~~~~~~~~~
**Argument:** string, optional

A dotted path to a subclass of :class:`~pypicloud.storage.IStorage`. The
default is :class:`~pypicloud.storage.FileStorage`. Each storage option may
have additional configuration options. Documentation for the built-in storage
backends can be found at :ref:`storage`.


Cache
^^^^^
``pypi.db``
~~~~~~~~~~~~~~~
**Argument:** string, optional

A dotted path to a subclass of :class:`~pypicloud.cache.ICache`. The
default is :class:`~pypicloud.cache.SQLCache`. Each cache option
may have additional configuration options. Documentation for the built-in
cache backends can be found at :ref:`cache`.

Access Control
^^^^^^^^^^^^^^

``pypi.access_backend``
~~~~~~~~~~~~~~~~~~~~~~~
**Argument:** string, optional

A dotted path to a subclass of :class:`~pypicloud.access.IAccessBackend`. The
default is :class:`~pypicloud.access.ConfigAccessBackend`. Each backend option
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
~~~~~~~~~~~~~~~~~~~~~~~
**Argument:** bool, optional

If True, only set the session cookie for HTTPS connections (default False).
When running a production server, make sure this is always set to ``true``.
