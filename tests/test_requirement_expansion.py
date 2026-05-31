# Copyright (C) 2026 David Redmond
# SPDX-License-Identifier: AGPL-3.0-only
#
"""Requirements mapping: expanded coverage for current issues.cgi and regression-test requirements.

This module adds focused checks for issue-list fields, open-only inline editing,
form rendering, direct backend authorization, Markdown help behavior, timestamp
formatting, per-user preferences, and issue lifecycle side effects.
"""

import datetime as dt
import json
import sqlite3

import pytest

from conftest import Field, call_flex, find_callable


def text_body(parse_headers, output):
    body = parse_headers(output)[2]
    return body.decode("utf-8", "replace") if isinstance(body, bytes) else body


def joined_status_body(parse_headers, output):
    status, _headers, body = parse_headers(output)
    body_text = body.decode("utf-8", "replace") if isinstance(body, bytes) else str(body)
    return (status + " " + body_text).lower()


def assert_redirect(parse_headers, output):
    status, headers, body = parse_headers(output)
    joined = status + " " + str(body)
    assert "location" in headers or "303" in joined or "302" in joined


def assert_client_or_forbidden(parse_headers, output, *codes):
    joined = joined_status_body(parse_headers, output)
    expected = codes or ("400", "403", "404")
    assert any(code in joined for code in expected), joined


def make_upload_form(form, filename="auth-check.txt", file_bytes=b"payload"):
    form._fields["file"] = Field(value="", filename=filename, file_bytes=file_bytes)
    form._fields["attachment"] = form._fields["file"]
    return form


def test_issue_list_displays_percent_complete_column_values_counts_and_id_order(app, patched_environment, seed_issue, seed_comment, seed_attachment, invoke_action, parse_headers):
    first = seed_issue(title="Older", pct_complete=12, creator_username="alice", assigned_username="bob")
    second = seed_issue(title="Newer", pct_complete=87, creator_username="alice", assigned_username="bob")
    seed_comment(first)
    seed_attachment(first)

    output = invoke_action(app, "list", user="alice")
    html = text_body(parse_headers, output)
    lower = html.lower()

    header_row = html[html.find("<thead><tr>"):html.find("</tr></thead>") + len("</tr></thead>")]
    expected_headers = [
        "<th>ID</th>", "<th>Title</th>", "<th>Status</th>",
        "<th>Due</th>", "<th>Priority</th>", "<th>Creator</th>",
        "<th>Assignee</th>", "<th>State</th>", "<th>% Complete</th>",
        "<th>Comments</th>", "<th>Attachments</th>", "<th>Updated</th>",
    ]
    positions = [header_row.find(header) for header in expected_headers]
    assert all(pos >= 0 for pos in positions), header_row
    assert positions == sorted(positions), header_row
    assert "<th>Assigned</th>" not in header_row
    assert "percent complete" in lower or "% complete" in lower
    assert ">87<" in html or "87" in html
    assert ">12<" in html or "12" in html
    assert "comments" in lower and "attachments" in lower
    assert html.find("Newer") < html.find("Older")


def test_issue_list_preferences_apply_status_priority_and_admin_creator_filter(app, patched_environment, seed_issue, write_config, invoke_action, make_form, parse_headers, temp_config_dir):
    seed_issue(title="Alice high", creator_username="alice", assigned_username="bob", priority="high", status="open")
    seed_issue(title="Mallory high", creator_username="mallory", assigned_username="", priority="high", status="open")
    seed_issue(title="Closed high", creator_username="alice", assigned_username="bob", priority="high", status="closed")

    write_config("admin", {"status": "open", "priority": "high", "creator": "alice", "all": True})
    admin_html = text_body(parse_headers, invoke_action(app, "list", make_form(action="list"), "admin"))
    assert "Alice high" in admin_html
    assert "Mallory high" not in admin_html
    assert "Closed high" not in admin_html
    assert "all users issues" not in admin_html.lower()

    invoke_action(app, "list", make_form(action="list", status="closed", priority="any", creator="any"), "admin")
    saved = json.loads((temp_config_dir / "admin.json").read_text(encoding="utf-8"))
    assert saved["status"] == "closed"
    assert saved["priority"] == "any"
    assert saved["creator"] == "any"
    assert "all" not in saved

    write_config("alice", {"status": "open", "priority": "any", "creator": "mallory", "all": True})
    alice_html = text_body(parse_headers, invoke_action(app, "list", make_form(action="list"), "alice"))
    assert "Mallory high" not in alice_html
    assert "all users issues" not in alice_html.lower()


