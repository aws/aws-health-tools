#!/usr/bin/env python3
"""
Check DataSync task execution status from registry.
"""

import json
import sys
import time
import signal
import csv
from datetime import datetime
from typing import Dict, List, Optional
import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

BOTO3_CONFIG = Config(retries={'max_attempts': 10, 'mode': 'standard'})
DEFAULT_REGISTRY = "datasync_tasks.json"
POLL_INTERVAL = 30  # seconds

# Global state for signal handler
last_known_states = {}
monitoring = False


def load_registry(file_path: str) -> List[Dict]:
    """Load task registry from JSON file."""
    try:
        with open(file_path, 'r') as f:
            data = json.load(f)
            return data.get('tasks', [])
    except FileNotFoundError:
        print(f"❌ Registry file not found: {file_path}")
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"❌ Invalid JSON in registry: {e}")
        sys.exit(1)


def get_task_executions(client, task_arn: str) -> List[Dict]:
    """Get all executions for a task, sorted by start time (newest first)."""
    try:
        response = client.list_task_executions(TaskArn=task_arn)
        executions = response.get('TaskExecutions', [])
        
        # Get StartTime for each execution by describing it
        executions_with_time = []
        for exec_summary in executions:
            exec_arn = exec_summary['TaskExecutionArn']
            try:
                details = client.describe_task_execution(TaskExecutionArn=exec_arn)
                exec_summary['StartTime'] = details.get('StartTime')
                executions_with_time.append(exec_summary)
            except ClientError:
                # Skip executions we can't describe
                continue
        
        # Sort by StartTime descending (newest first)
        executions_with_time.sort(key=lambda x: x.get('StartTime', datetime.min), reverse=True)
        return executions_with_time
    except ClientError as e:
        if e.response['Error']['Code'] == 'ResourceNotFoundException':
            return []
        raise


def get_execution_details(client, execution_arn: str) -> Optional[Dict]:
    """Get detailed execution information."""
    try:
        response = client.describe_task_execution(TaskExecutionArn=execution_arn)
        return response
    except ClientError:
        return None


def format_status(status: str) -> str:
    """Format status with emoji."""
    status_map = {
        'LAUNCHING': '🚀',
        'PREPARING': '⚙️',
        'TRANSFERRING': '📤',
        'VERIFYING': '🔍',
        'SUCCESS': '✅',
        'ERROR': '❌',
        'QUEUED': '⏳'
    }
    emoji = status_map.get(status, '❓')
    return f"{emoji} {status}"


def check_task_status(task: Dict) -> Dict:
    """Check status of a single task."""
    task_arn = task['task_arn']
    region = task['task_region']
    source_bucket = task['source']['bucket']
    dest_bucket = task['destination']['bucket']
    
    client = boto3.client('datasync', region_name=region, config=BOTO3_CONFIG)
    
    # Get executions
    executions = get_task_executions(client, task_arn)
    
    status_info = {
        'task_arn': task_arn,
        'source': source_bucket,
        'destination': dest_bucket,
        'region': region,
        'has_execution': False,
        'is_running': False,
        'status': 'NEVER_RUN',
        'test_mode': False,
        'execution_arn': None,
        'start_time': None,
        'bytes_transferred': None,
        'files_transferred': None
    }
    
    if not executions:
        return status_info
    
    # Get latest execution details
    latest = executions[0]
    execution_arn = latest['TaskExecutionArn']
    details = get_execution_details(client, execution_arn)
    
    if not details:
        return status_info
    
    status_info['has_execution'] = True
    status_info['execution_arn'] = execution_arn
    status_info['status'] = details.get('Status', 'UNKNOWN')
    status_info['start_time'] = details.get('StartTime')
    
    # Check if running
    running_states = ['LAUNCHING', 'PREPARING', 'TRANSFERRING', 'VERIFYING', 'QUEUED']
    status_info['is_running'] = status_info['status'] in running_states
    
    # Check for test mode (includes filter present)
    includes = details.get('Includes', [])
    status_info['test_mode'] = len(includes) > 0
    
    # Get transfer stats if available
    if 'BytesTransferred' in details:
        status_info['bytes_transferred'] = details['BytesTransferred']
    if 'FilesTransferred' in details:
        status_info['files_transferred'] = details['FilesTransferred']
    
    return status_info


def format_bytes(bytes_val: Optional[int]) -> str:
    """Format bytes to human readable."""
    if bytes_val is None:
        return "N/A"
    
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if bytes_val < 1024.0:
            return f"{bytes_val:.2f} {unit}"
        bytes_val /= 1024.0
    return f"{bytes_val:.2f} PB"


def print_task_status(status: Dict, show_header: bool = True):
    """Print task status."""
    if show_header:
        print(f"\n{'='*80}")
        print(f"Task: {status['source']} → {status['destination']} ({status['region']})")
        print(f"{'='*80}")
    
    print(f"Task ARN: {status['task_arn']}")
    
    if not status['has_execution']:
        print("Status: ⚪ NEVER_RUN")
        print("Execution ARN: N/A")
        return
    
    print(f"Execution ARN: {status['execution_arn']}")
    print(f"Status: {format_status(status['status'])}")
    print(f"Running: {'Yes' if status['is_running'] else 'No'}")
    print(f"Test Mode: {'Yes' if status['test_mode'] else 'No'}")
    
    if status['start_time']:
        print(f"Started: {status['start_time'].strftime('%Y-%m-%d %H:%M:%S UTC')}")
    
    if status['bytes_transferred'] is not None:
        print(f"Transferred: {format_bytes(status['bytes_transferred'])} ({status['files_transferred']} files)")


