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

"""Replicate subcommand — creates S3 Batch Replication jobs from sub-manifests."""

import logging
import pathlib
from typing import Literal

import click

from s3_batch_replication.aws.complete import complete_buckets
from s3_batch_replication.aws.iam import (
    get_account_id,
    resolve_role_arn,
    validate_role_trust_policy,
)
from s3_batch_replication.aws.s3 import S3_BATCH_OPERATIONS_PRINCIPAL, upload_manifest
from s3_batch_replication.aws.s3control import (
    create_batch_replication_job,
)
from s3_batch_replication.cli import cli
from s3_batch_replication.output import echo
from s3_batch_replication.types import IamRoleArn, ManifestInput, S3BucketArn

logger = logging.getLogger(__name__)


@cli.command()
@click.option("--manifests", type=ManifestInput(), multiple=True, default=None, help="S3 URIs or local file paths of sub-manifests")
@click.option("--role-arn", type=IamRoleArn(), default=None, help="IAM role ARN for the batch replication jobs")
@click.option("--dest-bucket", default=None, shell_complete=complete_buckets, help="S3 bucket to upload local manifests to (required if --manifests are local files)")
@click.option("--dest-prefix", default="", help="S3 key prefix for uploaded manifests")
@click.option("--priority", type=int, default=10, show_default=True, help="Job priority (higher = runs first)")
@click.option("--report-bucket", type=S3BucketArn(), default=None, shell_complete=complete_buckets, help="S3 bucket ARN (or name) to write completion reports to")
@click.option("--report-scope", type=click.Choice(["AllTasks", "FailedTasksOnly"]), default="AllTasks", show_default=True, help="Completion report scope (only used when --report-bucket is set)")
@click.option("--skip-iam-validation", is_flag=True, default=False, help="Skip IAM role trust policy validation")
@click.option("--no-confirmation", is_flag=True, default=False, help="Create jobs in active state instead of suspended (skips manual review step)")
@click.pass_context
def replicate(ctx: click.Context, manifests: tuple[str, ...], role_arn: str, dest_bucket: str | None, dest_prefix: str, priority: int, report_bucket: str | None, report_scope: Literal["AllTasks", "FailedTasksOnly"], skip_iam_validation: bool, no_confirmation: bool) -> None:
    """Create S3 Batch Replication jobs (suspended) from sub-manifests."""
    ctx.ensure_object(dict)

    role_arn = resolve_role_arn(ctx, role_arn)

    if not report_bucket:
        report_bucket = ctx.obj.get("report_bucket")

    # When chained after split, use the URIs written by that command
    if not manifests:
        manifests = tuple(ctx.obj.get("split_manifests", []))
    if not manifests:
        raise click.UsageError("--manifests is required when not chained after split")

    logger.info("Creating %d batch replication job(s)  priority: %d", len(manifests), priority)
    logger.debug("role-arn: %s  report-bucket: %s", role_arn, report_bucket)

    # Validate all manifests are the same type
    are_s3 = [m.startswith("s3://") for m in manifests]
    if any(are_s3) and not all(are_s3):
        raise click.UsageError("--manifests must be all S3 URIs or all local files, not a mix")

    local = not are_s3[0]

    if local and not dest_bucket:
        raise click.UsageError("--dest-bucket is required when --manifests are local files")
    if not local and dest_bucket:
        raise click.UsageError("--dest-bucket is not valid when --manifests are S3 URIs")

    if not skip_iam_validation:
        logger.debug("Validating IAM role trust policy for %s", S3_BATCH_OPERATIONS_PRINCIPAL)
        try:
            validate_role_trust_policy(role_arn, S3_BATCH_OPERATIONS_PRINCIPAL)
            logger.debug("IAM role trust policy OK")
        except RuntimeError as e:
            raise click.ClickException(str(e)) from e
    else:
        logger.info("Skipping IAM role trust policy validation")

    # Upload local manifests to S3 if needed
    s3_manifests: list[str] = []
    for m in manifests:
        if local:
            filename = pathlib.Path(m).name
            destination = f"s3://{dest_bucket}/{dest_prefix}" if dest_prefix else f"s3://{dest_bucket}"
            try:
                uri = upload_manifest(pathlib.Path(m).read_bytes(), destination, filename)
            except Exception as e:
                raise click.ClickException(f"Failed to upload {m}: {e}") from e
            echo(ctx, f"Uploaded {m} → {uri}")
            s3_manifests.append(uri)
        else:
            s3_manifests.append(m)

    try:
        account_id = get_account_id()
        logger.debug("AWS account ID: %s", account_id)
    except Exception as e:
        raise click.ClickException(f"Failed to determine AWS account ID: {e}") from e

    for i, uri in enumerate(s3_manifests, 1):
        logger.debug("Fetching ETag for %s", uri)
        try:
            job_id = create_batch_replication_job(
                manifest_uri=uri,
                role_arn=role_arn,
                account_id=account_id,
                description=f"Batch replication part {i} of {len(s3_manifests)}",
                priority=priority,
                report_bucket_arn=report_bucket,
                report_scope=report_scope,
                confirmation_required=not no_confirmation,
            )
        except RuntimeError as e:
            raise click.ClickException(str(e)) from e
        state = "active" if no_confirmation else "suspended"
        echo(ctx, f"Created job {job_id} ({state}) for {uri}")

    if not no_confirmation:
        echo(ctx, (
            "\nJobs are suspended and require manual activation. To run them:\n"
            "  1. Open the S3 console → Batch Operations\n"
            "  2. Select each job and choose 'Run job'\n"
            "  Or use: aws s3control update-job-status --account-id <account> "
            "--job-id <job-id> --requested-job-status Ready --region <region>"
        ))
