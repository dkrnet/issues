#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-only
#
# Issues CGI Application
# Copyright (C) 2026 David Redmond
#
# This program is free software: you can redistribute it and/or modify it
# under the terms of version 3 of the GNU Affero General Public License
# as published by the Free Software Foundation.
#
# See the LICENSE file for the full license text.

# =============================================================================
# AI / LLM EDITING GUARDRAIL -- READ BEFORE MODIFYING
# =============================================================================
#
# This file is part of the Issues CGI application and depends on external
# project requirements.
#
# STOP: Before making any non-trivial edit to this file, an AI/LLM assistant
# must have the current requirements.md, regression_testing_requirements.md,
# and AGENTS.md files in the current chat or working context and must read them 
# before changing code.
#
# If these files have not been provided, the correct response is exactly:
#
#   Please provide the following files before I modify this file
#     - requirements.md
#     - regression_testing_requirements.md
#     - AGENTS.md
#
# Do not proceed with non-trivial code changes until these files have been
# provided and reviewed, unless the user explicitly directs you to proceed
# without it or to disregard this requirement.
#
# =============================================================================
"""
issues.cgi - CGI issue tracker backed by SQLite.

This script is intentionally self-contained. It expects an existing SQLite
schema matching the requirements document and dispatches all requests through
this single CGI entry point using the `action` query/form parameter.
"""

from __future__ import annotations

import base64
import cgi
import datetime as _dt
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from email.message import EmailMessage
import grp
import html
import json
import mimetypes
import os
import pwd
import re
import sqlite3
import subprocess
import sys
import traceback
from pathlib import Path
from typing import Any, Iterable, Optional
from urllib.parse import parse_qs, urlencode, urlsplit

# ---------------------------------------------------------------------------
# Global configuration
# ---------------------------------------------------------------------------

DB_FILE = "/var/lib/issues/issues.db"
DEFAULT_CLOSING_COMMENT = "no comment provided"
ISSUES_VERSION = "1.0.0-dev.12+d94c448"
MAX_UPLOAD_BYTES = 10485760
ASSIGNEE_GROUP = "users"
ASSIGNEE_EXCLUDE = ""
PER_USER_CONFIG_DIR = "/var/lib/issues/config"
CONFIG_DEFAULTS = {
    "status": "open",
    "priority": "any",
    "creator": "any",
    "assignee": "any",
    "state": "any",
    "due_date": "any",
    "has_comments": False,
    "has_attachments": False,
    "search": "",
    "auto_refresh": "never",
}
MAX_FILENAME_LEN = 255
STATUSES = ("any", "open", "closed", "canceled")
PRIORITIES = ("any", "high", "normal", "low")
STATES = ("not started", "in progress", "deferred", "waiting", "complete")
ADMINS_GROUP = "wheel"
ADMINS_GROUP_EXCLUDE = ""
ADMINS_EXCLUDE = ADMINS_GROUP_EXCLUDE  # compatibility with the user-provided name
BANNER_FILE = ""
BANNER_DIMENSIONS = ""
AUTH_FORM_ACTION = "/login"
AUTH_FORM_USERNAME_FIELD = "httpd_username"
AUTH_FORM_PASSWORD_FIELD = "httpd_password"
AUTH_FORM_LOCATION_FIELD = "httpd_location"
AUTH_FORM_LOCATION_ALIASES = ("next", "return_to", "return", "redirect_to", "redirect", "url")
AUTH_FORM_LOCATION_PATH_FIELD = "next_path"
AUTH_FORM_LOCATION_QUERY_FIELD = "next_query"
# REGRESSION GUARD: This default destination must match the deployed CGI URL.
# If it is changed to /issues.cgi or a relative issues.cgi path, successful
# form authentication redirects users away from /cgi-bin/issues.cgi.
AUTH_FORM_DEFAULT_LOCATION = "/cgi-bin/issues.cgi"
LOGOUT_URL = "/issues-logout"
FAVICON_MIME_TYPE = "image/x-icon"
SITE_CONFIG_FILE = "/etc/issues.conf"
EMAIL_NOTIFICATIONS_ENABLED = False
SENDMAIL_PATH = "/usr/sbin/sendmail"
NOTIFICATION_FROM = "issues@localhost"
NOTIFICATION_SUBJECT_PREFIX = "[Issues]"
ISSUE_BASE_URL = ""
NOTIFICATION_TRIAGE_RECIPIENTS = "root"
NOTIFICATION_BODY_MAX_CHARS = 8192

ISSUE_TERMINAL_STATUSES = ("closed", "canceled")
DUE_DATE_FILTERS = ("any", "no due date", "today", "within 5 days", "within 30 days")
AUTO_REFRESH_OPTIONS = ("never", "5 minutes", "10 minutes", "20 minutes", "30 minutes")
AUTO_REFRESH_SECONDS = {
    "5 minutes": 5 * 60,
    "10 minutes": 10 * 60,
    "20 minutes": 20 * 60,
    "30 minutes": 30 * 60,
}
ISSUES_PER_PAGE = 25
SEARCH_HISTORY_LIMIT = 10

SITE_CONFIG_KEYS = {
    "DB_FILE",
    "DEFAULT_CLOSING_COMMENT",
    "MAX_UPLOAD_BYTES",
    "ASSIGNEE_GROUP",
    "ASSIGNEE_EXCLUDE",
    "PER_USER_CONFIG_DIR",
    "MAX_FILENAME_LEN",
    "ADMINS_GROUP",
    "ADMINS_GROUP_EXCLUDE",
    "BANNER_FILE",
    "BANNER_DIMENSIONS",
    "EMAIL_NOTIFICATIONS_ENABLED",
    "SENDMAIL_PATH",
    "NOTIFICATION_FROM",
    "NOTIFICATION_SUBJECT_PREFIX",
    "ISSUE_BASE_URL",
    "NOTIFICATION_TRIAGE_RECIPIENTS",
    "NOTIFICATION_BODY_MAX_CHARS",
}
SITE_CONFIG_INTEGER_KEYS = {"MAX_UPLOAD_BYTES", "MAX_FILENAME_LEN", "NOTIFICATION_BODY_MAX_CHARS"}
SITE_CONFIG_BOOLEAN_KEYS = {"EMAIL_NOTIFICATIONS_ENABLED"}
SITE_CONFIG_REQUIRED_STRING_KEYS = {
    "DB_FILE",
    "DEFAULT_CLOSING_COMMENT",
    "ASSIGNEE_GROUP",
    "PER_USER_CONFIG_DIR",
    "ADMINS_GROUP",
    "SENDMAIL_PATH",
    "NOTIFICATION_FROM",
    "NOTIFICATION_SUBJECT_PREFIX",
    "NOTIFICATION_TRIAGE_RECIPIENTS",
}


def _valid_banner_dimensions(value: str) -> bool:
    value = value.strip()
    return value == "" or re.fullmatch(r"[1-9][0-9]*x[1-9][0-9]*", value) is not None


def _parse_site_config_bool(value: str) -> Optional[bool]:
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    return None


def _valid_sendmail_path(value: str) -> bool:
    return bool(value.strip()) and value.strip().startswith("/")


def _strip_site_config_comment(line: str) -> str:
    return line.split("#", 1)[0].strip()


def load_site_config(path: str = SITE_CONFIG_FILE) -> None:
    """Load optional site configuration from a simple KEY=value file."""
    try:
        lines = Path(path).read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return
    except OSError:
        return

    for raw_line in lines:
        line = _strip_site_config_comment(raw_line)
        if not line or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if key not in SITE_CONFIG_KEYS:
            continue
        if key in SITE_CONFIG_BOOLEAN_KEYS:
            parsed_bool = _parse_site_config_bool(value)
            if parsed_bool is None:
                continue
            globals()[key] = parsed_bool
            continue
        if key in SITE_CONFIG_INTEGER_KEYS:
            try:
                parsed = int(value)
            except ValueError:
                continue
            if parsed <= 0:
                continue
            globals()[key] = parsed
            continue
        if key == "BANNER_DIMENSIONS" and not _valid_banner_dimensions(value):
            continue
        if key == "SENDMAIL_PATH" and not _valid_sendmail_path(value):
            continue
        if key in SITE_CONFIG_REQUIRED_STRING_KEYS and not value:
            continue
        globals()[key] = value


load_site_config()

# ---------------------------------------------------------------------------
# Optional Markdown support
# ---------------------------------------------------------------------------

try:
    import markdown as _markdown  # type: ignore
except Exception:  # pragma: no cover - depends on deployment environment
    _markdown = None

MARKDOWN_EXTENSIONS = ["fenced_code", "tables", "attr_list", "footnotes"]


# ---------------------------------------------------------------------------
# CGI response helpers
# ---------------------------------------------------------------------------

class ResponseSent(Exception):
    """Raised after a response has been written."""


class AppError(Exception):
    def __init__(self, message: str, status: str = "400 Bad Request") -> None:
        super().__init__(message)
        self.message = message
        self.status = status


def send_headers(content_type: str = "text/html; charset=utf-8", status: Optional[str] = None,
                 extra_headers: Iterable[tuple[str, str]] = ()) -> None:
    if status:
        print(f"Status: {status}")
    print(f"Content-Type: {content_type}")
    print("X-Content-Type-Options: nosniff")
    for name, value in extra_headers:
        print(f"{name}: {value}")
    print()


def redirect(location: str, status: str = "303 See Other") -> None:
    print(f"Status: {status}")
    print(f"Location: {location}")
    print("Content-Type: text/plain; charset=utf-8")
    print()
    print(f"Redirecting to {location}")
    raise ResponseSent()


def plain_error(message: str, status: str = "400 Bad Request") -> None:
    send_headers("text/plain; charset=utf-8", status)
    print(message)
    raise ResponseSent()


def html_error(message: str, status: str = "400 Bad Request", title: str = "Error") -> None:
    send_headers(status=status)
    print(render_page(title, f"<p class='error'>{h(message)}</p>"))
    raise ResponseSent()


def h(value: Any) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def parse_banner_dimensions() -> tuple[str, str]:
    match = re.fullmatch(r"\s*(\d+)x(\d+)\s*", str(BANNER_DIMENSIONS))
    if not match:
        return "", ""
    return match.group(1), match.group(2)


