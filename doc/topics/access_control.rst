.. _access_control:

Access Control
==============
PyPICloud has a complete access control system that allows you to fine-tune who
has access to your packages. There are several choices for where to store your
user credentials and access rules.

If you ever need to change your access backend, or you want to back up your
current state, check out the :ref:`import/export <change_access>` functionality.

If you want an in-depth look at your options for managing users, see the
:ref:`user_management` section.

Users and Groups
----------------
The access control uses a combination of users and groups. A group is a list of
users. There are also *admin* users, who always have read/write permissions for
everything, and can do a few special operations besides. There are two special
groups:

* ``everyone`` - This group refers to any anonymous user making a request
* ``authenticated`` - This group refers to all logged-in users

You will never need to specify the members of these groups, as membership is
automatic.

.. _config_access_control:

Config File
-----------
The simplest access control available (which is the default) pulls user, group,
and package permission information directly from the config file.

Here is a sample configuration to get you started:

.. code-block:: ini

    # USERS
    # user: stevearc, pass: gunface
    user.stevearc = $5$rounds=80000$yiWi67QBJLDTvbI/$d6qIG/bIoM3hp0lxH8v/vzxg8Qc4CJbxbxiUH4MlnE7
    # user: dsa, pass: paranoia
    user.dsa = $5$rounds=80000$U/lot7eW6gFvuvna$KDyrQvi40XXWzMRkBq1Z/0odJEXzqUVNaPIArL/W0s6
    # user: donlan, pass: osptony
    user.donlan = $5$rounds=80000$Qjz9eRNXrybydMz.$PoD.5vAR9Z2IYlOCPYbza1cKvQ.8kuz1cP0zKl314g0

    # GROUPS
    group.sharkfest =
        stevearc
        dsa
    group.brotatos =
        donlan
        dsa

    # PACKAGES
    package.django_unchained.user.stevearc = rw
    package.django_unchained.group.sharkfest = rw

    package.polite_requests.user.dsa = rw
    package.polite_requests.group.authenticated = r
    package.polite_requests.group.brotatos = rw

    package.pyramid_head.group.brotatos = rw
    package.pyramid_head.group.everyone = r


Here is a table that describes who has what permissions on these packages. Note
that if the entry is ``none``, that user will not even see the package listed,
depending on your ``pypi.default_read`` and ``pypi.default_write`` settings.

========  ================  =================  =============
User      django_unchained  polite_requests    pyramid_head
========  ================  =================  =============
stevearc  rw (user)         r (authenticated)  r (everyone)
dsa       rw (sharkfest)    rw (user)          rw (brotatos)
donlan    none              rw (brotatos)      rw (brotatos)
everyone  none              none               r (everyone)
========  ================  =================  =============


.. _config_file:

Configuration
^^^^^^^^^^^^^

Set ``pypi.auth = config`` OR ``pypi.auth =
pypicloud.access.ConfigAccessBackend`` OR leave it out completely since this is
the default.

.. _auth_scheme:

``auth.scheme``
~~~~~~~~~~~~~~~
**Argument:** str, optional

The default password hash to use. See the passlib docs for `choosing a hash
<https://passlib.readthedocs.io/en/stable/narr/quickstart.html>`__.  Defaults to
``sha512_crypt`` on 64 bit systems and ``sha256_crypt`` on 32 bit systems.

Note this only matters for auth backends that allow dynamic user registration.
If you are generating hashes for your config file with
``pypicloud-gen-password``, you can configure this with the ``-s`` argument.

.. _auth_rounds:

``auth.rounds``
~~~~~~~~~~~~~~~
**Argument:** int, optional

The number of rounds to use when hashing passwords. See PassLib's docs on
`choosing rounds values
<http://passlib.readthedocs.io/en/stable/narr/hash-tutorial.html#choosing-the-right-rounds-value>`__.
The default rounds chosen by pypicloud are *significantly lower* than PassLib
recommends; see :ref:`passlib` for why.

