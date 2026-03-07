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

"""Boto3 client factory with optional region override."""

from __future__ import annotations

import boto3
from botocore.client import BaseClient

_region: str | None = None


def set_region(region: str | None) -> None:
    """
    Set the default region for all future boto3 clients.

    :param region: AWS region or None to use the default region
    """
    global _region
    _region = region


def client(service: str, region_name: str | None = None) -> BaseClient:
    """
    Create a boto3 client for the given service, using the configured region.

    :param service: AWS service name (e.g. "s3", "iam", "s3control").
    :param region_name: Optional region override.
    :return: A boto3 client for the requested service.
    """
    return boto3.client(service, region_name=region_name or _region)
