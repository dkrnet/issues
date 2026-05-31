# Copyright (C) 2026 David Redmond
# SPDX-License-Identifier: AGPL-3.0-only
#
import subprocess


def _history_actions(fetch_history, issue_id):
    return [row["action"] for row in fetch_history(issue_id)]


def test_notifications_disabled_by_default_do_not_invoke_mail(app, patched_environment, monkeypatch, seed_issue, make_form, invoke_action, fetch_history):
    calls = []

    def fake_run(*args, **kwargs):
        calls.append((args, kwargs))
        raise AssertionError("mail command should not be invoked when notifications are disabled")

    monkeypatch.setattr(app.subprocess, "run", fake_run, raising=False)
    issue_id = seed_issue(creator_username="alice", assigned_username="", status="open")

    invoke_action(app, "assign", make_form(action="assign", id=str(issue_id), assigned_username="bob"), "alice", method="POST")

    assert calls == []
    assert "email_sent" not in _history_actions(fetch_history, issue_id)


def test_assignment_notification_uses_local_sendmail_and_records_compact_history(app, patched_environment, monkeypatch, seed_issue, make_form, invoke_action, fetch_history):
    sent = []

    def fake_run(cmd, input=None, check=False):
        sent.append((cmd, input, check))
        return subprocess.CompletedProcess(cmd, 0)

    monkeypatch.setattr(app.subprocess, "run", fake_run, raising=False)
    monkeypatch.setattr(app, "EMAIL_NOTIFICATIONS_ENABLED", True, raising=False)
    monkeypatch.setattr(app, "SENDMAIL_PATH", "/tmp/fake-sendmail", raising=False)
    monkeypatch.setattr(app, "NOTIFICATION_FROM", "issues@example.test", raising=False)
    monkeypatch.setattr(app, "NOTIFICATION_SUBJECT_PREFIX", "[Tracker]", raising=False)
    monkeypatch.setattr(app, "ISSUE_BASE_URL", "https://issues.example.test/cgi-bin/issues.cgi", raising=False)

    issue_id = seed_issue(title="Notify assignment", creator_username="alice", assigned_username="", status="open")
    invoke_action(app, "assign", make_form(action="assign", id=str(issue_id), assigned_username="bob"), "alice", method="POST")

    assert len(sent) == 1
    cmd, message, check = sent[0]
    assert cmd == ["/tmp/fake-sendmail", "-t", "-oi"]
    assert check is True
    assert b"To: bob" in message
    assert b"From: issues@example.test" in message
    assert b"Subject: [Tracker]" in message
    assert b"https://issues.example.test/cgi-bin/issues.cgi?action=view" in message

    history = fetch_history(issue_id)
    email_rows = [row for row in history if row["action"] == "email_sent"]
    assert len(email_rows) == 1
    assert email_rows[0]["summary"] == "Notification email sent to bob"
    assert "Subject:" not in email_rows[0]["summary"]
    assert "Notify assignment" not in email_rows[0]["summary"]


def test_comment_notification_excludes_commenter_and_uses_creator_and_assignee(app, patched_environment, monkeypatch, seed_issue, make_form, invoke_action, fetch_history):
    sent = []

    def fake_run(cmd, input=None, check=False):
        sent.append(input)
        return subprocess.CompletedProcess(cmd, 0)

    monkeypatch.setattr(app.subprocess, "run", fake_run, raising=False)
    monkeypatch.setattr(app, "EMAIL_NOTIFICATIONS_ENABLED", True, raising=False)

    issue_id = seed_issue(title="Notify comment", creator_username="alice", assigned_username="bob", status="open")
    invoke_action(app, "comment_submit", make_form(action="comment_submit", id=str(issue_id), comment_text="Please review this."), "admin", method="POST")

    assert len(sent) == 1
    assert b"To: alice, bob" in sent[0]
    email_rows = [row for row in fetch_history(issue_id) if row["action"] == "email_sent"]
    assert len(email_rows) == 1
    assert email_rows[0]["summary"] == "Notification email sent to alice, bob"