def test_issue_list_ignores_invalid_stored_preferences(app, patched_environment, write_config, invoke_action, make_form, parse_headers):
    write_config("alice", {"status": "nonsense", "priority": "urgent", "creator": "mallory", "assignee": "vwboot", "state": "bogus", "due_date": "yesterday", "has_comments": "yes", "has_attachments": "yes", "all": "yes"})
    output = invoke_action(app, "list", make_form(action="list"), "alice")
    html = text_body(parse_headers, output).lower()
    assert "issue list" in html
    assert 'name="status"' in html and 'name="priority"' in html
    assert "all users issues" not in html


def test_issue_view_metadata_ordering_timestamps_blank_due_and_consistent_actions(app, patched_environment, seed_issue, seed_comment, seed_attachment, invoke_action, make_form, parse_headers):
    issue_id = seed_issue(
        status="closed",
        due_date=None,
        created_at="2026-01-01T12:00:00+00:00",
        updated_at="2026-01-01T12:05:00+00:00",
        completed_at="2026-01-01T12:10:00+00:00",
    )
    seed_comment(issue_id, text="older", created_at="2026-01-01T12:01:00+00:00")
    seed_comment(issue_id, text="newer", created_at="2026-01-01T12:02:00+00:00")
    seed_attachment(issue_id, filename="a.txt", created_at="2026-01-01T12:01:00+00:00")
    seed_attachment(issue_id, filename="b.txt", created_at="2026-01-01T12:02:00+00:00")

    html = text_body(parse_headers, invoke_action(app, "view", make_form(action="view", id=str(issue_id)), "admin"))
    lower = html.lower()
    assert "description" in lower and "comments" in lower and "attachments" in lower
    assert "completed" in lower
    assert html.find("newer") < html.find("older")
    assert html.find("a.txt") < html.find("b.txt")
    assert 'class="local-timestamp"' in html
    assert 'data-utc="2026-01-01T12:00:00Z"' in html
    assert "Intl.DateTimeFormat" in html
    assert 'timeZoneName: "short"' in html
    assert "YYYY-MM-DD" not in html
    assert "<th>Assignee</th>" in html
    assert "<th>Assigned</th>" not in html

    actions_start = html.find('<div class="actions"')
    actions_end = html.find("</div>", actions_start)
    actions = html[actions_start:actions_end]
    assert "<form" in actions
    assert "<a " not in actions.lower()


def test_issue_view_role_controls_are_precise_for_open_and_closed_issues(app, patched_environment, seed_issue, invoke_action, make_form, parse_headers):
    open_id = seed_issue(creator_username="alice", assigned_username="bob", status="open")
    closed_id = seed_issue(creator_username="alice", assigned_username="bob", status="closed", completed_at="2026-01-01T12:00:00+00:00")

    creator_open = text_body(parse_headers, invoke_action(app, "view", make_form(action="view", id=str(open_id)), "alice"))
    assigned_open = text_body(parse_headers, invoke_action(app, "view", make_form(action="view", id=str(open_id)), "bob"))
    admin_closed = text_body(parse_headers, invoke_action(app, "view", make_form(action="view", id=str(closed_id)), "admin"))
    creator_closed = text_body(parse_headers, invoke_action(app, "view", make_form(action="view", id=str(closed_id)), "alice"))

    assert "Edit Title" in creator_open
    assert "Cancel" in creator_open
    assert 'name="assigned_username"' in creator_open
    assert "Assignee" in creator_open
    assert "Assigned user" not in creator_open
    assert 'name="priority"' in creator_open
    assert 'name="due_date"' in creator_open
    assert "Close" in assigned_open
    assert 'name="pct_complete"' in assigned_open
    assert 'name="state"' in assigned_open
    assert "Re-open" in admin_closed
    assert "Edit Title" not in creator_closed
    assert 'name="priority"' not in creator_closed
    assert 'name="pct_complete"' not in creator_closed
    assert 'name="state"' not in creator_closed
    assert 'name="due_date"' not in creator_closed


