# Copyright (C) 2026 David Redmond
# SPDX-License-Identifier: AGPL-3.0-only
#
"""Requirements mapping: per-user preferences, dynamic filters, and creator-filter privileges."""

import datetime as dt
import json

from conftest import html_has_control, html_has_option


def _html(parse_headers, output):
    body = parse_headers(output)[2]
    return body.decode("utf-8", "replace") if isinstance(body, bytes) else body


def _list(app, invoke_action, make_form, user="alice", **fields):
    return invoke_action(app, "list", make_form(action="list", **fields), user)


def _assert_contains_only(html, expected, absent):
    for title in expected:
        assert title in html, f"expected {title!r} in issue list"
    for title in absent:
        assert title not in html, f"did not expect {title!r} in issue list"


def test_admin_creator_filter_replaces_legacy_all_users_scope(app, patched_environment, seed_issue, write_config, invoke_action, make_form, parse_headers, temp_config_dir):
    seed_issue(title="Alice open", creator_username="alice", assigned_username="bob", priority="normal", status="open")
    seed_issue(title="Mallory open", creator_username="mallory", assigned_username="", priority="normal", status="open")
    seed_issue(title="Bob closed", creator_username="bob", assigned_username="alice", priority="normal", status="closed")

    write_config("admin", {"status": "open", "priority": "any", "creator": "any", "all": True})
    admin_html = _html(parse_headers, _list(app, invoke_action, make_form, "admin"))
    assert "Alice open" in admin_html and "Mallory open" in admin_html
    assert "Bob closed" not in admin_html
    assert html_has_control(admin_html, "creator")
    assert not html_has_control(admin_html, "all")
    assert "all users issues" not in admin_html.lower()

    alice_only = _html(parse_headers, _list(app, invoke_action, make_form, "admin", status="open", priority="any", creator="alice"))
    _assert_contains_only(alice_only, ["Alice open"], ["Mallory open", "Bob closed"])
    saved = json.loads((temp_config_dir / "admin.json").read_text(encoding="utf-8"))
    assert saved["status"] == "open"
    assert saved["priority"] == "any"
    assert saved["creator"] == "alice"
    assert "all" not in saved


def test_static_and_dynamic_filter_controls_and_options_are_rendered_precisely(app, patched_environment, seed_issue, seed_comment, seed_attachment, invoke_action, make_form, parse_headers):
    commented = seed_issue(title="Commented", creator_username="alice", assigned_username="bob", state="waiting", priority="high")
    attached = seed_issue(title="Attached", creator_username="alice", assigned_username="", state="deferred", priority="high")
    seed_issue(title="Mallory option", creator_username="mallory", assigned_username="bob", state="waiting", priority="high")
    seed_comment(commented)
    seed_attachment(attached)

    admin_html = _html(parse_headers, _list(app, invoke_action, make_form, "admin", status="open", priority="high"))
    assert html_has_control(admin_html, "creator")
    for name in ("priority", "assignee", "state", "due_date", "has_comments", "has_attachments"):
        assert html_has_control(admin_html, name)
    static_start = admin_html.find('class="static-filters"')
    dynamic_start = admin_html.find('class="dynamic-filters"')
    assert static_start >= 0 and dynamic_start > static_start
    static_html = admin_html[static_start:dynamic_start]
    dynamic_html = admin_html[dynamic_start:admin_html.find("<noscript>", dynamic_start)]
    for name in ('name="status"', 'name="due_date"', 'name="has_comments"', 'name="has_attachments"'):
        assert name in static_html
    assert 'name="priority"' not in static_html
    for name in ('name="priority"', 'name="creator"', 'name="assignee"', 'name="state"'):
        assert name in dynamic_html
    assert dynamic_html.find('name="priority"') < dynamic_html.find('name="creator"') < dynamic_html.find('name="assignee"') < dynamic_html.find('name="state"')
    for value in ("any", "high"):
        assert html_has_option(admin_html, value)
    for value in ("any", "alice", "mallory"):
        assert html_has_option(admin_html, value)
    for value in ("any", "bob", "unassigned"):
        assert html_has_option(admin_html, value)
    for value in ("any", "waiting", "deferred"):
        assert html_has_option(admin_html, value)
    for value in ("any", "no due date", "today", "within 5 days", "within 30 days"):
        assert html_has_option(admin_html, value)

    alice_html = _html(parse_headers, _list(app, invoke_action, make_form, "alice", status="open", priority="high"))
    assert not html_has_control(alice_html, "creator")
    for name in ("priority", "assignee", "state", "due_date", "has_comments", "has_attachments"):
        assert html_has_control(alice_html, name)



