""" Helpers for syncing packages into the cache in AWS Lambda """
import argparse
import json
import logging
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile
from distutils.spawn import find_executable  # pylint: disable=E0611,F0401
from urllib.request import urlretrieve

import boto3
from pyramid.paster import get_appsettings

from pypicloud import __version__, _lambda_handler
from pypicloud.storage.s3 import S3Storage

HANDLER_FILENAME = "lambda_script.py"

VENV_VERSION = "15.1.0"
VENV_URL = (
    "https://pypi.org/packages/source/v/"
    "virtualenv/virtualenv-%s.tar.gz" % VENV_VERSION
)


def _create_role(role_name, description, policy):
    """ Idempotently create the IAM Role """
    iam = boto3.client("iam")
    iam_resource = boto3.resource("iam")
    role = iam_resource.Role(role_name)
    try:
        role.load()
    except iam.exceptions.NoSuchEntityException:
        print("Creating IAM role %s" % role_name)
        iam.create_role(
            Path="/pypicloud/",
            RoleName=role_name,
            AssumeRolePolicyDocument="""{
            "Version": "2012-10-17",
            "Statement": [{
            "Effect": "Allow",
            "Principal": {"Service": ["lambda.amazonaws.com"]},
            "Action": ["sts:AssumeRole"]
            }]}
            """,
            Description=description,
        )
        role.load()

    policy_name = "inline_policy"
    exists = False
    for role_policy in role.policies.all():
        if role_policy.name == policy_name:
            exists = True
            break
    if not exists:
        print("Attaching inline role policy")
        iam.put_role_policy(
            RoleName=role_name, PolicyName=policy_name, PolicyDocument=policy
        )
    return role.arn


def _create_dynamodb_role(settings, bucket):
    """ Create the AWS Role needed for Lambda with a DynamoDB cache """
    # Jump through hoops to get the table names
    from pypicloud.cache.dynamo import DynamoPackage, PackageSummary

    namespace = settings.get("db.namespace", ())
    policy = """{
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Action": "logs:*",
                "Resource": "arn:aws:logs:*"
            },
            {
                "Effect": "Allow",
                "Action": [
                    "s3:GetObject"
                ],
                "Resource": "arn:aws:s3:::%s/*"
            },
            {
                "Effect": "Allow",
                "Action": [
                    "dynamodb:ListTables"
                ],
                "Resource": "*"
            },
            {
                "Effect": "Allow",
                "Action": [
                    "dynamodb:BatchGetItem",
                    "dynamodb:BatchWriteItem",
                    "dynamodb:DeleteItem",
                    "dynamodb:DescribeLimits",
                    "dynamodb:DescribeTable",
                    "dynamodb:GetItem",
                    "dynamodb:GetRecords",
                    "dynamodb:PutItem",
                    "dynamodb:Query",
                    "dynamodb:Scan",
                    "dynamodb:UpdateItem"
                ],
                "Resource": [%s]
            }]}
    """
    dynamo = boto3.client("dynamodb", region_name=settings["db.region_name"])
    table_arns = []
    for model in (DynamoPackage, PackageSummary):
        tablename = model.meta_.ddb_tablename(namespace)
        try:
            result = dynamo.describe_table(TableName=tablename)
        except dynamo.exceptions.ResourceNotFoundException:
            print(
                "Could not find DynamoDB table %r. "
                "Try running the server first to create the tables" % tablename
            )
            sys.exit(1)
        table_arns.append(result["Table"]["TableArn"])
    index_arns = [t + "/index/*" for t in table_arns]
    table_arns.extend(index_arns)
    table_arns = ['"' + t + '"' for t in table_arns]
    full_policy = policy % (bucket.name, (",".join(table_arns)))

    return _create_role(
        "pypicloud_lambda_dynamo",
        "Lambda role for syncing S3 package changes to DynamoDB",
        full_policy,
    )


def _create_default_role(settings, bucket):
    """ Create the AWS Role needed for Lambda with most caches """
    policy = (
        """{
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Action": "logs:*",
                "Resource": "arn:aws:logs:*"
            },
            {
                "Effect": "Allow",
                "Action": [
                    "s3:GetObject"
                ],
                "Resource": "arn:aws:s3:::%s/*"
            }]}
    """
        % bucket.name
    )
    db = settings["pypi.db"]
    return _create_role(
        "pypicloud_lambda_" + db,
        "Lambda role for syncing S3 package changes to " + db,
        policy,
    )


def make_virtualenv(env):
    """ Create a virtualenv """
    if find_executable("virtualenv") is not None:
        cmd = ["virtualenv"] + [env]
        subprocess.check_call(cmd)
    else:
        # Otherwise, download virtualenv from pypi
        path = urlretrieve(VENV_URL)[0]
        try:
            subprocess.check_call(["tar", "xzf", path])
            subprocess.check_call(
                [sys.executable, "virtualenv-%s/virtualenv.py" % VENV_VERSION, env]
            )
        finally:
            os.unlink(path)
            shutil.rmtree("virtualenv-%s" % VENV_VERSION)


def build_lambda_bundle(argv=None):
    """ Build the zip bundle that will be deployed to AWS Lambda """
    if argv is None:
        argv = sys.argv[1:]
    parser = argparse.ArgumentParser(description=build_lambda_bundle.__doc__)
    parser.add_argument(
        "-o", help="Name of output file (default %(default)s)", default="output.zip"
    )
    parser.add_argument("config", help="Name of config file")

    args = parser.parse_args(argv)
    settings = get_appsettings(args.config)
    bundle = _build_lambda_bundle(settings)
    with open(args.o, "wb") as ofile:
        ofile.write(bundle)
    print("Wrote bundle file %s" % args.o)


