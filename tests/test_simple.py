""" Unit tests for the simple endpoints """
from types import MethodType

from mock import MagicMock, patch

from . import MockServerTest, make_package
from pypicloud.auth import _request_login
from pypicloud.views.simple import (upload, search, simple, package_versions,
                                    get_fallback_packages)


try:
    import unittest2 as unittest  # pylint: disable=F0401
except ImportError:
    import unittest


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
        pkg = upload(self.request, content, name, version)

        self.assertEquals(pkg, self.request.db.packages[content.filename])

    def test_upload_bad_action(self):
        """ Upload endpoint only respects 'file_upload' action """
        self.params = {
            ':action': 'blah',
        }
        name, version, content = 'foo', 'bar', 'baz'
        response = upload(self.request, content, name, version)
        self.assertEqual(response.status_code, 400)

    def test_upload_no_write_permission(self):
        """ Upload without write permission returns 403 """
        self.params = {
            ':action': 'file_upload',
        }
        name, version, content = 'foo', 'bar', MagicMock()
        content.filename = 'foo-1.2.tar.gz'
        self.request.access.has_permission.return_value = False
        response = upload(self.request, content, name, version)
        self.assertEqual(response, self.request.forbid())

    def test_upload_duplicate(self):
        """ Uploading a duplicate package returns 400 """
        self.params = {
            ':action': 'file_upload',
        }
        name, version, content = 'foo', '1.2', MagicMock()
        content.filename = 'foo-1.2.tar.gz'
        self.db.upload(content.filename, content, name)
        response = upload(self.request, content, name, version)
        self.assertEqual(response.status_code, 400)

    def test_search(self):
        """ Pip search executes successfully """
        self.params = {
            ':action': 'file_upload',
        }
        name1, version1, content1 = 'foo', '1.1', MagicMock()
        content1.filename = 'bar-1.2.tar.gz'
        name2, version2, content2 = 'bar', '1.0', MagicMock()
        content2.filename = 'bar-1.2.tar.gz'
        upload(self.request, content1, name1, version1)
        upload(self.request, content2, name2, version2)

        criteria = {
            'name': ['foo'],
            'summary': ['foo']
        }
        response = search(self.request, criteria, 'or')
        expected = [
            {
                'name': 'foo',
                'version': '1.1',
                'summary': None
            }
        ]
        self.assertListEqual(response, expected)

    def test_list(self):
        """ Simple list should return api call """
        self.request.db = MagicMock()
        self.request.db.distinct.return_value = ['a', 'b', 'c']
        self.request.access.has_permission.side_effect = lambda x, _: x == 'b'
        result = simple(self.request)
        self.assertEqual(result, {'pkgs': ['b']})

    def test_fallback_packages(self):
        """ Fetch fallback packages """
        self.request.locator = MagicMock()
        version = '1.1'
        name = 'foo'
        filename = '%s-%s.tar.gz' % (name, version)
        url = 'http://pypi.python.org/pypi/%s/%s' % (name, filename)
        wheelname = '%s-%s.whl' % (name, version)
        wheel_url = 'http://pypi.python.org/pypi/%s/%s' % (name, wheelname)
        dist = MagicMock()
        dist.name = name
        self.request.locator.get_project.return_value = {
            version: dist,
            'urls': {
                version: [url, wheel_url]
            }
        }
        self.request.app_url = MagicMock()
        pkgs = get_fallback_packages(self.request, 'foo', False)
        self.request.app_url.assert_any_call('api', 'package', name, filename)
        self.request.app_url.assert_any_call('api', 'package', name, wheelname)
        self.assertEqual(pkgs, {
            filename: self.request.app_url(),
            wheelname: self.request.app_url(),
        })

    def test_fallback_packages_redirect(self):
        """ Fetch fallback packages with redirect URLs """
        self.request.locator = MagicMock()
        version = '1.1'
        name = 'foo'
        filename = '%s-%s.tar.gz' % (name, version)
        url = 'http://pypi.python.org/pypi/%s/%s' % (name, filename)
        wheelname = '%s-%s.whl' % (name, version)
        wheel_url = 'http://pypi.python.org/pypi/%s/%s' % (name, wheelname)
        dist = MagicMock()
        dist.name = name
        self.request.locator.get_project.return_value = {
            version: dist,
            'urls': {
                version: [url, wheel_url]
            }
        }
        pkgs = get_fallback_packages(self.request, 'foo')
        self.assertEqual(pkgs, {
            filename: url,
            wheelname: wheel_url,
        })


