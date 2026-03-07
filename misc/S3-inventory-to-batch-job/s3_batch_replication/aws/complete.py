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

"""Shell completion helpers."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import click


def complete_regions(
    ctx: click.Context, param: click.Parameter, incomplete: str
) -> list[click.shell_completion.CompletionItem]:
    """
    Complete AWS region names using botocore's bundled endpoints data.

    :param ctx: Click context.
    :param param: Click parameter being completed.
    :param incomplete: Partial value typed so far.
    :return: Matching region completion items.
    """
    from click.shell_completion import CompletionItem
    try:
        import botocore.session
        regions = botocore.session.get_session().get_available_regions("s3")
    except Exception:  # shell completion must never raise — silently degrade if botocore is unavailable
        regions = []
    return [CompletionItem(r) for r in regions if r.startswith(incomplete)]


def complete_buckets(
    ctx: click.Context, param: click.Parameter, incomplete: str
) -> list[click.shell_completion.CompletionItem]:
    """
    Complete S3 bucket names from the current account, using the typed prefix for server-side filtering.

    :param ctx: Click context.
    :param param: Click parameter being completed.
    :param incomplete: Partial value typed so far, used as a server-side prefix filter.
    :return: Matching bucket name completion items.
    """
    from click.shell_completion import CompletionItem
    try:
        import boto3
        kwargs: dict = {"MaxBuckets": 50 if incomplete else 100}
        if incomplete:
            kwargs["Prefix"] = incomplete
        buckets = boto3.client("s3").list_buckets(**kwargs).get("Buckets", [])
        return [CompletionItem(b["Name"]) for b in buckets]
    except Exception:  # shell completion must never raise — silently degrade on auth errors or network issues
        return []
