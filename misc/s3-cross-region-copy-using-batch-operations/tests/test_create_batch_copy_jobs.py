"""Tests for create_batch_copy_jobs.py."""

import argparse
import json
import sys
import os
from unittest.mock import MagicMock, patch

import boto3
import pytest
from botocore.exceptions import ClientError
from moto import mock_aws

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import create_batch_copy_jobs as mod


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _client_error(code, msg="err"):
    return ClientError({"Error": {"Code": code, "Message": msg}}, "op")


def _make_args(**overrides):
    defaults = dict(
        source_bucket="src-bkt", source_region="us-east-1", dest_bucket=None,
        region="eu-west-1", manifest_bucket="manifest-bkt", manifest_key=None,
        manifest_keys=None, manifest_region=None, role_arn=None, account_id=None,
        report_prefix="batch-copy-reports", storage_class="STANDARD",
        description=None, priority=10, confirm=False, start=False,
        include_versions=False, profile=None,
    )
    defaults.update(overrides)
    return argparse.Namespace(**defaults)


# ---------------------------------------------------------------------------
# 1 & 2  discover_manifest_keys
# ---------------------------------------------------------------------------

@mock_aws
def test_discover_manifest_keys_found():
    s3 = boto3.client("s3", region_name="us-east-1")
    s3.create_bucket(Bucket="mbkt")
    for k in ["base-003.csv", "base-001.csv", "base-002.csv"]:
        s3.put_object(Bucket="mbkt", Key=k, Body=b"x")
    result = mod.discover_manifest_keys(s3, "mbkt", "base")
    assert result == ["base-001.csv", "base-002.csv", "base-003.csv"]


@mock_aws
def test_discover_manifest_keys_none():
    s3 = boto3.client("s3", region_name="us-east-1")
    s3.create_bucket(Bucket="mbkt")
    with pytest.raises(SystemExit):
        mod.discover_manifest_keys(s3, "mbkt", "base")


# ---------------------------------------------------------------------------
# 3 & 4  get_account_id
# ---------------------------------------------------------------------------

def test_get_account_id_explicit():
    assert mod.get_account_id(None, "111122223333") == "111122223333"


@mock_aws
def test_get_account_id_auto():
    session = boto3.Session(region_name="us-east-1")
    acct = mod.get_account_id(session, None)
    assert acct and acct.isdigit()


# ---------------------------------------------------------------------------
# 5  _check_bucket_accessible
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("scenario,expected", [
    ("exists", True),
    ("404", False),
    ("403", SystemExit),
])
@mock_aws
def test_check_bucket_accessible(scenario, expected):
    s3 = boto3.client("s3", region_name="us-east-1")
    if scenario == "exists":
        s3.create_bucket(Bucket="bkt")
        assert mod._check_bucket_accessible(s3, "bkt", "Test") is True
    elif scenario == "404":
        assert mod._check_bucket_accessible(s3, "no-such-bkt", "Test") is False
    else:
        mock_s3 = MagicMock()
        mock_s3.head_bucket.side_effect = _client_error("403")
        with pytest.raises(SystemExit):
            mod._check_bucket_accessible(mock_s3, "bkt", "Test")


# ---------------------------------------------------------------------------
# 6  ensure_bucket (exists)
# ---------------------------------------------------------------------------

@mock_aws
def test_ensure_bucket_exists():
    s3 = boto3.client("s3", region_name="us-east-1")
    s3.create_bucket(Bucket="bkt")
    mod.ensure_bucket(s3, "bkt", "us-east-1", "Test")
    # no error means no-op


# ---------------------------------------------------------------------------
# 7  ensure_bucket (creates) — parameterized by region
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("region", ["us-east-1", "eu-west-1"])
@mock_aws
def test_ensure_bucket_creates(region):
    s3 = boto3.client("s3", region_name=region)
    mod.ensure_bucket(s3, "new-bkt", region, "Test")

    # bucket exists now
    s3.head_bucket(Bucket="new-bkt")

    # encryption configured
    enc = s3.get_bucket_encryption(Bucket="new-bkt")
    rule = enc["ServerSideEncryptionConfiguration"]["Rules"][0]
    assert rule["ApplyServerSideEncryptionByDefault"]["SSEAlgorithm"] == "AES256"

    # public access block
    pab = s3.get_public_access_block(Bucket="new-bkt")["PublicAccessBlockConfiguration"]
    assert pab["BlockPublicAcls"] is True

    # policy present
    pol = json.loads(s3.get_bucket_policy(Bucket="new-bkt")["Policy"])
    assert pol["Statement"][0]["Sid"] == "DenyInsecureTransport"

    # LocationConstraint check
    loc = s3.get_bucket_location(Bucket="new-bkt")["LocationConstraint"]
    if region == "us-east-1":
        assert loc is None
    else:
        assert loc == region


# ---------------------------------------------------------------------------
# 8, 9, 10  copy_versioning
# ---------------------------------------------------------------------------

@mock_aws
def test_copy_versioning_enabled():
    s3 = boto3.client("s3", region_name="us-east-1")
    s3.create_bucket(Bucket="src")
    s3.create_bucket(Bucket="dst")
    s3.put_bucket_versioning(Bucket="src", VersioningConfiguration={"Status": "Enabled"})
    mod.copy_versioning(s3, s3, "src", "dst")
    assert s3.get_bucket_versioning(Bucket="dst").get("Status") == "Enabled"


