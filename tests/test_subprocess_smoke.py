# Copyright (C) 2026 David Redmond
# SPDX-License-Identifier: AGPL-3.0-only
#
"""Requirements mapping: subprocess CGI smoke testing for GET/POST routing and headers."""

import getpass
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys


def _make_subprocess_app(issues_cgi_path, tmp_path, temp_db, temp_config_dir):
    app_copy = tmp_path / "issues.cgi"
    text = issues_cgi_path.read_text(encoding="utf-8")
    replacements = {
        'DB_FILE = "/var/lib/issues/issues.db"': f'DB_FILE = {str(temp_db)!r}',
        'PER_USER_CONFIG_DIR = "/var/lib/issues/config"': f'PER_USER_CONFIG_DIR = {str(temp_config_dir)!r}',
        'ASSIGNEE_GROUP = "users"': 'ASSIGNEE_GROUP = ""',
        'ADMINS_GROUP = "wheel"': 'ADMINS_GROUP = ""',
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    app_copy.write_text(text, encoding="utf-8")
    app_copy.chmod(0o755)
    return app_copy


def _run_cgi(script, query_string="", method="GET", body="", remote_user=None):
    if remote_user is None:
        remote_user = getpass.getuser()
    env = os.environ.copy()
    env.update({
        "REQUEST_METHOD": method,
        "QUERY_STRING": query_string,
        "REMOTE_USER": remote_user,
        "CONTENT_TYPE": "application/x-www-form-urlencoded",
        "CONTENT_LENGTH": str(len(body.encode("utf-8"))),
        "SERVER_NAME": "localhost",
        "SERVER_PORT": "443",
        "SERVER_PROTOCOL": "HTTP/1.1",
        "GATEWAY_INTERFACE": "CGI/1.1",
        "SCRIPT_NAME": "/issues.cgi",
    })
    if remote_user == "":
        env.pop("REMOTE_USER", None)
    return subprocess.run([sys.executable, str(script)], env=env, input=body, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)


def _headers(stdout):
    return stdout.split("\n\n", 1)[0]


def test_subprocess_cgi_smoke_missing_action_defaults_to_list_with_remote_user_and_login_without_remote_user(issues_cgi_path, tmp_path, temp_db, temp_config_dir):
    script = _make_subprocess_app(issues_cgi_path, tmp_path, temp_db, temp_config_dir)
    authenticated = _run_cgi(script)
    assert authenticated.returncode == 0, authenticated.stderr
    authenticated_headers = _headers(authenticated.stdout)
    assert authenticated.stdout.find("Content-Type:") < authenticated.stdout.find("<")
    assert "Content-Type: text/html" in authenticated_headers
    assert "<html" in authenticated.stdout.lower()
    assert "Issues Login" not in authenticated.stdout

    unauthenticated = _run_cgi(script, remote_user="")
    assert unauthenticated.returncode == 0, unauthenticated.stderr
    unauthenticated_headers = _headers(unauthenticated.stdout)
    assert "Content-Type: text/html" in unauthenticated_headers
    assert "Issues Login" in unauthenticated.stdout
    assert "Anonymous or invalid user" not in unauthenticated.stdout


def test_subprocess_cgi_smoke_known_action_unknown_action_and_get_parsing(issues_cgi_path, tmp_path, temp_db, temp_config_dir):
    script = _make_subprocess_app(issues_cgi_path, tmp_path, temp_db, temp_config_dir)
    known = _run_cgi(script, "action=markdown_help")
    assert known.returncode == 0, known.stderr
    assert "Markdown Help" in known.stdout
    unknown = _run_cgi(script, "action=not_real")
    assert "Status: 404 Not Found" in _headers(unknown.stdout)
    assert "Traceback" not in unknown.stderr
    assert unknown.returncode == 0, unknown.stderr
    unsafe = _run_cgi(script, "action=bad-name")
    assert "Status: 400 Bad Request" in _headers(unsafe.stdout)
    assert "Traceback" not in unsafe.stderr
    assert unsafe.returncode == 0, unsafe.stderr


def test_subprocess_cgi_smoke_blank_search_submission_clears_saved_search(issues_cgi_path, tmp_path, temp_db, temp_config_dir):
    script = _make_subprocess_app(issues_cgi_path, tmp_path, temp_db, temp_config_dir)
    temp_config_dir.mkdir(parents=True, exist_ok=True)
    username = getpass.getuser()
    (temp_config_dir / f"{username}.json").write_text(
        json.dumps({
            "status": "any",
            "priority": "any",
            "creator": "any",
            "assignee": "any",
            "state": "any",
            "due_date": "any",
            "has_comments": False,
            "has_attachments": False,
            "search": "printer",
            "auto_refresh": "never",
        }),
        encoding="utf-8",
    )

    with sqlite3.connect(temp_db) as con:
        con.execute(
            "INSERT INTO issues (title, description, creator_username, assigned_username, priority, pct_complete, state, status, due_date, created_at, updated_at, completed_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'), NULL)",
            ("Printer queue failure", "Routine description", username, "", "normal", 0, "not started", "open", ""),
        )
        con.execute(
            "INSERT INTO issues (title, description, creator_username, assigned_username, priority, pct_complete, state, status, due_date, created_at, updated_at, completed_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'), NULL)",
            ("Unrelated issue", "Routine description", username, "", "normal", 0, "not started", "open", ""),
        )

    result = _run_cgi(script, "action=list&status=any&priority=any&search=")
    assert result.returncode == 0, result.stderr
    assert "Printer queue failure" in result.stdout
    assert "Unrelated issue" in result.stdout
    saved = (temp_config_dir / f"{username}.json").read_text(encoding="utf-8")
    assert '"search": ""' in saved
    assert 'name="search" value=""' in result.stdout


def test_subprocess_cgi_smoke_post_parsing_for_representative_form(issues_cgi_path, tmp_path, temp_db, temp_config_dir):
    script = _make_subprocess_app(issues_cgi_path, tmp_path, temp_db, temp_config_dir)
    body = "action=create_submit&title=Subprocess+issue&description=Body&priority=normal&assigned_username="
    result = _run_cgi(script, method="POST", body=body)
    assert result.returncode == 0, result.stderr
    headers = _headers(result.stdout)
    assert "Location:" in headers
    with sqlite3.connect(temp_db) as con:
        count = con.execute("SELECT COUNT(*) FROM issues WHERE title = 'Subprocess issue'").fetchone()[0]
    assert count == 1


def test_subprocess_cgi_smoke_login_action_without_remote_user(issues_cgi_path, tmp_path, temp_db, temp_config_dir):
    script = _make_subprocess_app(issues_cgi_path, tmp_path, temp_db, temp_config_dir)
    result = _run_cgi(script, "action=login", remote_user="")
    assert result.returncode == 0, result.stderr
    headers = _headers(result.stdout)
    assert "Content-Type: text/html" in headers
    assert "Issues Login" in result.stdout
    assert "Anonymous or invalid user" not in result.stdout


def test_subprocess_cgi_smoke_protected_action_without_remote_user_is_rejected(issues_cgi_path, tmp_path, temp_db, temp_config_dir):
    script = _make_subprocess_app(issues_cgi_path, tmp_path, temp_db, temp_config_dir)
    result = _run_cgi(script, "action=list", remote_user="")
    assert result.returncode == 0, result.stderr
    assert "Status: 403 Forbidden" in _headers(result.stdout)
