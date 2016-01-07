""" Tools and resources for traversal routing """
import functools


class IStaticResource(object):

    """ Simple resource base class for static-mapping of paths """
    __name__ = ''
    __parent__ = None
    subobjects = {}

    def __init__(self, request):
        self.request = request

    def __getitem__(self, name):
        child = self.subobjects[name](self.request)
        child.__parent__ = self
        child.__name__ = name
        return child


class IResourceFactory(object):

    """ Resource that generates child resources from a factory """
    __name__ = ''
    __parent__ = None
    __factory__ = lambda x: None

    def __init__(self, request):
        self.request = request

    def __getitem__(self, name):
        child = self.__factory__(name)
        child.__name__ = name
        child.__parent__ = self
        return child


class SimpleResource(object):

    """ Resource for simple pip calls """

    def __init__(self, request):
        self.request = request

    def __getitem__(self, name):
        child = SimplePackageResource(self.request, name)
        child.__parent__ = self
        child.__name__ = name
        return child


class SimplePackageResource(object):

    """ Resource for requesting simple endpoint package versions """

    __parent__ = None
    __name__ = None

    def __init__(self, request, name):
        self.request = request
        self.name = name
        self.__acl__ = request.access.get_acl(self.name)


class APIPackagingResource(IResourceFactory):

    """ Resource for api package queries """

    def __init__(self, request):
        super(APIPackagingResource, self).__init__(request)
        self.__factory__ = functools.partial(APIPackageResource, self.request)


class APIPackageResource(IResourceFactory):

    """ Resource for requesting package versions """

    def __init__(self, request, name):
        super(APIPackageResource, self).__init__(request)
        self.name = name
        self.__factory__ = functools.partial(
            APIPackageFileResource, self.request, self.name)
        self.__acl__ = request.access.get_acl(self.name)


class APIPackageFileResource(object):

    """ Resource for api endpoints dealing with a single package version """

    __parent__ = None
    __name__ = None

    def __init__(self, request, name, filename):
        self.request = request
        self.name = name
        self.filename = filename


class APIResource(IStaticResource):

    """ Resource for api calls """
    subobjects = {
        'package': APIPackagingResource,
    }


class AdminResource(IStaticResource):

    """ Resource for admin calls """


class PackagesResource(IStaticResource):

    """ Resource for cleaner buildout config """


class Root(IStaticResource):

    """ Root context for PyPI Cloud """
    subobjects = {
        'api': APIResource,
        'admin': AdminResource,
        'simple': SimpleResource,
        'pypi': SimpleResource,
        'packages': PackagesResource,
    }

    def __init__(self, request):
        super(Root, self).__init__(request)
        self.__acl__ = request.access.ROOT_ACL
