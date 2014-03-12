Extending PyPICloud
===================
Certain parts of PyPICloud were created to be pluggable. The
storage backend, cache database, and access control backend can all be replaced
very easily.

The steps for extending are:

1. Create a new implementation that subclasses the base class (:class:`~pypicloud.cache.base.ICache`, :class:`~pypicloud.storage.base.IStorage`, :class:`~pypicloud.access.base.IAccessBackend`/:class:`~pypicloud.access.base.IMutableAccessBackend`)
2. Put that implementation in a package and install that package in the same virtualenv as PyPICloud
3. Pass in a dotted path to that implementation for the approprate config field (e.g. ``pypi.db``)
