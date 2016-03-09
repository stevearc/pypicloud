""" Utilities """
from __future__ import division
import logging
import posixpath
from datetime import datetime
from functools import wraps

from distlib.locators import Locator, SimpleScrapingLocator
from distlib.util import split_filename
from pytz import UTC
from six.moves.urllib.parse import urlparse  # pylint: disable=F0401,E0611


LOG = logging.getLogger(__name__)
ALL_EXTENSIONS = Locator.source_extensions + Locator.binary_extensions
EPOCH = datetime(1970, 1, 1, tzinfo=UTC)


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
    return name.lower().replace('-', '_')


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


def getdefaults(settings, *args):
    """
    Attempt multiple gets from a dict, returning a default value if none of the
    keys are found.

    """
    assert len(args) >= 3
    args, default = args[:-1], args[-1]
    canonical = args[0]
    for key in args:
        if key in settings:
            if key != canonical:
                LOG.warn("Using deprecated option '%s' "
                         "(replaced by '%s')", key, canonical)
            return settings[key]
    return default


def dt2ts(dt):
    """Datetime to float timestamp."""
    td = dt - EPOCH
    # Emulate total_seconds for py26
    return (td.microseconds + (td.seconds + td.days * 24 * 3600) * 10**6) / 10**6


def ts2dt(ts):
    """Timestamp to datetime."""
    return datetime.utcfromtimestamp(float(ts)).replace(tzinfo=UTC)


def retry(tries=3, exceptions=(Exception,)):
    """Decorator to try something at most `tries` times when some of
    `exceptions` happen."""
    def retry_applier(fn):
        """The actual decorator."""
        @wraps(fn)
        def retrying_wrapper(*args, **kwargs):
            """The actual retrier."""
            for n in xrange(tries):
                try:
                    return fn(*args, **kwargs)
                except exceptions:
                    if n == tries - 1:
                        raise
                    continue
        return retrying_wrapper
    return retry_applier
