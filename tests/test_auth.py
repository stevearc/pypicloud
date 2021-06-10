""" Tests for auth methods """
from base64 import b64encode

from mock import MagicMock, PropertyMock, patch
from pyramid.testing import DummyRequest

from pypicloud import auth

from . import MockServerTest


class TestBasicAuth(MockServerTest):

    """Unit tests for getting HTTP basic auth credentials"""

    def setUp(self):
        super(TestBasicAuth, self).setUp()
        self.request.environ["wsgi.version"] = "9001"
        self.request.registry.realm = "pypi"

    def test_no_headers(self):
        """Returns None if no headers found"""
        creds = auth.get_basicauth_credentials(self.request)
        self.assertIsNone(creds)

    def test_bad_format(self):
        """Returns None if headers malformed"""
        self.request.environ["HTTP_AUTHORIZATION"] = "alskdjasd"
        creds = auth.get_basicauth_credentials(self.request)
        self.assertIsNone(creds)

    def test_not_basic(self):
        """Returns None if auth isn't 'basic'"""
        self.request.environ["HTTP_AUTHORIZATION"] = "advanced abcdefg"
        creds = auth.get_basicauth_credentials(self.request)
        self.assertIsNone(creds)

    def test_not_base64(self):
        """Returns None if auth isn't base64 encoded"""
        self.request.environ["HTTP_AUTHORIZATION"] = "Basic abcdefg"
        creds = auth.get_basicauth_credentials(self.request)
        self.assertIsNone(creds)

    def test_malformed_user_pass(self):
        """Returns None if username/password is malformed"""
        userpass = b64encode(b"abcd").decode("utf8")
        self.request.environ["HTTP_AUTHORIZATION"] = "Basic " + userpass
        creds = auth.get_basicauth_credentials(self.request)
        self.assertIsNone(creds)

    def test_valid(self):
        """Returns username, password if everything is valid"""
        username = "dsa"
        password = "conspiracytheory"
        userpass = b64encode((username + ":" + password).encode("utf8")).decode("utf8")
        self.request.environ["HTTP_AUTHORIZATION"] = "Basic " + userpass
        creds = auth.get_basicauth_credentials(self.request)
        self.assertEqual(creds, {"login": username, "password": password})

    def test_forbid(self):
        """When not logged in, forbid() returns 401"""
        ret = auth._forbid(self.request)
        self.assertEqual(ret.status_code, 401)

    def test_forbid_logged_in(self):
        """When logged in, forbid() returns 403"""
        with patch.object(
            DummyRequest, "authenticated_userid", new_callable=PropertyMock
        ) as auid:
            auid.return_value = "abc"
            ret = auth._forbid(self.request)
            self.assertEqual(ret.status_code, 403)


class TestBasicAuthPolicy(MockServerTest):

    """Tests for the BasicAuthPolicy"""

    def setUp(self):
        super(TestBasicAuthPolicy, self).setUp()
        self.policy = auth.PypicloudSecurityPolicy()
        self.request.access = MagicMock()
        self.get_creds = patch("pypicloud.auth.get_basicauth_credentials").start()
        self.get_creds.return_value = None

    def tearDown(self):
        super(TestBasicAuthPolicy, self).tearDown()
        patch.stopall()

    def test_auth_userid_no_credentials(self):
        """No userid if no credentials"""
        self.get_creds.return_value = None
        userid = self.policy.authenticated_userid(self.request)
        self.assertIsNone(userid)

    def test_auth_fail_verification(self):
        """No userid if access backend fails verification"""
        self.get_creds.return_value = {"login": "dsa", "password": "foobar"}
        self.request.access.verify_user.return_value = False
        userid = self.policy.authenticated_userid(self.request)
        self.assertIsNone(userid)

    def test_auth(self):
        """Return userid if basic auth succeeds"""
        self.get_creds.return_value = {"login": "dsa", "password": "foobar"}
        self.request.access.verify_user.return_value = True
        userid = self.policy.authenticated_userid(self.request)
        self.assertEqual(userid, "dsa")

    def test_remember(self):
        """Remember headers are empty"""
        headers = self.policy.remember(self.request, "principal")
        self.assertEqual(headers, [])

    def test_forget(self):
        """Forget headers are empty"""
        with patch.object(self.request, "session"):
            headers = self.policy.forget(self.request)
            self.assertEqual(headers, [])


class TestSessionAuthPolicy(MockServerTest):

    """Tests for the SessionAuthPolicy"""

    def setUp(self):
        super().setUp()
        self.policy = auth.PypicloudSecurityPolicy()
        self.request.access = MagicMock()
        self.request.session = {}
        self.get_creds = patch("pypicloud.auth.get_basicauth_credentials").start()
        self.get_creds.return_value = None

    def tearDown(self):
        super().tearDown()
        patch.stopall()

    def test_auth_no_userid(self):
        """Auth userid is None if no userid in session"""
        userid = self.policy.authenticated_userid(self.request)
        self.assertIsNone(userid)

    def test_auth_userid(self):
        """Auth userid is the 'user' in the session"""
        self.request.session["user"] = "dsa"
        userid = self.policy.authenticated_userid(self.request)
        self.assertEqual(userid, "dsa")

    def test_remember(self):
        """Remember headers are empty"""
        headers = self.policy.remember(self.request, "dsa")
        self.assertEqual(headers, [])
        self.assertEqual(self.request.session, {"user": "dsa"})

    def test_forget(self):
        """Forget headers are empty"""
        session = self.request.session = MagicMock()
        headers = self.policy.forget(self.request)
        self.assertTrue(session.delete.called)
        self.assertEqual(headers, [])