def render_page(title: str, body: str, current_user: Optional[str] = None, browser_title: Optional[str] = None) -> str:
    width, height = parse_banner_dimensions()
    if BANNER_FILE:
        dimension_attrs = ""
        if width and height:
            dimension_attrs = f' width="{h(width)}" height="{h(height)}"'
        banner_html = f'<img class="banner" src="{h(BANNER_FILE)}"{dimension_attrs} alt="Banner">'
    else:
        banner_html = '<div class="css-header"><div class="css-header-title">Issues</div></div>'
    user_value = (current_user or "").strip()
    if user_value:
        user_block = (
            f'<div class="current-user">Welcome, <strong>{h(display_username(user_value))}</strong> '
            f'<span class="logout-wrapper">(<a class="logout-link" href="{h(LOGOUT_URL)}">Logout</a>)</span></div>'
        )
    else:
        user_block = ""
    version_value = ISSUES_VERSION.strip()
    # REQUIREMENTS: Version text is intentionally omitted from unauthenticated
    # public pages even when ISSUES_VERSION is configured.
    footer_html = (
        f'<footer class="app-footer">Issues {h(version_value)}</footer>'
        if version_value and user_value else ""
    )
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>{h(browser_title or title)}</title>
<link rel="icon" href="issues.cgi?action=favicon" type="image/x-icon">
<style>
body {{ font-family: Arial, sans-serif; margin: 1.5rem; line-height: 1.4; }}
.banner {{ display: block; margin-bottom: 1rem; }}
.css-header {{ position: relative; height: 35px; margin: -0.75rem -0.75rem 1rem -0.75rem; background: linear-gradient(90deg, #E6E9EF 0%, rgba(230, 233, 239, 0) 100%); }}
.css-header-title {{ position: relative; z-index: 1; height: 35px; display: flex; align-items: center; padding-left: 1rem; font-size: 1.1rem; font-weight: bold; color: #BFC5D0; }}
.header {{ display: flex; align-items: baseline; justify-content: space-between; gap: 1rem; margin-bottom: 1rem; }}
.header h1 {{ margin: 0; font-size: 2rem; line-height: 1.2; }}
h2, .section-heading {{ margin: 1.25rem 0 0.6rem; font-size: 1.35rem; line-height: 1.25; }}
h3 {{ margin: 1rem 0 0.45rem; font-size: 1.05rem; line-height: 1.3; }}
.metadata-text, .comment-meta, .current-user, .notice, .last-refreshed {{ color: #555; }}
.comment-meta {{ margin: 1rem 0 0.35rem; font-size: 0.9rem; line-height: 1.35; font-weight: 600; }}
.current-user {{ color: #555; text-align: right; white-space: nowrap; }}
.current-user strong {{ font-weight: bold; color: #333; }}
.logout-wrapper {{ margin-left: 0.4em; }}
.logout-link {{ text-decoration: underline; }}
.app-footer {{ margin-top: 1.5rem; text-align: center; color: #777; font-size: 0.85rem; }}
table {{ border-collapse: collapse; width: 100%; margin: 1rem 0; }}
th, td {{ border: 1px solid #ccc; padding: 0.4rem 0.55rem; vertical-align: top; }}
th {{ background: #eee; text-align: left; }}
form.inline {{ display: inline-flex; align-items: center; gap: 0.4rem; margin: 0; }}
button, input, select, textarea {{ font: inherit; }}
input[type=text], input[type=date], input[type=number], textarea, select {{ max-width: 100%; }}
textarea {{ width: 100%; min-height: 12rem; }}
.actions {{ display: flex; align-items: center; gap: 0.65rem; flex-wrap: wrap; margin: 0.5rem 0 1rem; }}
.actions form {{ margin: 0; }}
.static-filters, .dynamic-filters {{ margin: 0.5rem 0; }}
.static-filters label, .dynamic-filters label {{ margin-right: 0; }}
.static-filter-row {{ display: flex; align-items: center; justify-content: space-between; gap: 1em; flex-wrap: wrap; }}
.static-filter-left {{ display: flex; align-items: center; gap: 0.75em; flex-wrap: wrap; }}
.static-filter-left label {{ margin-right: 0; }}
.static-filter-search {{ margin-left: auto; white-space: nowrap; }}
.search-box-with-history {{ position: relative; display: inline-block; }}
.search-box-with-history input[type=search] {{ width: clamp(12em, 28vw, 32em); max-width: 100%; padding-left: 2rem; }}
.search-history-toggle {{ position: absolute; left: 0.3rem; top: 50%; transform: translateY(-50%); z-index: 2; border: 0; background: transparent; color: #555; padding: 0.1rem 0.25rem; line-height: 1; }}
.search-history-pane {{ position: absolute; top: calc(100% + 0.25rem); left: 0; right: 0; z-index: 5; min-width: 16rem; max-height: 18rem; overflow-y: auto; background: #fff; border: 1px solid #bbb; box-shadow: 0 0.25rem 0.75rem rgba(0,0,0,0.16); white-space: normal; }}
.search-history-pane ul {{ list-style: none; margin: 0; padding: 0.25rem 0; }}
.search-history-pane li {{ display: flex; align-items: stretch; justify-content: space-between; gap: 0.35rem; margin: 0; padding: 0.15rem 0.25rem; }}
.search-history-term {{ flex: 1 1 auto; align-self: stretch; overflow-wrap: anywhere; border: 0; background: transparent; padding: 0.25rem 0.35rem; text-align: left; color: #222; font: inherit; border-radius: 2px; }}
.search-history-term:hover, .search-history-term:focus {{ background: #f4f4f4; }}
.search-history-delete {{ flex: 0 0 auto; border: 0; background: transparent; color: #333; padding: 0.15rem 0.35rem; text-decoration: none; font: inherit; font-size: 1.05rem; line-height: 1; }}
.search-history-empty {{ margin: 0; padding: 0.5rem; color: #666; }}
.search-history-clear {{ border-top: 1px solid #ddd; padding: 0.4rem; text-align: center; }}
.search-history-clear button {{ border: 1px solid #bbb; background: #f7f7f7; color: #333; padding: 0.2rem 0.55rem; }}
.dual-listbox {{ display: flex; align-items: center; gap: 0.75rem; flex-wrap: wrap; margin: 0.4rem 0; }}
.dual-listbox-column {{ display: flex; flex-direction: column; gap: 0.25rem; }}
.dual-listbox-column select {{ min-width: 12rem; width: clamp(12rem, 22vw, 18rem); }}
.dual-listbox-actions {{ display: flex; flex-direction: column; gap: 0.35rem; }}
.dual-listbox-actions button {{ min-width: 2.25rem; }}
.dynamic-filters {{ display: flex; align-items: center; gap: 0.75em; flex-wrap: wrap; padding-top: 0.5rem; border-top: 1px solid #ddd; }}
.pagination-controls {{ display: inline-flex !important; align-items: center; justify-content: flex-end; margin: 0; white-space: nowrap; }}
.pagination-controls form {{ display: inline-flex !important; align-items: center; gap: 0.4rem; margin: 0; white-space: nowrap; }}
.pagination-controls select {{ margin: 0; }}
.auto-refresh-control {{ display: inline-flex !important; align-items: center; justify-content: flex-start; margin: 0; white-space: nowrap; }}
.auto-refresh-control form {{ display: inline-flex !important; align-items: center; margin: 0; white-space: nowrap; }}
.last-refreshed {{ margin-left: 0.5rem; color: #555; font-size: 0.9em; }}
/* REGRESSION GUARD: Use float-based list control rows instead of flex/grid.
   Some deployments rendered the nested pagination form on a separate line or
   aligned it left despite flex/grid declarations. Floats provide a conservative
   two-column layout for the left action and right pagination controls. */
.list-control-row {{ overflow: hidden; margin: 0.5rem 0; width: 100%; }}
.list-control-left {{ float: left; }}
.list-control-right {{ float: right; text-align: right; white-space: nowrap; }}
.list-control-right .pagination-controls {{ justify-content: flex-end; }}
.issue-list-table, .issue-history-table, .issue-metadata-table {{ clear: both; margin: 0.5rem 0; font-size: 0.9rem; }}
.error {{ color: #900; font-weight: bold; }}
.notice {{ color: #555; }}
.section {{ margin-top: 1.5rem; }}
.markdown-body {{ border: 1px solid #ddd; padding: 0.75rem; background: #fafafa; }}
.markdown-body > :first-child {{ margin-top: 0; }}
.markdown-body > :last-child {{ margin-bottom: 0; }}
.markdown-body h1 {{ margin: 0.4rem 0 0.5rem; font-size: 1.35rem; line-height: 1.25; }}
.markdown-body h2 {{ margin: 0.9rem 0 0.45rem; font-size: 1.2rem; line-height: 1.25; }}
.markdown-body h3 {{ margin: 0.8rem 0 0.4rem; font-size: 1.05rem; line-height: 1.3; }}
.markdown-body p, .markdown-body ul, .markdown-body ol, .markdown-body table {{ margin: 0.6rem 0; }}
.markdown-body code {{ font-family: Menlo, Consolas, monospace; font-size: 0.95em; }}
pre {{ overflow-x: auto; background: #f3f3f3; padding: 0.5rem; }}
.form-actions {{ display: flex; align-items: center; gap: 0.6rem; flex-wrap: wrap; }}
.form-actions input[type=submit], .form-actions button, .form-actions .button-link {{ box-sizing: border-box; display: inline-flex; align-items: center; justify-content: center; min-height: 1.65rem; border: 1px solid #999; border-radius: 2px; padding: 0.15rem 0.55rem; background: #f4f4f4; color: #111; font-size: 0.85rem; font-weight: 400; text-decoration: none; line-height: 1.2; }}
button, input[type=submit] {{ cursor: pointer; }}
</style>
<script>
(function() {{
    function part(parts, type) {{
        for (var i = 0; i < parts.length; i += 1) {{
            if (parts[i].type === type) {{
                return parts[i].value;
            }}
        }}
        return "";
    }}
    function renderLocalTimestamps() {{
        if (!window.Intl || !Intl.DateTimeFormat) {{
            return;
        }}
        var nodes = document.getElementsByClassName("local-timestamp");
        var formatter = new Intl.DateTimeFormat(undefined, {{
            year: "numeric",
            month: "2-digit",
            day: "2-digit",
            hour: "2-digit",
            minute: "2-digit",
            second: "2-digit",
            hour12: false,
            timeZoneName: "short"
        }});
        for (var i = 0; i < nodes.length; i += 1) {{
            var utc = nodes[i].getAttribute("data-utc");
            var date = new Date(utc);
            if (!utc || isNaN(date.getTime())) {{
                continue;
            }}
            var parts = formatter.formatToParts(date);
            var rendered = (
                part(parts, "year") + "-" +
                part(parts, "month") + "-" +
                part(parts, "day") + " " +
                part(parts, "hour") + ":" +
                part(parts, "minute") + ":" +
                part(parts, "second")
            );
            var zone = part(parts, "timeZoneName");
            if (zone) {{
                rendered += " " + zone;
            }}
            nodes[i].textContent = rendered;
        }}
    }}
    function renderRelativeRefreshTimes() {{
        var nodes = document.getElementsByClassName("last-refreshed");
        for (var i = 0; i < nodes.length; i += 1) {{
            var utc = nodes[i].getAttribute("data-refreshed-at-utc");
            var date = new Date(utc);
            if (!utc || isNaN(date.getTime())) {{
                continue;
            }}
            var elapsedMs = (new Date()).getTime() - date.getTime();
            var minutes = Math.floor(Math.max(0, elapsedMs) / 60000);
            var label = "just now";
            if (minutes === 1) {{
                label = "1 minute ago";
            }} else if (minutes > 1) {{
                label = minutes + " minutes ago";
            }}
            nodes[i].textContent = "(Last refreshed: " + label + ")";
        }}
    }}
    function renderDynamicTimes() {{
        renderLocalTimestamps();
        renderRelativeRefreshTimes();
    }}
    window.toggleSearchHistory = function(button) {{
        var wrapper = button && button.parentNode;
        var pane = wrapper && wrapper.getElementsByClassName("search-history-pane")[0];
        if (!pane) {{
            return;
        }}
        var panes = document.getElementsByClassName("search-history-pane");
        for (var i = 0; i < panes.length; i += 1) {{
            if (panes[i] !== pane) {{
                panes[i].hidden = true;
            }}
        }}
        pane.hidden = !pane.hidden;
    }};
    window.applySearchHistoryTerm = function(button, term) {{
        var form = button && button.form;
        if (!form) {{
            return;
        }}
        var search = form.elements["search"];
        if (search) {{
            search.value = term;
        }}
        form.submit();
    }};
    window.goToSearchHistoryUrl = function(url) {{
        window.location.href = url;
    }};
    function hasClass(node, className) {{
        if (!node || !node.className) {{
            return false;
        }}
        return (" " + String(node.className) + " ").indexOf(" " + className + " ") >= 0;
    }}
    window.moveDualListOptions = function(button, direction) {{
        var root = button;
        while (root && !hasClass(root, "dual-listbox")) {{
            root = root.parentNode;
        }}
        if (!root) {{
            return;
        }}
        var available = root.getElementsByClassName("dual-listbox-available")[0];
        var selected = root.getElementsByClassName("dual-listbox-selected")[0];
        var source = direction === "right" ? available : selected;
        var target = direction === "right" ? selected : available;
        if (!source || !target) {{
            return;
        }}
        var moving = [];
        for (var i = 0; i < source.options.length; i += 1) {{
            if (source.options[i].selected) {{
                moving.push(source.options[i]);
            }}
        }}
        for (var j = 0; j < moving.length; j += 1) {{
            moving[j].selected = false;
            target.appendChild(moving[j]);
        }}
        sortSelectOptions(target);
    }};
    function optionNode(value, labels) {{
        var option = document.createElement("option");
        option.value = value;
        option.text = (labels && labels[value]) || value;
        return option;
    }}
    function optionValues(select) {{
        var values = [];
        if (!select) {{
            return values;
        }}
        for (var i = 0; i < select.options.length; i += 1) {{
            values.push(select.options[i].value);
        }}
        return values;
    }}
    function dualListLabels(select) {{
        var root = select;
        while (root && !hasClass(root, "dual-listbox")) {{
            root = root.parentNode;
        }}
        if (!root) {{
            return {{}};
        }}
        try {{
            return JSON.parse(root.getAttribute("data-user-labels") || "{{}}");
        }} catch (err) {{
            return {{}};
        }}
    }}
    function replaceOptions(select, values) {{
        var labels = dualListLabels(select);
        while (select.options.length) {{
            select.remove(0);
        }}
        for (var i = 0; i < values.length; i += 1) {{
            select.add(optionNode(values[i], labels));
        }}
    }}
    function sortSelectOptions(select) {{
        var labels = dualListLabels(select);
        replaceOptions(select, optionValues(select).sort(function(left, right) {{
            return ((labels[left] || left).localeCompare((labels[right] || right), undefined, {{sensitivity: "base"}}));
        }}));
    }}
    window.syncDualListExclusions = function(root, extraExcluded) {{
        if (!root) {{
            return;
        }}
        var allUsers = [];
        var baseExcluded = [];
        try {{
            allUsers = JSON.parse(root.getAttribute("data-all-users") || "[]");
            baseExcluded = JSON.parse(root.getAttribute("data-base-excluded") || "[]");
        }} catch (err) {{
            return;
        }}
        var excluded = {{}};
        for (var i = 0; i < baseExcluded.length; i += 1) {{
            excluded[baseExcluded[i]] = true;
        }}
        for (var j = 0; j < (extraExcluded || []).length; j += 1) {{
            if (extraExcluded[j]) {{
                excluded[extraExcluded[j]] = true;
            }}
        }}
        var available = root.getElementsByClassName("dual-listbox-available")[0];
        var selected = root.getElementsByClassName("dual-listbox-selected")[0];
        var selectedValues = optionValues(selected).filter(function(value, index, values) {{
            return !excluded[value] && values.indexOf(value) === index;
        }});
        var selectedMap = {{}};
        for (var k = 0; k < selectedValues.length; k += 1) {{
            selectedMap[selectedValues[k]] = true;
        }}
        var availableValues = allUsers.filter(function(value) {{
            return !excluded[value] && !selectedMap[value];
        }});
        replaceOptions(available, availableValues);
        replaceOptions(selected, selectedValues);
    }};
    window.syncContributingUsersWithAssignee = function(select) {{
        var form = select && select.form;
        var root = form && form.getElementsByClassName("contributing-users-dual-list")[0];
        window.syncDualListExclusions(root, [select.value]);
    }};
    window.prepareDualListSubmit = function(form) {{
        var selectedLists = form.getElementsByClassName("dual-listbox-selected");
        for (var i = 0; i < selectedLists.length; i += 1) {{
            for (var j = 0; j < selectedLists[i].options.length; j += 1) {{
                selectedLists[i].options[j].selected = true;
            }}
        }}
        return true;
    }};
    function installSearchHistoryDismissal() {{
        if (!document.addEventListener) {{
            return;
        }}
        document.addEventListener("click", function(event) {{
            var target = event.target;
            while (target) {{
                if (target.className && String(target.className).indexOf("search-box-with-history") >= 0) {{
                    return;
                }}
                target = target.parentNode;
            }}
            var panes = document.getElementsByClassName("search-history-pane");
            for (var i = 0; i < panes.length; i += 1) {{
                panes[i].hidden = true;
            }}
        }});
    }}
    if (document.addEventListener) {{
        document.addEventListener("DOMContentLoaded", function() {{
            installSearchHistoryDismissal();
            renderDynamicTimes();
            window.setInterval(renderRelativeRefreshTimes, 60000);
        }});
    }} else {{
        window.attachEvent && window.attachEvent("onload", function() {{
            renderDynamicTimes();
            window.setInterval(renderRelativeRefreshTimes, 60000);
        }});
    }}
}}());
</script>
</head>
<body>
{banner_html}
<div class="header"><h1>{h(title)}</h1>{user_block}</div>
{body}
{footer_html}
</body>
</html>"""


def apply_strikethrough_markup(escaped_text: str) -> str:
    # REQUIREMENTS: Support GitLab-style strikethrough while preserving the
    # existing escape-before-render behavior so unsafe HTML inside ~~...~~
    # remains text, not executable markup.
    return re.sub(r"~~([^~\n]+)~~", r"<del>\1</del>", escaped_text)


def fallback_inline_markdown(text: str) -> str:
    escaped = html.escape(text or "", quote=False)
    escaped = re.sub(r"`([^`]+)`", r"<code>\1</code>", escaped)
    escaped = re.sub(r"\*\*([^*\n]+)\*\*", r"<strong>\1</strong>", escaped)
    escaped = re.sub(r"(?<!\*)\*([^*\n]+)\*(?!\*)", r"<em>\1</em>", escaped)
    escaped = apply_strikethrough_markup(escaped)
    return escaped


def fallback_markdown_to_html(text: str) -> str:
    # REGRESSION GUARD: When the optional markdown package is unavailable,
    # keep supported block-list syntax as real lists instead of paragraph text
    # with <br> line breaks. The Markdown help page relies on this to prove
    # unordered and ordered examples render as separate list blocks.
    lines = (text or "").splitlines()
    blocks = []
    paragraph = []
    i = 0

    def flush_paragraph() -> None:
        if paragraph:
            blocks.append("<p>" + "<br>\n".join(fallback_inline_markdown(line) for line in paragraph) + "</p>")
            paragraph.clear()

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        if not stripped:
            flush_paragraph()
            i += 1
            continue

        if stripped.startswith("```"):
            flush_paragraph()
            code_lines = []
            i += 1
            while i < len(lines) and not lines[i].strip().startswith("```"):
                code_lines.append(lines[i])
                i += 1
            if i < len(lines):
                i += 1
            blocks.append("<pre><code>" + html.escape("\n".join(code_lines), quote=False) + "</code></pre>")
            continue

        heading_match = re.match(r"^(#{1,6})\s+(.+)$", stripped)
        if heading_match:
            flush_paragraph()
            level = len(heading_match.group(1))
            blocks.append(f"<h{level}>" + fallback_inline_markdown(heading_match.group(2)) + f"</h{level}>")
            i += 1
            continue

        unordered_match = re.match(r"^[-*+]\s+(.+)$", stripped)
        if unordered_match:
            flush_paragraph()
            items = []
            while i < len(lines):
                match = re.match(r"^[-*+]\s+(.+)$", lines[i].strip())
                if not match:
                    break
                items.append("<li>" + fallback_inline_markdown(match.group(1)) + "</li>")
                i += 1
            blocks.append("<ul>\n" + "\n".join(items) + "\n</ul>")
            continue

        ordered_match = re.match(r"^\d+[.)]\s+(.+)$", stripped)
        if ordered_match:
            flush_paragraph()
            items = []
            while i < len(lines):
                match = re.match(r"^\d+[.)]\s+(.+)$", lines[i].strip())
                if not match:
                    break
                items.append("<li>" + fallback_inline_markdown(match.group(1)) + "</li>")
                i += 1
            blocks.append("<ol>\n" + "\n".join(items) + "\n</ol>")
            continue

        paragraph.append(line)
        i += 1

    flush_paragraph()
    return "\n".join(blocks)


def markdown_to_html(text: str) -> str:
    safe_text = html.escape(text or "", quote=False)
    safe_text = apply_strikethrough_markup(safe_text)
    if _markdown is not None:
        return _markdown.markdown(safe_text, extensions=MARKDOWN_EXTENSIONS)
    return fallback_markdown_to_html(text or "")


# ---------------------------------------------------------------------------
# Request helpers
# ---------------------------------------------------------------------------

def method() -> str:
    return os.environ.get("REQUEST_METHOD", "GET").upper()


def field_value(form: cgi.FieldStorage, name: str, default: str = "") -> str:
    item = form.getfirst(name, default)
    if item is None:
        return default
    return str(item)


def optional_str(value: str) -> Optional[str]:
    value = (value or "").strip()
    return value if value else None


def require_id(form: cgi.FieldStorage, name: str = "id") -> int:
    raw = field_value(form, name).strip()
    if not raw.isdigit():
        raise AppError(f"Missing or invalid {name}", "400 Bad Request")
    return int(raw)


def action_url(action: str, **params: Any) -> str:
    data = {"action": action}
    data.update({k: v for k, v in params.items() if v is not None})
    return "issues.cgi?" + urlencode(data)


def safe_return_url(value: str, fallback: str) -> str:
    raw = (value or "").strip()
    if not raw:
        return fallback
    parsed = urlsplit(raw)
    if "\r" in raw or "\n" in raw or raw.lower().startswith("//"):
        return fallback
    if parsed.scheme or parsed.netloc:
        allowed_hosts = {
            os.environ.get("HTTP_HOST", "").strip(),
            os.environ.get("SERVER_NAME", "").strip(),
        }
        allowed_hosts.discard("")
        if parsed.netloc not in allowed_hosts:
            return fallback
        raw = parsed.path or fallback
        if parsed.query:
            raw += f"?{parsed.query}"
    return raw or fallback


def previous_page_url(form: cgi.FieldStorage, fallback: str) -> str:
    # REGRESSION GUARD: Cancel controls use prior-page destinations supplied by
    # the browser or a hidden field, but keep them same-site to avoid turning a
    # simple cancel link into an open redirect.
    submitted = field_value(form, "return_to", "").strip()
    referer = os.environ.get("HTTP_REFERER", "").strip()
    return safe_return_url(submitted or referer, fallback)


def hidden_return_to(return_to: str) -> str:
    return f'<input type="hidden" name="return_to" value="{h(return_to)}">'


def cancel_control(return_to: str) -> str:
    return f'<a class="button-link cancel-button" href="{h(return_to)}">Cancel</a>'


def current_request_destination() -> str:
    request_uri = os.environ.get("REQUEST_URI", "").strip()
    if request_uri:
        return safe_auth_destination(request_uri)
    script_name = os.environ.get("SCRIPT_NAME", "").strip() or AUTH_FORM_DEFAULT_LOCATION
    query_string = os.environ.get("QUERY_STRING", "").strip()
    return safe_auth_destination(script_name + (f"?{query_string}" if query_string else ""))


# ---------------------------------------------------------------------------
# System user and group helpers
# ---------------------------------------------------------------------------

def split_csv_names(value: str) -> set[str]:
    return {item.strip() for item in (value or "").split(",") if item.strip()}


def user_exists(username: str) -> bool:
    if not username:
        return False
    try:
        pwd.getpwnam(username)
        return True
    except KeyError:
        return False


def display_username(username: Any) -> str:
    login = "" if username is None else str(username).strip()
    if not login:
        return ""
    try:
        gecos = str(getattr(pwd.getpwnam(login), "pw_gecos", "") or "")
    except KeyError:
        return login
    full_name = gecos.split(",", 1)[0].strip()
    if not full_name or not re.search(r"\s", full_name):
        return login
    return full_name


def display_usernames(usernames: Iterable[str]) -> str:
    names = [display_username(username) for username in usernames if username]
    return ", ".join(name for name in names if name)


def get_current_user() -> str:
    username = os.environ.get("REMOTE_USER", "").strip()
    if not username or not user_exists(username):
        plain_error("Anonymous or invalid user is not allowed", "403 Forbidden")
    return username


def user_in_group(username: str, group_name: str) -> bool:
    if not username or not group_name or not user_exists(username):
        return False
    try:
        user = pwd.getpwnam(username)
        target_group = grp.getgrnam(group_name)
    except KeyError:
        return False
    try:
        group_ids = os.getgrouplist(username, user.pw_gid)
    except Exception:
        group_ids = [user.pw_gid]
    return target_group.gr_gid in group_ids


def get_group_members(group_name: str) -> set[str]:
    """Return explicitly listed NSS members of a group.

    REGRESSION GUARD: The assignable-user dropdown must not be polluted by
    users whose primary gid happens to match a local group such as games. Direct
    validation of a submitted assignee still uses user_in_group(), which checks
    complete group membership for the specific submitted username.
    """
    if not group_name:
        return set()
    try:
        group = grp.getgrnam(group_name)
    except KeyError:
        return set()
    return {name for name in group.gr_mem if user_exists(name)}


def is_admin(username: str) -> bool:
    if username in split_csv_names(ADMINS_GROUP_EXCLUDE):
        return False
    return user_in_group(username, ADMINS_GROUP)


def get_assignable_users() -> list[str]:
    excluded = split_csv_names(ASSIGNEE_EXCLUDE)
    return sorted(
        username for username in get_group_members(ASSIGNEE_GROUP)
        if username not in excluded and user_exists(username)
    )


def get_contributing_candidate_users(exclude: Iterable[str] = ()) -> list[str]:
    excluded = {username for username in exclude if username}
    return [username for username in get_assignable_users() if username not in excluded]


def valid_assignee(username: str) -> bool:
    if not username:
        return True
    if username in split_csv_names(ASSIGNEE_EXCLUDE):
        return False
    return user_exists(username) and user_in_group(username, ASSIGNEE_GROUP)


def parse_contributing_usernames(value: str) -> list[str]:
    usernames: list[str] = []
    for username in re.split(r"[\s,]+", value or ""):
        username = username.strip()
        if username and username not in usernames:
            usernames.append(username)
    return usernames


def contributing_user_values(form: cgi.FieldStorage, field_name: str) -> list[str]:
    if field_name not in form:
        return []
    value = form[field_name]
    if isinstance(value, list):
        raw_values = [str(getattr(item, "value", item)) for item in value]
    else:
        raw_values = [str(getattr(value, "value", value))]
    usernames: list[str] = []
    for raw_value in raw_values:
        for username in parse_contributing_usernames(raw_value):
            if username not in usernames:
                usernames.append(username)
    return usernames


def validate_contributing_usernames(usernames: Iterable[str]) -> list[str]:
    valid: list[str] = []
    contributing_candidates = set(get_contributing_candidate_users())
    for username in usernames:
        if username not in contributing_candidates:
            raise AppError(f"Contributing user does not exist or is not contributing candidate: {username}")
        if username not in valid:
            valid.append(username)
    return valid


def validate_contributing_usernames_for_issue_roles(usernames: Iterable[str], excluded_roles: Iterable[str]) -> list[str]:
    excluded = {username for username in excluded_roles if username}
    valid = validate_contributing_usernames(usernames)
    for username in valid:
        if username in excluded:
            raise AppError(f"Contributing user cannot be the issue creator or assigned user: {username}")
    return valid


# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------

def db_connect() -> sqlite3.Connection:
    if not os.path.exists(DB_FILE):
        plain_error(f"Database not found: {DB_FILE}", "500 Internal Server Error")
    con = sqlite3.connect(DB_FILE)
    con.row_factory = sqlite3.Row
    return con


def fetch_issue(con: sqlite3.Connection, issue_id: int) -> Optional[sqlite3.Row]:
    return con.execute("SELECT * FROM issues WHERE id = ?", (issue_id,)).fetchone()


def fetch_contributing_usernames(con: sqlite3.Connection, issue_id: int) -> list[str]:
    return [
        row["contributing_username"]
        for row in con.execute(
            "SELECT contributing_username FROM issue_contributing_users WHERE issue_id = ? ORDER BY contributing_username",
            (issue_id,),
        ).fetchall()
    ]


def is_contributing_user(con: sqlite3.Connection, issue_id: int, username: str) -> bool:
    if not username:
        return False
    row = con.execute(
        "SELECT 1 FROM issue_contributing_users WHERE issue_id = ? AND contributing_username = ?",
        (issue_id, username),
    ).fetchone()
    return row is not None


def can_view_issue(issue: sqlite3.Row, username: str, con: Optional[sqlite3.Connection] = None) -> bool:
    if is_admin(username) or issue["creator_username"] == username or issue["assigned_username"] == username:
        return True
    return con is not None and is_contributing_user(con, int(issue["id"]), username)


def can_owner_or_admin(issue: sqlite3.Row, username: str) -> bool:
    return is_admin(username) or issue["creator_username"] == username


def can_owner_assigned_contributing_or_admin(issue: sqlite3.Row, username: str, con: sqlite3.Connection) -> bool:
    return can_view_issue(issue, username, con)


def can_owner_assigned_or_admin(issue: sqlite3.Row, username: str) -> bool:
    return is_admin(username) or issue["creator_username"] == username or issue["assigned_username"] == username


def can_manage_contributing_users(issue: sqlite3.Row, username: str) -> bool:
    return is_admin(username) or issue["creator_username"] == username or issue["assigned_username"] == username


def require_issue_access(con: sqlite3.Connection, issue_id: int, username: str) -> sqlite3.Row:
    issue = fetch_issue(con, issue_id)
    if issue is None:
        raise AppError("Issue not found", "404 Not Found")
    if not can_view_issue(issue, username, con):
        raise AppError("You are not authorized to view this issue", "403 Forbidden")
    return issue


def now_utc_sql() -> str:
    return _dt.datetime.now(_dt.timezone.utc).replace(microsecond=0).isoformat(sep=" ")


def timestamp_utc_datetime(value: Any) -> Optional[_dt.datetime]:
    text = "" if value is None else str(value).strip()
    if not text:
        return None
    if text.endswith(" UTC"):
        normalized = text[:-4] + "+00:00"
    elif text.endswith("Z"):
        normalized = text[:-1] + "+00:00"
    else:
        normalized = text
    try:
        dt = _dt.datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=_dt.timezone.utc)
    return dt.astimezone(_dt.timezone.utc).replace(microsecond=0)


def format_timestamp(value: Any) -> str:
    text = "" if value is None else str(value).strip()
    if not text:
        return ""
    dt = timestamp_utc_datetime(value)
    if dt is None:
        return text
    return dt.strftime("%Y-%m-%d %H:%M:%S UTC")


def timestamp_html(value: Any) -> str:
    dt = timestamp_utc_datetime(value)
    if dt is None:
        return h(format_timestamp(value))
    utc_value = dt.isoformat().replace("+00:00", "Z")
    # REGRESSION GUARD: Store and emit UTC timestamps, but render them in the
    # browser's local timezone with the browser-local timezone abbreviation.
    # The UTC fallback remains visible only when JavaScript is unavailable.
    return (
        f'<span class="local-timestamp" data-utc="{h(utc_value)}">'
        f'{h(format_timestamp(value))}</span>'
    )


def elapsed_time_worked(start_value: Any, end_value: Optional[Any] = None) -> str:
    start_dt = timestamp_utc_datetime(start_value)
    end_dt = timestamp_utc_datetime(end_value) if end_value is not None else _dt.datetime.now(_dt.timezone.utc).replace(microsecond=0)
    if start_dt is None or end_dt is None:
        return ""
    elapsed_minutes = max(0, int((end_dt - start_dt).total_seconds() // 60))
    return labeled_time_worked(elapsed_minutes)


TIME_WORKED_UNITS = {
    "m": Decimal("1"),
    "min": Decimal("1"),
    "mins": Decimal("1"),
    "minute": Decimal("1"),
    "minutes": Decimal("1"),
    "h": Decimal("60"),
    "hour": Decimal("60"),
    "hours": Decimal("60"),
    "d": Decimal("480"),
    "day": Decimal("480"),
    "days": Decimal("480"),
}


def parse_time_worked_minutes(value: str) -> Optional[int]:
    raw = value.strip()
    if not raw:
        return None
    match = re.fullmatch(r"([0-9]+(?:\.[0-9]{1,2})?)\s*([A-Za-z]+)?", raw)
    if not match:
        raise ValueError("Time worked must be a number with an optional m, h, or d time unit.")
    try:
        amount = Decimal(match.group(1))
    except InvalidOperation as exc:
        raise ValueError("Time worked must be a valid number.") from exc
    unit = (match.group(2) or "h").lower()
    if unit not in TIME_WORKED_UNITS:
        raise ValueError("Time worked uses an unsupported time unit.")
    minutes = amount * TIME_WORKED_UNITS[unit]
    rounded_minutes = int(minutes.to_integral_value(rounding=ROUND_HALF_UP))
    if rounded_minutes <= 0 or minutes >= 1440:
        raise ValueError("Time worked must be greater than 0 minutes and less than 24 hours.")
    return rounded_minutes


def labeled_time_worked(minutes_value: Any) -> str:
    try:
        minutes = max(0, int(minutes_value or 0))
    except (TypeError, ValueError):
        minutes = 0

    weeks, remainder = divmod(minutes, 2400)
    days, remainder = divmod(remainder, 480)
    hours, minutes_part = divmod(remainder, 60)

    if minutes < 60:
        parts = [("minute", minutes_part)]
    elif minutes < 480:
        parts = [("hour", hours), ("minute", minutes_part)]
    elif minutes < 2400:
        parts = [("day", days), ("hour", hours), ("minute", minutes_part)]
    else:
        parts = [("week", weeks), ("day", days), ("hour", hours), ("minute", minutes_part)]

    return ", ".join(f"{count} {label if count == 1 else label + 's'}" for label, count in parts)


def history_summary_text(value: Any, limit: int = 80) -> str:
    text = "" if value is None else str(value)
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 3)].rstrip() + "..."


def display_value(value: Any, blank_label: str = "unassigned") -> str:
    text = "" if value is None else str(value).strip()
    return text if text else blank_label


def description_change_summary(old_value: Any, new_value: Any) -> str:
    old_text = "" if old_value is None else str(old_value)
    new_text = "" if new_value is None else str(new_value)
    old_lines = len(old_text.splitlines()) if old_text else 0
    new_lines = len(new_text.splitlines()) if new_text else 0
    return (
        "Updated description: "
        f"{old_lines} lines -> {new_lines} lines, "
        f"{len(old_text)} -> {len(new_text)} characters"
    )


def issue_update_summary(issue: sqlite3.Row, new_title: str, description_supplied: bool, new_description: str) -> str:
    parts: list[str] = []
    old_title = str(issue["title"] or "")
    old_description = str(issue["description"] or "")
    if old_title != new_title:
        parts.append(history_change_summary("title", old_title, new_title))
    if description_supplied and old_description != new_description:
        parts.append(description_change_summary(old_description, new_description))
    if not parts:
        return "Updated issue"
    return "; ".join(parts)


def record_issue_history(
    con: sqlite3.Connection,
    issue_id: int,
    actor_username: str,
    action: str,
    summary: str,
    created_at: Optional[str] = None,
    *,
    comment_id: Optional[int] = None,
    attachment_id: Optional[int] = None,
) -> None:
    # REGRESSION GUARD: History entries are intentionally compact. Store row
    # references and concise summaries rather than full comments, attachment
    # content, full issue snapshots, or full text diffs.
    con.execute(
        """INSERT INTO issue_history
           (issue_id, actor_username, action, summary, comment_id, attachment_id, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (issue_id, actor_username, action, summary, comment_id, attachment_id, created_at or now_utc_sql()),
    )


def unique_notification_recipients(values: Iterable[Any], exclude: str = "") -> list[str]:
    recipients: list[str] = []
    excluded = (exclude or "").strip()
    for value in values:
        recipient = "" if value is None else str(value).strip()
        if not recipient or recipient == excluded or recipient in recipients:
            continue
        recipients.append(recipient)
    return recipients


def issue_participant_recipients(con: sqlite3.Connection, issue: sqlite3.Row, exclude: str = "") -> list[str]:
    return unique_notification_recipients(
        [issue["creator_username"], issue["assigned_username"]] + fetch_contributing_usernames(con, int(issue["id"])),
        exclude=exclude,
    )


def contributing_users_summary(usernames: Iterable[str], verb: str) -> str:
    names = sorted({name for name in usernames if name})
    if not names:
        return f"{verb} no contributing users"
    return f"{verb} contributing user{'s' if len(names) != 1 else ''}: {display_usernames(names)}"


def resolve_notification_triage_recipients(exclude: str = "") -> list[str]:
    # REQUIREMENTS: Triage recipients are local mail recipients and can be a
    # comma-separated mixture of names and @group references. Group references
    # are resolved through NSS-aware Python group lookup, not by reading
    # /etc/group directly.
    raw_items = [item.strip() for item in NOTIFICATION_TRIAGE_RECIPIENTS.split(",")]
    resolved: list[str] = []
    for item in raw_items:
        if not item:
            continue
        if item.startswith("@"):
            group_name = item[1:].strip()
            if not group_name:
                continue
            try:
                members = grp.getgrnam(group_name).gr_mem
            except KeyError:
                print(f"Notification triage group not found: {group_name}", file=sys.stderr)
                continue
            resolved.extend(members)
        else:
            resolved.append(item)
    return unique_notification_recipients(resolved, exclude=exclude)


def notification_body_text(value: Any) -> str:
    text = "" if value is None else str(value)
    max_chars = max(1, int(NOTIFICATION_BODY_MAX_CHARS))
    if len(text) <= max_chars:
        return text
    omitted = len(text) - max_chars
    return text[:max_chars] + f"\n\n[Notification content truncated; {omitted} characters omitted.]"


def issue_notification_url(issue_id: int) -> str:
    base = ISSUE_BASE_URL.strip()
    if not base:
        return ""
    separator = "&" if "?" in base else "?"
    return f"{base}{separator}{urlencode({'action': 'view', 'id': issue_id})}"


def issue_notification_subject(event: str, issue: sqlite3.Row) -> str:
    prefix = NOTIFICATION_SUBJECT_PREFIX.strip() or "[Issues]"
    title = history_summary_text(issue["title"], 80)
    return f"{prefix} {event}: Issue #{issue['id']} {title}"


def issue_notification_body(event: str, issue: sqlite3.Row, actor_username: str, details: str = "") -> str:
    lines = [
        f"Issue #{issue['id']}: {issue['title']}",
        f"Action: {event}",
        f"By: {display_username(actor_username)}",
        f"Status: {issue['status']}",
        f"Priority: {issue['priority']}",
    ]
    if issue["due_date"]:
        lines.append(f"Due: {issue['due_date']}")
    if details:
        lines.extend(["", details])
    link = issue_notification_url(int(issue["id"]))
    if link:
        lines.extend(["", "View issue:", link])
    return "\n".join(str(line) for line in lines) + "\n"


def submit_notification_email(recipients: list[str], subject: str, body: str) -> None:
    # REQUIREMENTS: Notification mail is handed to a local sendmail-compatible
    # command. The application does not connect directly to remote SMTP servers
    # and does not store SMTP credentials.
    msg = EmailMessage()
    msg["From"] = NOTIFICATION_FROM
    msg["To"] = ", ".join(recipients)
    msg["Subject"] = subject
    msg.set_content(body)
    subprocess.run([SENDMAIL_PATH, "-t", "-oi"], input=msg.as_bytes(), check=True)


def notify_issue_event(issue_id: int, actor_username: str, recipients: list[str], event: str, details: str = "") -> None:
    if not EMAIL_NOTIFICATIONS_ENABLED:
        return
    try:
        with db_connect() as con:
            issue = fetch_issue(con, issue_id)
        if issue is None:
            return
        if not recipients and not issue["assigned_username"]:
            recipients = resolve_notification_triage_recipients(exclude=actor_username)
        if not recipients:
            return
        subject = issue_notification_subject(event, issue)
        body = issue_notification_body(event, issue, actor_username, details)
        submit_notification_email(recipients, subject, body)
        now = now_utc_sql()
        recipients_text = display_usernames(recipients)
        with db_connect() as con:
            record_issue_history(
                con,
                issue_id,
                actor_username,
                "email_sent",
                f"Notification email sent to {recipients_text}",
                now,
            )
            con.commit()
    except Exception as exc:
        # REGRESSION GUARD: Mail delivery problems must not roll back or turn a
        # successful issue action into a user-visible internal server error.
        print(f"Notification email failed for issue {issue_id}: {exc}", file=sys.stderr)


def today_utc() -> _dt.date:
    return _dt.datetime.now(_dt.timezone.utc).date()


# ---------------------------------------------------------------------------
# Per-user config
# ---------------------------------------------------------------------------

def config_path(username: str) -> Path:
    return Path(PER_USER_CONFIG_DIR) / f"{username}.json"


def normalize_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "on", "yes")
    return bool(value)


def normalize_filter_name(value: Any, default: str = "any", allow_unassigned: bool = False) -> str:
    text = str(value if value is not None else default).strip()
    if text == "all":
        # REGRESSION GUARD: Legacy config files used "all" for status/admin scope;
        # updated requirements use "any" and must not revive the removed all-users filter.
        return "any"
    if text == "any" or (allow_unassigned and text == "unassigned"):
        return text
    if re.fullmatch(r"[A-Za-z0-9_.@+-]{1,128}", text):
        return text
    return default


def normalize_config(data: dict[str, Any], admin: bool = False) -> dict[str, Any]:
    status = str(data.get("status", CONFIG_DEFAULTS["status"])).strip()
    if status == "all":
        # REGRESSION GUARD: Treat old saved status=all as status=any without
        # retaining the obsolete All Users Issues preference.
        status = "any"
    priority = str(data.get("priority", CONFIG_DEFAULTS["priority"])).strip()
    creator = normalize_filter_name(data.get("creator", CONFIG_DEFAULTS["creator"])) if admin else "any"
    assignee = normalize_filter_name(data.get("assignee", CONFIG_DEFAULTS["assignee"]), allow_unassigned=True)
    state = str(data.get("state", CONFIG_DEFAULTS["state"])).strip()
    due_date = str(data.get("due_date", CONFIG_DEFAULTS["due_date"])).strip()
    search = str(data.get("search", CONFIG_DEFAULTS["search"])).strip()
    auto_refresh = str(data.get("auto_refresh", CONFIG_DEFAULTS["auto_refresh"])).strip()

    if status not in STATUSES:
        status = CONFIG_DEFAULTS["status"]
    if priority not in PRIORITIES:
        priority = CONFIG_DEFAULTS["priority"]
    if state not in ("any",) + STATES:
        state = CONFIG_DEFAULTS["state"]
    if due_date not in DUE_DATE_FILTERS:
        due_date = CONFIG_DEFAULTS["due_date"]
    if auto_refresh not in AUTO_REFRESH_OPTIONS:
        auto_refresh = CONFIG_DEFAULTS["auto_refresh"]

    # REQUIREMENTS: Static and dynamic filter preferences are normalized,
    # saved, and read consistently. The removed "all" preference is
    # intentionally omitted from the returned config.
    return {
        "status": status,
        "priority": priority,
        "creator": creator,
        "assignee": assignee,
        "state": state,
        "due_date": due_date,
        "has_comments": normalize_bool(data.get("has_comments", CONFIG_DEFAULTS["has_comments"])),
        "has_attachments": normalize_bool(data.get("has_attachments", CONFIG_DEFAULTS["has_attachments"])),
        "search": search,
        "auto_refresh": auto_refresh,
    }


def normalize_search_history(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    history: list[str] = []
    for item in value:
        term = str(item if item is not None else "").strip()
        if term and term not in history:
            history.append(term)
        if len(history) >= SEARCH_HISTORY_LIMIT:
            break
    return history


def load_user_config_data(username: str) -> dict[str, Any]:
    try:
        with config_path(username).open("r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            return data
    except Exception:
        pass
    return dict(CONFIG_DEFAULTS)


def load_user_config(username: str, admin: bool = False) -> dict[str, Any]:
    return normalize_config(load_user_config_data(username), admin)


def load_user_search_history(username: str) -> list[str]:
    return normalize_search_history(load_user_config_data(username).get("search_history", []))


def add_search_history_term(history: Iterable[str], term: str) -> list[str]:
    normalized_term = str(term or "").strip()
    values = [normalized_term] if normalized_term else []
    values.extend(str(item).strip() for item in history if str(item).strip() != normalized_term)
    return normalize_search_history(values)


def save_user_config(username: str, cfg: dict[str, Any]) -> None:
    try:
        Path(PER_USER_CONFIG_DIR).mkdir(parents=True, exist_ok=True)
        tmp = config_path(username).with_suffix(".tmp")
        stored = dict(cfg)
        if "search_history" not in stored:
            history = load_user_search_history(username)
            if history:
                stored["search_history"] = history
        elif not stored["search_history"]:
            stored["search_history"] = []
        else:
            stored["search_history"] = normalize_search_history(stored["search_history"])
        with tmp.open("w", encoding="utf-8") as f:
            json.dump(stored, f, indent=2, sort_keys=True)
        tmp.replace(config_path(username))
    except Exception:
        # Preferences must not prevent core issue tracking from working.
        pass


# ---------------------------------------------------------------------------
# Rendering helpers
# ---------------------------------------------------------------------------

def option_tags(
    options: Iterable[str],
    selected: Optional[str] = None,
    include_empty: bool = False,
    labels: Optional[dict[str, str]] = None,
) -> str:
    labels = labels or {}
    tags: list[str] = []
    if include_empty:
        tags.append(f'<option value=""{" selected" if not selected else ""}></option>')
    for opt in options:
        sel = " selected" if opt == selected else ""
        tags.append(f'<option value="{h(opt)}"{sel}>{h(labels.get(opt, opt))}</option>')
    return "\n".join(tags)


def username_option_tags(options: Iterable[str], selected: Optional[str] = None, include_empty: bool = False) -> str:
    values = list(options)
    labels = {value: display_username(value) for value in values if value not in {"any", "unassigned"}}
    return option_tags(values, selected, include_empty=include_empty, labels=labels)


def sort_usernames_for_display(usernames: Iterable[str]) -> list[str]:
    return sorted(usernames, key=lambda username: (display_username(username).lower(), username.lower()))


def assignee_option_tags(selected: Optional[str] = None) -> str:
    return username_option_tags(sort_usernames_for_display(get_assignable_users()), selected, include_empty=True)


def contributing_user_dual_list(name: str, selected_usernames: Iterable[str] = (), exclude: Iterable[str] = ()) -> str:
    excluded = {username for username in exclude if username}
    all_users = get_contributing_candidate_users()
    contributing_candidates = set(all_users)
    selected = [
        username for username in selected_usernames
        if username in contributing_candidates and username not in excluded
    ]
    selected_set = set(selected)
    display_names = {username: display_username(username) for username in all_users}
    available = sort_usernames_for_display(get_contributing_candidate_users(excluded | selected_set))
    selected = sort_usernames_for_display(selected)
    available_options = "\n".join(f'<option value="{h(username)}">{h(display_names.get(username, username))}</option>' for username in available)
    selected_options = "\n".join(f'<option value="{h(username)}">{h(display_names.get(username, username))}</option>' for username in selected)
    return f"""
<div class="dual-listbox contributing-users-dual-list" data-all-users="{h(json.dumps(all_users))}" data-user-labels="{h(json.dumps(display_names))}" data-base-excluded="{h(json.dumps(sorted(excluded)))}">
<div class="dual-listbox-column">
<label>Available users<br><select class="dual-listbox-available" multiple size="8">{available_options}</select></label>
</div>
<div class="dual-listbox-actions">
<button type="button" onclick="moveDualListOptions(this, 'right')" aria-label="Add selected contributing users">&gt;</button>
<button type="button" onclick="moveDualListOptions(this, 'left')" aria-label="Remove selected contributing users">&lt;</button>
</div>
<div class="dual-listbox-column">
<label>Contributing users<br><select class="dual-listbox-selected" name="{h(name)}" multiple size="8">{selected_options}</select></label>
</div>
</div>"""


def render_markdown_help_link() -> str:
    return f'<p class="notice"><a href="{h(action_url("markdown_help"))}" target="_blank" rel="noopener noreferrer">Markdown help</a></p>'


def render_action_button(action: str, label: str, method_name: str = "get", **params: Any) -> str:
    hidden = [f'<input type="hidden" name="action" value="{h(action)}">']
    hidden.extend(
        f'<input type="hidden" name="{h(name)}" value="{h(value)}">'
        for name, value in params.items()
        if value is not None
    )
    return f'<form class="inline" method="{h(method_name)}" action="issues.cgi">{"".join(hidden)}<input type="submit" value="{h(label)}"></form>'


# ---------------------------------------------------------------------------
# Actions
# ---------------------------------------------------------------------------

def list_filter_submitted(form: cgi.FieldStorage) -> bool:
    return any(
        name in form for name in (
            "status",
            "priority",
            "creator",
            "assignee",
            "state",
            "due_date",
            "has_comments",
            "has_attachments",
            "search",
            "auto_refresh",
            "page",
        )
    )


def sql_like_contains_pattern(value: str) -> str:
    # REGRESSION GUARD: Treat issue-list search text as a literal substring.
    # Escape SQL LIKE wildcard characters so user input such as "%" or "_"
    # cannot broaden results beyond the typed search text.
    value = value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{value.lower()}%"


def add_issue_visibility_filter(conditions: list[str], params: list[Any], username: str, admin: bool) -> None:
    if admin:
        return
    conditions.append(
        """(
            i.creator_username = ?
            OR i.assigned_username = ?
            OR EXISTS (
                SELECT 1 FROM issue_contributing_users tu_scope
                WHERE tu_scope.issue_id = i.id
                  AND tu_scope.contributing_username = ?
            )
        )"""
    )
    params.extend([username, username, username])


def add_static_list_filters(
    conditions: list[str], params: list[Any], cfg: dict[str, Any], username: str, admin: bool
) -> None:
    if cfg["status"] != "any":
        conditions.append("i.status = ?")
        params.append(cfg["status"])
    add_issue_visibility_filter(conditions, params, username, admin)

    search = cfg.get("search", "")
    if search:
        pattern = sql_like_contains_pattern(str(search))
        conditions.append("""(
            lower(i.title) LIKE ? ESCAPE '\\'
            OR lower(i.description) LIKE ? ESCAPE '\\'
            OR EXISTS (
                SELECT 1 FROM comments c_search
                WHERE c_search.issue_id = i.id
                  AND lower(c_search.comment_text) LIKE ? ESCAPE '\\'
            )
            OR EXISTS (
                SELECT 1 FROM attachments a_search
                WHERE a_search.issue_id = i.id
                  AND (
                      lower(a_search.filename) LIKE ? ESCAPE '\\'
                      OR lower(a_search.uploader_username) LIKE ? ESCAPE '\\'
                      OR lower(a_search.created_at) LIKE ? ESCAPE '\\'
                  )
            )
        )""")
        params.extend([pattern, pattern, pattern, pattern, pattern, pattern])

    # REQUIREMENTS: Due-date filters are part of the static filter group, are
    # offered and applied only for open/any status, and use the current UTC date
    # for comparisons.
    if cfg["status"] in ("open", "any"):
        today = today_utc()
        due_date_filter = cfg["due_date"]
        if due_date_filter == "no due date":
            conditions.append("(i.due_date IS NULL OR TRIM(i.due_date) = '')")
        elif due_date_filter == "today":
            conditions.append("date(i.due_date) = ?")
            params.append(today.isoformat())
        elif due_date_filter in ("within 5 days", "within 30 days"):
            days = 5 if due_date_filter == "within 5 days" else 30
            through = today + _dt.timedelta(days=days)
            conditions.append("(i.due_date IS NOT NULL AND TRIM(i.due_date) != '' AND date(i.due_date) BETWEEN ? AND ?)")
            params.extend([today.isoformat(), through.isoformat()])

    if cfg["has_comments"]:
        conditions.append("EXISTS (SELECT 1 FROM comments c_filter WHERE c_filter.issue_id = i.id)")
    if cfg["has_attachments"]:
        conditions.append("EXISTS (SELECT 1 FROM attachments a_filter WHERE a_filter.issue_id = i.id)")


def build_static_list_filters(cfg: dict[str, Any], username: str, admin: bool) -> tuple[list[str], list[Any]]:
    conditions: list[str] = []
    params: list[Any] = []
    add_static_list_filters(conditions, params, cfg, username, admin)
    return conditions, params


def count_accessible_open_issues(con: sqlite3.Connection, username: str, admin: bool) -> int:
    conditions = ["i.status = ?"]
    params: list[Any] = ["open"]
    add_issue_visibility_filter(conditions, params, username, admin)
    row = con.execute(f"SELECT COUNT(*) FROM issues i {list_where_clause(conditions)}", params).fetchone()
    return int(row[0] if row else 0)


def add_dynamic_list_filters(
    conditions: list[str], params: list[Any], cfg: dict[str, Any], admin: bool
) -> None:
    if cfg["priority"] != "any":
        conditions.append("i.priority = ?")
        params.append(cfg["priority"])

    if admin and cfg["creator"] != "any":
        conditions.append("i.creator_username = ?")
        params.append(cfg["creator"])

    if cfg["assignee"] == "unassigned":
        conditions.append("(i.assigned_username IS NULL OR TRIM(i.assigned_username) = '')")
    elif cfg["assignee"] != "any":
        conditions.append("i.assigned_username = ?")
        params.append(cfg["assignee"])

    if cfg["state"] != "any":
        conditions.append("i.state = ?")
        params.append(cfg["state"])

def list_where_clause(conditions: list[str]) -> str:
    return " WHERE " + " AND ".join(conditions) if conditions else ""


def parse_page_number(form: cgi.FieldStorage) -> int:
    try:
        return int(field_value(form, "page", "1"))
    except ValueError:
        return 1


def clamp_page(page: int, total_pages: int) -> int:
    if page < 1:
        return 1
    if page > total_pages:
        return total_pages
    return page


def list_form_hidden_inputs(
    cfg: dict[str, Any],
    page: Optional[int] = None,
    *,
    include_creator: bool = False,
    include_auto_refresh: bool = True,
) -> str:
    values: dict[str, Any] = {
        "action": "list",
        "status": cfg["status"],
        "priority": cfg["priority"],
        "assignee": cfg["assignee"],
        "state": cfg["state"],
        "search": cfg.get("search", ""),
    }
    # REGRESSION GUARD: Omit the hidden auto_refresh field from the
    # auto-refresh selector form itself. If that form contains both a hidden
    # old auto_refresh value and the newly selected <select name="auto_refresh">
    # value, some browsers submit both values and cgi.FieldStorage.getfirst()
    # reads the stale hidden value. Pagination/filter-preservation forms still
    # include auto_refresh when they do not also contain the selector.
    if include_auto_refresh:
        values["auto_refresh"] = cfg["auto_refresh"]
    # REGRESSION GUARD: Do not preserve unavailable filter controls as
    # hidden inputs. Non-admin users must not receive a creator control, and
    # due-date filtering is available only for open/any status. Hidden inputs
    # with those names are still controls to the regression suite and to the
    # browser, and can incorrectly preserve unavailable filter preferences.
    if include_creator:
        values["creator"] = cfg["creator"]
    if cfg["status"] in ("open", "any"):
        values["due_date"] = cfg["due_date"]
    if cfg.get("has_comments"):
        values["has_comments"] = "1"
    if cfg.get("has_attachments"):
        values["has_attachments"] = "1"
    if page is not None:
        values["page"] = str(page)
    return "".join(f'<input type="hidden" name="{h(k)}" value="{h(v)}">' for k, v in values.items())


def render_pagination_controls(cfg: dict[str, Any], page: int, total_pages: int, admin: bool = False) -> str:
    previous_page = max(1, page - 1)
    next_page = min(total_pages, page + 1)
    previous_disabled = " disabled" if page <= 1 else ""
    next_disabled = " disabled" if page >= total_pages else ""
    page_options = []
    for number in range(1, total_pages + 1):
        selected = " selected" if number == page else ""
        page_options.append(f'<option value="{number}"{selected}>{number} of {total_pages}</option>')
    # REGRESSION GUARD: Keep a single successful control named "page" in the
    # pagination form. Some browsers submit both a clicked submit button value
    # and the selected <select name="page"> value; others prioritize them
    # differently. That made Previous/Next ignore their target page or fall back
    # to page 1 in Firefox and IE-mode browsers. Use one hidden page field, and
    # make Previous/Next plain buttons that set that field before submitting.
    return f'''<div class="pagination-controls" style="display:inline-flex;align-items:center;justify-content:flex-end;margin:0;white-space:nowrap;">
<form method="get" action="issues.cgi" style="display:inline-flex;align-items:center;gap:0.4rem;margin:0;white-space:nowrap;">
{list_form_hidden_inputs(cfg, page=page, include_creator=admin)}
<button type="button" onclick="this.form.elements['page'].value='{previous_page}'; this.form.submit()"{previous_disabled}>Previous</button>
<select aria-label="Page" onchange="this.form.elements['page'].value=this.value; this.form.submit()">{''.join(page_options)}</select>
<button type="button" onclick="this.form.elements['page'].value='{next_page}'; this.form.submit()"{next_disabled}>Next</button>
</form>
</div>'''


def render_auto_refresh_control(cfg: dict[str, Any], page: int, admin: bool = False) -> str:
    # REGRESSION GUARD: Use the existing UTC timestamp parser/normalizer here.
    # A prior change accidentally called a nonexistent iso_utc() helper, which
    # made every issue-list request return a 500 error.
    refreshed_dt = timestamp_utc_datetime(now_utc_sql())
    refreshed_at_utc = refreshed_dt.isoformat().replace("+00:00", "Z") if refreshed_dt else ""
    # REGRESSION GUARD: The visible last-refreshed value is relative text
    # updated by browser JavaScript. Keep the server-generated UTC timestamp
    # in a data attribute so the display can update once per minute without
    # reloading the page.
    return f'''<div class="auto-refresh-control" style="display:inline-flex;align-items:center;justify-content:flex-start;margin:0;white-space:nowrap;">
<form method="get" action="issues.cgi" style="display:inline-flex;align-items:center;margin:0;white-space:nowrap;">
{list_form_hidden_inputs(cfg, page=page, include_creator=admin, include_auto_refresh=False)}
<label>Auto-refresh <select name="auto_refresh" onchange="this.form.submit()">{option_tags(AUTO_REFRESH_OPTIONS, cfg["auto_refresh"])}</select></label>
<span class="last-refreshed" data-refreshed-at-utc="{h(refreshed_at_utc)}">(Last refreshed: just now)</span>
</form>
</div>'''


def list_request_params(cfg: dict[str, Any], page: int, admin: bool = False) -> dict[str, Any]:
    params: dict[str, Any] = {
        "status": cfg["status"],
        "priority": cfg["priority"],
        "assignee": cfg["assignee"],
        "state": cfg["state"],
        "search": cfg.get("search", ""),
        "auto_refresh": cfg["auto_refresh"],
        "has_comments": "1" if cfg.get("has_comments") else None,
        "has_attachments": "1" if cfg.get("has_attachments") else None,
        "page": page,
    }
    if admin:
        params["creator"] = cfg["creator"]
    if cfg["status"] in ("open", "any"):
        params["due_date"] = cfg["due_date"]
    return params


def list_cfg_from_form(form: cgi.FieldStorage, defaults: dict[str, Any], admin: bool) -> dict[str, Any]:
    return normalize_config({
        "status": field_value(form, "status", defaults["status"]),
        "priority": field_value(form, "priority", defaults["priority"]),
        "creator": field_value(form, "creator", defaults["creator"]),
        "assignee": field_value(form, "assignee", defaults["assignee"]),
        "state": field_value(form, "state", defaults["state"]),
        "due_date": field_value(form, "due_date", defaults["due_date"]),
        "has_comments": field_value(form, "has_comments", "") in ("1", "true", "on", "yes"),
        "has_attachments": field_value(form, "has_attachments", "") in ("1", "true", "on", "yes"),
        "search": field_value(form, "search", ""),
        "auto_refresh": field_value(form, "auto_refresh", defaults["auto_refresh"]),
    }, admin)


def render_search_history_pane(cfg: dict[str, Any], history: list[str], page: int, admin: bool = False) -> str:
    if history:
        items = []
        for term in history:
            remove_params = list_request_params(cfg, page, admin)
            remove_params["term"] = term
            remove_url = action_url("search_history_remove", **remove_params)
            items.append(
                f'<li><button type="button" class="search-history-term" onclick="applySearchHistoryTerm(this, {h(json.dumps(term))})">{h(term)}</button>'
                f'<button type="button" class="search-history-delete" onclick="goToSearchHistoryUrl({h(json.dumps(remove_url))})" '
                f'aria-label="Remove search term {h(term)}" title="Remove search term">&#128465;</button></li>'
            )
        content = f'<ul>{"".join(items)}</ul>'
    else:
        content = '<p class="search-history-empty">No previous searches.</p>'
    clear_params = list_request_params(cfg, page, admin)
    clear_url = action_url("search_history_clear", **clear_params)
    content += (
        f'<div class="search-history-clear"><button type="button" onclick="goToSearchHistoryUrl({h(json.dumps(clear_url))})">'
        "Clear search history</button></div>"
    )
    return f'<div class="search-history-pane" hidden>{content}</div>'


def render_search_control(cfg: dict[str, Any], history: list[str], page: int, admin: bool = False) -> str:
    return f'''
<div class="search-box-with-history">
<button type="button" class="search-history-toggle" aria-label="Search history" title="Search history" onclick="toggleSearchHistory(this)">&#128269;</button>
<input type="search" name="search" value="{h(cfg.get('search', ''))}" placeholder="Search issues" aria-label="Search issues">
{render_search_history_pane(cfg, history, page, admin)}
</div>'''


def render_auto_refresh_script(cfg: dict[str, Any], page: int, admin: bool = False) -> str:
    seconds = AUTO_REFRESH_SECONDS.get(cfg.get("auto_refresh", "never"), 0)
    if not seconds:
        return ""
    url = action_url("list", **list_request_params(cfg, page, admin))
    milliseconds = seconds * 1000
    return f'<script>setTimeout(function(){{ window.location.href = {json.dumps(url)}; }}, {milliseconds});</script>'


def distinct_issue_values(
    con: sqlite3.Connection,
    column_sql: str,
    where: str,
    params: list[Any],
    include_blank: bool = False,
) -> list[str]:
    rows = con.execute(
        f"SELECT DISTINCT {column_sql} AS value FROM issues i {where} ORDER BY value COLLATE NOCASE",
        params,
    ).fetchall()
    values: list[str] = []
    for row in rows:
        value = "" if row["value"] is None else str(row["value"]).strip()
        if value:
            values.append(value)
        elif include_blank and "unassigned" not in values:
            values.append("unassigned")
    return values


def action_list(form: cgi.FieldStorage, username: str) -> None:
    admin = is_admin(username)
    submitted = list_filter_submitted(form)
    cfg = load_user_config(username, admin)
    search_history = load_user_search_history(username)
    if submitted:
        cfg = list_cfg_from_form(form, cfg, admin)
        search_history = add_search_history_term(search_history, cfg.get("search", ""))
        cfg["search_history"] = search_history
    else:
        # REQUIREMENTS: Stored searches are kept in history but are not applied
        # automatically on an initial issue-list load.
        cfg["search"] = ""

    static_conditions, static_params = build_static_list_filters(cfg, username, admin)
    static_where = list_where_clause(static_conditions)

    with db_connect() as con:
        # REGRESSION GUARD: Dynamic filter option lists are generated from
        # the static filter group/auth scope before dynamic filters are applied,
        # matching the requirements and avoiding self-narrowing menus.
        raw_priority_values = distinct_issue_values(con, "i.priority", static_where, static_params)
        priority_values = [value for value in PRIORITIES if value != "any" and value in raw_priority_values]
        creator_options = distinct_issue_values(con, "i.creator_username", static_where, static_params) if admin else []
        assignee_values = distinct_issue_values(con, "i.assigned_username", static_where, static_params, include_blank=True)
        state_values = [value for value in distinct_issue_values(con, "i.state", static_where, static_params) if value in STATES]

        if cfg["priority"] != "any" and cfg["priority"] not in priority_values:
            cfg["priority"] = "any"
        if admin and cfg["creator"] != "any" and cfg["creator"] not in creator_options:
            cfg["creator"] = "any"
        if cfg["assignee"] != "any" and cfg["assignee"] not in assignee_values:
            cfg["assignee"] = "any"
        if cfg["state"] != "any" and cfg["state"] not in state_values:
            cfg["state"] = "any"
        if cfg["status"] not in ("open", "any"):
            cfg["due_date"] = "any"
        if submitted:
            if search_history:
                cfg["search_history"] = search_history
            else:
                cfg.pop("search_history", None)
            save_user_config(username, cfg)

        final_conditions = list(static_conditions)
        final_params = list(static_params)
        add_dynamic_list_filters(final_conditions, final_params, cfg, admin)
        final_where = list_where_clause(final_conditions)

        sql = f"""
            SELECT i.*,
                   (SELECT COUNT(*) FROM comments c WHERE c.issue_id = i.id) AS comment_count,
                   (SELECT COUNT(*) FROM attachments a WHERE a.issue_id = i.id) AS attachment_count
            FROM issues i
            {final_where}
            ORDER BY i.id DESC
        """
        all_rows = con.execute(sql, final_params).fetchall()
        open_issue_count = count_accessible_open_issues(con, username, admin)

    total_pages = max(1, (len(all_rows) + ISSUES_PER_PAGE - 1) // ISSUES_PER_PAGE)
    page = clamp_page(parse_page_number(form), total_pages)
    start = (page - 1) * ISSUES_PER_PAGE
    rows = all_rows[start:start + ISSUES_PER_PAGE]

    creator_filter = ""
    if admin:
        creator_filter = f'<label>Creator <select name="creator" onchange="this.form.submit()">{username_option_tags(["any"] + creator_options, cfg["creator"])}</select></label>'

    due_filter = ""
    if cfg["status"] in ("open", "any"):
        due_filter = f'<label>Due <select name="due_date" onchange="this.form.submit()">{option_tags(DUE_DATE_FILTERS, cfg["due_date"])}</select></label>'

    # REGRESSION GUARD: Some browsers defer checkbox onchange handling until
    # blur. Use onclick for comments/attachments filters so clicking the
    # checkbox immediately submits the list filter form.
    comments_checked = " checked" if cfg["has_comments"] else ""
    attachments_checked = " checked" if cfg["has_attachments"] else ""
    search_control = render_search_control(cfg, search_history, page, admin)
    filter_form = f"""
<form method="get" action="issues.cgi">
<input type="hidden" name="action" value="list">
<input type="hidden" name="auto_refresh" value="{h(cfg['auto_refresh'])}">
<div class="static-filters">
<div class="static-filter-row">
<div class="static-filter-left">
<label>Status <select name="status" onchange="this.form.submit()">{option_tags(STATUSES, cfg['status'])}</select></label>
{due_filter}
<label><input type="checkbox" name="has_comments" value="1"{comments_checked} onclick="this.form.submit()"> Has comments</label>
<label><input type="checkbox" name="has_attachments" value="1"{attachments_checked} onclick="this.form.submit()"> Has attachments</label>
</div>
<div class="static-filter-search">{search_control}</div>
</div>
</div>
<div class="dynamic-filters">
<label>Priority <select name="priority" onchange="this.form.submit()">{option_tags(["any"] + priority_values, cfg['priority'])}</select></label>
{creator_filter}
<label>Assignee <select name="assignee" onchange="this.form.submit()">{username_option_tags(["any"] + assignee_values, cfg["assignee"])}</select></label>
<label>State <select name="state" onchange="this.form.submit()">{option_tags(["any"] + state_values, cfg["state"])}</select></label>
</div>
<noscript><input type="submit" value="Apply"></noscript>
</form>
"""

    pagination_top = render_pagination_controls(cfg, page, total_pages, admin)
    pagination_bottom = render_pagination_controls(cfg, page, total_pages, admin)
    auto_refresh_control = render_auto_refresh_control(cfg, page, admin)
    auto_refresh_script = render_auto_refresh_script(cfg, page, admin)
    top_controls = f'''
<div class="list-control-row issue-list-top-controls">
<div class="list-control-left" style="float:left;"><a href="{h(action_url('create'))}">Create new issue</a></div>
<div class="list-control-right" style="float:right;text-align:right;white-space:nowrap;">{pagination_top}</div>
</div>'''
    bottom_controls = f'''
<div class="list-control-row issue-list-bottom-controls">
<div class="list-control-left" style="float:left;">{auto_refresh_control}</div>
<div class="list-control-right" style="float:right;text-align:right;white-space:nowrap;">{pagination_bottom}</div>
</div>'''
    body = [filter_form, top_controls, "<table class='issue-list-table'><thead><tr><th>ID</th><th>Title</th><th>Status</th><th>Due</th><th>Priority</th><th>Creator</th><th>Assignee</th><th>State</th><th>% Complete</th><th>Comments</th><th>Attachments</th><th>Updated</th></tr></thead><tbody>"]
    for r in rows:
        body.append(
            "<tr>"
            f"<td>{h(r['id'])}</td>"
            f"<td><a href=\"{h(action_url('view', id=r['id']))}\">{h(r['title'])}</a></td>"
            f"<td>{h(r['status'])}</td>"
            f"<td>{h(r['due_date'])}</td>"
            f"<td>{h(r['priority'])}</td>"
            f"<td>{h(display_username(r['creator_username']))}</td>"
            f"<td>{h(display_username(r['assigned_username']))}</td>"
            f"<td>{h(r['state'])}</td>"
            f"<td>{h(r['pct_complete'])}</td>"
            f"<td>{h(r['comment_count'])}</td>"
            f"<td>{h(r['attachment_count'])}</td>"
            f"<td>{timestamp_html(r['updated_at'])}</td>"
            "</tr>"
        )
    if not rows:
        body.append("<tr><td colspan='12'>No matching issues.</td></tr>")
    body.append("</tbody></table>")
    body.append(bottom_controls)
    body.append(auto_refresh_script)
    send_headers()
    print(render_page("Issue List", "\n".join(body), username, browser_title=f"Issue List - {open_issue_count} open"))


def action_view(form: cgi.FieldStorage, username: str) -> None:
    issue_id = require_id(form)
    with db_connect() as con:
        issue = require_issue_access(con, issue_id, username)
        comments = con.execute(
            "SELECT * FROM comments WHERE issue_id = ? ORDER BY created_at DESC, id DESC", (issue_id,)
        ).fetchall()
        total_time_worked = con.execute(
            "SELECT COALESCE(SUM(time_worked_minutes), 0) FROM comments WHERE issue_id = ?", (issue_id,)
        ).fetchone()[0]
        attachments = con.execute(
            "SELECT id, filename, uploader_username, created_at FROM attachments WHERE issue_id = ? ORDER BY created_at ASC, id ASC",
            (issue_id,),
        ).fetchall()
        contributing_users = fetch_contributing_usernames(con, issue_id)

    admin = is_admin(username)
    open_issue = issue["status"] == "open"
    owner_or_admin = can_owner_or_admin(issue, username)
    assigned = issue["assigned_username"] == username
    can_manage_tags = can_manage_contributing_users(issue, username)
    user_is_contributing = username in contributing_users
    can_comment_attach = open_issue and (owner_or_admin or assigned or user_is_contributing)

    actions: list[str] = [render_action_button("list", "Back to list")]
    actions.append(render_action_button("history", "History", id=issue_id))
    if open_issue and owner_or_admin:
        actions.append(render_action_button("update", "Edit Title & Description", id=issue_id))
    if can_comment_attach:
        actions.append(render_action_button("comment", "Add comment", id=issue_id))
        actions.append(render_action_button("attach", "Add attachment", id=issue_id))
    if open_issue and (owner_or_admin or assigned):
        actions.append(render_action_button("close", "Close", id=issue_id))
    if open_issue and issue["creator_username"] == username:
        actions.append(render_action_button("cancel", "Cancel", id=issue_id))
    if issue["status"] != "open" and admin:
        actions.append(render_action_button("reopen", "Re-open", "post", id=issue_id))

    assign_cell = h(display_username(issue["assigned_username"]))
    if open_issue and owner_or_admin:
        assign_cell = f"""
<form method="post" action="issues.cgi" class="inline">
<input type="hidden" name="action" value="assign"><input type="hidden" name="id" value="{h(issue_id)}">
<select name="assigned_username" onchange="this.form.submit()">{assignee_option_tags(issue['assigned_username'])}</select>
</form>"""

    priority_cell = h(issue["priority"])
    if open_issue and owner_or_admin:
        priority_cell = f"""
<form method="post" action="issues.cgi" class="inline">
<input type="hidden" name="action" value="set_priority"><input type="hidden" name="id" value="{h(issue_id)}">
<select name="priority" onchange="this.form.submit()">{option_tags([p for p in PRIORITIES if p != 'any'], issue['priority'])}</select>
</form>"""

    percent_cell = h(issue["pct_complete"])
    if open_issue and assigned:
        percent_cell = f"""
<form method="post" action="issues.cgi" class="inline">
<input type="hidden" name="action" value="set_percent_complete"><input type="hidden" name="id" value="{h(issue_id)}">
<input type="number" name="pct_complete" min="0" max="100" value="{h(issue['pct_complete'])}" oninput="this.form.querySelector('input[type=submit]').disabled = false">
<input type="submit" value="Set" disabled>
</form>"""

    state_cell = h(issue["state"])
    if open_issue and assigned:
        state_cell = f"""
<form method="post" action="issues.cgi" class="inline">
<input type="hidden" name="action" value="set_state"><input type="hidden" name="id" value="{h(issue_id)}">
<select name="state" onchange="this.form.submit()">{option_tags(STATES, issue['state'])}</select>
</form>"""

    due_value = issue["due_date"] or ""
    due_cell = h(due_value if (due_value or not open_issue) else "YYYY-MM-DD")
    if open_issue and owner_or_admin:
        due_cell = f"""
<form method="post" action="issues.cgi" class="inline">
<input type="hidden" name="action" value="set_due_date"><input type="hidden" name="id" value="{h(issue_id)}">
<input type="date" name="due_date" value="{h(due_value)}" placeholder="YYYY-MM-DD" oninput="this.form.querySelector('input[type=submit]').disabled = false">
<input type="submit" value="Set" disabled>
</form>"""

    rows = [
        ("ID", issue["id"]),
        ("Title", issue["title"]),
        ("Creator", display_username(issue["creator_username"])),
        ("Assignee", assign_cell),
        ("Priority", priority_cell),
        ("Percent complete", percent_cell),
        ("State", state_cell),
        ("Time in current state", (elapsed_time_worked(issue["state_changed_at"] or issue["created_at"]) + " (wall clock)") if open_issue else ""),
        ("Status", issue["status"]),
        ("Due date", due_cell),
        ("Created", timestamp_html(issue["created_at"])),
        ("Updated", timestamp_html(issue["updated_at"])),
    ]
    if int(total_time_worked or 0) > 0:
        rows.insert(8, ("Total time worked", f"{labeled_time_worked(total_time_worked)} (work time)"))
    if issue["status"] in ISSUE_TERMINAL_STATUSES:
        rows.append(("Completed", timestamp_html(issue["completed_at"])))

    contributing_display = display_usernames(contributing_users) if contributing_users else "none"
    rows.append(("Contributing users", contributing_display))

    meta_rows = []
    for label, value in rows:
        if label == "Time in current state" and not open_issue:
            continue
        meta_rows.append(
            f"<tr><th>{h(label)}</th><td>{value if label in {'Assignee','Priority','Percent complete','State','Due date','Created','Updated','Completed','Time in current state'} else h(value)}</td></tr>"
        )
    meta = "<table class='issue-metadata-table'>" + "".join(meta_rows) + "</table>"

    comments_html = ["<div class='section'><h2>Comments</h2>"]
    if comments:
        for c in comments:
            time_worked = ""
            if c["time_worked_minutes"] is not None:
                time_worked = f" (Time worked: {h(labeled_time_worked(c['time_worked_minutes']))} (work time))"
            comments_html.append(
                f"<article><div class='comment-meta'>{h(display_username(c['commenter_username']))} at {timestamp_html(c['created_at'])}{time_worked}</div>"
                f"<div class='markdown-body'>{markdown_to_html(c['comment_text'])}</div></article>"
            )
    else:
        comments_html.append("<p>No comments.</p>")
    comments_html.append("</div>")

    attach_html = ["<div class='section'><h2>Attachments</h2>"]
    if attachments:
        attach_html.append("<table><tr><th>Filename</th><th>Uploader</th><th>Created</th></tr>")
        for a in attachments:
            attach_html.append(
                f"<tr><td><a href=\"{h(action_url('download', id=a['id']))}\">{h(a['filename'])}</a></td>"
                f"<td>{h(display_username(a['uploader_username']))}</td><td>{timestamp_html(a['created_at'])}</td></tr>"
            )
        attach_html.append("</table>")
    else:
        attach_html.append("<p>No attachments.</p>")
    attach_html.append("</div>")

    tag_html = ["<div class='section'><h2>Contributing users</h2>"]
    if can_manage_tags:
        role_exclusions = [issue["creator_username"], issue["assigned_username"]]
        tag_html.append(f"""
<form method="post" action="issues.cgi" onsubmit="return prepareDualListSubmit(this)">
<input type="hidden" name="action" value="contributing_users_update">
<input type="hidden" name="id" value="{h(issue_id)}">
<input type="hidden" name="contributing_users_final_present" value="1">
{contributing_user_dual_list("contributing_users_final", contributing_users, role_exclusions)}
<p class="form-actions"><input type="submit" value="Update contributing users"></p>
</form>""")
    elif user_is_contributing:
        tag_html.append(f"""
<form method="post" action="issues.cgi">
<input type="hidden" name="action" value="contributing_users_update">
<input type="hidden" name="id" value="{h(issue_id)}">
<input type="hidden" name="remove_contributing_users" value="{h(username)}">
<p class="form-actions"><input type="submit" value="Remove me from contributing users"></p>
</form>""")
    elif contributing_users:
        tag_html.append("<p>" + h(display_usernames(contributing_users)) + "</p>")
    else:
        tag_html.append("<p>No contributing users.</p>")
    tag_html.append("</div>")

    body = f"""
<div class="actions">{' '.join(actions)}</div>
{meta}
<div class="section"><h2>Description</h2><div class="markdown-body">{markdown_to_html(issue['description'])}</div></div>
{''.join(tag_html)}
{''.join(comments_html)}
{''.join(attach_html)}
"""
    send_headers()
    print(render_page(f"Issue {issue_id} - {issue['title']}", body, username))


def action_create(form: cgi.FieldStorage, username: str) -> None:
    if method() == "POST":
        return action_create_submit(form, username)
    return_to = previous_page_url(form, action_url("list"))
    body = f"""
<form method="post" action="issues.cgi" onsubmit="return prepareDualListSubmit(this)">
<input type="hidden" name="action" value="create_submit">
{hidden_return_to(return_to)}
<p><label>Title<br><input type="text" name="title" size="80" required autofocus></label></p>
<p><label>Description<br><textarea name="description" required></textarea></label></p>
{render_markdown_help_link()}
<p><label>Priority <select name="priority">{option_tags([p for p in PRIORITIES if p != 'any'], 'normal')}</select></label></p>
<p><label>Due date <input type="date" name="due_date"></label> <span class="notice">Use YYYY-MM-DD.</span></p>
<p><label>Assignee <select name="assigned_username" onchange="syncContributingUsersWithAssignee(this)">{assignee_option_tags('')}</select></label></p>
<div class="section"><h2>Contributing users</h2>{contributing_user_dual_list("contributing_users", [], [username])}</div>
<p class="form-actions"><input type="submit" value="Create issue">{cancel_control(return_to)}</p>
</form>
"""
    send_headers()
    print(render_page("Create Issue", body, username))


def action_create_submit(form: cgi.FieldStorage, username: str) -> None:
    title = field_value(form, "title").strip()
    description = field_value(form, "description").strip()
    priority = field_value(form, "priority", "normal").strip()
    due_date = optional_str(field_value(form, "due_date"))
    assignee = optional_str(field_value(form, "assigned_username"))

    if not title:
        raise AppError("Title is required")
    if not description:
        raise AppError("Description is required")
    if priority not in [p for p in PRIORITIES if p != "any"]:
        raise AppError("Invalid priority")
    if due_date:
        validate_due_date(due_date)
    if assignee and not valid_assignee(assignee):
        raise AppError("Assignee does not exist or is not assignable")
    contributing_users = validate_contributing_usernames_for_issue_roles(
        contributing_user_values(form, "contributing_users"),
        [username, assignee or ""],
    )

    now = now_utc_sql()
    with db_connect() as con:
        cur = con.execute(
            """INSERT INTO issues
               (title, description, creator_username, assigned_username, priority, pct_complete, state, status, due_date, created_at, updated_at, state_changed_at, completed_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (title, description, username, assignee or "", priority, 0, STATES[0], "open", due_date, now, now, now, None),
        )
        issue_id = int(cur.lastrowid)
        record_issue_history(con, issue_id, username, "created", "Created issue", now)
        for contributing_username in contributing_users:
            con.execute(
                "INSERT INTO issue_contributing_users (issue_id, contributing_username, contributed_by_username, created_at) VALUES (?, ?, ?, ?)",
                (issue_id, contributing_username, username, now),
            )
        if contributing_users:
            record_issue_history(con, issue_id, username, "contributing_users_added", contributing_users_summary(contributing_users, "Added"), now)
        con.commit()
    create_event = "Issue assigned" if assignee else "Issue created"
    notify_issue_event(issue_id, username, unique_notification_recipients([assignee] + contributing_users, exclude=username), create_event)
    redirect(action_url("view", id=issue_id))


def action_assign(form: cgi.FieldStorage, username: str) -> None:
    issue_id = require_id(form)
    assignee = field_value(form, "assigned_username").strip()
    if assignee and not valid_assignee(assignee):
        raise AppError("Target user does not exist or is not assignable")
    with db_connect() as con:
        issue = fetch_issue(con, issue_id)
        if issue is None:
            raise AppError("Issue not found", "404 Not Found")
        if issue["status"] != "open":
            raise AppError("Only open issues can be assigned")
        if not can_owner_or_admin(issue, username):
            raise AppError("You are not authorized to assign this issue", "403 Forbidden")
        now = now_utc_sql()
        con.execute("UPDATE issues SET assigned_username = ?, updated_at = ? WHERE id = ?", (assignee, now, issue_id))
        record_issue_history(
            con, issue_id, username, "assigned",
            history_user_change_summary("assignee", issue["assigned_username"], assignee), now
        )
        con.commit()
    notification_recipients = [assignee]
    if assignee and str(issue["assigned_username"] or "").strip() and str(issue["assigned_username"] or "").strip() != assignee:
        notification_recipients.append(issue["assigned_username"])
    notify_issue_event(
        issue_id,
        username,
        unique_notification_recipients(notification_recipients, exclude=username),
        "Issue assigned",
    )
    redirect(action_url("view", id=issue_id))


def action_contributing_users_update(form: cgi.FieldStorage, username: str) -> None:
    issue_id = require_id(form)
    raw_add_usernames = contributing_user_values(form, "add_contributing_users")
    remove_usernames = contributing_user_values(form, "remove_contributing_users")
    final_usernames_present = "contributing_users_final_present" in form
    raw_final_usernames = contributing_user_values(form, "contributing_users_final")
    with db_connect() as con:
        issue = fetch_issue(con, issue_id)
        if issue is None:
            raise AppError("Issue not found", "404 Not Found")
        current_contributors = set(fetch_contributing_usernames(con, issue_id))
        manager = can_manage_contributing_users(issue, username)
        if not manager:
            if final_usernames_present or raw_add_usernames or any(contributing_username != username for contributing_username in remove_usernames):
                raise AppError("You are not authorized to update contributing users for this issue", "403 Forbidden")
            if username not in current_contributors:
                raise AppError("You are not authorized to update contributing users for this issue", "403 Forbidden")
            remove_usernames = [username]
            add_usernames: list[str] = []
        else:
            role_exclusions = [issue["creator_username"], issue["assigned_username"]]
            if final_usernames_present:
                final_usernames = set(validate_contributing_usernames_for_issue_roles(raw_final_usernames, role_exclusions))
                add_usernames = sorted(final_usernames - current_contributors)
                remove_usernames = sorted(current_contributors - final_usernames)
            else:
                add_usernames = validate_contributing_usernames_for_issue_roles(raw_add_usernames, role_exclusions)

        added = [contributing_username for contributing_username in add_usernames if contributing_username not in current_contributors]
        removed = [contributing_username for contributing_username in remove_usernames if contributing_username in current_contributors]
        if added or removed:
            now = now_utc_sql()
            for contributing_username in added:
                con.execute(
                    "INSERT INTO issue_contributing_users (issue_id, contributing_username, contributed_by_username, created_at) VALUES (?, ?, ?, ?)",
                    (issue_id, contributing_username, username, now),
                )
            for contributing_username in removed:
                con.execute(
                    "DELETE FROM issue_contributing_users WHERE issue_id = ? AND contributing_username = ?",
                    (issue_id, contributing_username),
                )
            con.execute("UPDATE issues SET updated_at = ? WHERE id = ?", (now, issue_id))
            if added:
                record_issue_history(con, issue_id, username, "contributing_users_added", contributing_users_summary(added, "Added"), now)
            if removed:
                record_issue_history(con, issue_id, username, "contributing_users_removed", contributing_users_summary(removed, "Removed"), now)
            con.commit()
        else:
            con.commit()

    if added:
        recipients = unique_notification_recipients(added, exclude=username)
        if recipients:
            notify_issue_event(issue_id, username, recipients, "Contributing user added")
    if removed:
        recipients = unique_notification_recipients(removed, exclude=username)
        if recipients:
            notify_issue_event(issue_id, username, recipients, "Contributing user removed")
    redirect(action_url("view", id=issue_id))


def search_history_redirect(form: cgi.FieldStorage, username: str) -> None:
    admin = is_admin(username)
    cfg = list_cfg_from_form(form, load_user_config(username, admin), admin)
    page = parse_page_number(form)
    redirect(action_url("list", **list_request_params(cfg, page, admin)))


def action_search_history_remove(form: cgi.FieldStorage, username: str) -> None:
    term = field_value(form, "term").strip()
    history = [item for item in load_user_search_history(username) if item != term]
    cfg = list_cfg_from_form(form, load_user_config(username, is_admin(username)), is_admin(username))
    cfg["search_history"] = history
    save_user_config(username, cfg)
    search_history_redirect(form, username)


def action_search_history_clear(form: cgi.FieldStorage, username: str) -> None:
    cfg = list_cfg_from_form(form, load_user_config(username, is_admin(username)), is_admin(username))
    cfg["search_history"] = []
    save_user_config(username, cfg)
    search_history_redirect(form, username)


def action_attach(form: cgi.FieldStorage, username: str) -> None:
    if method() == "POST":
        return action_attach_submit(form, username)
    issue_id = require_id(form)
    return_to = previous_page_url(form, action_url("view", id=issue_id))
    with db_connect() as con:
        issue = require_issue_access(con, issue_id, username)
        if issue["status"] != "open":
            raise AppError("Only open issues can have attachments added")
        if not can_owner_assigned_contributing_or_admin(issue, username, con):
            raise AppError("You are not authorized to attach files to this issue", "403 Forbidden")
    max_upload_mb = MAX_UPLOAD_BYTES / (1024 * 1024)
    max_upload_display = f"{max_upload_mb:g} MB"
    body = f"""
<form method="post" action="issues.cgi" enctype="multipart/form-data">
<input type="hidden" name="action" value="attach_submit">
<input type="hidden" name="id" value="{h(issue_id)}">
{hidden_return_to(return_to)}
<p><label>File <input type="file" name="file" required></label></p>
<p class="notice">Maximum upload size: {h(max_upload_display)}.</p>
<p class="form-actions"><input type="submit" value="Attach file">{cancel_control(return_to)}</p>
</form>
"""
    send_headers()
    print(render_page("Attach File", body, username))


def normalize_filename(filename: str) -> str:
    name = os.path.basename(filename or "")
    name = re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("._")
    if not name:
        name = "attachment"
    return name[:MAX_FILENAME_LEN]


def action_attach_submit(form: cgi.FieldStorage, username: str) -> None:
    issue_id = require_id(form)
    upload = form["file"] if "file" in form else None
    if upload is None or not getattr(upload, "filename", ""):
        raise AppError("No file supplied")
    data = upload.file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise AppError("Uploaded file exceeds maximum size")
    filename = normalize_filename(upload.filename)

    with db_connect() as con:
        issue = fetch_issue(con, issue_id)
        if issue is None:
            raise AppError("Issue not found", "404 Not Found")
        if issue["status"] != "open":
            raise AppError("Only open issues can have attachments added")
        if not can_owner_assigned_contributing_or_admin(issue, username, con):
            raise AppError("You are not authorized to attach files to this issue", "403 Forbidden")
        now = now_utc_sql()
        cur = con.execute(
            "INSERT INTO attachments (issue_id, filename, content, uploader_username, created_at) VALUES (?, ?, ?, ?, ?)",
            (issue_id, filename, sqlite3.Binary(data), username, now),
        )
        attachment_id = int(cur.lastrowid)
        con.execute("UPDATE issues SET updated_at = ? WHERE id = ?", (now, issue_id))
        record_issue_history(
            con, issue_id, username, "attachment_added",
            f"Added attachment {history_summary_text(filename)}", now, attachment_id=attachment_id
        )
        recipients = issue_participant_recipients(con, issue, exclude=username)
        attachment_details = "\n".join([
            "Attachment:",
            f"Filename: {notification_body_text(filename)}",
            f"Uploaded by: {username}",
            f"Uploaded at: {now}",
            f"Size: {len(data)} bytes",
        ])
        con.commit()
    notify_issue_event(issue_id, username, recipients, "Attachment added", attachment_details)
    redirect(action_url("view", id=issue_id))


def action_download(form: cgi.FieldStorage, username: str) -> None:
    attachment_id = require_id(form)
    with db_connect() as con:
        row = con.execute(
            """SELECT a.*, i.creator_username, i.assigned_username, i.id AS issue_id
               FROM attachments a JOIN issues i ON i.id = a.issue_id
               WHERE a.id = ?""",
            (attachment_id,),
        ).fetchone()
        if row is None:
            raise AppError("Attachment not found", "404 Not Found")
        pseudo_issue = {"id": row["issue_id"], "creator_username": row["creator_username"], "assigned_username": row["assigned_username"]}
        if not can_view_issue(pseudo_issue, username, con):
            raise AppError("You are not authorized to download this attachment", "403 Forbidden")
        filename = normalize_filename(row["filename"])
        content = row["content"]
    ctype = mimetypes.guess_type(filename)[0] or "application/octet-stream"
    send_headers(
        ctype,
        extra_headers=[
            ("Content-Disposition", f'attachment; filename="{filename}"'),
            ("Content-Length", str(len(content))),
        ],
    )
    sys.stdout.flush()
    sys.stdout.buffer.write(content)
    raise ResponseSent()


def render_comment_form(issue_id: int, username: str, comment_text: str = "", time_worked: str = "", error: str = "", return_to: str = "") -> str:
    error_html = f'<p class="error">{h(error)}</p>' if error else ""
    return_target = return_to or action_url("view", id=issue_id)
    body = f"""
{error_html}
<form method="post" action="issues.cgi">
<input type="hidden" name="action" value="comment_submit">
<input type="hidden" name="id" value="{h(issue_id)}">
{hidden_return_to(return_target)}
<p><label>Comment<br><textarea name="comment_text" required autofocus>{h(comment_text)}</textarea></label></p>
<p><label>Time worked (optional)<br><input type="text" name="time_worked" value="{h(time_worked)}" size="24" placeholder="Examples: 30m, 1.5h, 1d" onfocus="this.dataset.placeholder=this.placeholder;this.placeholder=''" onblur="if(!this.placeholder) this.placeholder=this.dataset.placeholder || 'Examples: 30m, 1.5h, 1d'"></label></p>
{render_markdown_help_link()}
<p class="form-actions"><input type="submit" value="Add comment">{cancel_control(return_target)}</p>
</form>
"""
    return render_page("Add Comment", body, username)


def action_comment(form: cgi.FieldStorage, username: str) -> None:
    if method() == "POST":
        return action_comment_submit(form, username)
    issue_id = require_id(form)
    with db_connect() as con:
        issue = fetch_issue(con, issue_id)
        if issue is None:
            raise AppError("Issue not found", "404 Not Found")
        # REGRESSION GUARD: Closed/canceled issue comment forms are admin-only even when the user can view the issue.
        if issue["status"] == "open":
            allowed = can_owner_assigned_contributing_or_admin(issue, username, con)
        else:
            allowed = is_admin(username)
        if not allowed:
            raise AppError("You are not authorized to comment on this issue", "403 Forbidden")
    send_headers()
    print(render_comment_form(issue_id, username, return_to=previous_page_url(form, action_url("view", id=issue_id))))


def action_comment_submit(form: cgi.FieldStorage, username: str) -> None:
    issue_id = require_id(form)
    comment = field_value(form, "comment_text").strip()
    if not comment:
        raise AppError("Comment text is required")
    time_worked_raw = field_value(form, "time_worked", "")
    with db_connect() as con:
        issue = fetch_issue(con, issue_id)
        if issue is None:
            raise AppError("Issue not found", "404 Not Found")
        if issue["status"] == "open":
            allowed = can_owner_assigned_contributing_or_admin(issue, username, con)
        else:
            allowed = is_admin(username)
        if not allowed:
            raise AppError("You are not authorized to comment on this issue", "403 Forbidden")
        try:
            time_worked_minutes = parse_time_worked_minutes(time_worked_raw)
        except ValueError as exc:
            send_headers(status="400 Bad Request")
            print(render_comment_form(issue_id, username, comment, time_worked_raw, str(exc), previous_page_url(form, action_url("view", id=issue_id))))
            raise ResponseSent()
        now = now_utc_sql()
        cur = con.execute(
            "INSERT INTO comments (issue_id, commenter_username, comment_text, time_worked_minutes, created_at) VALUES (?, ?, ?, ?, ?)",
            (issue_id, username, comment, time_worked_minutes, now),
        )
        comment_id = int(cur.lastrowid)
        con.execute("UPDATE issues SET updated_at = ? WHERE id = ?", (now, issue_id))
        record_issue_history(con, issue_id, username, "comment_added", "Added comment", now, comment_id=comment_id)
        recipients = issue_participant_recipients(con, issue, exclude=username)
        con.commit()
    comment_details = "Comment:\n" + notification_body_text(comment)
    notify_issue_event(issue_id, username, recipients, "Comment added", comment_details)
    redirect(action_url("view", id=issue_id))


def action_update(form: cgi.FieldStorage, username: str) -> None:
    if method() == "POST":
        return action_update_submit(form, username)
    issue_id = require_id(form)
    return_to = previous_page_url(form, action_url("view", id=issue_id))
    with db_connect() as con:
        issue = fetch_issue(con, issue_id)
        if issue is None:
            raise AppError("Issue not found", "404 Not Found")
        # REGRESSION GUARD: The update form itself must not render for closed or canceled issues.
        if issue["status"] != "open":
            raise AppError("Only open issues can be updated")
        if not can_owner_or_admin(issue, username):
            raise AppError("You are not authorized to edit this issue", "403 Forbidden")
    body = f"""
<form method="post" action="issues.cgi">
<input type="hidden" name="action" value="update_submit">
<input type="hidden" name="id" value="{h(issue_id)}">
{hidden_return_to(return_to)}
<p><label>Title<br><input type="text" name="title" size="80" value="{h(issue['title'])}" required autofocus></label></p>
<p><label>Description<br><textarea name="description">{h(issue['description'])}</textarea></label></p>
{render_markdown_help_link()}
<p class="form-actions"><input type="submit" value="Update issue">{cancel_control(return_to)}</p>
</form>
"""
    send_headers()
    print(render_page("Update Issue", body, username))


def action_update_submit(form: cgi.FieldStorage, username: str) -> None:
    issue_id = require_id(form)
    title = field_value(form, "title").strip()
    description_supplied = "description" in form
    description = field_value(form, "description")
    if not title:
        raise AppError("Title is required")
    with db_connect() as con:
        issue = fetch_issue(con, issue_id)
        if issue is None:
            raise AppError("Issue not found", "404 Not Found")
        if issue["status"] != "open":
            raise AppError("Only open issues can be updated")
        if not can_owner_or_admin(issue, username):
            raise AppError("You are not authorized to update this issue", "403 Forbidden")
        now = now_utc_sql()
        summary = issue_update_summary(issue, title, description_supplied, description)
        if description_supplied:
            con.execute("UPDATE issues SET title = ?, description = ?, updated_at = ? WHERE id = ?", (title, description, now, issue_id))
        else:
            con.execute("UPDATE issues SET title = ?, updated_at = ? WHERE id = ?", (title, now, issue_id))
        record_issue_history(con, issue_id, username, "updated", summary, now)
        recipients = issue_participant_recipients(con, issue, exclude=username)
        updated_description = description if description_supplied else issue["description"]
        update_details = "\n".join([
            "Updated title:",
            notification_body_text(title),
            "",
            "Updated description:",
            notification_body_text(updated_description),
        ])
        con.commit()
    notify_issue_event(issue_id, username, recipients, "Issue updated", update_details)
    redirect(action_url("view", id=issue_id))


def action_set_priority(form: cgi.FieldStorage, username: str) -> None:
    issue_id = require_id(form)
    priority = field_value(form, "priority").strip()
    if priority not in [p for p in PRIORITIES if p != "any"]:
        raise AppError("Invalid priority")
    with db_connect() as con:
        issue = fetch_issue(con, issue_id)
        if issue is None:
            raise AppError("Issue not found", "404 Not Found")
        # REGRESSION GUARD: Direct CGI calls must not update priority on closed or canceled issues.
        if issue["status"] != "open":
            raise AppError("Only open issues can have priority updated")
        if not can_owner_or_admin(issue, username):
            raise AppError("You are not authorized to set priority", "403 Forbidden")
        now = now_utc_sql()
        old_priority = issue["priority"]
        con.execute("UPDATE issues SET priority = ?, updated_at = ? WHERE id = ?", (priority, now, issue_id))
        record_issue_history(con, issue_id, username, "priority_changed", history_change_summary("priority", old_priority, priority), now)
        con.commit()
    redirect(action_url("view", id=issue_id))


def validate_due_date(value: str) -> None:
    try:
        due = _dt.date.fromisoformat(value)
    except ValueError:
        raise AppError("Due date must be YYYY-MM-DD")
    if due <= today_utc():
        raise AppError("Due date must be later than the current UTC date")


def action_set_due_date(form: cgi.FieldStorage, username: str) -> None:
    issue_id = require_id(form)
    due_date = field_value(form, "due_date").strip()
    validate_due_date(due_date)
    with db_connect() as con:
        issue = fetch_issue(con, issue_id)
        if issue is None:
            raise AppError("Issue not found", "404 Not Found")
        # REGRESSION GUARD: Direct CGI calls must not bypass the open-issue-only due-date rule.
        if issue["status"] != "open":
            raise AppError("Only open issues can have due dates updated")
        if not can_owner_or_admin(issue, username):
            raise AppError("You are not authorized to set due date", "403 Forbidden")
        now = now_utc_sql()
        old_due = display_value(issue["due_date"], "no due date")
        con.execute("UPDATE issues SET due_date = ?, updated_at = ? WHERE id = ?", (due_date, now, issue_id))
        record_issue_history(con, issue_id, username, "due_date_changed", history_change_summary("due date", old_due, due_date), now)
        recipients = unique_notification_recipients([issue["assigned_username"]], exclude=username)
        con.commit()
    notify_issue_event(issue_id, username, recipients, "Due date changed")
    redirect(action_url("view", id=issue_id))


def action_set_percent_complete(form: cgi.FieldStorage, username: str) -> None:
    issue_id = require_id(form)
    raw = field_value(form, "pct_complete").strip()
    try:
        pct = int(raw)
    except ValueError:
        raise AppError("Percent complete must be an integer")
    if pct < 0 or pct > 100:
        raise AppError("Percent complete must be between 0 and 100")
    with db_connect() as con:
        issue = fetch_issue(con, issue_id)
        if issue is None:
            raise AppError("Issue not found", "404 Not Found")
        # REGRESSION GUARD: Direct CGI calls must not update percent complete on closed or canceled issues.
        if issue["status"] != "open":
            raise AppError("Only open issues can have percent complete updated")
        if issue["assigned_username"] != username:
            raise AppError("Only the assigned user can set percent complete", "403 Forbidden")
        now = now_utc_sql()
        old_pct = issue["pct_complete"]
        con.execute("UPDATE issues SET pct_complete = ?, updated_at = ? WHERE id = ?", (pct, now, issue_id))
        record_issue_history(con, issue_id, username, "percent_complete_changed", history_change_summary("percent complete", old_pct, pct), now)
        con.commit()
    redirect(action_url("view", id=issue_id))


def action_set_state(form: cgi.FieldStorage, username: str) -> None:
    issue_id = require_id(form)
    state = field_value(form, "state").strip()
    if state not in STATES:
        raise AppError("Invalid state")
    with db_connect() as con:
        issue = fetch_issue(con, issue_id)
        if issue is None:
            raise AppError("Issue not found", "404 Not Found")
        # REGRESSION GUARD: Direct CGI calls must not update state on closed or canceled issues.
        if issue["status"] != "open":
            raise AppError("Only open issues can have state updated")
        if issue["assigned_username"] != username:
            raise AppError("Only the assigned user can set state", "403 Forbidden")
        # REQUIREMENTS: Marking workflow state complete must also set percent complete to 100.
        now = now_utc_sql()
        old_state = issue["state"]
        if state == "complete":
            con.execute("UPDATE issues SET state = ?, pct_complete = 100, updated_at = ?, state_changed_at = ? WHERE id = ?", (state, now, now, issue_id))
        else:
            con.execute("UPDATE issues SET state = ?, updated_at = ?, state_changed_at = ? WHERE id = ?", (state, now, now, issue_id))
        record_issue_history(con, issue_id, username, "state_changed", history_change_summary("state", old_state, state), now)
        con.commit()
    redirect(action_url("view", id=issue_id))


def action_close(form: cgi.FieldStorage, username: str) -> None:
    if method() == "POST":
        return action_close_submit(form, username)
    issue_id = require_id(form)
    return_to = previous_page_url(form, action_url("view", id=issue_id))
    with db_connect() as con:
        issue = fetch_issue(con, issue_id)
        if issue is None:
            raise AppError("Issue not found", "404 Not Found")
        if issue["status"] != "open":
            raise AppError("Only open issues can be closed")
        if not can_owner_assigned_or_admin(issue, username):
            raise AppError("You are not authorized to close this issue", "403 Forbidden")
    body = f"""
<form method="post" action="issues.cgi">
<input type="hidden" name="action" value="close_submit">
<input type="hidden" name="id" value="{h(issue_id)}">
{hidden_return_to(return_to)}
<p><label>Closing comment<br><textarea name="closing_comment" autofocus></textarea></label></p>
{render_markdown_help_link()}
<p class="form-actions"><input type="submit" value="Close issue">{cancel_control(return_to)}</p>
</form>
"""
    send_headers()
    print(render_page("Close Issue", body, username))


def action_close_submit(form: cgi.FieldStorage, username: str) -> None:
    issue_id = require_id(form)
    comment = field_value(form, "closing_comment", field_value(form, "comment_text", "")).strip() or DEFAULT_CLOSING_COMMENT
    with db_connect() as con:
        issue = fetch_issue(con, issue_id)
        if issue is None:
            raise AppError("Issue not found", "404 Not Found")
        # REGRESSION GUARD: The close action can be invoked directly, so enforce open status here too.
        if issue["status"] != "open":
            raise AppError("Only open issues can be closed")
        if not can_owner_assigned_or_admin(issue, username):
            raise AppError("You are not authorized to close this issue", "403 Forbidden")
        now = now_utc_sql()
        # REQUIREMENTS: Closing an issue makes the workflow state complete, which also makes percent complete 100.
        con.execute("UPDATE issues SET status = 'closed', state = 'complete', pct_complete = 100, completed_at = ?, updated_at = ?, state_changed_at = ? WHERE id = ?", (now, now, now, issue_id))
        cur = con.execute(
            "INSERT INTO comments (issue_id, commenter_username, comment_text, created_at) VALUES (?, ?, ?, ?)",
            (issue_id, username, comment, now),
        )
        comment_id = int(cur.lastrowid)
        record_issue_history(con, issue_id, username, "closed", "Closed issue with comment", now, comment_id=comment_id)
        recipients = issue_participant_recipients(con, issue, exclude=username)
        con.commit()
    notify_issue_event(issue_id, username, recipients, "Issue closed")
    redirect(action_url("view", id=issue_id), "302 Found")


def action_cancel(form: cgi.FieldStorage, username: str) -> None:
    if method() == "POST":
        return action_cancel_submit(form, username)
    issue_id = require_id(form)
    return_to = previous_page_url(form, action_url("view", id=issue_id))
    with db_connect() as con:
        issue = fetch_issue(con, issue_id)
        if issue is None:
            raise AppError("Issue not found", "404 Not Found")
        if issue["status"] != "open":
            raise AppError("Only open issues can be canceled")
        if issue["creator_username"] != username:
            raise AppError("Only the issue owner can cancel this issue", "403 Forbidden")
    body = f"""
<form method="post" action="issues.cgi">
<input type="hidden" name="action" value="cancel_submit">
<input type="hidden" name="id" value="{h(issue_id)}">
{hidden_return_to(return_to)}
<p><label>Cancel comment<br><textarea name="cancel_comment" autofocus></textarea></label></p>
{render_markdown_help_link()}
<p class="form-actions"><input type="submit" value="Cancel issue">{cancel_control(return_to)}</p>
</form>
"""
    send_headers()
    print(render_page("Cancel Issue", body, username))


def action_cancel_submit(form: cgi.FieldStorage, username: str) -> None:
    issue_id = require_id(form)
    comment = field_value(form, "cancel_comment", field_value(form, "comment_text", "")).strip() or DEFAULT_CLOSING_COMMENT
    with db_connect() as con:
        issue = fetch_issue(con, issue_id)
        if issue is None:
            raise AppError("Issue not found", "404 Not Found")
        if issue["status"] != "open":
            raise AppError("Only open issues can be canceled")
        if issue["creator_username"] != username:
            raise AppError("Only the issue owner can cancel this issue", "403 Forbidden")
        now = now_utc_sql()
        con.execute("UPDATE issues SET status = 'canceled', completed_at = ?, updated_at = ? WHERE id = ?", (now, now, issue_id))
        cur = con.execute(
            "INSERT INTO comments (issue_id, commenter_username, comment_text, created_at) VALUES (?, ?, ?, ?)",
            (issue_id, username, comment, now),
        )
        comment_id = int(cur.lastrowid)
        record_issue_history(con, issue_id, username, "canceled", "Canceled issue with comment", now, comment_id=comment_id)
        recipients = issue_participant_recipients(con, issue, exclude=username)
        con.commit()
    notify_issue_event(issue_id, username, recipients, "Issue canceled")
    redirect(action_url("view", id=issue_id), "302 Found")


def action_reopen(form: cgi.FieldStorage, username: str) -> None:
    issue_id = require_id(form)
    comment = field_value(form, "comment", field_value(form, "comment_text", "")).strip()
    if "comment" in form or "comment_text" in form:
        comment = comment or DEFAULT_CLOSING_COMMENT
    with db_connect() as con:
        issue = fetch_issue(con, issue_id)
        if issue is None:
            raise AppError("Issue not found", "404 Not Found")
        if not is_admin(username):
            raise AppError("Only a system administrator can re-open issues", "403 Forbidden")
        if issue["status"] in ISSUE_TERMINAL_STATUSES:
            now = now_utc_sql()
            con.execute("UPDATE issues SET status = 'open', completed_at = NULL, updated_at = ? WHERE id = ?", (now, issue_id))
            if comment:
                con.execute("INSERT INTO comments (issue_id, commenter_username, comment_text, created_at) VALUES (?, ?, ?, ?)", (issue_id, username, comment, now))
            record_issue_history(con, issue_id, username, "reopened", "Reopened issue", now)
            recipients = issue_participant_recipients(con, issue, exclude=username)
            con.commit()
            notify_issue_event(issue_id, username, recipients, "Issue reopened")
    redirect(action_url("view", id=issue_id))


def render_history_pagination_controls(issue_id: int, page: int, total_pages: int) -> str:
    previous_page = max(1, page - 1)
    next_page = min(total_pages, page + 1)
    previous_disabled = " disabled" if page <= 1 else ""
    next_disabled = " disabled" if page >= total_pages else ""
    page_options = []
    for number in range(1, total_pages + 1):
        selected = " selected" if number == page else ""
        page_options.append(f'<option value="{number}"{selected}>{number} of {total_pages}</option>')
    # REGRESSION GUARD: Match issue-list pagination by using one hidden page
    # control and button-based Previous/Next updates. This avoids
    # browser-dependent duplicate page submissions.
    return f'''<div class="pagination-controls" style="display:inline-flex;align-items:center;justify-content:flex-end;margin:0;white-space:nowrap;">
<form method="get" action="issues.cgi" style="display:inline-flex;align-items:center;gap:0.4rem;margin:0;white-space:nowrap;">
<input type="hidden" name="action" value="history"><input type="hidden" name="id" value="{h(issue_id)}"><input type="hidden" name="page" value="{h(page)}">
<button type="button" onclick="this.form.elements['page'].value='{previous_page}'; this.form.submit()"{previous_disabled}>Previous</button>
<select aria-label="Page" onchange="this.form.elements['page'].value=this.value; this.form.submit()">{''.join(page_options)}</select>
<button type="button" onclick="this.form.elements['page'].value='{next_page}'; this.form.submit()"{next_disabled}>Next</button>
</form>
</div>'''


def history_comment_excerpt(value: Any, max_words: int = 8, max_chars: int = 80) -> str:
    words = str(value or "").split()
    excerpt = " ".join(words[:max_words])
    if len(excerpt) > max_chars:
        excerpt = excerpt[:max_chars].rstrip()
    if len(words) > max_words or len(str(value or "")) > len(excerpt):
        excerpt = excerpt.rstrip(".,;:") + "..."
    return excerpt


def emphasize_quoted_history_values(summary: Any) -> str:
    # REGRESSION GUARD: Do not use regex here. A malformed regular
    # expression caused history pages to fail with "unterminated character
    # set" while rendering quoted old/new values. This parser safely escapes
    # all text and bolds only complete double-quoted spans.
    text = str(summary or "")
    pieces: list[str] = []
    quoted: list[str] = []
    in_quote = False

    for ch in text:
        if ch == '"':
            if in_quote:
                pieces.append(f'<strong>&quot;{h("".join(quoted))}&quot;</strong>')
                quoted = []
                in_quote = False
            else:
                in_quote = True
            continue
        if in_quote:
            quoted.append(ch)
        else:
            pieces.append(h(ch))

    if in_quote:
        pieces.append('&quot;' + h("".join(quoted)))

    return "".join(pieces)


def history_display_summary_html(row: sqlite3.Row) -> str:
    # REGRESSION GUARD: Keep the history page self-contained by folding
    # comment excerpts and attachment metadata into the Summary column instead
    # of reintroducing a separate Reference column.
    summary = emphasize_quoted_history_values(row["summary"])
    if row["comment_id"]:
        excerpt = history_comment_excerpt(row["comment_text"] if "comment_text" in row.keys() else "")
        if excerpt:
            summary += f": {h(excerpt)}"
    if row["attachment_id"]:
        filename = row["attachment_filename"]
        if filename:
            link = action_url("download", id=row["attachment_id"])
            summary += f': <a href="{h(link)}">{h(filename)}</a>'
    return summary


def history_change_summary(field: str, old_value: Any, new_value: Any) -> str:
    return (
        f'Changed {field} from "{history_summary_text(display_value(old_value))}" '
        f'to "{history_summary_text(display_value(new_value))}"'
    )


def history_user_change_summary(field: str, old_value: Any, new_value: Any) -> str:
    return (
        f'Changed {field} from "{history_summary_text(display_username(old_value))}" '
        f'to "{history_summary_text(display_username(new_value))}"'
    )


def action_history(form: cgi.FieldStorage, username: str) -> None:
    issue_id = require_id(form)
    with db_connect() as con:
        issue = require_issue_access(con, issue_id, username)
        total_entries = con.execute("SELECT COUNT(*) FROM issue_history WHERE issue_id = ?", (issue_id,)).fetchone()[0]
        total_pages = max(1, (total_entries + ISSUES_PER_PAGE - 1) // ISSUES_PER_PAGE)
        page = clamp_page(parse_page_number(form), total_pages)
        start = (page - 1) * ISSUES_PER_PAGE
        # REGRESSION GUARD: History display joins attachment metadata only. Do
        # not select attachments.content here; attachment BLOB data is used only
        # by the download action.
        rows = con.execute(
            """SELECT h.id, h.issue_id, h.actor_username, h.action, h.summary,
                      h.comment_id, h.attachment_id, h.created_at,
                      c.comment_text AS comment_text,
                      a.filename AS attachment_filename,
                      a.uploader_username AS attachment_uploader,
                      a.created_at AS attachment_created_at
               FROM issue_history h
               LEFT JOIN comments c ON c.id = h.comment_id
               LEFT JOIN attachments a ON a.id = h.attachment_id
               WHERE h.issue_id = ?
               ORDER BY h.created_at DESC, h.id DESC
               LIMIT ? OFFSET ?""",
            (issue_id, ISSUES_PER_PAGE, start),
        ).fetchall()

    pagination_top = render_history_pagination_controls(issue_id, page, total_pages)
    pagination_bottom = render_history_pagination_controls(issue_id, page, total_pages)
    table_rows = []
    for row in rows:
        table_rows.append(
            "<tr>"
            f"<td>{timestamp_html(row['created_at'])}</td>"
            f"<td>{h(display_username(row['actor_username']))}</td>"
            f"<td>{h(row['action'])}</td>"
            f"<td>{history_display_summary_html(row)}</td>"
            "</tr>"
        )
    if table_rows:
        entries = (
            "<table class='issue-history-table'><thead><tr>"
            "<th>When</th><th>Actor</th><th>Action</th><th>Summary</th>"
            "</tr></thead><tbody>" + "".join(table_rows) + "</tbody></table>"
        )
    else:
        entries = "<p>No history entries.</p>"
    body = f'''
<div class="actions">{render_action_button("view", "Back to issue", id=issue_id)}</div>
<h2>History for issue {h(issue_id)}: {h(issue['title'])}</h2>
<div class="list-control-row issue-history-top-controls"><div class="list-control-right" style="float:right;text-align:right;white-space:nowrap;">{pagination_top}</div></div>
{entries}
<div class="list-control-row issue-history-bottom-controls"><div class="list-control-right" style="float:right;text-align:right;white-space:nowrap;">{pagination_bottom}</div></div>
'''
    send_headers()
    print(render_page(f"Issue {issue_id} History", body, username))


def action_markdown_help(form: cgi.FieldStorage, username: str) -> None:
    # REGRESSION GUARD: Keep the unordered and ordered examples separated by
    # labeled paragraph blocks and blank lines so Markdown renderers do not fold
    # the numbered-list example into the preceding bulleted list.
    examples = """
# Heading

Use **bold**, *italic*, `inline code`, and ~~strikethrough~~.

**Unordered List:**

- Bulleted list item
- Another item

**Ordered List:**

1. Numbered item
2. Another numbered item

```python
print("fenced code block")
```

| Column | Value |
| --- | --- |
| Priority | high |

Footnote example.[^1]

[^1]: This is a footnote.
"""
    body = f"""
<p>This page shows supported Markdown syntax for issue descriptions, comments, closing comments, and cancel comments.</p>
<div class="markdown-body">{markdown_to_html(examples)}</div>
<h2>Raw Markdown example</h2>
<pre>{h(examples)}</pre>
<p class="notice">Raw Markdown is preserved in storage and rendered only for display.</p>
"""
    send_headers()
    print(render_page("Markdown Help", body, username))


def action_help(form: cgi.FieldStorage, username: str) -> None:
    return action_markdown_help(form, username)


def safe_auth_destination(value: str) -> str:
    raw = (value or "").strip() or AUTH_FORM_DEFAULT_LOCATION
    # REGRESSION GUARD: The login page may echo a destination into a hidden
    # field for Apache form-auth handling. Keep it relative and single-line so
    # it cannot become an open redirect target or inject attributes.
    lowered = raw.lower()
    parsed = urlsplit(raw)
    if "\r" in raw or "\n" in raw or parsed.scheme or lowered.startswith("//"):
        return AUTH_FORM_DEFAULT_LOCATION
    return raw


def is_public_auth_destination(candidate: str) -> bool:
    query = parse_qs(urlsplit(candidate).query, keep_blank_values=True)
    action_values = [value.strip() for value in query.get("action", [])]
    return any(value in PUBLIC_ACTIONS for value in action_values)


def login_destination_or_default(value: str) -> str:
    destination = safe_auth_destination(value)
    if is_public_auth_destination(destination):
        return AUTH_FORM_DEFAULT_LOCATION
    return destination


def field_first_present_value(form: cgi.FieldStorage, names: Iterable[str]) -> str:
    for name in names:
        if name in form:
            return field_value(form, name, "")
    return ""


def raw_query_parameter_remainder(name: str) -> str:
    raw_query = os.environ.get("QUERY_STRING", "")
    marker = f"{name}="
    for part in raw_query.split("&"):
        if part.startswith(marker):
            index = raw_query.find(marker)
            if index >= 0:
                return raw_query[index + len(marker):]
    return ""


def explicit_split_login_destination(form: cgi.FieldStorage) -> str:
    path = field_value(form, AUTH_FORM_LOCATION_PATH_FIELD, "").strip()
    if not path:
        return ""
    query = raw_query_parameter_remainder(AUTH_FORM_LOCATION_QUERY_FIELD)
    if not query and AUTH_FORM_LOCATION_QUERY_FIELD in form:
        query = field_value(form, AUTH_FORM_LOCATION_QUERY_FIELD, "").strip()
    destination = path + (f"?{query}" if query else "")
    return login_destination_or_default(destination)


def explicit_login_destination(form: cgi.FieldStorage) -> str:
    split_destination = explicit_split_login_destination(form)
    if split_destination:
        return split_destination
    raw_destination = field_first_present_value(form, (AUTH_FORM_LOCATION_FIELD,) + AUTH_FORM_LOCATION_ALIASES)
    return login_destination_or_default(raw_destination) if raw_destination else ""


def same_origin_referer_destination() -> str:
    referer = os.environ.get("HTTP_REFERER", "").strip()
    if not referer:
        return AUTH_FORM_DEFAULT_LOCATION
    parsed = urlsplit(referer)
    if parsed.scheme:
        request_host = (os.environ.get("HTTP_HOST") or os.environ.get("SERVER_NAME") or "").strip().lower()
        referer_host = parsed.netloc.lower()
        if not request_host or referer_host != request_host:
            return AUTH_FORM_DEFAULT_LOCATION
        candidate = parsed.path or AUTH_FORM_DEFAULT_LOCATION
        if parsed.query:
            candidate += "?" + parsed.query
    else:
        candidate = referer
    candidate = safe_auth_destination(candidate)
    if candidate != AUTH_FORM_DEFAULT_LOCATION and not is_public_auth_destination(candidate):
        return candidate
    return AUTH_FORM_DEFAULT_LOCATION


def request_auth_destination() -> str:
    redirect_url = os.environ.get("REDIRECT_URL", "").strip()
    if redirect_url:
        redirect_query = os.environ.get("REDIRECT_QUERY_STRING", "").strip()
        candidate = redirect_url + (f"?{redirect_query}" if redirect_query and "?" not in redirect_url else "")
        candidate = safe_auth_destination(candidate)
        if candidate != AUTH_FORM_DEFAULT_LOCATION and not is_public_auth_destination(candidate):
            return candidate

    request_uri = os.environ.get("REQUEST_URI", "").strip()
    if request_uri:
        candidate = safe_auth_destination(request_uri)
        if candidate != AUTH_FORM_DEFAULT_LOCATION and not is_public_auth_destination(candidate):
            return candidate

    referer_candidate = same_origin_referer_destination()
    if referer_candidate != AUTH_FORM_DEFAULT_LOCATION:
        return referer_candidate

    script_name = os.environ.get("SCRIPT_NAME", "").strip() or AUTH_FORM_DEFAULT_LOCATION
    query_string = os.environ.get("QUERY_STRING", "").strip()
    candidate = script_name + (f"?{query_string}" if query_string else "")
    candidate = safe_auth_destination(candidate)
    if is_public_auth_destination(candidate):
        return AUTH_FORM_DEFAULT_LOCATION
    return candidate


def action_login(form: cgi.FieldStorage, username: Optional[str] = None) -> None:
    destination = explicit_login_destination(form) or login_destination_or_default(request_auth_destination())
    body = f"""
<p>Please sign in.</p>
<div class="login-panel">
<form method="post" action="{h(AUTH_FORM_ACTION)}">
<input type="hidden" name="{h(AUTH_FORM_LOCATION_FIELD)}" value="{h(destination)}">
<p><label for="auth_username">Username</label><br>
<input type="text" id="auth_username" name="{h(AUTH_FORM_USERNAME_FIELD)}" autocomplete="username" autofocus></p>
<p><label for="auth_password">Password</label><br>
<input type="password" id="auth_password" name="{h(AUTH_FORM_PASSWORD_FIELD)}" autocomplete="current-password"></p>
<p class="form-actions"><button type="submit">Log in</button></p>
</form>
</div>
"""
    send_headers()
    print(render_page("Issues Login", body, None))


def action_login_failed(form: cgi.FieldStorage, username: Optional[str] = None) -> None:
    body = f"""
<p class="error">Login failed.</p>
<p><a href="{h(action_url('login'))}">Return to login</a></p>
"""
    send_headers(status="401 Unauthorized")
    print(render_page("Login Failed", body, None))


def action_logged_out(form: cgi.FieldStorage, username: Optional[str] = None) -> None:
    body = f"""
<p>You have been logged out.</p>
<p><a href="{h(action_url('login'))}">Log in</a></p>
"""
    send_headers()
    print(render_page("Logged Out", body, None))


def action_auth_error(form: cgi.FieldStorage, username: Optional[str] = None) -> None:
    body = f"""
<p class="error">The application could not accept the authenticated user.</p>
<p><a href="{h(action_url('login'))}">Return to login</a></p>
"""
    send_headers(status="403 Forbidden")
    print(render_page("Authentication Error", body, None))


def embedded_favicon_bytes() -> bytes:
    # REGRESSION GUARD: The embedded favicon payload is intentionally kept at
    # the end of the file so normal maintenance does not require scrolling past
    # a large Base64 block. Decode it only when the favicon action is requested.
    return base64.b64decode(EMBEDDED_FAVICON_BASE64)


def action_favicon(form: cgi.FieldStorage, username: Optional[str] = None) -> None:
    data = embedded_favicon_bytes()
    send_headers(
        FAVICON_MIME_TYPE,
        extra_headers=(
            ("Cache-Control", "public, max-age=86400"),
            ("Content-Length", str(len(data))),
        ),
    )
    sys.stdout.flush()
    sys.stdout.buffer.write(data)
    raise ResponseSent()

PUBLIC_ACTIONS = {"login", "login_failed", "logged_out", "auth_error", "favicon"}


ACTION_MAP = {
    "login": action_login,
    "login_failed": action_login_failed,
    "logged_out": action_logged_out,
    "auth_error": action_auth_error,
    "favicon": action_favicon,
    "list": action_list,
    "search_history_remove": action_search_history_remove,
    "search_history_clear": action_search_history_clear,
    "view": action_view,
    "history": action_history,
    "create_submit": action_create_submit,
    "assign": action_assign,
    "contributing_users_update": action_contributing_users_update,
    "attach_submit": action_attach_submit,
    "download": action_download,
    "comment_submit": action_comment_submit,
    "update_submit": action_update_submit,
    "set_priority": action_set_priority,
    "set_due_date": action_set_due_date,
    "set_percent_complete": action_set_percent_complete,
    "set_state": action_set_state,
    "close_submit": action_close_submit,
    "cancel_submit": action_cancel_submit,
    "reopen": action_reopen,
    "markdown_help": action_markdown_help,
    "help": action_help,
}


def default_action_for_request() -> str:
    """Return the implicit action for requests that omit the action parameter."""
    return "list" if os.environ.get("REMOTE_USER", "").strip() else "login"


def dispatch() -> None:
    # REGRESSION GUARD: Preserve blank submitted values such as search=.
    # cgi.FieldStorage drops blank query/form fields by default, which makes a
    # cleared Search field look absent and reloads the previously saved search.
    form = cgi.FieldStorage(keep_blank_values=True)
    # REQUIREMENTS: When action is omitted, authenticated requests default to
    # the issue list, while unauthenticated requests default to the public login
    # page. Explicit protected actions still require a valid REMOTE_USER.
    action = field_value(form, "action", default_action_for_request()).strip() or default_action_for_request()
    if not re.fullmatch(r"[A-Za-z0-9_]+", action):
        raise AppError("Invalid action", "400 Bad Request")

    handler = globals().get(f"action_{action}")
    if not callable(handler):
        handler = ACTION_MAP.get(action)
    if not callable(handler):
        raise AppError("Unknown action", "404 Not Found")

    if action in PUBLIC_ACTIONS:
        username = None
    else:
        raw_username = os.environ.get("REMOTE_USER", "").strip()
        if not raw_username:
            # BUGFIX: When the app itself receives an unauthenticated request
            # for a protected page, send the user through the public login page
            # with the requested URL embedded. Otherwise form authentication
            # falls back to its generic success URL after login.
            redirect(action_url("login", **{AUTH_FORM_LOCATION_FIELD: current_request_destination()}))
        username = get_current_user()
    handler(form, username)


def main() -> None:
    try:
        dispatch()
    except ResponseSent:
        return
    except AppError as exc:
        try:
            html_error(exc.message, exc.status)
        except ResponseSent:
            # REGRESSION GUARD: Expected application errors have already emitted
            # their CGI response and must not escape as Python tracebacks when
            # the script is executed as a subprocess.
            return
    except Exception:
        # Avoid exposing tracebacks to normal users, but show details in the web
        # server error log for administration.
        traceback.print_exc(file=sys.stderr)
        try:
            html_error("Internal server error", "500 Internal Server Error")
        except ResponseSent:
            return


# ---------------------------------------------------------------------------
# Embedded favicon payload
# ---------------------------------------------------------------------------
# REQUIREMENTS: Keep this large Base64 payload at the end of the file. It is
# intentionally separated from application logic so the single-file CGI script
# remains readable during maintenance.
EMBEDDED_FAVICON_BASE64 = """
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
"""

if __name__ == "__main__":
    main()
