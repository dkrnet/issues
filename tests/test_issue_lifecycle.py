# Copyright (C) 2026 David Redmond
# SPDX-License-Identifier: AGPL-3.0-only
#
"""Requirements mapping: issue creation, assignment, close, cancel, and reopen workflows."""
import sqlite3


def test_successful_issue_creation_uses_acting_user_and_defaults(app, patched_environment, make_form, invoke_action, parse_headers, fetch_issue, temp_db):
    form = make_form(
        action="create",
        title="New regression issue",
        description="Created by pytest",
        priority="normal",
        due_date="",
        assigned_username="bob",
        assignee="bob",
    )
    output = invoke_action(app, "create", form, "alice", method="POST")
    status, headers, body = parse_headers(output)
    joined = status + " " + str(body)
    assert "303" in joined or "302" in joined or "Location" in output

    with sqlite3.connect(temp_db) as con:
        con.row_factory = sqlite3.Row
        row = con.execute("SELECT * FROM issues WHERE title = ?", ("New regression issue",)).fetchone()
    assert row is not None
    assert row["creator_username"] == "alice"
    assert row["assigned_username"] in ("bob", None, "")
    assert row["priority"] == "normal"
    assert row["status"] == "open"
    assert row["pct_complete"] == 0
    assert row["completed_at"] is None


def test_create_rejects_nonassignable_assignee(app, patched_environment, make_form, invoke_action, parse_headers, temp_db):
    form = make_form(
        action="create",
        title="Bad assignee",
        description="Should not be inserted",
        priority="normal",
        assigned_username="mallory",
        assignee="mallory",
    )
    output = invoke_action(app, "create", form, "alice", method="POST")
    status, _, body = parse_headers(output)
    assert "400" in (status + str(body)) or "bad request" in str(body).lower()
    with sqlite3.connect(temp_db) as con:
        count = con.execute("SELECT COUNT(*) FROM issues WHERE title = 'Bad assignee'").fetchone()[0]
    assert count == 0


def test_direct_unauthorized_close_is_rejected_by_backend(app, patched_environment, seed_issue, make_form, invoke_action, parse_headers, fetch_issue):
    issue_id = seed_issue(creator_username="alice", assigned_username="bob", status="open")
    form = make_form(action="close", id=str(issue_id), issue_id=str(issue_id), comment="trying")
    output = invoke_action(app, "close", form, "mallory", method="POST")
    status, _, body = parse_headers(output)
    assert "403" in (status + str(body)) or "forbidden" in str(body).lower()
    assert fetch_issue(issue_id)["status"] == "open"


def test_creator_can_cancel_open_issue(app, patched_environment, seed_issue, make_form, invoke_action, parse_headers, fetch_issue):
    issue_id = seed_issue(creator_username="alice", assigned_username="bob", status="open")
    form = make_form(action="cancel", id=str(issue_id), issue_id=str(issue_id), comment="not needed")
    output = invoke_action(app, "cancel", form, "alice", method="POST")
    status, _, body = parse_headers(output)
    assert "303" in (status + str(body)) or "302" in (status + str(body)) or "Location" in output
    row = fetch_issue(issue_id)
    assert row["status"] == "canceled"
    assert row["completed_at"]


def test_admin_can_reopen_closed_issue(app, patched_environment, seed_issue, make_form, invoke_action, parse_headers, fetch_issue):
    issue_id = seed_issue(creator_username="alice", assigned_username="bob", status="closed", completed_at="2026-01-01T12:10:00")
    form = make_form(action="reopen", id=str(issue_id), issue_id=str(issue_id), comment="reopen")
    output = invoke_action(app, "reopen", form, "admin", method="POST")
    status, _, body = parse_headers(output)
    assert "303" in (status + str(body)) or "302" in (status + str(body)) or "Location" in output
    assert fetch_issue(issue_id)["status"] == "open"


