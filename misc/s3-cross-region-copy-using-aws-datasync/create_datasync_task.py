#!/usr/bin/env python3
"""
DataSync Enhanced Task Creator

Creates an AWS DataSync task to transfer data from an S3 bucket in one region
to another S3 bucket in a different region with throughput limits.

Usage:
    python create_datasync_task.py \\
        --source-bucket SOURCE_BUCKET \\
        --source-region SOURCE_REGION \\
        --dest-bucket DEST_BUCKET \\
        --dest-region DEST_REGION \\
        [--throughput-mbps THROUGHPUT] \\
        [--source-role-arn ROLE_ARN] \\
        [--dest-role-arn ROLE_ARN] \\
        [--task-name TASK_NAME]

Example:
    python create_datasync_task.py \\
        --source-bucket my-source-bucket \\
        --source-region me-central-1 \\
        --dest-bucket my-dest-bucket \\
        --dest-region us-east-1 \\
        --throughput-mbps 100 \\
        --task-name my-transfer-task
"""

import argparse
import sys
import json
import time
import csv
from datetime import datetime, timezone
from pathlib import Path
import boto3
from botocore.exceptions import ClientError
from botocore.config import Config

# Configure boto3 with increased retries
BOTO3_CONFIG = Config(retries={'max_attempts': 10, 'mode': 'standard'})

DEFAULT_THROUGHPUT_MBPS = 100
DEFAULT_OUTPUT_FILE = "datasync_tasks.json"
DEFAULT_SOURCE_REGION = "me-central-1"
DEFAULT_LOG_LEVEL = "BASIC"

# AWS service name limits
MAX_S3_BUCKET_NAME_LENGTH = 63
MAX_IAM_ROLE_NAME_LENGTH = 64


def _truncate_name(name, max_length):
    """Truncate a name to fit within max_length, stripping trailing hyphens."""
    if len(name) <= max_length:
        return name
    return name[:max_length].rstrip('-')


def generate_dest_bucket_name(source_bucket, dest_region):
    """Generate destination bucket name based on source bucket and region.
    
    S3 bucket names must be 3-63 characters. The region suffix is always
    preserved; the base name is truncated if needed.
    """
    base_name = source_bucket.rsplit('-', 1)[0] if '-' in source_bucket else source_bucket
    suffix = f"-{dest_region}"
    max_base = MAX_S3_BUCKET_NAME_LENGTH - len(suffix)
    if max_base < 3:
        raise ValueError(f"Region suffix '{suffix}' is too long to form a valid bucket name")
    base_name = base_name[:max_base].rstrip('-')
    return f"{base_name}{suffix}"


def create_destination_bucket(source_bucket, source_region, dest_region):
    """Create destination S3 bucket with secure policy matching source versioning."""
    bucket_name = generate_dest_bucket_name(source_bucket, dest_region)
    s3_source = boto3.client('s3', region_name=source_region, config=BOTO3_CONFIG)
    s3_dest = boto3.client('s3', region_name=dest_region, config=BOTO3_CONFIG)
    
    print(f"\nCreating destination bucket: {bucket_name}")
    
    # Get source bucket versioning status
    try:
        source_versioning = s3_source.get_bucket_versioning(Bucket=source_bucket)
        versioning_enabled = source_versioning.get('Status') == 'Enabled'
    except ClientError:
        versioning_enabled = False
        print(f"  ⚠ Could not check source versioning, defaulting to disabled")
    
    try:
        # Create bucket
        if dest_region == 'us-east-1':
            s3_dest.create_bucket(Bucket=bucket_name)
        else:
            s3_dest.create_bucket(
                Bucket=bucket_name,
                CreateBucketConfiguration={'LocationConstraint': dest_region}
            )
        print(f"✓ Created bucket: {bucket_name}")
        
        # Block public access
        s3_dest.put_public_access_block(
            Bucket=bucket_name,
            PublicAccessBlockConfiguration={
                'BlockPublicAcls': True,
                'IgnorePublicAcls': True,
                'BlockPublicPolicy': True,
                'RestrictPublicBuckets': True
            }
        )
        print(f"✓ Enabled public access block")
        
        # Enable default encryption
        s3_dest.put_bucket_encryption(
            Bucket=bucket_name,
            ServerSideEncryptionConfiguration={
                'Rules': [{
                    'ApplyServerSideEncryptionByDefault': {
                        'SSEAlgorithm': 'AES256'
                    },
                    'BucketKeyEnabled': True
                }]
            }
        )
        print(f"✓ Enabled default encryption")
        
        # Match source versioning
        if versioning_enabled:
            s3_dest.put_bucket_versioning(
                Bucket=bucket_name,
                VersioningConfiguration={'Status': 'Enabled'}
            )
            print(f"✓ Enabled versioning (matching source)")
        else:
            print(f"✓ Versioning disabled (matching source)")
        
        print()
        return bucket_name
        
    except ClientError as e:
        if e.response['Error']['Code'] == 'BucketAlreadyOwnedByYou':
            print(f"✓ Bucket already exists: {bucket_name}\n")
            return bucket_name
        print(f"✗ Failed to create bucket: {e}", file=sys.stderr)
        raise


