# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""S3 operations."""

from __future__ import annotations

import json
import logging
import pathlib
from typing import cast

from botocore.exceptions import BotoCoreError, ClientError
from mypy_boto3_s3 import S3Client

from s3_batch_replication.aws.boto import client

INVENTORY_MANIFEST_VERSION = "2016-11-30"
S3_BATCH_OPERATIONS_PRINCIPAL = "batchoperations.s3.amazonaws.com"


def parse_s3_uri(uri: str) -> tuple[str, str]:
    """
    Parse an S3 URI into (bucket, key).

    :param uri: S3 URI in the format s3://<bucket>/<key>
    :return: A tuple of (bucket, key)
    :raises ValueError: If the URI is not a valid S3 URI
    """
    if not uri.startswith("s3://"):
        raise ValueError(f"{uri!r} is not a valid S3 URI (expected s3://bucket/key)")
    parts = uri[5:].split("/", 1)
    if not parts[0] or len(parts) < 2 or not parts[1]:
        raise ValueError(f"{uri!r} must include a bucket and key path (expected s3://bucket/key)")
    return parts[0], parts[1]


def upload_manifest(content: bytes, destination: str, filename: str) -> str:
    """
    Write content to destination/filename.

    :param content: Content to write
    :param destination: S3 URI or local directory path
    :param filename: Filename to use
    :return the full path or S3 URI written
    """
    s3_client: S3Client = cast(S3Client, client("s3"))
    if destination.startswith("s3://"):
        bucket, prefix = parse_s3_uri(destination) if "/" in destination[5:] else (destination[5:], "")
        dest_key = f"{prefix.rstrip('/')}/{filename}".lstrip("/")
        s3_client.put_object(Bucket=bucket, Key=dest_key, Body=content)
        return f"s3://{bucket}/{dest_key}"
    else:
        path = pathlib.Path(destination) / filename
        path.write_bytes(content)
        return str(path)


def get_bucket_kms_key(bucket: str) -> str | None:
    """
    Return the customer-managed KMS key ARN configured for SSE-KMS on a bucket, or None.

    Returns None if the bucket uses SSE-S3, the AWS-managed S3 key (aws/s3), or has no
    default encryption — none of which require explicit KMS permissions on the replication role.

    :param bucket: S3 bucket name.
    :return: KMS key ARN string, or None if no customer-managed key is configured.
    :raises RuntimeError: If the encryption configuration cannot be retrieved.
    """
    try:
        response = cast(S3Client, client("s3")).get_bucket_encryption(Bucket=bucket)
        rules = response.get("ServerSideEncryptionConfiguration", {}).get("Rules", [])
        for rule in rules:
            sse = rule.get("ApplyServerSideEncryptionByDefault", {})
            if sse.get("SSEAlgorithm") == "aws:kms":
                key_arn = sse.get("KMSMasterKeyID")
                # AWS-managed key alias — no explicit permissions needed
                if key_arn and not key_arn.endswith("aws/s3"):
                    return key_arn
        return None
    except ClientError as e:
        code = e.response["Error"]["Code"]
        if code in ("ServerSideEncryptionConfigurationNotFoundError", "NoSuchEncryptionConfiguration", "NoSuchBucket", "404"):
            return None
        if code == "AccessDenied":
            logging.getLogger(__name__).debug("Access denied reading encryption config for %s — skipping KMS key detection", bucket)
            return None
        raise RuntimeError(f"Failed to get encryption configuration for {bucket}: {e}") from e


def download_manifest(s3_uri: str) -> dict:
    """
    Download a manifest from S3.

    :param s3_uri: S3 URI of the manifest
    :return: The content of the manifest as a dictionary
    :raises RuntimeError: If the download fails or the manifest is not valid JSON
    """
    bucket, key = parse_s3_uri(s3_uri)
    try:
        response = cast(S3Client, client("s3")).get_object(Bucket=bucket, Key=key)
        data = response["Body"].read()
    except ClientError as e:
        raise RuntimeError(f"Failed to download manifest from {s3_uri}: {e}") from e
    except BotoCoreError as e:
        raise RuntimeError(f"AWS error downloading manifest from {s3_uri}: {e}") from e
    try:
        return json.loads(data)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Manifest at {s3_uri} is not valid JSON") from e
