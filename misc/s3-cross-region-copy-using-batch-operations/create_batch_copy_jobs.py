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

"""Create S3 Batch Operations copy jobs using pre-generated CSV manifests.

Reads one or more CSV manifest files (produced by ``generate_manifest.py``) from an S3 bucket and creates
a separate S3 Batch Operations copy job for each manifest. Each job copies objects from the source bucket
to a destination bucket in another region using the S3PutObjectCopy operation.

The script can auto-discover manifests by listing ``{manifest-key}-*.csv`` in the manifest bucket, or accept
explicit manifest keys via ``--manifest-keys``. If neither is provided, it defaults to ``{source-bucket}-manifest``
as the base key.

Features:
    - Auto-creates the destination bucket (with public access blocked, AES256 encryption, and versioning mirrored
      from the source bucket) if it does not exist.
    - Auto-creates a report bucket (``{source-bucket}-{dest-region}-report``) for job completion reports.
    - Auto-creates a least-privilege IAM role for the batch job if ``--role-arn`` is not provided. The role is
      scoped to the caller's account via ``s3:ResourceAccount`` condition. A 60-second wait is applied after
      role creation to allow IAM propagation.
    - Jobs are created in Suspended state by default. Pass ``--start`` to run immediately.

Usage:
    python create_batch_copy_jobs.py --source-bucket SOURCE --destination-region REGION \\
        --manifest-bucket MANIFEST_BUCKET [OPTIONS]

Examples:
    # Auto-discover manifests using default base key ({source-bucket}-manifest)
    python create_batch_copy_jobs.py \\
        --source-bucket my-source-bucket \\
        --destination-region eu-west-1 \\
        --manifest-bucket my-manifest-bucket

    # Auto-discover manifests using a custom base key
    python create_batch_copy_jobs.py \\
        --source-bucket my-source-bucket \\
        --destination-region eu-west-1 \\
        --manifest-bucket my-manifest-bucket \\
        --manifest-key manifests/prod-copy

    # Explicit manifest keys (no auto-discovery)
    python create_batch_copy_jobs.py \\
        --source-bucket my-source-bucket \\
        --destination-region eu-west-1 \\
        --manifest-bucket my-manifest-bucket \\
        --manifest-keys manifests/prod-copy-001.csv manifests/prod-copy-large.csv

    # Versioned bucket, custom destination, named profile, start immediately
    python create_batch_copy_jobs.py \\
        --source-bucket my-source-bucket \\
        --source-region us-east-1 \\
        --dest-bucket my-dest-bucket-eu \\
        --destination-region eu-central-1 \\
        --manifest-bucket my-manifest-bucket \\
        --manifest-key manifests/prod-copy \\
        --include-versions \\
        --storage-class STANDARD_IA \\
        --start \\
        --profile prod

    # Bring your own IAM role
    python create_batch_copy_jobs.py \\
        --source-bucket my-source-bucket \\
        --destination-region eu-west-1 \\
        --manifest-bucket my-manifest-bucket \\
        --role-arn arn:aws:iam::123456789012:role/MyBatchCopyRole
"""

import argparse
import json
import logging
import sys
import time
import uuid

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger(__name__)

RETRY_CONFIG = Config(retries={"max_attempts": 10, "mode": "standard"})
_S3_BUCKET_NAME_MAX_LEN = 63

TRUST_POLICY = json.dumps({
    "Version": "2012-10-17",
    "Statement": [{
        "Effect": "Allow",
        "Principal": {"Service": "batchoperations.s3.amazonaws.com"},
        "Action": "sts:AssumeRole",
    }],
})


def _get_session(profile):
    return boto3.Session(profile_name=profile) if profile else boto3.Session()


