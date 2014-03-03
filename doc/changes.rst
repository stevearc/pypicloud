If you are upgrading an existing installation, read :ref:`the instructions <upgrade>`

0.2.0
-----
* Bug fix: Timestamp display on web interface :pr:`18`
* Feature: pypicloud-migrate-packages, command to move packages between storage backends :sha:`399a990`
* Feature: Adding support for more than one package with the same version. Now you can upload wheels! :sha:`2f24877`
* Cleanup: Splitting and isolating the cache and storage backends better :sha:`d66fdde`, :sha:`b262539`
* Cleanup: Hosting all js & css ourselves (no CDN) :sha:`20e345c`
* Breakage: Removed the ``pypi.use_fallback`` option (see ``pypi.fallback`` for details)

0.1.0
-----
* First public release
