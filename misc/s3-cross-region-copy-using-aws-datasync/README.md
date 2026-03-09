# Quick Start Guide

Get started with DataSync task creation in minutes.

## Prerequisites

1. **AWS Credentials**: Configure with `aws configure`
2. **IAM Permissions**:
   - `iam:CreateRole`, `iam:PutRolePolicy`, `iam:GetRole`
   - `iam:CreateServiceLinkedRole` (for Enhanced mode)
   - `s3:CreateBucket` (if auto-creating destination bucket)
   - `datasync:*`
3. **Source Bucket**: Must exist in source region (default: me-central-1)

## Simplest Usage

### Provide the source and destination buckets and let the script create the rest:

```bash
python create_datasync_task.py \
    --source-bucket my-bucket \
    --source-region me-central-1 \
    --dest-bucket my-dest-bucket \
    --dest-region us-east-1
```

This automatically:
- Creates IAM roles (source read-only, destination write)
- Creates DataSync locations
- Creates Enhanced mode task (250 MB/s default)
- Saves to `datasync_tasks.json`

### Auto-create destination bucket and all resources:

```bash
python create_datasync_task.py \
    --source-bucket my-bucket \
    --source-region me-central-1 \
    --dest-region us-east-1
```

This automatically:
- Creates destination bucket: `my-bucket-us-east-1`
- Creates IAM roles (source read-only, destination write)
- Creates DataSync locations
- Creates Enhanced mode task (250 MB/s default)
- Saves to `datasync_tasks.json`

## Command Line Options

### Required
- `--source-bucket` - Source S3 bucket name
- `--dest-region` - Destination AWS region (e.g., us-east-1, eu-west-1)

