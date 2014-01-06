""" Unit tests for views """
import re

from mock import MagicMock, patch
from pypicloud.models import Package
from pyramid.httpexceptions import HTTPBadRequest

from . import DBTest, RedisTest
from pypicloud import api


class UpdateTestMixin(object):

    """ Setup method for update tests """

    def setUp(self):
        super(UpdateTestMixin, self).setUp()
        self.Key = patch.object(api, 'Key').start()  # pylint: disable=C0103
        self.prefix = '/mypkgs/'
        self.request.registry.prefix = self.prefix
        self.request.registry.prepend_hash = False
        self.request.registry.allow_overwrite = True
        self.content = MagicMock()
        self.content.filename = 'a-1.tar.gz'


class TestUpdate(UpdateTestMixin, DBTest):

    """ Tests for update view """

    def test_upload(self):
        """ Uploading package sets metadata and sends to S3 """
        from mock import call
        name, version = 'a', '1'
        api.upload_package(self.request, name, version, self.content)

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
        name, version = 'a', '1'
        old_path = 'old_package_path-1.tar.gz'
        old_pkg = Package(name, version, old_path)
        self.db.add(old_pkg)
        key, old_key = MagicMock(), MagicMock()
        keys = [key, old_key]
        self.Key.side_effect = lambda x: keys.pop(0)
        api.upload_package(self.request, name, version, self.content)

        count = self.db.query(Package).count()
        self.assertEquals(count, 1)
        pkg = self.db.query(Package).first()
        self.assertEquals(pkg.path, self.prefix + self.content.filename)

        self.assertEquals(old_key.key, old_path)
        old_key.delete.assert_called()

    def test_upload_no_overwrite(self):
        """ If allow_overwrite=False duplicate package throws exception """
        name, version = 'a', '1'
        pkg = Package(name, version, 'any/path.tar.gz')
        self.db.add(pkg)
        self.request.registry.allow_overwrite = False
        with self.assertRaises(HTTPBadRequest):
            api.upload_package(self.request, name, version, self.content)

    def test_upload_prepend_hash(self):
        """ If prepend_hash = True, attach a hash to the file path """
        name, version = 'a', '1'
        self.request.registry.prepend_hash = True
        api.upload_package(self.request, name, version, self.content)

        pkg = self.db.query(Package).first()
        filename = pkg.path[len(self.prefix):]
        match = re.match(r'^[0-9a-f]{4}:.+$', filename)
        self.assertIsNotNone(match)

    def test_delete(self):
        """ Can delete a package """
        path = '/path/to/package.tar.gz'
        pkg = Package('a', '1', path)
        self.db.add(pkg)
        api.delete_package(self.request, pkg.name, pkg.version)

        count = self.db.query(Package).count()
        self.assertEquals(count, 0)

        key = self.Key()
        self.assertEquals(key.key, path)
        key.delete.assert_called()


class TestUpdateRedis(UpdateTestMixin, RedisTest):

    """ Test the update commands with a redis backend """

    def test_upload(self):
        """ Uploading with redis backend stores record in redis """
        name, version = 'a', '1'
        api.upload_package(self.request, name, version, self.content)

        pkg = Package.fetch(self.request, name, version)
        self.assertEquals(pkg.name, name)
        self.assertEquals(pkg.version, version)
        self.assertEquals(pkg.path, self.prefix + self.content.filename)

    def test_delete(self):
        """ Can delete from redis backend """
        path = '/path/to/package.tar.gz'
        pkg = Package('a', '1', path)
        pkg.save(self.request)
        api.delete_package(self.request, pkg.name, pkg.version)

        new_pkg = Package.fetch(self.request, pkg.name, pkg.version)
        self.assertIsNone(new_pkg)
