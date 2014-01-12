""" Tests for access backends """
from mock import MagicMock, patch
from pypicloud.access import (IAccessBackend, ConfigAccessBackend,
                              RemoteAccessBackend)
from pypicloud.route import Root
from pyramid.authorization import ACLAuthorizationPolicy
from pyramid.security import Everyone, Authenticated
from pyramid.testing import DummyRequest


try:
    import unittest2 as unittest  # pylint: disable=F0401
except ImportError:
    import unittest


class BaseACLTest(unittest.TestCase):

    """ Base test for anything checking ACLs """

    def setUp(self):
        self.request = DummyRequest()
        self.auth = ACLAuthorizationPolicy()

    def allowed(self, context, perm):
        """ Get all allowed principals from a context or an ACL """
        if not hasattr(context, '__acl__'):
            acl = context
            context = MagicMock()
            context.__acl__ = acl
            context.__parent__ = None
        return self.auth.principals_allowed_by_permission(context, perm)

    def assert_allowed(self, context, perm, principals):
        """ Assert that only a particular set of principals has access """
        allowed = self.allowed(context, perm)
        self.assertEqual(allowed, set(principals))


class TestBaseBackend(BaseACLTest):

    """ Tests for the access backend interface """

    def setUp(self):
        super(TestBaseBackend, self).setUp()
        self.backend = IAccessBackend(self.request)
        self.backend.verify_user = MagicMock()
        self.backend.user_groups = MagicMock()
        self.backend.is_admin = MagicMock()
        self.backend.all_group_permissions = MagicMock()
        self.backend.all_user_permissions = MagicMock()
        self.request.access = self.backend

    def test_root_acl(self):
        """ Root ACL sets login, admin, and DENY ALL """
        root = Root(self.request)
        self.assert_allowed(root, 'login', ['admin', Authenticated])
        self.assert_allowed(root, 'admin', ['admin'])
        self.assert_allowed(root, 'arbitrary', ['admin'])

    def test_user_rw(self):
        """ Owner always has rw perms on a package """
        self.backend.all_user_permissions.return_value = {
            'dsa': ['read', 'write'],
        }
        acl = self.backend.get_acl('mypkg')
        self.assert_allowed(acl, 'read', ['user:dsa'])
        self.assert_allowed(acl, 'write', ['user:dsa'])

    def test_group_everyone(self):
        """ Special 'everyone' group sets perms for everyone """
        self.backend.all_group_permissions.return_value = {
            'everyone': ['read', 'write'],
        }
        acl = self.backend.get_acl('mypkg')
        self.assert_allowed(acl, 'read', [Everyone])
        self.assert_allowed(acl, 'write', [Everyone])

    def test_group_authenticated(self):
        """ Special 'authenticated' group sets perms for logged-in users """
        self.backend.all_group_permissions.return_value = {
            'authenticated': ['read', 'write'],
        }
        acl = self.backend.get_acl('mypkg')
        self.assert_allowed(acl, 'read', [Authenticated])
        self.assert_allowed(acl, 'write', [Authenticated])

    def test_group(self):
        """ Groups set perms for a 'group:<>' principal """
        self.backend.all_group_permissions.return_value = {
            'brotatos': ['read', 'write'],
        }
        acl = self.backend.get_acl('mypkg')
        self.assert_allowed(acl, 'read', ['group:brotatos'])
        self.assert_allowed(acl, 'write', ['group:brotatos'])


