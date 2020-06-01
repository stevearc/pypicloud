""" Tests for pypicloud utilities """
import unittest

from mock import patch

from pypicloud import util


class TestParse(unittest.TestCase):

    """ Tests for parse_filename """

    def test_valid_source(self):
        """ Parse a valid source package """
        name, version = util.parse_filename("mypkg-1.1.tar.gz")
        self.assertEqual(name, "mypkg")
        self.assertEqual(version, "1.1")

    def test_invalid_source(self):
        """ Parse fails on invalid package name """
        with self.assertRaises(ValueError):
            util.parse_filename("invalid_package_name.tar.gz")

    def test_valid_wheel(self):
        """ Parse a valid wheel package """
        name, version = util.parse_filename("mypkg-1.1-py2.py3-none-any.whl")
        self.assertEqual(name, "mypkg")
        self.assertEqual(version, "1.1")

    def test_invalid_file_ext(self):
        """ Parse fails on invalid file extension """
        with self.assertRaises(ValueError):
            util.parse_filename("mypkg-1.1.pdf")

    def test_use_name(self):
        """ Can pass in name to assist parsing """
        name, version = util.parse_filename("mypkg-1.1-py2.py3-none-any.whl", "mypkg")
        self.assertEqual(name, "mypkg")
        self.assertEqual(version, "1.1")


class TestNormalizeName(unittest.TestCase):

    """ Tests for normalize_name """

    def test_normalize_namespace_package(self):
        """ Namespace packages must be normalized according to PEP503 """
        self.assertEqual(util.normalize_name("repoze.lru"), "repoze-lru")


class TestTimedCache(unittest.TestCase):

    """ Tests for the TimedCache class """

    @patch("pypicloud.util.time")
    def test_evict(self, time):
        """ Cache evicts value after expiration """
        cache = util.TimedCache(5)
        time.time.return_value = 0
        cache["a"] = 1
        time.time.return_value = 3
        self.assertEqual(cache["a"], 1)
        time.time.return_value = 8
        with self.assertRaises(KeyError):
            cache["a"]  # pylint: disable=W0104

    @patch("pypicloud.util.time")
    def test_evict_get(self, time):
        """ Cache .get() evicts value after expiration """
        cache = util.TimedCache(5)
        time.time.return_value = 0
        cache["a"] = 1
        time.time.return_value = 8
        self.assertEqual(cache.get("a", 5), 5)

    def test_negative_cache_time(self):
        """ cache_time cannot be negative """
        with self.assertRaises(ValueError):
            util.TimedCache(-4)

    @patch("pypicloud.util.time")
    def test_cache_time_zero(self, time):
        """ Cache time of 0 never caches """
        cache = util.TimedCache(0)
        time.time.return_value = 0
        cache["a"] = 1
        self.assertTrue("a" not in cache)

    def test_factory(self):
        """ Factory function populates cache """
        cache = util.TimedCache(None, lambda a: a)
        self.assertEqual(cache["a"], "a")

    def test_factory_none(self):
        """ When factory function returns None, no value """
        cache = util.TimedCache(None, lambda a: None)
        with self.assertRaises(KeyError):
            cache["a"]  # pylint: disable=W0104

    def test_factory_get(self):
        """ Factory function populates cache from .get() """
        cache = util.TimedCache(None, lambda a: a)
        self.assertEqual(cache.get("a"), "a")

    def test_factory_get_none(self):
        """ Factory function populates cache from .get() """
        cache = util.TimedCache(None, lambda a: None)
        self.assertEqual(cache.get("a", "f"), "f")

    def test_get(self):
        """ .get() functions as per dict """
        cache = util.TimedCache(None)
        cache["a"] = 1
        self.assertEqual(cache.get("a"), 1)
        self.assertEqual(cache.get("b", 6), 6)

    @patch("pypicloud.util.time")
    def test_set_no_expire(self, time):
        """ set_expire with None will never expire value """
        cache = util.TimedCache(5)
        cache.set_expire("a", 1, None)
        time.time.return_value = 8
        self.assertEqual(cache["a"], 1)

    @patch("pypicloud.util.time")
    def test_set_expire(self, time):
        """ set_expire is calculated from now """
        cache = util.TimedCache(5)
        time.time.return_value = 0
        cache.set_expire("a", 1, 30)
        self.assertEqual(cache["a"], 1)
        time.time.return_value = 29
        self.assertEqual(cache["a"], 1)
        time.time.return_value = 31
        self.assertTrue("a" not in cache)

    @patch("pypicloud.util.time")
    def test_set_expire_clear(self, time):
        """ set_expire with 0 will evict value """
        cache = util.TimedCache(5)
        time.time.return_value = 0
        cache["a"] = 1
        cache.set_expire("a", None, 0)
        self.assertTrue("a" not in cache)
        cache.set_expire("b", None, 0)
        self.assertTrue("b" not in cache)
