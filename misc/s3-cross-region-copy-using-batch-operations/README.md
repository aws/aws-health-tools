# S3 Cross-Region Copy Using Batch Operations

Use these scripts to copy S3 objects across regions using S3 Batch Operations. The scripts will generate CSV manifests from the source bucket, auto-create the destination and report buckets (with public access blocked, encryption, and versioning mirrored from the source), create a least-privilege IAM role for the batch job, and submit one S3 Batch Operations job per manifest. Objects larger than 5 GB are written to a separate manifest (`{manifest-key}-large.csv`) for handling with multipart copy or other tooling.

## Overview

This tool provides three scripts that work together:

1. **`generate_manifest.py`** — Lists objects in a source bucket and produces CSV manifest files compatible with S3 Batch Operations.
2. **`create_batch_copy_jobs.py`** — Creates S3 Batch Operations copy jobs using the manifests generated in the previous step.
3. **`copy_large_objects.py`** — Copies objects larger than 5 GB across regions using the multipart copy API, preserving original part structure and ETags.

Objects are split into two categories:
- **Standard** (≤ 5 GB) — copied via S3 Batch Operations `S3PutObjectCopy`
- **Large** (> 5 GB) — written to a separate manifest for handling with multipart copy or other tooling

## Prerequisites

- Python 3.8+
- `pip install -r requirements.txt`
- AWS credentials configured (`aws configure`, environment variables, or IAM role)
- Permissions to list the source bucket, create/write to the manifest and destination buckets, and create IAM roles (if using auto-role creation)

## Usage

### Step 1 — Generate Manifests

```bash
python generate_manifest.py \
  --bucket my-source-bucket \
  --source-region me-central-1 \
  --manifest-bucket my-manifest-bucket \
  --manifest-region eu-west-1
```

This lists every object in `my-source-bucket` and uploads CSV manifests to `s3://my-manifest-bucket/manifests/my-job-001.csv`, `my-job-002.csv`, etc. Objects larger than 5 GB go to `my-job-large.csv`.

#### Options

| Flag | Required | Default | Description |
|------|----------|---------|-------------|
| `--bucket` | Yes | — | Source S3 bucket |
| `--prefix` | No | (none) | Only include objects under this prefix |
| `--source-region` | Yes | — | Source bucket region |
| `--manifest-bucket` | Yes | — | Bucket to upload manifests to |
| `--manifest-key` | No | `{bucket}-manifest` | Base key prefix for manifests |
| `--manifest-region` | No | source region | Manifest bucket region |
| `--include-versions` | No | off | Include `VersionId` in manifest (for versioned buckets) |
| `--profile` | No | default | AWS CLI profile name |

#### Checking for Objects Larger Than 5 GB

Before creating batch copy jobs, you can check whether your bucket contains objects larger than 5 GB by running `generate_manifest.py` with `--local-only`:

```bash
python generate_manifest.py \
  --bucket my-source-bucket \
  --source-region me-central-1 \
  --local-only
```

The summary output will show the breakdown:

```
Standard objects (<=5GB): 999850
Large objects (>5GB):     150
Total objects:            1000000
```

If `Large objects` is 0, all objects can be copied with S3 Batch Operations. If there are large objects, they are written to a separate `large.csv` manifest in the output directory and need to be handled with `copy_large_objects.py` (Step 3) or another tool such as [DataSync](../s3-cross-region-copy-using-aws-datasync/).

### Step 2 — Create Batch Copy Jobs

```bash
python create_batch_copy_jobs.py \
  --source-bucket my-source-bucket \
  --source-region me-central-1 \
  --destination-region eu-west-1 \
  --manifest-bucket my-manifest-bucket \
  --manifest-region eu-west-1
```

This auto-discovers all `manifests/my-job-*.csv` files and creates one S3 Batch Operations job per manifest. You can also pass explicit keys with `--manifest-keys`.

#### Options

| Flag | Required | Default | Description |
|------|----------|---------|-------------|
| `--source-bucket` | Yes | — | Source S3 bucket |
| `--source-region` | Yes | — | Source bucket region |
| `--dest-bucket` | No | `{source}-{region}` | Destination bucket name |
| `--destination-region` | Yes | — | Destination region (job runs here) |
| `--manifest-bucket` | Yes | — | Bucket containing manifest CSVs |
| `--manifest-key` | No | `{source-bucket}-manifest` | Base manifest key (auto-discovers `{key}-001.csv`, etc.) |
| `--manifest-keys` | No | auto-discovered | Explicit manifest CSV keys (overrides `--manifest-key`) |
| `--manifest-region` | No | destination region | Manifest bucket region |
| `--role-arn` | No | auto-created | IAM role ARN for batch operations |
| `--account-id` | No | auto-detected | AWS account ID |
| `--report-prefix` | No | `batch-copy-reports` | S3 prefix for job reports |
| `--storage-class` | No | `STANDARD` | Storage class for copied objects |
| `--description` | No | auto-generated | Job description |
| `--priority` | No | `10` | Job priority |
| `--confirm` | No | off | (Deprecated) Ignored — jobs now default to Suspended |
| `--start` | No | off | Start jobs immediately (default: jobs are created in Suspended state) |
| `--include-versions` | No | off | Manifest includes VersionId column |
| `--profile` | No | default | AWS CLI profile name |

