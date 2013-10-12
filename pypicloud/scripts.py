""" Commandline scripts """
from pyramid.paster import bootstrap

from .models import create_schema, drop_schema


def setup(description):
    """ Parse the config_uri from arguments and bootstrap the script """
    import argparse
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument('config_uri')

    args = vars(parser.parse_args())

    return bootstrap(args['config_uri'])


def run_create_schema():
    """ Create the schema for the sqlalchemy database """
    env = setup(run_create_schema.__doc__)
    create_schema(env['registry'])
    print "Success!"


def run_drop_schema():
    """ Drop all tables and schema from the sqlalchemy database """
    env = setup(run_drop_schema.__doc__)
    drop_schema(env['registry'])
    print "Success!"