def test_inline_buttons_start_disabled_and_onchange_controls_submit(app, patched_environment, seed_issue, invoke_action, make_form, parse_headers):
    issue_id = seed_issue(creator_username="alice", assigned_username="bob", status="open")
    assigned_html = text_body(parse_headers, invoke_action(app, "view", make_form(action="view", id=str(issue_id)), "bob"))
    creator_html = text_body(parse_headers, invoke_action(app, "view", make_form(action="view", id=str(issue_id)), "alice"))
    assert 'name="pct_complete"' in assigned_html and "disabled" in assigned_html
    assert 'name="due_date"' in creator_html and "disabled" in creator_html
    assert 'name="state"' in assigned_html and "this.form.submit()" in assigned_html
    assert 'name="assigned_username"' in creator_html and "this.form.submit()" in creator_html
    assert 'name="priority"' in creator_html and "this.form.submit()" in creator_html


@pytest.mark.parametrize("action,label", [
    ("create", "Create issue"),
    ("comment", "Add comment"),
    ("update", "Update issue"),
    ("close", "Close issue"),
    ("cancel", "Cancel issue"),
])
def test_markdown_forms_render_required_fields_and_new_tab_help(app, patched_environment, seed_issue, invoke_action, make_form, parse_headers, action, label):
    issue_id = seed_issue(creator_username="alice", assigned_username="bob", status="open")
    user = "alice"
    form = make_form(action=action, id=str(issue_id)) if action != "create" else make_form(action=action)
    output = invoke_action(app, action, form, user)
    html = text_body(parse_headers, output)
    lower = html.lower()
    assert "markdown help" in lower
    assert 'target="_blank"' in lower
    assert "noopener" in lower and "noreferrer" in lower
    assert label.lower() in lower
    if action == "create":
        for fragment in ('name="title"', 'name="description"', 'name="priority"', 'name="due_date"', 'name="assigned_username"'):
            assert fragment in lower
        assert ">alice<" in html and ">bob<" in html and "vwboot" not in html
    elif action in {"comment", "close", "cancel"}:
        assert "<textarea" in lower
    elif action == "update":
        assert 'name="title"' in lower and 'name="description"' in lower


def test_markdown_help_page_contains_examples_and_real_lists(app, patched_environment, invoke_action, make_form, parse_headers):
    html = text_body(parse_headers, invoke_action(app, "markdown_help", make_form(action="markdown_help"), "alice"))
    lower = html.lower()
    assert "markdown help" in lower
    assert 'class="banner"' not in lower
    assert "raw markdown" in lower
    assert "supported markdown syntax" in lower

    unordered_label = lower.find("<strong>unordered list:</strong>")
    ordered_label = lower.find("<strong>ordered list:</strong>")
    raw_example = lower.find("<h2>raw markdown example</h2>")
    assert unordered_label >= 0, html
    assert ordered_label >= 0, html
    assert raw_example > ordered_label, html

    rendered_region = lower[unordered_label:raw_example]
    unordered_index = rendered_region.find("<ul")
    ordered_index = rendered_region.find("<ol")
    assert unordered_index >= 0, "Bulleted-list help items must render as real list items."
    assert "<li>bulleted list item</li>" in rendered_region
    assert "<li>another item</li>" in rendered_region
    assert ordered_index >= 0, "Numbered-list help items must render as real list items."
    assert "<li>numbered item</li>" in rendered_region
    assert "<li>another numbered item</li>" in rendered_region
    assert unordered_index < ordered_index, "Bulleted and numbered examples must remain separate lists."
    assert "<p>- bulleted list item" not in rendered_region
    assert "<p>1. numbered item" not in rendered_region
    assert "<h2>bulleted list</h2>" not in lower
    assert "<h2>numbered list</h2>" not in lower
    assert "<del>strikethrough</del>" in lower


def test_markdown_strikethrough_renders_like_gitlab_and_escapes_html(app, patched_environment, seed_issue, make_form, invoke_action, parse_headers):
    issue_id = seed_issue(creator_username="alice", assigned_username="bob", status="open", description="Keep ~~old text~~ and ~~<script>x</script>~~")
    html = text_body(parse_headers, invoke_action(app, "view", make_form(action="view", id=str(issue_id), issue_id=str(issue_id)), "alice"))
    lower = html.lower()
    assert "<del>old text</del>" in lower
    assert "<script>x</script>" not in lower
    assert "<del>&lt;script&gt;x&lt;/script&gt;</del>" in lower


