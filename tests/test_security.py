""" Tests for view security and auth """
import base64
import webtest
from collections import defaultdict
from passlib.hash import sha256_crypt  # pylint: disable=E0611

from . import DummyCache, DummyStorage, make_package
from pypicloud import main


try:
    import unittest2 as unittest  # pylint: disable=F0401
except ImportError:
    import unittest

# pylint: disable=W0212


def _simple_auth(username, password):
    """ Generate a basic auth header """
    base64string = base64.encodestring('%s:%s' %
                                       (username, password)).replace('\n', '')
    return {
        'Authorization': 'Basic %s' % base64string,
    }


class GlobalDummyStorage(DummyStorage):

    """ Dummy storage with class-level package storage """

    global_packages = {}

    def __init__(self, request=None, **kwargs):
        super(GlobalDummyStorage, self).__init__(request, **kwargs)
        self.packages = self.global_packages


class GlobalDummyCache(DummyCache):

    """ Dummy cache with class-level package storage """
    global_packages = defaultdict(list)

    def __init__(self, request=None, **kwargs):
        kwargs.setdefault('storage', GlobalDummyStorage)
        super(GlobalDummyCache, self).__init__(request, **kwargs)
        self.packages = self.global_packages


class TestEndpointSecurity(unittest.TestCase):

    """
    Functional tests for view permissions

    These assert that a view is protected by specific permissions (e.g. read,
    write), not that the ACL for those permissions is correct.

    """
    @classmethod
    def setUpClass(cls):
        cls.package = package = make_package()
        settings = {
            'pyramid.debug_authorization': True,
            'pypi.db': 'tests.test_security.GlobalDummyCache',
            'pypi.storage': 'tests.test_security.GlobalDummyStorage',
            'session.validate_key': 'a',
            'user.user': sha256_crypt.encrypt('user'),
            'user.user2': sha256_crypt.encrypt('user2'),
            'package.%s.group.authenticated' % package.name: 'r',
            'package.%s.group.brotatos' % package.name: 'rw',
            'group.brotatos': ['user2'],
        }
        app = main({}, **settings)
        cls.app = webtest.TestApp(app)

    def setUp(self):
        cache = GlobalDummyCache()
        cache.upload(self.package.filename, None, self.package.name,
                     self.package.version)

    def tearDown(self):
        GlobalDummyCache.global_packages.clear()
        GlobalDummyStorage.global_packages.clear()
        self.app.reset()

    def test_simple_401(self):
        """ If simple endpoints unauthorized, ask pip for auth """
        response = self.app.get('/pypi/%s/' % self.package.name,
                                expect_errors=True)
        self.assertEqual(response.status_int, 401)

        response = self.app.get('/simple/%s/' % self.package.name,
                                expect_errors=True)
        self.assertEqual(response.status_int, 401)

    def test_simple_unauth_missing(self):
        """ If simple endpoints unauthorized and package missing, 401 """
        response = self.app.get('/pypi/pkg2/', expect_errors=True)
        self.assertEqual(response.status_int, 401)

        response = self.app.get('/simple/pkg2/', expect_errors=True)
        self.assertEqual(response.status_int, 401)

    def test_simple_auth_missing(self):
        """ If simple endpoints authorized and package missing, redirect """
        response = self.app.get('/pypi/pkg2/', expect_errors=True,
                                headers=_simple_auth('user', 'user'))
        self.assertEqual(response.status_int, 302)

        response = self.app.get('/simple/pkg2/', expect_errors=True,
                                headers=_simple_auth('user', 'user'))
        self.assertEqual(response.status_int, 302)

    def test_simple(self):
        """ If simple endpoints authed, return a list of versions """
        response = self.app.get('/pypi/%s/' % self.package.name,
                                headers=_simple_auth('user', 'user'))
        self.assertEqual(response.status_int, 200)

    def test_api_pkg_unauthed(self):
        """ /api/package/<pkg> requires read perms """
        response = self.app.get('/api/package/%s/' % self.package.name,
                                expect_errors=True)
        self.assertEqual(response.status_int, 401)

    def test_api_pkg_authed(self):
        """ /api/package/<pkg> requires read perms """
        response = self.app.get('/api/package/%s/' % self.package.name,
                                headers=_simple_auth('user', 'user'))
        self.assertEqual(response.status_int, 200)

    def test_api_pkg_versions_unauthed(self):
        """ /api/package/<pkg>/<filename> requires write perms """
        params = {
            'content': webtest.forms.Upload('filename.txt', 'datadatadata'),
        }
        url = '/api/package/%s/%s/' % (self.package.name,
                                       self.package.filename)
        response = self.app.post(url, params, expect_errors=True,
                                 headers=_simple_auth('user', 'user'))
        self.assertEqual(response.status_int, 403)

    def test_api_pkg_versions_authed(self):
        """ /api/package/<pkg>/<filename> requires write perms """
        package = make_package(self.package.name, '1.5')
        params = {
            'content': webtest.forms.Upload(package.filename, 'datadatadata'),
        }
        url = '/api/package/%s/%s' % (package.name, package.filename)
        response = self.app.post(url, params,
                                 headers=_simple_auth('user2', 'user2'))
        self.assertEqual(response.status_int, 200)

    def test_api_delete_unauthed(self):
        """ delete /api/package/<pkg>/<filename> requires write perms """
        url = '/api/package/%s/%s' % (self.package.name,
                                      self.package.filename)
        response = self.app.delete(url, expect_errors=True,
                                   headers=_simple_auth('user', 'user'))
        self.assertEqual(response.status_int, 403)

    def test_api_delete_authed(self):
        """ delete /api/package/<pkg>/<filename> requires write perms """
        url = '/api/package/%s/%s' % (self.package.name,
                                      self.package.filename)
        response = self.app.delete(url,
                                   headers=_simple_auth('user2', 'user2'))
        self.assertEqual(response.status_int, 200)

    def test_api_rebuild_admin(self):
        """ /api/rebuild requires admin """
        response = self.app.get('/api/rebuild/', expect_errors=True,
                                headers=_simple_auth('user2', 'user2'))
        self.assertEqual(response.status_int, 404)
