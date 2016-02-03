""" Tests for pypicloud utilities """
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
