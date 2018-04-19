""" Backend that defers to another server for access control """
import boto3
from botocore.exceptions import ClientError
import json
try:
    from json.decoder import JSONDecodeError
except ImportError:
    JSONDecodeError = ValueError

from .base_json import IMutableJsonAccessBackend, IMutableJsonAccessDB


class AWSSecretsManagerDB(IMutableJsonAccessDB):
    """
    This class implements IMutableJsonAccessDB class for the AWS Secrets
    Manager backend.
    """
    def __init__(self, region, secret_id, credentials, *args, **kwargs):
        super(AWSSecretsManagerDB, self).__init__(*args, **kwargs)
        self.region = region
        self.secret_id = secret_id
        self.credentials = credentials
        self.__client = None
        self.update(self._fetch())

    @property
    def _client(self):
        """Cached instance of the boto3 client"""
        if not self.__client:
            session = boto3.session.Session(**self.credentials)
            self.__client = session.client(
                service_name='secretsmanager',
                region_name=self.region,
                endpoint_url="https://secretsmanager.{}.amazonaws.com".format(
                    self.region
                )
            )
        return self.__client

    def _fetch(self):
        """ Hit a server endpoint and return the json response """
        try:
            return json.loads(self._client.get_secret_value(
                SecretId=self.secret_id
            )['SecretString'])
        except ClientError as e:
            if e.response['Error']['Code'] == 'ResourceNotFoundException':
                raise Exception(
                    "The requested secret " + self.secret_id +
                    " was not found")
            elif e.response['Error']['Code'] == 'InvalidRequestException':
                raise Exception("The request was invalid due to:", e)
            elif e.response['Error']['Code'] == 'InvalidParameterException':
                raise Exception("The request had invalid params:", e)
            raise
        except JSONDecodeError as e:
            raise Exception('Invalid json detected: {}'.format(e))

    def save(self):
        self._client.update_secret(
            SecretId=self.secret_id,
            SecretString=json.dumps(self)
        )


class AWSSecretsManagerAccessBackend(IMutableJsonAccessBackend):

    """
    This backend allows you to store all user and package permissions in
    AWS Secret Manager

    """

    def __init__(self, request=None, region=None, secret_id=None,
                 credentials=None, **kwargs):
        super(AWSSecretsManagerAccessBackend, self).__init__(request, **kwargs)
        self.region = region
        self.secret_id = secret_id
        self.credentials = {}
        self.credentials.update(credentials or {})

    @classmethod
    def configure(cls, settings):
        kwargs = super(AWSSecretsManagerAccessBackend, cls).configure(settings)
        kwargs['region'] = settings['auth.region']
        kwargs['secret_id'] = settings['auth.secret_id']
        credentials = {}

        if settings.get('auth.access_key'):
            credentials['aws_access_key_id'] = settings['auth.access_key']
        if settings.get('auth.secret_key'):
            credentials['aws_secret_access_key'] = settings['auth.secret_key']
        if settings.get('auth.session_token'):
            credentials['aws_session_token'] = settings['auth.session_token']
        if settings.get('auth.profile_name'):
            credentials['profile_name'] = settings['auth.profile_name']
        kwargs['credentials'] = credentials
        return kwargs

    def _get_db(self):
        return AWSSecretsManagerDB(
            self.region, self.secret_id, self.credentials
        )