def test_dynamic_priority_options_follow_static_filter_group(app, patched_environment, seed_issue, seed_comment, invoke_action, make_form, parse_headers):
    high_comment = seed_issue(title="High commented", creator_username="alice", assigned_username="bob", priority="high", status="open")
    seed_comment(high_comment)
    seed_issue(title="Low no comment", creator_username="alice", assigned_username="bob", priority="low", status="open")
    seed_issue(title="Closed normal", creator_username="alice", assigned_username="bob", priority="normal", status="closed")

    html = _html(parse_headers, _list(app, invoke_action, make_form, "alice", status="open", has_comments="1"))
    dynamic_start = html.find('class="dynamic-filters"')
    dynamic_html = html[dynamic_start:html.find("<noscript>", dynamic_start)]
    assert 'value="high"' in dynamic_html
    assert 'value="low"' not in dynamic_html
    assert 'value="normal"' not in dynamic_html

    html = _html(parse_headers, _list(app, invoke_action, make_form, "alice", status="open"))
    dynamic_start = html.find('class="dynamic-filters"')
    dynamic_html = html[dynamic_start:html.find("<noscript>", dynamic_start)]
    assert 'value="high"' in dynamic_html
    assert 'value="low"' in dynamic_html
    assert 'value="normal"' not in dynamic_html

def test_dynamic_filters_apply_individually_and_in_combination(app, patched_environment, seed_issue, seed_comment, seed_attachment, invoke_action, make_form, parse_headers):
    bob_waiting = seed_issue(title="Bob waiting commented", creator_username="alice", assigned_username="bob", priority="high", state="waiting", status="open")
    admin_waiting = seed_issue(title="Admin waiting attached", creator_username="alice", assigned_username="admin", priority="high", state="waiting", status="open")
    seed_issue(title="Unassigned deferred", creator_username="alice", assigned_username="", priority="high", state="deferred", status="open")
    seed_issue(title="Low priority bob", creator_username="alice", assigned_username="bob", priority="low", state="waiting", status="open")
    seed_comment(bob_waiting)
    seed_attachment(admin_waiting)

    base_absent = ["Admin waiting attached", "Unassigned deferred", "Low priority bob"]
    html = _html(parse_headers, _list(app, invoke_action, make_form, status="open", priority="high", assignee="bob"))
    _assert_contains_only(html, ["Bob waiting commented"], base_absent)

    html = _html(parse_headers, _list(app, invoke_action, make_form, status="open", priority="high", assignee="unassigned"))
    _assert_contains_only(html, ["Unassigned deferred"], ["Bob waiting commented", "Admin waiting attached", "Low priority bob"])

    html = _html(parse_headers, _list(app, invoke_action, make_form, status="open", priority="high", assignee="any", state="waiting", due_date="any"))
    _assert_contains_only(html, ["Bob waiting commented", "Admin waiting attached"], ["Unassigned deferred", "Low priority bob"])

    html = _html(parse_headers, _list(app, invoke_action, make_form, status="open", priority="high", assignee="any", state="any", due_date="any", has_comments="1"))
    _assert_contains_only(html, ["Bob waiting commented"], ["Admin waiting attached", "Unassigned deferred", "Low priority bob"])

    html = _html(parse_headers, _list(app, invoke_action, make_form, status="open", priority="high", assignee="any", state="any", due_date="any", has_attachments="1"))
    _assert_contains_only(html, ["Admin waiting attached"], ["Bob waiting commented", "Unassigned deferred", "Low priority bob"])

    html = _html(parse_headers, _list(app, invoke_action, make_form, status="open", priority="high", assignee="bob", state="waiting", due_date="any", has_comments="1"))
    _assert_contains_only(html, ["Bob waiting commented"], ["Admin waiting attached", "Unassigned deferred", "Low priority bob"])


