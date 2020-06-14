import argparse
import hashlib

from azure.storage.blob import BlobServiceClient

parser = argparse.ArgumentParser()
parser.add_argument("storage_account_url", help="Storage account url")
parser.add_argument("storage_account_key", help="Storage account key")
parser.add_argument("container_name", help="Container")
parser.add_argument("prefix", default="", help="Path prefix")
args = parser.parse_args()

blob_service_client = BlobServiceClient(
    account_url=args.storage_account_url, credential=args.storage_account_key
)

container_client = blob_service_client.get_container_client(args.container_name)

for blob_properties in container_client.list_blobs(name_starts_with=args.prefix):
    metadata = blob_properties.metadata or {}
    key = blob_properties.name
    if "hash_sha256" in metadata and "hash_md5" in metadata:
        continue

    blob = container_client.get_blob_client(key)
    data = blob.download_blob().readall()
    metadata["hash_sha256"] = hashlib.sha256(data).hexdigest()
    metadata["hash_md5"] = hashlib.md5(data).hexdigest()
    blob.set_blob_metadata(metadata)
    print("Updated metadata on {0}".format(key))
