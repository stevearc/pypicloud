""" Backend that defers to another server for access control """
import json
from json import JSONDecodeError

import boto3
from botocore.exceptions import ClientError

from pypicloud.util import get_settings

from .base_json import IMutableJsonAccessBackend


class AWSSecretsManagerAccessBackend(IMutableJsonAccessBackend):

    """
    This backend allows you to store all user and package permissions in
    AWS Secret Manager

    """

    def __init__(
        self, request=None, secret_id=None, kms_key_id=None, client=None, **kwargs
    ):
        super(AWSSecretsManagerAccessBackend, self).__init__(request, **kwargs)
        self.secret_id = secret_id
        self.kms_key_id = kms_key_id
        self.client = client
        self.dirty = False

    @classmethod
    def configure(cls, settings):
        kwargs = super(AWSSecretsManagerAccessBackend, cls).configure(settings)
        kwargs["secret_id"] = settings["auth.secret_id"]
        kwargs["kms_key_id"] = settings.get("auth.kms_key_id")
        session = boto3.session.Session(
            **get_settings(
                settings,
                "auth.",
                region_name=str,
                aws_access_key_id=str,
                aws_secret_access_key=str,
                aws_session_token=str,
                profile_name=str,
            )
        )
        kwargs["client"] = session.client("secretsmanager")

        return kwargs

    def _get_db(self):
        """ Hit a server endpoint and return the json response """
        try:
            response = self.client.get_secret_value(SecretId=self.secret_id)
        except ClientError as e:
            if e.response["Error"]["Code"] == "ResourceNotFoundException":
                return {}
            elif e.response["Error"]["Code"] == "InvalidRequestException":
                raise Exception("The request was invalid due to:", e)
            elif e.response["Error"]["Code"] == "InvalidParameterException":
                raise Exception("The request had invalid params:", e)
            raise

        try:
            return json.loads(response["SecretString"])
        except JSONDecodeError as e:
            raise Exception("Invalid json detected: {}".format(e))

    def _save(self):
        if not self.dirty:
            self.dirty = True
            self.request.tm.get().addAfterCommitHook(self._do_save)

    def _do_save(self, succeeded):
        """ Save the auth data to the backend """
        if not succeeded:
            return
        kwargs = {"SecretString": json.dumps(self._db)}
        if self.kms_key_id is not None:
            kwargs["KmsKeyId"] = self.kms_key_id
        try:
            self.client.update_secret(SecretId=self.secret_id, **kwargs)
        except ClientError as e:
            if e.response["Error"]["Code"] == "ResourceNotFoundException":
                self.client.create_secret(Name=self.secret_id, **kwargs)
            raise

    def check_health(self):
        try:
            self._get_db()
        except Exception as e:
            return (False, str(e))
        else:
            return (True, "")
