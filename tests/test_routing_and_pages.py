# Copyright (C) 2026 David Redmond
# SPDX-License-Identifier: AGPL-3.0-only
#
"""Requirements mapping: routing, headers, issue list/view pages, and role-specific UI controls."""

import sqlite3

from conftest import assert_banner_uses_config, html_has_control, html_has_option, html_select_option_values


def _html(parse_headers, output):
    body = parse_headers(output)[2]
    return body.decode("utf-8", "replace") if isinstance(body, bytes) else body


def test_missing_action_defaults_to_list_when_remote_user_is_set_and_login_when_missing(app, patched_environment, make_form, invoke_action, parse_headers):
    output = invoke_action(app, action=None, form=make_form(), user="alice")
    status, headers, body = parse_headers(output)
    body_text = body.decode("utf-8", "replace") if isinstance(body, bytes) else body
    assert headers.get("content-type", "").startswith("text/html")
    assert "<html" in body_text.lower()
    assert "issue" in body_text.lower()
    assert "issues login" not in body_text.lower()

    login_output = invoke_action(app, action=None, form=make_form(), user=None)
    login_status, login_headers, login_body = parse_headers(login_output)
    login_text = login_body.decode("utf-8", "replace") if isinstance(login_body, bytes) else login_body
    assert login_headers.get("content-type", "").startswith("text/html")
    assert "<html" in login_text.lower()
    assert "issues login" in login_text.lower()
    assert 'rel="icon"' in login_text
    assert 'action=favicon' in login_text
    assert "anonymous or invalid user" not in login_text.lower()


def test_unknown_action_returns_not_found_and_unsafe_action_returns_bad_request(app, patched_environment, invoke_action, parse_headers):
    unknown = invoke_action(app, action="definitely_not_a_real_action", user="alice")
    unknown_status, unknown_headers, unknown_body = parse_headers(unknown)
    assert "404" in (unknown_status + str(unknown_body))
    assert unknown_headers.get("content-type", "").startswith(("text/plain", "text/html"))

    unsafe = invoke_action(app, action="bad-name", user="alice")
    unsafe_status, unsafe_headers, unsafe_body = parse_headers(unsafe)
    assert "400" in (unsafe_status + str(unsafe_body))
    assert unsafe_headers.get("content-type", "").startswith(("text/plain", "text/html"))


def test_dispatcher_prefers_global_action_handler_then_internal_fallback(app, patched_environment, monkeypatch, invoke_action, parse_headers):
    calls = []

    def action_probe(form=None, user=None, username=None, current_user=None):
        calls.append("global")
        print("Content-Type: text/plain\n\nglobal probe")

    monkeypatch.setattr(app, "action_probe", action_probe, raising=False)
    output = invoke_action(app, action="probe", user="alice")
    assert calls == ["global"]
    assert "global probe" in _html(parse_headers, output)

    output = invoke_action(app, action="markdown_help", user="alice")
    assert "markdown help" in _html(parse_headers, output).lower()


def test_get_and_post_use_same_cgi_entry_point(app, patched_environment, invoke_action, make_form, parse_headers):
    get_html = _html(parse_headers, invoke_action(app, action="markdown_help", user="alice", method="GET"))
    post_html = _html(parse_headers, invoke_action(app, action="markdown_help", form=make_form(action="markdown_help"), user="alice", method="POST"))
    assert "markdown help" in get_html.lower()
    assert "markdown help" in post_html.lower()


def test_public_authentication_actions_are_routed_without_user_lookup(app, patched_environment, invoke_action, make_form, parse_headers):
    for action in ("login", "login_failed", "logged_out", "auth_error"):
        html = _html(parse_headers, invoke_action(app, action=action, form=make_form(action=action), user=None))
        assert "invalid user" not in html.lower()
        assert "anonymous" not in html.lower()
        assert "<html" in html.lower()
    status, headers, body = parse_headers(invoke_action(app, action="favicon", form=make_form(action="favicon"), user=None))
    assert "403" not in status
    assert headers.get("content-type", "").startswith("image/x-icon")