def parse_args():
    p = argparse.ArgumentParser(
        description="Create S3 Batch Operations copy jobs from pre-generated manifests."
    )
    p.add_argument("--source-bucket", required=True, help="Source S3 bucket name")
    p.add_argument("--source-region", required=True, help="Source bucket region")
    p.add_argument("--dest-bucket", default=None, help="Destination bucket (default: {source}-{region})")
    p.add_argument("--destination-region", required=True, dest="region", help="Destination region")
    p.add_argument("--manifest-bucket", required=True, help="Bucket where manifest CSVs are stored")
    p.add_argument("--manifest-key", default=None, help="Base manifest key (auto-discovers {key}-001.csv, etc.)")
    p.add_argument("--manifest-keys", default=None, nargs="+", help="Explicit S3 keys for manifest CSV files (overrides --manifest-key)")
    p.add_argument("--manifest-region", default=None, help="Region of manifest bucket (default: destination region)")
    p.add_argument("--role-arn", default=None, help="IAM role ARN (auto-created if omitted)")
    p.add_argument("--account-id", default=None, help="AWS account ID (auto-detected if omitted)")
    p.add_argument("--report-prefix", default="batch-copy-reports", help="Report prefix")
    p.add_argument("--storage-class", default="STANDARD", help="Storage class (default: STANDARD)")
    p.add_argument("--description", default=None, help="Job description")
    p.add_argument("--priority", type=int, default=10, help="Job priority (default: 10)")
    p.add_argument("--confirm", action="store_true", help="(Deprecated, ignored) Jobs now default to Suspended. Use --start to run immediately.")
    p.add_argument("--start", action="store_true", help="Start jobs immediately (default: jobs are created in Suspended state)")
    p.add_argument("--include-versions", action="store_true", help="Manifest contains VersionId column")
    p.add_argument("--profile", default=None, help="AWS CLI profile name")
    return p.parse_args()


def discover_manifest_keys(s3, bucket, base_key):
    """List all manifest CSVs matching {base_key}-*.csv in the bucket."""
    prefix = f"{base_key}-"
    paginator = s3.get_paginator("list_objects_v2")
    keys = []
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for obj in page.get("Contents", []):
            if obj["Key"].endswith(".csv"):
                keys.append(obj["Key"])
    if not keys:
        log.error("No manifests found matching s3://%s/%s*.csv", bucket, prefix)
        sys.exit(1)
    keys.sort()
    log.info("Discovered %d manifest(s): %s", len(keys), ", ".join(keys))
    return keys


def get_account_id(session, account_id):
    if account_id:
        return account_id
    return session.client("sts", config=RETRY_CONFIG).get_caller_identity()["Account"]


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
        return False


def ensure_bucket(s3, bucket, region, label=""):
    """Ensure an S3 bucket exists, creating it if necessary.

    If the bucket does not exist, it is created with public access blocked and AES256 server-side encryption
    with BucketKey enabled. Distinguishes between 403 (access denied — exits immediately) and 404 (not found
    — proceeds to create). Handles the us-east-1 LocationConstraint quirk.
    """
    if _check_bucket_accessible(s3, bucket, label):
        return
    params = {"Bucket": bucket}
    if region != "us-east-1":
        params["CreateBucketConfiguration"] = {"LocationConstraint": region}
    s3.create_bucket(**params)
    log.info("Created bucket %s", bucket)
    s3.put_public_access_block(Bucket=bucket, PublicAccessBlockConfiguration={
        "BlockPublicAcls": True, "IgnorePublicAcls": True,
        "BlockPublicPolicy": True, "RestrictPublicBuckets": True,
    })
    s3.put_bucket_encryption(Bucket=bucket, ServerSideEncryptionConfiguration={
        "Rules": [{"ApplyServerSideEncryptionByDefault": {"SSEAlgorithm": "AES256"}, "BucketKeyEnabled": True}],
    })
    s3.put_bucket_policy(Bucket=bucket, Policy=json.dumps({
        "Version": "2012-10-17",
        "Statement": [{"Sid": "DenyInsecureTransport", "Effect": "Deny",
                       "Principal": "*", "Action": "s3:*", "Resource": [
                           f"arn:aws:s3:::{bucket}",
                           f"arn:aws:s3:::{bucket}/*"],
                       "Condition": {"Bool": {"aws:SecureTransport": "false"}}}],
    }))