def test_create_submission_validation_defaults_empty_assignee_and_redirect(app, patched_environment, make_form, invoke_action, parse_headers, fetch_issue, temp_db):
    bad_cases = [
        {"title": "", "description": "body", "priority": "normal", "assigned_username": "bob"},
        {"title": "Title", "description": "", "priority": "normal", "assigned_username": "bob"},
        {"title": "Title", "description": "body", "priority": "urgent", "assigned_username": "bob"},
        {"title": "Title", "description": "body", "priority": "normal", "assigned_username": "nobody"},
        {"title": "Title", "description": "body", "priority": "normal", "assigned_username": "mallory"},
        {"title": "Title", "description": "body", "priority": "normal", "assigned_username": "vwboot"},
    ]
    for fields in bad_cases:
        assert_client_or_forbidden(parse_headers, invoke_action(app, "create", make_form(action="create", **fields), "alice", method="POST"), "400")

    output = invoke_action(app, "create", make_form(action="create", title="Unassigned", description="body", priority="normal", due_date="", assigned_username=""), "alice", method="POST")
    assert_redirect(parse_headers, output)
    with sqlite3.connect(temp_db) as con:
        con.row_factory = sqlite3.Row
        row = con.execute("SELECT * FROM issues WHERE title = 'Unassigned'").fetchone()
    assert row["creator_username"] == "alice"
    assert row["assigned_username"] in ("", None)
    assert row["status"] == "open"
    assert row["state"] == "not started"
    assert row["pct_complete"] == 0
    assert row["created_at"] and row["updated_at"] and row["completed_at"] is None


def test_assignment_permissions_validation_persistence_and_redirect(app, patched_environment, seed_issue, make_form, invoke_action, parse_headers, fetch_issue):
    issue_id = seed_issue(creator_username="alice", assigned_username="bob", status="open")
    assert_redirect(parse_headers, invoke_action(app, "assign", make_form(action="assign", id=str(issue_id), assigned_username="admin"), "alice", method="POST"))
    assert fetch_issue(issue_id)["assigned_username"] == "admin"
    assert_redirect(parse_headers, invoke_action(app, "assign", make_form(action="assign", id=str(issue_id), assigned_username="bob"), "admin", method="POST"))
    for user in ("bob", "mallory"):
        assert_client_or_forbidden(parse_headers, invoke_action(app, "assign", make_form(action="assign", id=str(issue_id), assigned_username="alice"), user, method="POST"), "403")
    for bad in ("nobody", "mallory", "vwboot"):
        assert_client_or_forbidden(parse_headers, invoke_action(app, "assign", make_form(action="assign", id=str(issue_id), assigned_username=bad), "alice", method="POST"), "400")
    closed_id = seed_issue(creator_username="alice", assigned_username="bob", status="closed")
    canceled_id = seed_issue(creator_username="alice", assigned_username="bob", status="canceled")
    for issue_id in (closed_id, canceled_id):
        assert_client_or_forbidden(parse_headers, invoke_action(app, "assign", make_form(action="assign", id=str(issue_id), assigned_username="bob"), "alice", method="POST"), "400")


def test_comment_form_and_submission_status_sensitive_permissions(app, patched_environment, seed_issue, make_form, invoke_action, parse_headers, fetch_comments):
    open_id = seed_issue(creator_username="alice", assigned_username="bob", status="open")
    closed_id = seed_issue(creator_username="alice", assigned_username="bob", status="closed")
    for user in ("alice", "bob", "admin"):
        html = text_body(parse_headers, invoke_action(app, "comment", make_form(action="comment", id=str(open_id)), user))
        assert 'name="comment_text"' in html
    assert_client_or_forbidden(parse_headers, invoke_action(app, "comment", make_form(action="comment", id=str(open_id)), "mallory"), "403")
    assert_client_or_forbidden(parse_headers, invoke_action(app, "comment", make_form(action="comment", id=str(closed_id)), "alice"), "403")
    assert 'name="comment_text"' in text_body(parse_headers, invoke_action(app, "comment", make_form(action="comment", id=str(closed_id)), "admin"))
    for text in ("", "   "):
        assert_client_or_forbidden(parse_headers, invoke_action(app, "comment", make_form(action="comment", id=str(open_id), comment_text=text), "alice", method="POST"), "400")
    output = invoke_action(app, "comment", make_form(action="comment", id=str(open_id), comment_text="**raw**"), "bob", method="POST")
    assert_redirect(parse_headers, output)
    assert fetch_comments(open_id)[0]["comment_text"] == "**raw**"


