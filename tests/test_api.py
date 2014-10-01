""" Tests for API endpoints """
from distlib.database import Distribution
from mock import MagicMock, patch
from pyramid.httpexceptions import HTTPBadRequest, HTTPNotFound, HTTPForbidden

from . import MockServerTest, make_package
from pypicloud.views import api


class TestApi(MockServerTest):

    """ Tests for API endpoints """

    def setUp(self):
        super(TestApi, self).setUp()
        self.access = self.request.access = MagicMock()

    def test_list_packages(self):
        """ List all packages """
        p1 = make_package()
        self.db.upload(p1.filename, None)
        pkgs = api.all_packages(self.request)
        self.assertEqual(pkgs['packages'], [p1.name])

    def test_list_packages_no_perm(self):
        """ If no read permission, package not in all_packages """
        p1 = make_package()
        self.db.upload(p1.filename, None)
        self.access.has_permission.return_value = False
        pkgs = api.all_packages(self.request)
        self.assertEqual(pkgs['packages'], [])

    def test_list_packages_verbose(self):
        """ List all package data """
        p1 = make_package()
        p1 = self.db.upload(p1.filename, None)
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

    def test_download(self):
        """ Downloading package returns download response from db """
        db = self.request.db = MagicMock()
        context = MagicMock()
        ret = api.download_package(context, self.request)
        db.fetch.assert_called_with(context.filename)
        db.download_response.assert_called_with(db.fetch())
        self.assertEqual(ret, db.download_response())

    def test_download_fallback_no_cache(self):
        """ Downloading missing package on non-'cache' fallback returns 404 """
        db = self.request.db = MagicMock()
        self.request.registry.fallback = 'none'
        db.fetch.return_value = None
        context = MagicMock()
        ret = api.download_package(context, self.request)
        self.assertEqual(ret.status_code, 404)

    def test_download_fallback_cache_no_perm(self):
        """ Downloading missing package without cache perm returns 403 """
        db = self.request.db = MagicMock()
        self.request.registry.fallback = 'cache'
        self.request.access.can_update_cache.return_value = False
        db.fetch.return_value = None
        context = MagicMock()
        ret = api.download_package(context, self.request)
        self.assertEqual(ret, self.request.forbid())

    @patch('pypicloud.views.api.FilenameScrapingLocator')
    def test_download_fallback_cache_missing(self, locator):
        """ If fallback url is missing dist, return 404 """
        db = self.request.db = MagicMock()
        self.request.registry.fallback = 'cache'
        self.request.registry.fallback_url = 'http://pypi.com'
        self.request.access.can_update_cache.return_value = True
        db.fetch.return_value = None
        context = MagicMock()
        locator().get_project.return_value = {
            context.filename: None
        }
        ret = api.download_package(context, self.request)
        self.assertEqual(ret.status_code, 404)

    @patch('pypicloud.views.api.fetch_dist')
    @patch('pypicloud.views.api.FilenameScrapingLocator')
    def test_download_fallback_cache(self, locator, fetch_dist):
        """ Downloading missing package caches result from fallback """
        db = self.request.db = MagicMock()
        self.request.registry.fallback = 'cache'
        self.request.registry.fallback_url = 'http://pypi.com'
        self.request.access.can_update_cache.return_value = True
        db.fetch.return_value = None
        fetch_dist.return_value = (MagicMock(), MagicMock())
        context = MagicMock()
        dist = MagicMock(spec=Distribution)
        locator().get_project.return_value = {
            context.filename: dist,
        }
        ret = api.download_package(context, self.request)
        fetch_dist.assert_called_with(self.request, dist)
        self.assertEqual(ret.body, fetch_dist()[1])

    def test_fetch_requirements_no_perm(self):
        """ Fetching requirements without perms returns 403 """
        self.request.access.can_update_cache.return_value = False
        requirements = 'requests>=2.0'
        ret = api.fetch_requirements(self.request, requirements)
        self.assertEqual(ret.status_code, 403)

    @patch('pypicloud.views.api.fetch_dist')
    @patch('pypicloud.views.api.BetterScrapingLocator')
    def test_fetch_requirements(self, locator, fetch_dist):
        """ Fetching requirements without perms returns 403 """
        requirements = 'requests>=2.0'
        ret = api.fetch_requirements(self.request, requirements)
        fetch_dist.assert_called_with(self.request, locator().locate())
        self.assertEqual(ret, {'pkgs': [fetch_dist()[0]]})
