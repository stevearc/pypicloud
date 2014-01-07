""" Tests for view security and auth """
import base64
import boto.s3.key
import transaction
import webtest
from mock import patch
from passlib.hash import sha256_crypt  # pylint: disable=E0611
from pypicloud.models import Package
from pypicloud.route import Root
from pyramid.security import Everyone, Authenticated, Allow, ALL_PERMISSIONS
from pyramid.testing import DummyRequest
from pyramid.httpexceptions import HTTPNotFound

import pypicloud
from pypicloud import api, auth, main


try:
    import unittest2 as unittest  # pylint: disable=F0401
except ImportError:
    import unittest

# pylint: disable=W0212


class TestListPackages(unittest.TestCase):

    """ Tests for package enumeration api """

    @patch('pypicloud.models.Package.distinct')
    def test_zero_security(self, distinct):
        """ In zero security mode, everyone can read everything """
        request = DummyRequest()
        request.registry.zero_security_mode = True
        names = ['a', 'b', 'c']
        distinct.return_value = names
        ret = api.list_packages(request)
        self.assertEqual(ret, names)

    @patch('pypicloud.models.Package.distinct')
    def test_admin(self, distinct):
        """ Admins can do anything go anywhere """
        request = DummyRequest()
        request.registry.zero_security_mode = False
        request.userid = 'a'
        request.is_admin = lambda x: True
        names = ['a', 'b', 'c']
        distinct.return_value = names
        ret = api.list_packages(request)
        self.assertEqual(ret, names)

    @patch('pypicloud.models.Package.distinct')
    def test_filter_permission(self, distinct):
        """ Filter package names by permission """
        request = DummyRequest()
        request.registry.zero_security_mode = False
        request.userid = 'a'
        request.is_admin = lambda x: False
        request.has_permission = lambda x, y: x < 'c'
        names = ['a', 'b', 'c']
        distinct.return_value = names
        ret = api.list_packages(request)
        self.assertEqual(ret, ['a', 'b'])


class TestPermissionSettings(unittest.TestCase):

    """ Tests for retrieving permissions from settings """

    def setUp(self):
        super(TestPermissionSettings, self).setUp()
        self.request = DummyRequest()
        self.settings = self.request.registry.settings = {}

    def test_owner(self):
        """ If set as owner, user is owner of a package """
        self.settings['package.mypkg.owner'] = 'dsa'
        ret = auth._package_owner(self.request, 'mypkg')
        self.assertEqual(ret, 'dsa')

    def test_build_group(self):
        """ Group specifications create user map to groups """
        settings = {
            'group.g1': 'u1 u2 u3',
            'group.g2': 'u2 u3 u4',
            'unrelated': 'weeeeee',
        }
        user_map = auth._build_group_map(settings)
        self.assertEqual(user_map, {
            'u1': ['group:g1'],
            'u2': ['group:g1', 'group:g2'],
            'u3': ['group:g1', 'group:g2'],
            'u4': ['group:g2'],
        })

    def test_group_permission(self):
        """ User in a group has permissions of that group """
        self.settings['package.mypkg.group.g1'] = 'r'
        perms = auth._group_permission(self.request, 'mypkg', 'group:g1')
        self.assertEqual(perms, 'r')

    def test_everyone_permission(self):
        """ All users have 'everyone' permissions """
        self.settings['package.mypkg.group.everyone'] = 'r'
        perms = auth._group_permission(self.request, 'mypkg', Everyone)
        self.assertEqual(perms, 'r')

    def test_authenticated_permission(self):
        """ All logged-in users have 'authenticated' permissions """
        self.settings['package.mypkg.group.authenticated'] = 'r'
        perms = auth._group_permission(self.request, 'mypkg', Authenticated)
        self.assertEqual(perms, 'r')

    def test_zero_security(self):
        """ In zero_security_mode everyone has 'r' permission """
        self.request.userid = None
        self.request.registry.zero_security_mode = True
        can_read = auth._has_permission(self.request, 'floobydooby', 'r')
        self.assertTrue(can_read)

    def test_zero_security_write(self):
        """ zero_security_mode has no impact on 'w' permission """
        self.request.userid = None
        self.request.registry.zero_security_mode = True
        can_write = auth._has_permission(self.request, 'floobydooby', 'w')
        self.assertFalse(can_write)


