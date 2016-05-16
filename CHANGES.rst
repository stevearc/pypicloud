Changelog
=========
If you are upgrading an existing installation, read :ref:`the instructions <upgrade>`

0.4.0 - 2016/5/16
-----------------
**Backwards incompatibility**: This version was released to handle a change in
the way pip 8.1.2 handles package names. If you are upgrading from a previous
version, there are :ref:`detailed instructions for how to upgrade safely
<upgrade0.4>`.

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
