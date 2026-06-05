# Copyright (C) 2026 David Redmond
# SPDX-License-Identifier: AGPL-3.0-only
#
"""
Shared pytest fixtures for the issues.cgi regression suite.

The suite is intentionally written to run without Apache, mod_ssl, a live CGI
server, production Unix users/groups, or the production SQLite database.
Place this tests/ directory next to issues.cgi, or set ISSUE_CGI_PATH to the
application file before running pytest.
"""

from __future__ import annotations

import contextlib
import datetime as _dt
import importlib.util
from importlib.machinery import SourceFileLoader
import io
import json
import os
import pathlib
import pwd
import grp
import sqlite3
import subprocess
import sys
import types
from dataclasses import dataclass
from typing import Any, Callable, Iterable, Dict, List, Optional, Tuple, Union

import pytest


REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
DEFAULT_APP_PATH = REPO_ROOT / "issues.cgi"


def app_path() -> pathlib.Path:
    return pathlib.Path(os.environ.get("ISSUE_CGI_PATH", DEFAULT_APP_PATH)).resolve()


@pytest.fixture(scope="session")
def issues_cgi_path() -> pathlib.Path:
    path = app_path()
    if not path.exists():
        pytest.skip(
            f"issues.cgi was not found at {path}. Place tests/ next to issues.cgi "
            "or set ISSUE_CGI_PATH=/path/to/issues.cgi."
        )
    return path