### Optional
- `--source-region` - Source AWS region (default: me-central-1)
- `--dest-bucket` - Destination bucket name (omit to auto-create)
- `--throughput-mbps` - Throughput limit in Mbps (default: 250)
- `--log-level` - CloudWatch logging level: OFF, BASIC, TRANSFER (default: BASIC)
- `--source-role-arn` - IAM role ARN for source (omit to auto-create)
- `--dest-role-arn` - IAM role ARN for destination (omit to auto-create)
- `--task-name` - Friendly name for the task
- `--output-file` - JSON registry file (default: datasync_tasks.json)
- `--start` - Start task execution after creation (mutually exclusive with --test-mode)
- `--include-filter` - Include filter pattern (e.g., /test/*) - only with --start
- `--csv-file` - CSV file for batch processing
- `--test-mode` - Start CSV tasks with include filters (mutually exclusive with --start)

## Common Examples

### Use Existing Destination Bucket
```bash
python create_datasync_task.py \
    --source-bucket my-bucket \
    --dest-bucket existing-bucket \
    --dest-region us-east-1
```

### Custom Source Region
```bash
python create_datasync_task.py \
    --source-bucket my-bucket \
    --source-region us-west-2 \
    --dest-region eu-west-1
```

### Custom Throughput
```bash
python create_datasync_task.py \
    --source-bucket my-bucket \
    --dest-region us-east-1 \
    --throughput-mbps 100
```

### Custom CloudWatch Logging
```bash
# Detailed transfer logs
python create_datasync_task.py \
    --source-bucket my-bucket \
    --dest-region us-east-1 \
    --log-level TRANSFER

# Disable logging
python create_datasync_task.py \
    --source-bucket my-bucket \
    --dest-region us-east-1 \
    --log-level OFF
```

### Auto-Start Task
```bash
python create_datasync_task.py \
    --source-bucket my-bucket \
    --dest-region us-east-1 \
    --start
```

### Test with Include Filter
```bash
# Test with small subset of files
python create_datasync_task.py \
    --source-bucket my-bucket \
    --dest-region us-east-1 \
    --start \
    --include-filter /test/*
```

### Use Existing IAM Roles
```bash
python create_datasync_task.py \
    --source-bucket my-bucket \
    --dest-bucket my-dest \
    --dest-region us-east-1 \
    --source-role-arn arn:aws:iam::123456789012:role/SourceRole \
    --dest-role-arn arn:aws:iam::123456789012:role/DestRole
```

## CSV Batch Processing

### CSV Format

**Required columns**: `source_bucket`, `dest_region`

**Optional columns**: `source_region`, `dest_bucket`, `throughput_mbps`, `source_role_arn`, `dest_role_arn`, `task_name`, `log_level`, `include_filter`

### Example CSV

```csv
source_bucket,source_region,dest_region,throughput_mbps,log_level,include_filter,task_name
bucket1,me-central-1,us-east-1,250,BASIC,/test/*,Transfer to US East
bucket2,us-west-2,eu-west-1,100,TRANSFER,/sample/*.txt,Transfer to EU West
bucket3,ap-south-1,us-east-1,250,OFF,,Transfer to AP South
```

### Run Batch

```bash
# Create tasks without starting
python create_datasync_task.py --csv-file tasks.csv

# Create and start all tasks
python create_datasync_task.py --csv-file tasks.csv --start

# Create and start tasks with include filters from CSV (test mode)
python create_datasync_task.py --csv-file tasks.csv --test-mode
```

**Notes**:
- Column names are case-insensitive
- Boolean values no longer used (use --start or --test-mode flags instead)
- Log level values: `OFF`, `BASIC`, `TRANSFER` (default: BASIC)
- Include filter: Must start with `/` (e.g., `/test/*`, `/sample/*.txt`)
- Empty `dest_bucket` auto-creates bucket
- Empty `include_filter` runs without filter
- Tasks processed sequentially
- Failures don't stop other tasks
- Use `--start` to start all tasks
- Use `--test-mode` to start tasks with include filters from CSV

## Test Mode

Test mode allows you to run tasks with a small subset of files before running the full transfer.

### Usage

```bash
# Test run with include filters from CSV
python create_datasync_task.py --csv-file tasks.csv --test-mode

# Production run without filters
python create_datasync_task.py --csv-file tasks.csv
```

### How It Works

- `--test-mode` flag uses `include_filter` column from CSV
- Same CSV file works for both test and production runs
- Tasks without `include_filter` run normally even in test mode
- Include filters are passed to DataSync `start_task_execution` API

## Starting Tasks

### Manual Start
```bash
aws datasync start-task-execution \
    --task-arn <TASK_ARN> \
    --region <DEST_REGION>
```

### Auto-Start
Use `--start` flag (single task or CSV) or `--test-mode` flag (CSV only) when creating tasks.

## Checking Task Status

Check execution status of all tasks in registry:
```bash
python check_task_status.py
```

Monitor tasks continuously (updates on status change):
```bash
python check_task_status.py --monitor
```

Output in machine-friendly formats:
```bash
# JSON format
python check_task_status.py --json

# CSV format
python check_task_status.py --csv
```

The script shows:
- Task ARN and Execution ARN
- Current execution status (LAUNCHING, TRANSFERRING, SUCCESS, ERROR, etc.)
- Whether task is currently running
- Test mode indicator (include filter present/absent)
- Transfer progress (bytes and files transferred)
- Start time of current/last execution

Press Ctrl+C to stop monitoring and see final status.

## Cleanup

Preview what will be deleted:
```bash
python cleanup_datasync_tasks.py --dry-run
```

Delete all resources (buckets are never deleted):
```bash
python cleanup_datasync_tasks.py
```

## What Gets Created

1. **Destination Bucket** (if omitted):
   - Name: `{source-bucket}-{dest-region}` (truncated to 63 chars)
   - Public access blocked
   - AES256 encryption enabled
   - Versioning matches source

2. **IAM Roles** (if not provided):
   - Source: `DataSyncS3Role-{bucket}-source` (read-only, truncated to 64 chars)
   - Destination: `DataSyncS3Role-{bucket}-dest` (write, truncated to 64 chars)

3. **DataSync Locations**:
   - Source location in source region
   - Destination location in destination region

4. **DataSync Task**:
   - Enhanced mode (optimal for S3-to-S3)
   - Created in destination region
   - Throughput limit applied
   - CloudWatch logging enabled (default: BASIC level)
   - Logs written to: `/aws/datasync` log group
   - Verify: ONLY_FILES_TRANSFERRED
   - Overwrite: ALWAYS
   - Transfer: CHANGED

5. **Registry File**: JSON file tracking all created resources