def test_static_due_date_filters_use_current_utc_day(app, patched_environment, seed_issue, invoke_action, make_form, parse_headers, monkeypatch):
    class FrozenDateTime(dt.datetime):
        @classmethod
        def now(cls, tz=None):
            base = cls(2026, 5, 17, 12, 0, 0)
            return base.replace(tzinfo=tz) if tz else base

        @classmethod
        def today(cls):
            return cls(2026, 5, 17, 12, 0, 0)

    class FrozenDate(dt.date):
        @classmethod
        def today(cls):
            return cls(2026, 5, 17)

    if hasattr(app, "datetime") and hasattr(app.datetime, "datetime"):
        monkeypatch.setattr(app.datetime, "datetime", FrozenDateTime, raising=False)
    if hasattr(app, "datetime") and hasattr(app.datetime, "date"):
        monkeypatch.setattr(app.datetime, "date", FrozenDate, raising=False)
    if hasattr(app, "dt") and hasattr(app.dt, "datetime"):
        monkeypatch.setattr(app.dt, "datetime", FrozenDateTime, raising=False)
    if hasattr(app, "dt") and hasattr(app.dt, "date"):
        monkeypatch.setattr(app.dt, "date", FrozenDate, raising=False)
    if hasattr(app, "_dt") and hasattr(app._dt, "datetime"):
        monkeypatch.setattr(app._dt, "datetime", FrozenDateTime, raising=False)
    if hasattr(app, "_dt") and hasattr(app._dt, "date"):
        monkeypatch.setattr(app._dt, "date", FrozenDate, raising=False)
    if hasattr(app, "date"):
        monkeypatch.setattr(app, "date", FrozenDate, raising=False)

    seed_issue(title="No due", creator_username="alice", assigned_username="bob", due_date=None, status="open")
    seed_issue(title="Today", creator_username="alice", assigned_username="bob", due_date="2026-05-17", status="open")
    seed_issue(title="In five", creator_username="alice", assigned_username="bob", due_date="2026-05-22", status="open")
    seed_issue(title="In thirty", creator_username="alice", assigned_username="bob", due_date="2026-06-16", status="open")
    seed_issue(title="After thirty", creator_username="alice", assigned_username="bob", due_date="2026-06-17", status="open")
    seed_issue(title="Closed today", creator_username="alice", assigned_username="bob", due_date="2026-05-17", status="closed")

    html = _html(parse_headers, _list(app, invoke_action, make_form, due_date="no due date"))
    _assert_contains_only(html, ["No due"], ["Today", "In five", "In thirty", "After thirty", "Closed today"])

    html = _html(parse_headers, _list(app, invoke_action, make_form, due_date="today"))
    _assert_contains_only(html, ["Today"], ["No due", "In five", "In thirty", "After thirty", "Closed today"])

    html = _html(parse_headers, _list(app, invoke_action, make_form, due_date="within 5 days"))
    _assert_contains_only(html, ["Today", "In five"], ["No due", "In thirty", "After thirty", "Closed today"])

    html = _html(parse_headers, _list(app, invoke_action, make_form, due_date="within 30 days"))
    _assert_contains_only(html, ["Today", "In five", "In thirty"], ["No due", "After thirty", "Closed today"])

    html = _html(parse_headers, _list(app, invoke_action, make_form, due_date="any"))
    _assert_contains_only(html, ["No due", "Today", "In five", "In thirty", "After thirty"], ["Closed today"])


