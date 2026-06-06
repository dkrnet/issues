# Issues CGI Application

`issues.cgi` is a single-file Python CGI issue tracker backed by SQLite. It provides a browser interface for creating, viewing, updating, assigning, commenting on, attaching files to, closing, canceling, and reopening issues.

The application is intended for deployment behind Apache authentication. Apache authenticates the user and passes the username:q to the CGI script through `REMOTE_USER`.

## Intended use

This application is intended for small networks, internal workgroups, and air-gapped or isolated environments that need lightweight issue tracking without deploying a larger issue-tracking platform.

It is designed to be simple to host on an existing Apache/Python/SQLite system, with minimal moving parts and no requirement for external cloud services. It can be useful where a full-featured ticketing system would be too large, too complex, unavailable, or inappropriate for the environment.

The application is not intended to replace enterprise issue-tracking systems for large organizations, complex workflows, public customer support, or heavily integrated development processes.

## Main features

- SQLite-backed issue tracking
- Single-file CGI deployment
- Apache-authenticated users through `REMOTE_USER`
- Role-aware access control based on issue creator, assignee, contributing participants, and administrator group membership
- Issue creation, editing, assignment, closing, canceling, and reopening
- Compact issue history for material actions taken on issues
- Optional local notification email through a sendmail-compatible command
- Comments with Markdown rendering and optional time-worked entries
- File attachments stored in the database
- Issue-list search, filtering, sorting, pagination, and auto-refresh
- Per-user saved list preferences
- Form cancel controls for returning to the previous page without submitting changes
- Browser-local timestamp display
- Public login, login-failed, logged-out, and authentication-error support pages for form-based authentication
- Embedded favicon served by the CGI script
- Optional site configuration through `/etc/issues.conf`
- Pytest regression test suite

## Runtime requirements

Use Python 3.9 through Python 3.12.

Do not use Python 3.13 unless the application has been updated to remove its dependency on the standard-library `cgi` module, which was removed in Python 3.13.

The optional `markdown` package enables fuller Markdown rendering behavior:

```bash
python3 -m pip install markdown
```

Without the package, the application uses its built-in fallback renderer.

Optional notification email requires a local sendmail-compatible command, such as the one commonly provided by Postfix, Sendmail, Exim, or OpenSMTPD. Notification email is disabled unless `EMAIL_NOTIFICATIONS_ENABLED` is set to a true value in `/etc/issues.conf`.

## Default paths

The built-in defaults are:

```text
DB_FILE=/var/lib/issues/issues.db
PER_USER_CONFIG_DIR=/var/lib/issues/config
```

The application can override selected deployment values from:

```text
/etc/issues.conf
```

If `/etc/issues.conf` does not exist, or if a value is omitted, the built-in default is used.

## Optional `/etc/issues.conf`

The site configuration file uses simple `KEY=value` lines. Lines beginning with `#` are comments. Inline `#` comments are ignored. Unknown keys are ignored.

Supported keys include:

```text
DB_FILE
PER_USER_CONFIG_DIR
ASSIGNEE_GROUP
ASSIGNEE_EXCLUDE
ADMINS_GROUP
ADMINS_GROUP_EXCLUDE
BANNER_FILE
BANNER_DIMENSIONS
MAX_UPLOAD_BYTES
MAX_FILENAME_LEN
DEFAULT_CLOSING_COMMENT
EMAIL_NOTIFICATIONS_ENABLED
SENDMAIL_PATH
NOTIFICATION_FROM
NOTIFICATION_SUBJECT_PREFIX
ISSUE_BASE_URL
NOTIFICATION_TRIAGE_RECIPIENTS
NOTIFICATION_BODY_MAX_CHARS
```

Example:

```ini
# /etc/issues.conf

DB_FILE=/var/lib/issues/issues.db
PER_USER_CONFIG_DIR=/var/lib/issues/config

ASSIGNEE_GROUP=users
ASSIGNEE_EXCLUDE=

ADMINS_GROUP=wheel
ADMINS_GROUP_EXCLUDE=

BANNER_FILE=
BANNER_DIMENSIONS=

MAX_UPLOAD_BYTES=10485760
MAX_FILENAME_LEN=255
DEFAULT_CLOSING_COMMENT=no comment provided

EMAIL_NOTIFICATIONS_ENABLED=False
SENDMAIL_PATH=/usr/sbin/sendmail
NOTIFICATION_FROM=issues@localhost
NOTIFICATION_SUBJECT_PREFIX=[Issues]
ISSUE_BASE_URL=
NOTIFICATION_TRIAGE_RECIPIENTS=root
NOTIFICATION_BODY_MAX_CHARS=8192
```

