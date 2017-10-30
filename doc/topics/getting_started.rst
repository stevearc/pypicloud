.. _getting_started:

Getting Started
===============

There is a `docker container <https://github.com/stevearc/pypicloud-docker>`__
if you're into that sort of thing.

Installation
------------
First create and activate a virtualenv to contain the installation:

.. code-block:: bash

    $ virtualenv mypypi
    New python executable in mypypi/bin/python
    Installing setuptools.............done.
    Installing pip...............done.
    $ source mypypi/bin/activate
    (mypypi)$

Now install pypicloud and waitress. To get started, we're using
`waitress <https://pylons.readthedocs.org/projects/waitress/en/latest/>`_ as
the WSGI server because it's easy to set up.

.. code-block:: bash

    (mypypi)$ pip install pypicloud[server]

Configuration
-------------
Generate a server configuration file. Choose ``filesystem`` when it asks where
you want to store your packages.

.. code-block:: bash

    (mypypi)$ ppc-make-config -t server.ini

.. warning::

    Note that this configuration should only be used for testing.  If you want
    to set up your server for production, read the section on :ref:`deploying
    <deploy>`.

Running
-------
You can run the server using pserve

.. code-block:: bash

    (mypypi)$ pserve server.ini

The server is running on port 6543. You can view the web interface at
http://localhost:6543/

Packages will be stored in a directory named ``packages`` next to the
``server.ini`` file. Pypicloud will use a SQLite database in the same location
to cache the package index. This is the simplest configuration for pypicloud
because it is entirely self-contained on a single server.

Installing Packages
-------------------
After you have the webserver started, you can install packages using::

    pip install -i http://localhost:6543/simple/ PACKAGE1 [PACKAGE2 ...]

If you want to configure pip to always use pypicloud, you can put your
preferences into the ``$HOME/.pip/pip.conf`` file::

    [global]
    index-url = http://localhost:6543/simple/

Uploading Packages
------------------
To upload packages, you will need to add your server as an index server inside
your ``$HOME/.pypirc``:

.. code-block:: ini

    [distutils]
    index-servers = pypicloud

    [pypicloud]
    repository: http://localhost:6543/simple/
    username: <<username>>
    password: <<password>>

Then you can run::

    python setup.py sdist upload -r pypicloud

Searching Packages
------------------
After packages have been uploaded, you can search for them via pip::

    pip search -i http://localhost:6543/pypi QUERY1 [QUERY2 ...]

If you want to configure pip to use pypicloud for search, you can update your
preferences in the ``$HOME/.pip/pip.conf`` file::

    [search]
    index = http://localhost:6543/pypi

Note that this will ONLY return results from the pypicloud repository. The
official PyPi repository will not be queried (regardless of your :ref:`fallback
<fallback>` setting)
