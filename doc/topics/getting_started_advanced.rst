.. _getting_started_advanced:

Advanced Configurations
=======================

Now we're going to try something a bit more complicated. We're going to store
the packages in S3 and cache the package index in DynamoDB.

Follow the same :ref:`installation instructions <getting_started>` as before.

AWS
---
If you have not already, create an access key and secret by following the `AWS
guide
<http://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSGettingStartedGuide/AWSCredentials.html>`_

The default configuration should work, but if you get permission errors or
403's, you will need to set :ref:`a policy on your bucket <s3_policy>`.

Configuration
-------------
This time when you create a config file (``ppc-make-config -t server_s3.ini``),
choose ``S3`` when it asks where you want to store your packages. Then add the
following configuration (replacing the ``<>`` strings with the values you want)

.. code-block:: ini

    pypi.fallback = redirect

    pypi.db = dynamo
    db.region_name = <region>

    pypi.storage = s3
    storage.bucket = <my_bucket>
    storage.region_name = <region>

Running
-------
Since you're using AWS services now, you need credentials. Put them somewhere
that `boto can find them
<http://boto3.readthedocs.io/en/latest/guide/configuration.html#configuring-credentials>`__.
The easiest method is the ``AWS_ACCESS_KEY_ID`` and ``AWS_SECRET_ACCESS_KEY``
environment variables, but you can also put them directly into the
``server_s3.ini`` file if you wish (see :ref:`dynamo <dynamo_credentials>` and
:ref:`s3 <s3_credentials>`)

Now you can run ``pserve server_s3.ini``. On the first run it should create the S3
bucket and DynamoDB tables for you (you may need to tweak the provisioned
capacity for the DynamoDB tables, depending on your expected load).

If you uploaded any packages to the first server and have them stored locally,
you can migrate them to S3 using the ``ppc-migrate`` tool::

    ppc-migrate server.ini server_s3.ini