class PackageReadTestBase(unittest.TestCase):

    """ Base class test for reading packages """
    fallback = None
    always_show_upstream = None
    fallback_url = 'http://pypi.python.org/pypi/'

    @classmethod
    def setUpClass(cls):
        cls.package = make_package()
        cls.package2 = make_package(version='2.1')

    def setUp(self):
        get = patch('pypicloud.views.simple.get_fallback_packages').start()
        p2 = self.package2
        self.fallback_packages = get.return_value = {
            p2.filename: self.fallback_url + p2.filename
        }

    def tearDown(self):
        patch.stopall()

    def get_request(self, package=None, perms='', user=None):
        """ Construct a fake request """
        request = MagicMock()
        request.registry.fallback = self.fallback
        request.registry.always_show_upstream = self.always_show_upstream
        request.registry.fallback_url = self.fallback_url
        request.userid = user
        request.access.can_update_cache = lambda: 'c' in perms
        request.access.has_permission.side_effect = lambda n, p: 'r' in perms
        request.is_logged_in = user is not None
        request.request_login = MethodType(
            _request_login,
            request,
            request.__class__)
        pkgs = []
        if package is not None:
            pkgs.append(package)
        request.db.all.return_value = pkgs
        return request

    def should_ask_auth(self, request):
        """ When requested, the endpoint should return a 401 """
        ret = package_versions(self.package, request)
        self.assertEqual(ret.status_code, 401)

    def should_404(self, request):
        """ When requested, the endpoint should return a 404 """
        ret = package_versions(self.package, request)
        self.assertEqual(ret.status_code, 404)

    def should_403(self, request):
        """ When requested, the endpoint should return a 403 """
        ret = package_versions(self.package, request)
        self.assertEqual(ret.status_code, 403)

    def should_redirect(self, request):
        """ When requested, the endpoint should redirect to the fallback """
        ret = package_versions(self.package, request)
        self.assertEqual(ret.status_code, 302)
        self.assertEqual(ret.location,
                         self.fallback_url + self.package.name + '/')

    def should_serve(self, request):
        """ When requested, the endpoint should serve the packages """
        ret = package_versions(self.package, request)
        self.assertEqual(ret, {'pkgs': {
            self.package.filename: self.package.get_url(request),
        }})

    def should_cache(self, request):
        """ When requested, the endpoint should serve the fallback packages """
        ret = package_versions(self.package, request)
        self.assertEqual(ret, {'pkgs': self.fallback_packages})

    def should_serve_and_redirect(self, request):
        """ Should serve mixture of package urls and redirect urls """
        ret = package_versions(self.package, request)
        f2name = self.package2.filename
        self.assertEqual(ret, {'pkgs': {
            self.package.filename: self.package.get_url(request),
            f2name: self.fallback_packages[f2name],
        }})


class TestRedirect(PackageReadTestBase):

    """ Test reading packages with fallback=redirect and always_show_upstream=false """
    fallback = 'redirect'
    always_show_upstream = False

    def test_no_package_no_read_no_user(self):
        """ No package, no read perms, no user """
        self.should_redirect(self.get_request())

    def test_no_package_no_read_user(self):
        """ No package, no read perms, user """
        self.should_redirect(self.get_request(user='foo'))

    def test_no_package_read_no_user(self):
        """ No package, read perms, no user """
        self.should_redirect(self.get_request(perms='r'))

    def test_no_package_read_user(self):
        """ No package, read perms, user """
        self.should_redirect(self.get_request(perms='r', user='foo'))

    def test_no_package_write_no_user(self):
        """ No package, write perms, no user """
        self.should_redirect(self.get_request(perms='rc'))

    def test_no_package_write_user(self):
        """ No package, write perms, user """
        self.should_redirect(self.get_request(perms='rc', user='foo'))

    def test_package_no_read_no_user(self):
        """ Package, no read perms, no user. """
        self.should_ask_auth(self.get_request(self.package, ''))

    def test_package_no_read_user(self):
        """ Package, no read perms, user. """
        self.should_redirect(self.get_request(self.package, '', 'foo'))

    def test_package_read_no_user(self):
        """ Package, read perms, no user. """
        self.should_serve(self.get_request(self.package, 'r'))

    def test_package_read_user(self):
        """ Package, read perms, user. """
        self.should_serve(self.get_request(self.package, 'r', 'foo'))

    def test_package_write_no_user(self):
        """ Package, write perms, no user. """
        self.should_serve(self.get_request(self.package, 'rc'))

    def test_package_write_user(self):
        """ Package, write perms, user. """
        self.should_serve(self.get_request(self.package, 'rc', 'foo'))


