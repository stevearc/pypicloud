""" Base class for storage backends """


class IStorage(object):

    """ Base class for a backend that stores package files """

    def __init__(self, request):
        self.request = request

    @classmethod
    def configure(cls, config):
        """ Configure the storage method with app settings """

    def list(self, factory):
        """ Return a list or generator of all packages """
        raise NotImplementedError

    def get_url(self, package):
        """
        Create or return an HTTP url for a package file

        By default this will return a link to the download endpoint

        /api/package/<package>/<version>/download/<filename>

        """
        return self.request.app_url('api/package', package.name,
                                    package.version, 'download',
                                    package.filename)

    def download_response(self, package):
        """
        Return a HTTP Response that will download this package

        This is called from the download endpoint

        """
        raise NotImplementedError

    def upload(self, name, version, filename, data):
        """
        Upload a package file to the storage backend

        Parameters
        ----------
        name : str
            The name of the package
        version : str
            The version of the package
        filename : str
            The name of the package file that was uploaded
        data : file
            A temporary file object that contains the package data

        Returns
        -------
        path : str
            The unique path to the file in the storage backend

        """
        raise NotImplementedError

    def delete(self, path):
        """
        Delete a package file

        Parameters
        ----------
        path : str
            The unique path to the package

        """
        raise NotImplementedError
