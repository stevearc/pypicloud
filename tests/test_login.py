""" Tests for login views """
from . import MockServerTest
from mock import MagicMock, patch
from pypicloud.views import login


class TestLoginPage(MockServerTest):

    """ Tests for the login/403 page """

    def setUp(self):
        super(TestLoginPage, self).setUp()
        self.request.app_url = lambda *x: '/' + '/'.join(x)
        self.request.userid = None

    def test_user_fetch_login(self):
        """ If a logged-in user is fetching /login, redirect to / """
        self.request.userid = 'dsa'
        self.request.url = '/login'
        ret = login.get_login_page(self.request)
        self.assertEqual(ret.status_code, 302)
        self.assertEqual(ret.location, '/')

    def test_anon_fetch_login(self):
        """ Anonymous user fetching /login renders login page """
        self.request.url = '/login'
        ret = login.get_login_page(self.request)
        self.assertEqual(ret, {})


class TestLogin(MockServerTest):

    """ Tests for login/register/logout operations """

    def setUp(self):
        super(TestLogin, self).setUp()
        self.request.app_url = lambda *x: '/' + '/'.join(x)
        self.request.access = MagicMock()

    def test_login_invalid(self):
        """ Attempting login with invalid credentials returns 403 """
        self.request.access.verify_user.return_value = False
        ret = login.do_login(self.request, 'dsa', 'conspiracytheory')
        self.assertEqual(ret.status_code, 403)

    @patch('pypicloud.views.login.remember')
    def test_login_valid(self, remember):
        """ Logging in sets the user in the session """
        self.request.access.verify_user.return_value = True
        login.do_login(self.request, 'dsa', 'conspiracytheory')
        remember.assert_called_with(self.request, 'dsa')

    def test_register(self):
        """ Registering new user registers user with access backend """
        self.request.access.user_data.return_value = None
        login.register(self.request, 'dsa', 'pass')
        # pylint: disable=E1101
        self.request.access.register.assert_called_with('dsa', 'pass')
        # pylint: enable=E1101

    def test_register_disabled(self):
        """ If registration is disabled, registering new user returns 403 """
        self.request.access.allow_register.return_value = False
        self.request.access.need_admin.return_value = False
        ret = login.register(self.request, 'dsa', 'pass')
        self.assertEqual(ret.status_code, 403)

    def test_register_long_username(self):
        """ Super long usernames can't register """
        self.request.access.user_data.return_value = None
        ret = login.register(self.request, 200 * 'a', 'pass')
        self.assertEqual(ret['code'], 400)

    def test_register_blank_username(self):
        """ Blank usernames can't register """
        self.request.access.user_data.return_value = None
        ret = login.register(self.request, '', 'pass')
        self.assertEqual(ret['code'], 400)

    def test_register_long_password(self):
        """ Super long passwords can't register """
        self.request.access.user_data.return_value = None
        ret = login.register(self.request, 'abc', 200 * 'a')
        self.assertEqual(ret['code'], 400)

    def test_register_duplicate(self):
        """ If registering duplicate user, registration returns 400 """
        ret = login.register(self.request, 'dsa', 'pass')
        self.assertEqual(ret['code'], 400)
        self.assertEqual(self.request.response.status_code, 400)

    @patch('pypicloud.views.login.forget')
    def test_logout(self, forget):
        """ Logging out returns the auth policy forget headers """
        login.logout(self.request)
        forget.assert_called_with(self.request)
