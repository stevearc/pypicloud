Changelog
=========
If you are upgrading an existing installation, read :ref:`the instructions <upgrade>`

0.2.7
-----
* Bug fix: First download of package using S3 backend and `pypi.fallback = cache` returns 404 (:issue:`31`)

0.2.6
-----
* Bug fix: Rebuilding SQL cache sometimes crashes (:issue:`29`)

0.2.5
-----
* Bug fix: Rebuilding SQL cache sometimes deadlocks (:pr:`27`)

0.2.4
-----
* Bug fix: ``ppc-migrate`` between two S3 backends (:pr:`22`)

0.2.3
-----
* Bug fix: Caching works with S3 backend (:sha:`4dc593a`)

0.2.2
-----
* Bug fix: Security bug in user auth (:sha:`001e8a5`)
* Bug fix: Package caching from pypi was slightly broken (:sha:`065f6c5`)
* Bug fix: ``ppc-migrate`` works when migrating to the same storage type (:sha:`45abcde`)

0.2.1
-----
* Bug fix: Pre-existing S3 download links were broken by 0.2.0 (:sha:`52e3e6a`)

0.2.0
-----
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

0.1.0
-----
* First public release