class TestRedirectAlwaysShow(PackageReadTestBase):

    """ Test reading packages with fallback=redirect and always_show_upstream=truue """
    fallback = 'redirect'
    always_show_upstream = True

    def test_no_package_no_read_no_user(self):
        """ No package, no read perms, no user """
        self.should_redirect(self.get_request())

    def test_no_package_no_read_user(self):
        """ No package, no read perms, user """
        self.should_redirect(self.get_request(user='foo'))

    def test_no_package_read_no_user(self):
        """ No package, read perms, no user """
        self.should_redirect(self.get_request(perms='r'))

    def test_no_package_read_user(self):
        """ No package, read perms, user """
        self.should_redirect(self.get_request(perms='r', user='foo'))

    def test_no_package_write_no_user(self):
        """ No package, write perms, no user """
        self.should_redirect(self.get_request(perms='rc'))

    def test_no_package_write_user(self):
        """ No package, write perms, user """
        self.should_redirect(self.get_request(perms='rc', user='foo'))

    def test_package_no_read_no_user(self):
        """ Package, no read perms, no user. """
        self.should_ask_auth(self.get_request(self.package, ''))

    def test_package_no_read_user(self):
        """ Package, no read perms, user. """
        self.should_redirect(self.get_request(self.package, '', 'foo'))

    def test_package_read_no_user(self):
        """ Package, read perms, no user. """
        req = self.get_request(self.package, 'r', 'foo')
        self.should_serve_and_redirect(req)

    def test_package_read_user(self):
        """ Package, read perms, user. """
        req = self.get_request(self.package, 'r', 'foo')
        self.should_serve_and_redirect(req)

    def test_package_write_no_user(self):
        """ Package, write perms, no user. """
        req = self.get_request(self.package, 'r', 'foo')
        self.should_serve_and_redirect(req)

    def test_package_write_user(self):
        """ Package, write perms, user. """
        req = self.get_request(self.package, 'r', 'foo')
        self.should_serve_and_redirect(req)


class TestCache(PackageReadTestBase):

    """ Test reading packages with fallback=cache and always_show_upstream=false """
    fallback = 'cache'
    always_show_upstream = False

    def test_no_package_no_read_no_user(self):
        """ No package, no read perms, no user """
        self.should_ask_auth(self.get_request())

    def test_no_package_no_read_user(self):
        """ No package, no read perms, user """
        self.should_404(self.get_request(user='foo'))

    def test_no_package_read_no_user(self):
        """ No package, read perms, no user """
        self.should_ask_auth(self.get_request(perms='r'))

    def test_no_package_read_user(self):
        """ No package, read perms, user """
        self.should_404(self.get_request(perms='r', user='foo'))

    def test_no_package_write_no_user(self):
        """ No package, write perms, no user """
        self.should_cache(self.get_request(perms='rc'))

    def test_no_package_write_user(self):
        """ No package, write perms, user """
        self.should_cache(self.get_request(perms='rc', user='foo'))

    def test_package_no_read_no_user(self):
        """ Package, no read perms, no user. """
        self.should_ask_auth(self.get_request(self.package, ''))

    def test_package_no_read_user(self):
        """ Package, no read perms, user. """
        self.should_404(self.get_request(self.package, '', 'foo'))

    def test_package_read_no_user(self):
        """ Package, read perms, no user. """
        self.should_serve(self.get_request(self.package, 'r'))

    def test_package_read_user(self):
        """ Package, read perms, user. """
        self.should_serve(self.get_request(self.package, 'r', 'foo'))

    def test_package_write_no_user(self):
        """ Package, write perms, no user. """
        self.should_serve(self.get_request(self.package, 'rc'))

    def test_package_write_user(self):
        """ Package, write perms, user. """
        self.should_serve(self.get_request(self.package, 'rc', 'foo'))


