#!/usr/bin/env python3
# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
#
# SPDX-License-Identifier: Apache-2.0
#
# Licensed under the Apache License, Version 2.0 (the "License").
# You may not use this file except in compliance with the License.
# You may obtain a copy of the License at:
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Generate S3 Batch Operations manifests for cross-region copy.

Lists all objects in a source S3 bucket, splits them into standard (<=5 GB) and large (>5 GB) categories,
and uploads CSV manifest files to a manifest bucket. The manifests follow the S3BatchOperations_CSV_20180820
format and can be used directly with ``create_batch_copy_jobs.py`` to create S3 Batch Operations copy jobs.

Manifest naming convention:
    {manifest-key}-001.csv, {manifest-key}-002.csv, ...   Standard objects (<=5 GB)
    {manifest-key}-large.csv                               Large objects (>5 GB)

CSV format (per row):
    bucket,url-encoded-key                                 Without --include-versions
    bucket,url-encoded-key,version-id                      With --include-versions

Keys are percent-encoded per RFC 3986 (all characters including '/' are encoded).

Usage:
    python generate_manifest.py --bucket SOURCE --manifest-bucket MANIFEST_BUCKET [OPTIONS]

Examples:
    # Basic — list all objects and upload manifests with default key ({bucket}-manifest)
    python generate_manifest.py \\
        --bucket my-source-bucket \\
        --manifest-bucket my-manifest-bucket

    # Custom manifest key and region
    python generate_manifest.py \\
        --bucket my-source-bucket \\
        --manifest-bucket my-manifest-bucket \\
        --manifest-key manifests/prod-copy \\
        --source-region eu-west-1

    # Only objects under a prefix, with version IDs, using a named profile
    python generate_manifest.py \\
        --bucket my-source-bucket \\
        --prefix data/2024/ \\
        --manifest-bucket my-manifest-bucket \\
        --include-versions \\
        --profile prod

    # Manifest bucket in a different region than the source bucket
    python generate_manifest.py \\
        --bucket my-source-bucket \\
        --source-region us-east-1 \\
        --manifest-bucket my-manifest-bucket \\
        --manifest-region eu-central-1
