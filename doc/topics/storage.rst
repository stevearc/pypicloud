.. _storage:

Storage Backends
================
The storage backend is where the package files are ultimately stored for the
long-term.

Files
-----
This will store your packages in a directory. It's much simpler and faster to
set up if you don't need the reliability and scalability of S3.

Set ``pypi.storage = file`` OR ``pypi.storage = pypicloud.storage.FileStorage``
OR leave it out completely since this is the default.

``storage.dir``
~~~~~~~~~~~~~~~
**Argument:** string

The directory where the package files should be stored.

S3
--
This option will store your packages in S3.

Set ``pypi.storage = s3`` OR ``pypi.s3 = pypicloud.storage.S3Storage``

``aws.bucket``
~~~~~~~~~~~~~~
**Argument:** string

The name of the S3 bucket to store package in. Note: your bucket must not have
"." in it. Amazon's SSL certificate for S3 urls is only valid for
\*.s3.amazonaws.com

``aws.access_key``, ``aws.secret_key``
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
**Argument:** string, optional

Your AWS access key id and secret access key. If they are not specified then
pypicloud will attempt to get the values from the environment variables
``AWS_ACCESS_KEY_ID`` and ``AWS_SECRET_ACCESS_KEY``.

``aws.region``
~~~~~~~~~~~~~~
**Argument:** string, optional

If the S3 bucket does not exist, it will be created in this region (defaults to
classic US region)

``aws.prefix``
~~~~~~~~~~~~~~
**Argument:** string, optional

If present, all packages will be prefixed with this value when stored in S3.
Use this to store your packages in a subdirectory, such as "packages/"

``aws.prepend_hash``
~~~~~~~~~~~~~~~~~~~~~
**Argument:** bool, optional

Prepend a 4-letter hash to all S3 keys (default True). This helps S3 load
balance when traffic scales. See the `AWS documentation
<http://docs.aws.amazon.com/AmazonS3/latest/dev/request-rate-perf-considerations.html>`_
on the subject.

``aws.expire_after``
~~~~~~~~~~~~~~~~~~~~
**Argument:** int, optional

How long the generated S3 urls are valid for (default 86400 (1 day)). In
practice, there is no real reason why these generated urls need to expire at
all. S3 does it for security, but expiring links isn't part of the python
package security model. So in theory you can bump this number up.

``aws.buffer_time``
~~~~~~~~~~~~~~~~~~~
**Argument:** int, optional

Regenerate the cached S3 urls this long before they actually expire (default
600 (10 minutes)). This will help guarantee that if pip pulls down a url, it
will be valid long enough for it to finish downloading the package.