def test_attachment_form_submission_download_and_validation(app, patched_environment, seed_issue, make_form, invoke_action, parse_headers, fetch_attachments, monkeypatch):
    issue_id = seed_issue(creator_username="alice", assigned_username="bob", status="open")
    html = text_body(parse_headers, invoke_action(app, "attach", make_form(action="attach", id=str(issue_id)), "alice"))
    assert 'type="file"' in html and "Maximum upload size" in html and "MB" in html
    assert_client_or_forbidden(parse_headers, invoke_action(app, "attach", make_form(action="attach"), "alice", method="POST"), "400")
    assert_client_or_forbidden(parse_headers, invoke_action(app, "attach", make_form(action="attach", id=str(issue_id)), "alice", method="POST"), "400")

    form = make_form(action="attach", id=str(issue_id))
    form._fields["file"] = Field(value="", filename="../../unsafe name.txt", file_bytes=b"payload")
    output = invoke_action(app, "attach", form, "bob", method="POST")
    assert_redirect(parse_headers, output)
    attachments = fetch_attachments(issue_id)
    assert attachments[0]["content"] == b"payload"
    assert "/" not in attachments[0]["filename"] and ".." not in attachments[0]["filename"]

    aid = attachments[0]["id"]
    assert_client_or_forbidden(parse_headers, invoke_action(app, "download", make_form(action="download"), "alice"), "400")
    assert_client_or_forbidden(parse_headers, invoke_action(app, "download", make_form(action="download", id="99999"), "alice"), "404")
    for user in ("alice", "bob", "admin"):
        status, headers, body = parse_headers(invoke_action(app, "download", make_form(action="download", id=str(aid)), user))
        assert "content-disposition" in headers
        assert "unsafe" in headers["content-disposition"] and ".." not in headers["content-disposition"]
        assert b"payload" in body if isinstance(body, bytes) else "payload" in body
    assert_client_or_forbidden(parse_headers, invoke_action(app, "download", make_form(action="download", id=str(aid)), "mallory"), "403")

    monkeypatch.setattr(app, "MAX_UPLOAD_BYTES", 3, raising=False)
    too_big = make_form(action="attach", id=str(issue_id))
    too_big._fields["file"] = Field(value="", filename="big.txt", file_bytes=b"four")
    assert_client_or_forbidden(parse_headers, invoke_action(app, "attach", too_big, "alice", method="POST"), "400")


def test_update_form_and_submission_enforce_open_issue_authorization_and_title_rules(app, patched_environment, seed_issue, make_form, invoke_action, parse_headers, fetch_issue):
    open_id = seed_issue(creator_username="alice", assigned_username="bob", status="open", title="Old", description="Old desc")
    closed_id = seed_issue(creator_username="alice", assigned_username="bob", status="closed")
    html = text_body(parse_headers, invoke_action(app, "update", make_form(action="update", id=str(open_id)), "alice"))
    assert 'name="title"' in html and "Old" in html and 'name="description"' in html
    assert_client_or_forbidden(parse_headers, invoke_action(app, "update", make_form(action="update", id=str(open_id)), "bob"), "403")
    assert_client_or_forbidden(parse_headers, invoke_action(app, "update", make_form(action="update", id=str(closed_id)), "alice"), "400")
    assert_client_or_forbidden(parse_headers, invoke_action(app, "update", make_form(action="update", id=str(open_id), title=""), "alice", method="POST"), "400")
    assert_redirect(parse_headers, invoke_action(app, "update", make_form(action="update", id=str(open_id), title="New"), "admin", method="POST"))
    assert fetch_issue(open_id)["title"] == "New"
    assert fetch_issue(open_id)["description"] == "Old desc"
    assert_redirect(parse_headers, invoke_action(app, "update", make_form(action="update", id=str(open_id), title="New2", description="Desc2"), "alice", method="POST"))
    assert fetch_issue(open_id)["description"] == "Desc2"


