""" Tests for API endpoints """
from mock import MagicMock
from pypicloud.views import api
from pyramid.httpexceptions import HTTPBadRequest, HTTPNotFound, HTTPForbidden

from . import MockServerTest
from .test_cache import make_package


class TestApi(MockServerTest):

    """ Tests for API endpoints """

    def setUp(self):
        super(TestApi, self).setUp()
        self.access = self.request.access = MagicMock()

    def test_list_packages(self):
        """ List all packages """
        p1 = make_package()
        self.db.upload(p1.name, p1.version, p1.path, None)
        pkgs = api.all_packages(self.request)
        self.assertEqual(pkgs['packages'], [p1.name])

    def test_list_packages_no_perm(self):
        """ If no read permission, package not in all_packages """
        p1 = make_package()
        self.db.upload(p1.name, p1.version, p1.path, None)
        self.access.has_permission.return_value = False
        pkgs = api.all_packages(self.request)
        self.assertEqual(pkgs['packages'], [])

    def test_list_packages_verbose(self):
        """ List all package data """
        p1 = make_package()
        p1 = self.db.upload(p1.name, p1.version, p1.path, None)
        pkgs = api.all_packages(self.request, True)
        self.assertEqual(pkgs['packages'], [{
            'name': p1.name,
            'stable': p1.version,
            'unstable': p1.version,
            'last_modified': p1.last_modified,
        }])

    def test_delete_missing(self):
        """ Deleting a missing package raises 400 """
        context = MagicMock()
        context.name = 'pkg1'
        context.version = '1.1'
        ret = api.delete_package(context, self.request)
        self.assertTrue(isinstance(ret, HTTPBadRequest))

    def test_register_not_allowed(self):
        """ If registration is disabled, register() returns 404 """
        self.request.named_subpaths = {'username': 'a'}
        self.access.allow_register = False
        self.access.need_admin.return_value = False
        ret = api.register(self.request, 'b')
        self.assertTrue(isinstance(ret, HTTPNotFound))

    def test_register(self):
        """ Registration registers user with access backend """
        self.request.named_subpaths = {'username': 'a'}
        self.access.need_admin.return_value = False
        api.register(self.request, 'b')
        self.access.register.assert_called_with('a', 'b')

    def test_register_set_admin(self):
        """ If access needs admin, first registered user is set as admin """
        self.request.named_subpaths = {'username': 'a'}
        self.access.need_admin.return_value = True
        api.register(self.request, 'b')
        self.access.register.assert_called_with('a', 'b')
        self.access.approve_user.assert_called_with('a')
        self.access.set_user_admin.assert_called_with('a', True)

    def test_change_password(self):
        """ Change password forwards to access """
        self.request.userid = 'u'
        api.change_password(self.request, 'a', 'b')
        self.access.edit_user_password.assert_called_with('u', 'b')

    def test_change_password_no_verify(self):
        """ Change password fails if invalid credentials """
        self.request.userid = 'u'
        self.access.verify_user.return_value = False
        ret = api.change_password(self.request, 'a', 'b')
        self.assertTrue(isinstance(ret, HTTPForbidden))
        self.access.verify_user.assert_called_with('u', 'a')
