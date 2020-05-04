:orphan:

.. _passlib:

A Brief Discussion on Password Hashing
======================================

What is password hashing?
-------------------------
In brief, it is the process of taking a plaintext password and putting it
through a one-way function to produce a resulting hash. Pypicloud uses the
PassLib library, which uses modern best-practices for password hashing and
verification.

The reason to hash passwords is so that if an attacker gets access to your user
database, they can't read everyone's passwords. The hashes can be used to
*verify* a password that a user provides, but there is no easy way to convert
the hash back into the original password. The main approach to cracking a hash
is to brute force try every possible input until a match is found.  For this
reason, it is useful to have a hashing function that **takes a long time**.  If
it takes a long time for you, it'll take a long time for a hacker that has to
check millions of possible inputs.

There's an excellent discussion of this here: `<https://stackoverflow.com/a/13572232>`__

What is the problem?
--------------------
The *normal* way that a website uses password hashing is that a user will input
their password at most once-per-session, and thereafter they will have a signed
cookie to authenticate themselves. The login process may be slow, but everything
afterwards will be fast.

For pypicloud, you provide an index to pip in the form
``https://user:password@mypypiserver.com``. Every single request made by pip
will send up the username and password because pip cannot store and use a signed
cookie. A typical ``pip install`` can easily make 10 requests to the server.  If
you made your password hash take 350ms like PassLib suggests, that's 3.5 seconds
of *pegging* the CPU. If you have a fleet of servers all hitting pypicloud at
the same time, that can easily become a problematic bottleneck.

In fact, there have been reports from pypicloud users to this effect.
:issue:`115` and :issue:`237` both report too much time being consumed by
password hashing.


What does pypicloud do?
-----------------------
The threat model of pypicloud is somewhat different from a typical website.
Though pypicloud does offer auth backends where users can register accounts, by
far the most common use case is one user account that is shared by a fleet.
There is no worry of exposing user data, and having the password to communicate
to the pypicloud server doesn't help them any more than already having access to
the servers themselves.

For this reason, pypicloud is now tuned by default to only take ~10ms per
password hash rather than the PassLib recommended 350ms.  The settings can be
tweaked with :ref:`auth_scheme` and :ref:`auth_rounds`, so it can still be made
as secure as you like, but the default mode now is to optimize for speed. Of
course, if you want to fully optimize it you can always set the
:ref:`auth_rounds` to 1.
