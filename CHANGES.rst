Changelog
=========
If you are upgrading an existing installation, read :ref:`the instructions <upgrade>`

1.0.11 - 2019/4/5
-----------------
* Add ability to stream files through pypicloud (:pr:`202`)
* Support spaces in ``auth.ldap.admin_value`` values (:pr:`206`)

1.0.10 - 2018/11/26
-------------------
* Strip non-ASCII characters from summary for S3 backend (:pr:`197`)
* Fix an issue with production log format (:issue:`198`)
* Add ``auth.ldap.fallback`` to use config file configure groups and permissions with LDAP access backend (:issue:`199`)

1.0.9 - 2018/9/6
----------------
* Fix: Exception during LDAP reconnect (:pr:`192`)
* Fix: LDAP on Python 3 could not detect admins (:pr:`193`)
* Feature: New ``pypi.auth.admin_group_dn`` setting for LDAP (for when memberOf is unavailable)

1.0.8 - 2018/8/27
-----------------
* Feature: Google Cloud Storage support (:pr:`189`)

1.0.7 - 2018/8/14
-----------------
* Feature: ``/health`` endpoint checks health of connection to DB backends (:issue:`181`)
* Feature: Options for LDAP access backend to ignore referrals and ignore multiple user results (:pr:`184`)
* Fix: Exception when ``storage.cloud_front_key_file`` was set (:pr:`185`)
* Fix: Bad redirect to the fallback url when searching the ``/json`` endpoint (:pr:`188`)
* Deprecation: ``pypi.fallback_url`` has been deprecated in favor of ``pypi.fallback_base_url`` (:pr:`188`)

1.0.6 - 2018/6/11
-----------------
* Fix: Support ``auth.profile_name`` passing in a boto profile name (:pr:`172`)
* Fix: Uploading package with empty description using twine crashes DynamoDB backend (:issue:`174`)
* Fix: Config file generation for use with docker container (using %(here)s was not working)
* Use cryptography package instead of horrifyingly old and deprecated pycrypto (:issue:`179`)
* Add ``storage.public_url`` to S3 backend (:issue:`173`)

1.0.5 - 2018/4/24
-----------------
* Fix: Download ACL button throws error in Python 3 (:issue:`166`)
* New access backend: AWS Secrets Manager (:pr:`164`)
* Add ``storage.storage_class`` option for S3 storage (:pr:`170`)
* Add ``db.tablenames`` option for DynamoDB cache (:issue:`167`)
* Reduce startup race conditions on empty caches when running multiple servers (:issue:`167`)

1.0.4 - 2018/4/1
----------------
* Fix: Fix SQL connection issues with uWSGI (:issue:`160`)
* Miscellaneous python 3 fixes

1.0.3 - 2018/3/26
-----------------
* Fix: uWSGI hangs in python 3 (:issue:`153`)
* Fix: Crash when using ``ppc-migrate`` to migrate from S3 to S3
* Add warnings and documentation for edge case where S3 bucket has a dot in it (:issue:`145`)
* Admin can create signup tokens (:issue:`156`)

1.0.2 - 2018/1/26
-----------------
* Fix: Hang when rebuilding Postgres cache (:issue:`147`)
* Fix: Some user deletes fail with Foreign Key errors (:issue:`150`)
* Fix: Incorrect parsing of version for wheels (:issue:`154`)
* Configuration option for number of rounds to use in password hash (:issue:`115`)
* Make request errors visible in the browser (:issue:`151`)
* Add a Create User button to admin page (:issue:`149`)
* SQL access backend defaults to disallowing anonymous users to register

1.0.1 - 2017/12/3
-----------------
* Support for LDAP anonymous bind (:pr:`142`)
* Fix a crash in Python 3 (:issue:`141`)

1.0.0 - 2017/10/29
------------------
* Python3 support thanks to boto3
* Removing stable/unstable version from package summary
* Changing and removing many settings
* Performance tweaks
* ``graceful_reload`` option for caches, to refresh from the storage backend while remaining operational
* Complete rewrite of LDAP access backend
* Utilities for hooking into :ref:`S3 create & delete notifications <s3_sync>` to keep multiple caches in sync