def test_inline_priority_due_percent_and_state_validation_permissions_and_redirects(app, patched_environment, seed_issue, make_form, invoke_action, parse_headers, fetch_issue):
    issue_id = seed_issue(creator_username="alice", assigned_username="bob", status="open", priority="normal", pct_complete=10, state="not started")
    closed_id = seed_issue(creator_username="alice", assigned_username="bob", status="closed")
    canceled_id = seed_issue(creator_username="alice", assigned_username="bob", status="canceled")

    assert_redirect(parse_headers, invoke_action(app, "set_priority", make_form(action="set_priority", id=str(issue_id), priority="high"), "alice", method="POST"))
    assert fetch_issue(issue_id)["priority"] == "high"
    assert_redirect(parse_headers, invoke_action(app, "set_priority", make_form(action="set_priority", id=str(issue_id), priority="low"), "admin", method="POST"))
    for user in ("bob", "mallory"):
        assert_client_or_forbidden(parse_headers, invoke_action(app, "set_priority", make_form(action="set_priority", id=str(issue_id), priority="normal"), user, method="POST"), "403")
    for bad_id in (closed_id, canceled_id):
        assert_client_or_forbidden(parse_headers, invoke_action(app, "set_priority", make_form(action="set_priority", id=str(bad_id), priority="normal"), "alice", method="POST"), "400")
    assert_client_or_forbidden(parse_headers, invoke_action(app, "set_priority", make_form(action="set_priority", id=str(issue_id), priority="urgent"), "alice", method="POST"), "400")

    future = (dt.datetime.now(dt.timezone.utc).date() + dt.timedelta(days=10)).isoformat()
    today = dt.datetime.now(dt.timezone.utc).date().isoformat()
    past = (dt.datetime.now(dt.timezone.utc).date() - dt.timedelta(days=1)).isoformat()
    assert_redirect(parse_headers, invoke_action(app, "set_due_date", make_form(action="set_due_date", id=str(issue_id), due_date=future), "alice", method="POST"))
    assert fetch_issue(issue_id)["due_date"] == future
    for bad_due in ("not-a-date", today, past):
        assert_client_or_forbidden(parse_headers, invoke_action(app, "set_due_date", make_form(action="set_due_date", id=str(issue_id), due_date=bad_due), "alice", method="POST"), "400")
    for bad_id in (closed_id, canceled_id):
        assert_client_or_forbidden(parse_headers, invoke_action(app, "set_due_date", make_form(action="set_due_date", id=str(bad_id), due_date=future), "alice", method="POST"), "400")

    assert_redirect(parse_headers, invoke_action(app, "set_percent_complete", make_form(action="set_percent_complete", id=str(issue_id), pct_complete="0"), "bob", method="POST"))
    assert fetch_issue(issue_id)["pct_complete"] == 0
    assert_redirect(parse_headers, invoke_action(app, "set_percent_complete", make_form(action="set_percent_complete", id=str(issue_id), pct_complete="100"), "bob", method="POST"))
    for bad_pct in ("x", "-1", "101"):
        assert_client_or_forbidden(parse_headers, invoke_action(app, "set_percent_complete", make_form(action="set_percent_complete", id=str(issue_id), pct_complete=bad_pct), "bob", method="POST"), "400")
    for user in ("alice", "admin", "mallory"):
        assert_client_or_forbidden(parse_headers, invoke_action(app, "set_percent_complete", make_form(action="set_percent_complete", id=str(issue_id), pct_complete="50"), user, method="POST"), "403")
    for bad_id in (closed_id, canceled_id):
        assert_client_or_forbidden(parse_headers, invoke_action(app, "set_percent_complete", make_form(action="set_percent_complete", id=str(bad_id), pct_complete="50"), "bob", method="POST"), "400")

    for state in app.STATES:
        assert_redirect(parse_headers, invoke_action(app, "set_state", make_form(action="set_state", id=str(issue_id), state=state), "bob", method="POST"))
        assert fetch_issue(issue_id)["state"] == state
    assert_redirect(parse_headers, invoke_action(app, "set_state", make_form(action="set_state", id=str(issue_id), state="complete"), "bob", method="POST"))
    assert fetch_issue(issue_id)["pct_complete"] == 100
    assert_client_or_forbidden(parse_headers, invoke_action(app, "set_state", make_form(action="set_state", id=str(issue_id), state="bad"), "bob", method="POST"), "400")
    for user in ("alice", "admin", "mallory"):
        assert_client_or_forbidden(parse_headers, invoke_action(app, "set_state", make_form(action="set_state", id=str(issue_id), state="waiting"), user, method="POST"), "403")
    for bad_id in (closed_id, canceled_id):
        assert_client_or_forbidden(parse_headers, invoke_action(app, "set_state", make_form(action="set_state", id=str(bad_id), state="waiting"), "bob", method="POST"), "400")


