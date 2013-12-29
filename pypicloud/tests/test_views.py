""" Unit tests for views """
import re
import pypicloud.views
from mock import MagicMock, patch
from pypicloud.models import Package, create_schema
from pypicloud.views import update, simple, all_packages, package_versions
from pyramid.testing import DummyRequest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from . import DBTest


class TestViews(DBTest):

    """ Unit tests for views """

    def _add_packages(self):
        """ Add three packages to db for testing """
        p1 = Package('a', '1', 'abc')
        p2 = Package('a', '2', 'abc2')
        p3 = Package('b', '2', 'bcd')
        self.db.add_all([p1, p2, p3])
        return p1, p2, p3

    def test_simple(self):
        """ Simple index view renders all unique package names in order """
        p1, p2, p3 = self._add_packages()
        uniques = list(sorted(set([p1.name, p2.name, p3.name])))

        pkgs = simple(self.request)
        self.request.fetch_packages_if_needed.assert_called()
        self.assertEquals(len(pkgs), 1)
        self.assertEquals(pkgs['pkgs'], uniques)

    def test_all_packages(self):
        """ /packages lists all packages """
        p1, p2, p3 = self._add_packages()

        pkgs = all_packages(self.request)
        self.request.fetch_packages_if_needed.assert_called()
        self.assertEquals(len(pkgs), 1)
        self.assertEquals(pkgs['pkgs'], [p1, p2, p3])

    def test_package_versions(self):
        """ List all package versions with a given name """
        p1, p2, _ = self._add_packages()

        self.request.registry.use_fallback = False
        self.request.subpath = [p1.name]
        pkgs = package_versions(self.request)
        self.request.fetch_packages_if_needed.assert_called()
        self.assertEquals(len(pkgs), 1)
        self.assertEquals(pkgs['pkgs'], [p1, p2])

    def test_package_versions_fallback(self):
        """ If no packages exist, redirect to fallback_url """
        self.request.registry.use_fallback = True
        fallback, pkg = 'http://pypi.com', 'missing'
        self.request.registry.fallback_url = fallback
        self.request.subpath = [pkg]
        response = package_versions(self.request)
        self.request.fetch_packages_if_needed.assert_called()
        self.assertEquals(response.location, '%s/%s/' % (fallback, pkg))


class TestUpdate(DBTest):
    """ Tests for update view """

    def setUp(self):
        super(TestUpdate, self).setUp()
        self.Key = patch.object(pypicloud.views, 'Key').start()  # pylint: disable=C0103
        self.prefix = '/mypkgs/'
        self.request.registry.prefix = self.prefix
        self.request.registry.prepend_hash = False
        self.content = MagicMock()
        self.content.filename = 'a-1.tar.gz'
        self.params = {
            'name': 'a',
            'version': '1',
            'content': self.content,
        }

    def test_upload(self):
        """ Uploading package sets metadata and sends to S3 """
        from mock import call
        name, version = self.params['name'], self.params['version']
        self.params[':action'] = 'file_upload'
        update(self.request)

        pkg = self.db.query(Package).first()
        self.assertEquals(pkg.name, name)
        self.assertEquals(pkg.version, version)
        self.assertEquals(pkg.path, self.prefix + self.content.filename)
        key = self.Key()
        key.set_contents_from_file.assert_called_with(self.content.file)
        key.set_metadata.assert_has_calls([call('name', name),
                                           call('version', version)])

    def test_upload_overwrite(self):
        """ Uploading a preexisting packages overwrites current package """
        name, version = self.params['name'], self.params['version']
        old_path = 'old_package_path-1.tar.gz'
        old_pkg = Package(name, version, old_path)
        self.db.add(old_pkg)
        self.params[':action'] = 'file_upload'
        key, old_key = MagicMock(), MagicMock()
        keys = [key, old_key]
        self.Key.side_effect = lambda x: keys.pop(0)
        update(self.request)

        count = self.db.query(Package).count()
        self.assertEquals(count, 1)
        pkg = self.db.query(Package).first()
        self.assertEquals(pkg.path, self.prefix + self.content.filename)

        self.assertEquals(old_key.key, old_path)
        old_key.delete.assert_called()

    def test_upload_prepend_hash(self):
        """ If prepend_hash = True, attach a hash to the file path """
        self.params[':action'] = 'file_upload'
        self.request.registry.prepend_hash = True
        update(self.request)

        pkg = self.db.query(Package).first()
        filename = pkg.path[len(self.prefix):]
        match = re.match(r'^[0-9a-f]{4}-.+$', filename)
        self.assertIsNotNone(match)

    def test_delete(self):
        """ Can delete a package """
        path = '/path/to/package.tar.gz'
        pkg = Package(self.params['name'], self.params['version'], path)
        self.db.add(pkg)
        self.params[':action'] = 'remove_pkg'
        update(self.request)

        count = self.db.query(Package).count()
        self.assertEquals(count, 0)

        key = self.Key()
        self.assertEquals(key.key, path)
        key.delete.assert_called()
