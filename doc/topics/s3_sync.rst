:orphan:

.. _s3_sync:

Using S3 Notifications to sync caches
=====================================

**What is this for?**

Let's say you have servers in multiple regions. You may want to have pypicloud
set up in each region. So in each region you set up an S3 bucket, a cache
backend (let's say DynamoDB), and a server running pypicloud. The first problem
is that there is no communication; if you upload a package to one region, the
other region doesn't see it.

So you set up `Cross-Region Replication
<http://docs.aws.amazon.com/AmazonS3/latest/dev/crr.html>`__ for your S3
buckets, and now every time you upload a package in one region, it gets copied
to the S3 bucket in the other. Unfortunately, pypicloud isn't picking up on
those changes so you still can't install packages that were uploaded from a
different region. That's where this tool comes in.

**Tell me more**

Pypicloud provides some utilities for setting up an AWS Lambda function that
will receive create and delete operations from a S3 bucket and sync those
changes to your pypicloud cache. After it's set up, you should be able to run a
pypicloud stack in as many regions as you want and keep them all perfectly in
sync.

Get Started
-----------

Create a ``config.ini`` file that contains the configuration for S3 storage and
whichever cache you want to sync to. Make sure you have AWS credentials in a
format that can be `read by boto
<http://boto3.readthedocs.io/en/latest/guide/configuration.html#configuring-credentials>`__.
Then run::

  ppc-create-s3-sync config.ini

That's all! You should now have an AWS Lambda function running whenever an
object is created or deleted from your bucket.

Moving Parts
------------
Chances are good that you will have to make some edits to this setup, so it's
important to know what it's doing. There are three main components.

IAM Role
^^^^^^^^
The Lambda function must have a Role that defines the permissions it has.
``ppc-create-s3-sync`` attempts to create one (named "pypicloud_lambda...") that
has permissions to write logs and read from S3. If your cache is DynamoDB, it
also includes read/write permissions on the pypicloud tables.

Lambda Function
^^^^^^^^^^^^^^^
It builds a bundle and uploads it to a new Lambda function, then it gives the S3
bucket Invoke permissions on the function.

Bucket Notifications
^^^^^^^^^^^^^^^^^^^^
The last step is to go to the S3 bucket and add a Notification Configuration
that calls our lambda function on all ObjectCreate and ObjectDelete events.

More Details
------------
I have only thoroughly tested this with a DynamoDB cache. You may have to make
changes to make it work with other caches.

Many of the steps are customizable. Look at the args you can pass in by running
``ppc-create-s3-sync -h``. For example, if you want to create the Role yourself
you can pass the ARN in with ``-a <arn>`` and the command will use your existing
Role.

If you're building the Lambda function by hand, you can use
``ppc-build-lambda-bundle`` to build the zip bundle that is uploaded to Lambda.
You will need to add an environment variable ``PYPICLOUD_SETTINGS`` that is a
json string of all the relevant config options for the db, including ``pypi.db``
and all the ``db.<option>: <value>`` entries.

Feedback
--------
This is all very new and largely untested. Please email me or file issues with
feedback and/or bug reports. Did you get this working? Was it easy? Was it hard? Was it confusing? Did you
have to change the policies? Did you have to change anything else?
