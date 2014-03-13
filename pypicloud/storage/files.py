""" Store packages as files on disk """
from datetime import datetime
from contextlib import closing

from pyramid.response import FileResponse

import os
from .base import IStorage
from pypicloud.models import Package


class FileStorage(IStorage):

    """ Stores package files on the filesystem """

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

    def get_path(self, package):
        """ Get the fully-qualified file path for a package """
        return os.path.join(self.directory, package.name, package.version,
                            package.filename)

    def list(self, factory=Package):
        for root, _, files in os.walk(self.directory):
            for filename in files:
                shortpath = root[len(self.directory):].strip('/')
                name, version = shortpath.split('/')
                fullpath = os.path.join(root, filename)
                last_modified = datetime.fromtimestamp(os.path.getmtime(
                    fullpath))
                yield factory(name, version, filename, last_modified)

    def download_response(self, package):
        return FileResponse(self.get_path(package),
                            request=self.request,
                            content_type='application/octet-stream')

    def upload(self, package, data):
        destfile = self.get_path(package)
        destdir = os.path.dirname(destfile)
        if not os.path.exists(destdir):
            os.makedirs(destdir)
        uid = os.urandom(4).encode('hex')
        tempfile = os.path.join(destdir, '.' + package.filename + '.' + uid)
        # Write to a temporary file
        with open(tempfile, 'w') as ofile:
            for chunk in iter(lambda: data.read(16 * 1024), ''):
                ofile.write(chunk)

        os.rename(tempfile, destfile)

    def delete(self, package):
        filename = self.get_path(package)
        os.unlink(filename)
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
