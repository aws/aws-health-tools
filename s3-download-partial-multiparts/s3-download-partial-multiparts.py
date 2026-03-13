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

"""
Script to download S3 multi-part objects with potentially missing parts.

This tool downloads each part individually using the partNumber query parameter
and handles missing/corrupted parts by skipping them and recording the missing byte ranges.

Usage:
    python download_partial_multipart.py --bucket BUCKET_NAME --key OBJECT_KEY --output OUTPUT_FILE

The script will use the AWS_PROFILE environment variable if set.
"""

import argparse
import boto3
import os
import sys
from typing import List, Tuple
from botocore.exceptions import ClientError
from botocore.config import Config


class PartInfo:
    """Information about a downloaded part."""
    def __init__(self, part_number: int, start_byte: int, end_byte: int, size: int):
        self.part_number = part_number
        self.start_byte = start_byte
        self.end_byte = end_byte
        self.size = size


def read_missing_ranges(missing_ranges_path: str) -> List[Tuple[int, int]]:
    """
    Read the .MISSINGRANGES file and parse byte ranges.
    Returns: List of (start_byte, end_byte) tuples
    """
    missing_ranges = []
    if os.path.exists(missing_ranges_path):
        with open(missing_ranges_path, 'r') as f:
            for line in f:
                line = line.strip()
                if line and '-' in line:
                    try:
                        start, end = map(int, line.split('-'))
                        missing_ranges.append((start, end))
                    except ValueError:
                        # Skip malformed lines
                        pass
    return missing_ranges


def is_retry_mode(output_path: str) -> bool:
    """
    Check if we're in retry mode (.PARTIAL file and .MISSINGRANGES both exist).
    """
    partial_path = output_path + ".PARTIAL"
    missing_ranges_path = output_path + ".MISSINGRANGES"
    return os.path.exists(partial_path) and os.path.exists(missing_ranges_path)


def get_part_count(s3_client, bucket: str, key: str) -> Tuple[int, int]:
    """
    Get the total number of parts by requesting metadata for part 1.
    Returns: (total_parts_count, total_object_size)
    """
    try:
        # Use HEAD request to get metadata about the multipart object without downloading data
        response = s3_client.head_object(
            Bucket=bucket,
            Key=key,
            PartNumber=1
        )

        # Read the response headers
        parts_count = int(response['ResponseMetadata']['HTTPHeaders'].get('x-amz-mp-parts-count', 0))

        if parts_count == 0:
            print(f"✗ Object does not appear to be a multi-part object", file=sys.stderr)
            sys.exit(1)

        # Get the total object size from Content-Range header
        # Format: "bytes START-END/TOTAL"
        content_range = response['ResponseMetadata']['HTTPHeaders'].get('content-range', '')
        total_size = 0

        if content_range:
            # Parse "bytes 0-5242879/75497472" to get the total (75497472)
            total_size = int(content_range.split('/')[1])

        return parts_count, total_size

    except ClientError as e:
        if e.response['Error']['Code'] == 'NoSuchKey':
            print(f"✗ Object not found: s3://{bucket}/{key}", file=sys.stderr)
            sys.exit(1)
        else:
            raise


def download_part(s3_client, bucket: str, key: str, part_number: int,
                 output_file, verbose: bool = True) -> Tuple[bool, PartInfo]:
    """
    Download a single part using partNumber query parameter.
    Returns: (success: bool, part_info: PartInfo or None)
    """
    if verbose:
        print(f"Downloading part {part_number}...", end=' ', flush=True)

    try:
        response = s3_client.get_object(
            Bucket=bucket,
            Key=key,
            PartNumber=part_number
        )

        # Get part information from headers
        content_length = int(response['ContentLength'])
        content_range = response['ResponseMetadata']['HTTPHeaders'].get('content-range', '')

        # Parse Content-Range header: "bytes START-END/TOTAL"
        if content_range:
            range_part = content_range.split()[1]  # Get "START-END/TOTAL"
            byte_range = range_part.split('/')[0]  # Get "START-END"
            start_byte, end_byte = map(int, byte_range.split('-'))
        else:
            # Fallback if no Content-Range
            start_byte = 0
            end_byte = content_length - 1

        # Read the data
        data = response['Body'].read()

        # Verify we got the expected amount of data
        if len(data) != content_length:
            if verbose:
                print(f"✗ Size mismatch (expected {content_length}, got {len(data)})")
            return False, None

        # Seek to the correct position in the output file
        output_file.seek(start_byte)
        output_file.write(data)

        if verbose:
            size_mb = content_length / (1024 * 1024)
            print(f"✓ (bytes {start_byte}-{end_byte}, {size_mb:.2f} MB)")

        part_info = PartInfo(part_number, start_byte, end_byte, content_length)
        return True, part_info

    except ClientError as e:
        error_code = e.response['Error']['Code']
        status_code = e.response['ResponseMetadata']['HTTPStatusCode']

        if error_code == 'InvalidPartNumber' or status_code == 416:
            # Part doesn't exist
            if verbose:
                print(f"✗ Part does not exist")
            return False, None

        if verbose:
            print(f"✗ Error {status_code} ({error_code})")

        return False, None

    except Exception as e:
        if verbose:
            print(f"✗ Unexpected error: {e}")

        return False, None


