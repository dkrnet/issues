# Copyright (C) 2026 David Redmond
# SPDX-License-Identifier: AGPL-3.0-only
#
"""Requirements mapping: repository build script version stamping."""

import os
import shutil
import subprocess


def _run(command, cwd):
    return subprocess.run(command, cwd=cwd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)


def _init_git_repo(path):
    assert _run(["git", "init"], path).returncode == 0
    assert _run(["git", "config", "user.email", "tests@example.invalid"], path).returncode == 0
    assert _run(["git", "config", "user.name", "Tests"], path).returncode == 0
    assert _run(["git", "add", "build.sh", "issues.cgi"], path).returncode == 0
    result = _run(["git", "commit", "-m", "initial"], path)
    assert result.returncode == 0, result.stderr
    result = _run(["git", "rev-parse", "--verify", "HEAD"], path)
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()


def test_build_script_stamps_issues_version_with_semver_build_metadata(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    source_root = os.path.dirname(os.path.dirname(__file__))
    shutil.copy2(os.path.join(source_root, "build.sh"), repo / "build.sh")
    (repo / "issues.cgi").write_text(
        '\nDB_FILE = "/var/lib/issues/issues.db"\nISSUES_VERSION = "1.0.0"\nMAX_UPLOAD_BYTES = 10485760\n',
        encoding="utf-8",
    )
    (repo / "build.sh").chmod(0o755)
    (repo / "issues.cgi").chmod(0o755)
    git_id = _init_git_repo(repo)

    result = _run(["./build.sh"], repo)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == f"1.0.0+{git_id}"
    text = (repo / "issues.cgi").read_text(encoding="utf-8")
    assert f'ISSUES_VERSION = "1.0.0+{git_id}"' in text

    result = _run(["./build.sh"], repo)
    assert result.returncode == 0, result.stderr
    text = (repo / "issues.cgi").read_text(encoding="utf-8")
    assert f'ISSUES_VERSION = "1.0.0+{git_id}"' in text
    assert text.count("+") == 1


def test_build_script_fails_without_exactly_one_version_assignment(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    source_root = os.path.dirname(os.path.dirname(__file__))
    shutil.copy2(os.path.join(source_root, "build.sh"), repo / "build.sh")
    (repo / "issues.cgi").write_text(
        'ISSUES_VERSION = "1.0.0"\nISSUES_VERSION = "1.0.1"\n',
        encoding="utf-8",
    )
    (repo / "build.sh").chmod(0o755)
    _init_git_repo(repo)

    result = _run(["./build.sh"], repo)
    assert result.returncode != 0
    assert "exactly one ISSUES_VERSION assignment" in result.stderr
