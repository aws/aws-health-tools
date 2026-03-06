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
@click.option("--destination-region", default=None, help="AWS region for destination bucket (required if creating new bucket)")
@click.option("--role-arn", type=IamRoleArn(), default=None, help="IAM role ARN for replication")
@click.option("--force", is_flag=True, default=False, help="Overwrite existing replication configuration")
@click.pass_context
def setup_replication_rules(ctx: click.Context, source_bucket: str, destination_bucket: str, destination_region: str | None, role_arn: str, force: bool) -> None:
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
    status = versioning.get("Status", "Not enabled")
    logger.debug("Source bucket versioning status: %s", status)
    if status != "Enabled":
        s3.put_bucket_versioning(Bucket=source_bucket, VersioningConfiguration={"Status": "Enabled"})
        echo(ctx, f"Enabled versioning on source bucket {source_bucket!r}")

    # Check/create destination bucket and enable versioning
    s3_dest: S3Client | None = None
    try:
        s3.head_bucket(Bucket=destination_bucket)
        logger.debug("Destination bucket %s exists", destination_bucket)
    except ClientError as e:
        if e.response["Error"]["Code"] == "404":
            if not destination_region:
                raise click.UsageError("--destination-region is required when creating a new destination bucket")
            logger.info("Creating destination bucket %s in %s", destination_bucket, destination_region)
            s3_dest = cast(S3Client, client("s3", region_name=destination_region))
            if destination_region == "us-east-1":
                s3_dest.create_bucket(Bucket=destination_bucket)
            else:
                s3_dest.create_bucket(Bucket=destination_bucket, CreateBucketConfiguration={"LocationConstraint": destination_region})
            echo(ctx, f"Created destination bucket {destination_bucket!r} in {destination_region}")
        else:
            raise click.ClickException(f"Cannot access destination bucket {destination_bucket!r}: {e}") from e

    # Enable versioning on destination bucket (use destination region client if we created it)
    s3_for_dest = s3_dest or s3
    dest_versioning = s3_for_dest.get_bucket_versioning(Bucket=destination_bucket)
    if dest_versioning.get("Status") != "Enabled":
        s3_for_dest.put_bucket_versioning(Bucket=destination_bucket, VersioningConfiguration={"Status": "Enabled"})
        echo(ctx, f"Enabled versioning on destination bucket {destination_bucket!r}")

    # Check for existing replication configuration
    try:
        existing = s3.get_bucket_replication(Bucket=source_bucket)
        existing_rules = existing.get("ReplicationConfiguration", {}).get("Rules", [])
        logger.debug("Existing replication rules found: %d", len(existing_rules))
        if not force:
            raise click.ClickException(
                f"Bucket {source_bucket!r} already has a replication configuration. "
                "Use --force to overwrite (this replaces the entire configuration)."
            )
        echo(ctx, f"Warning: overwriting existing replication configuration on {source_bucket!r}")
    except ClientError as e:
        if e.response["Error"]["Code"] != "ReplicationConfigurationNotFoundError":
            raise click.ClickException(f"Failed to check replication configuration: {e}") from e
        logger.debug("No existing replication configuration found")

    rule_id = f"batch-replication-{uuid.uuid4().hex[:8]}"
    logger.debug("Generated rule ID: %s", rule_id)

    rule: ReplicationRuleTypeDef = {
        "ID": rule_id,
        "Priority": 1,
        "Status": "Enabled",
        "Filter": {"Prefix": ""},
        "Destination": {"Bucket": destination_bucket_arn},
        "DeleteMarkerReplication": {"Status": "Disabled"},
    }
    replication_config: ReplicationConfigurationTypeDef = {
        "Role": role_arn,
        "Rules": [rule],
    }

    try:
        s3.put_bucket_replication(
            Bucket=source_bucket,
            ReplicationConfiguration=replication_config,
        )
    except (ClientError, BotoCoreError) as e:
        raise click.ClickException(f"Failed to put replication configuration: {e}") from e

    echo(ctx, f"Replication rule {rule_id!r} configured on {source_bucket!r} → {destination_bucket_arn}")
