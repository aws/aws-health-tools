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

"""validate-setup subcommand — pre-flight checks before running batch replication."""

import json
import logging
import sys
from typing import cast

import click
from botocore.exceptions import ClientError
from mypy_boto3_s3 import S3Client

from s3_batch_replication.aws.boto import client
from s3_batch_replication.aws.complete import complete_buckets
from s3_batch_replication.aws.iam import (
    validate_role_kms_permissions,
    validate_role_trust_policy,
)
from s3_batch_replication.aws.s3 import S3_BATCH_OPERATIONS_PRINCIPAL
from s3_batch_replication.cli import cli
from s3_batch_replication.types import IamRoleArn, S3BucketArn

logger = logging.getLogger(__name__)


def _result(ctx: click.Context, label: str, passed: bool, detail: str = "") -> None:
    if not ctx.obj.get("quiet"):
        icon = "✓" if passed else "✗"
        msg = f"{icon} {label}"
        if detail:
            msg += f": {detail}"
        click.echo(msg)


def _check_versioning(ctx: click.Context, s3: S3Client, source_bucket: str | None, destination_bucket: str | None) -> bool:
    """Check versioning is enabled on source and destination buckets."""
    failed = False
    for bucket, label in [(source_bucket, "source"), (destination_bucket, "destination")]:
        if not bucket:
            _result(ctx, f"Versioning ({label})", False, "bucket not specified")
            failed = True
            continue
        try:
            status = s3.get_bucket_versioning(Bucket=bucket).get("Status")
            ok = status == "Enabled"
            _result(ctx, f"Versioning ({label}: {bucket})", ok, status or "not enabled")
            if not ok:
                failed = True
        except ClientError as e:
            _result(ctx, f"Versioning ({label}: {bucket})", False, str(e))
            failed = True
    return failed


def _check_replication_rule(ctx: click.Context, s3: S3Client, source_bucket: str | None) -> bool:
    """Check at least one enabled replication rule exists on the source bucket."""
    if not source_bucket:
        _result(ctx, "Replication rule", False, "source bucket not specified")
        return True
    try:
        config = s3.get_bucket_replication(Bucket=source_bucket)
        rules = config.get("ReplicationConfiguration", {}).get("Rules", [])
        enabled = [r for r in rules if r.get("Status") == "Enabled"]
        ok = bool(enabled)
        _result(ctx, f"Replication rule ({source_bucket})", ok,
                f"{len(enabled)} enabled rule(s)" if ok else "no enabled rules found")
        return not ok
    except ClientError as e:
        if e.response["Error"]["Code"] == "ReplicationConfigurationNotFoundError":
            _result(ctx, f"Replication rule ({source_bucket})", False, "no replication configuration")
        else:
            _result(ctx, f"Replication rule ({source_bucket})", False, str(e))
        return True


def _check_iam_role(ctx: click.Context, role_arn: str | None) -> bool:
    """Check the IAM role trusts batchoperations.s3.amazonaws.com."""
    if not role_arn:
        _result(ctx, "IAM role", False, "role ARN not specified")
        return True
    role_name = role_arn.split("/")[-1]
    try:
        validate_role_trust_policy(role_arn, S3_BATCH_OPERATIONS_PRINCIPAL)
        _result(ctx, f"IAM role trust policy ({role_name})", True, "trusts batchoperations.s3.amazonaws.com")
        return False
    except RuntimeError as e:
        _result(ctx, f"IAM role trust policy ({role_name})", False, str(e))
        return True


