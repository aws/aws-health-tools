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

"""S3 Inventory manifest parsing and job partitioning."""

import json
from dataclasses import dataclass
from typing import Iterator

from s3_batch_replication.aws.s3 import INVENTORY_MANIFEST_VERSION


@dataclass
class ManifestFile:
    """A single inventory CSV file entry from an S3 Inventory manifest."""

    key: str
    size: int
    md5_checksum: str


@dataclass
class Manifest:
    """A parsed S3 Inventory manifest, containing metadata and the list of inventory files."""

    source_bucket: str
    destination_bucket: str
    file_schema: str
    creation_timestamp: str
    files: list[ManifestFile]


def _parse_manifest_file(index: int, data: dict) -> ManifestFile:
    """
    Parse a single file entry from a manifest's ``files`` array.

    :param index: Zero-based index of the entry, used in error messages.
    :param data: Raw file entry dict from the manifest JSON.
    :return: A parsed :class:`ManifestFile`.
    :raises RuntimeError: If a required field is missing.
    """
    for field in ("key", "size", "MD5checksum"):
        if field not in data:
            raise RuntimeError(f"Manifest file entry {index} is missing required field: {field!r}")
    return ManifestFile(key=data["key"], size=data["size"], md5_checksum=data["MD5checksum"])


def parse_manifest(data: dict) -> Manifest:
    """
    Parse a raw S3 Inventory manifest.json dict into a :class:`Manifest`.

    :param data: Parsed JSON content of a manifest.json file.
    :return: A validated :class:`Manifest` instance.
    :raises RuntimeError: If required fields are missing, the version is unsupported,
        the format is not CSV, or the file list is empty.
    """
    for field in ("sourceBucket", "destinationBucket", "version", "fileFormat", "fileSchema", "creationTimestamp", "files"):
        if field not in data:
            raise RuntimeError(f"Manifest is missing required field: {field!r}")
    if data["version"] != INVENTORY_MANIFEST_VERSION:
        raise RuntimeError(f"Unsupported manifest version: {data['version']!r} (expected {INVENTORY_MANIFEST_VERSION!r})")
    if data["fileFormat"] != "CSV":
        raise RuntimeError(
            f"Manifest fileFormat is {data['fileFormat']!r} — only CSV is supported by S3 Batch Replication"
        )
    if not data["files"]:
        raise RuntimeError("Manifest contains no files")
    if "VersionId" not in data["fileSchema"]:
        raise RuntimeError(
            "Manifest fileSchema does not include VersionId — "
            "S3 Batch Replication requires VersionId in the inventory configuration. "
            "Update the inventory configuration to include VersionId and wait for a new report."
        )
    files = [_parse_manifest_file(i, f) for i, f in enumerate(data["files"])]
    return Manifest(
        source_bucket=data["sourceBucket"],
        destination_bucket=data["destinationBucket"],
        file_schema=data["fileSchema"],
        creation_timestamp=data["creationTimestamp"],
        files=files,
    )


def build_manifest(source: Manifest, files: list[ManifestFile]) -> Manifest:
    """
    Construct a new :class:`Manifest` from a subset of inventory files, preserving source metadata.

    :param source: The original manifest to copy metadata from.
    :param files: The subset of inventory files to include.
    :return: A new :class:`Manifest` with the given files and source metadata.
    """
    return Manifest(
        source_bucket=source.source_bucket,
        destination_bucket=source.destination_bucket,
        file_schema=source.file_schema,
        creation_timestamp=source.creation_timestamp,
        files=files,
    )


def serialise_manifest(manifest: Manifest) -> bytes:
    """
    Serialise a :class:`Manifest` to JSON bytes suitable for upload as a manifest.json.

    :param manifest: The manifest to serialise.
    :return: UTF-8 encoded JSON bytes.
    """
    return json.dumps({
        "sourceBucket": manifest.source_bucket,
        "destinationBucket": manifest.destination_bucket,
        "version": INVENTORY_MANIFEST_VERSION,
        "creationTimestamp": manifest.creation_timestamp,
        "fileFormat": "CSV",
        "fileSchema": manifest.file_schema,
        "files": [{"key": f.key, "size": f.size, "MD5checksum": f.md5_checksum} for f in manifest.files],
    }, indent=2).encode()


def partition_files(files: list[ManifestFile], files_per_job: int) -> Iterator[list[ManifestFile]]:
    """
    Partition a list of inventory files into fixed-size bins, one bin per batch job.

    :param files: Full list of inventory files from the source manifest.
    :param files_per_job: Maximum number of files per partition.
    :return: An iterator of file lists, each suitable for one batch replication job's manifest.
    """
    # Accumulate files into a bin up to files_per_job, then yield it and start a new one.
    # Each yielded bin becomes one job's manifest.
    manifest_bin: list[ManifestFile] = []
    for f in files:
        if len(manifest_bin) >= files_per_job:  # >= rather than == in case files_per_job ever changes to a batch add
            yield manifest_bin
            manifest_bin = []
        manifest_bin.append(f)
    if manifest_bin:
        yield manifest_bin  # yield the final bin even if it never reached files_per_job
