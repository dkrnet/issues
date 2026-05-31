# Copyright (C) 2026 David Redmond
# SPDX-License-Identifier: AGPL-3.0-only
#
"""Requirements mapping: access/authentication, fake users/groups, assignable-user rules."""
from conftest import FakeUser, call_flex, find_callable


def test_missing_empty_and_unknown_remote_user_are_rejected(app, patched_environment, invoke_action, parse_headers):
    for remote_user in (None, "", "nobody"):
        output = invoke_action(app, action="list", user=remote_user)
        status, headers, body = parse_headers(output)
        joined = (status + " " + str(body)).lower()
        assert "403" in joined or "forbidden" in joined or "auth" in joined
        assert headers.get("content-type", "").startswith(("text/plain", "text/html"))


def test_valid_remote_user_is_accepted(app, patched_environment, invoke_action, parse_headers):
    output = invoke_action(app, action="list", user="alice")
    status, headers, body = parse_headers(output)
    html = body.decode("utf-8", "replace") if isinstance(body, bytes) else body
    assert "403" not in (status + str(body))
    assert headers.get("content-type", "").startswith("text/html")
    assert 'Current user: <strong>alice</strong>' in html
    assert f'<a class="logout-link" href="{app.LOGOUT_URL}">Logout</a>' in html
    assert '<strong>alice</strong> <span class="logout-wrapper">(' in html


def _html(parse_headers, output):
    body = parse_headers(output)[2]
    return body.decode("utf-8", "replace") if isinstance(body, bytes) else body


def test_public_authentication_support_pages_do_not_require_remote_user(app, patched_environment, invoke_action, make_form, parse_headers):
    for action, title_fragment in (
        ("login", "Issues Login"),
        ("login_failed", "Login Failed"),
        ("logged_out", "Logged Out"),
        ("auth_error", "Authentication Error"),
    ):
        output = invoke_action(app, action=action, form=make_form(action=action), user=None)
        _status, headers, body = parse_headers(output)
        html = body.decode("utf-8", "replace") if isinstance(body, bytes) else body
        assert headers.get("content-type", "").startswith("text/html")
        assert "<html" in html.lower()
        assert title_fragment in html
        assert "Current user:" not in html



def test_favicon_action_is_public_and_returns_embedded_icon(app, patched_environment, invoke_action, make_form, parse_headers):
    output = invoke_action(app, action="favicon", form=make_form(action="favicon"), user=None)
    status, headers, body = parse_headers(output)
    assert "403" not in status
    assert headers.get("content-type", "").startswith("image/x-icon")
    assert int(headers.get("content-length", "0")) > 0
    assert isinstance(body, bytes)
    assert body.startswith(b"\x00\x00\x01\x00")

def test_login_page_uses_configured_external_form_fields_without_authentication_disclosure(app, patched_environment, invoke_action, make_form, parse_headers):
    output = invoke_action(app, action="login", form=make_form(action="login"), user=None)
    html = _html(parse_headers, output)
    lower = html.lower()
    assert 'method="post"' in lower
    assert 'action="/login"' in lower
    assert 'name="httpd_username"' in lower
    assert 'name="httpd_password"' in lower
    assert 'type="password"' in lower
    assert 'name="httpd_location"' in lower
    assert 'value="/cgi-bin/issues.cgi"' in lower
    assert 'value="/issues.cgi"' not in lower
    assert 'value="issues.cgi"' not in lower
    assert "please sign in" in lower
    assert "apache" not in lower
    assert "pam" not in lower
    assert "web server" not in lower
    assert "authentication is handled" not in lower
    assert "do_login" not in lower and "check_password" not in lower


def test_login_destination_is_sanitized_and_password_is_not_echoed(app, patched_environment, invoke_action, make_form, parse_headers):
    form = make_form(action="login", httpd_location="https://evil.example/", httpd_password="secret-password")
    html = _html(parse_headers, invoke_action(app, action="login", form=form, user=None))
    assert 'value="/cgi-bin/issues.cgi"' in html.lower()
    assert 'value="/issues.cgi"' not in html.lower()
    assert 'value="issues.cgi"' not in html.lower()
    assert "evil.example" not in html
    assert "secret-password" not in html


def test_administrator_recognition_uses_fake_group_membership(app, patched_environment, monkeypatch):
    is_admin = find_callable(app, ["is_admin", "is_system_admin", "is_admin_user", "user_is_admin"])
    assert call_flex(is_admin, "admin", username="admin") is True
    assert call_flex(is_admin, "alice", username="alice") is False
    assert call_flex(is_admin, "mallory", username="mallory") is False

    monkeypatch.setattr(app, "ADMINS_GROUP_EXCLUDE", "admin", raising=False)
    assert call_flex(is_admin, "admin", username="admin") is False


def test_assignable_user_list_includes_only_allowed_users(app, patched_environment):
    get_assignable = find_callable(app, ["get_assignable_users", "assignable_users", "list_assignable_users"])
    users = call_flex(get_assignable)
    names = {u[0] if isinstance(u, (tuple, list)) else str(u) for u in users}
    assert {"alice", "bob", "admin"}.issubset(names)
    assert "vwboot" not in names
    assert "mallory" not in names


def test_assignable_user_dropdown_uses_explicit_group_members_only(app, patched_environment, monkeypatch, fake_users, fake_groups):
    # REGRESSION GUARD: Enumerating assignable users must not pick up accounts
    # only because their primary gid matches the configured group, such as local
    # service or games accounts. Submitted assignee validation is checked
    # separately with direct group-membership logic.
    fake_users["gamekeeper"] = FakeUser("gamekeeper", 2006, 2005)
    fake_users["primaryonly"] = FakeUser("primaryonly", 2007, 2005)
    fake_groups["games"] = {"gid": 2005, "members": ["gamekeeper"]}
    monkeypatch.setattr(app, "ASSIGNEE_GROUP", "games", raising=False)
    monkeypatch.setattr(app, "ASSIGNEE_EXCLUDE", "", raising=False)

    get_assignable = find_callable(app, ["get_assignable_users", "assignable_users", "list_assignable_users"])
    users = call_flex(get_assignable)
    names = {u[0] if isinstance(u, (tuple, list)) else str(u) for u in users}
    assert "gamekeeper" in names
    assert "primaryonly" not in names


def test_nonempty_assignee_must_be_assignable(app, patched_environment, seed_issue, make_form, invoke_action, parse_headers):
    validator = find_callable(app, ["is_valid_assignee", "validate_assignee", "is_assignable_user"], required=False)
    if validator is not None:
        assert call_flex(validator, "alice", username="alice") in (True, None)
        assert call_flex(validator, "mallory", username="mallory") is False
        assert call_flex(validator, "vwboot", username="vwboot") is False
        return

    # Some implementations expose assignee validation only through action handlers.
    issue_id = seed_issue(creator_username="alice", assigned_username="bob", status="open")
    good = invoke_action(app, "assign", make_form(action="assign", id=str(issue_id), assigned_username="alice"), "alice", method="POST")
    good_status, good_headers, good_body = parse_headers(good)
    assert "location" in good_headers or "303" in (good_status + str(good_body)) or "302" in (good_status + str(good_body))
    for bad_name in ("mallory", "vwboot"):
        bad = invoke_action(app, "assign", make_form(action="assign", id=str(issue_id), assigned_username=bad_name), "alice", method="POST")
        bad_status, _bad_headers, bad_body = parse_headers(bad)
        assert "400" in (bad_status + str(bad_body))
