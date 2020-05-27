""" Tests for commandline scripts """
import unittest

from mock import patch

from pypicloud import scripts
from pypicloud.access import get_pwd_context


class TestScripts(unittest.TestCase):

    """ Tests for commandline scripts """

    @patch.object(scripts, "getpass")
    def test_gen_password(self, getpass):
        """ Generate a password """
        pwd_context = get_pwd_context()
        passwds = ["foo", "foo", "bar", "baz"]
        getpass.getpass.side_effect = passwds.pop
        ret = scripts._gen_password()
        self.assertEqual(len(passwds), 0)
        self.assertTrue(pwd_context.verify("foo", ret))

    @patch.object(scripts, "_gen_password")
    def test_cli_gen_password(self, genpass):
        """ Commandline prints generated password """
        scripts.gen_password([])
        self.assertTrue(genpass.called)

    @patch("pypicloud.scripts.wrapped_input", return_value="")
    def test_prompt_default(self, _):
        """ If user hits 'enter', return default value """
        ret = scripts.prompt("", default="abc")
        self.assertEqual(ret, "abc")

    @patch("pypicloud.scripts.wrapped_input")
    def test_prompt_no_default(self, stdin):
        """ If no default, require a value """
        invals = ["", "foo"]
        stdin.side_effect = lambda x: invals.pop(0)
        ret = scripts.prompt("")
        self.assertEqual(ret, "foo")

    @patch("pypicloud.scripts.wrapped_input")
    def test_prompt_validate(self, stdin):
        """ Prompt user until return value passes validation check """
        invals = ["foo", "bar"]
        stdin.side_effect = lambda x: invals.pop(0)
        ret = scripts.prompt("", validate=lambda x: x == "bar")
        self.assertEqual(ret, "bar")

    @patch("pypicloud.scripts.prompt")
    def test_prompt_choice(self, prompt):
        """ Prompt the user to choose from a list """
        prompt.return_value = 2
        ret = scripts.prompt_option("", ["a", "b", "c"])
        self.assertEqual(ret, "b")

    @patch("pypicloud.scripts.prompt")
    def test_prompt_choice_bad_int(self, prompt):
        """ Bad ints require user to re-input value """
        invals = ["a", "b", 1]
        prompt.side_effect = lambda *_, **__: invals.pop(0)
        ret = scripts.prompt_option("", ["a", "b", "c"])
        self.assertEqual(ret, "a")

    @patch("pypicloud.scripts.prompt")
    def test_prompt_choice_index_error(self, prompt):
        """ Out-of-range ints require user to re-input value """
        invals = [44, 4, 0, -1, 3]
        prompt.side_effect = lambda *_, **__: invals.pop(0)
        ret = scripts.prompt_option("", ["a", "b", "c"])
        self.assertEqual(ret, "c")

    @patch("pypicloud.scripts.prompt")
    def test_promptyn_yes(self, prompt):
        """ Prompt user for y/n user says yes """
        prompt.return_value = "y"
        ret = scripts.promptyn("")
        self.assertTrue(ret)

    @patch("pypicloud.scripts.prompt")
    def test_promptyn_no(self, prompt):
        """ Prompt user for y/n user says no """
        prompt.return_value = "n"
        ret = scripts.promptyn("")
        self.assertFalse(ret)

    @patch("pypicloud.scripts.prompt")
    def test_promptyn_no_default(self, prompt):
        """ Prompt user for y/n requires an answer """
        invals = ["", "42", "yeees", "wat", "1", "no"]
        prompt.side_effect = lambda *_, **__: invals.pop(0)
        ret = scripts.promptyn("")
        self.assertEqual(len(invals), 0)
        self.assertFalse(ret)

    @patch("pypicloud.scripts.prompt")
    def test_promptyn_default(self, prompt):
        """ Prompt user for y/n user default on no input """
        prompt.return_value = ""
        ret = scripts.promptyn("", True)
        self.assertTrue(ret)
        ret = scripts.promptyn("", False)
        self.assertFalse(ret)

    def test_bucket_validate(self):
        """ Validate bucket name """
        ret = scripts.bucket_validate("bucketname")
        self.assertTrue(ret)
        ret = scripts.bucket_validate("bucket.name")
        self.assertTrue(ret)
        ret = scripts.bucket_validate("bucketname.")
        self.assertFalse(ret)
        ret = scripts.bucket_validate(".bucketname")
        self.assertFalse(ret)
        ret = scripts.bucket_validate("bucket..name")
        self.assertFalse(ret)
