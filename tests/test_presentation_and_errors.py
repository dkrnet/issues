# Copyright (C) 2026 David Redmond
# SPDX-License-Identifier: AGPL-3.0-only
#
"""Requirements mapping: banners, Markdown help links, precise error responses, and canceled-status UI."""

import pytest

from conftest import assert_banner_uses_config
from test_requirement_expansion import assert_client_or_forbidden


def _html(parse_headers, output):
    body = parse_headers(output)[2]
    return body.decode("utf-8", "replace") if isinstance(body, bytes) else body


def _headers_and_text(parse_headers, output):
    status, headers, body = parse_headers(output)
    text = body.decode("utf-8", "replace") if isinstance(body, bytes) else str(body)
    return status, headers, text


@pytest.mark.parametrize("action,user", [
    ("list", "alice"),
    ("create", "alice"),
    ("markdown_help", "alice"),
])
def test_top_banner_is_present_on_global_pages(app, patched_environment, invoke_action, make_form, parse_headers, action, user):
    html = _html(parse_headers, invoke_action(app, action, make_form(action=action), user))
    assert_banner_uses_config(html)


@pytest.mark.parametrize("action,user", [
    ("view", "alice"),
    ("update", "alice"),
    ("comment", "alice"),
    ("attach", "alice"),
    ("close", "alice"),
    ("cancel", "alice"),
])
def test_top_banner_is_present_on_issue_pages_and_forms(app, patched_environment, seed_issue, invoke_action, make_form, parse_headers, action, user):
    issue_id = seed_issue(creator_username="alice", assigned_username="bob", status="open")
    html = _html(parse_headers, invoke_action(app, action, make_form(action=action, id=str(issue_id)), user))
    assert_banner_uses_config(html)


@pytest.mark.parametrize("action", ["create", "update", "comment", "close", "cancel"])
def test_markdown_help_links_open_in_new_tab_with_safe_rel(app, patched_environment, seed_issue, invoke_action, make_form, parse_headers, action):
    issue_id = seed_issue(creator_username="alice", assigned_username="bob", status="open")
    form = make_form(action=action) if action == "create" else make_form(action=action, id=str(issue_id))
    html = _html(parse_headers, invoke_action(app, action, form, "alice"))
    lower = html.lower()
    assert "markdown" in lower and "help" in lower
    assert 'target="_blank"' in lower
    assert "rel=" in lower and "noopener" in lower and "noreferrer" in lower



def test_create_form_uses_assignee_label(app, patched_environment, invoke_action, make_form, parse_headers):
    html = _html(parse_headers, invoke_action(app, "create", make_form(action="create"), "alice"))
    assert "Assignee" in html
    assert "Assigned user" not in html


def test_error_responses_use_required_status_codes_and_content_types(app, patched_environment, seed_issue, make_form, invoke_action, parse_headers):
    issue_id = seed_issue(creator_username="alice", assigned_username="bob", status="open")
    checks = [
        ("create", make_form(action="create", title="", description="body", priority="normal"), "alice", "POST", "400"),
        ("set_priority", make_form(action="set_priority", id=str(issue_id), priority="urgent"), "alice", "POST", "400"),
        ("set_percent_complete", make_form(action="set_percent_complete", id=str(issue_id), pct_complete="101"), "bob", "POST", "400"),
        ("view", make_form(action="view", id=str(issue_id)), "mallory", "GET", "403"),
        ("view", make_form(action="view", id="999999"), "alice", "GET", "404"),
        ("download", make_form(action="download", id="999999"), "alice", "GET", "404"),
    ]
    for action, form, user, method, code in checks:
        status, headers, text = _headers_and_text(parse_headers, invoke_action(app, action, form, user, method=method))
        assert code in (status + text), (action, status, text)
        assert headers.get("content-type", "").startswith(("text/plain", "text/html")), (action, headers)


