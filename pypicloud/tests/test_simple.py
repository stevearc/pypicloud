""" Unit tests for the simple endpoints """
import pypicloud.views.simple
from mock import MagicMock, patch
from pypicloud.route import SimplePackageResource
from pypicloud.views.simple import upload, simple, package_versions
from pyramid.httpexceptions import HTTPBadRequest, HTTPFound

from . import DBTest


class TestSimple(DBTest):

    """ Unit tests for simple simple """

    def setUp(self):
        super(TestSimple, self).setUp()
        self.request.registry.zero_security_mode = True
        self.request.get_acl = lambda x: []
        self.request.has_permission = MagicMock()
        self.request.has_permission.return_value = True
        self.api_call = patch.object(pypicloud.views.simple, 'api').start()
        self.package = patch.object(pypicloud.views.simple, 'Package').start()

    def test_upload(self):
        """ Upload endpoint returns the result of api call """
        self.params = {
            ':action': 'file_upload',
        }
        name, version, content = 'foo', 'bar', 'baz'
        pkgs = upload(self.request, name, version, content)
        self.assertEquals(pkgs, self.api_call.upload_package())

    def test_upload_bad_action(self):
        """ Upload endpoint only respects 'file_upload' action """
        self.params = {
            ':action': 'blah',
        }
        name, version, content = 'foo', 'bar', 'baz'
        with self.assertRaises(HTTPBadRequest):
            upload(self.request, name, version, content)

    def test_list(self):
        """ Simple list should return api call """
        result = simple(self.request)
        self.api_call.list_packages.assert_called_with(self.request)
        self.assertEqual(result, {'pkgs': self.api_call.list_packages()})

    def test_list_versions(self):
        """ Listing package versions should return api call """
        self.request.registry.use_fallback = False
        context = SimplePackageResource(self.request, 'mypkg')
        result = package_versions(context, self.request)
        self.package.normalize_name.assert_called_with(context.name)
        self.package.all.assert_called_with(self.request,
                                            self.package.normalize_name())
        self.assertEqual(result, {'pkgs': self.package.all()})

    def test_list_versions_fallback(self):
        """ Listing package versions can fall back to external url """
        self.request.registry.use_fallback = True
        fb = self.request.registry.fallback_url = 'http://pypi.com'
        context = SimplePackageResource(self.request, 'mypkg')
        self.package.normalize_name.return_value = context.name
        self.package.all.return_value = []
        result = package_versions(context, self.request)
        url = fb + '/' + context.name + '/'
        self.assertTrue(isinstance(result, HTTPFound))
        self.assertEqual(result.location, url)