def copy_versioning(s3_source, s3_dest, source_bucket, dest_bucket):
    """Mirror the versioning configuration from the source bucket to the destination bucket.

    Reads the versioning status from the source bucket and applies it to the destination. Silently skips
    if the source bucket versioning cannot be read (e.g. cross-account access).
    """
    try:
        resp = s3_source.get_bucket_versioning(Bucket=source_bucket)
        status = resp.get("Status")
        if status:
            s3_dest.put_bucket_versioning(Bucket=dest_bucket, VersioningConfiguration={"Status": status})
            log.info("Set versioning on %s to %s", dest_bucket, status)
    except ClientError:
        pass


def _validate_bucket_name_length(name, label):
    if len(name) > _S3_BUCKET_NAME_MAX_LEN:
        log.error("Auto-generated %s bucket name '%s' is %d chars (max %d). Provide it explicitly.",
                  label, name, len(name), _S3_BUCKET_NAME_MAX_LEN)
        sys.exit(1)


def create_role(iam, account_id, source_bucket, dest_bucket, report_bucket, manifest_bucket, manifest_keys):
    """Create a least-privilege IAM role for S3 Batch Operations.

    The role trusts the batchoperations.s3.amazonaws.com service principal and grants:
        - s3:GetObject, s3:GetObjectVersion, s3:GetObjectTagging, s3:GetObjectVersionTagging, s3:ListBucket
          on the source bucket (for reading objects to copy).
        - s3:PutObject, s3:PutObjectTagging on the destination bucket (for writing copied objects).
        - s3:PutObject on the report bucket (for writing job completion reports).
        - s3:GetObject on the specific manifest keys in the manifest bucket.
    All statements are scoped to the caller's account via the s3:ResourceAccount condition key.

    Waits 60 seconds after creation for IAM propagation before returning.
    Returns (role_arn, role_name).
    """
    manifest_arns = [f"arn:aws:s3:::{manifest_bucket}/{k}" for k in manifest_keys]
    role_name = f"S3BatchCopy-{source_bucket[:20]}-{int(time.time())}"
    policy = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Action": ["s3:GetObject", "s3:GetObjectVersion", "s3:GetObjectTagging",
                           "s3:GetObjectVersionTagging", "s3:ListBucket"],
                "Resource": [f"arn:aws:s3:::{source_bucket}", f"arn:aws:s3:::{source_bucket}/*"],
                "Condition": {"StringEquals": {"s3:ResourceAccount": account_id}},
            },
            {
                "Effect": "Allow",
                "Action": ["s3:PutObject", "s3:PutObjectTagging"],
                "Resource": f"arn:aws:s3:::{dest_bucket}/*",
                "Condition": {"StringEquals": {"s3:ResourceAccount": account_id}},
            },
            {
                "Effect": "Allow",
                "Action": "s3:PutObject",
                "Resource": f"arn:aws:s3:::{report_bucket}/*",
                "Condition": {"StringEquals": {"s3:ResourceAccount": account_id}},
            },
            {
                "Effect": "Allow",
                "Action": "s3:GetObject",
                "Resource": manifest_arns,
                "Condition": {"StringEquals": {"s3:ResourceAccount": account_id}},
            },
        ],
    }
    role = iam.create_role(RoleName=role_name, AssumeRolePolicyDocument=TRUST_POLICY,
                           Description="Auto-created for S3 Batch Copy")
    role_arn = role["Role"]["Arn"]
    policy_name = f"{role_name}-policy"
    iam.put_role_policy(RoleName=role_name, PolicyName=policy_name, PolicyDocument=json.dumps(policy))
    log.info("Created IAM role %s, waiting 60s for propagation...", role_name)
    time.sleep(60)
    return role_arn, role_name


