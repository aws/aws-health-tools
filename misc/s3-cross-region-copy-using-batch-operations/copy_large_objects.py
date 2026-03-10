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

"""Copy large S3 objects across regions preserving original multipart part structure.

Uses the low-level S3 multipart copy API (create_multipart_upload / upload_part_copy /
complete_multipart_upload) to reproduce the exact same part boundaries as the source object,
so the resulting ETag matches the original.

Reads a CSV manifest file produced by ``generate_manifest.py`` (the ``large.csv`` output) and copies each
object to a destination bucket. Objects are copied in parallel using a thread pool.

The source bucket region is auto-detected via get_bucket_location.

The manifest follows the S3BatchOperations_CSV_20180820 format (no header):
    bucket,url-encoded-key
    bucket,url-encoded-key,version-id

Usage:
    python copy_large_objects.py --manifest large.csv --dest-bucket DEST \\
        --dest-region REGION [OPTIONS]

The --manifest argument accepts either a local file path or an S3 URI (s3://bucket/key).

Examples:
    # From local manifest
    python copy_large_objects.py \\
        --manifest manifests/large.csv \\
        --dest-bucket my-dest-bucket \\
        --dest-region eu-west-1

    # From S3 manifest (as uploaded by generate_manifest.py)
    python copy_large_objects.py \\
        --manifest s3://my-manifest-bucket/my-source-bucket-manifest-large.csv \\
        --dest-bucket my-dest-bucket \\
        --dest-region eu-west-1

    # With optional prefix, profile, and higher concurrency
    python copy_large_objects.py \\
        --manifest s3://my-manifest-bucket/my-source-bucket-manifest-large.csv \\
        --dest-bucket my-dest-bucket \\
        --dest-region eu-west-1 \\
        --dest-prefix backup/2024/ \\
        --profile prod \\
        --concurrency 20

Required IAM permissions:

    Source bucket:
        s3:GetBucketLocation
        s3:GetObject
        s3:GetObjectTagging
        s3:GetObjectVersion          (if copying versioned objects)
        s3:GetObjectVersionTagging   (if copying versioned objects)

    Manifest bucket (if --manifest is an S3 URI):
        s3:GetBucketLocation
        s3:GetObject

    Destination bucket:
        s3:PutObject
        s3:AbortMultipartUpload

Limitations:
    ETag preservation only works for unencrypted or SSE-S3 encrypted objects.
    SSE-KMS encrypted objects produce different ETags after copy because the
    destination uses a different encryption context.
"""

import argparse
import csv
import logging
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import quote, unquote

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger(__name__)

RETRY_CONFIG = Config(retries={"max_attempts": 10, "mode": "standard"})


def _get_session(profile):
    """Return a boto3 Session, optionally using a named profile."""
    return boto3.Session(profile_name=profile) if profile else boto3.Session()


def parse_args():
    """Parse command-line arguments."""
    p = argparse.ArgumentParser(
        description="Copy large S3 objects across regions preserving original part structure and ETags."
    )
    p.add_argument("--manifest", required=True,
                   help="Path to CSV manifest file — local path or S3 URI (s3://bucket/key)")
    p.add_argument("--dest-bucket", required=True, help="Destination S3 bucket name")
    p.add_argument("--dest-region", required=True, help="Destination bucket region")
    p.add_argument("--dest-prefix", default="", help="Prefix to prepend to destination keys")
    p.add_argument("--profile", default=None, help="AWS CLI profile name")
    p.add_argument("--concurrency", type=int, default=10, help="Number of parallel copy threads (default: 10)")
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
            log.error("%s bucket %s does not exist", label, bucket)
            sys.exit(1)
        log.error("%s bucket %s: HeadBucket failed with HTTP %s", label, bucket, code)
        sys.exit(1)


def _parse_manifest_rows(lines):
    """Yield (bucket, key, version_id) tuples from CSV lines.

    Keys are URL-decoded from the manifest's percent-encoded format.
    version_id is None when the manifest row has only two columns.
    """
    for row in csv.reader(lines):
        if not row:
            continue
        bucket = row[0]
        key = unquote(row[1])
        version_id = row[2] if len(row) > 2 else None
        yield bucket, key, version_id


def _read_manifest(path, session):
    """Read a CSV manifest from a local file or S3 URI (s3://bucket/key)."""
    if path.startswith("s3://"):
        parts = path[5:].split("/", 1)
        if len(parts) < 2 or not parts[0] or not parts[1]:
            log.error("Invalid S3 URI: %s (expected s3://bucket/key)", path)
            sys.exit(1)
        bucket, key = parts[0], parts[1]
        region = _get_bucket_region(session, bucket)
        s3 = session.client("s3", region_name=region, config=RETRY_CONFIG)
        resp = s3.get_object(Bucket=bucket, Key=key)
        lines = resp["Body"].iter_lines()
        return list(_parse_manifest_rows(line.decode("utf-8") for line in lines))
    else:
        with open(path) as f:
            return list(_parse_manifest_rows(f))


def _get_bucket_region(session, bucket):
    """Return the region of a bucket. Returns 'us-east-1' when location is None."""
    s3 = session.client("s3", config=RETRY_CONFIG)
    resp = s3.get_bucket_location(Bucket=bucket)
    return resp["LocationConstraint"] or "us-east-1"


