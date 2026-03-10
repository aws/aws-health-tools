"""Tests for copy_large_objects.py."""

import os
import sys
import textwrap

import boto3
import pytest
from moto import mock_aws
from unittest.mock import MagicMock, patch, call
from botocore.exceptions import ClientError

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import copy_large_objects as mod  # noqa: E402


# ---------------------------------------------------------------------------
# _parse_manifest_rows
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "lines, expected",
    [
        (["bucket,key1"], [("bucket", "key1", None)]),
        (["bucket,key1,v1"], [("bucket", "key1", "v1")]),
        (["bucket,my%20file.txt"], [("bucket", "my file.txt", None)]),
        (["bucket,a%2Fb.txt,v2"], [("bucket", "a/b.txt", "v2")]),
        (["", "bucket,k1"], [("bucket", "k1", None)]),
        ([], []),
    ],
    ids=["2-col", "3-col", "url-decoded", "url-decoded-with-version", "skip-empty", "empty-input"],
)
def test_parse_manifest_rows(lines, expected):
    assert list(mod._parse_manifest_rows(lines)) == expected


# ---------------------------------------------------------------------------
# _read_manifest — local file
# ---------------------------------------------------------------------------
def test_read_manifest_local(tmp_path):
    csv_file = tmp_path / "manifest.csv"
    csv_file.write_text("bucket,key1\nbucket,key2,v1\n")
    result = mod._read_manifest(str(csv_file), None)
    assert result == [("bucket", "key1", None), ("bucket", "key2", "v1")]


# ---------------------------------------------------------------------------
# _read_manifest — S3
# ---------------------------------------------------------------------------
@mock_aws
def test_read_manifest_s3(populate_bucket):
    session = boto3.Session()
    s3 = session.client("s3", region_name="us-east-1")
    populate_bucket(s3, "manifest-bkt", [])
    s3.put_object(Bucket="manifest-bkt", Key="m.csv", Body=b"src,key1\nsrc,key2,v1\n")
    result = mod._read_manifest("s3://manifest-bkt/m.csv", session)
    assert result == [("src", "key1", None), ("src", "key2", "v1")]


# ---------------------------------------------------------------------------
# _read_manifest — invalid S3 URIs
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("uri", ["s3://", "s3://bucket", "s3:///key"])
def test_read_manifest_invalid_s3_uri(uri):
    with pytest.raises(SystemExit):
        mod._read_manifest(uri, boto3.Session())


# ---------------------------------------------------------------------------
# _get_bucket_region
# ---------------------------------------------------------------------------
@mock_aws
@pytest.mark.parametrize(
    "region, expected",
    [
        ("us-east-1", "us-east-1"),
        ("eu-west-1", "eu-west-1"),
    ],
)
def test_get_bucket_region(region, expected, populate_bucket):
    session = boto3.Session()
    s3 = session.client("s3", region_name=region)
    populate_bucket(s3, "region-test-bkt", [], region=region)
    assert mod._get_bucket_region(session, "region-test-bkt") == expected


# ---------------------------------------------------------------------------
# _get_part_sizes
# ---------------------------------------------------------------------------
def test_get_part_sizes():
    mock_s3 = MagicMock()
    sizes = [5_000_000, 3_000_000, 2_000_000]
    mock_s3.head_object.side_effect = [{"ContentLength": s} for s in sizes]
    result = mod._get_part_sizes(mock_s3, "bkt", "key", None, 3)
    assert result == sizes
    assert mock_s3.head_object.call_count == 3
    # Verify PartNumber passed correctly
    for i, c in enumerate(mock_s3.head_object.call_args_list, 1):
        assert c == call(Bucket="bkt", Key="key", PartNumber=i)


def test_get_part_sizes_with_version_id():
    mock_s3 = MagicMock()
    mock_s3.head_object.return_value = {"ContentLength": 100}
    mod._get_part_sizes(mock_s3, "bkt", "key", "vid1", 1)
    mock_s3.head_object.assert_called_once_with(Bucket="bkt", Key="key", PartNumber=1, VersionId="vid1")


