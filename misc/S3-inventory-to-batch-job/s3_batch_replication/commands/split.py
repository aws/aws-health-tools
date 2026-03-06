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

"""Split subcommand — partitions a master inventory manifest into sub-manifests."""

import hashlib
import logging
from dataclasses import replace

import click

from s3_batch_replication.aws.s3 import download_manifest, parse_s3_uri, upload_manifest
from s3_batch_replication.cli import cli
from s3_batch_replication.manifest import (
    build_manifest,
    parse_manifest,
    partition_files,
    serialise_manifest,
)
from s3_batch_replication.output import echo
from s3_batch_replication.types import (
    ObjectCount,
    OutputDestination,
    PercentageToFloat,
    S3Uri,
)

logger = logging.getLogger(__name__)


@cli.command()
@click.option("--manifest", type=S3Uri(), default=None, help="S3 URI of the inventory manifest.json")
@click.option("--objects-per-job", type=ObjectCount(), default="10B", show_default=True, help="Max objects per batch replication job (e.g. 10B, 500M)")
@click.option("--objects-per-manifest-file", type=ObjectCount(), default=None, show_default="3M", help="Approximate number of objects per inventory manifest file (e.g. 3M)")
@click.option("--output", type=OutputDestination, default=None, help="S3 URI prefix or local directory for sub-manifests (default: same prefix as input manifest)")
@click.option("--max-objects", type=ObjectCount(), default=None, help="Only include up to this many objects across all jobs (useful for testing)")
@click.option("--failure-threshold", type=PercentageToFloat(), default="0", show_default=True, help="Percentage of sub-manifest upload failures to tolerate before aborting (0 = any failure aborts)")
@click.option("--continue-after-failure", is_flag=True, default=False, help="Continue uploading remaining sub-manifests after the failure threshold is reached; still exits non-zero and does not chain to replicate")
@click.pass_context
def split(ctx: click.Context, manifest: str | None, objects_per_job: int, objects_per_manifest_file: int | None, output: str | None, max_objects: int | None, failure_threshold: float, continue_after_failure: bool) -> None:
    """Partition an S3 Inventory manifest into sub-manifests for batch replication jobs."""
    ctx.ensure_object(dict)

    if not manifest:
        manifest = ctx.obj.get("manifest")
    if not manifest:
        raise click.UsageError("--manifest is required when not chained after split-files")

    objects_per_manifest_file_explicit = objects_per_manifest_file is not None
    if objects_per_manifest_file is None:
        objects_per_manifest_file = ctx.obj.get("objects_per_manifest_file", 3_000_000)

    try:
        manifest_data = download_manifest(manifest)
        manifest_obj = parse_manifest(manifest_data)
    except RuntimeError as e:
        raise click.ClickException(str(e)) from e

    logger.info("Manifest: %s", manifest)
    logger.info("Source bucket: %s  inventory files: %d", manifest_obj.source_bucket, len(manifest_obj.files))
    logger.debug("objects-per-job: %d  objects-per-manifest-file: %d", objects_per_job, objects_per_manifest_file)

    if max_objects is not None:
        max_files = max(1, max_objects // objects_per_manifest_file)
        if max_files < len(manifest_obj.files):
            click.echo(f"Warning: --max-objects limits processing to {max_files} of {len(manifest_obj.files)} inventory files (~{max_files * objects_per_manifest_file:,} objects)", err=True)
            manifest_obj = replace(manifest_obj, files=manifest_obj.files[:max_files])

    bucket, key = parse_s3_uri(manifest)
    key_stem = key.removesuffix(".json")
    output_prefix = output or f"s3://{bucket}/{'/'.join(key.split('/')[:-1])}"
    base_name = key_stem.split("/")[-1]

    # objects_per_manifest_file is an estimate — files_per_job is therefore approximate,
    # but precise enough for distributing load across jobs.
    files_per_job = objects_per_job // objects_per_manifest_file
    if files_per_job < 1:
        raise click.UsageError(
            f"--objects-per-job ({objects_per_job:,}) is less than --objects-per-manifest-file "
            f"({objects_per_manifest_file:,}) — would produce empty jobs. "
            "Increase --objects-per-job or decrease --objects-per-manifest-file."
        )
    if objects_per_manifest_file_explicit:
        click.echo(
            "Warning: --objects-per-manifest-file is overriding the default estimate of 2.5M. "
            "Ensure this reflects the actual density of your inventory files.",
            err=True,
        )
    if files_per_job < 3:
        click.echo(
            f"Warning: --objects-per-job / --objects-per-manifest-file = {files_per_job} file(s) per job. "
            "With so few files per job, the estimate in --objects-per-manifest-file has an outsized effect "
            "on how many jobs are created. Verify the actual file density from your inventory manifest before proceeding.",
            err=True,
        )
    logger.debug("files-per-job: %d  output-prefix: %s", files_per_job, output_prefix)

    total_parts = -(-len(manifest_obj.files) // files_per_job)  # ceiling division
    written: list[str] = []
    failed: list[str] = []
    covered_files = 0
    threshold_exceeded = False

    for i, partition in enumerate(partition_files(manifest_obj.files, files_per_job)):
        sub_manifest = build_manifest(manifest_obj, partition)
        content = serialise_manifest(sub_manifest)
        filename = f"{base_name}_part{i + 1}.json"

        if threshold_exceeded and not continue_after_failure:
            break

        try:
            destination = upload_manifest(content, output_prefix, filename)
            upload_manifest(hashlib.md5(content).hexdigest().encode(), output_prefix, filename.replace(".json", ".checksum"))
            written.append(destination)
            covered_files += len(partition)
            echo(ctx, f"Part {i + 1}: {len(partition)} files (~{len(partition) * objects_per_manifest_file:,} objects) → {destination}")
        except Exception as e:
            failed.append(filename)
            click.echo(f"Warning: failed to write sub-manifest {filename}: {e}", err=True)
            failure_rate = len(failed) / total_parts
            if failure_rate > failure_threshold:
                threshold_exceeded = True
                click.echo(
                    f"Error: failure threshold exceeded ({len(failed)}/{total_parts} = "
                    f"{failure_rate:.0%} > {failure_threshold}%).",
                    err=True,
                )
                if not continue_after_failure:
                    break

    logger.info("Total parts written: %d  failed: %d", len(written), len(failed))

    if covered_files != len(manifest_obj.files):
        click.echo(
            f"Warning: {covered_files:,} of {len(manifest_obj.files):,} inventory files covered by uploaded manifests "
            f"({len(manifest_obj.files) - covered_files:,} in failed or skipped uploads)",
            err=True,
        )
    else:
        logger.info("All %d inventory files covered by uploaded manifests", len(manifest_obj.files))

    if failed and not threshold_exceeded:
        # Failures within threshold — warn but allow chaining
        click.echo(f"Warning: {len(failed)} sub-manifest(s) failed but within threshold ({failure_threshold}%)", err=True)

    if threshold_exceeded:
        # Do not propagate to replicate — exit non-zero after optionally finishing uploads
        ctx.exit(1)
        return

    ctx.obj["split_manifests"] = written