def _build_lambda_bundle(settings):
    """ Build the lambda bundle """
    venv_dir = tempfile.mkdtemp()
    try:
        print("Creating virtualenv %s" % venv_dir)
        make_virtualenv(venv_dir)
        print("Installing pypicloud into virtualenv")
        pip = os.path.join(venv_dir, "bin", "pip")
        subprocess.check_call(
            [pip, "install", "pypicloud[dynamo,redis]==%s" % __version__]
        )

        bundle = "%s/output.zip" % venv_dir
        zipf = zipfile.ZipFile(bundle, "w", zipfile.ZIP_DEFLATED)

        site_packages = os.path.join(venv_dir, "lib", "site-packages")
        if not os.path.exists(site_packages):
            subdir = [
                f
                for f in os.listdir(os.path.join(venv_dir, "lib"))
                if f.startswith("python")
            ][0]
            site_packages = os.path.join(venv_dir, "lib", subdir, "site-packages")

        # Hack because importing some modules blows up on Lambda
        for mod in ["zope", "repoze"]:
            open(os.path.join(site_packages, mod, "__init__.py"), "a").close()
        for root, dirs, files in os.walk(site_packages):
            for filename in files:
                fullpath = os.path.join(root, filename)
                zipf.write(fullpath, os.path.relpath(fullpath, site_packages))

        handler = os.path.join(
            os.path.dirname(_lambda_handler.__file__), "_lambda_handler.py"
        )
        zipf.write(handler, HANDLER_FILENAME)

        zipf.close()
        with open(bundle, "rb") as ifile:
            return ifile.read()
    finally:
        shutil.rmtree(venv_dir)


def create_sync_scripts(argv=None):
    """
    Set bucket notifications and create AWS Lambda functions that will sync
    changes in the S3 bucket to the cache

    """
    if argv is None:
        argv = sys.argv[1:]
    parser = argparse.ArgumentParser(description=create_sync_scripts.__doc__)
    parser.add_argument(
        "-n",
        help="Name of the AWS Lambda function to " " create (default %(default)s)",
        default="pypicloud_s3_sync",
    )
    parser.add_argument(
        "-f", help="Overwrite existing AWS Lambda functions", action="store_true"
    )
    parser.add_argument(
        "-a",
        help="The ARN of the IAM role to run as. If not "
        "provided, pypicloud will attempt to create one.",
    )
    parser.add_argument(
        "-r",
        help="The AWS region to create the Lambda in "
        "(will attempt to auto-detect from config file)",
    )
    parser.add_argument("config", help="Name of config file")

    args = parser.parse_args(argv)
    logging.basicConfig()
    settings = get_appsettings(args.config)

    if args.r:
        region = args.r
    else:
        if settings.get("pypi.storage") == "s3":
            region = settings.get("storage.region_name")
    if not region:
        print("No region detected in config file. Please use -r <region>")
        sys.exit(1)

    kwargs = S3Storage.configure(settings)
    bucket = kwargs["bucket"]

    # Create the Role
    if args.a:
        role_arn = args.a
    else:
        db = settings["pypi.db"]
        if db == "dynamo":
            role_arn = _create_dynamodb_role(settings, bucket)
        else:
            role_arn = _create_default_role(settings, bucket)

    lam = boto3.client("lambda", region_name=region)
    func_arn = None
    try:
        func = lam.get_function(FunctionName=args.n)
    except lam.exceptions.ResourceNotFoundException:
        pass
    else:
        if args.f:
            print("Deleting pre-existing function %r" % args.n)
            lam.delete_function(FunctionName=args.n)
        else:
            func_arn = func["Configuration"]["FunctionArn"]
            print("Lambda function %r already exists. Use -f to overwrite" % args.n)

    # Create the lambda function
    if func_arn is None:
        bundle = _build_lambda_bundle(settings)
        handler_module = os.path.splitext(HANDLER_FILENAME)[0]
        # Pull out only the cache db settings
        small_settings = {"pypi.db": settings["pypi.db"]}
        for key, val in settings.items():
            if key.startswith("db."):
                small_settings[key] = val

        print("Creating Lambda function %s" % args.n)
        func = lam.create_function(
            FunctionName=args.n,
            Runtime="python2.7",
            Handler=handler_module + ".handle_s3_event",
            Code={"ZipFile": bundle},
            Environment={
                "Variables": {"PYPICLOUD_SETTINGS": json.dumps(small_settings)}
            },
            Description="Process S3 Object notifications & update pypicloud cache",
            Timeout=30,
            Publish=True,
            Role=role_arn,
        )
        func_arn = func["FunctionArn"]

    print("Adding invoke permission for S3")
    account_id = boto3.client("sts").get_caller_identity().get("Account")
    try:
        lam.add_permission(
            Action="lambda:InvokeFunction",
            FunctionName=args.n,
            Principal="s3.amazonaws.com",
            SourceAccount=account_id,
            SourceArn="arn:aws:s3:::" + bucket.name,
            StatementId="s3_invoke",
        )
    except lam.exceptions.ResourceConflictException:
        print("Permission already present")

    print("Adding lambda configuration to S3 bucket")
    notification = bucket.Notification()
    notification.put(
        NotificationConfiguration={
            "LambdaFunctionConfigurations": [
                {"LambdaFunctionArn": func_arn, "Events": ["s3:ObjectCreated:*"]},
                {"LambdaFunctionArn": func_arn, "Events": ["s3:ObjectRemoved:*"]},
            ]
        }
    )