**NOTE** Because of the boto3 rewrite, many settings have changed. You will need
to review the settings for your storage, cache, and access backends to make sure
they are correct, as well as rebuilding your cache as per usual.

0.5.6 - 2017/10/29
------------------
* Add ``storage.object_acl`` for S3 (:pr:`139`)

0.5.5 - 2017/9/9
----------------
* Allow search endpoint to have a trailing slash (:issue:`133`)

0.5.4 - 2017/8/10
-----------------
* Allow overriding the displayed download URL in the web interface (:pr:`125`)
* Bump up the DB size of the version field (SQL-only) (:pr:`128`)

0.5.3 - 2017/4/30
-----------------
* Bug fix: S3 uploads failing from web interface and when fallback=cache (:issue:`120`)

0.5.2 - 2017/4/22
-----------------
* Bug fix: The ``/pypi`` path was broken for viewing & uploading packages (:issue:`119`)
* Update docs to recommend ``/simple`` as the install/upload URL
* Beaker session sets ``invalidate_corrupt = true`` by default

0.5.1 - 2017/4/17
-----------------
* Bug fix: Deleting packages while using the Dynamo cache would sometimes remove the wrong package from Dynamo (:issue:`118`)

0.5.0 - 2017/3/29
-----------------
**Upgrade breaks**: SQL caching database. You will need to rebuild it.

* Feature: Pip search works now (:pr:`107`)

0.4.6 - 2017/4/17
-----------------
* Bug fix: Deleting packages while using the Dynamo cache would sometimes remove the wrong package from Dynamo (:issue:`118`)

0.4.5 - 2017/3/25
-----------------
* Bug fix: Access backend now works with MySQL family (:pr:`106`)
* Bug fix: Return http 409 for duplicate upload to work better with twine (:issue:`112`)
* Bug fix: Show upload button in interface if ``default_write = everyone``
* Confirm prompt before deleting a user or group in the admin interface
* Do some basica sanity checking of username/password inputs

0.4.4 - 2016/10/5
-----------------
* Feature: Add optional AWS S3 Server Side Encryption option (:pr:`99`)

0.4.3 - 2016/8/2
----------------
* Bug fix: Rebuilding cache always ends up with correct name/version (:pr:`93`)
* Feature: /health endpoint (nothing fancy, just returns 200) (:issue:`95`)

0.4.2 - 2016/6/16
-----------------
* Bug fix: Show platform-specific versions of wheels (:issue:`91`)

0.4.1 - 2016/6/8
----------------
* Bug fix: LDAP auth disallows empty passwords for anonymous binding (:pr:`92`)
* Config generator sets ``pypi.default_read = authenticated`` for prod mode

0.4.0 - 2016/5/16
-----------------
**Backwards incompatibility**: This version was released to handle a change in
the way pip 8.1.2 handles package names. If you are upgrading from a previous
version, there are :ref:`detailed instructions for how to upgrade safely <upgrade0.4>`.

0.3.13 - 2016/6/8
-----------------
* Bug fix: LDAP auth disallows empty passwords for anonymous binding (:pr:`92`)

0.3.12 - 2016/5/5
-----------------
* Feature: Setting ``auth.ldap.service_account`` for LDAP auth (:pr:`84`)

0.3.11 - 2016/4/28
------------------
* Bug fix: Missing newline in config template (:pr:`77`)
* Feature: ``pypi.always_show_upstream`` for tweaking fallback behavior (:issue:`82`)

0.3.10 - 2016/3/21
------------------
* Feature: S3 backend setting ``storage.redirect_urls``

0.3.9 - 2016/3/13
-----------------
* Bug fix: SQL cache works with MySQL (:issue:`74`)
* Feature: S3 backend can use S3-compatible APIs (:pr:`72`)

0.3.8 - 2016/3/10
-----------------
* Feature: Cloudfront storage (:pr:`71`)
* Bug fix: Rebuilding cache from storage won't crash on odd file names (:pr:`70`)

0.3.7 - 2016/1/12
-----------------
* Feature: ``/packages`` endpoint to list all files for all packages (:pr:`64`)

0.3.6 - 2015/12/3
-----------------
* Bug fix: Settings parsed incorrectly for LDAP auth (:issue:`62`)

0.3.5 - 2015/11/15
------------------
* Bug fix: Mirror mode: only one package per version is displayed (:issue:`61`)

