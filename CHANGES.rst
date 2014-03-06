If you are upgrading an existing installation, read :ref:`the instructions <upgrade>`

0.2.0
-----
* Bug fix: Timestamp display on web interface :pr:`18`
* Bug fix: User registration stores password as plaintext :sha:`21ebe44`
* Feature: pypicloud-migrate-packages, command to move packages between storage backends :sha:`399a990`
* Feature: Adding support for more than one package with the same version. Now you can upload wheels! :sha:`2f24877`
* Feature: Allow transparently downloading and caching packages from pypi :sha:`e4dabc7`
* Hosting all js & css ourselves (no CDN) :sha:`20e345c`
* Obligatory miscellaneous refactoring

0.1.0
-----
* First public release