def load_task_registry(file_path):
    """Load existing task registry or create new one."""
    if Path(file_path).exists():
        with open(file_path, 'r') as f:
            return json.load(f)
    return {"tasks": []}


def save_task_registry(file_path, registry):
    """Save task registry to file."""
    try:
        with open(file_path, 'w') as f:
            json.dump(registry, f, indent=2)
        print(f"\n💾 Task information saved to: {file_path}")
    except Exception as e:
        print(f"\n⚠ Warning: Failed to save registry to {file_path}: {e}", file=sys.stderr)
        raise


def add_task_to_registry(registry, task_info):
    """Add new task to registry."""
    registry["tasks"].append(task_info)
    return registry


def validate_csv_format(file_path):
    """
    Validate CSV file format and return list of task configurations.
    
    Required columns: source_bucket, dest_region
    Optional columns: source_region, dest_bucket, throughput_mbps, source_role_arn, dest_role_arn, task_name, log_level, include_filter
    
    Returns:
        List of dictionaries with task configurations
    
    Raises:
        ValueError if CSV format is invalid
    """
    required_columns = {'source_bucket', 'dest_region'}
    optional_columns = {'source_region', 'dest_bucket', 'throughput_mbps', 'source_role_arn', 'dest_role_arn', 
                       'task_name', 'log_level', 'include_filter'}
    valid_columns = required_columns | optional_columns
    
    try:
        with open(file_path, 'r') as f:
            reader = csv.DictReader(f)
            
            # Check if file is empty
            if reader.fieldnames is None:
                raise ValueError("CSV file is empty")
            
            # Normalize column names (strip whitespace, lowercase)
            columns = {col.strip().lower() for col in reader.fieldnames}
            
            # Check for required columns
            missing = required_columns - columns
            if missing:
                raise ValueError(f"Missing required columns: {', '.join(sorted(missing))}")
            
            # Check for invalid columns
            invalid = columns - valid_columns
            if invalid:
                raise ValueError(f"Invalid columns: {', '.join(sorted(invalid))}. Valid columns: {', '.join(sorted(valid_columns))}")
            
            # Parse rows
            tasks = []
            for row_num, row in enumerate(reader, start=2):  # Start at 2 (header is row 1)
                # Normalize keys
                normalized_row = {k.strip().lower(): v.strip() if v else None for k, v in row.items()}
                
                # Validate required fields are not empty
                for col in required_columns:
                    if not normalized_row.get(col):
                        raise ValueError(f"Row {row_num}: '{col}' cannot be empty")
                
                # Convert throughput to int if provided
                if normalized_row.get('throughput_mbps'):
                    try:
                        normalized_row['throughput_mbps'] = int(normalized_row['throughput_mbps'])
                    except ValueError:
                        raise ValueError(f"Row {row_num}: 'throughput_mbps' must be a number")
                else:
                    normalized_row['throughput_mbps'] = DEFAULT_THROUGHPUT_MBPS
                
                # Set default source region if not provided
                if not normalized_row.get('source_region'):
                    normalized_row['source_region'] = DEFAULT_SOURCE_REGION
                
                # Validate and set log level
                if normalized_row.get('log_level'):
                    log_level = normalized_row['log_level'].upper()
                    if log_level not in ('OFF', 'BASIC', 'TRANSFER'):
                        raise ValueError(f"Row {row_num}: 'log_level' must be OFF, BASIC, or TRANSFER")
                    normalized_row['log_level'] = log_level
                else:
                    normalized_row['log_level'] = DEFAULT_LOG_LEVEL
                
                # Validate include_filter if provided
                if normalized_row.get('include_filter'):
                    filter_val = normalized_row['include_filter']
                    # Basic validation: must start with / and contain valid filter pattern
                    if not filter_val.startswith('/'):
                        raise ValueError(f"Row {row_num}: 'include_filter' must start with '/' (e.g., '/test/*')")
                    if len(filter_val) < 2:
                        raise ValueError(f"Row {row_num}: 'include_filter' must have a pattern after '/'")
                
                tasks.append(normalized_row)
            
            if not tasks:
                raise ValueError("CSV file contains no data rows")
            
            return tasks
            
    except FileNotFoundError:
        raise ValueError(f"CSV file not found: {file_path}")
    except csv.Error as e:
        raise ValueError(f"CSV parsing error: {e}")



