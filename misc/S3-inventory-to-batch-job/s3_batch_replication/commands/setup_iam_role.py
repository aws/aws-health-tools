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

"""setup-iam-role subcommand — creates the IAM role for S3 Batch Replication."""

import json
import logging
from typing import cast

import click
from botocore.exceptions import ClientError
from mypy_boto3_iam import IAMClient

from s3_batch_replication.aws.boto import client
from s3_batch_replication.aws.complete import complete_buckets
from s3_batch_replication.aws.s3 import get_bucket_kms_key, parse_s3_uri
from s3_batch_replication.cli import cli
from s3_batch_replication.output import echo
from s3_batch_replication.types import KmsKeyArn, S3Uri

logger = logging.getLogger(__name__)


_TRUST_POLICY = json.dumps({
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Principal": {"Service": "s3.amazonaws.com"},
            "Action": "sts:AssumeRole",
        },
        {
            "Effect": "Allow",
            "Principal": {"Service": "batchoperations.s3.amazonaws.com"},
            "Action": "sts:AssumeRole",
        },
    ],
})


def _build_permissions(source_bucket: str, dest_bucket: str, source_kms_key: str | None, dest_kms_key: str | None, manifest_bucket: str | None = None, report_bucket: str | None = None) -> dict:
    statements = [
        {
            "Effect": "Allow",
            "Action": ["s3:GetReplicationConfiguration", "s3:ListBucket"],
            "Resource": f"arn:aws:s3:::{source_bucket}",
        },
        {
            "Effect": "Allow",
            "Action": [
                "s3:GetObjectVersionForReplication",
                "s3:GetObjectVersionAcl",
                "s3:GetObjectVersionTagging",
                "s3:InitiateReplication",
                "s3:GetObject",
                "s3:GetObjectVersion",
            ],
            "Resource": f"arn:aws:s3:::{source_bucket}/*",
        },
        {
            "Effect": "Allow",
            "Action": ["s3:ReplicateObject", "s3:ReplicateDelete", "s3:ReplicateTags", "s3:ObjectOwnerOverrideToBucketOwner"],
            "Resource": f"arn:aws:s3:::{dest_bucket}/*",
        },
    ]

    # If the manifest lives in a different bucket, the role needs read access there too
    if manifest_bucket and manifest_bucket != source_bucket:
        statements.append({
            "Effect": "Allow",
            "Action": ["s3:GetObject", "s3:GetObjectVersion"],
            "Resource": f"arn:aws:s3:::{manifest_bucket}/*",
        })

    # Report bucket needs write access for job completion reports
    if report_bucket:
        statements.append({
            "Effect": "Allow",
            "Action": "s3:PutObject",
            "Resource": f"arn:aws:s3:::{report_bucket}/*",
        })

    if source_kms_key:
        statements.append({
            "Effect": "Allow",
            "Action": "kms:Decrypt",
            "Resource": source_kms_key,
            "Condition": {"StringLike": {"kms:ViaService": "s3.*.amazonaws.com"}},
        })

    if dest_kms_key:
        statements.append({
            "Effect": "Allow",
            "Action": ["kms:Encrypt", "kms:GenerateDataKey"],
            "Resource": dest_kms_key,
            "Condition": {"StringLike": {"kms:ViaService": "s3.*.amazonaws.com"}},
        })

    return {"Version": "2012-10-17", "Statement": statements}


