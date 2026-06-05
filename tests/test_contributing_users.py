# Copyright (C) 2026 David Redmond
# SPDX-License-Identifier: AGPL-3.0-only
#
"""Requirements mapping: contributing issue participants."""

import subprocess

from conftest import Field


def _html(parse_headers, output):
    body = parse_headers(output)[2]
    return body.decode("utf-8", "replace") if isinstance(body, bytes) else body


def _status(parse_headers, output):
    return parse_headers(output)[0]


def _dual_list_html(html):
    start = html.find('class="dual-listbox contributing-users-dual-list"')
    assert start >= 0, html
    end = html.find("</form>", start)
    assert end >= 0, html[start:]
    return html[start:end]


def test_create_issue_can_add_multiple_contributing_users(app, patched_environment, make_form, invoke_action, parse_headers, fetch_contributing_users, fetch_history):
    create_html = _html(parse_headers, invoke_action(app, "create", make_form(action="create"), "alice"))
    assert 'class="dual-listbox contributing-users-dual-list"' in create_html
    assert 'class="dual-listbox-available"' in create_html
    assert 'class="dual-listbox-selected" name="contributing_users"' in create_html
    assert 'onchange="syncContributingUsersWithAssignee(this)"' in create_html
    create_dual = _dual_list_html(create_html)
    assert '<option value="bob">bob</option>' in create_dual
    assert '<option value="alice">alice</option>' not in create_dual
    assert '<option value="vwboot">vwboot</option>' not in create_dual
    assert '<option value="mallory">mallory</option>' not in create_dual

    output = invoke_action(
        app,
        "create_submit",
        make_form(
            action="create_submit",
            title="Contributing create",
            description="Contributing users can track this.",
            priority="normal",
            assigned_username="",
            contributing_users=["bob", "admin"],
        ),
        "alice",
        method="POST",
    )
    status, headers, _body = parse_headers(output)
    assert status.startswith(("302", "303"))
    issue_id = int(headers["location"].rsplit("id=", 1)[1])
    assert [row["contributing_username"] for row in fetch_contributing_users(issue_id)] == ["admin", "bob"]
    assert "contributing_users_added" in [row["action"] for row in fetch_history(issue_id)]

    assigned_rejected = invoke_action(
        app,
        "create_submit",
        make_form(
            action="create_submit",
            title="Assigned contributing create",
            description="Assignees are not contributing users.",
            priority="normal",
            assigned_username="bob",
            contributing_users=["bob"],
        ),
        "alice",
        method="POST",
    )
    assert "400" in _status(parse_headers, assigned_rejected)

    rejected = invoke_action(
        app,
        "create_submit",
        make_form(
            action="create_submit",
            title="Bad contributing create",
            description="Not contributing candidate.",
            priority="normal",
            contributing_users=["mallory"],
        ),
        "alice",
        method="POST",
    )
    assert "400" in _status(parse_headers, rejected)

    excluded = invoke_action(
        app,
        "create_submit",
        make_form(
            action="create_submit",
            title="Excluded contributing create",
            description="Excluded users follow assignee rules.",
            priority="normal",
            contributing_users=["vwboot"],
        ),
        "alice",
        method="POST",
    )
    assert "400" in _status(parse_headers, excluded)


def test_contributing_users_can_view_list_comment_attach_and_download(app, patched_environment, seed_issue, seed_contributing_user, make_form, invoke_action, parse_headers, fetch_comments, fetch_attachments):
    issue_id = seed_issue(title="Visible to contributing", creator_username="alice", assigned_username="", status="open")
    seed_contributing_user(issue_id, "bob")

    list_html = _html(parse_headers, invoke_action(app, "list", user="bob"))
    assert "Visible to contributing" in list_html

    view_html = _html(parse_headers, invoke_action(app, "view", make_form(action="view", id=str(issue_id)), "bob"))
    assert "Visible to contributing" in view_html
    assert "Add comment" in view_html
    assert "Add attachment" in view_html
    assert "Edit Title" not in view_html
    assert "Close" not in view_html
    assert "Update contributing users" not in view_html
    assert "Remove me from contributing users" in view_html

    creator_view = _html(parse_headers, invoke_action(app, "view", make_form(action="view", id=str(issue_id)), "alice"))
    assert 'select name="add_contributing_users" multiple' not in creator_view
    assert 'class="dual-listbox contributing-users-dual-list"' in creator_view
    assert 'name="contributing_users_final"' in creator_view
    assert "<p>bob</p>" not in creator_view
    assert "target.appendChild(moving[j])" in creator_view
    assert "sortSelectOptions(target)" in creator_view
    assert "labels[left] || left" in creator_view
    assert "labels[right] || right" in creator_view
    assert 'function hasClass(node, className)' in creator_view
    assert 'while (root && !hasClass(root, "dual-listbox"))' in creator_view
    creator_dual = _dual_list_html(creator_view)
    assert 'value="bob">bob</option>' in creator_dual
    assert '<option value="admin">admin</option>' in creator_dual
    assert 'data-user-labels' in creator_dual
    assert '<option value="alice">alice</option>' not in creator_dual
    assert '<option value="vwboot">vwboot</option>' not in creator_dual
    assert '<option value="mallory">mallory</option>' not in creator_dual

    output = invoke_action(app, "comment_submit", make_form(action="comment_submit", id=str(issue_id), comment_text="Watching this."), "bob", method="POST")
    assert _status(parse_headers, output).startswith(("302", "303"))
    assert fetch_comments(issue_id)[0]["commenter_username"] == "bob"

    form = make_form(action="attach_submit", id=str(issue_id))
    form._fields["file"] = Field(value="", filename="watcher.txt", file_bytes=b"payload")
    output = invoke_action(app, "attach_submit", form, "bob", method="POST")
    assert _status(parse_headers, output).startswith(("302", "303"))
    attachment_id = fetch_attachments(issue_id)[0]["id"]
    status, headers, body = parse_headers(invoke_action(app, "download", make_form(action="download", id=str(attachment_id)), "bob"))
    assert "403" not in status
    assert "content-disposition" in headers
    assert b"payload" in body


