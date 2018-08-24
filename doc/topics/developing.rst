Developing
==========

To get set up:

.. code-block:: bash

    $ git clone git@github.com:stevearc/pypicloud
    $ cd pypicloud
    $ virtualenv pypicloud_env
    $ . pypicloud_env/bin/activate
    $ pip install -r requirements_dev.txt

Run ``ppc-make-config -d development.ini`` to create a developer config file.

Now you can run the server with

.. code-block:: bash

    $ pserve --reload development.ini

The unit tests require a redis server to be running on port 6379, MySQL on port
3306, and Postgres on port 5432. If you have docker installed you can use the
``run-test-services.sh`` script to start all the necessary servers. Run unit
tests with:

.. code-block:: bash

    $ python setup.py nosetests

or:

.. code-block:: bash

    $ tox
