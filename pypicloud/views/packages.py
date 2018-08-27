""" View for cleaner buildout calls """
from pyramid.view import view_config
from pyramid_duh import addslash

from pypicloud.route import PackagesResource
from pypicloud.views.simple import packages_to_dict


@view_config(
    context=PackagesResource,
    request_method="GET",
    subpath=(),
    renderer="packages.jinja2",
)
@addslash
def list_packages(request):
    """ Render the list for all versions of all packages """
    names = request.db.distinct()
    # remove the ones that you are not allowed to see
    names = filter(lambda x: request.access.has_permission(x, "read"), names)
    packages = []
    for package_name in names:
        packages += request.db.all(package_name)
    return {"pkgs": packages_to_dict(request, packages)}
