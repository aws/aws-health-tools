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

"""split-files subcommand — splits inventory CSV files into smaller chunks for synthetic testing."""

import gzip
import hashlib
import io
import logging
from typing import cast

import click
from mypy_boto3_s3 import S3Client

from s3_batch_replication.aws.boto import client as aws_client
from s3_batch_replication.aws.s3 import download_manifest, parse_s3_uri
from s3_batch_replication.cli import cli
from s3_batch_replication.manifest import (
    ManifestFile,
    build_manifest,
    parse_manifest,
    serialise_manifest,
)
from s3_batch_replication.output import echo
from s3_batch_replication.types import ManifestInput

logger = logging.getLogger(__name__)


def _split_csv_gz(data: bytes, rows_per_file: int) -> tuple[list[bytes], int]:
    """
    Decompress a ``.csv.gz`` inventory file and split it into compressed chunks.

    Output is deterministically compressed (``mtime=0``) so MD5 checksums are
    stable for identical input.

    :param data: Raw compressed bytes of a ``.csv.gz`` inventory file.
    :param rows_per_file: Number of rows per output chunk.
    :return: Tuple of (list of compressed chunk bytes, total input row count).
    """
    lines = gzip.decompress(data).splitlines(keepends=True)
    input_rows = len(lines)
    chunks = []
    i = 0
    while i < len(lines):
        chunk = lines[i:i + rows_per_file]
        buf = io.BytesIO()
        with gzip.GzipFile(fileobj=buf, mode="wb", mtime=0) as gz:
            gz.writelines(chunk)
        chunks.append(buf.getvalue())
        i += rows_per_file
    return chunks, input_rows


@cli.command("split-files")
@click.option("--manifest", type=ManifestInput(), default=None, help="S3 URI or local path of the inventory manifest.json")
@click.option("--output-prefix", default="synth/", show_default=True, help="S3 key prefix for synthetic output (relative to source bucket)")
@click.option("--rows-per-file", type=int, default=100_000, show_default=True, help="Row count per output file")
@click.pass_context
def split_files(ctx: click.Context, manifest: str | None, output_prefix: str, rows_per_file: int) -> None:
    """Split inventory CSV files into smaller chunks to produce a synthetic test manifest."""
    ctx.ensure_object(dict)

    if not manifest:
        manifest = ctx.obj.get("manifest")
    if not manifest:
        raise click.UsageError("--manifest is required when not chained after another command")
    if not manifest.startswith("s3://"):
        raise click.UsageError("--manifest must be an S3 URI for split-files")

    try:
        manifest_data = download_manifest(manifest)
        manifest_obj = parse_manifest(manifest_data)
    except RuntimeError as e:
        raise click.ClickException(str(e)) from e

    logger.info("Manifest: %s  input files: %d", manifest, len(manifest_obj.files))
    logger.debug("rows-per-file: %d", rows_per_file)

    source_bucket, _ = parse_s3_uri(manifest)
    s3: S3Client = cast(S3Client, aws_client("s3"))
    synthetic_files: list[ManifestFile] = []
    total_input_rows = 0
    total_output_rows = 0

    for f in manifest_obj.files:
        stem = f.key.rsplit(".", 2)[0]  # strip .csv.gz
        filename_stem = stem.split("/")[-1]

        logger.debug("Downloading s3://%s/%s (%d bytes)", source_bucket, f.key, f.size)
        response = s3.get_object(Bucket=source_bucket, Key=f.key)
        raw = response["Body"].read()

        chunks, input_rows = _split_csv_gz(raw, rows_per_file)
        total_input_rows += input_rows
        logger.info("s3://%s/%s → %d chunks (%d rows)", source_bucket, f.key, len(chunks), input_rows)

        for i, chunk in enumerate(chunks):
            dest_key = f"{output_prefix.rstrip('/')}/{filename_stem}_part{i + 1:02d}.csv.gz"
            md5 = hashlib.md5(chunk).hexdigest()
            chunk_rows = len(gzip.decompress(chunk).splitlines())
            total_output_rows += chunk_rows
            s3.put_object(Bucket=source_bucket, Key=dest_key, Body=chunk)
            synthetic_files.append(ManifestFile(key=dest_key, size=len(chunk), md5_checksum=md5))
            echo(ctx, f"  {dest_key} ({len(chunk):,} bytes)")
            logger.debug("  md5: %s  rows: %d", md5, chunk_rows)

    if total_output_rows != total_input_rows:
        raise click.ClickException(
            f"Row count mismatch: input had {total_input_rows:,} rows but output has {total_output_rows:,} rows"
        )

    synthetic_manifest = build_manifest(manifest_obj, synthetic_files)
    manifest_bytes = serialise_manifest(synthetic_manifest)
    manifest_key = f"{output_prefix.rstrip('/')}/manifest.json"
    checksum_key = f"{output_prefix.rstrip('/')}/manifest.checksum"

    s3.put_object(Bucket=source_bucket, Key=manifest_key, Body=manifest_bytes)
    s3.put_object(Bucket=source_bucket, Key=checksum_key, Body=hashlib.md5(manifest_bytes).hexdigest().encode())

    synthetic_uri = f"s3://{source_bucket}/{manifest_key}"
    echo(ctx, f"Synthetic manifest: {synthetic_uri} ({len(synthetic_files)} files)")
    logger.debug("Checksum written to s3://%s/%s", source_bucket, checksum_key)

    ctx.obj["manifest"] = synthetic_uri
    ctx.obj["objects_per_manifest_file"] = rows_per_file