def test_all_filter_preferences_are_saved_read_and_invalid_values_are_ignored(app, patched_environment, seed_issue, seed_comment, seed_attachment, invoke_action, make_form, parse_headers, temp_config_dir, write_config):
    # REGRESSION GUARD: Use a due date relative to the current UTC date so the
    # within-30-days preference test does not fail when a hard-coded date ages
    # out of the active filter window.
    future_due = (dt.datetime.now(dt.timezone.utc).date() + dt.timedelta(days=5)).isoformat()
    issue_id = seed_issue(title="Preference target", creator_username="alice", assigned_username="bob", priority="high", state="waiting", due_date=future_due)
    seed_comment(issue_id)
    seed_attachment(issue_id)

    form = make_form(
        action="list",
        status="open",
        priority="high",
        creator="alice",
        assignee="bob",
        state="waiting",
        due_date="within 30 days",
        has_comments="1",
        has_attachments="1",
    )
    html = _html(parse_headers, invoke_action(app, "list", form, "admin"))
    assert "Preference target" in html
    saved = json.loads((temp_config_dir / "admin.json").read_text(encoding="utf-8"))
    assert saved == {
        "status": "open",
        "priority": "high",
        "creator": "alice",
        "assignee": "bob",
        "state": "waiting",
        "due_date": "within 30 days",
        "has_comments": True,
        "has_attachments": True,
        "search": "",
        "auto_refresh": "never",
    }

    # REGRESSION GUARD: unchecked checkboxes are omitted from GET forms. When
    # another submitted filter value is present, missing comments/attachments
    # checkbox fields must clear the saved preferences rather than preserving
    # stale True values.
    clear_form = make_form(
        action="list",
        status="open",
        priority="high",
        creator="alice",
        assignee="bob",
        state="waiting",
        due_date="within 30 days",
    )
    invoke_action(app, "list", clear_form, "admin")
    cleared = json.loads((temp_config_dir / "admin.json").read_text(encoding="utf-8"))
    assert cleared["has_comments"] is False
    assert cleared["has_attachments"] is False

    write_config("admin", {
        "status": "nonsense",
        "priority": "urgent",
        "creator": "nobody",
        "assignee": "vwboot",
        "state": "bogus",
        "due_date": "someday",
        "has_comments": "yes please",
        "has_attachments": "definitely",
        "search": 123,
        "all": True,
    })
    html = _html(parse_headers, invoke_action(app, "list", make_form(action="list"), "admin"))
    for name in ("status", "priority", "creator", "assignee", "state", "due_date", "has_comments", "has_attachments", "search"):
        assert html_has_control(html, name)
    assert not html_has_control(html, "all")


def test_non_admin_filters_never_broaden_visibility_from_submitted_or_stored_values(app, patched_environment, seed_issue, seed_comment, seed_attachment, write_config, invoke_action, make_form, parse_headers):
    alice_issue = seed_issue(title="Alice visible", creator_username="alice", assigned_username="bob", state="waiting", status="open")
    mallory_issue = seed_issue(title="Mallory hidden", creator_username="mallory", assigned_username="admin", state="deferred", status="open")
    seed_comment(mallory_issue)
    seed_attachment(mallory_issue)

    submitted = _html(parse_headers, _list(
        app,
        invoke_action,
        make_form,
        "alice",
        status="open",
        priority="any",
        creator="mallory",
        assignee="admin",
        state="deferred",
        due_date="any",
        has_comments="1",
        has_attachments="1",
    ))
    assert "Mallory hidden" not in submitted
    assert "Alice visible" not in submitted or "no issues" in submitted.lower() or "Mallory hidden" not in submitted

    write_config("alice", {
        "status": "open",
        "priority": "any",
        "creator": "mallory",
        "assignee": "admin",
        "state": "deferred",
        "due_date": "any",
        "has_comments": True,
        "has_attachments": True,
        "all": True,
    })
    stored = _html(parse_headers, _list(app, invoke_action, make_form, "alice"))
    assert "Mallory hidden" not in stored
    assert not html_has_control(stored, "creator")
    assert not html_has_control(stored, "all")


def test_auto_refresh_preference_is_saved_reloaded_and_emits_refresh_script(app, patched_environment, seed_issue, invoke_action, make_form, parse_headers, temp_config_dir, write_config):
    seed_issue(title="Refresh target", creator_username="alice", assigned_username="bob", status="open")

    html = _html(parse_headers, _list(app, invoke_action, make_form, "alice", status="open", priority="any", auto_refresh="10 minutes"))
    assert "Refresh target" in html
    assert "Auto-refresh" in html
    assert "setTimeout" in html and "600000" in html
    saved = json.loads((temp_config_dir / "alice.json").read_text(encoding="utf-8"))
    assert saved["auto_refresh"] == "10 minutes"

    reloaded = _html(parse_headers, invoke_action(app, "list", make_form(action="list"), "alice"))
    assert 'name="auto_refresh"' in reloaded
    assert 'value="10 minutes" selected' in reloaded or 'selected>10 minutes</option>' in reloaded

    # REGRESSION GUARD: The auto-refresh selector form must not also contain a
    # hidden auto_refresh field with the previous value. Some browsers submit
    # both values, and cgi.FieldStorage.getfirst() then reloads the stale value
    # instead of saving the newly selected option.
    marker = 'class="auto-refresh-control"'
    start = reloaded.find(marker)
    assert start >= 0, reloaded
    end = reloaded.find('</form>', start)
    assert end >= 0, reloaded[start:]
    auto_refresh_form = reloaded[start:end]
    assert auto_refresh_form.count('name="auto_refresh"') == 1
    assert 'type="hidden" name="auto_refresh"' not in auto_refresh_form
    assert 'class="last-refreshed"' in auto_refresh_form
    assert 'data-refreshed-at-utc=' in auto_refresh_form
    assert "(Last refreshed: just now)" in auto_refresh_form
    assert 'class="local-timestamp"' not in auto_refresh_form
    assert 'renderRelativeRefreshTimes' in reloaded
    assert 'setInterval(renderRelativeRefreshTimes, 60000)' in reloaded
    assert 'font-size: 0.9em' in reloaded

    write_config("alice", {"status": "open", "priority": "any", "auto_refresh": "every second"})
    fallback = _html(parse_headers, invoke_action(app, "list", make_form(action="list"), "alice"))
    assert 'value="never" selected' in fallback or 'selected>never</option>' in fallback
    assert "setTimeout" not in fallback