Note this only matters for auth backends that allow dynamic user registration.
If you are generating hashes for your config file with
``pypicloud-gen-password``, you can configure this with the ``-r`` argument.

``user.<username>``
~~~~~~~~~~~~~~~~~~~
**Argument:** string

Defines a single user login. You may specify any number of users in the file.
Use ``ppc-gen-password`` to create the password hashes.

``package.<package>.user.<user>``
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
**Argument:** {``r``, ``rw``}

Give read or read/write access on a package to a single user.

``package.<package>.group.<group>``
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
**Argument:** {``r``, ``rw``}

Give read or read/write access on a package to a group of users. The group must
be defined in a ``group.<group>`` field.

``auth.admins``
~~~~~~~~~~~~~~~
**Argument:** list

Whitespace-delimited list of users with admin privileges. Admins have
read/write access to all packages, and can perform maintenance tasks.

``group.<group>``
~~~~~~~~~~~~~~~~~
**Argument:** list

Whitespace-delimited list of users that belong to this group. Groups can have
separately-defined read/write permissions on packages.

SQL Database
------------
You can opt to store all user and group permissions inside a SQL database. The
advantages are that you can dynamically change these permissions using the web
interface. The disadvantages are that this information is not stored anywhere
else, so unlike the :ref:`cache database <cache>`, it actually needs to be
backed up. There is an import/export command :ref:`that makes this easy
<upgrade>`.

After you set up a new server using this backend, you will need to use the web
interface to create the initial admin user.

Configuration
^^^^^^^^^^^^^
Set ``pypi.auth = sql`` OR ``pypi.auth =
pypicloud.access.sql.SQLAccessBackend``

The SQLite engine is constructed by calling `engine_from_config
<http://docs.sqlalchemy.org/en/latest/core/engines.html#sqlalchemy.engine_from_config>`_
with the prefix ``auth.db.``, so you can pass in any valid parameters that way.

``auth.db.url``
~~~~~~~~~~~~~~~
**Argument:** string

The database url to use for storing user and group permissions. This may be the
same database as ``db.url`` (if you are also using the SQL caching database).

``auth.rounds``
~~~~~~~~~~~~~~~
**Argument:** int, optional

The number of rounds to use when hashing passwords. See :ref:`auth_rounds`

``auth.signing_key``
~~~~~~~~~~~~~~~~~~~~
**Argument:** string, optional

Encryption key to use for the token signing HMAC. You may also pass this in with
the environment variable ``PPC_AUTH_SIGNING_KEY``. Here is a reasonable way to
generate a random key:

.. code-block:: bash

    $ python -c 'import os, base64; print(base64.b64encode(os.urandom(32)))'

For more about generating and using tokens, see :ref:`token_registration`.
Changing this value will retroactively apply to tokens issued in the past.

.. _auth.token_expire:

``auth.token_expire``
~~~~~~~~~~~~~~~~~~~~~
**Argument:** number, optional

How long (in seconds) the generated registration tokens will be valid for
(default one week).

.. _ldap_config:

LDAP Authentication
-------------------
You can opt to authenticate all users through a remote LDAP or compatible
server. There is aggressive caching in the LDAP backend in order to keep
chatter with your LDAP server at a minimum. If you experience a change in your
LDAP layout, group modifications etc, restart your pypicloud process.

Note that you will need to ``pip install pypicloud[ldap]`` OR
``pip install -e .[ldap]`` (from source) in order to get the dependencies for
the LDAP authentication backend.

At the moment there is no way for pypicloud to discern groups from LDAP, so it
only has the built-in ``admin``, ``authenticated``, and ``everyone`` as the
available groups. All authorization is configured using ``pypi.default_read``,
``pypi.default_write``, and ``pypi.cache_update``. If you need to use groups,
you can use the :ref:`auth.ldap.fallback <auth_ldap_fallback>` setting below.