def _check_inventory(ctx: click.Context, s3: S3Client, source_bucket: str | None) -> tuple[bool, str | None]:
    """
    Check inventory configuration on the source bucket.

    :return: (failed, inventory_dest_bucket)
    """
    if not source_bucket:
        _result(ctx, "Inventory config", False, "source bucket not specified")
        return True, None
    try:
        configs = s3.list_bucket_inventory_configurations(Bucket=source_bucket)
        inventories = configs.get("InventoryConfigurationList", [])
        csv_configs = [c for c in inventories if c.get("Destination", {}).get("S3BucketDestination", {}).get("Format") == "CSV"]
        ok = bool(csv_configs)
        _result(ctx, f"Inventory config ({source_bucket})", ok,
                f"{len(csv_configs)} CSV inventory config(s)" if ok else "no CSV inventory configuration found")
        if not ok:
            return True, None

        # VersionId is included when IncludedObjectVersions is "All" — not via OptionalFields
        has_version_id = csv_configs[0].get("IncludedObjectVersions") == "All"
        _result(ctx, f"Inventory VersionId field ({source_bucket})", has_version_id,
                "IncludedObjectVersions=All (VersionId included)" if has_version_id else
                "IncludedObjectVersions is not 'All' — S3 Batch Replication requires VersionId; "
                "set IncludedObjectVersions=All in the inventory configuration")

        dest_arn = csv_configs[0]["Destination"]["S3BucketDestination"]["Bucket"]
        inventory_dest_bucket = dest_arn.split(":::")[-1]
        inventory_prefix = csv_configs[0]["Destination"]["S3BucketDestination"].get("Prefix", "")
        logger.debug("Inventory destination: s3://%s/%s", inventory_dest_bucket, inventory_prefix)
        return not has_version_id, inventory_dest_bucket
    except ClientError as e:
        _result(ctx, f"Inventory config ({source_bucket})", False, str(e))
        return True, None


def _check_bucket_policy_action(ctx: click.Context, s3: S3Client, bucket: str, label: str, required_action: str) -> bool:
    """Check a bucket policy allows s3.amazonaws.com to perform required_action."""
    try:
        policy = json.loads(s3.get_bucket_policy(Bucket=bucket)["Policy"])
        allowed = any(
            stmt.get("Effect") == "Allow"
            and stmt.get("Principal", {}).get("Service") == "s3.amazonaws.com"
            and required_action in (
                [stmt["Action"]] if isinstance(stmt["Action"], str) else stmt["Action"]
            )
            for stmt in policy.get("Statement", [])
        )
        _result(ctx, f"{label} ({bucket})", allowed,
                f"allows s3.amazonaws.com {required_action}" if allowed else f"missing {required_action} for s3.amazonaws.com")
        return not allowed
    except ClientError as e:
        if e.response["Error"]["Code"] == "NoSuchBucketPolicy":
            _result(ctx, f"{label} ({bucket})", False, "no bucket policy")
        else:
            _result(ctx, f"{label} ({bucket})", False, str(e))
        return True


def _check_report_bucket_writable(ctx: click.Context, s3: S3Client, report_bucket_arn: str) -> bool:
    """Check the report bucket allows s3:PutObject from batchoperations.s3.amazonaws.com."""
    # Strip arn:aws:s3::: prefix to get bucket name
    bucket = report_bucket_arn.split(":::")[-1]
    try:
        policy = json.loads(s3.get_bucket_policy(Bucket=bucket)["Policy"])
        allowed = any(
            stmt.get("Effect") == "Allow"
            and stmt.get("Principal", {}).get("Service") == "batchoperations.s3.amazonaws.com"
            and "s3:PutObject" in (
                [stmt["Action"]] if isinstance(stmt["Action"], str) else stmt["Action"]
            )
            for stmt in policy.get("Statement", [])
        )
        _result(ctx, f"Report bucket policy ({bucket})", allowed,
                "allows batchoperations.s3.amazonaws.com s3:PutObject" if allowed
                else "missing s3:PutObject for batchoperations.s3.amazonaws.com")
        return not allowed
    except ClientError as e:
        if e.response["Error"]["Code"] == "NoSuchBucketPolicy":
            _result(ctx, f"Report bucket policy ({bucket})", False, "no bucket policy")
        else:
            _result(ctx, f"Report bucket policy ({bucket})", False, str(e))
        return True


def _check_kms(ctx: click.Context, role_arn: str, source_kms_key: str | None, dest_kms_key: str | None) -> bool:
    """Smoke-test KMS permissions on the IAM role for source and destination keys."""
    failed = False
    for key_arn, actions, label in [
        (source_kms_key, ["kms:Decrypt"], "source"),
        (dest_kms_key, ["kms:Encrypt", "kms:GenerateDataKey"], "destination"),
    ]:
        if not key_arn:
            continue
        try:
            validate_role_kms_permissions(role_arn, key_arn, actions)
            _result(ctx, f"KMS permissions ({label})", True, f"allows {actions} on {key_arn}")
        except RuntimeError as e:
            _result(ctx, f"KMS permissions ({label})", False, str(e))
            failed = True
    return failed


