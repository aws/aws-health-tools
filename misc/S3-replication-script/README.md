# S3 Replication Setup Script

## Goal

This script is designed to quickly setup replication between a source bucket and a destination bucket.
This script is primarily intended to assist with migration from me-central-1. You can use this script to setup a one-time S3 batch replication job from any AWS region by specifying the `--source-region` command line argument.

## Requirements

- Python 3
- Boto3 library (AWS SDK for Python)
- Permissions to create a replication IAM role (or have an existing one) and to create destination bucket, batch job, replication config.

## Setup

Before running the script, ensure that you have Python 3 and Boto3 installed.
Install Boto3 using pip if it's not already installed:

```bash
pip install boto3
```

Configure your AWS credentials using the AWS CLI:

```bash
aws configure --profile your-profile-name
```

## Usage

Run the script from the command line, specifying the arns of the S3 source and destination buckets along with the destination region.
You can optionally provide the source region (it will default to me-central-1) and an IAM ARN to use as the replication role.
Versioning will be enabled on the source and destination buckets by the script as this is required for replication.

### Arguments

- `--source-bucket`: The name of the source bucket.
- `--destination-bucket`: The name of the destination bucket. This bucket will be created if it does not exist.
- `--destination-region`: The destination region. (e.g. eu-central-1)
- `--source-region`: (Optional) The source region. This will default to me-central-1.
- `--role-arn`: (Optional) The replication role arn. If this is not provided a role will be created called s3-replication-{source-region}-{source-bucket}

## Examples

- **Check Settings Without Updating**:
  ```bash
  python3 setupReplication-me-central-1.py --source-bucket=my-source-bucket --source-region=me-central-1 --destination-bucket=my-destination-bucket --destination-region=eu-central-1 --role-arn=arn:aws:iam::123456789012:role/my-replication-role
  ```