## Database

The application expects an existing SQLite database at `DB_FILE`.

Required tables:

- `issues`
- `comments`
- `attachments`
- `issue_contributing_users`
- `issue_history`

The schema is described in detail in `requirements.md`.

To create and initialize the default database file:

```bash
sudo mkdir -p /var/lib/issues /var/lib/issues/config
sudo sqlite3 /var/lib/issues/issues.db <<'SQL'
CREATE TABLE IF NOT EXISTS issues (
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

CREATE TABLE IF NOT EXISTS comments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    issue_id INTEGER NOT NULL,
    commenter_username TEXT NOT NULL,
    comment_text TEXT NOT NULL,
    time_worked_minutes INTEGER,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS attachments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    issue_id INTEGER NOT NULL,
    filename TEXT NOT NULL,
    content BLOB NOT NULL,
    uploader_username TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS issue_contributing_users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    issue_id INTEGER NOT NULL,
    contributing_username TEXT NOT NULL,
    contributed_by_username TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(issue_id, contributing_username)
);

CREATE TABLE IF NOT EXISTS issue_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    issue_id INTEGER NOT NULL,
    actor_username TEXT NOT NULL,
    action TEXT NOT NULL,
    summary TEXT NOT NULL,
    comment_id INTEGER,
    attachment_id INTEGER,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_comments_issue_id ON comments(issue_id);
CREATE INDEX IF NOT EXISTS idx_attachments_issue_id ON attachments(issue_id);
CREATE INDEX IF NOT EXISTS idx_issue_contributing_users_issue_user
    ON issue_contributing_users(issue_id, contributing_username);
CREATE INDEX IF NOT EXISTS idx_issue_history_issue_id_created_at
    ON issue_history(issue_id, created_at DESC, id DESC);
SQL
```

To add time-worked support to an existing database created before that column existed:

```bash
sudo sqlite3 /var/lib/issues/issues.db \
  "ALTER TABLE comments ADD COLUMN time_worked_minutes INTEGER;"
```

After creating the database, ensure the Apache runtime user can read and write the database file, the database journal/WAL files created beside it, and the per-user configuration directory. The exact ownership and permissions depend on the site’s Apache configuration and security policy.


## Authentication model

The application expects Apache to authenticate users and set:

```text
REMOTE_USER
```

Protected issue-tracking actions require a valid authenticated user.

The application also includes public display-only authentication support pages:

```text
/cgi-bin/issues.cgi?action=login
/cgi-bin/issues.cgi?action=login_failed
/cgi-bin/issues.cgi?action=logged_out
/cgi-bin/issues.cgi?action=auth_error
```

When no `action` parameter is supplied:

- if `REMOTE_USER` is missing, the default action is `login`
- if `REMOTE_USER` is present, the default action is `list`

Authenticated pages display the current user and a logout link:

```text
Welcome, username (Logout)
```

User-facing name displays prefer the user's full name from the system account record. If a full name is unavailable, empty, or only one word with no whitespace, the login name is displayed. Stored issue ownership, assignment, contributing-user membership, preferences, and notification recipients continue to use login names.

The logout link points to the configured logout URL, currently:

```text
/issues-logout
```

The login form default destination is:

```text
/cgi-bin/issues.cgi
```

When a protected page is requested before authentication, the application redirects to the login page with the safe originally requested application URL embedded as the post-login destination. If the web server redirects to the login page before the application sees the protected request, configure the login URL to include the full original safe application URL, including its query string, as `httpd_location`, `next`, or `return_to`; the login page copies that value into the hidden form-authentication destination field. If the web-server configuration cannot URL encode the full destination, pass the path and raw query string separately as `next_path` and `next_query`, for example `/cgi-bin/issues.cgi?action=login&next_path=%{REQUEST_URI}&next_query=%{QUERY_STRING}`. Unsafe external or scheme-based destinations fall back to `/cgi-bin/issues.cgi`.

When no banner image is configured, the application renders a 35-pixel CSS header with half-page-margin top and side spacing, `Issues` over a `#E6E9EF`-to-transparent gradient, and `#BFC5D0` header text. A non-empty internal `ISSUES_VERSION` value adds a small centered version footer to authenticated pages only; unauthenticated public pages do not display the version number.