@cli.command("validate-setup")
@click.option("--source-bucket", default=None, shell_complete=complete_buckets, help="Source S3 bucket name")
@click.option("--destination-bucket", default=None, shell_complete=complete_buckets, help="Destination S3 bucket name")
@click.option("--role-arn", type=IamRoleArn(), default=None, help="IAM role ARN for replication")
@click.option("--report-bucket", type=S3BucketArn(), default=None, shell_complete=complete_buckets, help="S3 bucket ARN (or name) for completion reports — checks write access if provided")
@click.option("--no-check-versioning", is_flag=True, default=False, help="Skip versioning checks")
@click.option("--no-check-replication-rule", is_flag=True, default=False, help="Skip replication rule check")
@click.option("--no-check-iam-role", is_flag=True, default=False, help="Skip IAM role trust policy check")
@click.option("--no-check-inventory", is_flag=True, default=False, help="Skip inventory configuration check")
@click.option("--no-check-inventory-policy", is_flag=True, default=False, help="Skip inventory bucket policy check")
@click.option("--no-check-kms", is_flag=True, default=False, help="Skip KMS key permissions check")
@click.pass_context
def validate_setup(
    ctx: click.Context,
    source_bucket: str | None,
    destination_bucket: str | None,
    role_arn: str | None,
    report_bucket: str | None,
    no_check_versioning: bool,
    no_check_replication_rule: bool,
    no_check_iam_role: bool,
    no_check_inventory: bool,
    no_check_inventory_policy: bool,
    no_check_kms: bool,
) -> None:
    """Run pre-flight checks before executing batch replication.

    Should be run after setup-iam-role and setup-replication-rules when chaining,
    so that the IAM role propagation delay has already been applied.
    """
    ctx.ensure_object(dict)

    if not source_bucket:
        source_bucket = ctx.obj.get("source_bucket")
    if not destination_bucket:
        destination_bucket = ctx.obj.get("dest_bucket")
    if not role_arn:
        role_arn = ctx.obj.get("role_arn")
    if not report_bucket:
        report_bucket = ctx.obj.get("report_bucket")

    if not report_bucket:
        report_bucket = ctx.obj.get("report_bucket")

    source_kms_key: str | None = ctx.obj.get("source_kms_key")
    dest_kms_key: str | None = ctx.obj.get("dest_kms_key")

    s3: S3Client = cast(S3Client, client("s3"))
    failed = False

    if not no_check_versioning:
        failed |= _check_versioning(ctx, s3, source_bucket, destination_bucket)

    if not no_check_replication_rule:
        failed |= _check_replication_rule(ctx, s3, source_bucket)

    if not no_check_iam_role:
        failed |= _check_iam_role(ctx, role_arn)

    inventory_dest_bucket = None
    if not no_check_inventory:
        inv_failed, inventory_dest_bucket = _check_inventory(ctx, s3, source_bucket)
        failed |= inv_failed

    if not no_check_inventory_policy:
        bucket = inventory_dest_bucket or source_bucket
        if not bucket:
            _result(ctx, "Inventory bucket policy", False, "bucket not determined")
            failed = True
        else:
            failed |= _check_bucket_policy_action(ctx, s3, bucket, "Inventory bucket policy", "s3:PutObject")

    # Note: destination bucket policy (s3:ReplicateObject) is not checked here because
    # for cross-account replication the destination bucket is in a different account and
    # cannot be validated from the source account. For cross-account replication, ensure
    # the destination bucket policy grants s3:ReplicateObject to the source account manually.

    if report_bucket:
        failed |= _check_report_bucket_writable(ctx, s3, report_bucket)

    if not no_check_kms and role_arn:
        failed |= _check_kms(ctx, role_arn, source_kms_key, dest_kms_key)

    if report_bucket:
        ctx.obj["report_bucket"] = report_bucket

    if failed:
        sys.exit(1)
