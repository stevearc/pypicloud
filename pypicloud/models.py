""" Model objects """
import os

class Package(object):
    """
    Representation of a versioned package

    Parameters
    ----------
    name : str
        The name of the package (will be normalized)
    version : str, optional
        The version number of the package
    path : str, optional
        The absolute S3 path of the package file

    """

    def __init__(self, name, version=None, path=None):
        self.name = name.lower().replace('-', '_')
        self.version = version
        self.path = path

    @property
    def filename(self):
        """ Just the package file name with no leading path """
        return os.path.basename(self.path)

    @classmethod
    def from_path(cls, path):
        """ Construct a Package object from the S3 path """
        filename = os.path.basename(path)
        name, version = cls.parse_package_and_version(filename)
        return cls(name, version, path)

    @classmethod
    def parse_package_and_version(cls, path):
        """ Parse the package name and version number from a path """
        filename, _ = os.path.splitext(path)
        if filename.endswith('.tar'):
            filename = filename[:-len('.tar')]
        if '-' not in filename:
            return filename, ''
        path_components = filename.split('-')
        for i, comp in enumerate(path_components):
            if comp[0].isdigit():
                return ('-'.join(path_components[:i]),
                        '-'.join(path_components[i:]))
        return filename, ''

    def __hash__(self):
        return hash(self.name, self.version)

    def __eq__(self, other):
        return self.name == other.name and self.version == other.version