def check_all_tasks(registry_file: str, verbose: bool = True) -> Dict[str, Dict]:
    """Check all tasks in registry."""
    tasks = load_registry(registry_file)
    
    if not tasks:
        print("No tasks found in registry.")
        return {}
    
    # Deduplicate by task_arn (keep first occurrence)
    seen_arns = set()
    unique_tasks = []
    for task in tasks:
        task_arn = task['task_arn']
        if task_arn not in seen_arns:
            seen_arns.add(task_arn)
            unique_tasks.append(task)
    
    statuses = {}
    for task in unique_tasks:
        try:
            status = check_task_status(task)
            statuses[status['task_arn']] = status
            if verbose:
                print_task_status(status)
        except Exception as e:
            print(f"\n❌ Error checking task {task['task_arn']}: {e}")
    
    return statuses


def output_json(statuses: Dict[str, Dict]):
    """Output statuses as JSON."""
    output = []
    for status in statuses.values():
        item = {
            'task_arn': status['task_arn'],
            'execution_arn': status['execution_arn'],
            'source_bucket': status['source'],
            'destination_bucket': status['destination'],
            'region': status['region'],
            'status': status['status'],
            'is_running': status['is_running'],
            'test_mode': status['test_mode'],
            'start_time': status['start_time'].isoformat() if status['start_time'] else None,
            'bytes_transferred': status['bytes_transferred'],
            'files_transferred': status['files_transferred']
        }
        output.append(item)
    
    print(json.dumps(output, indent=2))


def output_csv(statuses: Dict[str, Dict]):
    """Output statuses as CSV."""
    if not statuses:
        return
    
    fieldnames = [
        'task_arn',
        'execution_arn',
        'source_bucket',
        'destination_bucket',
        'region',
        'status',
        'is_running',
        'test_mode',
        'start_time',
        'bytes_transferred',
        'files_transferred'
    ]
    
    writer = csv.DictWriter(sys.stdout, fieldnames=fieldnames)
    writer.writeheader()
    
    for status in statuses.values():
        row = {
            'task_arn': status['task_arn'],
            'execution_arn': status['execution_arn'] or '',
            'source_bucket': status['source'],
            'destination_bucket': status['destination'],
            'region': status['region'],
            'status': status['status'],
            'is_running': status['is_running'],
            'test_mode': status['test_mode'],
            'start_time': status['start_time'].isoformat() if status['start_time'] else '',
            'bytes_transferred': status['bytes_transferred'] or '',
            'files_transferred': status['files_transferred'] or ''
        }
        writer.writerow(row)


def monitor_tasks(registry_file: str):
    """Monitor tasks continuously until interrupted."""
    global last_known_states, monitoring
    monitoring = True
    
    print("🔄 Starting task monitor (Ctrl+C to stop)...")
    print(f"Polling every {POLL_INTERVAL} seconds\n")
    
    # Initial check
    last_known_states = check_all_tasks(registry_file, verbose=True)
    
    try:
        while monitoring:
            time.sleep(POLL_INTERVAL)
            
            current_states = check_all_tasks(registry_file, verbose=False)
            
            # Check for changes
            for task_arn, current in current_states.items():
                previous = last_known_states.get(task_arn)
                
                if not previous:
                    # New task
                    print(f"\n🆕 New task detected:")
                    print_task_status(current)
                    continue
                
                # Check for status change
                if current['status'] != previous['status']:
                    print(f"\n🔔 Status change detected:")
                    print(f"Task: {current['source']} → {current['destination']}")
                    print(f"Previous: {format_status(previous['status'])}")
                    print(f"Current: {format_status(current['status'])}")
                    
                    if current['bytes_transferred'] is not None:
                        print(f"Transferred: {format_bytes(current['bytes_transferred'])} ({current['files_transferred']} files)")
            
            last_known_states = current_states
            
    except KeyboardInterrupt:
        print("\n\n⏹️  Monitoring stopped. Final status:\n")
        for task_arn, status in last_known_states.items():
            print_task_status(status)


def signal_handler(signum, frame):
    """Handle Ctrl+C gracefully."""
    global monitoring
    monitoring = False


def main():
    import argparse
    
    parser = argparse.ArgumentParser(
        description='Check DataSync task execution status',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        '--registry',
        default=DEFAULT_REGISTRY,
        help=f'Registry file (default: {DEFAULT_REGISTRY})'
    )
    parser.add_argument(
        '--monitor',
        action='store_true',
        help='Monitor tasks continuously'
    )
    parser.add_argument(
        '--json',
        action='store_true',
        help='Output as JSON (not compatible with --monitor)'
    )
    parser.add_argument(
        '--csv',
        action='store_true',
        help='Output as CSV (not compatible with --monitor)'
    )
    
    args = parser.parse_args()
    
    # Validate arguments
    if args.monitor and (args.json or args.csv):
        print("❌ Error: --monitor cannot be used with --json or --csv")
        sys.exit(1)
    
    if args.json and args.csv:
        print("❌ Error: --json and --csv cannot be used together")
        sys.exit(1)
    
    # Set up signal handler
    signal.signal(signal.SIGINT, signal_handler)
    
    if args.monitor:
        monitor_tasks(args.registry)
    else:
        statuses = check_all_tasks(args.registry, verbose=not (args.json or args.csv))
        
        if args.json:
            output_json(statuses)
        elif args.csv:
            output_csv(statuses)


if __name__ == '__main__':
    main()
