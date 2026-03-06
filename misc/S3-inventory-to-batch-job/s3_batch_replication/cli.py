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

"""CLI group definition."""

import logging

import click

from s3_batch_replication.aws.complete import complete_regions
from s3_batch_replication.version import get_version

logger = logging.getLogger(__name__)


def _configure_logging(verbosity: int, quiet: bool) -> None:
    """
    Configure logging based on verbosity count and quiet flag.

    - ``--quiet``: CRITICAL only (suppresses all normal output)
    - 0 (default): WARNING
    - ``-v``: INFO
    - ``-vv``: DEBUG
    - ``-vvv``: DEBUG + boto3/botocore wire logging

    :param verbosity: Number of times ``-v`` was passed.
    :param quiet: Whether ``--quiet`` was set.
    """
    if quiet:
        level = logging.CRITICAL
    elif verbosity == 0:
        level = logging.WARNING
    elif verbosity == 1:
        level = logging.INFO
    else:
        level = logging.DEBUG

    logging.basicConfig(format="%(levelname)s %(name)s: %(message)s", level=level)

    if verbosity < 3:
        # Suppress boto3/botocore unless explicitly requested
        logging.getLogger("boto3").setLevel(logging.WARNING)
        logging.getLogger("botocore").setLevel(logging.WARNING)
        logging.getLogger("urllib3").setLevel(logging.WARNING)


@click.group(chain=True)
@click.version_option(version=get_version(), prog_name="s3-batch-replication")
@click.option("--region", default=None, envvar="AWS_DEFAULT_REGION", shell_complete=complete_regions, help="AWS region (e.g. me-south-1)")
@click.option("-v", "--verbose", count=True, help="Verbosity: -v INFO, -vv DEBUG, -vvv DEBUG + boto3")
@click.option("-q", "--quiet", is_flag=True, default=False, help="Suppress all output (exit code only)")
@click.pass_context
def cli(ctx: click.Context, region: str | None, verbose: int, quiet: bool) -> None:
    """S3 Batch Replication tools."""
    ctx.ensure_object(dict)
    ctx.obj["quiet"] = quiet
    _configure_logging(verbose, quiet)
    from s3_batch_replication.aws.boto import set_region
    set_region(region)


# Import commands after cli is defined to avoid circular imports
from s3_batch_replication.commands import (  # noqa: E402, F401
    replicate,
    setup_iam_role,
    setup_replication_rules,
    split,
    split_files,
    validate_setup,
)