def test_issue_list_search_matches_title_description_comments_and_attachment_metadata(app, patched_environment, seed_issue, seed_comment, seed_attachment, invoke_action, make_form, parse_headers):
    title_match = seed_issue(title="Printer queue failure", description="Routine description", creator_username="alice", assigned_username="bob", priority="high")
    description_match = seed_issue(title="Network problem", description="Conference room projector Wi-Fi drops during calls", creator_username="alice", assigned_username="bob", priority="normal")
    comment_match = seed_issue(title="Payroll laptop", description="Routine description", creator_username="alice", assigned_username="bob", priority="low")
    attachment_filename_match = seed_issue(title="Accounting share", description="Routine description", creator_username="alice", assigned_username="", priority="normal")
    attachment_uploader_match = seed_issue(title="Scanner issue", description="Routine description", creator_username="alice", assigned_username="bob", priority="normal")
    attachment_timestamp_match = seed_issue(title="Timestamp issue", description="Routine description", creator_username="alice", assigned_username="bob", priority="normal")
    attachment_content_only = seed_issue(title="Hidden blob", description="Routine description", creator_username="alice", assigned_username="bob", priority="normal")
    unrelated = seed_issue(title="Unrelated", description="Routine description", creator_username="alice", assigned_username="bob", priority="normal")

    seed_comment(comment_match, text="The receipt scanner jams every morning.")
    seed_attachment(attachment_filename_match, filename="printer-diagnostics.pdf", content=b"nothing useful", user="alice")
    seed_attachment(attachment_uploader_match, filename="notes.txt", content=b"nothing useful", user="admin")
    seed_attachment(attachment_timestamp_match, filename="date-note.txt", content=b"nothing useful", user="alice", created_at="2026-07-04T12:00:00")
    seed_attachment(attachment_content_only, filename="blob.txt", content=b"secret-search-token", user="alice")

    title_html = _html(parse_headers, _list(app, invoke_action, make_form, "admin", status="any", priority="any", search="printer queue"))
    _assert_contains_only(title_html, ["Printer queue failure"], ["Network problem", "Payroll laptop", "Accounting share", "Scanner issue", "Timestamp issue", "Hidden blob", "Unrelated"])

    description_html = _html(parse_headers, _list(app, invoke_action, make_form, "admin", status="any", priority="any", search="projector wi-fi"))
    _assert_contains_only(description_html, ["Network problem"], ["Printer queue failure", "Payroll laptop", "Accounting share", "Scanner issue", "Timestamp issue", "Hidden blob", "Unrelated"])

    comment_html = _html(parse_headers, _list(app, invoke_action, make_form, "admin", status="any", priority="any", search="receipt scanner"))
    _assert_contains_only(comment_html, ["Payroll laptop"], ["Printer queue failure", "Network problem", "Accounting share", "Scanner issue", "Timestamp issue", "Hidden blob", "Unrelated"])

    filename_html = _html(parse_headers, _list(app, invoke_action, make_form, "admin", status="any", priority="any", search="diagnostics"))
    _assert_contains_only(filename_html, ["Accounting share"], ["Printer queue failure", "Network problem", "Payroll laptop", "Scanner issue", "Timestamp issue", "Hidden blob", "Unrelated"])

    uploader_html = _html(parse_headers, _list(app, invoke_action, make_form, "admin", status="any", priority="any", search="admin"))
    _assert_contains_only(uploader_html, ["Scanner issue"], ["Printer queue failure", "Network problem", "Payroll laptop", "Accounting share", "Timestamp issue", "Hidden blob", "Unrelated"])

    timestamp_html = _html(parse_headers, _list(app, invoke_action, make_form, "admin", status="any", priority="any", search="2026-07-04"))
    _assert_contains_only(timestamp_html, ["Timestamp issue"], ["Printer queue failure", "Network problem", "Payroll laptop", "Accounting share", "Scanner issue", "Hidden blob", "Unrelated"])

    content_html = _html(parse_headers, _list(app, invoke_action, make_form, "admin", status="any", priority="any", search="secret-search-token"))
    _assert_contains_only(content_html, [], ["Printer queue failure", "Network problem", "Payroll laptop", "Accounting share", "Scanner issue", "Timestamp issue", "Hidden blob", "Unrelated"])