# ---------------------------------------------------------------------------
# _build_tagging_string
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "tag_set, expected",
    [
        ([{"Key": "env", "Value": "prod"}], "env=prod"),
        ([{"Key": "a", "Value": "1"}, {"Key": "b", "Value": "2"}], "a=1&b=2"),
        ([{"Key": "k&k", "Value": "v=v"}], "k%26k=v%3Dv"),
        ([], ""),
    ],
    ids=["single", "multiple", "special-chars", "empty"],
)
def test_build_tagging_string(tag_set, expected):
    assert mod._build_tagging_string(tag_set) == expected


# ---------------------------------------------------------------------------
# _check_bucket_accessible
# ---------------------------------------------------------------------------
@mock_aws
def test_check_bucket_accessible_success(populate_bucket):
    s3 = boto3.client("s3", region_name="us-east-1")
    populate_bucket(s3, "ok-bkt", [])
    assert mod._check_bucket_accessible(s3, "ok-bkt", "Test") is True


@pytest.mark.parametrize("code", ["403", "404", "500"])
def test_check_bucket_accessible_errors(code):
    mock_s3 = MagicMock()
    mock_s3.head_bucket.side_effect = ClientError(
        {"Error": {"Code": code, "Message": "err"}}, "HeadBucket"
    )
    with pytest.raises(SystemExit):
        mod._check_bucket_accessible(mock_s3, "bkt", "Test")


# ---------------------------------------------------------------------------
# _copy_object — simple (non-multipart)
# ---------------------------------------------------------------------------
def test_copy_object_simple():
    src, dst = MagicMock(), MagicMock()
    src.head_object.return_value = {
        "ETag": '"abc123"',
        "ContentLength": 1024,
        "ContentType": "text/plain",
        "Metadata": {},
    }
    src.get_object_tagging.return_value = {"TagSet": []}

    key, ok, err = mod._copy_object(src, dst, "src-bkt", "file.txt", None, "dst-bkt", "")
    assert (key, ok, err) == ("file.txt", True, None)
    dst.copy_object.assert_called_once()
    dst.create_multipart_upload.assert_not_called()


# ---------------------------------------------------------------------------
# _copy_object — multipart
# ---------------------------------------------------------------------------
def test_copy_object_multipart():
    src, dst = MagicMock(), MagicMock()
    part_size = 5_000_000_000

    # First call: main HEAD; subsequent calls: per-part HEADs
    src.head_object.side_effect = [
        {
            "ETag": '"abc123-3"',
            "ContentLength": part_size * 3,
            "ContentType": "application/octet-stream",
            "Metadata": {"x": "y"},
        },
    ] + [{"ContentLength": part_size} for _ in range(3)]
    src.get_object_tagging.return_value = {"TagSet": []}

    dst.create_multipart_upload.return_value = {"UploadId": "uid"}
    dst.upload_part_copy.return_value = {"CopyPartResult": {"ETag": '"pe"'}}

    key, ok, err = mod._copy_object(src, dst, "src-bkt", "big.bin", None, "dst-bkt", "")
    assert (key, ok, err) == ("big.bin", True, None)
    dst.create_multipart_upload.assert_called_once()
    assert dst.upload_part_copy.call_count == 3
    dst.complete_multipart_upload.assert_called_once()
    dst.abort_multipart_upload.assert_not_called()

    # Verify byte ranges
    for i, c in enumerate(dst.upload_part_copy.call_args_list):
        expected_range = f"bytes={i * part_size}-{(i + 1) * part_size - 1}"
        assert c.kwargs["CopySourceRange"] == expected_range
        assert c.kwargs["PartNumber"] == i + 1


