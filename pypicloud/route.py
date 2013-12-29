""" Tools and resources for traversal routing """
import inspect
import functools
from pyramid.httpexceptions import HTTPFound
import fnmatch
import itertools
import re

from pyramid.security import (Allow, Deny, Authenticated, Everyone,
                              ALL_PERMISSIONS)


class Root(object):

    """ Root context for PyPI Cloud """
    __parent__ = None
    __name__ = ''
    __acl__ = [
        (Allow, Authenticated, ALL_PERMISSIONS),
        (Deny, Everyone, ALL_PERMISSIONS),
    ]
    request = None

    def __init__(self, request):
        self.request = request


def subpath(*paths, **kwargs):
    """
    Generate a custom predicate that matches subpaths

    Parameters
    ----------
    *paths : list
        List of globs or regexes. The subpaths must match these exactly.
    pcre : bool
        Use PCRE's instead of globs (default False)

    Notes
    -----
    This view will match ``/simple/foo``, ``/simple/bar/``, and
    ``/simple/lkjlfkjalkdsf``. It will **not** match ``/simple`` or
    ``/simple/foo/bar``.

    .. code-block:: python

        @view_config(context=Root, name='simple', custom_predicates=(subpath('*'),))
        def simple(request):
            request.response.body = '<h1>Hello</h1>'
            return request.response



    """
    pcre = kwargs.pop('pcre', False)
    if pcre:
        match = lambda pattern, path: bool(re.match('^%s$' % pattern, path))
    else:
        match = lambda pattern, path: fnmatch.fnmatch(path, pattern)

    def match_subpath(context, request):
        """ Match request subpath against provided patterns """
        if len(request.subpath) != len(paths):
            return False
        for pattern, path in itertools.izip(paths, request.subpath):
            if not match(pattern, path):
                return False
        return True

    return match_subpath


def addslash(fxn):
    """ View decorator that adds a trailing slash """
    argspec = inspect.getargspec(fxn)

    @functools.wraps(fxn)
    def slash_redirect(*args):
        """ Perform the redirect or pass though to view """
        if len(args) == 1:
            request = args[0]
        else:
            request = args[1]
        if not request.url.endswith('/'):
            return HTTPFound(location=request.url + '/')
        if len(argspec.args) == 1 and argspec.varargs is None:
            return fxn(request)
        else:
            return fxn(*args)

    return slash_redirect
