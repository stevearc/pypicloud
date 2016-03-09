""" Tests for pypicloud utilities """
from mock import MagicMock

from pypicloud import util

try:
    import unittest2 as unittest  # pylint: disable=F0401
except ImportError:
    import unittest


class TestParse(unittest.TestCase):

    """ Tests for parse_filename """

    def test_valid_source(self):
        """ Parse a valid source package """
        name, version = util.parse_filename('mypkg-1.1.tar.gz')
        self.assertEqual(name, 'mypkg')
        self.assertEqual(version, '1.1')

    def test_invalid_source(self):
        """ Parse fails on invalid package name """
        with self.assertRaises(ValueError):
            util.parse_filename('invalid_package_name.tar.gz')

    def test_valid_wheel(self):
        """ Parse a valid wheel package """
        name, version = util.parse_filename('mypkg-1.1-py2.py3-none-any.whl')
        self.assertEqual(name, 'mypkg')
        self.assertEqual(version, '1.1')

    def test_invalid_file_ext(self):
        """ Parse fails on invalid file extension """
        with self.assertRaises(ValueError):
            util.parse_filename('mypkg-1.1.pdf')

    def test_use_name(self):
        """ Can pass in name to assist parsing """
        name, version = util.parse_filename('mypkg-1.1-py2.py3-none-any.whl',
                                            'mypkg')
        self.assertEqual(name, 'mypkg')
        self.assertEqual(version, '1.1')


class TestScrapers(unittest.TestCase):

    """ Test the distlib scrapers """

    def test_wheel_scraper(self):
        """ Wheel scraper prefers wheel dists """
        locator = util.BetterScrapingLocator('localhost')
        self.assertTrue(locator.score_url('http://localhost/mypkg-1.1.whl') >
                        locator.score_url('http://localhost/mypkg-1.1.tar.gz'))

    def test_wheel_scraper_prefer_source(self):
        """ Wheel scraper can be marked to prefer source dists """
        locator = util.BetterScrapingLocator('localhost')
        locator.prefer_wheel = False
        self.assertTrue(locator.score_url('http://localhost/mypkg-1.1.whl') <
                        locator.score_url('http://localhost/mypkg-1.1.tar.gz'))


class TestRetry(unittest.TestCase):
    """Test the retry method."""

    def _mock_callee_and_retrier(
            self,
            return_value,
            leading_exceptions=(),
            retried_exceptions=(Exception,),
    ):
        """Helper method to have a mock callee and the retrying version of
        it."""
        target = MagicMock()
        target.__name__ = 'target'  # or wraps complains
        if leading_exceptions:
            target.side_effect = leading_exceptions + (return_value,)
        else:
            target.return_value = return_value

        return target, util.retry(tries=2, exceptions=retried_exceptions)(target)

    def test_ok(self):
        """If no exception happens, return value."""
        value = 1
        target, retrying = self._mock_callee_and_retrier(value)

        self.assertEqual(
            value,
            retrying(),
        )

        self.assertEqual(1, target.call_count)

    def test_retry_and_succeed(self):
        """If less than `tries` happen, return value."""
        value = 1
        target, retrying = self._mock_callee_and_retrier(
            value,
            leading_exceptions=(Exception,),
        )

        self.assertEqual(
            value,
            retrying(),
        )

        self.assertEqual(2, target.call_count)

    def test_let_other_exceptions_through(self):
        """If some other exception happens, let it through."""
        target, retrying = self._mock_callee_and_retrier(
            "Not used",
            leading_exceptions=(Exception,),
            retried_exceptions=(ValueError,)
        )

        with self.assertRaises(Exception):
            retrying()

        self.assertEqual(1, target.call_count)

    def test_raise_when_out_of_tries(self):
        """If we fail more than `tries` times, let the exception through."""
        target, retrying = self._mock_callee_and_retrier(
            "Not used",
            leading_exceptions=(Exception, Exception,),
        )

        with self.assertRaises(Exception):
            retrying()

        self.assertEqual(2, target.call_count)
