""" View for cleaner buildout calls """
from pyramid.view import view_config
from pyramid_duh import addslash

from pypicloud.route import BuildoutResource
from pypicloud.views.simple import _packages_to_dict


@view_config(context=BuildoutResource, request_method='GET', subpath=(),
             renderer='buildout.jinja2')
@addslash
def list_packages(request):
    """ Render the list for all versions of all packages """
    names = request.db.distinct()
    # remove the ones that you are not allowed to see
    names = filter(lambda x: request.access.has_permission(x, 'read'),
                   names)
    packages = []
    for package_name in names:
        packages += request.db.all(package_name)
    return {'pkgs': _packages_to_dict(request, packages)}
