""" Views """
from pypicloud.route import Root
from pyramid.view import view_config

from pypicloud import __version__
from pyramid_duh import addslash


@view_config(context=Root, request_method='GET', subpath=(),
             renderer='base.jinja2')
@addslash
def get_index(request):
    """ Render a home screen """
    return {
        'version': __version__,
    }