def create_datasync_role(iam_client, bucket_name, role_suffix, is_source=True):
    """Create a minimally permissioned IAM role for DataSync to access a specific S3 bucket."""
    role_name = _truncate_name(
        f"DataSyncS3Role-{bucket_name}-{role_suffix}",
        MAX_IAM_ROLE_NAME_LENGTH,
    )
    
    trust_policy = {
        "Version": "2012-10-17",
        "Statement": [{
            "Effect": "Allow",
            "Principal": {"Service": "datasync.amazonaws.com"},
            "Action": "sts:AssumeRole"
        }]
    }
    
    # Source role: read-only permissions
    if is_source:
        bucket_policy = {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Action": [
                        "s3:GetBucketLocation",
                        "s3:ListBucket",
                        "s3:ListBucketMultipartUploads"
                    ],
                    "Resource": f"arn:aws:s3:::{bucket_name}"
                },
                {
                    "Effect": "Allow",
                    "Action": [
                        "s3:GetObject",
                        "s3:GetObjectTagging",
                        "s3:ListMultipartUploadParts"
                    ],
                    "Resource": f"arn:aws:s3:::{bucket_name}/*"
                }
            ]
        }
    # Destination role: write permissions
    else:
        bucket_policy = {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Action": [
                        "s3:GetBucketLocation",
                        "s3:ListBucket",
                        "s3:ListBucketMultipartUploads"
                    ],
                    "Resource": f"arn:aws:s3:::{bucket_name}"
                },
                {
                    "Effect": "Allow",
                    "Action": [
                        "s3:AbortMultipartUpload",
                        "s3:DeleteObject",
                        "s3:GetObject",
                        "s3:ListMultipartUploadParts",
                        "s3:PutObject",
                        "s3:GetObjectTagging",
                        "s3:PutObjectTagging"
                    ],
                    "Resource": f"arn:aws:s3:::{bucket_name}/*"
                }
            ]
        }
    
    try:
        # Create role
        response = iam_client.create_role(
            RoleName=role_name,
            AssumeRolePolicyDocument=json.dumps(trust_policy),
            Description=f"DataSync access role for bucket {bucket_name}"
        )
        role_arn = response['Role']['Arn']
        print(f"✓ Created IAM role: {role_name}")
        
        # Attach inline policy
        iam_client.put_role_policy(
            RoleName=role_name,
            PolicyName=f"S3Access-{bucket_name}",
            PolicyDocument=json.dumps(bucket_policy)
        )
        print(f"✓ Attached S3 policy to role")
        
        # Wait for role to propagate
        print("  Waiting for IAM role to propagate...")
        time.sleep(10)
        
        return role_arn
    except ClientError as e:
        if e.response['Error']['Code'] == 'EntityAlreadyExists':
            # Role exists, get its ARN
            response = iam_client.get_role(RoleName=role_name)
            role_arn = response['Role']['Arn']
            print(f"✓ Using existing IAM role: {role_name}")
            return role_arn
        else:
            print(f"✗ Failed to create IAM role: {e}", file=sys.stderr)
            raise