0.3.4 - 2015/8/30
-----------------
* Add docker-specific option for config creation
* Move docker config files to a separate repository

0.3.3 - 2015/7/17
-----------------
* Feature: LDAP Support (:pr:`55`)
* Bug fix: Incorrect package name/version when uploading from web (:issue:`56`)

0.3.2 - 2015/7/7
----------------
* Bug fix: Restore direct links to S3 to fix easy_install (:issue:`54`)

0.3.1 - 2015/6/18
-----------------
* Bug fix: ``pypi.allow_overwrite`` causes crash in sql cache (:issue:`52`)

0.3.0 - 2015/6/16
-----------------
* Fully defines the behavior of every possible type of pip request. See :ref:`Fallbacks <fallback_detail>` for more detail.
* Don't bother caching generated S3 urls.

0.2.13 - 2015/5/27
------------------
* Bug fix: Crash when mirror mode serves private packages

0.2.12 - 2015/5/14
------------------
* Bug fix: Mirror mode works properly with S3 storage backend

0.2.11 - 2015/5/11
------------------
* Bug fix: Cache mode will correctly download packages with legacy versioning (:pr:`45`)
* Bug fix: Fix the fetch_requirements endpoint (:sha:`6b2e2db`)
* Bug fix: Incorrect expire time comparison with IAM roles (:pr:`47`)
* Feature: 'mirror' mode. Caches packages, but lists all available upstream versions.

0.2.10 - 2015/2/27
------------------
* Bug fix: S3 download links expire incorrectly with IAM roles (:issue:`38`)
* Bug fix: ``fallback = cache`` crashes with distlib 0.2.0 (:issue:`41`)

0.2.9 - 2014/12/14
------------------
* Bug fix: Connection problems with new S3 regions (:issue:`39`)
* Usability: Warn users trying to log in over http when ``session.secure = true`` (:issue:`40`)

0.2.8 - 2014/11/11
------------------
* Bug fix: Crash when migrating packages from file storage to S3 storage (:pr:`35`)

0.2.7 - 2014/10/2
-----------------
* Bug fix: First download of package using S3 backend and ``pypi.fallback = cache`` returns 404 (:issue:`31`)

0.2.6 - 2014/8/3
----------------
* Bug fix: Rebuilding SQL cache sometimes crashes (:issue:`29`)

0.2.5 - 2014/6/9
----------------
* Bug fix: Rebuilding SQL cache sometimes deadlocks (:pr:`27`)

0.2.4 - 2014/4/29
-----------------
* Bug fix: ``ppc-migrate`` between two S3 backends (:pr:`22`)

0.2.3 - 2014/3/13
-----------------
* Bug fix: Caching works with S3 backend (:sha:`4dc593a`)

0.2.2 - 2014/3/13
-----------------
* Bug fix: Security bug in user auth (:sha:`001e8a5`)
* Bug fix: Package caching from pypi was slightly broken (:sha:`065f6c5`)
* Bug fix: ``ppc-migrate`` works when migrating to the same storage type (:sha:`45abcde`)

0.2.1 - 2014/3/12
-----------------
* Bug fix: Pre-existing S3 download links were broken by 0.2.0 (:sha:`52e3e6a`)

0.2.0 - 2014/3/12
-----------------
**Upgrade breaks**: caching database

* Bug fix: Timestamp display on web interface (:pr:`18`)
* Bug fix: User registration stores password as plaintext (:sha:`21ebe44`)
* Feature: ``ppc-migrate``, command to move packages between storage backends (:sha:`399a990`)
* Feature: Adding support for more than one package with the same version. Now you can upload wheels! (:sha:`2f24877`)
* Feature: Allow transparently downloading and caching packages from pypi (:sha:`e4dabc7`)
* Feature: Export/Import access-control data via ``ppc-export`` and ``ppc-import`` (:sha:`dbd2a16`)
* Feature: Can set default read/write permissions for packages (:sha:`c9aa57b`)
* Feature: New cache backend: DynamoDB (:sha:`d9d3092`)
* Hosting all js & css ourselves (no more CDN links) (:sha:`20e345c`)
* Obligatory miscellaneous refactoring

0.1.0 - 2014/1/20
-----------------
* First public release
