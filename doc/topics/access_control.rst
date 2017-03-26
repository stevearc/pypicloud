.. _access_control:

Access Control
==============
PyPICloud has a complete access control system that allows you to fine-tune who
has access to your packages. There are several choices for where to store your
user credentials and access rules.

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


Configuration
^^^^^^^^^^^^^

Set ``pypi.auth = config`` OR ``pypi.auth =
pypicloud.access.ConfigAccessBackend`` OR leave it out completely since this is
the default.

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

``auth.zero_security_mode`` (deprecated)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
**Argument:** bool, optional

Replaced by ``pypi.default_read`` and ``pypi.default_write``. If enabled, will
set ``pypi.default_read = everyone`` and ``pypi.default_write =
authenticated``.

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

``auth.db.url``
~~~~~~~~~~~~~~~
**Argument:** string

The database url to use for storing user and group permissions. This may be the
same database as ``db.url`` (if you are also using the SQL caching database).

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
available groups.  All authorization is configured using ``pypi.default_read``,
``pypi.default_write``, and ``pypi.cache_update``.

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
**Argument:** string

The FQDN of the LDAP service account used. A service account is required to
perform the initial bind with. It only requires read access to your LDAP.

``auth.ldap.service_password``
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
**Argument:** string

The password for the LDAP service account.

``auth.ldap.base_dn``
~~~~~~~~~~~~~~~~~~~~~
**Argument:** string

The base DN under which all of your user accounts are organized in LDAP. Used
in combination with the ``all_user_search`` to find all potential users.

``auth.ldap.all_user_search``
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
**Argument:** string

An LDAP search phrase, which when used with the ``base_dn`` results in a list
of all users. As an example, this could be something like "(accountType=human)"
depending on your organization's LDAP configuration.

``auth.ldap.id_field``
~~~~~~~~~~~~~~~~~~~~~~
**Argument:** string

The field in the LDAP return when using ``all_user_search`` on ``base_dn`` to
determine the account name from the record. As an example this could be "name",
but it will depend on how your LDAP is set up.

``auth.ldap.admin_field``
~~~~~~~~~~~~~~~~~~~~~~~~~
**Argument:** string

The field to use in combination with ``admin_dns`` to determine the admin DNs
from the search result. As an example, this could be "groupMembers", but again,
will depend on your LDAP setup.

``auth.ldap.admin_dns``
~~~~~~~~~~~~~~~~~~~~~~~
**Argument:** list

A list of DNs to search for who should be considered an admin. It uses the
``admin_field`` to determine the source of admin DNs in the returned record(s).

``auth.ldap.service_account``
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
**Argument:** string, optional

A username for the service DN to self-authenticate as admin.
