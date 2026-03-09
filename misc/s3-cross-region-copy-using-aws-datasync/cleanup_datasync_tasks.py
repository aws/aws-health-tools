#!/usr/bin/env python3
"""
DataSync Task Cleanup Script

Cleans up DataSync tasks and associated resources using the task registry JSON file.

Usage:
    python cleanup_datasync_tasks.py [--registry-file FILE] [--task-arn ARN] [--dry-run]

Examples:
    # Clean up all tasks in registry
    python cleanup_datasync_tasks.py

    # Clean up specific task
    python cleanup_datasync_tasks.py --task-arn arn:aws:datasync:...

    # Dry run (show what would be deleted)
    python cleanup_datasync_tasks.py --dry-run
"""

import argparse
import json
import sys
from pathlib import Path
import boto3
from botocore.exceptions import ClientError
from botocore.config import Config

# Configure boto3 with increased retries
BOTO3_CONFIG = Config(retries={'max_attempts': 10, 'mode': 'standard'})

DEFAULT_REGISTRY_FILE = "datasync_tasks.json"


def load_registry(file_path):
    """Load task registry from JSON file."""
    if not Path(file_path).exists():
        print(f"✗ Registry file not found: {file_path}", file=sys.stderr)
        sys.exit(1)
    
    with open(file_path, 'r') as f:
        return json.load(f)


def delete_task(datasync_client, task_arn, dry_run=False):
    """Delete a DataSync task."""
    if dry_run:
        print(f"  [DRY RUN] Would delete task: {task_arn}")
        return True
    
    try:
        datasync_client.delete_task(TaskArn=task_arn)
        print(f"  ✓ Deleted task: {task_arn}")
        return True
    except ClientError as e:
        if e.response['Error']['Code'] == 'ResourceNotFoundException':
            print(f"  ⚠ Task not found (already deleted?): {task_arn}")
            return True
        print(f"  ✗ Failed to delete task: {e}", file=sys.stderr)
        return False


def delete_location(datasync_client, location_arn, location_type, dry_run=False):
    """Delete a DataSync location."""
    if dry_run:
        print(f"  [DRY RUN] Would delete {location_type} location: {location_arn}")
        return True
    
    try:
        datasync_client.delete_location(LocationArn=location_arn)
        print(f"  ✓ Deleted {location_type} location: {location_arn}")
        return True
    except ClientError as e:
        if e.response['Error']['Code'] == 'ResourceNotFoundException':
            print(f"  ⚠ Location not found (already deleted?): {location_arn}")
            return True
        print(f"  ✗ Failed to delete {location_type} location: {e}", file=sys.stderr)
        return False


def delete_role(iam_client, role_arn, dry_run=False):
    """Delete an IAM role and its inline policies."""
    role_name = role_arn.split('/')[-1]
    
    if dry_run:
        print(f"  [DRY RUN] Would delete role: {role_name}")
        return True
    
    try:
        # Delete inline policies first
        response = iam_client.list_role_policies(RoleName=role_name)
        for policy_name in response['PolicyNames']:
            iam_client.delete_role_policy(RoleName=role_name, PolicyName=policy_name)
            print(f"    ✓ Deleted inline policy: {policy_name}")
        
        # Delete role
        iam_client.delete_role(RoleName=role_name)
        print(f"  ✓ Deleted role: {role_name}")
        return True
    except ClientError as e:
        if e.response['Error']['Code'] == 'NoSuchEntity':
            print(f"  ⚠ Role not found (already deleted?): {role_name}")
            return True
        print(f"  ✗ Failed to delete role: {e}", file=sys.stderr)
        return False


def cleanup_task(task_info, dry_run=False):
    """Clean up a single task and its resources."""
    print(f"\n🗑️  Cleaning up task: {task_info.get('task_name', 'Unnamed')}")
    print(f"   Task ARN: {task_info['task_arn']}")
    
    source_region = task_info['source']['region']
    dest_region = task_info['destination']['region']
    task_region = task_info.get('task_region', source_region)  # Default to source for old registry files
    
    source_client = boto3.client('datasync', region_name=source_region, config=BOTO3_CONFIG)
    dest_client = boto3.client('datasync', region_name=dest_region, config=BOTO3_CONFIG)
    task_client = boto3.client('datasync', region_name=task_region, config=BOTO3_CONFIG)
    iam_client = boto3.client('iam', config=BOTO3_CONFIG)
    
    success = True
    
    # Delete task
    print("\n  Deleting DataSync task...")
    success &= delete_task(task_client, task_info['task_arn'], dry_run)
    
    # Delete source location
    print("\n  Deleting source location...")
    success &= delete_location(source_client, task_info['source']['location_arn'], 'source', dry_run)
    
    # Delete destination location
    print("\n  Deleting destination location...")
    success &= delete_location(dest_client, task_info['destination']['location_arn'], 'destination', dry_run)
    
    # Delete roles if they were created by the script
    if task_info['source'].get('role_created', False):
        print("\n  Deleting source IAM role...")
        success &= delete_role(iam_client, task_info['source']['role_arn'], dry_run)
    else:
        print(f"\n  ⏭️  Skipping source role (user-provided): {task_info['source']['role_arn']}")
    
    if task_info['destination'].get('role_created', False):
        print("\n  Deleting destination IAM role...")
        success &= delete_role(iam_client, task_info['destination']['role_arn'], dry_run)
    else:
        print(f"\n  ⏭️  Skipping destination role (user-provided): {task_info['destination']['role_arn']}")
    
    return success


def main():
    parser = argparse.ArgumentParser(
        description='Clean up DataSync tasks and resources',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    
    parser.add_argument(
        '--registry-file',
        default=DEFAULT_REGISTRY_FILE,
        help=f'Path to task registry JSON file (default: {DEFAULT_REGISTRY_FILE})'
    )
    parser.add_argument(
        '--task-arn',
        help='Clean up only the specified task ARN'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Show what would be deleted without actually deleting'
    )
    
    args = parser.parse_args()
    
    # Load registry
    registry = load_registry(args.registry_file)
    tasks = registry.get('tasks', [])
    
    if not tasks:
        print("No tasks found in registry.")
        return 0
    
    # Filter tasks if specific ARN provided
    if args.task_arn:
        tasks = [t for t in tasks if t['task_arn'] == args.task_arn]
        if not tasks:
            print(f"✗ Task not found in registry: {args.task_arn}", file=sys.stderr)
            return 1
    
    if args.dry_run:
        print("🔍 DRY RUN MODE - No resources will be deleted\n")
    
    print(f"Found {len(tasks)} task(s) to clean up")
    
    # Clean up each task
    all_success = True
    for task_info in tasks:
        success = cleanup_task(task_info, args.dry_run)
        all_success &= success
    
    if args.dry_run:
        print("\n✅ Dry run complete. Use without --dry-run to actually delete resources.")
    elif all_success:
        print("\n✅ Cleanup complete!")
    else:
        print("\n⚠️  Cleanup completed with some errors. Check output above.")
        return 1
    
    return 0


if __name__ == '__main__':
    sys.exit(main())
