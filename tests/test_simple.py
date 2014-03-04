""" Unit tests for the simple endpoints """
from datetime import datetime
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
        with self.assertRaises(HTTPBadRequest):
            upload(self.request, name, version, content)

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
