.. _deploy:

Deploying to Production
=======================
This section is geared towards helping you deploy this server properly for
production use.

`@powellc <https://github.com/powellc>`_ has put together an Ansible
playbook for pypicloud, which can be found here:
https://github.com/powellc/ansible-pypicloud

There is a `docker container <https://hub.docker.com/r/stevearc/pypicloud/>`__
that you can deploy or use as a base image. The following configuration
recommendations still apply.

Configuration
-------------
Remember when you generated a config file in :ref:`getting started
<getting_started>`? Well we can do the same thing with a different flag to
generate a default production config file.

.. code-block:: bash

    $ ppc-make-config -p prod.ini

.. warning::
    You should make sure that ``session.secure`` is ``true``

You may want to tweak :ref:`auth.scheme <auth_scheme>` or :ref:`auth.rounds
<auth_rounds>` for more speed or more security. See :ref:`passlib` for more
context.

WSGI Server
-----------
You probably don't want to use waitress for your production server, though it
will work fine for small deploys. I recommend using `uWSGI
<http://uwsgi-docs.readthedocs.org/en/latest/>`__. It's fast and mature.

After creating your production config file, it will have a section for uWSGI.
You can run uWSGI with:

.. code-block:: bash

    $ pip install uwsgi pastescript
    $ uwsgi --ini-paste-logged prod.ini

Now uWSGI is running and listening on port 8080.

.. warning::

    If you are using ``pypi.fallback = cache``, make sure your uWSGI settings
    includes ``enable-threads = true``. The package downloader uses threads.

HTTPS and Reverse Proxies
-------------------------
uWSGI has native support for `SSL termination
<http://uwsgi-docs.readthedocs.io/en/latest/HTTPS.html>`__, but you may wish to
use NGINX or an ELB to do the SSL termination plus load balancing. For this and
other reverse proxy behaviors, you will need uWSGI to generate URLs that match
what your proxy expects. You can do this with `paste
middleware <http://pythonpaste.org/deploy/modules/config.html>`__. For example, to
enforce https:

.. code-block:: ini

    [app:main]
    filter-with = proxy-prefix

    [filter:proxy-prefix]
    use = egg:PasteDeploy#prefix
    scheme = https