Configuration
^^^^^^^^^^^^^
Set ``pypi.auth = ldap`` OR ``pypi.auth =
pypicloud.access.ldap_.LDAPAccessBackend``

``auth.ldap.url``
~~~~~~~~~~~~~~~~~
**Argument:** string

The LDAP url to use for remote verification. It should include the protocol and
port, as an example: ``ldap://10.0.0.1:389``

``auth.ldap.service_dn``
~~~~~~~~~~~~~~~~~~~~~~~~
**Argument:** string, optional

The FQDN of the LDAP service account used. A service account is required to
perform the initial bind with. It only requires read access to your LDAP. If not
specified an anonymous bind will be used.

``auth.ldap.service_password``
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
**Argument:** string, optional

The password for the LDAP service account.

``auth.ldap.service_username``
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
**Argument:** string, optional

If provided, this will allow allow you to log in to the pypicloud interface as
the provided ``service_dn`` using this username. This account will have admin
privileges.

``auth.ldap.user_dn_format``
~~~~~~~~~~~~~~~~~~~~~~~~~~~~
**Argument:** string, optional

This is used to find a user when they attempt to log in. If the username is part
of the DN, then you can provide this templated string where ``{username}`` will
be replaced with the searched username. For example, if your LDAP directory
looks like this::

  dn: CN=bob,OU=users
  cn: bob
  -

Then you could use the setting ``auth.ldap.user_dn_format =
CN={username},OU=users``.

This option is the preferred method if possible because you can provide the full
DN when doing the search, which is more efficient. If your directory is not in
this format, you will need to instead use ``base_dn`` and
``user_search_filter``.

``auth.ldap.base_dn``
~~~~~~~~~~~~~~~~~~~~~
**Argument:** string, optional

The base DN under which all of your user accounts are organized in LDAP. Used
in combination with the ``user_search_filter`` to find users. See also:
``user_dn_format``.

``base_dn`` and ``user_search_filter`` should be used if your directory format
does not put the username in the DN of the user entry. For example::

  dn: CN=Robert Paulson,OU=users
  cn: Robert Paulson
  unixname: bob
  -

For that directory structure, you would use the following settings:

.. code-block:: ini

    auth.ldap.base_dn = OU=users
    auth.ldap.user_search_filter = (unixname={username})

``auth.ldap.user_search_filter``
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
**Argument:** string, optional

An LDAP search filter, which when used with the ``base_dn`` results a user entry.
The string ``{username}`` will be replaced with the username being searched for.
For example, ``(cn={username})`` or ``(&(objectClass=person)(name={username}))``

Note that the result of the search must be exactly one entry.

``auth.ldap.admin_field``
~~~~~~~~~~~~~~~~~~~~~~~~~
**Argument:** string, optional

When fetching the user entry, check to see if the ``admin_field`` attribute
contains any of ``admin_value``. If so, the user is an admin. This will
typically be used with the `memberOf overlay
<https://www.openldap.org/doc/admin24/overlays.html#Reverse%20Group%20Membership%20Maintenance>`__.

For example, if this is your LDAP directory::

  dn: uid=user1,ou=test
  cn: user1
  objectClass: posixAccount

  dn: cn=pypicloud_admin,dc=example,dc=org
  objectClass: groupOfUniqueNames
  uniqueMember: uid=user1,ou=test


You would use these settings:

.. code-block:: ini

    auth.ldap.admin_field = uniqueMemberOf
    auth.ldap.admin_value = cn=pypicloud_admin,dc=example,dc=org

Since the logic is just checking the value of an attribute, you could also use
``admin_value`` to specify the usernames of admins:

.. code-block:: ini

    auth.ldap.admin_field = cn
    auth.ldap.admin_value =
      user1
      user2

``auth.ldap.admin_value``
~~~~~~~~~~~~~~~~~~~~~~~~~
**Argument:** string, optional

See ``admin_field``


