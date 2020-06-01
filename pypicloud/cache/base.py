""" Base class for all cache implementations """
import hashlib
import logging
import posixpath
from datetime import datetime
from io import BytesIO
from typing import Any, BinaryIO, Callable, Dict, List, Optional, Tuple

from pyramid.settings import asbool

from pypicloud.models import Package
from pypicloud.storage import get_storage_impl
from pypicloud.util import create_matcher, normalize_name, parse_filename

LOG = logging.getLogger(__name__)


class ICache(object):

    """ Base class for a caching database that stores package metadata """

    def __init__(
        self, request=None, storage=None, allow_overwrite=None, calculate_hashes=True
    ):
        self.request = request
        self.storage = storage(request)
        self.allow_overwrite = allow_overwrite
        self.calculate_hashes = calculate_hashes

    def new_package(self, *args, **kwargs) -> Package:
        return Package(*args, **kwargs)

    def reload_if_needed(self) -> None:
        """
        Reload packages from storage backend if cache is empty

        This will be called when the server first starts

        """
        if not self.distinct():
            LOG.info("Cache is empty. Rebuilding from storage backend...")
            self.reload_from_storage(False)
            LOG.info("Cache repopulated")

    @classmethod
    def configure(cls, settings):
        """ Configure the cache method with app settings """
        return {
            "storage": get_storage_impl(settings),
            "allow_overwrite": asbool(settings.get("pypi.allow_overwrite", False)),
            "calculate_hashes": asbool(
                settings.get("pypi.calculate_package_hashes", True)
            ),
        }

    @classmethod
    def postfork(cls, **kwargs):
        """ This method will be called after uWSGI forks """

    def get_url(self, package: Package) -> str:
        """
        Get the download url for a package

        Parameters
        ----------
        package : :class:`~pypicloud.models.Package`

        Returns
        -------
        url : str

        """
        return self.storage.get_url(package)

    def download_response(self, package: Package):
        """ Pass through to storage """
        return self.storage.download_response(package)

    def reload_from_storage(self, clear: bool = True) -> None:
        """ Make sure local database is populated with packages """
        if clear:
            self.clear_all()
        packages = self.storage.list(self.new_package)
        for pkg in packages:
            self.save(pkg)

    def upload(
        self,
        filename: str,
        data: BinaryIO,
        name: Optional[str] = None,
        version: Optional[str] = None,
        summary: Optional[str] = None,
        requires_python: Optional[str] = None,
    ) -> Package:
        """
        Save this package to the storage mechanism and to the cache

        Parameters
        ----------
        filename : str
            Name of the package file
        data : file
            File-like readable object
        name : str, optional
            The name of the package (if not provided, will be parsed from
            filename)
        version : str, optional
            The version number of the package (if not provided, will be parsed
            from filename)
        summary : str, optional
            The summary of the package
        requires_python : str, optional
            The Python version requirement

        Returns
        -------
        package : :class:`~pypicloud.models.Package`
            The Package object that was uploaded

        Raises
        ------
        e : ValueError
            If the package already exists and allow_overwrite = False

        """
        if version is None or name is None:
            name, version = parse_filename(filename, name)
        name = normalize_name(name)
        filename = posixpath.basename(filename)
        old_pkg = self.fetch(filename)
        metadata = {"requires_python": requires_python}
        if old_pkg is not None and not self.allow_overwrite:
            raise ValueError("Package '%s' already exists!" % filename)
        if self.calculate_hashes:
            file_data = data.read()
            metadata["hash_sha256"] = hashlib.sha256(file_data).hexdigest()
            metadata["hash_md5"] = hashlib.md5(file_data).hexdigest()
            data = BytesIO(file_data)

        new_pkg = self.new_package(name, version, filename, summary=summary, **metadata)
        self.storage.upload(new_pkg, data)
        self.save(new_pkg)
        return new_pkg

    def delete(self, package: Package) -> None:
        """
        Delete this package from the database and from storage

        Parameters
        ----------
        package : :class:`~pypicloud.models.Package`

        """
        self.storage.delete(package)
        self.clear(package)

    def fetch(self, filename: str) -> Package:
        """
        Get matching package if it exists

        Parameters
        ----------
        filename : str
            Name of the package file

        Returns
        -------
        package : :class:`~pypicloud.models.Package`

        """
        raise NotImplementedError

    def all(self, name: str) -> List[Package]:
        """
        Search for all versions of a package

        Parameters
        ----------
        name : str
            The name of the package

        Returns
        -------
        packages : list
            List of all :class:`~pypicloud.models.Package` s with the given
            name

        """
        raise NotImplementedError

    def distinct(self) -> List[str]:
        """
        Get all distinct package names

        Returns
        -------
        names : list
            List of package names

        """
        raise NotImplementedError

    def search(self, criteria: Dict[str, List[str]], query_type: str) -> List[Package]:
        """
        Perform a search from pip

        Parameters
        ----------
        criteria : dict
            Dictionary containing the search criteria. Pip sends search criteria
            for "name" and "summary" (typically, both of these lists have the
            same search values).

            Example::

                {
                    "name": ["value1", "value2", ..., "valueN"],
                    "summary": ["value1", "value2", ..., "valueN"]
                }

        query_type : str
            Type of query to perform. By default, pip sends "or".


        """
        name_queries = criteria.get("name", [])
        summary_queries = criteria.get("summary", [])
        packages = []

        # Create matchers for the queries
        match_name = create_matcher(name_queries, query_type)
        match_summary = create_matcher(summary_queries, query_type)

        for key in self.distinct():
            # Search all versions of this package key
            latest = None
            for package in self.all(key):
                # Search for a match. If we've already found a match, make sure
                # we find the most recent version that matches.
                if latest is None or package > latest:
                    if match_name(package.name):
                        latest = package
                    elif package.summary is not None and match_summary(package.summary):
                        latest = package
            if latest is not None:
                packages.append(latest)

        return packages

    def summary(self) -> List[Dict[str, Any]]:
        """
        Summarize package metadata

        Returns
        -------
        packages : list
            List of package dicts, each of which contains 'name', 'summary',
            and 'last_modified'.

        """
        packages = []
        for name in self.distinct():
            pkg = {
                "name": name,
                "summary": "",
                "last_modified": datetime.fromtimestamp(0),
            }
            max_pkg = None
            for package in self.all(name):
                pkg["last_modified"] = max(pkg["last_modified"], package.last_modified)
                max_pkg = package if max_pkg is None else max(max_pkg, package)
            if max_pkg:
                pkg["summary"] = max_pkg.summary
                packages.append(pkg)

        return packages

    def clear(self, package: Package) -> None:
        """
        Remove this package from the caching database

        Parameters
        ----------
        package : :class:`~pypicloud.models.Package`

        """
        raise NotImplementedError

    def clear_all(self) -> None:
        """ Clear all cached packages from the database """
        raise NotImplementedError

    def save(self, package: Package) -> None:
        """
        Save this package to the database

        Parameters
        ----------
        package : :class:`~pypicloud.models.Package`

        """
        raise NotImplementedError

    def check_health(self) -> Tuple[bool, str]:
        """
        Check the health of the cache backend

        Returns
        -------
        (healthy, status) : (bool, str)
            Tuple that describes the health status and provides an optional
            status message

        """
        return True, ""
