""" Unit tests for views """
import pypicloud.views
from mock import MagicMock, patch
from pypicloud.models import Package, create_schema
from pypicloud.views import update, simple, all_packages, package_versions
from pyramid.testing import DummyRequest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from unittest import TestCase


class TestViews(TestCase):

    """ Unit tests for views """

    def setUp(self):
        super(TestViews, self).setUp()
        engine = create_engine('sqlite:///:memory:')
        create_schema(engine)
        self.db = sessionmaker(bind=engine)()
        self.request = DummyRequest()
        self.request.url = 'http://myserver/path/'
        self.request.bucket = MagicMock()
        self.request.fetch_packages_if_needed = MagicMock()
        self.request.db = self.db
        self.params = {}
        self.request.param = lambda x: self.params[x]

    def tearDown(self):
        super(TestViews, self).tearDown()
        self.db.close()
        patch.stopall()

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

    def test_upload(self):
        """ Uploading package sets metadata and sends to S3 """
        from mock import call
        name, version = 'a', '1'
        content = MagicMock()
        content.filename = '%s-%s.tar.gz' % (name, version)
        self.params = {
            'name': name,
            'version': version,
            'content': content,
            ':action': 'file_upload',
        }
        key = patch.object(pypicloud.views, 'Key').start()()
        prefix = '/mypkgs/'
        self.request.registry.prefix = prefix
        update(self.request)

        pkg = self.db.query(Package).first()
        self.assertEquals(pkg.name, name)
        self.assertEquals(pkg.version, version)
        self.assertEquals(pkg.path, prefix + content.filename)
        key.set_contents_from_file.assert_called_with(content.file)
        key.set_metadata.assert_has_calls([call('name', name),
                                           call('version', version)])

    def test_upload_overwrite(self):
        """ Uploading a preexisting packages overwrites current package """
        name, version = 'a', '1'
        content = MagicMock()
        content.filename = '%s-%s.tar.gz' % (name, version)
        old_path = 'old_package_path-1.tar.gz'
        old_pkg = Package(name, version, old_path)
        self.db.add(old_pkg)
        self.params = {
            'name': name,
            'version': version,
            'content': content,
            ':action': 'file_upload',
        }
        key, old_key = MagicMock(), MagicMock()
        keys = [key, old_key]
        key_obj = patch.object(pypicloud.views, 'Key').start()
        key_obj.side_effect = lambda x: keys.pop(0)
        prefix = '/mypkgs/'
        self.request.registry.prefix = prefix
        update(self.request)

        count = self.db.query(Package).count()
        self.assertEquals(count, 1)
        pkg = self.db.query(Package).first()
        self.assertEquals(pkg.path, prefix + content.filename)

        self.assertEquals(old_key.key, old_path)
        old_key.delete.assert_called()

    def test_delete(self):
        """ Can delete a package """
        name, version, path = 'a', '1', 'pkg-1.tar.gz'
        pkg = Package(name, version, path)
        self.db.add(pkg)
        self.params = {
            'name': name,
            'version': version,
            ':action': 'remove_pkg',
        }
        key = patch.object(pypicloud.views, 'Key').start()()
        update(self.request)

        count = self.db.query(Package).count()
        self.assertEquals(count, 0)

        self.assertEquals(key.key, path)
        key.delete.assert_called()
