.. _s3_policy:

S3 Policy
=========
In order for pypicloud to be able to access your S3 bucket, you may need to set
some policy options. The permissions required are:

* ``s3:GetObject``
* ``s3:PutObject``
* ``s3:DeleteObject``
* ``s3:ListBucket``

Note that ``s3:ListBucket`` is a *bucket* permission (applies to ``arn:aws:s3:::bucket``), whereas the others all
apply to *objects* (applies to ``arn:aws:s3:::bucket/*``).

You should use the `AWS Policy Generator
<http://awspolicygen.s3.amazonaws.com/policygen.html>`_ to create the json
policy for your bucket.