class TestCacheAlwaysShow(PackageReadTestBase):

    """ Test reading packages with fallback=cache and always_show_upstream=true """
    fallback = 'cache'
    always_show_upstream = True

    def test_no_package_no_read_no_user(self):
        """ No package, no read perms, no user """
        self.should_ask_auth(self.get_request())

    def test_no_package_no_read_user(self):
        """ No package, no read perms, user """
        self.should_redirect(self.get_request(user='foo'))

    def test_no_package_read_no_user(self):
        """ No package, read perms, no user """
        self.should_ask_auth(self.get_request(perms='r'))

    def test_no_package_read_user(self):
        """ No package, read perms, user """
        self.should_redirect(self.get_request(perms='r', user='foo'))

    def test_no_package_write_no_user(self):
        """ No package, write perms, no user """
        self.should_cache(self.get_request(perms='rc'))

    def test_no_package_write_user(self):
        """ No package, write perms, user """
        self.should_cache(self.get_request(perms='rc', user='foo'))

    def test_package_no_read_no_user(self):
        """ Package, no read perms, no user. """
        self.should_ask_auth(self.get_request(self.package, ''))

    def test_package_no_read_user(self):
        """ Package, no read perms, user. """
        self.should_redirect(self.get_request(self.package, '', 'foo'))

    def test_package_read_no_user(self):
        """ Package, read perms, no user. """
        self.should_ask_auth(self.get_request(self.package, 'r'))

    def test_package_read_user(self):
        """ Package, read perms, user. """
        req = self.get_request(self.package, 'r', 'foo')
        self.should_serve_and_redirect(req)

    def test_package_write_no_user(self):
        """ Package, write perms, no user. """
        # Should serve package urls and fallback urls
        req = self.get_request(self.package, 'rc')
        ret = package_versions(self.package, req)
        p2 = self.package2
        self.assertEqual(ret, {'pkgs': {
            self.package.filename: self.package.get_url(req),
            self.package2.filename: self.fallback_packages[p2.filename],
        }})

    def test_package_write_user(self):
        """ Package, write perms, user. """
        # Should serve package urls and fallback urls
        req = self.get_request(self.package, 'rc', 'foo')
        ret = package_versions(self.package, req)
        p2 = self.package2
        self.assertEqual(ret, {'pkgs': {
            self.package.filename: self.package.get_url(req),
            self.package2.filename: self.fallback_packages[p2.filename],
        }})


class TestNoFallback(PackageReadTestBase):

    """ Tests for reading packages with fallback=none """
    fallback = 'none'

    def test_no_package_no_read_no_user(self):
        """ No package, no read perms, no user """
        self.should_ask_auth(self.get_request())

    def test_no_package_no_read_user(self):
        """ No package, no read perms, user """
        self.should_404(self.get_request(user='foo'))

    def test_no_package_read_no_user(self):
        """ No package, read perms, no user """
        self.should_404(self.get_request(perms='r'))

    def test_no_package_read_user(self):
        """ No package, read perms, user """
        self.should_404(self.get_request(perms='r', user='foo'))

    def test_no_package_write_no_user(self):
        """ No package, write perms, no user """
        self.should_404(self.get_request(perms='rc'))

    def test_no_package_write_user(self):
        """ No package, write perms, user """
        self.should_404(self.get_request(perms='rc', user='foo'))

    def test_package_no_read_no_user(self):
        """ Package, no read perms, no user. """
        self.should_ask_auth(self.get_request(self.package, ''))

    def test_package_no_read_user(self):
        """ Package, no read perms, user. """
        self.should_404(self.get_request(self.package, '', 'foo'))

    def test_package_read_no_user(self):
        """ Package, read perms, no user. """
        self.should_serve(self.get_request(self.package, 'r'))

    def test_package_read_user(self):
        """ Package, read perms, user. """
        self.should_serve(self.get_request(self.package, 'r', 'foo'))

    def test_package_write_no_user(self):
        """ Package, write perms, no user. """
        self.should_serve(self.get_request(self.package, 'rc'))

    def test_package_write_user(self):
        """ Package, write perms, user. """
        self.should_serve(self.get_request(self.package, 'rc', 'foo'))
