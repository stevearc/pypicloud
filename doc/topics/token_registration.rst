:orphan:

.. _user_management:

User Management
===============
There are many ways to set up the :ref:`access_control` for pypicloud. This
section is dedicated to the methods available for dynamically adding and
removing users from your server.

Config File
-----------
If you use the :ref:`config file <config_file>` backend, you can simply make
edits and deploy the new file whenever you want to add or remove users.

**Pros:** Easy to understand

**Cons:** Requires deploying new files for every change

LDAP
----
Another straightforward option is to use the :ref:`LDAP <ldap_config>` backend.
LDAP is explicitly designed for managing users and permissions.

**Pros:** Once set up, all user management is centralized

**Cons:** If you don't already use LDAP, it's a lot of overhead

SQL
---
A SQL database is the final option for managing users, and it can be configured
to behave in different ways. The admin panel on the website is the gateway for
all user management actions.

User Registration
~~~~~~~~~~~~~~~~~
In the admin panel, there is a toggle button that allows you to enable user
registration. This allows anyone to register a username. You, as admin, can view
the pending user accounts and approve them.  Once approved, the user can log in
with the password they provided during registration.

**Pros:** It works I guess

**Cons:** Any random person can throw garbage into your pending user list

Manual User Creation
~~~~~~~~~~~~~~~~~~~~
In the admin panel, there is also a button labeled "Create user". This will
create a new user directly with a given username/password.

**Pros:** Fast and easy

**Cons:** Admin knows initial passwords, which is not a great security model.

.. _token_registration:

Registration via Tokens
~~~~~~~~~~~~~~~~~~~~~~~
There is a final button in the admin panel labeled "Get registration token".
This generates a token that can be used on the login page to create a new user.
The token is valid for a duration (set by :ref:`auth.token_expire`).

**Pros:** Fast and easy, pretty good security model

**Cons:** Edge case: If you delete a user in the window when the token is still
valid, the token can be used to re-create that user.
