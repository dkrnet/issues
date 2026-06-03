# Copyright (C) 2026 David Redmond
# SPDX-License-Identifier: AGPL-3.0-only
#
"""Requirements mapping: tagged issue participants."""

import subprocess

from conftest import Field


def _html(parse_headers, output):
    body = parse_headers(output)[2]
    return body.decode("utf-8", "replace") if isinstance(body, bytes) else body


def _status(parse_headers, output):
    return parse_headers(output)[0]


def _dual_list_html(html):
    start = html.find('class="dual-listbox tagged-users-dual-list"')
    assert start >= 0, html
    end = html.find("</form>", start)
    assert end >= 0, html[start:]
    return html[start:end]


def test_create_issue_can_add_multiple_tagged_users(app, patched_environment, make_form, invoke_action, parse_headers, fetch_tagged_users, fetch_history):
    create_html = _html(parse_headers, invoke_action(app, "create", make_form(action="create"), "alice"))
    assert 'class="dual-listbox tagged-users-dual-list"' in create_html
    assert 'class="dual-listbox-available"' in create_html
    assert 'class="dual-listbox-selected" name="tagged_users"' in create_html
    assert 'onchange="syncTaggedUsersWithAssignee(this)"' in create_html
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
            title="Tagged create",
            description="Tagged users can track this.",
            priority="normal",
            assigned_username="",
            tagged_users=["bob", "admin"],
        ),
        "alice",
        method="POST",
    )
    status, headers, _body = parse_headers(output)
    assert status.startswith(("302", "303"))
    issue_id = int(headers["location"].rsplit("id=", 1)[1])
    assert [row["tagged_username"] for row in fetch_tagged_users(issue_id)] == ["admin", "bob"]
    assert "tagged_users_added" in [row["action"] for row in fetch_history(issue_id)]

    assigned_rejected = invoke_action(
        app,
        "create_submit",
        make_form(
            action="create_submit",
            title="Assigned tagged create",
            description="Assignees are not tagged users.",
            priority="normal",
            assigned_username="bob",
            tagged_users=["bob"],
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
            title="Bad tagged create",
            description="Not taggable.",
            priority="normal",
            tagged_users=["mallory"],
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
            title="Excluded tagged create",
            description="Excluded users follow assignee rules.",
            priority="normal",
            tagged_users=["vwboot"],
        ),
        "alice",
        method="POST",
    )
    assert "400" in _status(parse_headers, excluded)


def test_tagged_users_can_view_list_comment_attach_and_download(app, patched_environment, seed_issue, seed_tagged_user, make_form, invoke_action, parse_headers, fetch_comments, fetch_attachments):
    issue_id = seed_issue(title="Visible to tagged", creator_username="alice", assigned_username="", status="open")
    seed_tagged_user(issue_id, "bob")

    list_html = _html(parse_headers, invoke_action(app, "list", user="bob"))
    assert "Visible to tagged" in list_html

    view_html = _html(parse_headers, invoke_action(app, "view", make_form(action="view", id=str(issue_id)), "bob"))
    assert "Visible to tagged" in view_html
    assert "Add comment" in view_html
    assert "Add attachment" in view_html
    assert "Edit Title" not in view_html
    assert "Close" not in view_html
    assert "Update tagged users" not in view_html
    assert "Remove me from tagged users" in view_html

    creator_view = _html(parse_headers, invoke_action(app, "view", make_form(action="view", id=str(issue_id)), "alice"))
    assert 'select name="add_tagged_users" multiple' not in creator_view
    assert 'class="dual-listbox tagged-users-dual-list"' in creator_view
    assert 'name="tagged_users_final"' in creator_view
    assert "<p>bob</p>" not in creator_view
    assert "target.appendChild(moving[j])" in creator_view
    assert "sortSelectOptions(target)" in creator_view
    assert "left.localeCompare(right" in creator_view
    assert 'function hasClass(node, className)' in creator_view
    assert 'while (root && !hasClass(root, "dual-listbox"))' in creator_view
    creator_dual = _dual_list_html(creator_view)
    assert 'value="bob">bob</option>' in creator_dual
    assert '<option value="admin">admin</option>' in creator_dual
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


