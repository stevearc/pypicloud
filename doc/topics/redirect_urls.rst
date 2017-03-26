.. _redirect_detail:

Why you should set redirect_urls = True
=======================================
pypicloud using S3/Cloudfront will generate signed urls for your clients to
download. When you run ``pip install <package>`` it will hit the
``/simple/<package>`` endpoint and attempt to render urls for all versions of
that package. That will look like this:

.. code-block:: html

    <a href="https://bucket.s3.amazonaws.com/package-0.1.tar.gz?Signature=SIGNATURE">package-0.1.tar.gz</a><br>
    <a href="https://bucket.s3.amazonaws.com/package-0.2.tar.gz?Signature=SIGNATURE">package-0.2.tar.gz</a><br>
    <a href="https://bucket.s3.amazonaws.com/package-0.3.tar.gz?Signature=SIGNATURE">package-0.3.tar.gz</a><br>

If you have a lot of versions of that package, that's a lot of cryptographic
signatures that have to be run just for one ``pip install``. It used to be that
boto used `M2Crypto <https://pypi.python.org/pypi/M2Crypto>`_ for these
signatures, but then `this pull request
<https://github.com/boto/boto/pull/1214>`_ landed which changed it to use `rsa
<https://stuvel.eu/rsa>`_, a pure-python library that's easier to install.

It has some advantages, but speed is not one of them. Signing all of these urls
can now take an obscenely long time.

**Solution**: Why don't we just render dummy urls in the ``/simple/<package>``
endpoint that will then return a HTTP redirect to the signed S3 url? Then we
only have to sign one url per ``pip install``.

**Problem**: Because `legacy code is the worst thing in the world
<https://github.com/stevearc/pypicloud/issues/54>`_. For reasons that I am
unable/unwilling to fully debug, ``easy_install`` cannot handle that. It just
can't.

So to compromise I added the ``storage.redirect_urls`` option. When set to true,
it will generate redirect urls instead of signed S3 urls at the ``/simple``
endpoint. This is much much faster, but breaks for ``easy_install``.

Please, please stop using ``easy_install``. Just stop.
