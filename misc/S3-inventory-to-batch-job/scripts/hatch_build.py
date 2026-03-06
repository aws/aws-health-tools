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

"""Hatch build hook — injects _version.py with git commit hash before wheel assembly."""

import subprocess
from pathlib import Path

from hatchling.builders.hooks.plugin.interface import BuildHookInterface

PKG_DIR = Path(__file__).parent.parent / "s3_batch_replication"
INJECTED = PKG_DIR / "_version.py"
COMMIT_FILE = PKG_DIR / "COMMIT"


def _git_commit() -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=Path(__file__).parent.parent,
            capture_output=True, text=True, timeout=2,
        )
        return result.stdout.strip() if result.returncode == 0 else None
    except (subprocess.SubprocessError, FileNotFoundError, OSError):
        return None


class CustomBuildHook(BuildHookInterface):
    """Inject _version.py into the package during wheel builds."""

    def initialize(self, version: str, build_data: dict) -> None:
        """Write _version.py (and COMMIT for sdist) before assembly."""
        pkg_version = (PKG_DIR / "VERSION").read_text().strip()

        # Resolve commit: from git if available, else from COMMIT file (sdist builds)
        commit = _git_commit()
        if commit:
            COMMIT_FILE.write_text(commit)
        elif COMMIT_FILE.exists():
            commit = COMMIT_FILE.read_text().strip()
        else:
            commit = "unknown"

        INJECTED.write_text(
            f'"""Static version injected during build."""\n\n'
            f'base_version = "{pkg_version}"\n'
            f'commit_hash = "{commit}"\n'
        )
        build_data["force_include"][str(INJECTED)] = "s3_batch_replication/_version.py"
        # Include COMMIT in sdist so wheel builds from sdist can read it
        build_data["force_include"][str(COMMIT_FILE)] = "s3_batch_replication/COMMIT"

    def finalize(self, version: str, build_data: dict, artifact_path: str) -> None:
        """Remove injected files after build."""
        INJECTED.unlink(missing_ok=True)
        COMMIT_FILE.unlink(missing_ok=True)
