# s3-inventory-to-batch-job

Splits an S3 Inventory CSV manifest across multiple concurrent S3 Batch Replication jobs.

S3 Batch Replication has a 20 billion object limit per job. For buckets exceeding this, the inventory
data files are distributed across N jobs -- each created in suspended state for review before activation.

## Requirements

- Source and destination buckets must have versioning enabled -- this is a hard requirement for
  S3 replication. See [Requirements for replication](https://docs.aws.amazon.com/AmazonS3/latest/userguide/replication-requirements.html).
  `setup-replication-rules` automatically enables versioning on the source bucket if not already
  enabled. For the destination bucket, versioning must be enabled manually before running this
  tool -- enabling versioning on an existing bucket has storage and cost implications (existing
  objects become versioned, delete operations create delete markers) that the bucket owner should
  review before proceeding.
- Source bucket must have a replication rule configured before running batch replication
- **KMS limitation:** This tool supports a single KMS key per bucket (the bucket's default
  encryption key). Objects encrypted with a different KMS key than the bucket default will fail
  to replicate silently. Ensure all objects in the source bucket use the same KMS key before
  running replication. This tool does not support buckets with mixed KMS keys.
- Inventory must be in CSV format (ORC/Parquet are not supported by S3 Batch Replication)
- Inventory must be configured with `IncludedObjectVersions: All` -- this adds `VersionId` to the
  schema, which S3 Batch Replication requires. Using `Current` will cause jobs to fail at creation.
  Note: `All` includes non-current versions in the inventory; these will also be replicated.
- Glacier Flexible Retrieval and Deep Archive objects will not replicate

## Installation

**From source:**

```
git clone <repository-url>
cd s3-inventory-to-batch-job
uv build
uv tool install dist/s3_batch_replication_from_inventory-*.whl
```

**From a wheel file (no source required):**

```
pip install s3_batch_replication_from_inventory-*.whl
# or
uv tool install s3_batch_replication_from_inventory-*.whl
```

**With pip (using pinned requirements):**

```
pip install -r requirements.txt
pip install s3_batch_replication_from_inventory-*.whl
```

To regenerate `requirements.txt` after updating dependencies: `uv export --frozen --all-extras -o requirements.txt`

## Shell Completion

**zsh** — add to `~/.zshrc`:
```zsh
eval "$(_S3_BATCH_REPLICATION_COMPLETE=zsh_source s3-batch-replication)"
```

**bash** — add to `~/.bashrc`:
```bash
eval "$(_S3_BATCH_REPLICATION_COMPLETE=bash_source s3-batch-replication)"
```

Note: completion for chained commands (options after the first subcommand) may be limited.

## Commands

All commands accept the following global options:

| Option | Description |
|--------|-------------|
| `--region` | AWS region (or set `AWS_DEFAULT_REGION`). For cross-region replication, use the source bucket's region. |
| `-v` | INFO — progress milestones |
| `-vv` | DEBUG — internals (ETags, file counts, rule IDs, etc.) |
| `-vvv` | DEBUG + boto3/botocore wire logging (HTTP requests, retries, credential resolution) |

### `setup-iam-role`

Creates an IAM role with the trust policy and permissions required for S3 Batch Replication.

```
s3-batch-replication setup-iam-role \
  --source-bucket my-source-bucket \
  --destination-bucket my-destination-bucket \
  [--report bucket my-reports-bucket] \
  [--role-name my-role-name] \
  [--source-kms-key arn:aws:kms:::key/...] \
  [--dest-kms-key arn:aws:kms:::key/...] \
  [--manifest s3://inventory-bucket/path/manifest.json] \
  [--force]
```

Role name defaults to `s3-batch-replication-<source-bucket>`. `--force` updates the permissions
policy on an existing role without recreating it.

If `--source-kms-key` or `--dest-kms-key` are not provided, the command will attempt to detect
customer-managed KMS keys from the bucket encryption configuration automatically. AWS-managed keys
(`aws/s3`) are ignored — no explicit permissions are needed for those.

If `--manifest` is provided and the manifest lives in a different bucket than the source bucket,
the role will be granted `s3:GetObject` on that bucket. The manifest URI is also propagated to
downstream `split` commands when chaining.

When chained, the role ARN is passed automatically to downstream commands. A 30-second propagation
delay is applied once by the first downstream command that consumes the role ARN from context.

### `setup-replication-rules`

Configures a Cross-Region Replication rule on the source bucket. Versioning is automatically
enabled on both buckets. The destination bucket must already exist with versioning enabled.

```
s3-batch-replication setup-replication-rules \
  --source-bucket my-source-bucket \
  --destination-bucket my-destination-bucket \
  --role-arn arn:aws:iam::123456789012:role/MyRole \
  [--force]
```

`--force` is required to add a new rule when a replication configuration already exists.
Without it the command aborts safely.

**Delete marker replication is disabled** by default. S3 Batch Replication replicates existing
objects from inventory -- delete markers are not objects and are not included in inventory data.
Enabling delete marker replication would replicate future live deletions, which is outside the
scope of this tool. As a result, `s3:ReplicateDelete` is intentionally omitted from the IAM role
permissions. If you need delete marker replication, enable it manually on the rule after creation
and add `s3:ReplicateDelete` to the role's permissions policy.

**Important — existing replication role is preserved:** If the source bucket already has a
replication configuration, the existing IAM role ARN is preserved and `--role-arn` is ignored.
This prevents silently breaking existing replication rules that depend on that role. However, the
existing role may not have permissions for the new destination bucket — you must ensure it has
`s3:ReplicateObject` on the new destination, either by updating the role manually or by re-running
`setup-iam-role --force --role-name <existing-role-name> --destination-bucket <new-bucket>` before
running this command. `--role-name` is required to target the correct existing role — without it a
new role will be created.

### `split`

Downloads the master inventory manifest, partitions it into sub-manifests, and writes them to S3 or
a local directory.

```
s3-batch-replication split \
  --manifest s3://bucket/path/manifest.json \
  [--objects-per-job 10B] \
  [--objects-per-manifest-file 3M] \
  [--output s3://bucket/prefix | /local/dir] \
  [--max-objects 100M] \
  [--failure-threshold 0] \
  [--continue-after-failure] \
  [--dry-run] \
  [--count-objects]
```

Sub-manifests are named after the source manifest: `manifest_part1.json`, `manifest_part2.json`, etc.
By default they are written to the same S3 prefix as the input manifest.

`--max-objects` limits processing to approximately the first N objects (rounded to whole inventory
files). Useful for testing without processing the full inventory.

`--failure-threshold` sets the percentage of sub-manifest upload failures to tolerate before aborting
(default `0` — any failure aborts). Only successfully uploaded manifests are passed to `replicate`.
`--continue-after-failure` keeps uploading remaining sub-manifests after the threshold is exceeded,
but still exits non-zero and does not chain to `replicate`.

**Recommended first step — dry run with exact object counts:**

Before running a full split, use `--dry-run --count-objects` to see exactly how many jobs would be
created and how many objects each job would contain:

```
s3-batch-replication split \
  --manifest s3://bucket/path/manifest.json \
  --objects-per-job 10B \
  --dry-run --count-objects
```

This downloads all inventory CSV files to count rows precisely. Downloads are parallelized across
half the available CPUs. Without `--count-objects`, job sizes are estimated using
`--objects-per-manifest-file` (default 3M) which may over- or under-estimate depending on actual
object key lengths and metadata.

**Cost warning:** `--count-objects` downloads all inventory CSV data files from S3. Standard S3
GET request and data transfer charges apply. For large inventories this can be significant — check
your inventory file sizes before using this option.

### `replicate`

Creates S3 Batch Replication jobs from a set of sub-manifests. Jobs are created in suspended state
by default for review before activation.

```
s3-batch-replication replicate \
  --manifests s3://bucket/path/manifest_part1.json \
  --manifests s3://bucket/path/manifest_part2.json \
  --role-arn arn:aws:iam::123456789012:role/MyRole \
  [--priority 10] \
  [--report-bucket my-reports-bucket] \
  [--report-scope AllTasks|FailedTasksOnly] \
  [--no-confirmation] \
  [--skip-iam-validation]
```

`--report-bucket` enables a completion report written to the specified bucket after each job completes.
Accepts a bucket name or full ARN. Defaults to `AllTasks` scope — use `--report-scope FailedTasksOnly`
to report only failed tasks.

`--no-confirmation` creates jobs in active state so they start immediately without manual review.
By default, jobs are suspended and must be activated manually:

- **Console**: S3 → Batch Operations → select job → Run job
- **CLI**: `aws s3control update-job-status --account-id <account> --job-id <job-id> --requested-job-status Ready --region <region>`

If sub-manifests are local files, upload them to S3 first:

```
s3-batch-replication replicate \
  --manifests /local/manifest_part1.json \
  --manifests /local/manifest_part2.json \
  --dest-bucket my-bucket \
  [--dest-prefix inventory/manifests] \
  --role-arn arn:aws:iam::123456789012:role/MyRole
```

### `validate-setup`

Runs pre-flight checks before executing batch replication. Exits with code 1 if any check fails.

```
s3-batch-replication validate-setup \
  --source-bucket my-source-bucket \
  --destination-bucket my-destination-bucket \
  --role-arn arn:aws:iam::123456789012:role/MyRole \
  [--report-bucket my-reports-bucket]
```

Checks performed:
- Versioning enabled on source and destination buckets
- At least one enabled replication rule on the source bucket
- IAM role trust policy includes `batchoperations.s3.amazonaws.com`
- At least one CSV inventory configuration on the source bucket
- Inventory is configured with `IncludedObjectVersions=All` (required for `VersionId` in schema)
- Inventory destination bucket policy allows `s3:PutObject` from `s3.amazonaws.com`
- IAM role has required KMS permissions for any customer-managed keys on source/destination buckets
  (smoke test only — use `--no-check-kms` if your policy uses conditions or wildcards that cause false positives)
- If `--report-bucket` is provided: bucket policy allows `s3:PutObject` from `batchoperations.s3.amazonaws.com`

**Cross-account replication limitation:** The destination bucket policy (`s3:ReplicateObject`) is
not validated. For cross-account replication, the destination bucket must have a bucket policy
granting `s3:ReplicateObject` to the source account — this cannot be verified from the source
account. Verify this manually on the destination account before activating jobs. See
[Configuring replication for source and destination buckets owned by different accounts](https://docs.aws.amazon.com/AmazonS3/latest/userguide/replication-walkthrough-2.html)
for details.

`--report-bucket` is propagated to a chained `replicate` command automatically.

Individual checks can be skipped with `--no-check-versioning`, `--no-check-replication-rule`,
`--no-check-iam-role`, `--no-check-inventory`, `--no-check-inventory-policy`,
and `--no-check-kms`.

When chained after `setup-iam-role` and `setup-replication-rules`, bucket and role context is
passed automatically — no flags required.

### Chained (one-shot)

Commands can be chained -- each passes its output to the next automatically:

```
s3-batch-replication --region me-south-1 \
  setup-iam-role \
    --source-bucket my-source-bucket \
    --destination-bucket my-destination-bucket \
    --report-bucket my-reports-bucket \
  setup-replication-rules \
    --source-bucket my-source-bucket \
    --destination-bucket my-destination-bucket \
  split \
    --manifest s3://bucket/path/manifest.json \
    --objects-per-job 14.5B \
  replicate \
    --report-bucket my-reports-bucket
```

Or skipping IAM and replication rule setup if already configured:

```
s3-batch-replication split --manifest s3://bucket/path/manifest.json \
  replicate --role-arn arn:aws:iam::123456789012:role/MyRole
```

## Splitting strategy

The number of inventory files assigned to each job is derived as:

```
files_per_job = objects_per_job / objects_per_manifest_file
```

Inventory files are assigned sequentially until `files_per_job` is reached, then a new job is started.
This avoids downloading the inventory data files — only the `manifest.json` is read.

`--objects-per-manifest-file` defaults to 3M, which is the ceiling used by S3 Inventory when writing
CSV files. Using this ceiling means `--objects-per-job` (default 10B) will never produce a job that
exceeds the limit. The actual value can vary -- if you need precise job sizing, verify the actual
file density from your inventory manifest before proceeding.