@mock_aws
def test_copy_versioning_not_set():
    s3 = boto3.client("s3", region_name="us-east-1")
    s3.create_bucket(Bucket="src")
    s3.create_bucket(Bucket="dst")
    mod.copy_versioning(s3, s3, "src", "dst")
    assert s3.get_bucket_versioning(Bucket="dst").get("Status") is None


def test_copy_versioning_error():
    mock_s3 = MagicMock()
    mock_s3.get_bucket_versioning.side_effect = _client_error("AccessDenied")
    mod.copy_versioning(mock_s3, mock_s3, "src", "dst")  # should not raise


# ---------------------------------------------------------------------------
# 11  _validate_bucket_name_length
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("length,exits", [(63, False), (64, True)])
def test_validate_bucket_name_length(length, exits):
    name = "a" * length
    if exits:
        with pytest.raises(SystemExit):
            mod._validate_bucket_name_length(name, "test")
    else:
        mod._validate_bucket_name_length(name, "test")  # no error


# ---------------------------------------------------------------------------
# 12  create_role
# ---------------------------------------------------------------------------

@mock_aws
@patch("create_batch_copy_jobs.time.sleep")
def test_create_role(mock_sleep):
    iam = boto3.client("iam", region_name="us-east-1")
    arn, name = mod.create_role(
        iam, "123456789012", "src-bkt", "dst-bkt", "rpt-bkt", "mfst-bkt", ["m-001.csv"],
    )
    mock_sleep.assert_called_once_with(60)
    assert arn.startswith("arn:aws:iam::")
    assert name.startswith("S3BatchCopy-")

    # trust policy
    role = iam.get_role(RoleName=name)["Role"]
    trust = role["AssumeRolePolicyDocument"]
    if isinstance(trust, str):
        trust = json.loads(trust)
    assert trust["Statement"][0]["Principal"]["Service"] == "batchoperations.s3.amazonaws.com"

    # inline policy
    pol_raw = iam.get_role_policy(RoleName=name, PolicyName=f"{name}-policy")["PolicyDocument"]
    pol_doc = json.loads(pol_raw) if isinstance(pol_raw, str) else pol_raw
    resources = []
    for stmt in pol_doc["Statement"]:
        r = stmt["Resource"]
        resources.extend(r if isinstance(r, list) else [r])
        assert stmt["Condition"]["StringEquals"]["s3:ResourceAccount"] == "123456789012"
    assert any("src-bkt" in r for r in resources)
    assert any("dst-bkt" in r for r in resources)
    assert any("rpt-bkt" in r for r in resources)
    assert any("m-001.csv" in r for r in resources)


# ---------------------------------------------------------------------------
# 13  create_job — parameterized
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("include_versions,start,description", [
    (False, False, None),
    (True, True, None),
    (False, False, "My copy job"),
])
@mock_aws
def test_create_job(include_versions, start, description):
    s3 = boto3.client("s3", region_name="us-east-1")
    s3.create_bucket(Bucket="manifest-bkt")
    s3.put_object(Bucket="manifest-bkt", Key="m.csv", Body=b"data")

    mock_ctrl = MagicMock()
    mock_ctrl.create_job.return_value = {"JobId": "test-job-id"}

    args = _make_args(
        include_versions=include_versions, start=start, description=description,
        manifest_bucket="manifest-bkt",
    )
    job_id = mod.create_job(
        mock_ctrl, s3, "123456789012", args, "dst-bkt", "rpt-bkt",
        "arn:aws:iam::123456789012:role/R", "m.csv",
    )
    assert job_id == "test-job-id"

    call_kwargs = mock_ctrl.create_job.call_args[1]
    assert call_kwargs["ConfirmationRequired"] is (not start)

    fields = call_kwargs["Manifest"]["Spec"]["Fields"]
    if include_versions:
        assert "VersionId" in fields
    else:
        assert "VersionId" not in fields

    if description:
        assert call_kwargs["Description"] == description
    else:
        assert "Description" not in call_kwargs


# ---------------------------------------------------------------------------
# 14  main end-to-end
# ---------------------------------------------------------------------------

@mock_aws
@patch("create_batch_copy_jobs.time.sleep")
def test_main_end_to_end(mock_sleep):
    s3 = boto3.client("s3", region_name="us-east-1")
    s3.create_bucket(Bucket="src-bkt")
    s3.create_bucket(Bucket="manifest-bkt")
    for k in ["src-bkt-manifest-001.csv", "src-bkt-manifest-002.csv"]:
        s3.put_object(Bucket="manifest-bkt", Key=k, Body=b"data")

    with patch("create_batch_copy_jobs.parse_args") as mock_pa, \
         patch("create_batch_copy_jobs._get_session") as mock_sess:

        mock_pa.return_value = _make_args(
            source_bucket="src-bkt", source_region="us-east-1",
            region="eu-west-1", manifest_bucket="manifest-bkt",
        )

        session = MagicMock()
        mock_sess.return_value = session

        # STS
        sts_client = MagicMock()
        sts_client.get_caller_identity.return_value = {"Account": "123456789012"}

        # IAM (use real moto)
        iam_client = boto3.client("iam", region_name="us-east-1")

        # s3control mock
        s3ctrl = MagicMock()
        s3ctrl.create_job.return_value = {"JobId": "job-123"}

        def _client_factory(svc, region_name=None, config=None):
            return {
                "sts": sts_client,
                "iam": iam_client,
                "s3": s3,
                "s3control": s3ctrl,
            }[svc]

        session.client.side_effect = _client_factory

        mod.main()

        assert s3ctrl.create_job.call_count == 2
