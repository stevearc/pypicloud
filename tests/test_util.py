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

    def test_filename_scraper(self):
        """ Filename scraper returns dict with filenames as keys """
        locator = util.FilenameScrapingLocator('localhost')
        result = {}
        info = {
            'filename': 'mypkg-1.1.tar.gz',
            'name': 'mypkg',
            'version': '1.1',
            'url': 'localhost/mypkg',
        }
        locator._update_version_data(result, info)
        self.assertEqual(len(result), 1)
        self.assertTrue(info['filename'] in result)

    def test_wheel_scraper(self):
        """ Wheel scraper prefers wheel dists """
        locator = util.BetterScrapingLocator('localhost')
        self.assertTrue(locator.score_url('http://localhost/mypkg-1.1.whl') >
                        locator.score_url('http://localhost/mypkg-1.1.tar.gz'))

    def test_wheel_scraper_prefer_source(self):
        """ Wheel scraper can be marked to prefer source dists """
        locator = util.BetterScrapingLocator('localhost', wheel=False)
        self.assertTrue(locator.score_url('http://localhost/mypkg-1.1.whl') <
                        locator.score_url('http://localhost/mypkg-1.1.tar.gz'))
