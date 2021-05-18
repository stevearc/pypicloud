""" Model objects """
import re
from functools import total_ordering

import pkg_resources

from .dateutil import UTC, utcnow
from .util import normalize_name

METADATA_FIELDS = ["requires_python", "summary", "hash_sha256", "hash_md5"]


@total_ordering
class Package(object):

    """
    Representation of a versioned package

    Parameters
    ----------
    name : str
        The name of the package (will be normalized)
    version : str
        The version number of the package
    filename : str
        The name of the package file
    last_modified : datetime, optional
        The datetime when this package was uploaded (default now)
    summary : str, optional
        The summary of the package
    **kwargs :
        Metadata about the package

    """

    def __init__(
        self, name, version, filename, last_modified=None, summary=None, **kwargs
    ):
        self.name = normalize_name(name)
        self.version = version
        self._parsed_version = None
        self.filename = filename
        if last_modified is not None:
            self.last_modified = last_modified
        else:
            self.last_modified = utcnow()
        if self.last_modified.tzinfo is None:
            self.last_modified = self.last_modified.replace(tzinfo=UTC)
        # Disallow empty string
        self.summary = summary or None
        # Filter out None or empty string
        self.data = {k: v for k, v in kwargs.items() if v}

    def get_url(self, request):
        """Create path to the download link"""
        return request.db.get_url(self)

    @property
    def parsed_version(self):
        """Parse and cache the version using pkg_resources"""
        # Use getattr because __init__ isn't called by some ORMs.
        if getattr(self, "_parsed_version", None) is None:
            self._parsed_version = pkg_resources.parse_version(self.version)
        return self._parsed_version

    @property
    def is_prerelease(self):
        """Returns True if the version is a prerelease version"""
        return re.match(r"^\d+(\.\d+)*$", self.version) is None

    @staticmethod
    def read_metadata(blob):
        """Read metadata from a blob"""
        metadata = {}
        for field in METADATA_FIELDS:
            value = blob.get(field)
            if value:
                metadata[field] = value
                continue
            value = blob.get(field.replace("_", "-"))
            if value:
                metadata[field] = value
        return metadata

    def get_metadata(self):
        """Returns the package metadata as a dict"""
        metadata = Package.read_metadata(self.data)
        if self.summary:
            metadata["summary"] = self.summary
        return metadata

    def __hash__(self):
        return hash(self.filename)

    def __eq__(self, other):
        return isinstance(other, Package) and self.filename == other.filename

    def __lt__(self, other):
        return (self.name, self.parsed_version, self.filename) < (
            other.name,
            other.parsed_version,
            self.filename,
        )

    def __repr__(self):
        return self.__str__()

    def __str__(self):
        return "Package(%s)" % self.filename

    def __json__(self, request):
        return {
            "name": self.name,
            "filename": self.filename,
            "last_modified": self.last_modified,
            "version": self.version,
            "url": self.get_url(request),
            "summary": self.summary,
        }

    def search_summary(self):
        """Data to return from a pip search"""
        return {
            "name": self.name,
            "summary": self.summary or "",  # May be None
            "version": self.version,
        }