def test_due_close_reopen_notifications_use_required_recipients(app, patched_environment, monkeypatch, seed_issue, make_form, invoke_action, fetch_history):
    sent = []

    def fake_run(cmd, input=None, check=False):
        sent.append(input)
        return subprocess.CompletedProcess(cmd, 0)

    monkeypatch.setattr(app.subprocess, "run", fake_run, raising=False)
    monkeypatch.setattr(app, "EMAIL_NOTIFICATIONS_ENABLED", True, raising=False)

    issue_id = seed_issue(title="Notify due close reopen", creator_username="alice", assigned_username="bob", status="open", due_date="2026-06-01")
    invoke_action(app, "set_due_date", make_form(action="set_due_date", id=str(issue_id), due_date="2026-06-30"), "alice", method="POST")
    invoke_action(app, "close_submit", make_form(action="close_submit", id=str(issue_id), closing_comment="Done"), "bob", method="POST")
    invoke_action(app, "reopen", make_form(action="reopen", id=str(issue_id), comment="Needs more work"), "admin", method="POST")

    assert len(sent) == 3
    assert b"To: bob" in sent[0]
    assert b"To: alice" in sent[1]
    assert b"To: alice, bob" in sent[2]
    summaries = [row["summary"] for row in fetch_history(issue_id) if row["action"] == "email_sent"]
    assert "Notification email sent to bob" in summaries
    assert "Notification email sent to alice" in summaries
    assert "Notification email sent to alice, bob" in summaries


def test_notification_failure_does_not_roll_back_or_return_internal_error(app, patched_environment, monkeypatch, seed_issue, make_form, invoke_action, parse_headers, fetch_issue, fetch_history):
    def fake_run(cmd, input=None, check=False):
        raise subprocess.CalledProcessError(1, cmd)

    monkeypatch.setattr(app.subprocess, "run", fake_run, raising=False)
    monkeypatch.setattr(app, "EMAIL_NOTIFICATIONS_ENABLED", True, raising=False)

    issue_id = seed_issue(title="Mail failure", creator_username="alice", assigned_username="", status="open")
    output = invoke_action(app, "assign", make_form(action="assign", id=str(issue_id), assigned_username="bob"), "alice", method="POST")
    status, headers, _body = parse_headers(output)

    assert status.startswith("303") or status.startswith("302")
    assert fetch_issue(issue_id)["assigned_username"] == "bob"
    assert "assigned" in _history_actions(fetch_history, issue_id)
    assert "email_sent" not in _history_actions(fetch_history, issue_id)


def test_unassigned_issue_creation_uses_triage_recipients(app, patched_environment, monkeypatch, make_form, invoke_action, fetch_history):
    sent = []

    def fake_run(cmd, input=None, check=False):
        sent.append(input)
        return subprocess.CompletedProcess(cmd, 0)

    monkeypatch.setattr(app.subprocess, "run", fake_run, raising=False)
    monkeypatch.setattr(app, "EMAIL_NOTIFICATIONS_ENABLED", True, raising=False)
    monkeypatch.setattr(app, "NOTIFICATION_TRIAGE_RECIPIENTS", "root, @wheel, root", raising=False)

    invoke_action(
        app,
        "create",
        make_form(action="create", title="Unassigned triage", description="Needs review", priority="normal", assigned_username=""),
        "alice",
        method="POST",
    )

    assert len(sent) == 1
    assert b"To: root, admin" in sent[0]
    email_rows = []
    for issue_id in (1,):
        email_rows.extend(row for row in fetch_history(issue_id) if row["action"] == "email_sent")
    assert email_rows[0]["summary"] == "Notification email sent to root, admin"


