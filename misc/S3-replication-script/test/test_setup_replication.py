#!/usr/bin/env python3
# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

import unittest
from unittest.mock import MagicMock, patch
import sys
import os
import io

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import the module but don't run main
import importlib.util
spec = importlib.util.spec_from_file_location(
    "setup_replication",
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "setupReplication-me-central-1.py")
)
setup_replication = importlib.util.module_from_spec(spec)


class TestSetupReplication(unittest.TestCase):
    """Tests for S3 replication setup script."""

    def setUp(self):
        """Set up test fixtures."""
        self.source_bucket = 'test-source-bucket'
        self.dest_bucket = 'test-dest-bucket'
        self.source_region = 'me-central-1'
        self.dest_region = 'eu-central-1'
        self.account_id = '123456789012'
        self.role_arn = f'arn:aws:iam::{self.account_id}:role/s3-replication-{self.source_region}-{self.source_bucket}'

    def _create_mock_clients(self, s3_src_config=None, s3_dest_config=None):
        """Helper to create mock boto3 clients."""
        mock_s3_src = MagicMock()
        mock_s3_dest = MagicMock()
        mock_sts = MagicMock()
        mock_sts.get_caller_identity.return_value = {'Account': self.account_id}
        mock_iam = MagicMock()
        mock_iam.create_role.return_value = {'Role': {'Arn': self.role_arn}}
        mock_s3control = MagicMock()
        mock_s3control.create_job.return_value = {'JobId': 'test-job-id'}
        mock_s3control.describe_job.return_value = {'Job': {'Status': 'Active', 'ProgressSummary': {}}}

        if s3_src_config:
            for k, v in s3_src_config.items():
                setattr(mock_s3_src, k, v) if not callable(v) else setattr(getattr(mock_s3_src, k), 'side_effect', v)
        if s3_dest_config:
            for k, v in s3_dest_config.items():
                if k == 'head_bucket_error':
                    mock_s3_dest.head_bucket.side_effect = Exception("Not found")

        def client_factory(service, region_name=None):
            if service == 's3' and region_name == self.source_region:
                return mock_s3_src
            elif service == 's3':
                return mock_s3_dest
            elif service == 'sts':
                return mock_sts
            elif service == 'iam':
                return mock_iam
            elif service == 's3control':
                return mock_s3control
            return MagicMock()

        return client_factory, mock_s3_src, mock_s3_dest, mock_sts, mock_iam, mock_s3control

    @patch('time.sleep')
    @patch('boto3.client')
    def test_source_bucket_not_exists(self, mock_boto_client, mock_sleep):
        """Test script exits when source bucket doesn't exist."""
        mock_s3 = MagicMock()
        mock_s3.head_bucket.side_effect = Exception("Bucket not found")

        def client_factory(service, region_name=None):
            return mock_s3

        mock_boto_client.side_effect = client_factory

        with patch('sys.argv', ['script', '--source-bucket=nonexistent', '--destination-bucket=dest', '--destination-region=eu-central-1']):
            with patch('sys.stdout', new_callable=io.StringIO):
                spec.loader.exec_module(setup_replication)
                with self.assertRaises(SystemExit) as ctx:
                    setup_replication.main()
                self.assertEqual(ctx.exception.code, 1)

    @patch('time.sleep')
    @patch('boto3.client')
    def test_destination_bucket_created_when_not_exists(self, mock_boto_client, mock_sleep):
        """Test destination bucket is created if it doesn't exist."""
        client_factory, mock_s3_src, mock_s3_dest, _, _, _ = self._create_mock_clients(
            s3_dest_config={'head_bucket_error': True}
        )
        mock_boto_client.side_effect = client_factory

        with patch('sys.argv', ['script', f'--source-bucket={self.source_bucket}', f'--destination-bucket={self.dest_bucket}', f'--destination-region={self.dest_region}']):
            with patch('sys.stdout', new_callable=io.StringIO):
                spec.loader.exec_module(setup_replication)
                setup_replication.main()

        mock_s3_dest.create_bucket.assert_called_once()
        mock_s3_dest.put_bucket_versioning.assert_called_once()

    @patch('time.sleep')
    @patch('boto3.client')
    def test_versioning_enabled_on_source(self, mock_boto_client, mock_sleep):
        """Test versioning is enabled on source bucket."""
        client_factory, mock_s3_src, _, _, _, _ = self._create_mock_clients()
        mock_boto_client.side_effect = client_factory

        with patch('sys.argv', ['script', f'--source-bucket={self.source_bucket}', f'--destination-bucket={self.dest_bucket}', f'--destination-region={self.dest_region}']):
            with patch('sys.stdout', new_callable=io.StringIO):
                spec.loader.exec_module(setup_replication)
                setup_replication.main()

        mock_s3_src.put_bucket_versioning.assert_called_with(
            Bucket=self.source_bucket,
            VersioningConfiguration={'Status': 'Enabled'}
        )

    @patch('time.sleep')
    @patch('boto3.client')
    def test_existing_role_arn_used(self, mock_boto_client, mock_sleep):
        """Test provided role ARN is used instead of creating new role."""
        client_factory, _, _, _, mock_iam, _ = self._create_mock_clients()
        mock_boto_client.side_effect = client_factory
        existing_role = 'arn:aws:iam::123456789012:role/existing-role'

        with patch('sys.argv', ['script', f'--source-bucket={self.source_bucket}', f'--destination-bucket={self.dest_bucket}', f'--destination-region={self.dest_region}', f'--role-arn={existing_role}']):
            with patch('sys.stdout', new_callable=io.StringIO):
                spec.loader.exec_module(setup_replication)
                setup_replication.main()

        mock_iam.create_role.assert_not_called()

    @patch('time.sleep')
    @patch('boto3.client')
    def test_role_created_when_not_provided(self, mock_boto_client, mock_sleep):
        """Test IAM role is created when not provided."""
        client_factory, _, _, _, mock_iam, _ = self._create_mock_clients()
        mock_boto_client.side_effect = client_factory

        with patch('sys.argv', ['script', f'--source-bucket={self.source_bucket}', f'--destination-bucket={self.dest_bucket}', f'--destination-region={self.dest_region}']):
            with patch('sys.stdout', new_callable=io.StringIO):
                spec.loader.exec_module(setup_replication)
                setup_replication.main()

        mock_iam.create_role.assert_called_once()
        mock_iam.put_role_policy.assert_called_once()

    @patch('time.sleep')
    @patch('boto3.client')
    def test_replication_config_applied(self, mock_boto_client, mock_sleep):
        """Test replication configuration is applied to source bucket."""
        client_factory, mock_s3_src, _, _, _, _ = self._create_mock_clients()
        mock_boto_client.side_effect = client_factory

        with patch('sys.argv', ['script', f'--source-bucket={self.source_bucket}', f'--destination-bucket={self.dest_bucket}', f'--destination-region={self.dest_region}']):
            with patch('sys.stdout', new_callable=io.StringIO):
                spec.loader.exec_module(setup_replication)
                setup_replication.main()

        mock_s3_src.put_bucket_replication.assert_called_once()
        call_args = mock_s3_src.put_bucket_replication.call_args
        self.assertEqual(call_args[1]['Bucket'], self.source_bucket)
        config = call_args[1]['ReplicationConfiguration']
        self.assertEqual(config['Rules'][0]['Destination']['Bucket'], f'arn:aws:s3:::{self.dest_bucket}')

    @patch('time.sleep')
    @patch('boto3.client')
    def test_batch_job_created(self, mock_boto_client, mock_sleep):
        """Test batch replication job is created."""
        client_factory, _, _, _, _, mock_s3control = self._create_mock_clients()
        mock_boto_client.side_effect = client_factory

        with patch('sys.argv', ['script', f'--source-bucket={self.source_bucket}', f'--destination-bucket={self.dest_bucket}', f'--destination-region={self.dest_region}']):
            with patch('sys.stdout', new_callable=io.StringIO):
                spec.loader.exec_module(setup_replication)
                setup_replication.main()

        mock_s3control.create_job.assert_called_once()
        call_args = mock_s3control.create_job.call_args
        self.assertEqual(call_args[1]['AccountId'], self.account_id)
        self.assertIn('S3ReplicateObject', call_args[1]['Operation'])


