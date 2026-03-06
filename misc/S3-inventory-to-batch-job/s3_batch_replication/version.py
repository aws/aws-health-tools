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

"""Version detection.

Priority:
1. Static _version.py injected during release build (wheel distributions)
2. Dynamic git detection (development)
3. Base version from VERSION file (fallback)
"""

import subprocess
from pathlib import Path


def _read_version_file() -> str:
    try:
        return (Path(__file__).parent / "VERSION").read_text().strip()
    except Exception:
        return "0.0.0"


__version__ = _read_version_file()


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


def get_version() -> str:
    """Return the current version string, including git commit hash if available."""
    # Release build: static _version.py injected by build_release.py
    try:
        from s3_batch_replication import _version  # type: ignore[attr-defined]
        return f"{_version.base_version} ({_version.commit_hash})"
    except (ImportError, AttributeError):
        pass

    # Development: derive from git
    commit = _git_commit()
    if commit:
        return f"{__version__} ({commit})"

    return f"{__version__} (untracked)"