The source default application version is `1.0.0`. Run `./build.sh` from the repository to stamp a development-branch build as `1.0.0-dev.N+GITID`, where `N` is the number of commits after the matching release tag and `GITID` is an abbreviated current local Git `HEAD` commit ID. Run `./build.sh --release` to stamp a release build as `1.0.0+GITID`.

## Issue list

The issue list shows issues in descending ID order and includes search, filtering, pagination, and auto-refresh.

The current list column order is:

```text
ID, Title, Status, Due, Priority, Creator, Assignee, State, % Complete, Comments, Attachments, Updated
```

The issue view and issue forms use the same user-facing label, `Assignee`, for the assigned-user field.

The filters are organized into two groups:

### Static filter group

- Status
- Due
- Has comments
- Has attachments
- Search

### Dynamic filter group

- Priority
- Creator, for administrators only
- Assignee
- State

The Search field appears on the right side of the Static filter row when screen width allows. Its width grows and shrinks with the browser window up to a reasonable maximum. Pressing Enter in the Search field applies the search; clearing the field and pressing Enter clears the active search.

Initial issue-list loads do not automatically reapply the user's last search term. Pagination and automatic list refresh preserve the currently active search value through the current list URL. The magnifying-glass control inside the Search field opens a search-history pane containing the user's last 10 non-empty searches, newest first. Selecting a history entry applies that search and promotes it to the top of the history. History entries are rendered as clickable text controls rather than hyperlinks, and the text area changes to very light grey on hover across the available row width. Each history entry includes a darker but unobtrusive delete control, and the bottom of the pane includes a clear-history button.

Search matches issue title, issue description, comment text, and attachment metadata such as filename, uploader username, and attachment creation timestamp. Attachment file content is not searched.

The Dynamic filter options are generated from rows matching the current Static filter settings, including Search.

Pagination appears above and below the issue list. Each page shows at most 25 issues.

The auto-refresh control appears below the list. The last-refreshed indicator appears beside it and updates once per minute, for example:

```text
(Last refreshed: 2 minutes ago)
```

## Issue workflow

Issues can be:

- open
- closed
- canceled

Open issues can be updated according to user role and issue relationship. Contributing users can view, comment on, and attach files to open issues, but do not receive edit, assignment, close, cancel, reopen, priority, due-date, state, or percent-complete permissions unless another role grants them. Closed and canceled issues are read-only except for administrator actions allowed by the application requirements.

Issue creators, assigned users, and administrators manage contributing users with a dual listbox. Available contributing-user candidates appear on the left, current contributing users appear on the right, and selected users move between the boxes with the controls between them. The creator and assigned user are excluded from both contributing-user boxes.

Closing an issue sets its state to `complete` and its percent complete to `100`.

Canceled issues are marked completed but remain distinguishable from closed issues.

## Issue history

The application records compact history entries for material actions taken on issues, such as creating an issue, assigning it, changing priority, changing due date, changing state, changing percent complete, updating title or description, adding comments, adding attachments, closing, canceling, and reopening.

History is stored separately from the main issue record. Entries contain a concise action summary, the acting user, and the time of the action. They do not store full issue snapshots, full description changes, full comment text, or attachment file content.

Comment history entries reference the related comment id. Attachment history entries reference the related attachment id and display only attachment metadata, such as the filename, not the stored file content.

History is available from the issue view through the issue history page. The issue list does not load or display history. The history page uses the same general pagination style as the issue list, with 25 entries per page and Previous / page dropdown / Next controls.

Successful notification-email submissions are also recorded as compact history entries. These entries identify the recipient or recipients, but do not store the email body, subject line, full headers, SMTP transcript, delivery status details, or attachment contents.

## Notification email

Notification email support is optional and disabled by default. When enabled, the application submits plain-text notification messages to a local sendmail-compatible command such as `/usr/sbin/sendmail`. The local mail system is responsible for deciding whether messages are delivered locally or relayed through other mail infrastructure.

The application does not connect directly to a remote SMTP server and does not store SMTP credentials.

Notification settings can be configured in `/etc/issues.conf`:

```ini
EMAIL_NOTIFICATIONS_ENABLED=False
SENDMAIL_PATH=/usr/sbin/sendmail
NOTIFICATION_FROM=issues@localhost
NOTIFICATION_SUBJECT_PREFIX=[Issues]
ISSUE_BASE_URL=
NOTIFICATION_TRIAGE_RECIPIENTS=root
NOTIFICATION_BODY_MAX_CHARS=8192
```

