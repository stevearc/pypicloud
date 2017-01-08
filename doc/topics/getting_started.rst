.. _getting_started:

Getting Started
===============

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

AWS
---
If you have not already, create an access key and secret by following the `AWS
guide
<http://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSGettingStartedGuide/AWSCredentials.html>`_

The default configuration should work, but if you get permission errors or
403's, you will need to set :ref:`a policy on your bucket <s3_policy>`.

Configuration
-------------
Generate a default server configuration

.. code-block:: bash

    (mypypi)$ ppc-make-config -t server.ini

.. warning::

    Note that this configuration should only be used for testing.  If you want
    to set up your server for production, read the section on :ref:`deploying
    <deploy>`.

Running
-------
Now you can run the server using pserve

.. code-block:: bash

    (mypypi)$ pserve server.ini

The server is now running on port 6543. You can view the web interface at
http://localhost:6543/

Installing Packages
-------------------
After you have the webserver started, you can install packages using::

    pip install -i http://localhost:6543/pypi/ PACKAGE1 [PACKAGE2 ...]

If you want to configure pip to always use PyPI Cloud, you can put your
preferences into the ``$HOME/.pip/pip.conf`` file::

    [global]
    index-url = http://localhost:6543/pypi/

Uploading Packages
------------------
To upload packages, you will need to add your server as an index server inside
your ``$HOME/.pypirc``::

    [distutils]
    index-servers = pypicloud

    [pypicloud]
    repository: http://localhost:6543/pypi/
    username: <<username>>
    password: <<password>>

Now to upload a package you should run::

    python setup.py sdist upload -r pypicloud

Searching Packages
------------------
After packages have been uploaded, you can search for them via pip::

    pip search -i http://localhost:6543/pypi/ QUERY1 [QUERY2 ...]

If you want to configure pip to use PyPI Cloud for search, you can update your
preferences in the ``$HOME/.pip/pip.conf`` file::

    [search]
    index = http://localhost:6543/pypi/

Note that this will ONLY return results from the PyPi Cloud repository. The
official PyPi repository will not be queried.