def test_close_cancel_and_reopen_full_lifecycle_side_effects(app, patched_environment, seed_issue, make_form, invoke_action, parse_headers, fetch_issue, fetch_comments):
    close_id = seed_issue(creator_username="alice", assigned_username="bob", status="open", pct_complete=20)
    assert 'name="closing_comment"' in text_body(parse_headers, invoke_action(app, "close", make_form(action="close", id=str(close_id)), "alice"))
    for user in ("alice", "bob", "admin"):
        issue_id = seed_issue(creator_username="alice", assigned_username="bob", status="open", pct_complete=20)
        output = invoke_action(app, "close", make_form(action="close", id=str(issue_id), closing_comment=""), user, method="POST")
        assert_redirect(parse_headers, output)
        row = fetch_issue(issue_id)
        assert row["status"] == "closed"
        assert row["state"] == "complete"
        assert row["pct_complete"] == 100
        assert row["completed_at"] and row["updated_at"]
        assert fetch_comments(issue_id)[0]["comment_text"] == app.DEFAULT_CLOSING_COMMENT
    assert_client_or_forbidden(parse_headers, invoke_action(app, "close", make_form(action="close", id=str(close_id)), "mallory"), "403")

    cancel_id = seed_issue(creator_username="alice", assigned_username="bob", status="open")
    assert 'name="cancel_comment"' in text_body(parse_headers, invoke_action(app, "cancel", make_form(action="cancel", id=str(cancel_id)), "alice"))
    for user in ("bob", "admin", "mallory"):
        assert_client_or_forbidden(parse_headers, invoke_action(app, "cancel", make_form(action="cancel", id=str(cancel_id)), user), "403")
    assert_redirect(parse_headers, invoke_action(app, "cancel", make_form(action="cancel", id=str(cancel_id), comment_text=""), "alice", method="POST"))
    assert fetch_issue(cancel_id)["status"] == "canceled"
    assert fetch_comments(cancel_id)[0]["comment_text"] == app.DEFAULT_CLOSING_COMMENT

    closed_id = seed_issue(creator_username="alice", assigned_username="bob", status="closed", completed_at="2026-01-01T12:00:00+00:00")
    canceled_id = seed_issue(creator_username="alice", assigned_username="bob", status="canceled", completed_at="2026-01-01T12:00:00+00:00")
    for issue_id in (closed_id, canceled_id):
        assert_redirect(parse_headers, invoke_action(app, "reopen", make_form(action="reopen", id=str(issue_id), comment=""), "admin", method="POST"))
        row = fetch_issue(issue_id)
        assert row["status"] == "open"
        assert row["completed_at"] is None
        assert fetch_comments(issue_id)[0]["comment_text"] == app.DEFAULT_CLOSING_COMMENT
    for user in ("alice", "bob", "mallory"):
        issue_id = seed_issue(creator_username="alice", assigned_username="bob", status="closed", completed_at="2026-01-01T12:00:00+00:00")
        assert_client_or_forbidden(parse_headers, invoke_action(app, "reopen", make_form(action="reopen", id=str(issue_id)), user, method="POST"), "403")
    open_id = seed_issue(creator_username="alice", assigned_username="bob", status="open", completed_at=None)
    assert_redirect(parse_headers, invoke_action(app, "reopen", make_form(action="reopen", id=str(open_id), comment="ignored"), "admin", method="POST"))
    assert fetch_issue(open_id)["status"] == "open"


def test_direct_helper_functions_filename_markdown_dates_timestamps_and_groups(app, patched_environment, monkeypatch):
    assert app.user_exists("alice") is True
    assert app.user_exists("nobody") is False
    assert app.valid_assignee("") is True
    assert app.valid_assignee("alice") is True
    assert app.valid_assignee("mallory") is False
    assert app.valid_assignee("vwboot") is False
    monkeypatch.setattr(app, "ADMINS_GROUP_EXCLUDE", "admin", raising=False)
    assert app.is_admin("admin") is False
    monkeypatch.setattr(app, "ADMINS_GROUP_EXCLUDE", "", raising=False)

    assert app.normalize_filename("safe.txt") == "safe.txt"
    assert "/" not in app.normalize_filename("../bad/name.txt")
    monkeypatch.setattr(app, "MAX_FILENAME_LEN", 8, raising=False)
    assert len(app.normalize_filename("averylongfilename.txt")) <= 8
    assert app.normalize_filename("")

    rendered = app.markdown_to_html("**bold** <script>x</script>")
    assert "script" not in rendered.lower() or "&lt;script" in rendered
    monkeypatch.setattr(app, "_markdown", None, raising=False)
    fallback = app.markdown_to_html("<script>x</script>\n\nline")
    assert "<script>" not in fallback and "&lt;script" in fallback

    future = (dt.datetime.now(dt.timezone.utc).date() + dt.timedelta(days=1)).isoformat()
    assert call_flex(app.validate_due_date, future) is None
    for value in ("bad", dt.datetime.now(dt.timezone.utc).date().isoformat(), (dt.datetime.now(dt.timezone.utc).date() - dt.timedelta(days=1)).isoformat()):
        with pytest.raises(Exception):
            app.validate_due_date(value)
    assert app.format_timestamp("2026-01-01T12:00:00+00:00").endswith(" UTC")
    timestamp_markup = app.timestamp_html("2026-01-01T12:00:00+00:00")
    assert 'class="local-timestamp"' in timestamp_markup
    assert 'data-utc="2026-01-01T12:00:00Z"' in timestamp_markup