@pytest.fixture(scope="session")
def syntax_check(issues_cgi_path: pathlib.Path) -> pathlib.Path:
    result = subprocess.run(
        [sys.executable, "-m", "py_compile", str(issues_cgi_path)],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    return issues_cgi_path


@pytest.fixture()
def app(syntax_check: pathlib.Path, monkeypatch: pytest.MonkeyPatch):
    # Import each test with a fresh module name to avoid cross-test global state.
    module_name = f"issues_cgi_under_test_{os.getpid()}_{id(monkeypatch)}"
    loader = SourceFileLoader(module_name, str(syntax_check))
    spec = importlib.util.spec_from_loader(module_name, loader)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    loader.exec_module(module)
    yield module
    sys.modules.pop(module_name, None)


@pytest.fixture()
def temp_db(tmp_path: pathlib.Path) -> pathlib.Path:
    db = tmp_path / "issues-test.db"
    with sqlite3.connect(db) as con:
        con.executescript(
            """
            CREATE TABLE issues (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                description TEXT NOT NULL,
                creator_username TEXT NOT NULL,
                assigned_username TEXT,
                priority TEXT NOT NULL,
                pct_complete INTEGER NOT NULL,
                state TEXT NOT NULL,
                status TEXT NOT NULL,
                due_date TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                completed_at TEXT
            );

            CREATE TABLE comments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                issue_id INTEGER NOT NULL,
                commenter_username TEXT NOT NULL,
                comment_text TEXT NOT NULL,
                time_worked_minutes INTEGER,
                created_at TEXT NOT NULL
            );

            CREATE TABLE attachments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                issue_id INTEGER NOT NULL,
                filename TEXT NOT NULL,
                content BLOB NOT NULL,
                uploader_username TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE issue_contributing_users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                issue_id INTEGER NOT NULL,
                contributing_username TEXT NOT NULL,
                contributed_by_username TEXT NOT NULL,
                created_at TEXT NOT NULL,
                UNIQUE(issue_id, contributing_username)
            );

            CREATE TABLE issue_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                issue_id INTEGER NOT NULL,
                actor_username TEXT NOT NULL,
                action TEXT NOT NULL,
                summary TEXT NOT NULL,
                comment_id INTEGER,
                attachment_id INTEGER,
                created_at TEXT NOT NULL
            );

            CREATE INDEX idx_issue_history_issue_id_created_at
                ON issue_history(issue_id, created_at DESC, id DESC);

            CREATE INDEX idx_issue_contributing_users_issue_user
                ON issue_contributing_users(issue_id, contributing_username);
            """
        )
    return db


@pytest.fixture()
def temp_config_dir(tmp_path: pathlib.Path) -> pathlib.Path:
    path = tmp_path / "config"
    path.mkdir()
    return path


@dataclass(frozen=True)
class FakeUser:
    name: str
    uid: int
    gid: int


@pytest.fixture()
def fake_users() -> Dict[str, FakeUser]:
    return {
        "alice": FakeUser("alice", 1001, 2001),
        "bob": FakeUser("bob", 1002, 2001),
        "admin": FakeUser("admin", 1003, 2001),
        "mallory": FakeUser("mallory", 1004, 2004),
        "vwboot": FakeUser("vwboot", 1005, 2001),
    }


@pytest.fixture()
def fake_groups(fake_users: Dict[str, FakeUser]) -> Dict[str, Dict[str, Any]]:
    return {
        "users": {
            "gid": 2001,
            "members": ["alice", "bob", "admin", "vwboot"],
        },
        "wheel": {
            "gid": 2002,
            "members": ["admin"],
        },
    }


@pytest.fixture()
def patched_environment(
    app,
    monkeypatch: pytest.MonkeyPatch,
    temp_db: pathlib.Path,
    temp_config_dir: pathlib.Path,
    fake_users: Dict[str, FakeUser],
    fake_groups: Dict[str, Dict[str, Any]],
):
    def getpwnam(name: str):
        if name not in fake_users:
            raise KeyError(name)
        user = fake_users[name]
        return types.SimpleNamespace(
            pw_name=user.name,
            pw_passwd="x",
            pw_uid=user.uid,
            pw_gid=user.gid,
            pw_gecos=user.name,
            pw_dir=f"/home/{user.name}",
            pw_shell="/bin/bash",
        )

    def getpwall():
        return [getpwnam(name) for name in sorted(fake_users)]

    def getgrnam(name: str):
        if name not in fake_groups:
            raise KeyError(name)
        g = fake_groups[name]
        return types.SimpleNamespace(
            gr_name=name,
            gr_passwd="x",
            gr_gid=g["gid"],
            gr_mem=list(g["members"]),
        )

    def getgrouplist(user: str, primary_gid: int):
        gids = {primary_gid}
        for group in fake_groups.values():
            if user in group["members"]:
                gids.add(group["gid"])
        return list(gids)

    monkeypatch.setattr(pwd, "getpwnam", getpwnam)
    monkeypatch.setattr(pwd, "getpwall", getpwall)
    monkeypatch.setattr(grp, "getgrnam", getgrnam)
    monkeypatch.setattr(os, "getgrouplist", getgrouplist)

    # If the application imported these modules, patch those references too.
    for module_name, function_name, replacement in (
        ("pwd", "getpwnam", getpwnam),
        ("pwd", "getpwall", getpwall),
        ("grp", "getgrnam", getgrnam),
        ("os", "getgrouplist", getgrouplist),
    ):
        mod = getattr(app, module_name, None)
        if mod is not None and hasattr(mod, function_name):
            monkeypatch.setattr(mod, function_name, replacement, raising=False)

    values = {
        "DB_FILE": str(temp_db),
        "DEFAULT_CLOSING_COMMENT": "no comment provided",
        "ISSUES_VERSION": "1.0.0",
        "PER_USER_CONFIG_DIR": str(temp_config_dir),
        "ASSIGNEE_GROUP": "users",
        "ASSIGNEE_EXCLUDE": "vwboot",
        "ADMINS_GROUP": "wheel",
        "ADMINS_GROUP_EXCLUDE": "",
        "MAX_UPLOAD_BYTES": 1024 * 1024,
        "MAX_FILENAME_LEN": 255,
        "BANNER_FILE": "",
        "BANNER_DIMENSIONS": "",
        "AUTH_FORM_ACTION": "/login",
        "AUTH_FORM_USERNAME_FIELD": "httpd_username",
        "AUTH_FORM_PASSWORD_FIELD": "httpd_password",
        "AUTH_FORM_LOCATION_FIELD": "httpd_location",
        "AUTH_FORM_DEFAULT_LOCATION": "/cgi-bin/issues.cgi",
        "CONFIG_DEFAULTS": {
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
        },
        "EMAIL_NOTIFICATIONS_ENABLED": False,
        "SENDMAIL_PATH": "/usr/sbin/sendmail",
        "NOTIFICATION_FROM": "issues@localhost",
        "NOTIFICATION_SUBJECT_PREFIX": "[Issues]",
        "ISSUE_BASE_URL": "",
        "NOTIFICATION_TRIAGE_RECIPIENTS": "root",
        "NOTIFICATION_BODY_MAX_CHARS": 8192,
    }
    for name, value in values.items():
        monkeypatch.setattr(app, name, value, raising=False)

    return values


class Field:
    def __init__(self, value: Any = "", filename: Optional[str] = None, file_bytes: Optional[bytes] = None):
        self.value = value
        self.filename = filename
        self.file = io.BytesIO(file_bytes if file_bytes is not None else bytes(str(value), "utf-8"))

    def __bool__(self) -> bool:
        return bool(self.value) or bool(self.filename)


class SimpleForm:
    """Small cgi.FieldStorage-compatible object for direct handler tests."""

    def __init__(self, fields: Optional[Dict[str, Any]] = None):
        self._fields: Dict[str, Any] = {}
        for key, value in (fields or {}).items():
            if isinstance(value, Field):
                self._fields[key] = value
            elif isinstance(value, list):
                self._fields[key] = [v if isinstance(v, Field) else Field(v) for v in value]
            else:
                self._fields[key] = Field(value)

    def __contains__(self, key: str) -> bool:
        return key in self._fields

    def __getitem__(self, key: str) -> Any:
        return self._fields[key]

    def keys(self):
        return self._fields.keys()

    def getfirst(self, key: str, default: Any = None) -> Any:
        item = self._fields.get(key)
        if item is None:
            return default
        if isinstance(item, list):
            item = item[0] if item else None
        return getattr(item, "value", default)

    def getvalue(self, key: str, default: Any = None) -> Any:
        item = self._fields.get(key)
        if item is None:
            return default
        if isinstance(item, list):
            return [getattr(v, "value", v) for v in item]
        return getattr(item, "value", item)


@pytest.fixture()
def make_form():
    def _make_form(**fields: Any) -> SimpleForm:
        return SimpleForm(fields)
    return _make_form


def find_callable(app: Any, names: Iterable[str], required: bool = True) -> Optional[Callable[..., Any]]:
    for name in names:
        fn = getattr(app, name, None)
        if callable(fn):
            return fn
    if required:
        pytest.fail("Expected one of these callables to exist: " + ", ".join(names))
    return None




def html_text(value: Union[str, bytes]) -> str:
    """Return CGI response bodies as text for precise HTML assertions."""
    return value.decode("utf-8", "replace") if isinstance(value, bytes) else value


def html_has_control(html: str, name: str) -> bool:
    """Match an HTML form control by name without relying on nearby label text."""
    import re

    return re.search(r'\bname=["\']' + re.escape(name) + r'["\']', html, re.IGNORECASE) is not None


def html_has_option(html: str, value: str) -> bool:
    """Match an option value precisely enough for filter dropdown assertions."""
    import re

    return re.search(r'<option\b[^>]*\bvalue=["\']' + re.escape(value) + r'["\']', html, re.IGNORECASE) is not None


def html_select_option_values(html: str, name: str) -> List[str]:
    """Return option values from a named select, preserving their rendered order."""
    from html.parser import HTMLParser

    class SelectOptionParser(HTMLParser):
        def __init__(self) -> None:
            super().__init__()
            self.in_target_select = False
            self.depth = 0
            self.values: List[str] = []

        def handle_starttag(self, tag: str, attrs: List[Tuple[str, Optional[str]]]) -> None:
            attrs_dict = {key.lower(): value for key, value in attrs}
            if tag.lower() == "select" and attrs_dict.get("name") == name:
                self.in_target_select = True
                self.depth = 1
                return
            if self.in_target_select:
                self.depth += 1
                if tag.lower() == "option":
                    value = attrs_dict.get("value")
                    if value is not None:
                        self.values.append(value)

        def handle_endtag(self, tag: str) -> None:
            if self.in_target_select:
                self.depth -= 1
                if tag.lower() == "select" or self.depth <= 0:
                    self.in_target_select = False
                    self.depth = 0

    parser = SelectOptionParser()
    parser.feed(html)
    return parser.values


def assert_banner_uses_config(html: str, src: str = "", dimensions: str = "") -> None:
    """REGRESSION GUARD: rendered pages honor the configured optional top banner."""
    lower = html.lower()
    body_index = lower.find("<body")
    body_html = lower[body_index:] if body_index >= 0 else lower
    if not src:
        assert 'class="banner"' not in lower
        assert 'class="css-header"' in lower
        assert 'class="css-header-title">issues</div>' in lower
        assert "linear-gradient" in lower
        assert "35px" in lower
        assert "#e6e9ef" in lower
        assert "#bfc5d0" in lower
        assert "-0.75rem -0.75rem 1rem -0.75rem" in lower
        return
    assert src.lower() in lower
    assert 'class="css-header"' not in lower
    if dimensions:
        width, height = dimensions.lower().split("x", 1)
        assert f'width="{width}"' in lower or f"width='{width}'" in lower or f"width: {width}" in lower or f"width:{width}" in lower
        assert f'height="{height}"' in lower or f"height='{height}'" in lower or f"height: {height}" in lower or f"height:{height}" in lower
    banner_index = body_html.find(src.lower())
    first_heading_index = min([i for i in [body_html.find("<h1"), body_html.find("<h2"), body_html.find("<h3")] if i >= 0] or [len(body_html)])
    assert banner_index >= 0 and banner_index < first_heading_index

def call_flex(fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
    """Call a project function while tolerating common CGI helper signatures."""
    import inspect

    sig = inspect.signature(fn)
    params = sig.parameters
    if any(p.kind == p.VAR_KEYWORD for p in params.values()):
        return fn(*args, **kwargs)
    allowed = {k: v for k, v in kwargs.items() if k in params}
    try:
        return fn(*args, **allowed)
    except TypeError:
        if args:
            return fn(*args)
        return fn(**allowed)


@pytest.fixture()
def parse_headers():
    def _parse(output: Union[str, bytes]):
        if isinstance(output, bytes):
            header_blob, _, body = output.partition(b"\r\n\r\n")
            if not body:
                header_blob, _, body = output.partition(b"\n\n")
            header_text = header_blob.decode("iso-8859-1", errors="replace")
            body_value: Union[str, bytes] = body
        else:
            header_blob, sep, body = output.partition("\r\n\r\n")
            if not sep:
                header_blob, _, body = output.partition("\n\n")
            header_text = header_blob
            body_value = body
        headers: Dict[str, str] = {}
        status = ""
        for line in header_text.splitlines():
            if not line.strip():
                continue
            if ":" in line:
                key, value = line.split(":", 1)
                headers[key.strip().lower()] = value.strip()
                if key.lower() == "status":
                    status = value.strip()
        return status, headers, body_value
    return _parse


class CapturedCgiStdout:
    """Capture CGI output written through both sys.stdout.write and sys.stdout.buffer.write."""

    def __init__(self) -> None:
        self._data = bytearray()
        self.buffer = self

    def write(self, value: Union[str, bytes]) -> int:
        if isinstance(value, bytes):
            data = value
        else:
            data = value.encode("utf-8")
        self._data.extend(data)
        return len(value)

    def flush(self) -> None:
        pass

    def getvalue(self) -> bytes:
        return bytes(self._data)


@pytest.fixture()
def invoke_action(monkeypatch: pytest.MonkeyPatch):
    def _invoke(
        app: Any,
        action: Optional[str] = "list",
        form: Optional[SimpleForm] = None,
        user: Optional[str] = "alice",
        method: str = "GET",
        query_string: Optional[str] = None,
    ) -> bytes:
        if form is None:
            form = SimpleForm({"action": action} if action is not None else {})
        if action is not None and "action" not in form:
            form._fields["action"] = Field(action)
        default_query = f"action={action}" if method == "GET" and action is not None else ""
        env = {
            "REQUEST_METHOD": method,
            "QUERY_STRING": default_query if query_string is None else query_string,
            "REMOTE_USER": user or "",
            "CONTENT_TYPE": "application/x-www-form-urlencoded",
            "CONTENT_LENGTH": "0",
            "SERVER_NAME": "localhost",
            "SERVER_PORT": "443",
            "SERVER_PROTOCOL": "HTTP/1.1",
            "GATEWAY_INTERFACE": "CGI/1.1",
            "SCRIPT_NAME": "/issues.cgi",
        }
        for key, value in env.items():
            if value == "" and key == "REMOTE_USER" and user is None:
                monkeypatch.delenv(key, raising=False)
            else:
                monkeypatch.setenv(key, value)

        # Replace FieldStorage in the common locations the application may use.
        if getattr(app, "cgi", None) is not None and hasattr(app.cgi, "FieldStorage"):
            monkeypatch.setattr(app.cgi, "FieldStorage", lambda *a, **k: form, raising=False)
        if hasattr(app, "FieldStorage"):
            monkeypatch.setattr(app, "FieldStorage", lambda *a, **k: form, raising=False)

        out = CapturedCgiStdout()
        with contextlib.redirect_stdout(out):
            main = find_callable(app, ["main", "cgi_main", "dispatch"], required=False)
            try:
                if main is not None:
                    call_flex(main)
                else:
                    handler = find_callable(app, [f"action_{action}", f"handle_{action}", f"do_{action}"])
                    call_flex(handler, form, user=user, username=user, current_user=user)
            except BaseException as exc:
                # Some CGI applications print the full response and then raise
                # a private ResponseSent/SystemExit-style sentinel to stop
                # further processing. Treat that as successful output capture.
                if exc.__class__.__name__ not in {"ResponseSent", "SystemExit"}:
                    raise
        return out.getvalue()
    return _invoke


@pytest.fixture()
def seed_issue(temp_db: pathlib.Path):
    def _seed_issue(**overrides: Any) -> int:
        now = _dt.datetime(2026, 1, 1, 12, 0, 0).isoformat(timespec="seconds")
        row = {
            "title": "Seed issue",
            "description": "Seed description",
            "creator_username": "alice",
            "assigned_username": "bob",
            "priority": "normal",
            "pct_complete": 0,
            "state": "not started",
            "status": "open",
            "due_date": None,
            "created_at": now,
            "updated_at": now,
            "completed_at": None,
        }
        row.update(overrides)
        with sqlite3.connect(temp_db) as con:
            cur = con.execute(
                """
                INSERT INTO issues
                (title, description, creator_username, assigned_username, priority,
                 pct_complete, state, status, due_date, created_at, updated_at, completed_at)
                VALUES
                (:title, :description, :creator_username, :assigned_username, :priority,
                 :pct_complete, :state, :status, :due_date, :created_at, :updated_at, :completed_at)
                """,
                row,
            )
            return int(cur.lastrowid)
    return _seed_issue


@pytest.fixture()
def seed_comment(temp_db: pathlib.Path):
    def _seed_comment(issue_id: int, text: str = "comment", user: str = "alice", created_at: str = "2026-01-01T12:00:00", time_worked_minutes: Optional[int] = None) -> int:
        with sqlite3.connect(temp_db) as con:
            cur = con.execute(
                "INSERT INTO comments (issue_id, commenter_username, comment_text, time_worked_minutes, created_at) VALUES (?, ?, ?, ?, ?)",
                (issue_id, user, text, time_worked_minutes, created_at),
            )
            return int(cur.lastrowid)
    return _seed_comment


@pytest.fixture()
def seed_attachment(temp_db: pathlib.Path):
    def _seed_attachment(issue_id: int, filename: str = "note.txt", content: bytes = b"content", user: str = "alice", created_at: str = "2026-01-01T12:00:00") -> int:
        with sqlite3.connect(temp_db) as con:
            cur = con.execute(
                "INSERT INTO attachments (issue_id, filename, content, uploader_username, created_at) VALUES (?, ?, ?, ?, ?)",
                (issue_id, filename, content, user, created_at),
            )
            return int(cur.lastrowid)
    return _seed_attachment


@pytest.fixture()
def seed_contributing_user(temp_db: pathlib.Path):
    def _seed_contributing_user(issue_id: int, contributing_username: str = "mallory", contributed_by_username: str = "alice", created_at: str = "2026-01-01T12:00:00") -> int:
        with sqlite3.connect(temp_db) as con:
            cur = con.execute(
                "INSERT INTO issue_contributing_users (issue_id, contributing_username, contributed_by_username, created_at) VALUES (?, ?, ?, ?)",
                (issue_id, contributing_username, contributed_by_username, created_at),
            )
            return int(cur.lastrowid)
    return _seed_contributing_user


@pytest.fixture()
def fetch_contributing_users(temp_db: pathlib.Path):
    def _fetch(issue_id: int) -> List[sqlite3.Row]:
        con = sqlite3.connect(temp_db)
        con.row_factory = sqlite3.Row
        with con:
            return con.execute("SELECT * FROM issue_contributing_users WHERE issue_id = ? ORDER BY contributing_username", (issue_id,)).fetchall()
    return _fetch


@pytest.fixture()
def fetch_issue(temp_db: pathlib.Path):
    def _fetch(issue_id: int) -> Optional[sqlite3.Row]:
        con = sqlite3.connect(temp_db)
        con.row_factory = sqlite3.Row
        with con:
            return con.execute("SELECT * FROM issues WHERE id = ?", (issue_id,)).fetchone()
    return _fetch


@pytest.fixture()
def fetch_comments(temp_db: pathlib.Path):
    def _fetch(issue_id: int) -> List[sqlite3.Row]:
        con = sqlite3.connect(temp_db)
        con.row_factory = sqlite3.Row
        with con:
            return con.execute("SELECT * FROM comments WHERE issue_id = ? ORDER BY created_at DESC", (issue_id,)).fetchall()
    return _fetch


@pytest.fixture()
def fetch_attachments(temp_db: pathlib.Path):
    def _fetch(issue_id: int) -> List[sqlite3.Row]:
        con = sqlite3.connect(temp_db)
        con.row_factory = sqlite3.Row
        with con:
            return con.execute("SELECT * FROM attachments WHERE issue_id = ? ORDER BY created_at ASC", (issue_id,)).fetchall()
    return _fetch




@pytest.fixture()
def fetch_history(temp_db: pathlib.Path):
    def _fetch(issue_id: int) -> List[sqlite3.Row]:
        con = sqlite3.connect(temp_db)
        con.row_factory = sqlite3.Row
        with con:
            return con.execute(
                "SELECT * FROM issue_history WHERE issue_id = ? ORDER BY created_at DESC, id DESC",
                (issue_id,),
            ).fetchall()
    return _fetch

@pytest.fixture()
def write_config(temp_config_dir: pathlib.Path):
    def _write(username: str, data: Dict[str, Any]) -> pathlib.Path:
        path = temp_config_dir / f"{username}.json"
        path.write_text(json.dumps(data), encoding="utf-8")
        return path
    return _write


@pytest.fixture()
def body_text(parse_headers):
    def _body_text(output: Union[str, bytes]) -> str:
        _status, _headers, body = parse_headers(output)
        if isinstance(body, bytes):
            return body.decode("utf-8", "replace")
        return body
    return _body_text


@pytest.fixture()
def assert_output_contains_required_fragments(body_text):
    def _assert(output: Union[str, bytes], fragments: Iterable[str]) -> None:
        body = body_text(output)
        missing = [fragment for fragment in fragments if fragment not in body]
        assert not missing, "Missing expected fragments: " + ", ".join(missing)
    return _assert


@pytest.fixture()
def assert_output_does_not_contain_forbidden_fragments(body_text):
    def _assert(output: Union[str, bytes], fragments: Iterable[str]) -> None:
        body = body_text(output)
        present = [fragment for fragment in fragments if fragment in body]
        assert not present, "Found forbidden fragments: " + ", ".join(present)
    return _assert