def test_unassigned_triage_excludes_actor_and_sends_nothing_when_empty(app, patched_environment, monkeypatch, make_form, invoke_action, fetch_history):
    sent = []

    def fake_run(cmd, input=None, check=False):
        sent.append(input)
        return subprocess.CompletedProcess(cmd, 0)

    monkeypatch.setattr(app.subprocess, "run", fake_run, raising=False)
    monkeypatch.setattr(app, "EMAIL_NOTIFICATIONS_ENABLED", True, raising=False)
    monkeypatch.setattr(app, "NOTIFICATION_TRIAGE_RECIPIENTS", "alice", raising=False)

    invoke_action(
        app,
        "create",
        make_form(action="create", title="No recipient", description="Actor only triage", priority="normal", assigned_username=""),
        "alice",
        method="POST",
    )

    assert sent == []
    assert "email_sent" not in _history_actions(fetch_history, 1)


def test_comment_update_and_attachment_notification_bodies_include_expected_context_with_caps(app, patched_environment, monkeypatch, seed_issue, make_form, invoke_action):
    from conftest import Field

    sent = []

    def fake_run(cmd, input=None, check=False):
        sent.append(input)
        return subprocess.CompletedProcess(cmd, 0)

    monkeypatch.setattr(app.subprocess, "run", fake_run, raising=False)
    monkeypatch.setattr(app, "EMAIL_NOTIFICATIONS_ENABLED", True, raising=False)
    monkeypatch.setattr(app, "NOTIFICATION_BODY_MAX_CHARS", 12, raising=False)

    issue_id = seed_issue(title="Notify body", description="Initial description", creator_username="alice", assigned_username="bob", status="open")

    invoke_action(
        app,
        "comment_submit",
        make_form(action="comment_submit", id=str(issue_id), comment_text="abcdefghijklmnopqrstuvwxyz"),
        "admin",
        method="POST",
    )
    invoke_action(
        app,
        "update_submit",
        make_form(action="update_submit", id=str(issue_id), title="Updated title for notification", description="Updated description for notification body"),
        "alice",
        method="POST",
    )
    invoke_action(
        app,
        "attach_submit",
        make_form(action="attach_submit", id=str(issue_id), file=Field(filename="evidence.txt", file_bytes=b"file bytes are not mailed")),
        "admin",
        method="POST",
    )

    assert len(sent) == 3
    assert b"Comment:\nabcdefghijkl" in sent[0]
    assert b"content truncated" in sent[0]
    assert b"Updated title:\nUpdated titl" in sent[1]
    assert b"Updated description:\nUpdated desc" in sent[1]
    assert b"Attachment:" in sent[2]
    assert b"Filename: evidence.txt" in sent[2]
    assert b"Uploaded by: admin" in sent[2]
    assert b"Size: 25 bytes" in sent[2]
    assert b"file bytes are not mailed" not in sent[2]

def test_reassignment_notification_includes_previous_assignee_except_actor(app, patched_environment, monkeypatch, seed_issue, make_form, invoke_action, fetch_history):
    sent = []

    def fake_run(cmd, input=None, check=False):
        sent.append(input)
        return subprocess.CompletedProcess(cmd, 0)

    monkeypatch.setattr(app.subprocess, "run", fake_run, raising=False)
    monkeypatch.setattr(app, "EMAIL_NOTIFICATIONS_ENABLED", True, raising=False)

    issue_id = seed_issue(title="Reassign notify", creator_username="alice", assigned_username="bob", status="open")
    invoke_action(app, "assign", make_form(action="assign", id=str(issue_id), assigned_username="admin"), "alice", method="POST")

    assert len(sent) == 1
    assert b"To: admin, bob" in sent[0]
    summaries = [row["summary"] for row in fetch_history(issue_id) if row["action"] == "email_sent"]
    assert "Notification email sent to admin, bob" in summaries

    sent.clear()
    issue_id = seed_issue(title="Reassign actor excluded", creator_username="bob", assigned_username="bob", status="open")
    invoke_action(app, "assign", make_form(action="assign", id=str(issue_id), assigned_username="admin"), "bob", method="POST")

    assert len(sent) == 1
    assert b"To: admin" in sent[0]
    assert b"To: admin, bob" not in sent[0]
