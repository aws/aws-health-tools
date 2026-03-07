# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Tests for KMS key detection and IAM permission building."""

import pytest
from botocore.exceptions import ClientError
from unittest.mock import MagicMock, patch

from s3_batch_replication.aws.s3 import get_bucket_kms_key
from s3_batch_replication.commands.setup_iam_role import _build_permissions


def _client_error(code: str) -> ClientError:
    return ClientError({"Error": {"Code": code, "Message": code}}, "GetBucketEncryption")


def _mock_encryption_response(algorithm: str, key_id: str | None = None) -> dict:
    rule = {"ApplyServerSideEncryptionByDefault": {"SSEAlgorithm": algorithm}}
    if key_id:
        rule["ApplyServerSideEncryptionByDefault"]["KMSMasterKeyID"] = key_id
    return {"ServerSideEncryptionConfiguration": {"Rules": [rule]}}


# --- get_bucket_kms_key ---

class TestGetBucketKmsKey:
    def test_customer_managed_key_returned(self, mocker):
        key_arn = "arn:aws:kms:us-east-1:123456789012:key/my-key"
        mocker.patch("s3_batch_replication.aws.s3.client").return_value.get_bucket_encryption.return_value = (
            _mock_encryption_response("aws:kms", key_arn)
        )
        assert get_bucket_kms_key("my-bucket") == key_arn

    def test_aws_managed_s3_key_returned(self, mocker):
        """aws/s3 key should be returned so SseKmsEncryptedObjects gets set."""
        key_arn = "arn:aws:kms:us-east-1:123456789012:alias/aws/s3"
        mocker.patch("s3_batch_replication.aws.s3.client").return_value.get_bucket_encryption.return_value = (
            _mock_encryption_response("aws:kms", key_arn)
        )
        assert get_bucket_kms_key("my-bucket") == key_arn

    def test_sse_s3_returns_none(self, mocker):
        mocker.patch("s3_batch_replication.aws.s3.client").return_value.get_bucket_encryption.return_value = (
            _mock_encryption_response("AES256")
        )
        assert get_bucket_kms_key("my-bucket") is None

    def test_no_encryption_config_returns_none(self, mocker):
        mocker.patch("s3_batch_replication.aws.s3.client").return_value.get_bucket_encryption.side_effect = (
            _client_error("ServerSideEncryptionConfigurationNotFoundError")
        )
        assert get_bucket_kms_key("my-bucket") is None

    def test_no_such_bucket_raises(self, mocker):
        mocker.patch("s3_batch_replication.aws.s3.client").return_value.get_bucket_encryption.side_effect = (
            _client_error("NoSuchBucket")
        )
        with pytest.raises(RuntimeError, match="does not exist"):
            get_bucket_kms_key("my-bucket")

    def test_access_denied_raises(self, mocker):
        mocker.patch("s3_batch_replication.aws.s3.client").return_value.get_bucket_encryption.side_effect = (
            _client_error("AccessDenied")
        )
        with pytest.raises(RuntimeError, match="Access denied"):
            get_bucket_kms_key("my-bucket")


# --- _build_permissions ---

class TestBuildPermissions:
    def test_customer_kms_key_adds_iam_grants(self):
        source_key = "arn:aws:kms:us-east-1:123:key/source-key"
        dest_key = "arn:aws:kms:eu-west-1:123:key/dest-key"
        policy = _build_permissions("src", "dst", source_key, dest_key)
        actions = [a for s in policy["Statement"] for a in ([s["Action"]] if isinstance(s["Action"], str) else s["Action"])]
        assert "kms:Decrypt" in actions
        assert "kms:Encrypt" in actions
        assert "kms:GenerateDataKey" in actions

    def test_customer_kms_key_scoped_to_region(self):
        source_key = "arn:aws:kms:us-east-1:123:key/source-key"
        dest_key = "arn:aws:kms:eu-west-1:123:key/dest-key"
        policy = _build_permissions("src", "dst", source_key, dest_key)
        decrypt = next(s for s in policy["Statement"] if s.get("Action") == "kms:Decrypt")
        encrypt = next(s for s in policy["Statement"] if "kms:Encrypt" in s.get("Action", []))
        assert decrypt["Condition"] == {"StringEquals": {"kms:ViaService": "s3.us-east-1.amazonaws.com"}}
        assert encrypt["Condition"] == {"StringEquals": {"kms:ViaService": "s3.eu-west-1.amazonaws.com"}}

    def test_aws_managed_key_skips_iam_grants(self):
        aws_key = "arn:aws:kms:us-east-1:123:alias/aws/s3"
        policy = _build_permissions("src", "dst", aws_key, aws_key)
        actions = [a for s in policy["Statement"] for a in ([s["Action"]] if isinstance(s["Action"], str) else s["Action"])]
        assert "kms:Decrypt" not in actions
        assert "kms:Encrypt" not in actions

    def test_no_kms_no_grants(self):
        policy = _build_permissions("src", "dst", None, None)
        actions = [a for s in policy["Statement"] for a in ([s["Action"]] if isinstance(s["Action"], str) else s["Action"])]
        assert "kms:Decrypt" not in actions
        assert "kms:Encrypt" not in actions

    def test_report_bucket_adds_put_object(self):
        policy = _build_permissions("src", "dst", None, None, report_bucket="my-reports")
        actions = [a for s in policy["Statement"] for a in ([s["Action"]] if isinstance(s["Action"], str) else s["Action"])]
        assert "s3:PutObject" in actions

    def test_manifest_bucket_adds_get_object(self):
        policy = _build_permissions("src", "dst", None, None, manifest_bucket="manifest-bucket")
        resources = [s["Resource"] for s in policy["Statement"]]
        assert any("manifest-bucket" in r for r in resources)
