""" Base class for storage backends """
from typing import BinaryIO, List, Tuple, Type

from pyramid.request import Request

from pypicloud.models import Package


class IStorage(object):

    """ Base class for a backend that stores package files """

    def __init__(self, request: Request):
        self.request = request

    @classmethod
    def configure(cls, settings):
        """ Configure the storage method with app settings """
        return {}

    def list(self, factory: Type[Package] = Package) -> List[Package]:
        """ Return a list or generator of all packages """
        raise NotImplementedError

    def get_url(self, package: Package) -> str:
        """
        Create or return an HTTP url for a package file

        By default this will return a link to the download endpoint

        /api/package/<package>/<filename>

        Returns
        -------
        link : str
            Link to the location of this package file

        """
        fragment = ""
        if package.data.get("hash_sha256"):
            fragment = "sha256=" + package.data["hash_sha256"]
        return self.request.app_url(
            "api", "package", package.name, package.filename, fragment=fragment
        )

    def download_response(self, package: Package):
        """
        Return a HTTP Response that will download this package

        This is called from the download endpoint

        """
        raise NotImplementedError

    def upload(self, package: Package, datastream: BinaryIO) -> None:
        """
        Upload a package file to the storage backend

        Parameters
        ----------
        package : :class:`~pypicloud.models.Package`
            The package metadata
        datastream : file
            A file-like object that contains the package data

        """
        raise NotImplementedError

    def delete(self, package: Package) -> None:
        """
        Delete a package file

        Parameters
        ----------
        package : :class:`~pypicloud.models.Package`
            The package metadata

        """
        raise NotImplementedError

    def open(self, package: Package):
        """
        Get a buffer object that can read the package data

        This should be a context manager. It is used in migration scripts, not
        directly by the web application.

        Parameters
        ----------
        package : :class:`~pypicloud.models.Package`

        Examples
        --------
        ::

            with storage.open(package) as pkg_data:
                with open('outfile.tar.gz', 'w') as ofile:
                    ofile.write(pkg_data.read())

        """
        raise NotImplementedError

    def check_health(self) -> Tuple[bool, str]:
        """
        Check the health of the storage backend

        Returns
        -------
        (healthy, status) : (bool, str)
            Tuple that describes the health status and provides an optional
            status message

        """
        return True, ""
