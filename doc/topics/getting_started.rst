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

    (mypypi)$ pip install pypicloud waitress

AWS
---
You will need to go to the `AWS S3 console
<https://console.aws.amazon.com/s3/home>`_ and create a bucket to contain your
packages. Make sure the bucket name does not have a "." in it. Amazon's SSL
certificate is only valid for ``*.s3.amazonaws.com``, and adding more
subdomains to the url will cause the connection to be rejected by pip.

If you have not already, create an access key and secret by following the `AWS
guide
<http://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSGettingStartedGuide/AWSCredentials.html>`_

You need your bucket to grant access to your user account. If you are getting
permissions errors or 403's, you will need to set :ref:`a policy on your bucket
<s3_policy>`.

Configuration
-------------
Generate a default server configuration

.. code-block:: bash

    (mypypi)$ pypicloud-make-config -t server.ini

.. warning::

    Note that this configuration should only be used for development and
    testing.  If you want to set up your server for production, read the
    section on :ref:`deploying <deploy>`.

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
To upload packages to, you will need to add your server as an index server
inside your ``$HOME/.pypirc``::

    [distutils]
    index-servers = pypicloud

    [pypicloud]
    repository: http://localhost:6543
    username: <<username>>
    password: <<password>>

Now to upload a package you should run::

    python setup.py sdist upload -r pypicloud