def download_multipart_object(bucket: str, key: str, output_path: str,
                              profile: str = None, region: str = None, verbose: bool = True):
    """
    Download a multi-part S3 object, handling missing parts gracefully.
    """
    # Check if the final file already exists (meaning download is already complete)
    if os.path.exists(output_path) and not os.path.exists(output_path + ".MISSINGRANGES"):
        if verbose:
            print(f"✓ File already exists and is complete: {output_path}")
            print(f"  (No .MISSINGRANGES or .PARTIAL file found)")
        return True

    # Create boto3 session with profile if specified
    if profile:
        session = boto3.Session(profile_name=profile)
        if verbose:
            print(f"Using AWS profile: {profile}\n")
    else:
        session = boto3.Session()
        if verbose:
            print("Using default AWS credentials\n")

    # Create S3 client with region if specified
    if region:
        s3_client = session.client('s3', region_name=region)
        if verbose:
            print(f"Using region: {region}\n")
    else:
        s3_client = session.client('s3')

    if verbose:
        print(f"Analyzing object: s3://{bucket}/{key}")

    # Get the total number of parts and object size
    parts_count, total_size = get_part_count(s3_client, bucket, key)

    if verbose:
        print(f"Found {parts_count} parts, total size: {total_size / (1024*1024):.2f} MB\n")

    # Work with .PARTIAL file during download
    partial_path = output_path + ".PARTIAL"
    missing_ranges_path = output_path + ".MISSINGRANGES"
    retry_mode = is_retry_mode(output_path)
    parts_to_retry = set()  # Part numbers to retry

    if retry_mode:
        # Read existing missing ranges and determine which parts to retry
        existing_missing_ranges = read_missing_ranges(missing_ranges_path)
        if verbose:
            print(f"RETRY MODE: Found {len(existing_missing_ranges)} missing range(s) from previous download\n")

        # We need to map byte ranges to part numbers by downloading each part's metadata
        # For simplicity, we'll just try all parts and check if they match missing ranges
        # Store the missing ranges for comparison
        missing_range_set = set(existing_missing_ranges)
    else:
        missing_range_set = set()

    # Track results
    missing_ranges = []
    successful_parts = []
    failed_parts = []

    try:
        # Open file in appropriate mode (work with .PARTIAL file)
        file_mode = 'r+b' if retry_mode else 'wb'
        with open(partial_path, file_mode) as output_file:
            if not retry_mode and total_size > 0:
                if verbose:
                    print(f"Pre-allocating file to {total_size / (1024*1024):.2f} MB...\n")
                # Seek to the last byte position and write a null byte
                output_file.seek(total_size - 1)
                output_file.write(b'\0')
                output_file.seek(0)

            # Download each part
            for part_num in range(1, parts_count + 1):
                # In retry mode, first check if this part needs to be retried
                skip_part = False
                if retry_mode:
                    # Try to get metadata for this part to see its byte range
                    # Use HEAD request instead of GET to avoid downloading the body
                    try:
                        response = s3_client.head_object(
                            Bucket=bucket,
                            Key=key,
                            PartNumber=part_num
                        )
                        content_range = response['ResponseMetadata']['HTTPHeaders'].get('content-range', '')
                        if content_range:
                            range_part = content_range.split()[1]
                            byte_range = range_part.split('/')[0]
                            start, end = map(int, byte_range.split('-'))

                            # Check if this part's range is in the missing ranges
                            if (start, end) not in missing_range_set:
                                skip_part = True
                                if verbose:
                                    print(f"Skipping part {part_num} (already downloaded)... ✓")
                    except:
                        # If we can't get metadata, try to download anyway
                        pass

                if skip_part:
                    continue

                success, part_info = download_part(s3_client, bucket, key, part_num,
                                                   output_file, verbose)

                if success and part_info:
                    successful_parts.append(part_info)
                else:
                    failed_parts.append(part_num)
                    # We'll try to get the byte range for this failed part later

        # For failed parts, try to get their byte ranges
        # We'll try briefly, but if it fails again, just use part number
        if failed_parts and verbose:
            print(f"\nAttempting to get byte ranges for {len(failed_parts)} failed part(s)...")

        for part_num in failed_parts:
            try:
                # Configure a shorter timeout for this metadata request (10 seconds)
                config = Config(
                    connect_timeout=10,
                    read_timeout=10
                )
                metadata_client = session.client('s3', config=config, region_name=region)

                # Use HEAD request to get just the headers without downloading body
                response = metadata_client.head_object(
                    Bucket=bucket,
                    Key=key,
                    PartNumber=part_num
                )

                content_range = response['ResponseMetadata']['HTTPHeaders'].get('content-range', '')
                if content_range:
                    range_part = content_range.split()[1]
                    byte_range = range_part.split('/')[0]
                    missing_ranges.append(byte_range)
                    if verbose:
                        print(f"  Part {part_num}: {byte_range}")
                else:
                    missing_ranges.append(f"part{part_num}-unknown-range")
                    if verbose:
                        print(f"  Part {part_num}: unknown-range")

            except Exception as e:
                # If we still can't get it, just record the part number
                missing_ranges.append(f"part{part_num}-unknown-range")
                if verbose:
                    print(f"  Part {part_num}: unknown-range (could not retrieve: {type(e).__name__})")

        if verbose:
            print(f"\n{'='*60}")
            if retry_mode:
                print(f"Retry complete:")
            else:
                print(f"Download complete:")
            print(f"  Output file: {partial_path}")
            print(f"  Total size: {total_size / (1024*1024):.2f} MB")
            if retry_mode:
                print(f"  Parts retried: {len(successful_parts)}")
                print(f"  Still failed: {len(failed_parts)}")
            else:
                print(f"  Successful parts: {len(successful_parts)}/{parts_count}")
                print(f"  Failed parts: {len(failed_parts)}/{parts_count}")

        # Handle missing ranges file
        if missing_ranges:
            # Still have missing parts - update the file
            with open(missing_ranges_path, 'w') as f:
                f.write('\n'.join(missing_ranges) + '\n')

            if verbose:
                print(f"  Missing ranges written to: {missing_ranges_path}")
                print(f"\nMissing byte ranges:")
                for range_str in missing_ranges:
                    print(f"    {range_str}")
                print(f"\n⚠️  File remains as {partial_path} until all parts are complete")
        else:
            # No missing parts - rename .PARTIAL to final name
            if os.path.exists(missing_ranges_path):
                # Delete the .MISSINGRANGES file since all parts are now complete
                os.remove(missing_ranges_path)
                if verbose:
                    print(f"  ✓ All parts now complete! Removed {missing_ranges_path}")
            elif verbose:
                print(f"  ✓ All parts downloaded successfully!")

            # Rename .PARTIAL to final filename
            os.rename(partial_path, output_path)
            if verbose:
                print(f"  ✓ Renamed {partial_path} → {output_path}")
                print(f"\n✓ Download complete: {output_path}")

        return True

    except Exception as e:
        print(f"\n✗ Error during download: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return False


def main():
    parser = argparse.ArgumentParser(
        description='Download S3 multi-part objects with potentially missing parts',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Download with AWS_PROFILE environment variable
  export AWS_PROFILE=my-profile
  python download_partial_multipart.py --bucket my-bucket --key data/file.dat --output ./file.dat

  # Download with explicit profile
  python download_partial_multipart.py --bucket my-bucket --key data/file.dat --output ./file.dat --profile my-profile

  # Quiet mode
  python download_partial_multipart.py --bucket my-bucket --key data/file.dat --output ./file.dat --quiet
        """
    )
    parser.add_argument(
        '--bucket',
        required=True,
        help='S3 bucket name'
    )
    parser.add_argument(
        '--key',
        required=True,
        help='S3 object key (path)'
    )
    parser.add_argument(
        '--output',
        required=True,
        help='Output file path'
    )
    parser.add_argument(
        '--profile',
        help='AWS profile name (defaults to AWS_PROFILE env var or default credentials)'
    )
    parser.add_argument(
        '--region',
        help='AWS region name (e.g., us-east-1, me-central-1). Required if bucket is in a different region.'
    )
    parser.add_argument(
        '--quiet', '-q',
        action='store_true',
        help='Suppress progress output'
    )

    args = parser.parse_args()

    # Use profile from args, or fall back to AWS_PROFILE env var
    profile = args.profile or os.environ.get('AWS_PROFILE')

    success = download_multipart_object(
        args.bucket,
        args.key,
        args.output,
        profile,
        args.region,
        verbose=not args.quiet
    )

    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