class TestConfigBackend(BaseACLTest):

    """ Tests for access backend that uses config settings """

    def setUp(self):
        super(TestConfigBackend, self).setUp()
        self.backend = ConfigAccessBackend(self.request)
        self.request.access = self.backend

    def test_build_group(self):
        """ Group specifications create user map to groups """
        settings = {
            'group.g1': 'u1 u2 u3',
            'group.g2': 'u2 u3 u4',
            'unrelated': 'weeeeee',
        }
        self.backend.configure(settings)
        self.assertItemsEqual(self.backend.user_groups('u1'), ['g1'])
        self.assertItemsEqual(self.backend.user_groups('u2'), ['g1', 'g2'])
        self.assertItemsEqual(self.backend.user_groups('u3'), ['g1', 'g2'])
        self.assertItemsEqual(self.backend.user_groups('u4'), ['g2'])

    def test_group_permission(self):
        """ User in a group has permissions of that group """
        settings = {'package.mypkg.group.g1': 'r'}
        self.backend.configure(settings)
        perms = self.backend.principal_permissions('mypkg', 'group:g1')
        self.assertEqual(perms, ['read'])

    def test_everyone_permission(self):
        """ All users have 'everyone' permissions """
        settings = {'package.mypkg.group.everyone': 'r'}
        self.backend.configure(settings)
        perms = self.backend.principal_permissions('mypkg', Everyone)
        self.assertEqual(perms, ['read'])

    def test_authenticated_permission(self):
        """ All logged-in users have 'authenticated' permissions """
        settings = {'package.mypkg.group.authenticated': 'r'}
        self.backend.configure(settings)
        perms = self.backend.principal_permissions('mypkg', Authenticated)
        self.assertEqual(perms, ['read'])

    def test_zero_security(self):
        """ In zero_security_mode everyone has 'r' permission """
        settings = {
            'auth.zero_security_mode': True
        }
        self.backend.configure(settings)
        can_read = self.backend.has_permission('floobydooby', 'read')
        self.assertTrue(can_read)

    def test_zero_security_write(self):
        """ zero_security_mode has no impact on 'w' permission """
        settings = {
            'auth.zero_security_mode': True
        }
        self.backend.configure(settings)
        perms = self.backend.principal_permissions('pkg', Everyone)
        self.assertEqual(perms, ['read'])

    def test_root_acl_zero_sec(self):
        """ Root ACL is super permissive in zero security mode """
        settings = {
            'auth.zero_security_mode': True
        }
        self.backend.configure(settings)
        root = Root(self.request)
        self.assert_allowed(root, 'login', ['admin', Everyone])
        self.assert_allowed(root, 'read', ['admin', Everyone])
        self.assert_allowed(root, 'write', ['admin', Authenticated])

    def test_zero_security_mode_acl(self):
        """ Zero security mode means ACL is empty """
        settings = {
            'auth.zero_security_mode': True
        }
        self.backend.configure(settings)
        acl = self.backend.get_acl('mypkg')
        self.assertEqual(acl, [])


class TestRemoteBackend(unittest.TestCase):

    """ Tests for the access backend that delegates calls to remote server """

    def setUp(self):
        request = DummyRequest()
        self.backend = RemoteAccessBackend(request)
        self.auth = ('user', 'pass')
        settings = {
            'auth.backend_server': 'server',
            'auth.user': self.auth[0],
            'auth.password': self.auth[1],
        }
        self.backend.configure(settings)
        self.requests = MagicMock()
        patch.dict('sys.modules', requests=self.requests).start()

    def tearDown(self):
        patch.stopall()

    def test_verify(self):
        """ Delegate login to remote server """
        verified = self.backend.verify_user('user', 'pass')
        params = {'username': 'user', 'password': 'pass'}
        self.requests.get.assert_called_with('server/verify', params=params,
                                             auth=self.auth)
        self.assertEqual(verified, self.requests.get().json())

    def test_user_groups(self):
        """ Delegate fetching user groups to remote server """
        groups = self.backend.user_groups('dsa')
        params = {'username': 'dsa'}
        self.requests.get.assert_called_with(
            'server/groups', params=params, auth=self.auth)
        self.assertEqual(groups, self.requests.get().json())

    def test_admin(self):
        """ Query server to determine if user is admin """
        is_admin = self.backend.is_admin('dsa')
        params = {'username': 'dsa'}
        self.requests.get.assert_called_with('server/admin', params=params,
                                             auth=self.auth)
        self.assertEqual(is_admin, self.requests.get().json())

    def test_group_perms(self):
        """ Query server for group permissions on a package """
        perms = self.backend.all_group_permissions('mypkg')
        params = {'package': 'mypkg'}
        self.requests.get.assert_called_with('server/group_permissions',
                                             params=params, auth=self.auth)
        self.assertEqual(perms, self.requests.get().json())

    def test_user_perms(self):
        """ Query server for user permissions on a package """
        perms = self.backend.all_user_permissions('mypkg')
        params = {'package': 'mypkg'}
        self.requests.get.assert_called_with('server/user_permissions',
                                             params=params, auth=self.auth)
        self.assertEqual(perms, self.requests.get().json())
