""" Store packages as files on disk """
from datetime import datetime

from pyramid.response import FileResponse

import os
from .base import IStorage


class FileStorage(IStorage):

    """ Stores package files on the filesystem """

    def __init__(self, request):
        super(FileStorage, self).__init__(request)

    @classmethod
    def configure(cls, config):
        settings = config.get_settings()
        cls.directory = os.path.abspath(settings['storage.dir']).rstrip('/')
        if not os.path.exists(cls.directory):
            os.makedirs(cls.directory)

    def list(self, factory):
        for root, _, files in os.walk(self.directory):
            for filename in files:
                shortpath = root[len(self.directory):].strip('/')
                name, version = shortpath.split('/')
                fullpath = os.path.join(root, filename)
                last_modified = datetime.fromtimestamp(os.path.getmtime(
                    fullpath))
                path = os.path.join(shortpath, filename)
                yield factory(name, version, path, last_modified)

    def download_response(self, package):
        return FileResponse(os.path.join(self.directory, package.path),
                            request=self.request,
                            content_type='application/octet-stream')

    def upload(self, name, version, filename, data):
        filename = os.path.basename(filename)
        destdir = os.path.join(self.directory, name, version)
        if not os.path.exists(destdir):
            os.makedirs(destdir)
        uid = os.urandom(4).encode('hex')
        tempfile = os.path.join(destdir, '.' + filename + '.' + uid)
        # Write to a temporary file
        with open(tempfile, 'w') as ofile:
            for chunk in iter(lambda: data.read(16 * 1024), ''):
                ofile.write(chunk)

        filename = os.path.join(destdir, filename)
        os.rename(tempfile, filename)
        return os.path.join(name, version, filename)

    def delete(self, path):
        filename = os.path.join(self.directory, path)
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