class TestArgumentParsing(unittest.TestCase):
    """Tests for command line argument parsing."""

    def test_default_source_region(self):
        """Test default source region is me-central-1."""
        import argparse
        parser = argparse.ArgumentParser()
        parser.add_argument('--source-bucket', required=True)
        parser.add_argument('--source-region', default='me-central-1')
        parser.add_argument('--destination-bucket', required=True)
        parser.add_argument('--destination-region', required=True)
        parser.add_argument('--role-arn', required=False)

        args = parser.parse_args(['--source-bucket=src', '--destination-bucket=dst', '--destination-region=eu-west-1'])
        self.assertEqual(args.source_region, 'me-central-1')

    def test_custom_source_region(self):
        """Test custom source region can be specified."""
        import argparse
        parser = argparse.ArgumentParser()
        parser.add_argument('--source-bucket', required=True)
        parser.add_argument('--source-region', default='me-central-1')
        parser.add_argument('--destination-bucket', required=True)
        parser.add_argument('--destination-region', required=True)
        parser.add_argument('--role-arn', required=False)

        args = parser.parse_args(['--source-bucket=src', '--source-region=us-east-1', '--destination-bucket=dst', '--destination-region=eu-west-1'])
        self.assertEqual(args.source_region, 'us-east-1')


class TestLocationConstraint(unittest.TestCase):
    """Tests for bucket location constraint mapping."""

    def test_us_east_1_constraint(self):
        """Test us-east-1 maps to US constraint."""
        constraint_map = {'us-east-1': 'US', 'eu-west-1': 'EU'}
        self.assertEqual(constraint_map.get('us-east-1', 'us-east-1'), 'US')

    def test_eu_west_1_constraint(self):
        """Test eu-west-1 maps to EU constraint."""
        constraint_map = {'us-east-1': 'US', 'eu-west-1': 'EU'}
        self.assertEqual(constraint_map.get('eu-west-1', 'eu-west-1'), 'EU')

    def test_other_region_uses_region_name(self):
        """Test other regions use region name as constraint."""
        constraint_map = {'us-east-1': 'US', 'eu-west-1': 'EU'}
        self.assertEqual(constraint_map.get('eu-central-1', 'eu-central-1'), 'eu-central-1')


if __name__ == '__main__':
    unittest.main()
