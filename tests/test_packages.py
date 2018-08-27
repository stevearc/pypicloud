""" Unit tests for the packages endpoints """
from mock import MagicMock

from . import MockServerTest
from pypicloud.views.packages import list_packages


class TestPackages(MockServerTest):

    """ Unit tests for the /packages endpoints """

    def setUp(self):
        super(TestPackages, self).setUp()
        self.request.access = MagicMock()

    def test_list_packages(self):
        """ Should return packages with their names and urls """
        self.request.db = MagicMock()
        self.request.db.distinct.return_value = ["a", "b", "c"]
        self.request.access.has_permission.side_effect = (
            lambda x, _: x == "b" or x == "c"
        )

        def get_packages(x):
            """ Returns a list of mocked package objects for this package """

            def mm(package_name):
                """ Mock packages for packages_to_dict """
                p = MagicMock()
                p.filename = package_name
                p.get_url.return_value = package_name + ".ext"
                return p

            d = {
                "a": [mm("a0"), mm("a1")],
                "b": [mm("b0")],
                "c": [mm("c0"), mm("c1"), mm("c2")],
            }
            return d.get(x, [])

        self.request.db.all.side_effect = get_packages
        result = list_packages(self.request)
        expected = {"b0": "b0.ext", "c0": "c0.ext", "c1": "c1.ext", "c2": "c2.ext"}
        self.assertEqual(result, {"pkgs": expected})
