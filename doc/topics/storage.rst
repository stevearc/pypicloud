.. _storage:

Storage Backends
================
The storage backend is where the actual package files are kept.

Files
-----
This will store your packages in a directory on disk. It's much simpler and
faster to set up if you don't need the reliability and scalability of S3.

Set ``pypi.storage = file`` OR ``pypi.storage = pypicloud.storage.FileStorage``
OR leave it out completely since this is the default.

``storage.dir``
~~~~~~~~~~~~~~~
**Argument:** string

The directory where the package files should be stored.

S3
--
This option will store your packages in S3.

.. note::

  Be sure you have set the correct :ref:`s3_policy`.

Set ``pypi.storage = s3`` OR ``pypi.s3 = pypicloud.storage.S3Storage``

A few key, required options are mentioned below, but pypicloud attempts to
support all options that can be passed to `resource
<http://boto3.readthedocs.io/en/latest/reference/core/session.html#boto3.session.Session.resource>`__
or to the `Config
<https://botocore.readthedocs.io/en/stable/reference/config.html#botocore.config.Config>`__
object. In general you can simply prefix the option with ``storage.`` and
pypicloud will pass it on. For example, to set the signature version on the
Config object::

    storage.signature_version = s3v4

Note that there is a ``s3`` option dict as well. Those options should also just
be prefixed with ``storage.``. For example::

    storage.use_accelerate_endpoint = true

Will pass the Config object the option ``Config(s3={'use_accelerate_endpoint': True})``.

.. note::

  If you plan to run pypicloud in multiple regions, read more about
  :ref:`syncing pypicloud caches using S3 notifications <s3_sync>`

``storage.bucket``
~~~~~~~~~~~~~~~~~~
**Argument:** string

The name of the S3 bucket to store packages in.

``storage.region_name``
~~~~~~~~~~~~~~~~~~~~~~~
**Argument:** string, semi-optional

This is required if your bucket is in a new region, such as ``eu-central-1``.
If your bucket does not yet exist, it will be created in this region on
startup. If blank, the classic US region will be used.

.. _s3_credentials:

``storage.access_key``, ``storage.secret_key``
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
**Argument:** string, optional

Your AWS access key id and secret access key. If they are not specified then
pypicloud will attempt to get the values from the environment variables
``AWS_ACCESS_KEY_ID`` and ``AWS_SECRET_ACCESS_KEY`` or any other `credentials
source
<http://boto3.readthedocs.io/en/latest/guide/configuration.html#configuring-credentials>`__.

``storage.prefix``
~~~~~~~~~~~~~~~~~~
**Argument:** string, optional

If present, all packages will be prefixed with this value when stored in S3.
Use this to store your packages in a subdirectory, such as "packages/"

``storage.prepend_hash``
~~~~~~~~~~~~~~~~~~~~~~~~
**Argument:** bool, optional

Prepend a 4-letter hash to all S3 keys (default True). This helps S3 load
balance when traffic scales. See the `AWS documentation
<http://docs.aws.amazon.com/AmazonS3/latest/dev/request-rate-perf-considerations.html>`_
on the subject.

``storage.expire_after``
~~~~~~~~~~~~~~~~~~~~~~~~
**Argument:** int, optional

How long (in seconds) the generated S3 urls are valid for (default 86400 (1
day)). In practice, there is no real reason why these generated urls need to
expire at all. S3 does it for security, but expiring links isn't part of the
python package security model. So in theory you can bump this number up.

``storage.redirect_urls``
~~~~~~~~~~~~~~~~~~~~~~~~~
**Argument:** bool, optional

The short story: set this to ``true`` if you only use pip and don't have to
support easy_install. It will dramatically speed up your server.

The long story: :ref:`redirect_detail`

``storage.server_side_encryption``
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
**Argument:** str, optional

Enables AES-256 transparent server side encryption. See the `AWS documention
<http://docs.aws.amazon.com/AmazonS3/latest/dev/UsingServerSideEncryption.html>`_.
Default is None.

``storage.object_acl``
~~~~~~~~~~~~~~~~~~~~~~
**Argument:** string, optional

Sets uploaded object's "canned" ACL. See the `AWS documentation
<http://docs.aws.amazon.com/AmazonS3/latest/dev/acl-overview.html#canned-acl>`_.
Default is "private", i.e. only the account owner will get full access.
May be useful, if the bucket and pypicloud are hosted in different AWS accounts.

CloudFront
----------
This option will store your packages in S3 but use CloudFront to deliver the packages.
This is an extension of the S3 storage backend and require the same settings as above,
but also the settings listed below.

Set ``pypi.storage = cloudfront`` OR ``pypi.s3 = pypicloud.storage.CloudFrontS3Storage``

``storage.cloud_front_domain``
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
**Argument:** string

The CloudFront domain you have set up. This CloudFront distribution must be set up to
use your S3 bucket as the origin.

Example: ``https://dabcdefgh12345.cloudfront.net``

``storage.cloud_front_key_id``
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
**Argument:** string, optional

If you want to protect your packages from public access you need to set up the CloudFront
distribution to use signed URLs. This setting specifies the key id of the `CloudFront key pair
<http://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/private-content-trusted-signers.html>`_
that is currently active on your AWS account.

``storage.cloud_front_key_file``
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
**Argument:** string, optional

Only needed when setting up CloudFront with signed URLs. This setting should be
set to the full path of the CloudFront private key file.

``storage.cloud_front_key_string``
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
**Argument:** string, optional

The same as ``cloud_front_key_file``, but contains the raw private key instead
of a path to a file.
