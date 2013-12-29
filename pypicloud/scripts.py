""" Commandline scripts """
import argparse
import getpass
from passlib.hash import sha256_crypt  # pylint: disable=E0611
from pyramid.paster import bootstrap
from sqlalchemy import engine_from_config
from sqlalchemy.orm import sessionmaker
from redis import StrictRedis

from .models import create_schema, drop_schema, Package


def setup(description):
    """ Parse the config_uri from arguments and bootstrap the script """
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument('config_uri')

    args = vars(parser.parse_args())

    return bootstrap(args['config_uri'])


def run_create_schema():
    """ Create the schema for the sqlalchemy database """
    env = setup(run_create_schema.__doc__)
    create_schema(env['registry'].dbmaker.kw['bind'])
    print "Success!"


def run_drop_schema():
    """ Drop all tables and schema from the sqlalchemy database """
    env = setup(run_drop_schema.__doc__)
    drop_schema(env['registry'].dbmaker.kw['bind'])
    print "Success!"


def db_and_type(env):
    """ Get a db instance and the type of the db """
    settings = env['registry'].settings
    if 'sqlalchemy.url' in settings:
        engine = engine_from_config(settings, prefix='sqlalchemy.')
        session = sessionmaker(bind=engine)()
        return session, 'sql'
    elif 'redis.url' in settings:
        return StrictRedis.from_url(settings['redis.url']), 'redis'
    else:
        raise ValueError("Config must specify either sqlalchemy.url or "
                         "redis.url!")


def run_refresh_packages():
    """ Clear the database and refresh packages from S3 """
    env = setup(run_refresh_packages.__doc__)
    db, db_type = db_and_type(env)
    if db_type == 'sql':
        db.query(Package).delete()
        db.commit()
        db.close()
    elif db_type == 'redis':
        for key in db.keys(Package.redis_prefix + '*'):
            del db[key]
    print "Success!"


def gen_password():
    """ Generate a salted password """
    password = getpass.getpass()
    verify = getpass.getpass()
    if password != verify:
        print "Passwords do not match!"
    else:
        print sha256_crypt.encrypt(password)