def create_job(s3control, s3_manifest, account_id, args, dest_bucket, report_bucket, role_arn, manifest_key):
    """Create a single S3 Batch Operations copy job for one manifest file.

    Fetches the ETag of the manifest object via HeadObject (required by the Manifest Location API), then
    calls s3control.create_job with:
        - Operation: S3PutObjectCopy to the destination bucket with the specified storage class.
        - Manifest: S3BatchOperations_CSV_20180820 format, fields [Bucket, Key] or [Bucket, Key, VersionId].
        - Report: enabled for all tasks, written to the report bucket under the configured prefix.
        - ConfirmationRequired: based on --start flag (default: True, jobs created in Suspended state).

    Returns the job ID.
    """
    head = s3_manifest.head_object(Bucket=args.manifest_bucket, Key=manifest_key)
    etag = head["ETag"]

    fields = ["Bucket", "Key", "VersionId"] if args.include_versions else ["Bucket", "Key"]

    params = {
        "AccountId": account_id,
        "ConfirmationRequired": not args.start,
        "Operation": {
            "S3PutObjectCopy": {
                "TargetResource": f"arn:aws:s3:::{dest_bucket}",
                "StorageClass": args.storage_class,
            },
        },
        "Manifest": {
            "Spec": {"Format": "S3BatchOperations_CSV_20180820", "Fields": fields},
            "Location": {
                "ObjectArn": f"arn:aws:s3:::{args.manifest_bucket}/{manifest_key}",
                "ETag": etag,
            },
        },
        "Report": {
            "Bucket": f"arn:aws:s3:::{report_bucket}",
            "Prefix": args.report_prefix,
            "Format": "Report_CSV_20180820",
            "Enabled": True,
            "ReportScope": "AllTasks",
        },
        "Priority": args.priority,
        "RoleArn": role_arn,
        "ClientRequestToken": str(uuid.uuid4()),
    }
    if args.description:
        params["Description"] = args.description

    resp = s3control.create_job(**params)
    return resp["JobId"]


def main():
    args = parse_args()
    args.manifest_region = args.manifest_region or args.region

    session = _get_session(args.profile)
    account_id = get_account_id(session, args.account_id)

    dest_bucket = args.dest_bucket or f"{args.source_bucket}-{args.region}"
    _validate_bucket_name_length(dest_bucket, "destination")

    report_bucket = f"{args.source_bucket}-{args.region}-report"
    _validate_bucket_name_length(report_bucket, "report")

    s3_source = session.client("s3", region_name=args.source_region, config=RETRY_CONFIG)
    s3_dest = session.client("s3", region_name=args.region, config=RETRY_CONFIG)
    s3_manifest = session.client("s3", region_name=args.manifest_region, config=RETRY_CONFIG)
    s3control = session.client("s3control", region_name=args.region, config=RETRY_CONFIG)

    # Resolve manifest keys
    if args.manifest_keys:
        manifest_keys = args.manifest_keys
    elif args.manifest_key:
        manifest_keys = discover_manifest_keys(s3_manifest, args.manifest_bucket, args.manifest_key)
    else:
        base = f"{args.source_bucket}-manifest"
        log.info("No --manifest-key or --manifest-keys provided, using default base: %s", base)
        manifest_keys = discover_manifest_keys(s3_manifest, args.manifest_bucket, base)

    ensure_bucket(s3_dest, dest_bucket, args.region, "Destination")
    copy_versioning(s3_source, s3_dest, args.source_bucket, dest_bucket)
    ensure_bucket(s3_dest, report_bucket, args.region, "Report")

    role_name = None
    role_arn = args.role_arn
    if not role_arn:
        iam = session.client("iam", config=RETRY_CONFIG)
        role_arn, role_name = create_role(iam, account_id, args.source_bucket, dest_bucket,
                                          report_bucket, args.manifest_bucket, manifest_keys)

    log.info("--- Creating batch copy jobs ---")
    job_ids = []
    for key in manifest_keys:
        job_id = create_job(s3control, s3_manifest, account_id, args, dest_bucket, report_bucket, role_arn, key)
        job_ids.append((job_id, key))
        log.info("Job %s created for manifest: %s", job_id, key)
        log.info("  Destination: s3://%s", dest_bucket)
        log.info("  Reports:     s3://%s/%s", report_bucket, args.report_prefix)
        log.info("  Describe:    aws s3control describe-job --account-id %s --job-id %s --region %s",
                 account_id, job_id, args.region)

    log.info("--- Summary: %d job(s) created ---", len(job_ids))
    if role_name:
        log.info("Cleanup auto-created role:")
        log.info("  aws iam delete-role-policy --role-name %s --policy-name %s-policy", role_name, role_name)
        log.info("  aws iam delete-role --role-name %s", role_name)


if __name__ == "__main__":
    main()