def test_issue_history_records_compact_entries_for_material_actions(app, patched_environment, make_form, invoke_action, parse_headers, fetch_history, fetch_issue, fetch_comments, temp_db):
    create_form = make_form(
        action="create",
        title="History issue",
        description="Initial description",
        priority="normal",
        assigned_username="bob",
    )
    invoke_action(app, "create", create_form, "alice", method="POST")
    with sqlite3.connect(temp_db) as con:
        issue_id = con.execute("SELECT id FROM issues WHERE title = ?", ("History issue",)).fetchone()[0]

    history = fetch_history(issue_id)
    assert len(history) == 1
    assert history[0]["action"] == "created"
    assert history[0]["summary"] == "Created issue"

    invoke_action(app, "assign", make_form(action="assign", id=str(issue_id), assigned_username="admin"), "alice", method="POST")
    invoke_action(app, "set_priority", make_form(action="set_priority", id=str(issue_id), priority="high"), "alice", method="POST")
    invoke_action(app, "set_due_date", make_form(action="set_due_date", id=str(issue_id), due_date="2099-06-01"), "alice", method="POST")
    invoke_action(app, "set_percent_complete", make_form(action="set_percent_complete", id=str(issue_id), pct_complete="40"), "admin", method="POST")
    invoke_action(app, "set_state", make_form(action="set_state", id=str(issue_id), state="complete"), "admin", method="POST")

    actions = [row["action"] for row in reversed(fetch_history(issue_id))]
    assert actions[:6] == [
        "created", "assigned", "priority_changed", "due_date_changed",
        "percent_complete_changed", "state_changed",
    ]
    assert fetch_issue(issue_id)["pct_complete"] == 100

    invoke_action(app, "close", make_form(action="close", id=str(issue_id), closing_comment="closing"), "alice", method="POST")
    invoke_action(app, "reopen", make_form(action="reopen", id=str(issue_id), comment="reopen"), "admin", method="POST")
    invoke_action(app, "cancel", make_form(action="cancel", id=str(issue_id), cancel_comment="cancel"), "alice", method="POST")

    actions = [row["action"] for row in reversed(fetch_history(issue_id))]
    assert "closed" in actions
    assert "reopened" in actions
    assert "canceled" in actions
    assert actions.count("comment_added") == 0

    comments_by_text = {row["comment_text"]: row["id"] for row in fetch_comments(issue_id)}
    history_by_action = {row["action"]: row for row in fetch_history(issue_id)}
    assert history_by_action["closed"]["comment_id"] == comments_by_text["closing"]
    assert history_by_action["closed"]["summary"] == "Closed issue with comment"
    assert history_by_action["canceled"]["comment_id"] == comments_by_text["cancel"]
    assert history_by_action["canceled"]["summary"] == "Canceled issue with comment"


def test_issue_history_comment_attachment_and_update_entries_are_compact(app, patched_environment, seed_issue, make_form, invoke_action, fetch_history, fetch_comments, fetch_attachments, temp_db):
    issue_id = seed_issue(
        title="Old title",
        description="Old line one\nOld line two",
        creator_username="alice",
        assigned_username="bob",
        status="open",
    )

    long_comment = "comment body that should not be duplicated in history"
    invoke_action(app, "comment", make_form(action="comment", id=str(issue_id), comment_text=long_comment), "alice", method="POST")
    comment_id = fetch_comments(issue_id)[0]["id"]
    comment_history = fetch_history(issue_id)[0]
    assert comment_history["action"] == "comment_added"
    assert comment_history["comment_id"] == comment_id
    assert long_comment not in comment_history["summary"]

    from conftest import Field
    form = make_form(action="attach", id=str(issue_id))
    form._fields["file"] = Field(value="", filename="history.txt", file_bytes=b"attachment content that should not be duplicated")
    invoke_action(app, "attach", form, "bob", method="POST")
    attachment_id = fetch_attachments(issue_id)[0]["id"]
    attach_history = fetch_history(issue_id)[0]
    assert attach_history["action"] == "attachment_added"
    assert attach_history["attachment_id"] == attachment_id
    assert "history.txt" in attach_history["summary"]
    assert "attachment content" not in attach_history["summary"]

    new_description = "New description line one\nNew description line two\nNew description line three"
    invoke_action(app, "update", make_form(action="update", id=str(issue_id), title="New title", description=new_description), "alice", method="POST")
    update_history = fetch_history(issue_id)[0]
    assert update_history["action"] == "updated"
    assert "Changed title" in update_history["summary"]
    assert "Updated description" in update_history["summary"]
    assert "Old line one" not in update_history["summary"]
    assert "New description line one" not in update_history["summary"]
    assert "characters" in update_history["summary"]


def test_issue_history_is_not_recorded_for_views_lists_or_downloads(app, patched_environment, seed_issue, seed_attachment, make_form, invoke_action, fetch_history):
    issue_id = seed_issue(creator_username="alice", assigned_username="bob", status="open")
    attachment_id = seed_attachment(issue_id, filename="download.txt")

    invoke_action(app, "list", make_form(action="list"), "alice")
    invoke_action(app, "view", make_form(action="view", id=str(issue_id)), "alice")
    invoke_action(app, "download", make_form(action="download", id=str(attachment_id)), "alice")

    assert fetch_history(issue_id) == []
