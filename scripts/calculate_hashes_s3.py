import argparse
import hashlib

import boto3

parser = argparse.ArgumentParser()
parser.add_argument("s3_bucket", help="S3 Bucket name")
parser.add_argument("s3_prefix", default="", help="S3 path prefix")
args = parser.parse_args()

s3 = boto3.client("s3")

paginator = s3.get_paginator("list_objects").paginate(
    Bucket=args.s3_bucket, Prefix=args.s3_prefix
)

for page in paginator:
    for obj in page["Contents"]:
        key = obj["Key"]
        resp = s3.head_object(Bucket=args.s3_bucket, Key=key)
        metadata = resp["Metadata"]
        if "hash_sha256" in metadata and "hash_md5" in metadata:
            continue

        resp = s3.get_object(Bucket=args.s3_bucket, Key=key)
        data = resp["Body"].read()
        metadata["hash_sha256"] = hashlib.sha256(data).hexdigest()
        metadata["hash_md5"] = hashlib.md5(data).hexdigest()
        s3.put_object(Bucket=args.s3_bucket, Key=key, Body=data, Metadata=metadata)
        print("Updated metadata on {0}".format(key))
