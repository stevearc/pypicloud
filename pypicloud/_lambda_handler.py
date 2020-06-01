""" AWS Lambda handler that process S3 object notifications """
import json
import os
import posixpath
from datetime import datetime

import boto3


def handle_s3_event(event, context):
    """ Handle S3 object notification """
    from pypicloud.cache import get_cache_impl
    from pypicloud.storage.s3 import S3Storage
    from pypicloud.util import parse_filename

    settings = json.loads(os.environ["PYPICLOUD_SETTINGS"])
    # Set 'file' storage as a hack. We're going to load the cache, which will
    # load a storage. We won't actually be using the storage for anything, but
    # the settings have to be present.
    settings.setdefault("pypi.storage", "file")
    settings.setdefault("storage.dir", "/tmp")
    cache_impl = get_cache_impl(settings)
    kwargs = cache_impl.configure(settings)
    cache = cache_impl(**kwargs)

    s3 = boto3.resource("s3")
    for record in event["Records"]:
        bucket = record["s3"]["bucket"]["name"]
        key = record["s3"]["object"]["key"]
        event_name = record["eventName"]
        if event_name.startswith("ObjectCreated"):
            print("S3 object %r created" % key)
            obj = s3.Object(bucket, key)
            package = S3Storage.package_from_object(obj, cache.new_package)
            existing_pkg = cache.fetch(package.filename)
            if existing_pkg is None:
                print("Saving package %s" % package)
                cache.save(package)
            else:
                print("Package already cached")
        else:
            print("S3 object %r deleted" % key)
            filename = posixpath.basename(key)
            try:
                name, version = parse_filename(filename)
            except ValueError:
                name = version = "dummy"
            package = cache.new_package(name, version, filename, datetime.utcnow(), "")
            print("Deleting package %s" % package)
            cache.clear(package)
