""" Utilities """
import posixpath
import re

import distlib.locators
import logging
import six
from distlib.locators import Locator, SimpleScrapingLocator
from distlib.util import split_filename
from six.moves.urllib.parse import urlparse  # pylint: disable=F0401,E0611


LOG = logging.getLogger(__name__)
ALL_EXTENSIONS = Locator.source_extensions + Locator.binary_extensions


def parse_filename(filename, name=None):
    """ Parse a name and version out of a filename """
    version = None
    for ext in ALL_EXTENSIONS:
        if filename.endswith(ext):
            trimmed = filename[:-len(ext)]
            parsed = split_filename(trimmed, name)
            if parsed is None:
                break
            else:
                parsed_name, version = parsed[:2]
            break
    if version is None:
        raise ValueError("Cannot parse package file '%s'" % filename)
    if name is None:
        name = parsed_name
    return normalize_name(name), version


def normalize_name(name):
    """ Normalize a python package name """
    # Lifted directly from PEP503:
    # https://www.python.org/dev/peps/pep-0503/#id4
    return re.sub(r"[-_.]+", "-", name).lower()


class BetterScrapingLocator(SimpleScrapingLocator):

    """ Layer on top of SimpleScrapingLocator that allows preferring wheels """
    prefer_wheel = True

    def __init__(self, *args, **kw):
        kw['scheme'] = 'legacy'
        super(BetterScrapingLocator, self).__init__(*args, **kw)

    def locate(self, requirement, prereleases=False, wheel=True):
        self.prefer_wheel = wheel
        return super(BetterScrapingLocator, self).locate(requirement, prereleases)

    def score_url(self, url):
        t = urlparse(url)
        filename = posixpath.basename(t.path)
        return (
            t.scheme == 'https',
            not (self.prefer_wheel ^ filename.endswith('.whl')),
            'pypi.python.org' in t.netloc,
            filename,
        )


# Distlib checks if wheels are compatible before returning them.
# This is useful if you are attempting to install on the system running
# distlib, but we actually want ALL wheels so we can display them to the
# clients.  So we have to monkey patch the method. I'm sorry.
def is_compatible(wheel, tags=None):
    """ Hacked function to monkey patch into distlib """
    return True

distlib.locators.is_compatible = is_compatible


def create_matcher(queries, query_type):
    """
    Create a matcher for a list of queries

    Parameters
    ----------
    queries : list
        List of queries

    query_type: str
        Type of query to run: ["or"|"and"]

    Returns
    -------
        Matcher function

    """
    queries = [query.lower() for query in queries]
    if query_type == 'or':
        return lambda x: any((q in x.lower() for q in queries))
    else:
        return lambda x: all((q in x.lower() for q in queries))


def get_settings(settings, prefix, **kwargs):
    """
    Convenience method for fetching settings

    Returns a dict; any settings that were missing from the config file will
    not be present in the returned dict (as opposed to being present with a
    None value)

    Parameters
    ----------
    settings : dict
        The settings dict
    prefix : str
        String to prefix all keys with when fetching value from settings
    **kwargs : dict
        Mapping of setting name to conversion function (e.g. str or asbool)

    """
    computed = {}
    for name, fxn in six.iteritems(kwargs):
        val = settings.get(prefix + name)
        if val is not None:
            computed[name] = fxn(val)
    return computed