def create_s3_location(client, bucket_name, region, role_arn, location_type):
    """Create a DataSync S3 location, or return existing one."""
    s3_config = {
        'BucketAccessRoleArn': role_arn
    }
    
    bucket_arn = f'arn:aws:s3:::{bucket_name}'
    expected_uri = f's3://{bucket_name}/'
    
    # Check if location already exists
    try:
        paginator = client.get_paginator('list_locations')
        for page in paginator.paginate():
            for location in page.get('Locations', []):
                location_arn = location['LocationArn']
                # Get location details to check bucket
                try:
                    details = client.describe_location_s3(LocationArn=location_arn)
                    if details.get('LocationUri') == expected_uri:
                        print(f"✓ Using existing {location_type} location: {location_arn}")
                        return location_arn
                except ClientError:
                    continue
    except ClientError as e:
        print(f"  ⚠ Could not list locations: {e}")
    
    # Create new location
    try:
        response = client.create_location_s3(
            S3BucketArn=bucket_arn,
            S3Config=s3_config
        )
        location_arn = response['LocationArn']
        print(f"✓ Created {location_type} location: {location_arn}")
        return location_arn
    except ClientError as e:
        print(f"✗ Failed to create {location_type} location: {e}", file=sys.stderr)
        raise


def start_datasync_task(task_arn, region, include_filter=None):
    """
    Start a DataSync task execution.
    
    Args:
        task_arn: DataSync task ARN
        region: AWS region where task is located
        include_filter: Optional include filter pattern (e.g., '/test/*')
    
    Returns:
        Task execution ARN if successful, None otherwise
    """
    client = boto3.client('datasync', region_name=region, config=BOTO3_CONFIG)
    
    print("Starting task execution...")
    if include_filter:
        print(f"  Using include filter: {include_filter}")
    
    try:
        params = {'TaskArn': task_arn}
        if include_filter:
            params['Includes'] = [{'FilterType': 'SIMPLE_PATTERN', 'Value': include_filter}]
        
        response = client.start_task_execution(**params)
        task_execution_arn = response['TaskExecutionArn']
        print(f"✓ Started task execution: {task_execution_arn}\n")
        print(f"  You can monitor task progress via the DataSync console or by running\n")
        print(f"  aws datasync describe-task-execution --task-execution-arn {task_execution_arn} --region {region}\n")
        return task_execution_arn
    except Exception as e:
        print(f"⚠ Failed to start task execution: {e}", file=sys.stderr)
        print("  Task created successfully but may not have been started.")
        print(f"\n  To start manually, run:")
        if include_filter:
            print(f"  aws datasync start-task-execution --task-arn {task_arn} --region {region} \\")
            print(f"    --includes FilterType=SIMPLE_PATTERN,Value={include_filter}\n")
        else:
            print(f"  aws datasync start-task-execution --task-arn {task_arn} --region {region}\n")
        return None


