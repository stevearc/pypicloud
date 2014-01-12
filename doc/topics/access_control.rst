.. _access_control:

Access Control
==============
PyPICloud has a complete access control system that allows you to fine-tune who
has access to your packages. To avoid storing user credentials and access rules
in a database, they are instead specified in a user-specified backend. The
default is to store the information in the config file.


Config Access Control
---------------------
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
that if the entry is ``none``, that user will not even see the package listed.

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

Set ``pypi.access_backend = pypicloud.access.ConfigAccessBackend``, or leave it
out completely since this is the default.

``user.<username>``
~~~~~~~~~~~~~~~~~~~
**Argument:** string

Defines a single user login. You may specify any number of users in the file.
Use ``pypicloud-gen-password`` to create the password hashes.

``package.<package>.user.<user>``
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
**Argument:** {``r``, ``rw``}

Give read or read/write access on a package to a single user.

``package.<package>.group.<group>``
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
**Argument:** {``r``, ``rw``}

Give read or read/write access on a package to a group of users. The group must
be defined in a ``group.<group>`` field. There are two special-case group
names. If you use ``everyone``, it will give that permission to all users; even
those not logged-in. If you use ``authenticated``, it will give that permission
to any user defined in the config file.

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

``auth.zero_security_mode``
~~~~~~~~~~~~~~~~~~~~~~~~~~~
**Argument:** bool, optional

Run in a special, limited access-control mode. Any user with valid credentials
can upload any package. Everyone (even not-logged-in users) can view and
download all packages. (default False)

Remote Access Control
---------------------
This implementation allows you to delegate all access control to another
server. If you already have an application with a user database, this allows
you to use that data directly.

Configuration
^^^^^^^^^^^^^
Set ``pypi.access_backend = pypicloud.access.RemoteAccessBackend``

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