def test_search_is_saved_restored_cleared_and_preserved_by_pagination(app, patched_environment, seed_issue, write_config, invoke_action, make_form, parse_headers, temp_config_dir):
    seed_issue(title="Printer queue failure", description="Routine description", creator_username="alice", assigned_username="bob")
    seed_issue(title="Unrelated", description="Routine description", creator_username="alice", assigned_username="bob")

    submitted = _html(parse_headers, _list(app, invoke_action, make_form, "alice", status="any", priority="any", search="printer"))
    _assert_contains_only(submitted, ["Printer queue failure"], ["Unrelated"])
    saved = json.loads((temp_config_dir / "alice.json").read_text(encoding="utf-8"))
    assert saved["search"] == "printer"

    restored = _html(parse_headers, _list(app, invoke_action, make_form, "alice"))
    _assert_contains_only(restored, ["Printer queue failure"], ["Unrelated"])
    assert 'name="search" value="printer"' in restored
    assert 'type="hidden" name="search" value="printer"' in restored

    cleared = _html(parse_headers, _list(app, invoke_action, make_form, "alice", status="any", priority="any", search=""))
    assert "Printer queue failure" in cleared and "Unrelated" in cleared
    saved = json.loads((temp_config_dir / "alice.json").read_text(encoding="utf-8"))
    assert saved["search"] == ""


def test_search_respects_authorization_updates_dynamic_options_and_has_no_side_effects(app, patched_environment, seed_issue, seed_comment, invoke_action, make_form, parse_headers, fetch_history, monkeypatch):
    visible = seed_issue(title="Visible printer issue", description="Need printer repair", creator_username="alice", assigned_username="bob", priority="high", state="waiting")
    hidden = seed_issue(title="Hidden printer issue", description="Need printer repair", creator_username="mallory", assigned_username="", priority="low", state="deferred")
    seed_comment(hidden, text="printer secret comment", user="mallory")

    calls = []
    monkeypatch.setattr(app, "EMAIL_NOTIFICATIONS_ENABLED", True, raising=False)
    monkeypatch.setattr(app.subprocess, "run", lambda *args, **kwargs: calls.append((args, kwargs)), raising=False)

    alice_html = _html(parse_headers, _list(app, invoke_action, make_form, "alice", status="any", priority="any", search="printer"))
    _assert_contains_only(alice_html, ["Visible printer issue"], ["Hidden printer issue"])
    assert html_has_option(alice_html, "high")
    assert not html_has_option(alice_html, "low")
    assert html_has_option(alice_html, "waiting")
    assert not html_has_option(alice_html, "deferred")

    assert fetch_history(visible) == []
    assert fetch_history(hidden) == []
    assert calls == []


def test_search_uses_literal_parameterized_like_text(app, patched_environment, seed_issue, invoke_action, make_form, parse_headers):
    seed_issue(title="100% real printer issue", description="Routine description", creator_username="alice", assigned_username="bob")
    seed_issue(title="100X real printer issue", description="Routine description", creator_username="alice", assigned_username="bob")
    seed_issue(title="Under_score issue", description="Routine description", creator_username="alice", assigned_username="bob")
    seed_issue(title="UnderXscore issue", description="Routine description", creator_username="alice", assigned_username="bob")

    percent_html = _html(parse_headers, _list(app, invoke_action, make_form, "alice", status="any", priority="any", search="100%"))
    _assert_contains_only(percent_html, ["100% real printer issue"], ["100X real printer issue"])

    underscore_html = _html(parse_headers, _list(app, invoke_action, make_form, "alice", status="any", priority="any", search="Under_score"))
    _assert_contains_only(underscore_html, ["Under_score issue"], ["UnderXscore issue"])

