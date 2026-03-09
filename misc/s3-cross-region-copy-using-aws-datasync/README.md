# Quick Start Guide

Use this guide to configure DataSync tasks for data replication between AWS S3 buckets in different regions.

## Requirements

- Python 3
- Boto3 library (AWS SDK for Python)
- **IAM Permissions**:
   - `iam:CreateRole`, `iam:PutRolePolicy`, `iam:GetRole`
   - `iam:CreateServiceLinkedRole`
   - `s3:CreateBucket` (if auto-creating destination bucket)
   - `datasync:*`

## Setup

Before running the create_datasync_task.py script, ensure that you have Python 3 and Boto3 installed.
Install Boto3 using pip if it's not already installed:

```bash
pip install boto3
```

Configure your AWS credentials using the AWS CLI:

```bash
aws configure --profile your-profile-name
```

## Usage

There are 3 tools provided to help your setup, run, monitor, and cleanup DataSync resources
for your data copy jobs:

1. Create and run your DataSync tasks - create_datasync_task.py
2. Check the status of your DataSync tasks - check_task_status.py
3. Delete the DataSync tasks - cleanup_datasync_tasks.py

### Run create_datasync_task.py:

This step will create a DataSync task to copy data from your source to destination bucket. It
can also optionally start the DataSync task, or you can start it yourself via the AWS DataSync console
or CLI.

The script also stores the ARNs of any resources created in datasync.json.

You will provide:

- The source bucket and optionally its region (default region is me-central-1)
- The destination bucket and its region
- Optionally, you can have the script run the create DataSync task

```bash
python create_datasync_task.py \
    --source-bucket my-bucket \
    --source-region me-central-1 \
    --dest-bucket my-dest-bucket \
    --dest-region eu-west-1 \
    --start
```

This automatically:
- Creates IAM roles (source read-only, destination write)
- Creates DataSync locations
- Creates DataSync enhanced mode task
- Saves to `datasync_tasks.json`
- Runs the created DataSync task

More options are covered later in the README.

### Run check_task_status.py

This command helps you monitor the DataSync tasks created by the create_datasync_task.py script.  You can run
the script multiple times manually or you can pass the `--monitor` option to have the script poll for
you and post any updates to the screen.

Check execution status of all tasks in registry:
```bash
python check_task_status.py
```

Same as above, but the script will poll for you:
```bash
python check_task_status.py --monitor
```

### Run cleanup_datasync_tasks.py

This step is optional, but can be useful if you do not intend to run the DataSync tasks again.

This script will delete all DataSync resources created by the script.  This will not affect any data
transferred by the DataSync tasks or any data in your S3 buckets.

Preview what will be deleted:
```bash
python cleanup_datasync_tasks.py --dry-run
```

Delete all resources (buckets are never deleted):
```bash
python cleanup_datasync_tasks.py
```

## Detailed Command Line Options for create_datasync_task.py

### Required
- `--source-bucket` - Source S3 bucket name
- `--dest-region` - Destination AWS region (e.g., us-east-1, eu-west-1)

### Optional
- `--source-region` - Source AWS region (default: me-central-1)
- `--dest-bucket` - Destination bucket name (omit to auto-create)
- `--throughput-mbps` - Throughput limit in Mbps (default: 100)
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

### Auto-create destination bucket and all resources:

```bash
python create_datasync_task.py \
    --source-bucket my-bucket \
    --source-region me-central-1 \
    --dest-region eu-west-1
```

This automatically:
- Creates destination bucket: `my-bucket-eu-west-1`
- Creates IAM roles (source read-only, destination write)
- Creates DataSync locations
- Creates Enhanced mode task
- Saves to `datasync_tasks.json`

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

If you have many buckets to copy, you can provide a list of the details in a CSV file.

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