# ---------------------------------------------------------------------------
# _copy_object — failure on head_object
# ---------------------------------------------------------------------------
def test_copy_object_failure():
    src = MagicMock()
    src.head_object.side_effect = ClientError(
        {"Error": {"Code": "404", "Message": "Not Found"}}, "HeadObject"
    )
    key, ok, err = mod._copy_object(src, MagicMock(), "bkt", "missing.txt", None, "dst", "")
    assert (key, ok) == ("missing.txt", False)
    assert err is not None


# ---------------------------------------------------------------------------
# _copy_object — multipart failure aborts upload
# ---------------------------------------------------------------------------
def test_copy_object_multipart_failure_aborts():
    src, dst = MagicMock(), MagicMock()
    src.head_object.side_effect = [
        {"ETag": '"abc-2"', "ContentLength": 2000, "ContentType": "text/plain", "Metadata": {}},
        {"ContentLength": 1000},
        {"ContentLength": 1000},
    ]
    src.get_object_tagging.return_value = {"TagSet": []}
    dst.create_multipart_upload.return_value = {"UploadId": "uid"}
    dst.upload_part_copy.side_effect = Exception("network error")

    key, ok, err = mod._copy_object(src, dst, "bkt", "fail.bin", None, "dst", "")
    assert (key, ok) == ("fail.bin", False)
    assert "network error" in err
    dst.abort_multipart_upload.assert_called_once_with(Bucket="dst", Key="fail.bin", UploadId="uid")


# ---------------------------------------------------------------------------
# _copy_object — with tags
# ---------------------------------------------------------------------------
def test_copy_object_with_tags():
    src, dst = MagicMock(), MagicMock()
    src.head_object.side_effect = [
        {"ETag": '"abc-1"', "ContentLength": 100, "ContentType": "text/plain", "Metadata": {}},
        {"ContentLength": 100},
    ]
    src.get_object_tagging.return_value = {"TagSet": [{"Key": "env", "Value": "prod"}]}
    dst.create_multipart_upload.return_value = {"UploadId": "uid"}
    dst.upload_part_copy.return_value = {"CopyPartResult": {"ETag": '"pe"'}}

    mod._copy_object(src, dst, "bkt", "tagged.bin", None, "dst", "")
    create_kwargs = dst.create_multipart_upload.call_args.kwargs
    assert create_kwargs["Tagging"] == "env=prod"


# ---------------------------------------------------------------------------
# _copy_object — with dest_prefix
# ---------------------------------------------------------------------------
def test_copy_object_with_dest_prefix():
    src, dst = MagicMock(), MagicMock()
    src.head_object.return_value = {
        "ETag": '"simple"',
        "ContentLength": 10,
        "ContentType": "text/plain",
        "Metadata": {},
    }
    src.get_object_tagging.return_value = {"TagSet": []}

    mod._copy_object(src, dst, "bkt", "original.txt", None, "dst", "backup/")
    dst.copy_object.assert_called_once()
    assert dst.copy_object.call_args.kwargs["Key"] == "backup/original.txt"


# ---------------------------------------------------------------------------
# main — end-to-end with moto
# ---------------------------------------------------------------------------
@mock_aws
def test_main_simple_copy(tmp_path, populate_bucket):
    session = boto3.Session()
    s3 = session.client("s3", region_name="us-east-1")
    populate_bucket(s3, "src-bkt", [("file1.txt", 10), ("file2.txt", 20)])

    # Create dest bucket
    populate_bucket(s3, "dst-bkt", [])

    # Write local manifest
    manifest = tmp_path / "manifest.csv"
    manifest.write_text("src-bkt,file1.txt\nsrc-bkt,file2.txt\n")

    test_args = [
        "copy_large_objects.py",
        "--manifest", str(manifest),
        "--dest-bucket", "dst-bkt",
        "--dest-region", "us-east-1",
    ]
    with patch.object(sys, "argv", test_args):
        mod.main()

    # Verify objects copied
    objs = s3.list_objects_v2(Bucket="dst-bkt")["Contents"]
    keys = sorted(o["Key"] for o in objs)
    assert keys == ["file1.txt", "file2.txt"]
