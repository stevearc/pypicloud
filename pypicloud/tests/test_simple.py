""" Unit tests for the simple endpoints """
import pypicloud.views.simple
from mock import MagicMock, patch
from pypicloud.models import Package
from pypicloud.route import SimplePackageResource
from pypicloud.views.simple import upload, simple, package_versions
from pyramid.httpexceptions import HTTPBadRequest, HTTPFound

from . import MockServerTest


class TestSimple(MockServerTest):

    """ Unit tests for simple simple """

    def setUp(self):
        super(TestSimple, self).setUp()
        self.request.access = MagicMock()
        self.api_call = patch.object(pypicloud.views.simple, 'api').start()

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
        pkg = Package('mypkg', '1.1', 'mypkg-1.1.tar.gz')
        self.request.db.upload(pkg.name, pkg.version, pkg.path, None)
        context = SimplePackageResource(self.request, 'mypkg')
        result = package_versions(context, self.request)
        self.assertEqual(result, {'pkgs': [pkg]})

    def test_list_versions_fallback(self):
        """ Listing package versions can fall back to external url """
        self.request.registry.use_fallback = True
        fb = self.request.registry.fallback_url = 'http://pypi.com'
        context = SimplePackageResource(self.request, 'mypkg')
        result = package_versions(context, self.request)
        url = fb + '/' + context.name + '/'
        self.assertTrue(isinstance(result, HTTPFound))
        self.assertEqual(result.location, url)
