""" Commandline scripts """
import argparse
import getpass
import gzip
import json
import logging
import os
import sys
from base64 import b64encode

import transaction
from jinja2 import Template
from pkg_resources import resource_string  # pylint: disable=E0611
from pyramid.paster import bootstrap

from pypicloud.access import SCHEMES, get_pwd_context


def gen_password(argv=None):
    """ Generate a salted password """
    if argv is None:
        argv = sys.argv[1:]
    parser = argparse.ArgumentParser(gen_password.__doc__)
    parser.add_argument("-r", help="Number of rounds", type=int)
    parser.add_argument(
        "-s",
        help="Hashing scheme (default %(default)s)",
        default=SCHEMES[0],
        choices=SCHEMES,
    )
    args = parser.parse_args(argv)
    print(_gen_password(args.s, args.r))


def _gen_password(scheme=None, rounds=None):
    """ Prompt user for a password twice for safety """
    pwd_context = get_pwd_context(scheme, rounds)
    while True:
        password = getpass.getpass()
        verify = getpass.getpass()
        if password == verify:
            return pwd_context.hash(password)
        else:
            print("Passwords do not match!")


NO_DEFAULT = object()


def wrapped_input(msg):
    """ Wraps input for tests """
    return input(msg)


def prompt(msg, default=NO_DEFAULT, validate=None):
    """ Prompt user for input """
    while True:
        response = wrapped_input(msg + " ").strip()
        if not response:
            if default is NO_DEFAULT:
                continue
            return default
        if validate is None or validate(response):
            return response


def prompt_option(text, choices, default=NO_DEFAULT):
    """ Prompt the user to choose one of a list of options """
    while True:
        for i, msg in enumerate(choices):
            print("[%d] %s" % (i + 1, msg))
        response = prompt(text, default=default)
        try:
            idx = int(response) - 1
            return choices[idx]
        except (ValueError, IndexError):
            print("Invalid choice\n")


def promptyn(msg, default=None):
    """ Display a blocking prompt until the user confirms """
    while True:
        yes = "Y" if default else "y"
        if default or default is None:
            no = "n"
        else:
            no = "N"
        confirm = prompt("%s [%s/%s]" % (msg, yes, no), "").lower()
        if confirm in ("y", "yes"):
            return True
        elif confirm in ("n", "no"):
            return False
        elif not confirm and default is not None:
            return default


def bucket_validate(name):
    """ Check for valid bucket name """
    if name.startswith("."):
        print("Bucket names cannot start with '.'")
        return False
    if name.endswith("."):
        print("Bucket names cannot end with '.'")
        return False
    if ".." in name:
        print("Bucket names cannot contain '..'")
        return False
    return True


def storage_account_name_validate(name):
    """ Check for valid storage account name """
    if "." in name:
        print("Storage account names cannot contain '.'")
        return False
    return True


