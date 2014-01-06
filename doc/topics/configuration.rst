Configuration Options
=====================
This is an exhaustive list of every configuration parameter for pypicloud

AWS
^^^

``aws.access_key``, ``aws.secret_key``
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
**Argument:** string

Your AWS access key id and secret access key. If they are not specified then
pypicloud will attempt to get the values from the environment variables
``AWS_ACCESS_KEY_ID`` and ``AWS_SECRET_ACCESS_KEY``.

``aws.bucket``
~~~~~~~~~~~~~~
**Argument:** string

The name of the S3 bucket to store package in. Note: your bucket must not have
"." in it. Amazon's SSL certificate for S3 urls is only valid for
\*.s3.amazonaws.com

``aws.prefix``
~~~~~~~~~~~~~~
**Argument:** string, optional
If present, all packages will be prefixed with this value when stored in S3.
Use this to store your packages in a subdirectory, such as "packages/"

``aws.expire_after``
~~~~~~~~~~~~~~~~~~~~
**Argument:** int, optional

How long the generated S3 urls are valid for (default 86400 (1 day)). In
practice, there is no real reason why these generated urls need to expire at
all. S3 does it for security, but expiring links isn't part of the python
package security model. So in theory you can bump this number up a bunch.

``aws.buffer_time``
~~~~~~~~~~~~~~~~~~~
**Argument:** int, optional

Regenerate our S3 urls this long before they actually expire (default 600 (10
minutes)). This will help guarantee that if pip pulls down a url, it will be
valid long enough for it to finish downloading the package.

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
~~~~~~~~~~~~~~~~~~~~~~~
**Argument:** string

Validation key used to sign the AES encrypted data.

``session.secure``
~~~~~~~~~~~~~~~~~~~~~~~
**Argument:** bool, optional

If True, only set the session cookie for HTTPS connections (default False).
When running a production server, make sure this is always set to ``true``.

PyPICloud
^^^^^^^^^

``pypi.db.url``
~~~~~~~~~~~~~~~
**Argument:** string

The database url to use for the caching database. May be a `SQLAlchemy url
<http://docs.sqlalchemy.org/en/rel_0_9/core/engines.html>`_, or a redis url.
Redis urls look like ``redis://username:password@localhost:6379/0``

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

``pypi.prepend_hash``
~~~~~~~~~~~~~~~~~~~~~
**Argument:** bool, optional

Prepend a 4-letter hash to all S3 keys (default True). This helps S3 load
balance when traffic scales. See the `AWS documentation
<http://docs.aws.amazon.com/AmazonS3/latest/dev/request-rate-perf-considerations.html>`_
on the subject.

``pypi.allow_overwrite``
~~~~~~~~~~~~~~~~~~~~~~~~
**Argument:** bool, optional

Allow users to upload packages that will overwrite an existing version (default
False)

.. _access_control_config:

Access Control
^^^^^^^^^^^^^^

``user.<username>``
~~~~~~~~~~~~~~~~~~~
**Argument:** string

Defines a single user login. You may specify any number of users in the file.
Use ``pypicloud-gen-password`` to create the password hashes.

``package.<package>.owner``
~~~~~~~~~~~~~~~~~~~~~~~~~~~
**Argument:** string

Define the owner of a package. The value should be a username set in a
``user.<username>`` field. Package owners always have read/write access to the
package.

``package.<package>.group.<group>``
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
**Argument:** {``r``, ``rw``}

Give read or read/write access on a package to a group of users. The group must
be defined in a ``group.<group>`` field. There are two special-case group
names. If you use ``everyone``, it will give that permission to all users; even
those not logged-in. If you use ``authenticated``, it will give that permission
to any user defined in the config file.

``pypi.admins``
~~~~~~~~~~~~~~~
**Argument:** list

Whitespace-delimited list of users with admin privileges. Admins have
read/write access to all packages, and can perform maintenance tasks.

``group.<group>``
~~~~~~~~~~~~~~~~~
**Argument:** list

Whitespace-delimited list of users that belong to this group. Groups can have
separately-defined read/write permissions on packages.

``pypi.zero_security_mode``
~~~~~~~~~~~~~~~~~~~~~~~~~~~
**Argument:** bool, optional

Run in a special, limited access-control mode. Any user with valid credentials
can upload any package. Everyone (even not-logged-in users) can view and
download all packages. (default False)