@cli.command("setup-iam-role")
@click.option("--source-bucket", required=True, shell_complete=complete_buckets, help="Source S3 bucket name")
@click.option("--destination-bucket", required=True, shell_complete=complete_buckets, help="Destination S3 bucket name")
@click.option("--role-name", default=None, help="IAM role name (default: s3-batch-replication-<source-bucket>)")
@click.option("--source-kms-key", type=KmsKeyArn(), default=None, help="KMS key ARN used to encrypt objects in the source bucket")
@click.option("--dest-kms-key", type=KmsKeyArn(), default=None, help="KMS key ARN to use for encrypting replicated objects in the destination bucket")
@click.option("--manifest", type=S3Uri(), default=None, help="S3 URI of the inventory manifest — grants the role read access to the manifest bucket if different from the source bucket")
@click.option("--report-bucket", default=None, shell_complete=complete_buckets, help="S3 bucket for job completion reports — grants the role write access")
@click.option("--force", is_flag=True, default=False, help="Update permissions policy if role already exists")
@click.pass_context
def setup_iam_role(ctx: click.Context, source_bucket: str, destination_bucket: str, role_name: str | None, source_kms_key: str | None, dest_kms_key: str | None, manifest: str | None, report_bucket: str | None, force: bool) -> None:
    """Create an IAM role for S3 Batch Replication.

    When chained before setup-replication-rules or replicate, a propagation delay is
    automatically applied by the downstream command to allow the role to become consistent across AWS.
    """
    ctx.ensure_object(dict)
    iam: IAMClient = cast(IAMClient, client("iam"))

    if not manifest:
        manifest = ctx.obj.get("manifest")
    manifest_bucket = parse_s3_uri(manifest)[0] if manifest else None
    if manifest_bucket and manifest_bucket != source_bucket:
        logger.debug("Manifest bucket differs from source bucket — adding read permissions for %s", manifest_bucket)

    role_name = role_name or f"s3-batch-replication-{source_bucket}"[:64]  # IAM role names have a 64-character limit

    # Auto-detect KMS keys from bucket encryption config if not explicitly provided
    if source_kms_key is None:
        try:
            source_kms_key = get_bucket_kms_key(source_bucket)
            if source_kms_key:
                logger.debug("Auto-detected source KMS key: %s", source_kms_key)
        except RuntimeError as e:
            raise click.ClickException(str(e)) from e
    if dest_kms_key is None:
        try:
            dest_kms_key = get_bucket_kms_key(destination_bucket)
            if dest_kms_key:
                logger.debug("Auto-detected destination KMS key: %s", dest_kms_key)
        except RuntimeError as e:
            raise click.ClickException(str(e)) from e

    permissions = _build_permissions(source_bucket, destination_bucket, source_kms_key, dest_kms_key, manifest_bucket, report_bucket)
    policy_name = "S3BatchReplicationPolicy"

    logger.info("Setting up IAM role: %s", role_name)
    if source_kms_key:
        logger.debug("Source KMS key: %s", source_kms_key)
    if dest_kms_key:
        logger.debug("Dest KMS key: %s", dest_kms_key)

    # Try to fetch the role — if it exists, update it (or error without --force).
    # If it doesn't exist (NoSuchEntity), fall through to create it.
    try:
        role = iam.get_role(RoleName=role_name)
        role_arn = role["Role"]["Arn"]
        logger.debug("Role already exists: %s", role_arn)

        if not force:
            raise click.ClickException(
                f"IAM role {role_name!r} already exists. Use --force to update its permissions policy."
            )

        iam.put_role_policy(
            RoleName=role_name,
            PolicyName=policy_name,
            PolicyDocument=json.dumps(permissions),
        )
        echo(ctx, f"Updated permissions policy on existing role: {role_arn}")

    except ClientError as e:
        if e.response["Error"]["Code"] != "NoSuchEntity":
            raise click.ClickException(f"Failed to check IAM role: {e}") from e

        role = iam.create_role(
            RoleName=role_name,
            AssumeRolePolicyDocument=_TRUST_POLICY,
            Description=f"S3 Batch Replication role for {source_bucket} to {destination_bucket}",
        )
        role_arn = role["Role"]["Arn"]
        iam.put_role_policy(
            RoleName=role_name,
            PolicyName=policy_name,
            PolicyDocument=json.dumps(permissions),
        )
        echo(ctx, f"Created IAM role: {role_arn}")

    ctx.obj["role_arn"] = role_arn
    ctx.obj["source_bucket"] = source_bucket
    ctx.obj["dest_bucket"] = destination_bucket
    ctx.obj["source_kms_key"] = source_kms_key
    ctx.obj["dest_kms_key"] = dest_kms_key
    if manifest:
        ctx.obj["manifest"] = manifest
