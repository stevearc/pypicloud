Developing
==========

The fast way to get set up:

.. code-block:: bash

    wget https://raw.github.com/stevearc/devbox/0.1.0/devbox/unbox.py && \
    python unbox.py git@github.com:stevearc/pypicloud

The slow way to get set up:

.. code-block:: bash

    $ git clone git@github.com:stevearc/pypicloud
    $ cd pypicloud
    $ virtualenv pypicloud_env
    $ . pypicloud_env/bin/activate
    $ pip install -r requirements_dev.txt
    $ pip install -e .
    $ rm -r .git/hooks
    $ ln -s ../git_hooks .git/hooks # This will run pylint before you commit

Run ``ppc-make-config -d development.ini`` to create a developer config
file.

Now you can run the server with

.. code-block:: bash

    $ pserve --reload development.ini

The unit tests require a redis server to be running on port 6379. Run unit
tests with:

.. code-block:: bash

    $ python setup.py nosetests

or:

.. code-block:: bash

    $ tox
