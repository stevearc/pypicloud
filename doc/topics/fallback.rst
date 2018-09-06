:orphan:

.. _fallback_detail:

Fallbacks
=========
Below is a detailed table for each possible fallback setting. The columns
indicate whether or not any package of that name is stored in pypicloud, whether
the user has read permissions, whether the user has `can_update_cache`
permissions, and whether the user is logged in.


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

Fallback = redirect, always_show_upstream = False
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

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

Fallback = redirect, always_show_upstream = True
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

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
☑        ☑     ☐                 ☐          Serve packages + redirect links [1]_
☑        ☑     ☐                 ☑          Serve packages + redirect links [1]_
☑        ☑     ☑                 ☐          Serve packages + redirect links [1]_
☑        ☑     ☑                 ☑          Serve packages + redirect links [1]_
=======  ====  ================  =========  =========

Fallback = cache, always_show_upstream = False
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

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

Fallback = cache, always_show_upstream = True
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

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