"""

import argparse
import atexit
import json
import logging
import os
import shutil
import sys
import tempfile
from urllib.parse import quote

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger(__name__)

SIZE_THRESHOLD = 5368709120  # 5 GB
MAX_KEYS_PER_MANIFEST = 20000000000  # 20 billion

RETRY_CONFIG = Config(retries={"max_attempts": 10, "mode": "standard"})


def _get_session(profile):
    return boto3.Session(profile_name=profile) if profile else boto3.Session()


def get_s3_client(session, region):
    return session.client("s3", region_name=region, config=RETRY_CONFIG)


def parse_args():
    p = argparse.ArgumentParser(
        description="Generate S3 Batch Operations manifests from a source bucket."
    )
    p.add_argument("--bucket", required=True, help="Source S3 bucket name")
    p.add_argument("--prefix", default="", help="Only include objects under this prefix")
    p.add_argument("--source-region", required=True, help="Source bucket region")
    p.add_argument("--manifest-bucket", default=None, help="S3 bucket to upload manifests to (required unless --local-only)")
    p.add_argument("--manifest-key", default=None, help="Base key for manifests in S3 (default: {bucket}-manifest)")
    p.add_argument("--manifest-region", default=None, help="Manifest bucket region (default: source bucket region)")
    p.add_argument("--include-versions", action="store_true", help="Include version IDs in manifest")
    p.add_argument("--local-only", action="store_true",
                   help="Write manifests to a local directory and skip S3 upload. "
                        "Use --output-dir to control where files are written (default: ./manifests).")
    p.add_argument("--output-dir", default=None, help="Local output directory for --local-only (default: ./manifests)")
    p.add_argument("--profile", default=None, help="AWS CLI profile name")
    return p.parse_args()


def _check_bucket_accessible(s3, bucket, label):
    """Check bucket exists and is accessible, with distinct error messages."""
    try:
        s3.head_bucket(Bucket=bucket)
        return True
    except ClientError as exc:
        code = exc.response["Error"]["Code"]
        if code == "403":
            log.error("%s bucket %s exists but access is denied", label, bucket)
            sys.exit(1)
        if code == "404":
            return False
        log.error("%s bucket %s: HeadBucket failed with HTTP %s", label, bucket, code)
        sys.exit(1)


def validate_inputs(args, s3_source, s3_manifest):
    """Validate that the source bucket exists and the manifest bucket is ready.

    Checks the source bucket via HeadBucket (exits on 403 or 404). If the manifest bucket does not exist,
    it is created automatically. The us-east-1 LocationConstraint quirk is handled (no LocationConstraint
    for us-east-1, explicit LocationConstraint for all other regions).
    """
    if not _check_bucket_accessible(s3_source, args.bucket, "Source"):
        log.error("Source bucket %s does not exist", args.bucket)
        sys.exit(1)

    if not _check_bucket_accessible(s3_manifest, args.manifest_bucket, "Manifest"):
        log.info("Creating manifest bucket %s...", args.manifest_bucket)
        params = {"Bucket": args.manifest_bucket}
        if args.manifest_region != "us-east-1":
            params["CreateBucketConfiguration"] = {"LocationConstraint": args.manifest_region}
        s3_manifest.create_bucket(**params)
        s3_manifest.put_public_access_block(Bucket=args.manifest_bucket, PublicAccessBlockConfiguration={
            "BlockPublicAcls": True, "IgnorePublicAcls": True,
            "BlockPublicPolicy": True, "RestrictPublicBuckets": True,
        })
        s3_manifest.put_bucket_encryption(Bucket=args.manifest_bucket, ServerSideEncryptionConfiguration={
            "Rules": [{"ApplyServerSideEncryptionByDefault": {"SSEAlgorithm": "AES256"}, "BucketKeyEnabled": True}],
        })
        s3_manifest.put_bucket_policy(Bucket=args.manifest_bucket, Policy=json.dumps({
            "Version": "2012-10-17",
            "Statement": [{"Sid": "DenyInsecureTransport", "Effect": "Deny",
                           "Principal": "*", "Action": "s3:*", "Resource": [
                               f"arn:aws:s3:::{args.manifest_bucket}",
                               f"arn:aws:s3:::{args.manifest_bucket}/*"],
                           "Condition": {"Bool": {"aws:SecureTransport": "false"}}}],
        }))


def generate_manifests(args, s3_source, workdir):
    """List objects in the source bucket and write them to local CSV manifest files.

    Uses boto3 paginators to iterate through all objects (or object versions if --include-versions is set).
    Objects are split into two categories based on SIZE_THRESHOLD (5 GB):
        - Standard objects are written to part-NNN.csv files, rotating at MAX_KEYS_PER_MANIFEST boundaries.
        - Large objects (>5 GB) are written to large.csv for separate handling (e.g. multipart copy).

    Returns (num_parts, standard_count, large_count).
    """
    bucket = args.bucket
    standard_count = 0
    large_count = 0
    part_num = 1
    large_path = os.path.join(workdir, "large.csv")
    part_path = os.path.join(workdir, f"part-{part_num:03d}.csv")
    large_file = open(large_path, "w")
    part_file = open(part_path, "w")

    try:
        paginate_kwargs = {"Bucket": bucket}
        if args.prefix:
            paginate_kwargs["Prefix"] = args.prefix

        if args.include_versions:
            paginator = s3_source.get_paginator("list_object_versions")
            pages = paginator.paginate(**paginate_kwargs)
            # Note: list_object_versions also returns DeleteMarkers; we only
            # process Versions (actual object versions) and skip DeleteMarkers.
            objects = (
                (obj["Key"], obj["Size"], obj["VersionId"])
                for page in pages for obj in page.get("Versions", [])
            )
        else:
            paginator = s3_source.get_paginator("list_objects_v2")
            pages = paginator.paginate(**paginate_kwargs)
            objects = (
                (obj["Key"], obj["Size"], None)
                for page in pages for obj in page.get("Contents", [])
            )

        for key, size, version_id in objects:
            # Keys are percent-encoded per RFC 3986 (including '/') as required
            # by the S3BatchOperations_CSV_20180820 manifest format.
            encoded_key = quote(key, safe="")
            line = f"{bucket},{encoded_key},{version_id}" if version_id else f"{bucket},{encoded_key}"

            if size > SIZE_THRESHOLD:
                large_file.write(line + "\n")
                large_count += 1
            else:
                if standard_count > 0 and standard_count % MAX_KEYS_PER_MANIFEST == 0:
                    part_file.close()
                    part_num += 1
                    part_path = os.path.join(workdir, f"part-{part_num:03d}.csv")
                    part_file = open(part_path, "w")
                part_file.write(line + "\n")
                standard_count += 1

            total = standard_count + large_count
            if total % 100000 == 0:
                log.info("Progress: %d objects listed...", total)
    finally:
        part_file.close()
        large_file.close()

    total = standard_count + large_count
    if total > 0 and total % 100000 != 0:
        log.info("Progress: %d objects listed... done", total)

    return part_num, standard_count, large_count


def upload_manifests(s3_manifest, args, workdir, num_parts, standard_count, large_count):
    """Upload local manifest CSV files to the manifest bucket.

    Standard part files are uploaded as {manifest_key}-001.csv, {manifest_key}-002.csv, etc.
    The large objects file is uploaded as {manifest_key}-large.csv (only if large_count > 0).
    Returns the number of standard manifest parts uploaded.
    """
    uploaded = 0
    if standard_count > 0:
        for i in range(1, num_parts + 1):
            local = os.path.join(workdir, f"part-{i:03d}.csv")
            key = f"{args.manifest_key}-{i:03d}.csv"
            log.info("Uploading s3://%s/%s", args.manifest_bucket, key)
            s3_manifest.upload_file(local, args.manifest_bucket, key)
            uploaded += 1

    if large_count > 0:
        local = os.path.join(workdir, "large.csv")
        key = f"{args.manifest_key}-large.csv"
        log.info("Uploading s3://%s/%s", args.manifest_bucket, key)
        s3_manifest.upload_file(local, args.manifest_bucket, key)

    return uploaded


def main():
    args = parse_args()
    if not args.local_only and not args.manifest_bucket:
        log.error("--manifest-bucket is required unless --local-only is set")
        sys.exit(1)

    args.manifest_region = args.manifest_region or args.source_region
    args.manifest_key = args.manifest_key or f"{args.bucket}-manifest"

    session = _get_session(args.profile)
    s3_source = get_s3_client(session, args.source_region)

    if args.local_only:
        outdir = args.output_dir or os.path.join(".", "manifests")
        os.makedirs(outdir, exist_ok=True)
        workdir = outdir
    else:
        s3_manifest = get_s3_client(session, args.manifest_region)
        validate_inputs(args, s3_source, s3_manifest)
        workdir = tempfile.mkdtemp(prefix="s3manifest_")
        atexit.register(shutil.rmtree, workdir, ignore_errors=True)

    log.info("Listing objects in s3://%s/%s ...", args.bucket, args.prefix)
    num_parts, standard_count, large_count = generate_manifests(args, s3_source, workdir)

    if standard_count == 0 and large_count == 0:
        log.info("No objects found in s3://%s/%s — nothing to upload.", args.bucket, args.prefix)
        return

    if args.local_only:
        log.info("Manifests written to %s", os.path.abspath(workdir))
    else:
        upload_manifests(s3_manifest, args, workdir, num_parts, standard_count, large_count)

    log.info("--- Summary ---")
    log.info("Standard manifest parts: %d", num_parts if standard_count > 0 else 0)
    log.info("Standard objects (<=5GB): %d", standard_count)
    log.info("Large objects (>5GB):     %d", large_count)
    log.info("Total objects:            %d", standard_count + large_count)
    log.info("Manifest format:          S3BatchOperations_CSV_20180820")


if __name__ == "__main__":
    main()