### Step 3 — Copy Large Objects

Objects larger than 5 GB cannot be copied by S3 Batch Operations. Use `copy_large_objects.py` to copy them using the multipart copy API while preserving the original part structure so ETags match.

**The script runs in dry-run mode by default** — it validates source objects and logs what would be copied without writing anything. Pass `--no-dry-run` to perform the actual copy.

```bash
# Dry-run (default) — see what would be copied
python copy_large_objects.py \
  --manifest s3://my-manifest-bucket/my-source-bucket-manifest-large.csv \
  --dest-bucket my-dest-bucket \
  --dest-region eu-west-1

# Actual copy
python copy_large_objects.py \
  --manifest s3://my-manifest-bucket/my-source-bucket-manifest-large.csv \
  --dest-bucket my-dest-bucket \
  --dest-region eu-west-1 \
  --no-dry-run
```

#### Options

| Flag | Required | Default | Description |
|------|----------|---------|-------------|
| `--manifest` | Yes | — | Path to CSV manifest file — local path or S3 URI (`s3://bucket/key`) |
| `--dest-bucket` | Yes | — | Destination S3 bucket name |
| `--dest-region` | Yes | — | Destination bucket region |
| `--dest-prefix` | No | (none) | Prefix to prepend to destination keys |
| `--profile` | No | default | AWS CLI profile name |
| `--concurrency` | No | `10` | Number of parallel copy threads (max: 32) |
| `--dry-run` | No | on | Show what would be copied without actually copying (default) |
| `--no-dry-run` | No | off | Perform the actual copy |

## End-to-End Example

```bash
# 1. Generate manifests from a versioned bucket
python generate_manifest.py \
  --bucket prod-data-me-central-1 \
  --manifest-bucket batch-manifests \
  --manifest-region eu-west-1 \
  --source-region me-central-1 \
  --include-versions \
  --profile prod

# 2. Create batch copy jobs to eu-west-1
python create_batch_copy_jobs.py \
  --source-bucket prod-data-me-central-1 \
  --source-region me-central-1 \
  --destination-region eu-west-1 \
  --manifest-bucket batch-manifests \
  --manifest-region eu-west-1 \
  --include-versions \
  --profile prod

# 3. Copy large objects (dry-run first, then actual copy)
python copy_large_objects.py \
  --manifest s3://batch-manifests/prod-data-me-central-1-manifest-large.csv \
  --dest-bucket prod-data-me-central-1-eu-west-1 \
  --dest-region eu-west-1 \
  --profile prod

# Review dry-run output, then run for real:
python copy_large_objects.py \
  --manifest s3://batch-manifests/prod-data-me-central-1-manifest-large.csv \
  --dest-bucket prod-data-me-central-1-eu-west-1 \
  --dest-region eu-west-1 \
  --profile prod \
  --no-dry-run
```

## Manifest Format

The generated CSV follows the `S3BatchOperations_CSV_20180820` format:

```
bucket,url-encoded-key
bucket,url-encoded-key,version-id   # with --include-versions
```

Keys are percent-encoded per RFC 3986 (including forward slashes).

## IAM Role

If `--role-arn` is not provided, `create_batch_copy_jobs.py` auto-creates a least-privilege IAM role with:
- `s3:GetObject`, `s3:GetObjectVersion`, `s3:GetObjectTagging`, `s3:GetObjectVersionTagging`, `s3:ListBucket` on the source bucket
- `s3:PutObject`, `s3:PutObjectTagging` on the destination bucket
- `s3:GetObject` on the manifest bucket
- `s3:PutObject` on the report bucket
- All scoped to the caller's account via `s3:ResourceAccount` condition

The role name and cleanup commands are printed after job creation.

## Retries

S3 Batch Operations has built-in extended retry with backoff to handle service outage scenarios. No customer action is needed — failed operations within a job are automatically retried.

## Limitations

- KMS-encrypted objects are not supported. Objects encrypted with AWS KMS (SSE-KMS) will fail during the batch copy operation because the auto-created IAM role does not include KMS permissions. If your bucket uses SSE-KMS, consider using [DataSync](../s3-cross-region-copy-using-aws-datasync/) instead.

## License

This project is licensed under the Apache License 2.0. See [LICENSE](../../LICENSE).
