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

"""setup-replication-rules subcommand — configures CRR on the source bucket."""

import logging
import uuid
from typing import cast

import click
from botocore.exceptions import BotoCoreError, ClientError
from mypy_boto3_s3 import S3Client
from mypy_boto3_s3.type_defs import (
    ReplicationConfigurationTypeDef,
    ReplicationRuleTypeDef,
)

from s3_batch_replication.aws.boto import client
from s3_batch_replication.aws.complete import complete_buckets
from s3_batch_replication.aws.iam import resolve_role_arn
from s3_batch_replication.cli import cli
from s3_batch_replication.output import echo
from s3_batch_replication.types import IamRoleArn

logger = logging.getLogger(__name__)




@cli.command("setup-replication-rules")
@click.option("--source-bucket", default=None, shell_complete=complete_buckets, help="Source S3 bucket name")
@click.option("--destination-bucket", default=None, shell_complete=complete_buckets, help="Destination S3 bucket name")
@click.option("--role-arn", type=IamRoleArn(), default=None, help="IAM role ARN for replication")
@click.option("--force", is_flag=True, default=False, help="Overwrite existing replication configuration")
@click.pass_context
def setup_replication_rules(ctx: click.Context, source_bucket: str, destination_bucket: str, role_arn: str, force: bool) -> None:
    """Configure a Cross-Region Replication rule on the source bucket.

    Creates the destination bucket if it does not exist and enables versioning on both buckets.
    """
    ctx.ensure_object(dict)
    s3: S3Client = cast(S3Client, client("s3"))

    if not source_bucket:
        source_bucket = ctx.obj.get("source_bucket")
    if not source_bucket:
        raise click.UsageError("--source-bucket is required when not chained after setup-iam-role")

    if not destination_bucket:
        destination_bucket = ctx.obj.get("dest_bucket")
    if not destination_bucket:
        raise click.UsageError("--destination-bucket is required when not chained after setup-iam-role")

    role_arn = resolve_role_arn(ctx, role_arn)

    destination_bucket_arn = f"arn:aws:s3:::{destination_bucket}"

    logger.info("Configuring replication: %s → %s", source_bucket, destination_bucket)

    # Enable versioning on source bucket
    versioning = s3.get_bucket_versioning(Bucket=source_bucket)
    status = versioning.get("Status", "")
    logger.debug("Source bucket versioning status: %s", status or "Not enabled")
    if status == "Suspended":
        raise click.ClickException(
            f"Versioning is suspended on source bucket {source_bucket!r}. "
            "Re-enable it manually before configuring replication."
        )
    if status != "Enabled":
        s3.put_bucket_versioning(Bucket=source_bucket, VersioningConfiguration={"Status": "Enabled"})
        echo(ctx, f"Enabled versioning on source bucket {source_bucket!r}")

    # Check destination bucket exists and enable versioning
    try:
        s3.head_bucket(Bucket=destination_bucket)
        logger.debug("Destination bucket %s exists", destination_bucket)
    except ClientError as e:
        if e.response["Error"]["Code"] == "404":
            raise click.ClickException(
                f"Destination bucket {destination_bucket!r} does not exist. Create it before running this command."
            ) from e
        raise click.ClickException(f"Cannot access destination bucket {destination_bucket!r}: {e}") from e

    # Enable versioning on destination bucket
    s3_for_dest = s3
    dest_status = s3_for_dest.get_bucket_versioning(Bucket=destination_bucket).get("Status", "")
    if dest_status != "Enabled":
        raise click.ClickException(
            f"Versioning is not enabled on destination bucket {destination_bucket!r} (status: {dest_status or 'Not enabled'}). "
            "S3 replication requires versioning on both buckets."
        )

    # Check for existing replication configuration
    existing_rules: list = []
    existing_role_arn: str | None = None
    try:
        existing = s3.get_bucket_replication(Bucket=source_bucket)
        existing_rules = existing.get("ReplicationConfiguration", {}).get("Rules", [])
        existing_role_arn = existing.get("ReplicationConfiguration", {}).get("Role")
        logger.debug("Existing replication rules found: %d", len(existing_rules))
        if not force:
            raise click.ClickException(
                f"Bucket {source_bucket!r} already has a replication configuration. "
                "Use --force to add a new rule to the existing configuration."
            )
        echo(ctx, f"Warning: adding new rule to existing replication configuration on {source_bucket!r}")
    except ClientError as e:
        if e.response["Error"]["Code"] != "ReplicationConfigurationNotFoundError":
            raise click.ClickException(f"Failed to check replication configuration: {e}") from e
        logger.debug("No existing replication configuration found")
        existing_rules = []

    rule_id = f"batch-replication-{uuid.uuid4().hex[:8]}"
    logger.debug("Generated rule ID: %s", rule_id)

    # Assign priority higher than any existing rule
    max_priority = max((r.get("Priority", 0) for r in existing_rules), default=0)

    # Pull KMS keys from context (set by setup-iam-role when chaining)
    source_kms_key: str | None = ctx.obj.get("source_kms_key")
    dest_kms_key: str | None = ctx.obj.get("dest_kms_key")

    destination_config: dict = {"Bucket": destination_bucket_arn}
    if dest_kms_key:
        destination_config["EncryptionConfiguration"] = {"ReplicaKmsKeyID": dest_kms_key}
        logger.debug("Using destination KMS key for replica encryption: %s", dest_kms_key)

    rule: ReplicationRuleTypeDef = {
        "ID": rule_id,
        "Priority": max_priority + 1,
        "Status": "Enabled",
        "Filter": {"Prefix": ""},
        "Destination": destination_config,
        "DeleteMarkerReplication": {"Status": "Disabled"},
    }
    if source_kms_key:
        rule["SourceSelectionCriteria"] = {"SseKmsEncryptedObjects": {"Status": "Enabled"}}
        logger.debug("Enabling SSE-KMS object replication for source key: %s", source_kms_key)
    replication_config: ReplicationConfigurationTypeDef = {
        "Role": existing_role_arn or role_arn,
        "Rules": [*existing_rules, rule],
    }
    if existing_role_arn:
        logger.debug("Preserving existing replication role: %s", existing_role_arn)
        if role_arn and existing_role_arn != role_arn:
            echo(ctx, (
                f"Warning: existing replication configuration already has role {existing_role_arn!r} — "
                f"ignoring provided role {role_arn!r} and preserving the existing one. "
                f"If the existing role does not have permissions for the new destination bucket "
                f"{destination_bucket!r}, update it manually or re-run setup-iam-role with --force."
            ))
        else:
            echo(ctx, (
                f"Note: preserving existing replication role {existing_role_arn!r}. "
                f"Ensure it has s3:ReplicateObject permissions on the new destination bucket {destination_bucket!r}."
            ))

    try:
        s3.put_bucket_replication(
            Bucket=source_bucket,
            ReplicationConfiguration=replication_config,
        )
    except (ClientError, BotoCoreError) as e:
        raise click.ClickException(f"Failed to put replication configuration: {e}") from e

    echo(ctx, f"Replication rule {rule_id!r} configured on {source_bucket!r} → {destination_bucket_arn}")
