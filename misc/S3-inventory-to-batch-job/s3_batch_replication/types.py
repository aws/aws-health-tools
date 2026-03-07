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

"""Custom Click parameter types for AWS values."""

import re

import click

from s3_batch_replication.aws.s3 import parse_s3_uri

_ARN_RE = re.compile(r"arn:[^:]+:iam::[0-9]{12}:role/.+")
_KMS_ARN_RE = re.compile(r"arn:[^:]+:kms:[^:]+:[0-9]{12}:(key|alias)/.+")


class PercentageToFloat(click.ParamType):
    """Click parameter type that accepts an integer percentage (0-100) and converts to a float (0.0-1.0)."""

    name = "percentage"

    def convert(self, value: str | int | float, param: click.Parameter | None, ctx: click.Context | None) -> float:
        """Convert integer percentage to float threshold."""
        try:
            pct = int(value)
        except (TypeError, ValueError):
            self.fail(f"{value!r} is not a valid integer percentage", param, ctx)
        if not 0 <= pct <= 100:
            self.fail(f"{pct} is out of range (0-100)", param, ctx)
        return pct / 100.0


class S3BucketArn(click.ParamType):
    """Click parameter type that accepts an S3 bucket ARN or plain bucket name, normalising to ARN form."""

    name = "s3_bucket_arn"

    def convert(self, value: str, param: click.Parameter | None, ctx: click.Context | None) -> str:
        """Return the value as an S3 bucket ARN, converting from plain bucket name if needed."""
        if not value.startswith("arn:"):
            return f"arn:aws:s3:::{value}"
        return value


class S3Uri(click.ParamType):
    """Click parameter type that validates an S3 URI (``s3://bucket/key``)."""

    name = "s3_uri"

    def convert(self, value: str, param: click.Parameter | None, ctx: click.Context | None) -> str:
        """Validate and return the S3 URI, or fail with a descriptive error."""
        try:
            parse_s3_uri(value)
        except ValueError as e:
            self.fail(str(e), param, ctx)
        return value


class KmsKeyArn(click.ParamType):
    """Click parameter type that validates a KMS key or alias ARN."""

    name = "kms_key_arn"

    def convert(self, value: str, param: click.Parameter | None, ctx: click.Context | None) -> str:
        """Validate and return the KMS key ARN, or fail with a descriptive error."""
        if not _KMS_ARN_RE.fullmatch(value):
            self.fail(f"{value!r} is not a valid KMS key ARN (expected arn:aws:kms:region:account:key/... or .../alias/...)", param, ctx)
        return value


class IamRoleArn(click.ParamType):
    """Click parameter type that validates an IAM role ARN."""

    name = "iam_role_arn"

    def convert(self, value: str, param: click.Parameter | None, ctx: click.Context | None) -> str:
        """Validate and return the IAM role ARN, or fail with a descriptive error."""
        if not _ARN_RE.fullmatch(value):
            self.fail(f"{value!r} is not a valid IAM role ARN", param, ctx)
        return value


class UnionType(click.ParamType):
    """Tries each delegate type in order, accepting the first that succeeds."""

    def __init__(self, *types: click.ParamType) -> None:
        self._types = types
        self.name = "|".join(t.name for t in types)

    def convert(self, value: str, param: click.Parameter | None, ctx: click.Context | None) -> str:
        """Try each delegate type in order and return the first successful conversion."""
        for t in self._types:
            try:
                return t.convert(value, param, None)  # pass None ctx to suppress per-type error messages — only the final combined error should surface
            except click.exceptions.BadParameter:
                continue
        self.fail(f"{value!r} is not a valid {self.name}", param, ctx)


class ManifestInput(click.ParamType):
    """Accepts an S3 URI (s3://bucket/key) or an existing local file path."""

    name = "s3_uri|file"
    _local = click.Path(exists=True, file_okay=True, dir_okay=False, readable=True)

    def convert(self, value: str, param: click.Parameter | None, ctx: click.Context | None) -> str:
        """Validate as an S3 URI or an existing local file path."""
        if value.startswith("s3://"):
            return S3Uri().convert(value, param, ctx)
        return self._local.convert(value, param, ctx)


OutputDestination = UnionType(
    S3Uri(),
    click.Path(exists=True, file_okay=False, dir_okay=True, writable=True),
)


class ObjectCount(click.ParamType):
    """Click parameter type that parses human-friendly object counts (e.g. ``1B``, ``500M``, ``2.5M``)."""

    name = "object_count"
    _SUFFIXES: dict[str, int] = {"k": 1_000, "m": 1_000_000, "b": 1_000_000_000}

    def convert(self, value: str | int, param: click.Parameter | None, ctx: click.Context | None) -> int:
        """Parse and return the object count as an integer, or fail with a descriptive error."""
        if isinstance(value, int):
            return value
        lower = value.lower()
        if lower[-1] in self._SUFFIXES:
            try:
                return int(float(lower[:-1]) * self._SUFFIXES[lower[-1]])
            except ValueError:
                pass
        try:
            return int(value)
        except ValueError:
            self.fail(f"{value!r} is not a valid object count (e.g. 1B, 500M, 2.5M, 1000)", param, ctx)
