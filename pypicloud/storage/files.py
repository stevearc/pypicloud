""" Store packages as files on disk """
import json
import os
from binascii import hexlify
from contextlib import closing
from datetime import datetime

from pyramid.response import FileResponse

from pypicloud.models import Package

from .base import IStorage


class FileStorage(IStorage):

    """ Stores package files on the filesystem """

    def __init__(self, request=None, **kwargs):
        self.directory = kwargs.pop("directory")
        super(FileStorage, self).__init__(request, **kwargs)

    @classmethod
    def configure(cls, settings):
        kwargs = super(FileStorage, cls).configure(settings)
        directory = os.path.abspath(settings["storage.dir"]).rstrip("/")
        if not os.path.exists(directory):
            os.makedirs(directory)
        kwargs["directory"] = directory
        return kwargs

    def get_path(self, package):
        """ Get the fully-qualified file path for a package """
        return os.path.join(
            self.directory, package.name, package.version, package.filename
        )

    def path_to_meta_path(self, path):
        """ Construct the filename for a metadata file """
        return path + ".meta"

    def get_metadata_path(self, package):
        """ Get the fully-qualified file path for a package metadata file """
        return self.path_to_meta_path(self.get_path(package))

    def list(self, factory=Package):
        for root, _, files in os.walk(self.directory):
            for filename in files:
                if filename.endswith(".meta"):
                    # We don't want to yield for this file
                    continue

                shortpath = root[len(self.directory) :].strip("/")
                name, version = shortpath.split("/")
                fullpath = os.path.join(root, filename)
                last_modified = datetime.fromtimestamp(os.path.getmtime(fullpath))
                metadata = {}
                metafile = self.path_to_meta_path(fullpath)
                if os.path.exists(metafile):
                    with open(metafile, "r") as mfile:
                        try:
                            metadata = json.load(mfile)
                        except ValueError:
                            # If JSON fails to decode, don't sweat it.
                            pass
                yield factory(name, version, filename, last_modified, **metadata)

    def download_response(self, package):
        return FileResponse(
            self.get_path(package),
            request=self.request,
            content_type="application/octet-stream",
        )

    def upload(self, package, datastream):
        destfile = self.get_path(package)
        dest_meta_file = self.get_metadata_path(package)
        destdir = os.path.dirname(destfile)
        if not os.path.exists(destdir):
            os.makedirs(destdir)
        uid = hexlify(os.urandom(4)).decode("utf-8")

        # Store metadata as JSON. This could be expanded in the future
        # to store additional metadata about a package (i.e. author)
        tempfile = os.path.join(destdir, ".metadata." + uid)
        with open(tempfile, "w") as mfile:
            json.dump(package.get_metadata(), mfile)

        os.rename(tempfile, dest_meta_file)

        # Write to a temporary file
        tempfile = os.path.join(destdir, "." + package.filename + "." + uid)
        with open(tempfile, "wb") as ofile:
            for chunk in iter(lambda: datastream.read(16 * 1024), b""):
                ofile.write(chunk)

        os.rename(tempfile, destfile)

    def delete(self, package):
        filename = self.get_path(package)
        meta_file = self.get_metadata_path(package)
        os.unlink(filename)
        try:
            os.unlink(meta_file)
        except OSError:
            # Metadata file may not exist
            pass
        version_dir = os.path.dirname(filename)
        try:
            os.rmdir(version_dir)
        except OSError:
            return
        package_dir = os.path.dirname(version_dir)
        try:
            os.rmdir(package_dir)
        except OSError:
            return

    def open(self, package):
        filename = self.get_path(package)
        return closing(open(filename, "rb"))
