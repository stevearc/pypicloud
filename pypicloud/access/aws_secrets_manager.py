""" Backend that defers to another server for access control """
import boto3
from botocore.exceptions import ClientError
import json

from .base import IAccessBackend

"""
Secret should look like this on AWS:

{
  "users": {
    "user1": "password1",
    "user2": "password2",
    "user3": "password3",
    "user4": "password4",
    "user5": "password5",
  },
  "groups": {
    "admins": [
      "user1",
      "user2"
    ],
    "group1": [
      "user3"
    ]
  },
  "packages": {
      "mypackage": {
          "groups": {
              "group1": ["read', "write"],
              "group2": ["read"],
              "group3": [],
          },
          "users": {
              "user1": ["read", "write"],
              "user2": ["read"],
              "user3": [],
              "user5": ["read"],
          }
      }
  }
}
"""


class AWSSecretsManagerAccessBackend(IAccessBackend):

    """
    This backend allows you to store all user and package permissions in
    AWS Secret Manager

    """

    def __init__(self, request=None, settings=None, region=None,
                 secret_id=None, credentials=None, **kwargs):
        super(AWSSecretsManagerAccessBackend, self).__init__(request, **kwargs)
        self._settings = settings
        self.region = region
        self.secret_id = secret_id
        self.credentials = {}
        self.credentials.update(credentials or {})

    @classmethod
    def configure(cls, settings):
        kwargs = super(AWSSecretsManagerAccessBackend, cls).configure(settings)
        kwargs['settings'] = settings
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

    def _fetch_credentials(self):
        """ Hit a server endpoint and return the json response """
        session = boto3.session.Session(**self.credentials)
        client = session.client(
            service_name='secretsmanager',
            region_name=self.region,
            endpoint_url="https://secretsmanager.{}.amazonaws.com".format(
                self.region
            )
        )

        try:
            return json.loads(client.get_secret_value(
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

    def verify_user(self, username, password):
        credentials = self._fetch_credentials()
        try:
            return credentials.get('users', {})[username] == password
        except KeyError:
            return False

    def _get_password_hash(self, username):
        # We don't have to do anything here because we overrode 'verify_user'
        pass

    def groups(self, username=None):
        credentials = self._fetch_credentials()
        if not username:
            return list(credentials.get('groups', {}).keys())
        groups = []
        for group_name, users in credentials.get('groups', {}).items():
            if username in users:
                groups.append(group_name)
        return groups

    def group_members(self, group):
        credentials = self._fetch_credentials()
        return list(credentials.get('groups', {}).get(group, []))

    def is_admin(self, username):
        credentials = self._fetch_credentials()
        admins = credentials.get('groups', {}).get('admins', [])
        return username in admins

    def group_permissions(self, package):
        credentials = self._fetch_credentials()
        packages = credentials.get('packages', {})
        package = packages.get('package', {})
        return package.get('groups', {})

    def user_permissions(self, package):
        credentials = self._fetch_credentials()
        packages = credentials.get('packages', {})
        package = packages.get('package', {})
        return package.get('users', {})

    def user_package_permissions(self, username):
        credentials = self._fetch_credentials()
        packages = []
        for package in credentials.get('packages', {}):
            users = package.get('users', {})
            if username in users:
                packages.append(username)
        return packages

    def group_package_permissions(self, group):
        credentials = self._fetch_credentials()
        packages = []
        for package in credentials.get('packages', {}):
            groups = package.get('groups', {})
            if group in groups:
                packages.append(group)
        return packages

    def user_data(self, username=None):
        credentials = self._fetch_credentials()
        admins = credentials.get('groups', {}).get('admins', [])
        users = []
        for user in credentials.get('users', {}):
            if username and user != username:
                continue
            users.append({
                'username': user,
                'admin': user in admins
            })
            if username and user == username:
                break
        return users