class TestGetACL(unittest.TestCase):

    """ Tests for generating the package ACL """

    def setUp(self):
        super(TestGetACL, self).setUp()
        self.request = DummyRequest()
        self.request.registry.zero_security_mode = False
        self.settings = self.request.registry.settings = {
            'unrelated': 'blaaaaah',
        }

    def assert_has_ace(self, entity, perm, acl):
        """ Assert that an access control entity exists """
        acl = getattr(acl, '__acl__', acl)
        self.assertTrue((Allow, entity, perm) in acl,
                        "Missing acl (Allow, %s, %s)" % (entity, perm))

    def test_root_acl(self):
        """ Root ACL sets login, admin, and DENY ALL """
        root = Root(self.request)
        self.assert_has_ace(Authenticated, 'login', root)
        self.assert_has_ace('admin', ALL_PERMISSIONS, root)

    def test_root_acl_zero_sec(self):
        """ Root ACL is super permissive in zero security mode """
        self.request.registry.zero_security_mode = True
        root = Root(self.request)
        self.assert_has_ace(Everyone, 'login', root)
        self.assert_has_ace(Everyone, 'read', root)
        self.assert_has_ace(Authenticated, 'write', root)

    def test_zero_security_mode(self):
        """ Zero security mode means ACL is empty """
        self.request.registry.zero_security_mode = True
        acl = auth._get_acl(self.request, 'mypkg')
        self.assertEqual(acl, [])

    def test_owner_rw(self):
        """ Owner always has rw perms on a package """
        self.settings['package.mypkg.owner'] = 'dsa'
        acl = auth._get_acl(self.request, 'mypkg')
        self.assert_has_ace('dsa', 'read', acl)
        self.assert_has_ace('dsa', 'write', acl)

    def test_group_everyone(self):
        """ Special 'everyone' group sets perms for everyone """
        self.settings['package.mypkg.group.everyone'] = 'rw'
        acl = auth._get_acl(self.request, 'mypkg')
        self.assert_has_ace(Everyone, 'read', acl)
        self.assert_has_ace(Everyone, 'write', acl)

    def test_group_authenticated(self):
        """ Special 'authenticated' group sets perms for logged-in users """
        self.settings['package.mypkg.group.authenticated'] = 'rw'
        acl = auth._get_acl(self.request, 'mypkg')
        self.assert_has_ace(Authenticated, 'read', acl)
        self.assert_has_ace(Authenticated, 'write', acl)

    def test_group(self):
        """ Groups set perms for a 'group:<>' principal """
        self.settings['package.mypkg.group.brotatos'] = 'rw'
        acl = auth._get_acl(self.request, 'mypkg')
        self.assert_has_ace('group:brotatos', 'read', acl)
        self.assert_has_ace('group:brotatos', 'write', acl)


def _simple_auth(username, password):
    """ Generate a basic auth header """
    base64string = base64.encodestring('%s:%s' %
                                       (username, password)).replace('\n', '')
    return {
        'Authorization': 'Basic %s' % base64string,
    }


class TestEndpointSecurity(unittest.TestCase):

    """
    Functional tests for view permissions

    These assert that a view is protected by specific permissions (e.g. read,
    write), not that the ACL for those permissions is correct.

    """

    @classmethod
    def setUpClass(cls):
        super(TestEndpointSecurity, cls).setUpClass()
        cls.boto = patch.object(pypicloud, 'boto').start()
        cls.key = patch.object(boto.s3.key, 'Key').start()
        cls.boto.connect_s3().get_bucket(
        ).connection.generate_url.return_value = '/mypath'
        settings = {
            'unittest': True,
            'pypi.db.url': 'sqlite://',
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
        config = main({}, **settings)
        cls.db = config.registry.dbmaker()
        cls.app = webtest.TestApp(config.make_wsgi_app())

    @classmethod
    def tearDownClass(cls):
        super(TestEndpointSecurity, cls).tearDownClass()
        cls.db.close()
        patch.stopall()

    def setUp(self):
        super(TestEndpointSecurity, self).setUp()
        self.db.add(Package('pkg1', '1', '/path'))
        transaction.commit()

    def tearDown(self):
        super(TestEndpointSecurity, self).tearDown()
        self.db.query(Package).delete()
        transaction.commit()
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