def create_datasync_task(source_bucket, source_region, dest_bucket, dest_region, throughput_mbps, 
                         source_role_arn=None, dest_role_arn=None, task_name=None, 
                         output_file=None, start_task=False, log_level=DEFAULT_LOG_LEVEL, 
                         include_filter=None):
    """
    Create an enhanced DataSync task with throughput limits.
    
    Args:
        source_bucket: Source S3 bucket name
        source_region: Source AWS region
        dest_bucket: Destination S3 bucket name (None to auto-create)
        dest_region: Destination AWS region
        throughput_mbps: Throughput limit in Mbps
        source_role_arn: Optional IAM role ARN for source location (created if not provided)
        dest_role_arn: Optional IAM role ARN for destination location (created if not provided)
        task_name: Optional task name
        output_file: Path to JSON file for saving task information
        start_task: If True, automatically start the task execution
        log_level: CloudWatch logging level (OFF, BASIC, or TRANSFER)
        include_filter: Optional include filter pattern for task execution (e.g., '/test/*')
    
    Returns:
        Tuple of (task_arn, task_info_dict)
    """
    # Auto-create destination bucket if not provided
    if not dest_bucket:
        dest_bucket = generate_dest_bucket_name(source_bucket, dest_region)
        dest_bucket = create_destination_bucket(source_bucket, source_region, dest_region)
    
    # Create clients
    source_client = boto3.client('datasync', region_name=source_region, config=BOTO3_CONFIG)
    dest_client = boto3.client('datasync', region_name=dest_region, config=BOTO3_CONFIG)
    iam_client = boto3.client('iam', config=BOTO3_CONFIG)
    print(f"\n📋 Creating DataSync task:")
    print(f"   Source: s3://{source_bucket} ({source_region})")
    print(f"   Destination: s3://{dest_bucket} ({dest_region})")
    print(f"   Task region: {dest_region}")
    print(f"   Throughput limit: {throughput_mbps} Mbps")
    print(f"   CloudWatch logging: {log_level}\n")
    
    # Track whether roles were created
    source_role_created = False
    dest_role_created = False
    
    # Create or use existing IAM roles
    if not source_role_arn:
        print("Creating IAM role for source location (read-only)...")
        source_role_arn = create_datasync_role(iam_client, source_bucket, "source", is_source=True)
        source_role_created = True
    else:
        print(f"Using provided source role: {source_role_arn}")
    
    if not dest_role_arn:
        print("Creating IAM role for destination location (write access)...")
        dest_role_arn = create_datasync_role(iam_client, dest_bucket, "dest", is_source=False)
        dest_role_created = True
    else:
        print(f"Using provided destination role: {dest_role_arn}")
    
    # Create source location in source region
    print("\nCreating source location...")
    source_location_arn = create_s3_location(
        source_client, source_bucket, source_region, source_role_arn, "source"
    )
    
    # Create destination location in destination region
    print("Creating destination location...")
    dest_location_arn = create_s3_location(
        dest_client, dest_bucket, dest_region, dest_role_arn, "destination"
    )
    
    # Create task in destination region with throughput limit
    print("Creating DataSync Enhanced mode task...")
    task_params = {
        'SourceLocationArn': source_location_arn,
        'DestinationLocationArn': dest_location_arn,
        'TaskMode': 'ENHANCED',
        'Options': {
            'VerifyMode': 'ONLY_FILES_TRANSFERRED',
            'OverwriteMode': 'ALWAYS',
            'TransferMode': 'CHANGED',
        },
    }
    
    # Add throughput limit (bandwidth limit in bytes/second)
    throughput_bytes_per_sec = throughput_mbps * 1024 * 1024 // 8
    task_params['Options']['BytesPerSecond'] = throughput_bytes_per_sec
    
    # Add CloudWatch logging level
    if log_level and log_level != 'OFF':
        task_params['Options']['LogLevel'] = log_level
        print(f"  CloudWatch logging enabled: {log_level}")
    
    if task_name:
        task_params['Name'] = task_name
    
    # Check if task already exists with these locations
    task_arn = None
    try:
        print("Checking for existing tasks with matching locations...")
        print(f"  Looking for source: {source_location_arn}")
        print(f"  Looking for dest: {dest_location_arn}")
        # List all tasks in destination region and check for matching locations
        paginator = dest_client.get_paginator('list_tasks')
        task_count = 0
        for page in paginator.paginate():
            for task in page.get('Tasks', []):
                task_count += 1
                task_details = dest_client.describe_task(TaskArn=task['TaskArn'])
                task_source = task_details.get('SourceLocationArn')
                task_dest = task_details.get('DestinationLocationArn')
                
                if task_source == source_location_arn and task_dest == dest_location_arn:
                    task_arn = task['TaskArn']
                    print(f"✓ Using existing task: {task_arn}\n")
                    break
            if task_arn:
                break
        if not task_arn:
            print(f"  No existing task found (checked {task_count} tasks)")
    except ClientError as e:
        print(f"  ⚠ Could not list tasks: {e}")
    
    # Create new task if not found
    if not task_arn:
        try:
            response = dest_client.create_task(**task_params)
            task_arn = response['TaskArn']
            print(f"✓ Created task: {task_arn}\n")
        except ClientError as e:
            print(f"✗ Failed to create task: {e}", file=sys.stderr)
            raise
    
    # Start task execution if requested
    task_execution_arn = None
    if start_task:
        task_execution_arn = start_datasync_task(task_arn, dest_region, include_filter)
    
    # Build task info for registry
    task_info = {
        "task_arn": task_arn,
        "task_name": task_name,
        "task_region": dest_region,
        "created_at": datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'),
        "source": {
            "bucket": source_bucket,
            "region": source_region,
            "location_arn": source_location_arn,
            "role_arn": source_role_arn,
            "role_created": source_role_created
        },
        "destination": {
            "bucket": dest_bucket,
            "region": dest_region,
            "location_arn": dest_location_arn,
            "role_arn": dest_role_arn,
            "role_created": dest_role_created
        },
        "throughput_mbps": throughput_mbps,
        "log_level": log_level
    }
    
    # Add execution ARN if task was started
    if task_execution_arn:
        task_info["task_execution_arn"] = task_execution_arn
        task_info["execution_started_at"] = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
    
    return task_arn, task_info


