Developing
==========

To get started developing pypicloud, run the following command:

.. code-block:: bash

    wget https://raw.github.com/mathcamp/devbox/master/devbox/unbox.py && \
    python unbox.py git@github.com:mathcamp/pypicloud

This will clone the repository and install the package into a virtualenv.

Run ``pypicloud-make-config -d development.ini`` to create a developer config
file.

Now you can run the server with

.. code-block:: bash

    $ pserve --reload development.ini

Run unit tests with:

.. code-block:: bash

    $ python setup.py nosetests

or:

.. code-block:: bash

    $ tox