def test_list_page_has_required_structure_new_filters_and_no_legacy_all_users_control(app, patched_environment, invoke_action, parse_headers):
    admin_html = _html(parse_headers, invoke_action(app, action="list", user="admin"))
    alice_html = _html(parse_headers, invoke_action(app, action="list", user="alice"))

    lowered = admin_html.lower()
    assert "<table" in lowered
    assert 'rel="icon"' in admin_html
    assert 'action=favicon' in admin_html
    assert "create" in lowered and "issue" in lowered
    assert_banner_uses_config(admin_html)

    for name in ("status", "priority", "creator", "assignee", "state", "due_date", "has_comments", "has_attachments", "search", "auto_refresh", "page"):
        assert html_has_control(admin_html, name), f"admin issue list should render {name!r} filter"
    assert 'class="static-filters"' in admin_html
    assert 'class="dynamic-filters"' in admin_html
    static_start = admin_html.find('class="static-filters"')
    dynamic_start = admin_html.find('class="dynamic-filters"')
    static_html = admin_html[static_start:dynamic_start]
    dynamic_html = admin_html[dynamic_start:admin_html.find("<noscript>", dynamic_start)]
    assert 'name="status"' in static_html
    assert 'name="due_date"' in static_html
    assert '>Due <select name="due_date"' in static_html
    assert 'Due date <select name="due_date"' not in static_html
    assert 'name="has_comments"' in static_html
    assert 'name="has_attachments"' in static_html
    assert 'class="static-filter-left"' in static_html
    assert 'class="static-filter-search"' in static_html
    assert 'type="search" name="search"' in static_html
    assert static_html.find('class="static-filter-left"') < static_html.find('class="static-filter-search"')
    assert static_html.find('name="has_attachments"') < static_html.find('name="search"')
    assert 'name="priority"' not in static_html
    assert dynamic_html.find('name="priority"') >= 0
    assert dynamic_html.find('name="priority"') < dynamic_html.find('name="creator"') < dynamic_html.find('name="assignee"') < dynamic_html.find('name="state"')
    assert html_select_option_values(admin_html, "status") == ["any", "open", "closed", "canceled"]
    for due in ("any", "no due date", "today", "within 5 days", "within 30 days"):
        assert html_has_option(admin_html, due), f"due-date filter should include {due!r}"

    assert not html_has_control(admin_html, "all")
    assert "all users issues" not in lowered
    assert not html_has_control(alice_html, "creator")
    assert not html_has_control(alice_html, "all")
    assert "all users issues" not in alice_html.lower()
    for name in ("status", "priority", "assignee", "state", "due_date", "has_comments", "has_attachments", "search", "auto_refresh", "page"):
        assert html_has_control(alice_html, name), f"non-admin issue list should render {name!r} filter"

    # REGRESSION GUARD: Comments-only and attachments-only checkboxes use
    # onclick so browsers that defer onchange until blur still apply filters
    # immediately when the checkbox is clicked.
    assert 'name="has_comments"' in admin_html
    assert 'name="has_attachments"' in admin_html
    assert "Has comments" in admin_html
    assert "Has attachments" in admin_html
    assert "Search" in admin_html
    assert "static-filter-row" in admin_html
    assert "clamp(12em, 28vw, 32em)" in admin_html
    assert "Comments only" not in admin_html
    assert "Attachments only" not in admin_html
    assert 'name="has_comments" value="1"' in admin_html and 'onclick="this.form.submit()"' in admin_html
    assert 'name="has_attachments" value="1"' in admin_html and 'onclick="this.form.submit()"' in admin_html
    assert admin_html.count('class="pagination-controls"') >= 2
    assert admin_html.count("Previous") >= 2 and admin_html.count("Next") >= 2
    assert 'name="page"' in admin_html and "1 of 1" in admin_html
    assert 'class="list-control-row issue-list-top-controls"' in admin_html
    assert 'class="list-control-row issue-list-bottom-controls"' in admin_html
    top_row_start = admin_html.find('class="list-control-row issue-list-top-controls"')
    table_start = admin_html.lower().find("<table", top_row_start)
    top_row_html = admin_html[top_row_start:table_start]
    assert "Create new issue" in top_row_html
    assert 'class="pagination-controls"' in top_row_html
    assert 'class="list-control-left"' in top_row_html
    assert 'class="list-control-right"' in top_row_html
    assert '<p><a href=' not in top_row_html
    assert 'float:left' in admin_html
    assert 'float:right' in admin_html
    assert 'white-space:nowrap' in admin_html
    assert "<table class='issue-list-table'>" in admin_html
    expected_headers = [
        "<th>ID</th>", "<th>Title</th>", "<th>Status</th>",
        "<th>Due</th>", "<th>Priority</th>", "<th>Creator</th>",
        "<th>Assignee</th>", "<th>State</th>", "<th>% Complete</th>",
        "<th>Comments</th>", "<th>Attachments</th>", "<th>Updated</th>",
    ]
    header_row = admin_html[admin_html.find("<thead><tr>"):admin_html.find("</tr></thead>") + len("</tr></thead>")]
    positions = [header_row.find(header) for header in expected_headers]
    assert all(pos >= 0 for pos in positions), header_row
    assert positions == sorted(positions), header_row
    assert "<th>Assigned</th>" not in header_row
    bottom_row_start = admin_html.find('class="list-control-row issue-list-bottom-controls"')
    bottom_row_html = admin_html[bottom_row_start:]
    assert "Auto-refresh" in bottom_row_html
    assert 'class="pagination-controls"' in bottom_row_html
    assert 'class="list-control-left"' in bottom_row_html
    assert 'class="list-control-right"' in bottom_row_html
    assert 'class="last-refreshed"' in bottom_row_html
    assert 'data-refreshed-at-utc=' in bottom_row_html
    assert "(Last refreshed: just now)" in bottom_row_html
    assert ".last-refreshed" in admin_html and "font-size: 0.9em" in admin_html
    assert 'class="local-timestamp"' not in bottom_row_html
    assert 'renderRelativeRefreshTimes' in admin_html
    assert 'setInterval(renderRelativeRefreshTimes, 60000)' in admin_html
    assert bottom_row_html.find('name="auto_refresh"') < bottom_row_html.find('class="last-refreshed"')
    assert html_select_option_values(admin_html, "auto_refresh") == ["never", "5 minutes", "10 minutes", "20 minutes", "30 minutes"]