def make_config(argv=None):
    """ Create a server config file """
    if argv is None:
        argv = sys.argv[1:]
    parser = argparse.ArgumentParser(description=make_config.__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "-d", action="store_true", help="Create config file for development"
    )
    group.add_argument("-t", action="store_true", help="Create config file for testing")
    group.add_argument(
        "-p", action="store_true", help="Create config file for production"
    )
    group.add_argument(
        "-r", action="store_true", help="Create config file for docker image"
    )

    parser.add_argument(
        "outfile", nargs="?", help="Name of output file (default stdout)"
    )

    args = parser.parse_args(argv)

    if args.outfile is not None and os.path.exists(args.outfile):
        msg = "'%s' already exists. Overwrite?" % args.outfile
        if not promptyn(msg, False):
            return

    if args.d:
        env = "dev"
    elif args.t:
        env = "test"
    elif args.p:
        env = "prod"
    elif args.r:
        env = "docker"
    else:
        env = prompt_option("What is this config file for?", ["dev", "test", "prod"])

    data = {
        "env": env,
        "workdir": "/var/lib/pypicloud" if env == "docker" else r"%(here)s",
    }
    data["reload_templates"] = env == "dev"

    storage = prompt_option(
        "Where do you want to store your packages?",
        ["s3", "gcs", "filesystem", "azure-blob"],
    )
    if storage == "filesystem":
        storage = "file"

    data["storage"] = storage

    if storage == "s3":
        if "AWS_ACCESS_KEY_ID" in os.environ:
            data["access_key"] = os.environ["AWS_ACCESS_KEY_ID"]
        else:
            data["access_key"] = prompt("AWS access key id?")
        if "AWS_SECRET_ACCESS_KEY" in os.environ:
            data["secret_key"] = os.environ["AWS_SECRET_ACCESS_KEY"]
        else:
            data["secret_key"] = prompt("AWS secret access key?")

        data["s3_bucket"] = prompt("S3 bucket name?", validate=bucket_validate)
        if "." in data["s3_bucket"]:
            data["bucket_region"] = prompt("S3 bucket region?")

    if storage == "gcs":
        data["gcs_bucket"] = prompt("GCS bucket name?", validate=bucket_validate)

    if storage == "azure-blob":
        data["storage_account_name"] = prompt(
            "Storage account name?", validate=storage_account_name_validate
        )
        data["storage_account_key"] = prompt("Storage account key?")
        data["storage_container_name"] = prompt("Container name?")

    data["encrypt_key"] = b64encode(os.urandom(32)).decode("utf-8")
    data["validate_key"] = b64encode(os.urandom(32)).decode("utf-8")

    data["admin"] = prompt("Admin username?")
    data["password"] = _gen_password()

    data["session_secure"] = env == "prod"
    data["env"] = env

    if env == "dev" or env == "test":
        data["wsgi"] = "waitress"
    else:
        if hasattr(sys, "real_prefix"):
            data["venv"] = sys.prefix
        data["wsgi"] = "uwsgi"

    tmpl_str = resource_string("pypicloud", "templates/config.ini.jinja2").decode(
        "utf-8"
    )
    template = Template(tmpl_str)

    config_file = template.render(**data)
    if args.outfile is None:
        sys.stdout.write(config_file)
        sys.stdout.write(os.linesep)
    else:
        with open(args.outfile, "w") as ofile:
            ofile.write(config_file)

        print("Config file written to '%s'" % args.outfile)


def migrate_packages(argv=None):
    """
    Migrate packages from one storage backend to another

    Create two config.ini files that are configured to use different storage
    backends. All packages will be migrated from the storage backend in the
    first to the storage backend in the second.

    ex: pypicloud-migrate-packages file_config.ini s3_config.ini

    """
    if argv is None:
        argv = sys.argv[1:]
    parser = argparse.ArgumentParser(
        description=migrate_packages.__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("config_from", help="Name of config file to migrate from")
    parser.add_argument("config_to", help="Name of config file to migrate to")

    args = parser.parse_args(argv)
    logging.basicConfig()

    old_env = bootstrap(args.config_from)

    old_storage = old_env["request"].db.storage

    all_packages = old_storage.list()

    new_env = bootstrap(args.config_to)
    new_storage = new_env["request"].db.storage
    for package in all_packages:
        print("Migrating %s" % package)
        with old_storage.open(package) as data:
            # we need to recalculate the path for the new storage config
            package.data.pop("path", None)
            new_storage.upload(package, data)


def export_access(argv=None):
    """ Dump the access control data to a universal format """
    if argv is None:
        argv = sys.argv[1:]
    parser = argparse.ArgumentParser(description=export_access.__doc__)
    parser.add_argument("config", help="Name of config file")
    parser.add_argument("-o", help="Name of output file")

    args = parser.parse_args(argv)
    logging.basicConfig()

    env = bootstrap(args.config)
    access = env["request"].access
    data = access.dump()
    if args.o:
        with gzip.open(args.o, "w") as ofile:
            json.dump(data, ofile)
    else:
        print(json.dumps(data, indent=2))


def import_access(argv=None):
    """
    Load the access control data from a dump file or stdin

    This operation is idempotent and graceful. It will not clobber your
    existing ACL.

    """
    if argv is None:
        argv = sys.argv[1:]
    parser = argparse.ArgumentParser(
        description=import_access.__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("config", help="Name of config file")
    parser.add_argument("-i", help="Name of input file")

    args = parser.parse_args(argv)
    logging.basicConfig()

    if args.i:
        with gzip.open(args.i, "r") as ifile:
            data = json.load(ifile)
    else:
        print("Reading data from stdin...")
        data = json.load(sys.stdin)

    env = bootstrap(args.config)
    access = env["request"].access
    result = access.load(data)
    transaction.commit()
    if result is not None:
        print(result)
