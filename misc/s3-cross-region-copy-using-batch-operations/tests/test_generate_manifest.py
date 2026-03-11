"""Tests for generate_manifest.py."""

import csv
import json
import os
import sys

import boto3
import pytest
from moto import mock_aws
from unittest.mock import MagicMock, patch
from urllib.parse import quote

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from generate_manifest import (
    SIZE_THRESHOLD,
    _check_bucket_accessible,
    generate_manifests,
    upload_manifests,
    validate_inputs,
)


# ---------------------------------------------------------------------------
# _check_bucket_accessible
# ---------------------------------------------------------------------------

@mock_aws
def test_check_bucket_accessible_success():
    s3 = boto3.client("s3", region_name="us-east-1")
    s3.create_bucket(Bucket="test-bucket")
    assert _check_bucket_accessible(s3, "test-bucket", "Test") is True


@pytest.mark.parametrize("error_code,expected", [
    ("403", SystemExit),
    ("404", False),
])
@mock_aws
def test_check_bucket_accessible_errors(error_code, expected):
    from botocore.exceptions import ClientError

    s3 = boto3.client("s3", region_name="us-east-1")
    # Patch head_bucket to raise the desired ClientError
    original = s3.head_bucket

    def fake_head_bucket(**kwargs):
        raise ClientError({"Error": {"Code": error_code, "Message": "err"}}, "HeadBucket")

    s3.head_bucket = fake_head_bucket
    if expected is SystemExit:
        with pytest.raises(SystemExit):
            _check_bucket_accessible(s3, "no-bucket", "Test")
    else:
        assert _check_bucket_accessible(s3, "no-bucket", "Test") is expected


# ---------------------------------------------------------------------------
# validate_inputs
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("scenario", ["missing", "forbidden"])
@mock_aws
def test_validate_inputs_source_inaccessible(make_args, scenario):
    s3_source = boto3.client("s3", region_name="us-east-1")
    s3_manifest = boto3.client("s3", region_name="us-east-1")
    args = make_args()

    code = "403" if scenario == "forbidden" else "404"
    from botocore.exceptions import ClientError

    def fake_head(**kwargs):
        raise ClientError({"Error": {"Code": code, "Message": "err"}}, "HeadBucket")

    s3_source.head_bucket = fake_head
    with pytest.raises(SystemExit):
        validate_inputs(args, s3_source, s3_manifest)


@mock_aws
def test_validate_inputs_both_exist(make_args, populate_bucket):
    s3 = boto3.client("s3", region_name="us-east-1")
    populate_bucket(s3, "source-bucket", [], region="us-east-1")
    populate_bucket(s3, "manifest-bucket", [], region="us-east-1")
    args = make_args()
    # Should not raise
    validate_inputs(args, s3, s3)


@pytest.mark.parametrize("region,expect_constraint", [
    ("us-east-1", False),
    ("eu-west-1", True),
])
@mock_aws
def test_validate_inputs_creates_manifest_bucket(make_args, populate_bucket, region, expect_constraint):
    s3_source = boto3.client("s3", region_name="us-east-1")
    s3_manifest = boto3.client("s3", region_name=region)
    populate_bucket(s3_source, "source-bucket", [], region="us-east-1")
    args = make_args(manifest_region=region)

    validate_inputs(args, s3_source, s3_manifest)

    # Bucket was created
    s3_manifest.head_bucket(Bucket="manifest-bucket")

    # Encryption
    enc = s3_manifest.get_bucket_encryption(Bucket="manifest-bucket")
    rule = enc["ServerSideEncryptionConfiguration"]["Rules"][0]
    assert rule["ApplyServerSideEncryptionByDefault"]["SSEAlgorithm"] == "AES256"

    # Public access block
    pab = s3_manifest.get_public_access_block(Bucket="manifest-bucket")
    cfg = pab["PublicAccessBlockConfiguration"]
    assert cfg["BlockPublicAcls"] is True
    assert cfg["BlockPublicPolicy"] is True

    # Policy
    policy = json.loads(s3_manifest.get_bucket_policy(Bucket="manifest-bucket")["Policy"])
    assert policy["Statement"][0]["Sid"] == "DenyInsecureTransport"