def main():
    parser = argparse.ArgumentParser(
        description='Create an enhanced DataSync task with throughput limits',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    
    # CSV input option
    parser.add_argument(
        '--csv-file',
        help='CSV file with task configurations (alternative to command-line args)'
    )
    
    parser.add_argument(
        '--source-bucket',
        help='Source S3 bucket name (in DXB/me-central-1 region)'
    )
    parser.add_argument(
        '--dest-bucket',
        help='Destination S3 bucket name (omit to auto-create with name: {source-bucket}-{dest-region})'
    )
    parser.add_argument(
        '--source-region',
        default=DEFAULT_SOURCE_REGION,
        help=f'Source AWS region (default: {DEFAULT_SOURCE_REGION})'
    )
    parser.add_argument(
        '--dest-region',
        help='Destination AWS region (e.g., us-east-1, eu-west-1)'
    )
    parser.add_argument(
        '--throughput-mbps',
        type=int,
        default=DEFAULT_THROUGHPUT_MBPS,
        help=f'Throughput limit in Mbps (default: {DEFAULT_THROUGHPUT_MBPS} Mbps)'
    )
    parser.add_argument(
        '--log-level',
        choices=['OFF', 'BASIC', 'TRANSFER'],
        default=DEFAULT_LOG_LEVEL,
        help=f'CloudWatch logging level (default: {DEFAULT_LOG_LEVEL}). OFF=no logging, BASIC=errors and basic info, TRANSFER=detailed file transfer logs'
    )
    parser.add_argument(
        '--source-role-arn',
        help='IAM role ARN for source location (created automatically if not provided)'
    )
    parser.add_argument(
        '--dest-role-arn',
        help='IAM role ARN for destination location (created automatically if not provided)'
    )
    parser.add_argument(
        '--task-name',
        help='Optional name for the DataSync task'
    )
    parser.add_argument(
        '--output-file',
        default=DEFAULT_OUTPUT_FILE,
        help=f'JSON file to save task information (default: {DEFAULT_OUTPUT_FILE})'
    )
    parser.add_argument(
        '--start',
        action='store_true',
        help='Start task execution after creation. Mutually exclusive with --test-mode.'
    )
    parser.add_argument(
        '--test-mode',
        action='store_true',
        help='Start task execution with include filter from CSV. Mutually exclusive with --start.'
    )
    parser.add_argument(
        '--include-filter',
        help='Include filter pattern for single task execution (e.g., /test/*). Only used with --start flag.'
    )
    
    args = parser.parse_args()
    
    # Validate mutually exclusive options
    if args.start and args.test_mode:
        parser.error("--start and --test-mode are mutually exclusive. Use only one.")
    
    # Determine if using CSV or command-line args
    if args.csv_file:
        # CSV mode
        try:
            print(f"📄 Validating CSV file: {args.csv_file}")
            tasks = validate_csv_format(args.csv_file)
            print(f"✓ CSV validation passed. Found {len(tasks)} task(s) to create.\n")
        except ValueError as e:
            print(f"❌ CSV validation failed: {e}", file=sys.stderr)
            return 1
        
        # Process each task from CSV
        registry = load_task_registry(args.output_file)
        success_count = 0
        fail_count = 0
        
        for idx, task_config in enumerate(tasks, start=1):
            print(f"{'='*60}")
            print(f"Processing task {idx}/{len(tasks)}")
            print(f"{'='*60}")
            
            # Determine if task should be started and with what filter
            start_task = args.start or args.test_mode
            include_filter = None
            
            if args.test_mode:
                if task_config.get('include_filter'):
                    include_filter = task_config['include_filter']
                    print(f"🧪 Test mode - using include filter: {include_filter}\n")
                else:
                    print(f"⚠️  Test mode enabled but no include_filter in CSV for this task\n")
            
            try:
                task_arn, task_info = create_datasync_task(
                    source_bucket=task_config['source_bucket'],
                    source_region=task_config['source_region'],
                    dest_bucket=task_config.get('dest_bucket'),
                    dest_region=task_config['dest_region'],
                    throughput_mbps=task_config['throughput_mbps'],
                    source_role_arn=task_config.get('source_role_arn'),
                    dest_role_arn=task_config.get('dest_role_arn'),
                    task_name=task_config.get('task_name'),
                    output_file=args.output_file,
                    start_task=start_task,
                    log_level=task_config['log_level'],
                    include_filter=include_filter
                )
                
                registry = add_task_to_registry(registry, task_info)
                success_count += 1
                print(f"✅ Task {idx} completed successfully.\n")
                
            except Exception as e:
                fail_count += 1
                print(f"❌ Task {idx} failed: {e}\n", file=sys.stderr)
                continue
        
        # Save registry after all tasks
        save_task_registry(args.output_file, registry)
        
        print(f"\n{'='*60}")
        print(f"Summary: {success_count} succeeded, {fail_count} failed out of {len(tasks)} total")
        print(f"{'='*60}")
        
        return 0 if fail_count == 0 else 1
        
    else:
        # Command-line args mode
        if not args.source_bucket or not args.dest_region:
            parser.error("--source-bucket and --dest-region are required (or use --csv-file)")
        
        # Validate include-filter if provided
        if args.include_filter:
            if not args.start:
                parser.error("--include-filter can only be used with --start")
            if not args.include_filter.startswith('/'):
                parser.error("--include-filter must start with '/' (e.g., /test/*)")
            if len(args.include_filter) < 2:
                parser.error("--include-filter must have a pattern after '/'")
        
        # test-mode is only for CSV
        if args.test_mode:
            parser.error("--test-mode can only be used with --csv-file")
        
        registry = load_task_registry(args.output_file)
        
        try:
            # Create task
            task_arn, task_info = create_datasync_task(
                source_bucket=args.source_bucket,
                source_region=args.source_region,
                dest_bucket=args.dest_bucket,
                dest_region=args.dest_region,
                throughput_mbps=args.throughput_mbps,
                source_role_arn=args.source_role_arn,
                dest_role_arn=args.dest_role_arn,
                task_name=args.task_name,
                output_file=args.output_file,
                start_task=args.start,
                log_level=args.log_level,
                include_filter=args.include_filter if args.start else None
            )
            
            # Add to registry and save
            print(f"\nAdding task to registry...")
            registry = add_task_to_registry(registry, task_info)
            save_task_registry(args.output_file, registry)
            
            print("✅ Success! Task created successfully.")
            
            if not args.start:
                print(f"\nTo start the task, run:")
                print(f"  aws datasync start-task-execution --task-arn {task_arn} --region {task_info['task_region']}")
            
            return 0
        except Exception as e:
            print(f"\n❌ Error: {e}", file=sys.stderr)
            return 1


if __name__ == '__main__':
    sys.exit(main())