def test_static_due_date_filter_visibility_tracks_status(app, patched_environment, invoke_action, make_form, parse_headers):
    for status in ("open", "any"):
        html = _html(parse_headers, invoke_action(app, "list", make_form(action="list", status=status, priority="any"), "alice"))
        assert html_has_control(html, "due_date")
    for status in ("closed", "canceled"):
        html = _html(parse_headers, invoke_action(app, "list", make_form(action="list", status=status, priority="any"), "alice"))
        assert not html_has_control(html, "due_date")


def test_view_page_authorization_and_role_specific_controls(app, patched_environment, seed_issue, invoke_action, make_form, parse_headers):
    issue_id = seed_issue(creator_username="alice", assigned_username="bob", status="open")

    creator_html = _html(parse_headers, invoke_action(app, "view", make_form(action="view", id=str(issue_id), issue_id=str(issue_id)), "alice"))
    assigned_html = _html(parse_headers, invoke_action(app, "view", make_form(action="view", id=str(issue_id), issue_id=str(issue_id)), "bob"))
    unauth_output = invoke_action(app, "view", make_form(action="view", id=str(issue_id), issue_id=str(issue_id)), "mallory")
    unauth_status, _, unauth_body = parse_headers(unauth_output)

    assert_banner_uses_config(creator_html)
    assert "Seed issue" in creator_html
    assert "<th>Assignee</th>" in creator_html
    assert "<th>Assigned</th>" not in creator_html
    assert "description" in creator_html.lower()
    assert "comments" in creator_html.lower()
    assert "attachments" in creator_html.lower()
    assert "Edit Title" in creator_html or "edit" in creator_html.lower()
    assert "Cancel" in creator_html
    assert "percent" in assigned_html.lower() or "complete" in assigned_html.lower()
    assert "403" in (unauth_status + str(unauth_body)) or "forbidden" in str(unauth_body).lower()


def test_issue_list_pagination_limits_to_25_and_navigates_pages(app, patched_environment, seed_issue, invoke_action, make_form, parse_headers):
    for number in range(1, 31):
        seed_issue(title=f"Paged issue {number:02d}", creator_username="alice", assigned_username="bob", status="open")

    page_one = _html(parse_headers, invoke_action(app, "list", make_form(action="list", status="open", priority="any", page="1"), "alice"))
    page_two = _html(parse_headers, invoke_action(app, "list", make_form(action="list", status="open", priority="any", page="2"), "alice"))

    assert page_one.count('class="pagination-controls"') >= 2
    assert 'class="list-control-row issue-list-top-controls"' in page_one
    assert 'class="list-control-row issue-list-bottom-controls"' in page_one
    assert page_one.count("Previous") >= 2 and page_one.count("Next") >= 2
    assert 'name="page"' in page_one
    # REGRESSION GUARD: Previous/Next must not be submit buttons named page.
    # Browsers disagree about whether a submit button named page or a selected
    # page dropdown value wins when both are submitted, which broke pagination.
    assert 'type="submit" name="page"' not in page_one
    assert "type=\"button\" onclick=\"this.form.elements['page'].value=" in page_one
    assert "select aria-label=\"Page\" onchange=\"this.form.elements['page'].value=this.value; this.form.submit()\"" in page_one
    assert "1 of 2" in page_one and "2 of 2" in page_one
    assert "Paged issue 30" in page_one
    assert "Paged issue 06" in page_one
    assert "Paged issue 05" not in page_one
    assert "Paged issue 05" in page_two
    assert "Paged issue 01" in page_two
    assert "Paged issue 30" not in page_two