When enabled, notifications are sent for assignment or reassignment, contributing-user changes, comments, issue close, issue reopen, and due-date changes. Assignment and reassignment notify the newly assigned user. Reassignment from one user to another also notifies the previously assigned user, unless the previously assigned user is the actor who made the change. Contributing users receive the same issue-activity notifications as issue creators. Ordinary page views, list filtering, pagination, auto-refresh, history page views, and attachment downloads do not send notification email.

For unassigned issues, notification-triggering actions use `NOTIFICATION_TRIAGE_RECIPIENTS` when there would otherwise be no non-actor recipient. The default triage recipient is `root`.

`NOTIFICATION_TRIAGE_RECIPIENTS` may contain a comma-separated mix of local recipient names and group references. Items beginning with `@` are treated as system group names and expanded through the same system name-service/group lookup used by Python; the application does not manually read `/etc/group`. For example:

```ini
NOTIFICATION_TRIAGE_RECIPIENTS=root,helpdesk,@it_triage
```

This resolves to `root`, `helpdesk`, and the members of the `it_triage` group, with duplicates removed. The actor is still excluded from the final recipient list. On systems where SSSD/LDAP group enumeration is restricted, explicit recipient names may be more reliable than `@group` expansion.

Notification bodies include useful context for selected actions. Comment notifications include the comment text. Attachment notifications include attachment metadata such as filename, uploader, timestamp, and size, but do not include or attach the file content. Title/description update notifications include the updated title and updated description. Long text included in notification bodies is capped by `NOTIFICATION_BODY_MAX_CHARS`, which defaults to `8192` characters.

Notification failures are logged server-side and do not roll back or block the issue action that triggered the notification.

## Comments and Markdown

Issue descriptions and comments support Markdown rendering.

Comment forms include an optional **Time worked** field. Values default to hours when no unit is provided and may use minutes, hours, or days. Compact examples include `30m`, `1.5h`, and `1d`. Saved time-worked values are submitted work-time entries and appear in compact comment metadata, such as `Time worked: 2 hours, 30 minutes (work time)`, and the issue view displays the total time worked for the issue as submitted work time.

The issue view also shows `Time in current state` for open issues as wall-clock elapsed time, with the parenthetical `(wall clock)`. The two displays are intentionally distinct.

The Markdown help page is available from Markdown-enabled forms. It includes examples for:

- headings and emphasis
- bulleted lists
- numbered lists
- fenced code
- tables
- footnotes
- GitLab-style strikethrough using `~~text~~`

Raw Markdown is stored in the database and rendered only for display.

## Attachments

Users with permission to view and participate in an issue can attach files.

Attachment filenames are normalized and constrained for safety. Uploaded file size is limited by `MAX_UPLOAD_BYTES`.

## Embedded favicon

The application serves its favicon from the CGI script through:

```text
/cgi-bin/issues.cgi?action=favicon
```

The favicon data is embedded in `issues.cgi`, preserving the single-file deployment model.

## Installation overview

A typical deployment requires:

1. Copy `issues.cgi` to the Apache CGI directory, such as `/var/www/cgi-bin/issues.cgi`.
2. Make the script executable.
3. Create writable application data directories, such as `/var/lib/issues` and `/var/lib/issues/config`.
4. Create the SQLite database using the required schema.
5. Configure Apache authentication so protected requests set `REMOTE_USER`.
6. Optionally create `/etc/issues.conf` to override site-specific settings.
7. If notification email will be used, configure and test the local mail system and sendmail-compatible command.
8. Verify the application loads at `/cgi-bin/issues.cgi`.

Example permissions vary by site policy, but the Apache runtime user must be able to read/write the database and per-user configuration directory.

## Regression tests

The project includes a pytest-based regression suite under `tests/`.

Install pytest:

```bash
python3 -m pip install pytest
```

Run the tests from the directory containing `issues.cgi` and `tests/`:

```bash
python3 -m py_compile issues.cgi tests/*.py
python3 -m pytest -q
```

If the CGI script is in another location, set:

```bash
ISSUE_CGI_PATH=/path/to/issues.cgi python3 -m pytest -q
```

The tests use a temporary database, temporary configuration directory, and fake users/groups. They do not use the production database or production configuration files.

## Requirements documents

`requirements.md` is the authoritative application requirements document.

`regression_testing_requirements.md` describes the expected regression test coverage.
