""" Unit tests for the simple endpoints """
from datetime import datetime

from distlib.database import Distribution
from mock import MagicMock, patch
from pyramid.httpexceptions import HTTPFound

from . import MockServerTest
from pypicloud.models import Package
from pypicloud.route import SimplePackageResource
from pypicloud.views.simple import upload, simple, package_versions


class TestSimple(MockServerTest):

    """ Unit tests for the /simple endpoints """

    def setUp(self):
        super(TestSimple, self).setUp()
        self.request.access = MagicMock()

    def test_upload(self):
        """ Upload endpoint returns the result of api call """
        self.params = {
            ':action': 'file_upload',
        }
        name, version, content = 'foo', 'bar', MagicMock()
        content.filename = 'foo-1.2.tar.gz'
        pkg = upload(self.request, name, version, content)

        self.assertEquals(pkg, self.request.db.packages[content.filename])

    def test_upload_bad_action(self):
        """ Upload endpoint only respects 'file_upload' action """
        self.params = {
            ':action': 'blah',
        }
        name, version, content = 'foo', 'bar', 'baz'
        response = upload(self.request, name, version, content)
        self.assertEqual(response.status_code, 400)

    def test_upload_no_write_permission(self):
        """ Upload without write permission returns 403 """
        self.params = {
            ':action': 'file_upload',
        }
        name, version, content = 'foo', 'bar', MagicMock()
        content.filename = 'foo-1.2.tar.gz'
        self.request.access.has_permission.return_value = False
        response = upload(self.request, name, version, content)
        self.assertEqual(response, self.request.forbid())

    def test_upload_duplicate(self):
        """ Uploading a duplicate package returns 400 """
        self.params = {
            ':action': 'file_upload',
        }
        name, version, content = 'foo', '1.2', MagicMock()
        content.filename = 'foo-1.2.tar.gz'
        self.db.upload(content.filename, content, name)
        response = upload(self.request, name, version, content)
        self.assertEqual(response.status_code, 400)

    def test_list(self):
        """ Simple list should return api call """
        self.request.db = MagicMock()
        self.request.db.distinct.return_value = ['a', 'b', 'c']
        self.request.access.has_permission.side_effect = lambda x, _: x == 'b'
        result = simple(self.request)
        self.assertEqual(result, {'pkgs': ['b']})

    def test_list_versions(self):
        """ Listing package versions should return api call """
        self.request.registry.use_fallback = False
        pkg = Package('mypkg', '1.1', 'mypkg-1.1.tar.gz', datetime.utcnow())
        self.request.db.upload(pkg.filename, None)
        context = SimplePackageResource(self.request, 'mypkg')
        self.request.app_url = MagicMock()
        result = package_versions(context, self.request)
        self.assertEqual(result, {'pkgs': {pkg.filename:
                                           self.request.app_url()}})

    def test_list_versions_fallback_redirect(self):
        """ Listing package versions can fall back to external url """
        self.request.registry.fallback = 'redirect'
        fb = self.request.registry.fallback_url = 'http://pypi.com'
        context = SimplePackageResource(self.request, 'mypkg')
        result = package_versions(context, self.request)
        url = fb + '/' + context.name + '/'
        self.assertTrue(isinstance(result, HTTPFound))
        self.assertEqual(result.location, url)

    def test_list_versions_fallback_none(self):
        """ Listing package versions with no fallback returns 404 """
        self.request.registry.fallback = 'none'
        context = SimplePackageResource(self.request, 'mypkg')
        result = package_versions(context, self.request)
        self.assertEqual(result.status_code, 404)


class TestSimpleCacheFallback(MockServerTest):

    """ Unit tests for /simple endpoints when fallback = 'cache' """

    def setUp(self):
        super(TestSimpleCacheFallback, self).setUp()
        self.request.access = MagicMock()
        self.request.registry.fallback = 'cache'
        self.fb = self.request.registry.fallback_url = 'http://pypi.com'
        self.context = SimplePackageResource(self.request, 'mypkg')

    def test_no_perms(self):
        """ If not in the update_cache groups, return 403 """
        self.request.access.can_update_cache.return_value = False
        result = package_versions(self.context, self.request)
        self.assertEqual(result, self.request.forbid())

    def test_no_dists(self):
        """ If no distributions found at fallback, return 404 """
        locator = self.request.locator = MagicMock()
        locator.get_project.return_value = {
            'urls': {}
        }
        result = package_versions(self.context, self.request)
        self.assertEqual(result.status_code, 404)

    def test_rename_dists(self):
        """ Rename distribution urls to localhost """
        dist = MagicMock(spec=Distribution)
        filename = 'pkg-1.1.tar.gz'
        dist.source_url = 'http://fallback.com/simple/%s' % filename
        dist.name = 'pkg'
        locator = self.request.locator = MagicMock()
        locator.get_project.return_value = {
            '1.1': dist,
            'urls': {
                '1.1': set([dist.source_url])
            }
        }
        self.request.app_url = lambda *x: '/'.join(x)
        result = package_versions(self.context, self.request)
        self.assertEqual(result, {'pkgs': {
            filename: 'api/package/pkg/pkg-1.1.tar.gz',
        }})