def test_issue_history_page_authorization_pagination_and_metadata_only(app, patched_environment, seed_issue, seed_attachment, make_form, invoke_action, parse_headers, temp_db):
    issue_id = seed_issue(title="History paged", creator_username="alice", assigned_username="bob", status="open")
    attachment_id = seed_attachment(issue_id, filename="metadata.txt", content=b"secret blob content")
    with sqlite3.connect(temp_db) as con:
        comment_id = con.execute(
            """INSERT INTO comments (issue_id, commenter_username, comment_text, created_at)
               VALUES (?, ?, ?, ?)""",
            (
                issue_id,
                "alice",
                "These first few words should appear but this complete comment should not be displayed",
                "2026-01-01 12:00:00+00:00",
            ),
        ).lastrowid
        for number in range(1, 31):
            con.execute(
                """INSERT INTO issue_history
                   (issue_id, actor_username, action, summary, comment_id, attachment_id, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    issue_id,
                    "alice",
                    "manual",
                    'Changed state from "not [started" to "in progress"' if number == 29 else f"History entry {number:02d}",
                    comment_id if number == 28 else None,
                    attachment_id if number == 30 else None,
                    f"2026-01-01 12:{number:02d}:00+00:00",
                ),
            )

    page_one = _html(parse_headers, invoke_action(app, "history", make_form(action="history", id=str(issue_id), page="1"), "alice"))
    page_two = _html(parse_headers, invoke_action(app, "history", make_form(action="history", id=str(issue_id), page="2"), "alice"))
    unauthorized_output = invoke_action(app, "history", make_form(action="history", id=str(issue_id)), "mallory")
    unauthorized_status, _, unauthorized_body = parse_headers(unauthorized_output)
    unauthorized = unauthorized_body.decode("utf-8", "replace") if isinstance(unauthorized_body, bytes) else unauthorized_body

    assert "History for issue" in page_one
    assert page_one.count('class="pagination-controls"') >= 2
    assert page_one.count("Previous") >= 2 and page_one.count("Next") >= 2
    assert 'name="page"' in page_one
    assert 'name="id" value="%s"' % issue_id in page_one
    assert "1 of 2" in page_one and "2 of 2" in page_one
    assert 'type="submit" name="page"' not in page_one
    assert "type=\"button\" onclick=\"this.form.elements['page'].value=" in page_one
    assert "History entry 30" in page_one
    assert "History entry 06" in page_one
    assert "History entry 05" not in page_one
    assert "History entry 05" in page_two
    assert "History entry 01" in page_two
    assert "History entry 30" not in page_two
    assert "metadata.txt" in page_one
    assert "secret blob content" not in page_one
    assert "Reference" not in page_one
    assert "Comment #" not in page_one
    assert "These first few words should appear" in page_one
    assert "complete comment should not be displayed" not in page_one
    assert '<strong>&quot;not [started&quot;</strong>' in page_one
    assert '<strong>&quot;in progress&quot;</strong>' in page_one
    assert "403" in unauthorized_status
    assert "not authorized" in unauthorized.lower()


def test_issue_view_links_to_history_but_list_does_not_load_or_display_history(app, patched_environment, seed_issue, make_form, invoke_action, parse_headers, temp_db):
    issue_id = seed_issue(title="History link", creator_username="alice", assigned_username="bob", status="open")
    with sqlite3.connect(temp_db) as con:
        con.execute(
            """INSERT INTO issue_history
               (issue_id, actor_username, action, summary, comment_id, attachment_id, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (issue_id, "alice", "manual", "Sensitive history row", None, None, "2026-01-01 12:00:00+00:00"),
        )

    view_html = _html(parse_headers, invoke_action(app, "view", make_form(action="view", id=str(issue_id)), "alice"))
    list_html = _html(parse_headers, invoke_action(app, "list", make_form(action="list"), "alice"))

    assert "History" in view_html
    assert 'name="action" value="history"' in view_html
    assert "Sensitive history row" not in view_html
    assert "Sensitive history row" not in list_html