``auth.ldap.admin_group_dn``
~~~~~~~~~~~~~~~~~~~~~~~~~~~~
**Argument:** string, optional

An alternative to using ``admin_field`` and ``admin_value``. If you don't have
access to the ``memberOf`` overlay, you can provide ``admin_group_dn``. When a
user is looked up, pypicloud will search this group to see if the user is a
member.

Note that to use this setting you must also use ``user_dn_format``.


``auth.ldap.cache_time``
~~~~~~~~~~~~~~~~~~~~~~~~
**Argument:** int, optional

When a user entry is pulled via searching with ``base_dn`` and
``user_search_filter``, pypicloud will cache that entry to decrease load on your
LDAP server. This value determines how long (in seconds) to cache the user
entries for.

The default behavior is to cache users forever (clearing the cache requires a
server restart).

``auth.ldap.ignore_cert``
~~~~~~~~~~~~~~~~~~~~~~~~~
**Argument:** bool, optional

If true then the ldap option to not verify the certificate is used. This is not
recommended but useful if the cert name does not match the fqdn. Default is false.

``auth.ldap.ignore_referrals``
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
**Argument:** bool, optional

If true then the ldap option to not follow referrals is used. This is not
recommended but useful if the referred servers does not work. Default is false.

``auth.ldap.ignore_multiple_results``
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
**Argument:** bool, optional

If true then the a warning is issued if multiple users are found. This is not
recommended but useful if there are more than user matching a given search criteria.
Default is false.

.. _auth_ldap_fallback:

``auth.ldap.fallback``
~~~~~~~~~~~~~~~~~~~~~~
**Argument:** string, optional

Since we do not support configuring groups or package permissions via LDAP, this
setting allows you to use another system on top of LDAP for that purpose. LDAP
will be used for user login and to determine admin status, but this other access
backend will be used to determine group membership and package permissions.

Currently the only value supported is ``config``, which will use the
:ref:`Config File <config_access_control>` values.

AWS Secrets Manager
-------------------
This stores all the user data in a single JSON blob using AWS Secrets Manager.

After you set up a new server using this backend, you will need to use the web
interface to create the initial admin user.

Configuration
^^^^^^^^^^^^^
Set ``pypi.auth = aws_secrets_manager`` OR ``pypi.auth =
pypicloud.access.aws_secrets_manager.AWSSecretsManagerAccessBackend``

The JSON format should look like this:

