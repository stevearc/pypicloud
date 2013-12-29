""" Tests for pypicloud """
from mock import MagicMock, patch
from pypicloud.models import create_schema, Package
from pyramid.testing import DummyRequest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from unittest import TestCase


class DBTest(TestCase):

    """ Base class that provides a sqlalchemy database """

    @classmethod
    def setUpClass(cls):
        engine = create_engine('sqlite:///:memory:')
        create_schema(engine)
        cls.dbmaker = sessionmaker(bind=engine)

    def setUp(self):
        super(DBTest, self).setUp()
        self.db = self.dbmaker()
        self.request = DummyRequest()
        self.request.url = 'http://myserver/path/'
        self.request.bucket = MagicMock()
        self.request.fetch_packages_if_needed = MagicMock()
        self.request.db = self.db
        self.params = {}
        self.request.param = lambda x: self.params[x]

    def tearDown(self):
        super(DBTest, self).tearDown()
        self.db.query(Package).delete()
        self.db.close()
        patch.stopall()
