""" Store packages as files on disk """
import json
from datetime import datetime
from contextlib import closing

from pyramid.response import FileResponse

import os
from .base import IStorage
from pypicloud.models import Package


class FileStorage(IStorage):

    """ Stores package files on the filesystem """

    METADATA_FILE = 'metadata.json'

    def __init__(self, request=None, **kwargs):
        self.directory = kwargs.pop('directory')
        super(FileStorage, self).__init__(request, **kwargs)

    @classmethod
    def configure(cls, settings):
        kwargs = super(FileStorage, cls).configure(settings)
        directory = os.path.abspath(settings['storage.dir']).rstrip('/')
        if not os.path.exists(directory):
            os.makedirs(directory)
        kwargs['directory'] = directory
        return kwargs

    def get_path(self, package, metadata=False):
        """
        Get the fully-qualified file path for a package and its metadata file.
        """
        if metadata:
            filename = self.METADATA_FILE
        else:
            filename = package.filename
        return os.path.join(self.directory, package.name, package.version,
                            filename)

    def list(self, factory=Package):
        for root, _, files in os.walk(self.directory):
            metadata = {}

            # Read the metadata file
            if self.METADATA_FILE in files:
                with open(os.path.join(root, self.METADATA_FILE), 'r') as mfile:
                    try:
                        metadata = json.loads(mfile.read())
                    except ValueError:
                        # If JSON fails to decode, don't sweat it.
                        pass

            for filename in files:
                if filename == self.METADATA_FILE:
                    # We don't want to yield for this file
                    continue

                shortpath = root[len(self.directory):].strip('/')
                name, version = shortpath.split('/')
                fullpath = os.path.join(root, filename)
                last_modified = datetime.fromtimestamp(os.path.getmtime(
                    fullpath))
                yield factory(name, version, filename, last_modified,
                              **metadata)

    def download_response(self, package):
        return FileResponse(self.get_path(package),
                            request=self.request,
                            content_type='application/octet-stream')

    def upload(self, package, data):
        destfile = self.get_path(package)
        dest_meta_file = self.get_path(package, metadata=True)
        destdir = os.path.dirname(destfile)
        if not os.path.exists(destdir):
            os.makedirs(destdir)
        uid = os.urandom(4).encode('hex')

        # Store metadata as JSON. This could be expanded in the future
        # to store additional metadata about a package (i.e. author)
        tempfile = os.path.join(destdir, '.metadata.' + uid)
        metadata = {'summary': package.summary}
        with open(tempfile, 'w') as mfile:
            json_data = json.dumps(metadata)
            mfile.write(json_data)

        os.rename(tempfile, dest_meta_file)

        # Write to a temporary file
        tempfile = os.path.join(destdir, '.' + package.filename + '.' + uid)
        with open(tempfile, 'w') as ofile:
            for chunk in iter(lambda: data.read(16 * 1024), ''):
                ofile.write(chunk)

        os.rename(tempfile, destfile)

    def delete(self, package):
        filename = self.get_path(package)
        meta_file = self.get_path(package, metadata=True)
        os.unlink(filename)
        os.unlink(meta_file)
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
        return closing(open(filename, 'r'))