def _get_part_sizes(s3, bucket, key, version_id, part_count):
    """Return a list of part sizes by calling head_object with PartNumber for each part."""
    sizes = []
    for n in range(1, part_count + 1):
        kwargs = {"Bucket": bucket, "Key": key, "PartNumber": n}
        if version_id:
            kwargs["VersionId"] = version_id
        resp = s3.head_object(**kwargs)
        sizes.append(resp["ContentLength"])
    return sizes


def _build_tagging_string(tag_set):
    """Convert a TagSet list to URL-encoded key=value&key=value string."""
    return "&".join(
        f"{quote(t['Key'], safe='')}={quote(t['Value'], safe='')}"
        for t in tag_set
    )


def _copy_object(s3_source, s3_dest, source_bucket, key, version_id, dest_bucket, dest_prefix):
    """Copy a single object preserving original part structure so ETags match.

    For multipart objects, uses create_multipart_upload / upload_part_copy /
    complete_multipart_upload with byte ranges matching the original parts.
    For non-multipart objects, uses copy_object directly.

    Returns (key, True, None) on success or (key, False, error_message) on failure.
    """
    dest_key = f"{dest_prefix}{key}" if dest_prefix else key
    try:
        # HEAD source object
        head_kwargs = {"Bucket": source_bucket, "Key": key}
        if version_id:
            head_kwargs["VersionId"] = version_id
        head = s3_source.head_object(**head_kwargs)

        etag = head["ETag"].strip('"')
        content_length = head["ContentLength"]
        content_type = head.get("ContentType", "application/octet-stream")
        metadata = head.get("Metadata", {})

        # Collect object properties to preserve on multipart path
        obj_props = {"ContentType": content_type, "Metadata": metadata}
        for prop in ("CacheControl", "ContentDisposition", "ContentEncoding",
                     "ContentLanguage", "Expires", "StorageClass"):
            if prop in head:
                obj_props[prop] = head[prop]

        # Get tags
        tag_kwargs = {"Bucket": source_bucket, "Key": key}
        if version_id:
            tag_kwargs["VersionId"] = version_id
        tag_resp = s3_source.get_object_tagging(**tag_kwargs)
        tag_set = tag_resp.get("TagSet", [])

        copy_source = {"Bucket": source_bucket, "Key": key}
        if version_id:
            copy_source["VersionId"] = version_id

        # Non-multipart: simple copy
        if "-" not in etag:
            s3_dest.copy_object(CopySource=copy_source, Bucket=dest_bucket, Key=dest_key)
            return key, True, None

        # Multipart: preserve original part structure
        part_count = int(etag.split("-")[1])
        part_sizes = _get_part_sizes(s3_source, source_bucket, key, version_id, part_count)

        # Initiate multipart upload
        create_kwargs = {
            "Bucket": dest_bucket,
            "Key": dest_key,
            **obj_props,
        }
        if tag_set:
            create_kwargs["Tagging"] = _build_tagging_string(tag_set)
        mpu = s3_dest.create_multipart_upload(**create_kwargs)
        upload_id = mpu["UploadId"]

        try:
            parts = []
            offset = 0
            for part_num, size in enumerate(part_sizes, 1):
                range_str = f"bytes={offset}-{offset + size - 1}"
                resp = s3_dest.upload_part_copy(
                    Bucket=dest_bucket,
                    Key=dest_key,
                    CopySource=copy_source,
                    CopySourceRange=range_str,
                    CopySourceIfMatch=head["ETag"],
                    PartNumber=part_num,
                    UploadId=upload_id,
                )
                parts.append({
                    "ETag": resp["CopyPartResult"]["ETag"],
                    "PartNumber": part_num,
                })
                offset += size

            s3_dest.complete_multipart_upload(
                Bucket=dest_bucket,
                Key=dest_key,
                UploadId=upload_id,
                MultipartUpload={"Parts": parts},
            )
        except Exception:
            try:
                s3_dest.abort_multipart_upload(
                    Bucket=dest_bucket, Key=dest_key, UploadId=upload_id
                )
            except Exception:
                log.warning("Failed to abort multipart upload %s for %s", upload_id, dest_key)
            raise

        return key, True, None
    except Exception as exc:
        return key, False, str(exc)


def main():
    args = parse_args()

    session = _get_session(args.profile)

    entries = _read_manifest(args.manifest, session)
    if not entries:
        log.info("Manifest %s is empty — nothing to copy.", args.manifest)
        return

    # Auto-detect source region from first entry's bucket
    source_region = _get_bucket_region(session, entries[0][0])
    log.info("Detected source bucket region: %s", source_region)

    s3_source = session.client("s3", region_name=source_region, config=RETRY_CONFIG)
    s3_dest = session.client("s3", region_name=args.dest_region, config=RETRY_CONFIG)

    _check_bucket_accessible(s3_dest, args.dest_bucket, "Destination")

    log.info("Copying %d object(s) to s3://%s/%s ...", len(entries), args.dest_bucket, args.dest_prefix)

    copied = 0
    failed = 0
    with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        futures = {
            pool.submit(_copy_object, s3_source, s3_dest, bucket, key, vid,
                        args.dest_bucket, args.dest_prefix): key
            for bucket, key, vid in entries
        }
        for future in as_completed(futures):
            key, ok, err = future.result()
            if ok:
                copied += 1
                log.info("Copied: %s (%d/%d)", key, copied + failed, len(entries))
            else:
                failed += 1
                log.error("FAILED: %s — %s", key, err)

    log.info("--- Summary ---")
    log.info("Total:   %d", len(entries))
    log.info("Copied:  %d", copied)
    log.info("Failed:  %d", failed)
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