.. code-block:: javascript

    {
        "users": {
            "user1": "hashed_password1",
            "user2": "hashed_password2",
            "user3": "hashed_password3",
            "user4": "hashed_password4",
            "user5": "hashed_password5",
        },
        "groups": {
            "admins": [
            "user1",
            "user2"
            ],
            "group1": [
            "user3"
            ]
        },
        "admins": [
            "user1"
        ]
        "packages": {
            "mypackage": {
                "groups": {
                    "group1": ["read', "write"],
                    "group2": ["read"],
                    "group3": [],
                },
                "users": {
                    "user1": ["read", "write"],
                    "user2": ["read"],
                    "user3": [],
                    "user5": ["read"],
                }
            }
        }
    }

If the secret is not already created, it will be when you make edits using the
web interface.

``auth.region_name``
~~~~~~~~~~~~~~~~~~~~
**Argument:** string

The AWS region you're storing your secrets in

``auth.secret_id``
~~~~~~~~~~~~~~~~~~
**Argument:** string

The unique ID of the secret

``auth.aws_access_key_id``, ``auth.aws_secret_access_key``
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
**Argument:** string, optional

Your AWS access key id and secret access key. If they are not specified then
pypicloud will attempt to get the values from the environment variables
``AWS_ACCESS_KEY_ID`` and ``AWS_SECRET_ACCESS_KEY`` or any other `credentials
source
<http://boto3.readthedocs.io/en/latest/guide/configuration.html#configuring-credentials>`__.

``auth.aws_session_token``
~~~~~~~~~~~~~~~~~~~~~~~~~~
**Argument:** string, optional

The session key for your AWS account. This is only needed when you are using
temporary credentials. See more: `<http://boto3.readthedocs.io/en/latest/guide/configuration.html#configuration-file>`__

``auth.profile_name``
~~~~~~~~~~~~~~~~~~~~~
**Argument:** string, optional

The credentials profile to use when reading credentials from the `shared credentials file <http://boto3.readthedocs.io/en/latest/guide/configuration.html#shared-credentials-file>`__

``auth.kms_key_id``
~~~~~~~~~~~~~~~~~~~~~
**Argument:** string, optional

The ARN or alias of the AWS KMS customer master key (CMK) to be used to encrypt the secret. See more: `<https://docs.aws.amazon.com/secretsmanager/latest/apireference/API_CreateSecret.html>`__

Remote Server
-------------
This implementation allows you to delegate all access control to another
server. If you already have an application with a user database, this allows
you to use that data directly.

You will need to ``pip install requests`` before running the server.

Configuration
^^^^^^^^^^^^^
Set ``pypi.auth = remote`` OR ``pypi.auth =
pypicloud.access.RemoteAccessBackend``

``auth.backend_server``
~~~~~~~~~~~~~~~~~~~~~~~
**Argument:** string

The base host url to connect to when fetching access data (e.g.
http://myserver.com)

``auth.user``
~~~~~~~~~~~~~
**Argument:** string, optional

If provided, the requests will use HTTP basic auth with this user

``auth.password``
~~~~~~~~~~~~~~~~~
**Argument:** string, optional

If ``auth.user`` is provided, this will be the HTTP basic auth password

``auth.uri.verify``
~~~~~~~~~~~~~~~~~~~
**Argument:** string, optional

The uri to hit when verifying a user's password (default ``/verify``).

params: ``username``, ``password``

returns: ``bool``

``auth.uri.groups``
~~~~~~~~~~~~~~~~~~~
**Argument:** string, optional

The uri to hit to retrieve the groups a user is a member of (default
``/groups``).

params: ``username``

returns: ``list``

``auth.uri.group_members``
~~~~~~~~~~~~~~~~~~~~~~~~~~
**Argument:** string, optional

The uri to hit to retrieve the list of users in a group (default
``/group_members``).

params: ``group``

returns: ``list``

``auth.uri.admin``
~~~~~~~~~~~~~~~~~~
**Argument:** string, optional

The uri to hit to determine if a user is an admin (default ``/admin``).

params: ``username``

returns: ``bool``

``auth.uri.group_permissions``
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
**Argument:** string, optional

The uri that returns a mapping of groups to lists of permissions (default
``/group_permissions``). The permission lists can contain zero or more of
('read', 'write').

params: ``package``

returns: ``dict``

``auth.uri.user_permissions``
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
**Argument:** string, optional

The uri that returns a mapping of users to lists of permissions (default
``/user_permissions``). The permission lists can contain zero or more of
('read', 'write').

params: ``package``

returns: ``dict``

``auth.uri.user_package_permissions``
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
**Argument:** string, optional

The uri that returns a list of all packages a user has permissions on (default
``/user_package_permissions``). Each element is a dict that contains 'package'
(str) and 'permissions' (list).

params: ``username``

returns: ``list``

``auth.uri.group_package_permissions``
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
**Argument:** string, optional

The uri that returns a list of all packages a group has permissions on (default
``/group_package_permissions``). Each element is a dict that contains 'package'
(str) and 'permissions' (list).

params: ``group``

returns: ``list``

``auth.uri.user_data``
~~~~~~~~~~~~~~~~~~~~~~
**Argument:** string, optional

The uri that returns a list of users (default ``/user_data``). Each user is a
dict that contains a ``username`` (str) and ``admin`` (bool). If a username is
passed to the endpoint, return just a single user dict that also contains
``groups`` (list).

params: ``username``

returns: ``list``