def test_tagged_users_can_remove_only_themselves(app, patched_environment, seed_issue, seed_tagged_user, make_form, invoke_action, parse_headers, fetch_tagged_users, fetch_history):
    issue_id = seed_issue(creator_username="alice", assigned_username="", status="open")
    seed_tagged_user(issue_id, "bob")
    seed_tagged_user(issue_id, "admin")

    forbidden = invoke_action(
        app,
        "tags_update",
        make_form(action="tags_update", id=str(issue_id), remove_tagged_users="admin"),
        "bob",
        method="POST",
    )
    assert "403" in _status(parse_headers, forbidden)
    assert [row["tagged_username"] for row in fetch_tagged_users(issue_id)] == ["admin", "bob"]

    output = invoke_action(
        app,
        "tags_update",
        make_form(action="tags_update", id=str(issue_id), remove_tagged_users="bob"),
        "bob",
        method="POST",
    )
    assert _status(parse_headers, output).startswith(("302", "303"))
    assert [row["tagged_username"] for row in fetch_tagged_users(issue_id)] == ["admin"]
    assert "tagged_users_removed" in [row["action"] for row in fetch_history(issue_id)]


def test_creator_assignee_and_admin_can_add_remove_multiple_tagged_users(app, patched_environment, seed_issue, seed_tagged_user, make_form, invoke_action, parse_headers, fetch_tagged_users):
    issue_id = seed_issue(creator_username="alice", assigned_username="", status="open")
    seed_tagged_user(issue_id, "bob")

    output = invoke_action(
        app,
        "tags_update",
        make_form(action="tags_update", id=str(issue_id), add_tagged_users=["admin"]),
        "alice",
        method="POST",
    )
    assert _status(parse_headers, output).startswith(("302", "303"))
    assert [row["tagged_username"] for row in fetch_tagged_users(issue_id)] == ["admin", "bob"]

    output = invoke_action(
        app,
        "tags_update",
        make_form(action="tags_update", id=str(issue_id), remove_tagged_users=["admin", "bob"]),
        "alice",
        method="POST",
    )
    assert _status(parse_headers, output).startswith(("302", "303"))
    assert fetch_tagged_users(issue_id) == []

    output = invoke_action(
        app,
        "tags_update",
        make_form(action="tags_update", id=str(issue_id), tagged_users_final_present="1", tagged_users_final=["bob", "admin"]),
        "admin",
        method="POST",
    )
    assert _status(parse_headers, output).startswith(("302", "303"))
    assert [row["tagged_username"] for row in fetch_tagged_users(issue_id)] == ["admin", "bob"]

    rejected = invoke_action(
        app,
        "tags_update",
        make_form(action="tags_update", id=str(issue_id), add_tagged_users=["mallory"]),
        "admin",
        method="POST",
    )
    assert "400" in _status(parse_headers, rejected)

    excluded = invoke_action(
        app,
        "tags_update",
        make_form(action="tags_update", id=str(issue_id), add_tagged_users=["vwboot"]),
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
        "tags_update",
        make_form(action="tags_update", id=str(assigned_issue_id), add_tagged_users=["bob"]),
        "admin",
        method="POST",
    )
    assert "400" in _status(parse_headers, assigned_rejected)


def test_tagged_users_receive_creator_notifications_and_tag_change_notifications(app, patched_environment, monkeypatch, seed_issue, seed_tagged_user, make_form, invoke_action, fetch_history):
    sent = []

    def fake_run(cmd, input=None, check=False):
        sent.append(input)
        return subprocess.CompletedProcess(cmd, 0)

    monkeypatch.setattr(app.subprocess, "run", fake_run, raising=False)
    monkeypatch.setattr(app, "EMAIL_NOTIFICATIONS_ENABLED", True, raising=False)

    issue_id = seed_issue(title="Tagged notifications", creator_username="alice", assigned_username="", status="open")
    seed_tagged_user(issue_id, "bob")

    invoke_action(app, "comment_submit", make_form(action="comment_submit", id=str(issue_id), comment_text="Update"), "admin", method="POST")
    assert b"To: alice, bob" in sent[-1]

    invoke_action(app, "tags_update", make_form(action="tags_update", id=str(issue_id), add_tagged_users=["admin"]), "alice", method="POST")
    assert b"To: admin" in sent[-1]

    invoke_action(app, "tags_update", make_form(action="tags_update", id=str(issue_id), remove_tagged_users="bob"), "alice", method="POST")
    assert b"To: bob" in sent[-1]

    summaries = [row["summary"] for row in fetch_history(issue_id)]
    assert "Notification email sent to alice, bob" in summaries
    assert "Notification email sent to admin" in summaries
    assert "Notification email sent to bob" in summaries