# ---------------------------------------------------------------------------
# generate_manifests — mock-based tests for size control
# ---------------------------------------------------------------------------

def _mock_s3_paginator(objects, paginator_name="list_objects_v2", content_key="Contents"):
    """Build a MagicMock s3 client whose paginator returns the given objects."""
    mock_s3 = MagicMock()
    mock_paginator = MagicMock()
    mock_s3.get_paginator.return_value = mock_paginator
    mock_paginator.paginate.return_value = [{content_key: objects}] if objects else [{}]
    return mock_s3


def test_generate_manifests_standard_only(tmp_path, make_args):
    objects = [{"Key": f"obj{i}.txt", "Size": 100} for i in range(3)]
    mock_s3 = _mock_s3_paginator(objects)
    args = make_args()

    num_parts, std, large = generate_manifests(args, mock_s3, str(tmp_path))

    assert (num_parts, std, large) == (1, 3, 0)
    content = (tmp_path / "part-001.csv").read_text()
    assert content.count("\n") == 3
    assert (tmp_path / "large.csv").read_text() == ""


def test_generate_manifests_large_only(tmp_path, make_args):
    objects = [
        {"Key": "big1.dat", "Size": SIZE_THRESHOLD + 1},
        {"Key": "big2.dat", "Size": SIZE_THRESHOLD + 999},
    ]
    mock_s3 = _mock_s3_paginator(objects)
    args = make_args()

    num_parts, std, large = generate_manifests(args, mock_s3, str(tmp_path))

    assert (std, large) == (0, 2)
    large_content = (tmp_path / "large.csv").read_text()
    assert "big1.dat" in large_content
    assert "big2.dat" in large_content
    assert (tmp_path / "part-001.csv").read_text() == ""


def test_generate_manifests_mixed(tmp_path, make_args):
    objects = [
        {"Key": "small.txt", "Size": 10},
        {"Key": "huge.bin", "Size": SIZE_THRESHOLD + 1},
        {"Key": "medium.txt", "Size": SIZE_THRESHOLD},
    ]
    mock_s3 = _mock_s3_paginator(objects)
    args = make_args()

    num_parts, std, large = generate_manifests(args, mock_s3, str(tmp_path))

    assert (std, large) == (2, 1)
    std_content = (tmp_path / "part-001.csv").read_text()
    assert "small.txt" in std_content
    assert "medium.txt" in std_content
    large_content = (tmp_path / "large.csv").read_text()
    assert "huge.bin" in large_content


def test_generate_manifests_with_versions(tmp_path, make_args):
    versions = [
        {"Key": "a.txt", "Size": 100, "VersionId": "v1"},
        {"Key": "a.txt", "Size": 200, "VersionId": "v2"},
    ]
    mock_s3 = _mock_s3_paginator(versions, paginator_name="list_object_versions", content_key="Versions")
    args = make_args(include_versions=True)

    num_parts, std, large = generate_manifests(args, mock_s3, str(tmp_path))

    assert std == 2
    lines = (tmp_path / "part-001.csv").read_text().strip().split("\n")
    for line in lines:
        cols = line.split(",")
        assert len(cols) == 3  # bucket, key, version_id
    assert "v1" in lines[0]
    assert "v2" in lines[1]


def test_generate_manifests_with_prefix(tmp_path, make_args):
    objects = [{"Key": "data/file1.txt", "Size": 10}]
    mock_s3 = _mock_s3_paginator(objects)
    args = make_args(prefix="data/")

    generate_manifests(args, mock_s3, str(tmp_path))

    # Verify paginator was called with Prefix
    mock_s3.get_paginator.return_value.paginate.assert_called_once_with(
        Bucket="source-bucket", Prefix="data/"
    )


def test_generate_manifests_empty_bucket(tmp_path, make_args):
    mock_s3 = _mock_s3_paginator([])
    args = make_args()

    num_parts, std, large = generate_manifests(args, mock_s3, str(tmp_path))

    assert (num_parts, std, large) == (1, 0, 0)


