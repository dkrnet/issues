# Copyright (C) 2026 David Redmond
# SPDX-License-Identifier: AGPL-3.0-only
#
"""Requirements mapping: import behavior, syntax checking, and temporary database schema."""
import sqlite3


def test_issues_cgi_syntax_check_passes(syntax_check):
    assert syntax_check.name == "issues.cgi"


def test_test_database_schema_matches_requirements(temp_db):
    with sqlite3.connect(temp_db) as con:
        tables = {row[0] for row in con.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        assert {"issues", "comments", "attachments", "issue_history"}.issubset(tables)
        issue_cols = [row[1] for row in con.execute("PRAGMA table_info(issues)")]
        assert issue_cols == [
            "id", "title", "description", "creator_username", "assigned_username",
            "priority", "pct_complete", "state", "status", "due_date",
            "created_at", "updated_at", "completed_at",
        ]
        history_cols = [row[1] for row in con.execute("PRAGMA table_info(issue_history)")]
        assert history_cols == [
            "id", "issue_id", "actor_username", "action", "summary",
            "comment_id", "attachment_id", "created_at",
        ]


def test_optional_site_config_overrides_allowed_values_and_ignores_comments_unknowns(app, tmp_path, monkeypatch):
    config_file = tmp_path / "issues.conf"
    config_file.write_text(
        """
# full-line comments are ignored
DB_FILE=/tmp/site/issues.db # inline comments are ignored
PER_USER_CONFIG_DIR=/tmp/site/config
ASSIGNEE_GROUP=site_assignees
ASSIGNEE_EXCLUDE=skipme
ADMINS_GROUP=site_admins
ADMINS_GROUP_EXCLUDE=blocked_admin
BANNER_FILE=/custom/header.png
BANNER_DIMENSIONS=640x80
MAX_UPLOAD_BYTES=2097152
MAX_FILENAME_LEN=128
DEFAULT_CLOSING_COMMENT=site default close comment
EMAIL_NOTIFICATIONS_ENABLED=yes
SENDMAIL_PATH=/usr/local/sbin/sendmail
NOTIFICATION_FROM=issues@example.test
NOTIFICATION_SUBJECT_PREFIX=[Tracker]
ISSUE_BASE_URL=https://issues.example.test/cgi-bin/issues.cgi
NOTIFICATION_TRIAGE_RECIPIENTS=root,@wheel,helpdesk
NOTIFICATION_BODY_MAX_CHARS=2048
UNKNOWN_VALUE=ignored
AUTH_FORM_ACTION=/bad-login
LOGOUT_URL=/bad-logout
ISSUES_PER_PAGE=3
AUTO_REFRESH_OPTIONS=bad
""".strip(),
        encoding="utf-8",
    )

    monkeypatch.setattr(app, "AUTH_FORM_ACTION", "/login", raising=False)
    monkeypatch.setattr(app, "LOGOUT_URL", "/issues-logout", raising=False)
    monkeypatch.setattr(app, "ISSUES_PER_PAGE", 25, raising=False)
    monkeypatch.setattr(app, "AUTO_REFRESH_OPTIONS", ("never", "5 minutes"), raising=False)
    app.load_site_config(str(config_file))

    assert app.DB_FILE == "/tmp/site/issues.db"
    assert app.PER_USER_CONFIG_DIR == "/tmp/site/config"
    assert app.ASSIGNEE_GROUP == "site_assignees"
    assert app.ASSIGNEE_EXCLUDE == "skipme"
    assert app.ADMINS_GROUP == "site_admins"
    assert app.ADMINS_GROUP_EXCLUDE == "blocked_admin"
    assert app.BANNER_FILE == "/custom/header.png"
    assert app.BANNER_DIMENSIONS == "640x80"
    assert app.MAX_UPLOAD_BYTES == 2097152
    assert app.MAX_FILENAME_LEN == 128
    assert app.DEFAULT_CLOSING_COMMENT == "site default close comment"
    assert app.EMAIL_NOTIFICATIONS_ENABLED is True
    assert app.SENDMAIL_PATH == "/usr/local/sbin/sendmail"
    assert app.NOTIFICATION_FROM == "issues@example.test"
    assert app.NOTIFICATION_SUBJECT_PREFIX == "[Tracker]"
    assert app.ISSUE_BASE_URL == "https://issues.example.test/cgi-bin/issues.cgi"
    assert app.NOTIFICATION_TRIAGE_RECIPIENTS == "root,@wheel,helpdesk"
    assert app.NOTIFICATION_BODY_MAX_CHARS == 2048
    assert app.AUTH_FORM_ACTION == "/login"
    assert app.LOGOUT_URL == "/issues-logout"
    assert app.ISSUES_PER_PAGE == 25
    assert app.AUTO_REFRESH_OPTIONS == ("never", "5 minutes")
    assert not hasattr(app, "UNKNOWN_VALUE")


def test_optional_site_config_missing_file_and_invalid_values_keep_defaults(app, tmp_path, monkeypatch):
    monkeypatch.setattr(app, "DB_FILE", "/var/lib/issues/issues.db", raising=False)
    monkeypatch.setattr(app, "MAX_UPLOAD_BYTES", 10485760, raising=False)
    monkeypatch.setattr(app, "MAX_FILENAME_LEN", 255, raising=False)
    monkeypatch.setattr(app, "BANNER_DIMENSIONS", "", raising=False)
    monkeypatch.setattr(app, "EMAIL_NOTIFICATIONS_ENABLED", False, raising=False)
    monkeypatch.setattr(app, "SENDMAIL_PATH", "/usr/sbin/sendmail", raising=False)
    monkeypatch.setattr(app, "NOTIFICATION_BODY_MAX_CHARS", 8192, raising=False)

    app.load_site_config(str(tmp_path / "missing.conf"))
    assert app.DB_FILE == "/var/lib/issues/issues.db"

    config_file = tmp_path / "bad.conf"
    config_file.write_text(
        """
DB_FILE=
MAX_UPLOAD_BYTES=not-a-number
MAX_FILENAME_LEN=0
BANNER_DIMENSIONS=wide-by-tall
EMAIL_NOTIFICATIONS_ENABLED=maybe
SENDMAIL_PATH=relative/sendmail
NOTIFICATION_BODY_MAX_CHARS=0
""".strip(),
        encoding="utf-8",
    )
    app.load_site_config(str(config_file))

    assert app.DB_FILE == "/var/lib/issues/issues.db"
    assert app.MAX_UPLOAD_BYTES == 10485760
    assert app.MAX_FILENAME_LEN == 255
    assert app.BANNER_DIMENSIONS == ""
    assert app.EMAIL_NOTIFICATIONS_ENABLED is False
    assert app.SENDMAIL_PATH == "/usr/sbin/sendmail"
    assert app.NOTIFICATION_BODY_MAX_CHARS == 8192