def test_contributing_users_can_remove_only_themselves(app, patched_environment, seed_issue, seed_contributing_user, make_form, invoke_action, parse_headers, fetch_contributing_users, fetch_history):
    issue_id = seed_issue(creator_username="alice", assigned_username="", status="open")
    seed_contributing_user(issue_id, "bob")
    seed_contributing_user(issue_id, "admin")

    forbidden = invoke_action(
        app,
        "contributing_users_update",
        make_form(action="contributing_users_update", id=str(issue_id), remove_contributing_users="admin"),
        "bob",
        method="POST",
    )
    assert "403" in _status(parse_headers, forbidden)
    assert [row["contributing_username"] for row in fetch_contributing_users(issue_id)] == ["admin", "bob"]

    output = invoke_action(
        app,
        "contributing_users_update",
        make_form(action="contributing_users_update", id=str(issue_id), remove_contributing_users="bob"),
        "bob",
        method="POST",
    )
    assert _status(parse_headers, output).startswith(("302", "303"))
    assert [row["contributing_username"] for row in fetch_contributing_users(issue_id)] == ["admin"]
    assert "contributing_users_removed" in [row["action"] for row in fetch_history(issue_id)]


def test_creator_assignee_and_admin_can_add_remove_multiple_contributing_users(app, patched_environment, seed_issue, seed_contributing_user, make_form, invoke_action, parse_headers, fetch_contributing_users):
    issue_id = seed_issue(creator_username="alice", assigned_username="", status="open")
    seed_contributing_user(issue_id, "bob")

    output = invoke_action(
        app,
        "contributing_users_update",
        make_form(action="contributing_users_update", id=str(issue_id), add_contributing_users=["admin"]),
        "alice",
        method="POST",
    )
    assert _status(parse_headers, output).startswith(("302", "303"))
    assert [row["contributing_username"] for row in fetch_contributing_users(issue_id)] == ["admin", "bob"]

    output = invoke_action(
        app,
        "contributing_users_update",
        make_form(action="contributing_users_update", id=str(issue_id), remove_contributing_users=["admin", "bob"]),
        "alice",
        method="POST",
    )
    assert _status(parse_headers, output).startswith(("302", "303"))
    assert fetch_contributing_users(issue_id) == []

    output = invoke_action(
        app,
        "contributing_users_update",
        make_form(action="contributing_users_update", id=str(issue_id), contributing_users_final_present="1", contributing_users_final=["bob", "admin"]),
        "admin",
        method="POST",
    )
    assert _status(parse_headers, output).startswith(("302", "303"))
    assert [row["contributing_username"] for row in fetch_contributing_users(issue_id)] == ["admin", "bob"]

    rejected = invoke_action(
        app,
        "contributing_users_update",
        make_form(action="contributing_users_update", id=str(issue_id), add_contributing_users=["mallory"]),
        "admin",
        method="POST",
    )
    assert "400" in _status(parse_headers, rejected)

    excluded = invoke_action(
        app,
        "contributing_users_update",
        make_form(action="contributing_users_update", id=str(issue_id), add_contributing_users=["vwboot"]),
        "admin",
        method="POST",
    )
    assert "400" in _status(parse_headers, excluded)

    assigned_issue_id = seed_issue(creator_username="alice", assigned_username="bob", status="open")
    assigned_view = _html(parse_headers, invoke_action(app, "view", make_form(action="view", id=str(assigned_issue_id)), "alice"))
    assigned_dual = _dual_list_html(assigned_view)
    assert '<option value="alice">alice</option>' not in assigned_dual
    assert '<option value="bob">bob</option>' not in assigned_dual
    assigned_rejected = invoke_action(
        app,
        "contributing_users_update",
        make_form(action="contributing_users_update", id=str(assigned_issue_id), add_contributing_users=["bob"]),
        "admin",
        method="POST",
    )
    assert "400" in _status(parse_headers, assigned_rejected)


def test_contributing_users_receive_creator_notifications_and_tag_change_notifications(app, patched_environment, monkeypatch, seed_issue, seed_contributing_user, make_form, invoke_action, fetch_history):
    sent = []

    def fake_run(cmd, input=None, check=False):
        sent.append(input)
        return subprocess.CompletedProcess(cmd, 0)

    monkeypatch.setattr(app.subprocess, "run", fake_run, raising=False)
    monkeypatch.setattr(app, "EMAIL_NOTIFICATIONS_ENABLED", True, raising=False)

    issue_id = seed_issue(title="Contributing notifications", creator_username="alice", assigned_username="", status="open")
    seed_contributing_user(issue_id, "bob")

    invoke_action(app, "comment_submit", make_form(action="comment_submit", id=str(issue_id), comment_text="Update"), "admin", method="POST")
    assert b"To: alice, bob" in sent[-1]

    invoke_action(app, "contributing_users_update", make_form(action="contributing_users_update", id=str(issue_id), add_contributing_users=["admin"]), "alice", method="POST")
    assert b"To: admin" in sent[-1]

    invoke_action(app, "contributing_users_update", make_form(action="contributing_users_update", id=str(issue_id), remove_contributing_users="bob"), "alice", method="POST")
    assert b"To: bob" in sent[-1]

    summaries = [row["summary"] for row in fetch_history(issue_id)]
    assert "Notification email sent to alice, bob" in summaries
    assert "Notification email sent to admin" in summaries
    assert "Notification email sent to bob" in summaries
