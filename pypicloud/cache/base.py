""" Base class for all cache implementations """
from datetime import datetime

import logging
from pkg_resources import parse_version
from pyramid.settings import asbool

import os
from pypicloud.models import Package, normalize_name
from pypicloud.storage import get_storage_impl


LOG = logging.getLogger(__name__)


class ICache(object):

    """ Base class for a caching database that stores package metadata """

    dbtype = None
    package_class = Package
    storage_impl = None

    def __init__(self, request=None):
        self.request = request
        self.storage = self.storage_impl(request)

    @classmethod
    def reload_if_needed(cls):
        """
        Reload packages from storage backend if cache is empty

        This will be called when the server first starts

        """
        cache = cls()
        if len(cache.distinct()) == 0:
            LOG.info("Cache is empty. Rebuilding from S3...")
            cache.reload_from_storage()
            LOG.info("Cache repopulated")
        return cache

    @classmethod
    def configure(cls, settings):
        """ Configure the cache method with app settings """
        cls.storage_impl = get_storage_impl(settings)
        cls.allow_overwrite = asbool(settings.get('pypi.allow_overwrite',
                                                  False))

    def get_url(self, package):
        """ Pass through to storage """
        url, changed = self.storage.get_url(package)
        if changed:
            self.save(package)
        return url

    def download_response(self, package):
        """ Pass through to storage """
        return self.storage.download_response(package)

    def reload_from_storage(self):
        """ Make sure local database is populated with packages """
        self.clear_all()
        packages = self.storage.list(self.package_class)
        for pkg in packages:
            self.save(pkg)

    @staticmethod
    def normalize_name(name):
        """ Normalize a python package name """
        return normalize_name(name)

    def upload(self, name, version, filename, data):
        """ Save this package to the storage mechanism and to the cache """
        name = self.normalize_name(name)
        filename = os.path.basename(filename)
        old_pkg = self.fetch(name, version)
        if old_pkg is not None and not self.allow_overwrite:
            raise ValueError("Package '%s==%s' already exists!" %
                             (name, version))
        path = self.storage.upload(name, version, filename, data)
        new_pkg = self.package_class(name, version, path, datetime.utcnow())
        # If we're overwriting the same package but with a different path,
        # delete the old path
        if old_pkg is not None and new_pkg.path != old_pkg.path:
            self.storage.delete(old_pkg.path)
        self.save(new_pkg)
        return new_pkg

    def delete(self, package):
        """ Delete this package from the database and from storage """
        self.storage.delete(package.path)
        self.clear(package)

    def fetch(self, name, version):
        """ Get matching package if it exists """
        return self._fetch(self.normalize_name(name), version)

    def _fetch(self, name, version):
        """ Override this method to implement 'fetch' """
        raise NotImplementedError

    def all(self, name):
        """ Search for all versions of a package """
        if name is not None:
            name = self.normalize_name(name)
        return self._all(name)

    def _all(self, name):
        """ Override this method to implement 'all' """
        raise NotImplementedError

    def distinct(self):
        """ Get all distinct package names """
        raise NotImplementedError

    def summary(self):
        """
        Summarize package metadata

        Returns
        -------
        packages : list
            List of package dicts, each of which contains 'name', 'stable',
            'unstable', and 'last_modified'.

        """
        packages = []
        for name in self.distinct():
            pkg = {
                'name': name,
                'stable': None,
                'unstable': '0',
                'last_modified': datetime.fromtimestamp(0),
            }
            for package in self.all(name):
                if not package.is_prerelease:
                    if pkg['stable'] is None:
                        pkg['stable'] = package.version
                    else:
                        pkg['stable'] = max(pkg['stable'], package.version,
                                            key=parse_version)
                pkg['unstable'] = max(pkg['unstable'], package.version,
                                      key=parse_version)
                pkg['last_modified'] = max(pkg['last_modified'],
                                           package.last_modified)
            packages.append(pkg)

        return packages

    def clear(self, package):
        """ Remove this package from the caching database """
        raise NotImplementedError

    def clear_all(self):
        """ Clear all cached packages from the database """
        raise NotImplementedError

    def save(self, package):
        """ Save this package to the database """
        raise NotImplementedError
