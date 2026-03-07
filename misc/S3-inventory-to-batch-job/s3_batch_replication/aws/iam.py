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

"""IAM operations."""

from __future__ import annotations

import time
from typing import cast

import click
from botocore.exceptions import ClientError
from mypy_boto3_iam import IAMClient
from mypy_boto3_sts import STSClient

from s3_batch_replication.aws.boto import client
from s3_batch_replication.constants import IAM_PROPAGATION_DELAY
from s3_batch_replication.output import echo


def validate_role_trust_policy(role_arn: str, required_principal: str) -> None:
    """
    Validate that an IAM role trusts the required principal.

    :param role_arn: The ARN of the role.
    :param required_principal: The service principal we want to ensure the IAM trusts.
    :raise RuntimeError: If the role does not trust the required principal or could not retrieve details of the IAM role.
    """
    iam: IAMClient = cast(IAMClient, client("iam"))
    role_name = role_arn.split("/")[-1]
    try:
        role = iam.get_role(RoleName=role_name)
    except ClientError as e:
        raise RuntimeError(f"Failed to retrieve IAM role {role_arn}: {e}") from e

    principals: list[str] = []
    for stmt in role["Role"]["AssumeRolePolicyDocument"]["Statement"]:
        if stmt.get("Effect") != "Allow":
            continue
        service = stmt.get("Principal", {}).get("Service")
        if not service:
            continue
        principals.extend([service] if isinstance(service, str) else service)
    if required_principal not in principals:
        raise RuntimeError(
            f"IAM role {role_arn} does not trust {required_principal} — "
            "add it to the role's trust policy before proceeding"
        )


def validate_role_kms_permissions(role_arn: str, key_arn: str, required_actions: list[str]) -> None:
    """
    Smoke-test that an IAM role's inline policy allows the required KMS actions on a key.

    This is a best-effort check — it does not perform full IAM policy evaluation and does
    not account for conditions, permission boundaries, or SCPs. If this check produces a
    false positive for your environment, use ``--no-check-kms`` to skip it.

    :param role_arn: The ARN of the IAM role to check.
    :param key_arn: The KMS key ARN to check permissions for.
    :param required_actions: KMS actions that must be allowed (e.g. ``["kms:Decrypt"]``).
    :raises RuntimeError: If any required action is not found in the role's inline policies,
        or if the role's policies cannot be retrieved.
    """
    iam: IAMClient = cast(IAMClient, client("iam"))
    role_name = role_arn.split("/")[-1]
    try:
        policies = iam.list_role_policies(RoleName=role_name)
    except ClientError as e:
        raise RuntimeError(f"Failed to list policies for IAM role {role_arn}: {e}") from e

    allowed_actions: set[str] = set()
    for policy_name in policies["PolicyNames"]:
        try:
            doc = iam.get_role_policy(RoleName=role_name, PolicyName=policy_name)
        except ClientError as e:
            raise RuntimeError(f"Failed to get policy {policy_name!r} for IAM role {role_arn}: {e}") from e
        for stmt in doc["PolicyDocument"].get("Statement", []):
            if stmt.get("Effect") != "Allow":
                continue
            resources = stmt.get("Resource", [])
            if isinstance(resources, str):
                resources = [resources]
            # Check if this statement covers the key (exact match or wildcard)
            if not any(r == "*" or r == key_arn for r in resources):
                continue
            actions = stmt.get("Action", [])
            if isinstance(actions, str):
                actions = [actions]
            allowed_actions.update(actions)

    missing = [a for a in required_actions if a not in allowed_actions]
    if missing:
        raise RuntimeError(
            f"IAM role {role_arn} appears to be missing {missing} for KMS key {key_arn} — "
            "this is a smoke test only; use --no-check-kms to skip if your policy uses conditions or wildcards"
        )


def get_account_id() -> str:
    """Get the AWS account ID of the current credentials."""
    return cast(STSClient, client("sts")).get_caller_identity()["Account"]


def resolve_role_arn(ctx: click.Context, role_arn: str | None) -> str:
    """
    Resolve the IAM role ARN from the Click context if not explicitly provided.

    If the role ARN comes from context (i.e. chained after setup-iam-role), applies a
    one-time propagation delay to allow the role to become consistent across AWS.

    :param ctx: Click context, used to read and update chained command state.
    :param role_arn: Explicitly provided role ARN, or None to resolve from context.
    :return: The resolved role ARN.
    :raises click.UsageError: If no role ARN is available from either source.
    """
    if not role_arn:
        role_arn = ctx.obj.get("role_arn")
        if role_arn and not ctx.obj.get("iam_propagation_waited"):
            echo(ctx, f"Waiting {IAM_PROPAGATION_DELAY}s for IAM role propagation...")
            time.sleep(IAM_PROPAGATION_DELAY)
            ctx.obj["iam_propagation_waited"] = True
    if not role_arn:
        raise click.UsageError("--role-arn is required when not chained after setup-iam-role")
    return role_arn
