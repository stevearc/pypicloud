""" Tests for view security and auth """
import base64
import webtest
from mock import MagicMock
from passlib.hash import sha256_crypt  # pylint: disable=E0611
from pyramid.testing import DummyRequest

from . import DummyCache
from pypicloud import api, main


try:
    import unittest2 as unittest  # pylint: disable=F0401
except ImportError:
    import unittest

# pylint: disable=W0212


class TestListPackages(unittest.TestCase):

    """ Tests for package enumeration api """

    def test_has_permission(self):
        """ If user has permission, package is visible """
        request = DummyRequest()
        request.access = MagicMock()
        request.access.has_permission.return_value = True
        request.db = MagicMock()
        names = ['a', 'b', 'c']
        request.db.distinct.return_value = names
        ret = api.list_packages(request)
        self.assertEqual(ret, names)

    def test_filter_permission(self):
        """ Filter package names by permission """
        request = DummyRequest()
        request.access = MagicMock()
        request.access.has_permission = lambda x, y: x < 'c'
        request.db = MagicMock()
        names = ['a', 'b', 'c']
        request.db.distinct.return_value = names
        ret = api.list_packages(request)
        self.assertEqual(ret, ['a', 'b'])


def _simple_auth(username, password):
    """ Generate a basic auth header """
    base64string = base64.encodestring('%s:%s' %
                                       (username, password)).replace('\n', '')
    return {
        'Authorization': 'Basic %s' % base64string,
    }

test_cache = DummyCache(None)  # pylint: disable=C0103


class TestEndpointSecurity(unittest.TestCase):

    """
    Functional tests for view permissions

    These assert that a view is protected by specific permissions (e.g. read,
    write), not that the ACL for those permissions is correct.

    """
    @classmethod
    def setUpClass(cls):
        settings = {
            'pyramid.debug_authorization': True,
            'pypi.db': 'pypicloud.tests.test_security.test_cache',
            'db.url': 'sqlite://',
            'session.validate_key': 'a',
            'aws.access_key': 'abc',
            'aws.secret_key': 'def',
            'aws.bucket': 's3bucket',
            'user.user': sha256_crypt.encrypt('user'),
            'user.user2': sha256_crypt.encrypt('user2'),
            'package.pkg1.group.authenticated': 'r',
            'package.pkg1.group.brotatos': 'rw',
            'group.brotatos': ['user2'],
        }
        cls.app = webtest.TestApp(main({}, **settings))

    def setUp(self):
        test_cache.upload('pkg1', '1', '/path', None)

    def tearDown(self):
        test_cache.reset()
        self.app.reset()

    def test_simple_401(self):
        """ If simple endpoints unauthorized, ask pip for auth """
        response = self.app.get('/pypi/pkg1/', expect_errors=True)
        self.assertEqual(response.status_int, 401)

        response = self.app.get('/simple/pkg1/', expect_errors=True)
        self.assertEqual(response.status_int, 401)

    def test_simple_302(self):
        """ If simple endpoints unauthorized and package missing, redirect """
        response = self.app.get('/pypi/pkg2/', expect_errors=True)
        self.assertEqual(response.status_int, 302)

        response = self.app.get('/simple/pkg2/', expect_errors=True)
        self.assertEqual(response.status_int, 302)

    def test_simple(self):
        """ If simple endpoints authed, return a list of versions """
        response = self.app.get('/pypi/pkg1/',
                                headers=_simple_auth('user', 'user'))
        self.assertEqual(response.status_int, 200)

    def test_api_pkg_unauthed(self):
        """ /api/package/<pkg> requires read perms """
        response = self.app.get('/api/package/pkg1/', expect_errors=True)
        self.assertEqual(response.status_int, 403)

    def test_api_pkg_authed(self):
        """ /api/package/<pkg> requires read perms """
        response = self.app.get('/api/package/pkg1/',
                                headers=_simple_auth('user', 'user'))
        self.assertEqual(response.status_int, 200)

    def test_api_pkg_versions_unauthed(self):
        """ /api/package/<pkg>/version requires write perms """
        params = {
            'content': webtest.forms.Upload('filename.txt', 'datadatadata'),
        }
        response = self.app.post('/api/package/pkg1/2/', params,
                                 expect_errors=True,
                                 headers=_simple_auth('user', 'user'))
        self.assertEqual(response.status_int, 404)

    def test_api_pkg_versions_authed(self):
        """ /api/package/<pkg>/version requires write perms """
        params = {
            'content': webtest.forms.Upload('filename.txt', 'datadatadata'),
        }
        response = self.app.post('/api/package/pkg1/2/', params,
                                 headers=_simple_auth('user2', 'user2'))
        self.assertEqual(response.status_int, 200)

    def test_api_delete_unauthed(self):
        """ delete /api/package/<pkg>/version requires write perms """
        response = self.app.delete('/api/package/pkg1/1/', expect_errors=True,
                                   headers=_simple_auth('user', 'user'))
        self.assertEqual(response.status_int, 404)

    def test_api_delete_authed(self):
        """ delete /api/package/<pkg>/version requires write perms """
        response = self.app.delete('/api/package/pkg1/1/',
                                   headers=_simple_auth('user2', 'user2'))
        self.assertEqual(response.status_int, 200)

    def test_api_rebuild_admin(self):
        """ /api/rebuild requires admin """
        response = self.app.get('/api/rebuild/', expect_errors=True,
                                headers=_simple_auth('user2', 'user2'))
        self.assertEqual(response.status_int, 404)
