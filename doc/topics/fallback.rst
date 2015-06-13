.. _fallback:

Fallbacks
=========
Below is a detailed table for each possible fallback setting.


Fallback = none
^^^^^^^^^^^^^^^

=======  ====  ================  =========  =========
Package  Read  Can update cache  Logged in  Response
=======  ====  ================  =========  =========
☐        ☐     ☐                 ☐          401 (to force upload of basic auth)
☐        ☐     ☐                 ☑          404
☐        ☑     ☐                 ☐          404
☐        ☑     ☐                 ☑          404
☐        ☑     ☑                 ☐          404
☐        ☑     ☑                 ☑          404
☑        ☐     ☐                 ☐          401 (to force upload of basic auth)
☑        ☐     ☐                 ☑          404
☑        ☑     ☐                 ☐          Serve package list
☑        ☑     ☐                 ☑          Serve package list
☑        ☑     ☑                 ☐          Serve package list
☑        ☑     ☑                 ☑          Serve package list
=======  ====  ================  =========  =========

Fallback = redirect
^^^^^^^^^^^^^^^^^^^

=======  ====  ================  =========  =========
Package  Read  Can update cache  Logged in  Response
=======  ====  ================  =========  =========
☐        ☐     ☐                 ☐          302 to fallback
☐        ☐     ☐                 ☑          302 to fallback
☐        ☑     ☐                 ☐          302 to fallback
☐        ☑     ☐                 ☑          302 to fallback
☐        ☑     ☑                 ☐          302 to fallback
☐        ☑     ☑                 ☑          302 to fallback
☑        ☐     ☐                 ☐          401 (to force upload of basic auth)
☑        ☐     ☐                 ☑          302 to fallback
☑        ☑     ☐                 ☐          Serve package list
☑        ☑     ☐                 ☑          Serve package list
☑        ☑     ☑                 ☐          Serve package list
☑        ☑     ☑                 ☑          Serve package list
=======  ====  ================  =========  =========

Fallback = cache
^^^^^^^^^^^^^^^^

=======  ====  ================  =========  =========
Package  Read  Can update cache  Logged in  Response
=======  ====  ================  =========  =========
☐        ☐     ☐                 ☐          401 (to force upload of basic auth)
☐        ☐     ☐                 ☑          404
☐        ☑     ☐                 ☐          401 (to force upload of basic auth)
☐        ☑     ☐                 ☑          404
☐        ☑     ☑                 ☐          Upstream links that will download & cache
☐        ☑     ☑                 ☑          Upstream links that will download & cache
☑        ☐     ☐                 ☐          401 (to force upload of basic auth)
☑        ☐     ☐                 ☑          404
☑        ☑     ☐                 ☐          Serve package list
☑        ☑     ☐                 ☑          Serve package list
☑        ☑     ☑                 ☐          Serve package list
☑        ☑     ☑                 ☑          Serve package list
=======  ====  ================  =========  =========

Fallback = mirror
^^^^^^^^^^^^^^^^^

=======  ====  ================  =========  =========
Package  Read  Can update cache  Logged in  Response
=======  ====  ================  =========  =========
☐        ☐     ☐                 ☐          401 (to force upload of basic auth)
☐        ☐     ☐                 ☑          302 to fallback
☐        ☑     ☐                 ☐          401 (to force upload of basic auth)
☐        ☑     ☐                 ☑          302 to fallback
☐        ☑     ☑                 ☐          Upstream links that will download & cache
☐        ☑     ☑                 ☑          Upstream links that will download & cache
☑        ☐     ☐                 ☐          401 (to force upload of basic auth)
☑        ☐     ☐                 ☑          302 to fallback
☑        ☑     ☐                 ☐          401 (to force upload of basic auth)
☑        ☑     ☐                 ☑          Serve packages + redirect links [1]_
☑        ☑     ☑                 ☐          Serve package list + cache links [2]_
☑        ☑     ☑                 ☑          Serve package list + cache links [2]_
=======  ====  ================  =========  =========

.. [1] Serves any package versions in the DB, plus redirect links for all
       versions that are not in the DB.
.. [2] Serves any package versions in the DB, plus links that will download &
       cache for all versions that are not in the DB.
