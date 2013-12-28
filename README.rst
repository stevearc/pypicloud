PyPI Cloud
==========
This package is a Pyramid WSGI app that runs a simple PyPI server where all the
packages are stored on Amazon's Simple Storage Service (S3).

The original goal was to have an instance of PyPI that can host private
packages. There are many projects that will do just this, and if that's all
you're looking for, I recommend checking out `Ralf Schmitt's pypiserver
<https://github.com/schmir/pypiserver>`_, which is both easier to set up and
more mature than this project. I didn't want to have to handle issues like
backing up my package directory and scaling up the number of webservers as our
cloud grows. Since all pypicloud is doing is serving pages that link to S3, it
should scale like a motherfucker.

Development
===========
To get started developing pypicloud, run the following command::

    wget https://raw.github.com/mathcamp/devbox/master/devbox/unbox.py && \
    python unbox.py git@github.com:mathcamp/pypicloud

This will clone the repository and install the package into a virtualenv. From
there you should add your AWS credentials to ``development.ini`` (details below).

Now you need to create the schema in the default sqlite database, so run::

    pypicloud-create-schema development.ini

Now you can run the server with::

    pserve --reload development.ini

Configuration Options
=====================
Here is the list of options that you can use to customize the behavior. Some
are optional, others are not. Optional keys are listed with their default
value::

    # Your AWS access key id (if not present the environment variable
    # AWS_ACCESS_KEY_ID is used)
    aws.access_key = <<AWS access key>>
    # Your AWS secret access key (if not present the environment variable
    # AWS_SECRET_ACCESS_KEY is used)
    aws.secret_key = <<AWS secret key>>

    # The name of the S3 bucket to store package in. Note: your bucket must not
    # have "." in it. Amazon's SSL certificate for S3 urls is only valid for
    # *.s3.amazonaws.com
    aws.bucket = <<AWS bucket>>
    # If present, all packages will be prefixed with this value (optional).
    # Use this to store your packages in a subdirectory, such as "packages/"
    aws.prefix =
    # How long the generated S3 urls are valid for (optional)
    aws.expire_after = 86400 # (1 day)
    # Our url cache will expire this long before the S3 urls actually expire,
    # giving applications time to complete their downloads (optional)
    aws.buffer_time = 300 # (5 minutes)

    # If True, forward requests for unknown packages to another url (optional)
    pypi.use_fallback = True
    # The url to forward unknown package requests to (optional)
    pypi.fallback_url = http://pypi.python.org/simple

    # The sqlalchemy database url (S3 urls are cached in the db)
    sqlalchemy.url = <<sqlalchemy url>>

    # To authenticate while uploading packages, provide any number of
    # username/passwords. To generate the password hash, use the
    # ``pypicloud-gen-password`` command that will become available after
    # installing pypicloud.
    user.<<username>> = <<salted password hash>>

Using with Pip
==============

Installing Packages
-------------------
After you have the webserver started, you can install packages using::

    pip install -i http://localhost:6543/simple/ PACKAGE1 [PACKAGE2 ...]

If you want to configure pip to always use PyPI Cloud, you can put your
preferences into the $HOME/.pip/pip.conf file::

    [global]
    index-url = http://localhost:6543/simple

Uploading Packages
------------------
To upload packages to PyPI Cloud, you will need to add this as an index server
inside your $HOME/.pypirc::

    [distutils]
    index-servers = pypicloud

    [pypicloud]
    repository: http://localhost:6543
    username: <<username>>
    password: <<password>>

Now to upload a package you should run::

    python setup.py sdist upload -r pypicloud