def test_security_escaping_and_sql_like_values_across_fields(app, patched_environment, seed_issue, seed_comment, seed_attachment, make_form, invoke_action, parse_headers, temp_db):
    issue_id = seed_issue(title="<script>title</script>", description="<script>desc</script>", creator_username="alice", assigned_username="bob")
    seed_comment(issue_id, text="<script>comment</script>")
    seed_attachment(issue_id, filename="<script>file</script>.txt")
    html = text_body(parse_headers, invoke_action(app, "view", make_form(action="view", id=str(issue_id)), "alice"))
    assert "<script>title</script>" not in html
    assert "<script>desc</script>" not in html
    assert "<script>comment</script>" not in html
    assert "<script>file</script>" not in html
    assert "alice" in html and "bob" in html

    dangerous = "x'); DROP TABLE comments; --"
    output = invoke_action(app, "comment", make_form(action="comment", id=str(issue_id), comment_text=dangerous), "alice", method="POST")
    assert_redirect(parse_headers, output)
    with sqlite3.connect(temp_db) as con:
        stored = con.execute("SELECT comment_text FROM comments WHERE comment_text = ?", (dangerous,)).fetchone()[0]
        count = con.execute("SELECT COUNT(*) FROM comments").fetchone()[0]
    assert stored == dangerous and count >= 1


def test_backend_authorization_for_each_protected_action(app, patched_environment, seed_issue, seed_attachment, make_form, invoke_action, parse_headers):
    issue_id = seed_issue(creator_username="alice", assigned_username="bob", status="open")
    attachment_id = seed_attachment(issue_id)
    direct_checks = [
        ("view", make_form(action="view", id=str(issue_id)), "mallory", "403"),
        ("assign", make_form(action="assign", id=str(issue_id), assigned_username="alice"), "mallory", "403"),
        ("attach", make_upload_form(make_form(action="attach", id=str(issue_id), issue_id=str(issue_id))), "mallory", "403"),
        ("download", make_form(action="download", id=str(attachment_id)), "mallory", "403"),
        ("comment", make_form(action="comment", id=str(issue_id), comment_text="x"), "mallory", "403"),
        ("update", make_form(action="update", id=str(issue_id), title="x", description="y"), "mallory", "403"),
        ("set_priority", make_form(action="set_priority", id=str(issue_id), priority="high"), "mallory", "403"),
        ("set_due_date", make_form(action="set_due_date", id=str(issue_id), due_date=(dt.datetime.now(dt.timezone.utc).date() + dt.timedelta(days=5)).isoformat()), "mallory", "403"),
        ("set_percent_complete", make_form(action="set_percent_complete", id=str(issue_id), pct_complete="50"), "mallory", "403"),
        ("set_state", make_form(action="set_state", id=str(issue_id), state="waiting"), "mallory", "403"),
        ("close", make_form(action="close", id=str(issue_id), closing_comment="x"), "mallory", "403"),
        ("cancel", make_form(action="cancel", id=str(issue_id), cancel_comment="x"), "mallory", "403"),
        ("reopen", make_form(action="reopen", id=str(issue_id)), "mallory", "403"),
    ]
    for action, form, user, code in direct_checks:
        assert_client_or_forbidden(parse_headers, invoke_action(app, action, form, user, method="POST"), code)


def test_output_assertion_helpers_exist_and_work(invoke_action, app, patched_environment, parse_headers, assert_output_contains_required_fragments, assert_output_does_not_contain_forbidden_fragments):
    output = invoke_action(app, "list", user="alice")
    assert_output_contains_required_fragments(output, ["Issue", "Create"])
    # REGRESSION GUARD: Pages may contain application-owned JavaScript, such as
    # browser-local timestamp conversion. This helper smoke test should verify
    # that forbidden-fragment assertions work without treating all script blocks
    # as unsafe user-supplied content.
    assert_output_does_not_contain_forbidden_fragments(output, ["__definitely_not_present_forbidden_fragment__"])