def test_canceled_status_is_first_class_in_filters_preferences_and_view_controls(app, patched_environment, seed_issue, invoke_action, make_form, parse_headers, write_config):
    open_id = seed_issue(title="Open issue", creator_username="alice", assigned_username="bob", status="open")
    canceled_id = seed_issue(title="Canceled issue", creator_username="alice", assigned_username="bob", status="canceled", completed_at="2026-01-01T12:00:00+00:00", due_date=None)
    closed_id = seed_issue(title="Closed issue", creator_username="alice", assigned_username="bob", status="closed", completed_at="2026-01-01T12:00:00+00:00")

    html = _html(parse_headers, invoke_action(app, "list", make_form(action="list", status="canceled", priority="any"), "alice"))
    assert "Canceled issue" in html
    assert "Open issue" not in html and "Closed issue" not in html

    write_config("alice", {"status": "canceled", "priority": "any", "assignee": "any", "state": "any", "due_date": "any"})
    html = _html(parse_headers, invoke_action(app, "list", make_form(action="list"), "alice"))
    assert "Canceled issue" in html
    assert "Open issue" not in html

    creator_html = _html(parse_headers, invoke_action(app, "view", make_form(action="view", id=str(canceled_id)), "alice"))
    admin_html = _html(parse_headers, invoke_action(app, "view", make_form(action="view", id=str(canceled_id)), "admin"))
    assert "completed" in creator_html.lower()
    for forbidden in ('name="assigned_username"', 'name="priority"', 'name="due_date"', 'name="pct_complete"', 'name="state"', "Edit Title"):
        assert forbidden not in creator_html
    assert '>Cancel<' not in creator_html and 'action="cancel"' not in creator_html.lower()
    assert '>Close<' not in creator_html and 'action="close"' not in creator_html.lower()
    assert "Re-open" not in creator_html
    assert "Re-open" in admin_html or "reopen" in admin_html.lower()

    for action in ("update", "assign", "set_priority", "set_due_date", "set_percent_complete", "set_state", "close", "cancel"):
        assert_client_or_forbidden(parse_headers, invoke_action(app, action, make_form(action=action, id=str(canceled_id)), "alice", method="POST"), "400", "403")

    assert open_id and closed_id  # keep seeded titles explicit and satisfy linters


def test_configured_banner_is_rendered_before_page_heading(app, patched_environment, monkeypatch, invoke_action, parse_headers):
    monkeypatch.setattr(app, "BANNER_FILE", "/images/custom_banner.png", raising=False)
    monkeypatch.setattr(app, "BANNER_DIMENSIONS", "640x80", raising=False)
    html = _html(parse_headers, invoke_action(app, "list", user="alice"))
    assert_banner_uses_config(html, "/images/custom_banner.png", "640x80")


def test_version_footer_renders_only_on_authenticated_pages(app, patched_environment, monkeypatch, invoke_action, make_form, parse_headers):
    monkeypatch.setattr(app, "ISSUES_VERSION", "1.2.3", raising=False)

    authenticated_html = _html(parse_headers, invoke_action(app, "list", make_form(action="list"), "alice"))
    assert '<footer class="app-footer">Issues 1.2.3</footer>' in authenticated_html

    for action in ("login", "login_failed", "logged_out", "auth_error"):
        public_html = _html(parse_headers, invoke_action(app, action, make_form(action=action), None))
        assert "1.2.3" not in public_html
        assert 'class="app-footer"' not in public_html


def test_text_entry_forms_autofocus_top_left_field_but_list_and_view_do_not(app, patched_environment, seed_issue, invoke_action, make_form, parse_headers):
    issue_id = seed_issue(creator_username="alice", assigned_username="bob", status="open")
    checks = [
        ("login", make_form(action="login"), None, 'id="auth_username" name="httpd_username" autocomplete="username" autofocus'),
        ("create", make_form(action="create"), "alice", 'name="title" size="80" required autofocus'),
        ("update", make_form(action="update", id=str(issue_id)), "alice", 'name="title" size="80" value='),
        ("comment", make_form(action="comment", id=str(issue_id)), "alice", 'name="comment_text" required autofocus'),
        ("close", make_form(action="close", id=str(issue_id)), "alice", 'name="closing_comment" autofocus'),
        ("cancel", make_form(action="cancel", id=str(issue_id)), "alice", 'name="cancel_comment" autofocus'),
    ]
    for action, form, user, fragment in checks:
        html = _html(parse_headers, invoke_action(app, action, form, user))
        assert fragment in html
        assert "autofocus" in html

    update_html = _html(parse_headers, invoke_action(app, "update", make_form(action="update", id=str(issue_id)), "alice"))
    assert 'required autofocus' in update_html

    list_html = _html(parse_headers, invoke_action(app, "list", make_form(action="list"), "alice"))
    view_html = _html(parse_headers, invoke_action(app, "view", make_form(action="view", id=str(issue_id)), "alice"))
    assert "autofocus" not in list_html.lower()
    assert "autofocus" not in view_html.lower()
