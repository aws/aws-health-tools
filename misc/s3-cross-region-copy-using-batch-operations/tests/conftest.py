import argparse
import os

import pytest


@pytest.fixture(autouse=True, scope="session")
def aws_credentials():
    """Set dummy AWS credentials for moto."""
    os.environ["AWS_ACCESS_KEY_ID"] = "testing"
    os.environ["AWS_SECRET_ACCESS_KEY"] = "testing"
    os.environ["AWS_SECURITY_TOKEN"] = "testing"
    os.environ["AWS_SESSION_TOKEN"] = "testing"
    os.environ["AWS_DEFAULT_REGION"] = "us-east-1"


@pytest.fixture
def make_args():
    """Factory to build argparse.Namespace with defaults."""
    def _make(**overrides):
        defaults = {
            "bucket": "source-bucket",
            "prefix": "",
            "source_region": "us-east-1",
            "manifest_bucket": "manifest-bucket",
            "manifest_key": "source-bucket-manifest",
            "manifest_region": "us-east-1",
            "include_versions": False,
            "local_only": False,
            "output_dir": None,
            "profile": None,
        }
        defaults.update(overrides)
        return argparse.Namespace(**defaults)
    return _make


@pytest.fixture
def populate_bucket():
    """Factory to put objects into a moto-mocked S3 bucket."""
    def _populate(s3_client, bucket, objects, region="us-east-1"):
        """Create bucket and put objects.

        objects: list of (key, size_in_bytes) tuples
        """
        params = {"Bucket": bucket}
        if region != "us-east-1":
            params["CreateBucketConfiguration"] = {"LocationConstraint": region}
        try:
            s3_client.create_bucket(**params)
        except s3_client.exceptions.BucketAlreadyOwnedByYou:
            pass
        for key, size in objects:
            s3_client.put_object(Bucket=bucket, Key=key, Body=b"x" * min(size, 1024))
        return bucket
    return _populate
