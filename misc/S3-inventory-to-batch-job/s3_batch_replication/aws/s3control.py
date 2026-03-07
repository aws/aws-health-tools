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

"""S3 Control (Batch Operations) operations."""
from __future__ import annotations

import uuid
from typing import Literal, cast

from botocore.exceptions import BotoCoreError, ClientError
from mypy_boto3_s3 import S3Client
from mypy_boto3_s3control.client import S3ControlClient
from mypy_boto3_s3control.type_defs import (
    JobManifestTypeDef,
    JobOperationTypeDef,
    JobReportTypeDef,
)

from s3_batch_replication.aws.boto import client
from s3_batch_replication.aws.s3 import parse_s3_uri


def get_object_etag(bucket: str, key: str) -> str:
    """
    Get the ETag of an S3 object.

    :param bucket: S3 bucket name.
    :param key: S3 object key.
    :return: The ETag string, with surrounding quotes stripped.
    :raises RuntimeError: If the object cannot be accessed.
    """
    try:
        response = cast(S3Client, client("s3")).head_object(Bucket=bucket, Key=key)
        return response["ETag"].strip('"')
    except (ClientError, BotoCoreError) as e:
        raise RuntimeError(f"Failed to get ETag for s3://{bucket}/{key}: {e}") from e


def create_batch_replication_job(
    manifest_uri: str,
    role_arn: str,
    account_id: str,
    description: str = "",
    priority: int = 10,
    report_bucket_arn: str | None = None,
    report_scope: Literal["AllTasks", "FailedTasksOnly"] = "AllTasks",
    confirmation_required: bool = True,
) -> str:
    """
    Create an S3 Batch Replication job.

    The job must be manually activated in the console or via the API after review.

    :param manifest_uri: S3 URI of the inventory manifest CSV to replicate from.
    :param role_arn: IAM role ARN that S3 Batch Operations will assume to run the job.
    :param account_id: AWS account ID that owns the job.
    :param description: Human-readable job description. Defaults to the manifest URI.
    :param priority: Job priority — higher values run first. Defaults to 10.
    :param report_bucket_arn: ARN of the S3 bucket to write completion reports to.
        If omitted, completion reporting is disabled.
    :param report_scope: Report scope — ``AllTasks`` (default) or ``FailedTasksOnly``.
        Only used when ``report_bucket_arn`` is provided.
    :param confirmation_required: If True (default), job is created in suspended state
        and must be manually activated. If False, job starts immediately.
    :return: The job ID of the created batch replication job.
    :raises RuntimeError: If the job cannot be created.
    """
    bucket, key = parse_s3_uri(manifest_uri)
    etag = get_object_etag(bucket, key)
    object_arn = f"arn:aws:s3:::{bucket}/{key}"

    operation: JobOperationTypeDef = {"S3ReplicateObject": {}}
    manifest: JobManifestTypeDef = {
        "Spec": {"Format": "S3InventoryReport_CSV_20161130"},
        "Location": {"ObjectArn": object_arn, "ETag": etag},
    }
    report: JobReportTypeDef
    if report_bucket_arn:
        report = {"Enabled": True, "Bucket": report_bucket_arn, "Format": "Report_CSV_20180820", "ReportScope": report_scope}
    else:
        report = {"Enabled": False}

    try:
        response = cast(S3ControlClient, client("s3control")).create_job(
            AccountId=account_id,
            ConfirmationRequired=confirmation_required,
            Operation=operation,
            Manifest=manifest,
            Report=report,
            Priority=priority,
            RoleArn=role_arn,
            ClientRequestToken=str(uuid.uuid4()),
            Description=description or f"Batch replication from {manifest_uri}",
        )
    except (ClientError, BotoCoreError) as e:
        raise RuntimeError(f"Failed to create batch job for {manifest_uri}: {e}") from e

    return response["JobId"]