@pytest.mark.parametrize("key,expected_encoded", [
    ("hello world.txt", quote("hello world.txt", safe="")),
    ("path/to/file.txt", quote("path/to/file.txt", safe="")),
    ("données/café.txt", quote("données/café.txt", safe="")),
    ("a+b=c&d.txt", quote("a+b=c&d.txt", safe="")),
])
def test_generate_manifests_special_chars(tmp_path, make_args, key, expected_encoded):
    objects = [{"Key": key, "Size": 10}]
    mock_s3 = _mock_s3_paginator(objects)
    args = make_args()

    generate_manifests(args, mock_s3, str(tmp_path))

    content = (tmp_path / "part-001.csv").read_text().strip()
    assert expected_encoded in content


# ---------------------------------------------------------------------------
# upload_manifests
# ---------------------------------------------------------------------------

@mock_aws
def test_upload_manifests_standard_and_large(tmp_path, make_args):
    s3 = boto3.client("s3", region_name="us-east-1")
    s3.create_bucket(Bucket="manifest-bucket")
    args = make_args()

    # Create local files
    (tmp_path / "part-001.csv").write_text("source-bucket,key1\n")
    (tmp_path / "large.csv").write_text("source-bucket,bigkey\n")

    uploaded = upload_manifests(s3, args, str(tmp_path), num_parts=1, standard_count=1, large_count=1)

    assert uploaded == 1
    # Verify both uploaded
    s3.head_object(Bucket="manifest-bucket", Key="source-bucket-manifest-001.csv")
    s3.head_object(Bucket="manifest-bucket", Key="source-bucket-manifest-large.csv")


@mock_aws
def test_upload_manifests_no_large(tmp_path, make_args):
    s3 = boto3.client("s3", region_name="us-east-1")
    s3.create_bucket(Bucket="manifest-bucket")
    args = make_args()

    (tmp_path / "part-001.csv").write_text("source-bucket,key1\n")
    (tmp_path / "large.csv").write_text("")

    uploaded = upload_manifests(s3, args, str(tmp_path), num_parts=1, standard_count=1, large_count=0)

    assert uploaded == 1
    s3.head_object(Bucket="manifest-bucket", Key="source-bucket-manifest-001.csv")
    # large should NOT exist
    with pytest.raises(s3.exceptions.ClientError):
        s3.head_object(Bucket="manifest-bucket", Key="source-bucket-manifest-large.csv")


# ---------------------------------------------------------------------------
# End-to-end: main()
# ---------------------------------------------------------------------------

@mock_aws
def test_main_local_only(tmp_path, make_args, populate_bucket):
    s3 = boto3.client("s3", region_name="us-east-1")
    populate_bucket(s3, "source-bucket", [("file1.txt", 10), ("file2.txt", 20)], region="us-east-1")

    outdir = str(tmp_path / "output")
    test_args = [
        "generate_manifest.py",
        "--bucket", "source-bucket",
        "--source-region", "us-east-1",
        "--local-only",
        "--output-dir", outdir,
    ]
    with patch("sys.argv", test_args):
        from generate_manifest import main
        main()

    assert os.path.isfile(os.path.join(outdir, "part-001.csv"))
    content = open(os.path.join(outdir, "part-001.csv")).read()
    assert "source-bucket" in content
    assert content.count("\n") == 2


@mock_aws
def test_main_s3_upload(tmp_path, make_args, populate_bucket):
    s3 = boto3.client("s3", region_name="us-east-1")
    populate_bucket(s3, "source-bucket", [("a.txt", 5), ("b.txt", 10)], region="us-east-1")
    populate_bucket(s3, "manifest-bucket", [], region="us-east-1")

    test_args = [
        "generate_manifest.py",
        "--bucket", "source-bucket",
        "--source-region", "us-east-1",
        "--manifest-bucket", "manifest-bucket",
        "--manifest-key", "my-manifest",
    ]
    with patch("sys.argv", test_args):
        from generate_manifest import main
        main()

    obj = s3.get_object(Bucket="manifest-bucket", Key="my-manifest-001.csv")
    body = obj["Body"].read().decode()
    assert "source-bucket" in body
    assert body.count("\n") == 2
