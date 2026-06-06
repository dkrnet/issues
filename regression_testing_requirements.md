# Regression Testing Requirements

**Issues Regression Tests** is the regression test suite for the `issues.cgi` CGI-based issue tracker application. The purpose of the test suite is to detect unintended feature removal, accidental permission changes, validation regressions, database behavior changes, UI-control regressions, and security-sensitive behavior changes during future maintenance.

# Implementation Language Requirement

- The regression tests shall be written in Python.
- The regression tests shall use `pytest` as the primary test framework.
- The regression tests shall run without requiring Apache, mod_ssl, or a live CGI deployment.
- The regression tests shall run against temporary test data, not against the production issue database.

# Test Suite Goals

- Verify that `issues.cgi` continues to satisfy the application requirements.
- Verify that user authentication and authorization behavior remains stable.
- Verify that database writes and reads remain correct.
- Verify that user-visible HTML contains required controls, forms, links, and sections.
- Verify that form cancel controls navigate to safe previous-page destinations without submitting data.
- Verify that unauthorized UI controls are not displayed to unauthorized users.
- Verify that protected CGI actions enforce authorization even when called directly.
- Verify that validation failures are rejected safely.
- Verify that attachment handling remains safe.
- Verify that Markdown storage and rendering behavior remains safe.
- Verify that future edits do not accidentally remove existing functionality.
- Verify that the embedded favicon remains available without an external file.
- Verify that compact issue history is recorded and displayed without unnecessary database growth or unnecessary list-page processing.
- Verify that optional notification email is submitted through the local mail system only when enabled and that notification attempts are recorded compactly in issue history.


# Requirements Authority and Traceability

- The application `requirements.md` is the authoritative source for expected application behavior.
- The regression testing requirements describe how that behavior shall be protected by tests; they do not replace or supersede the application requirements.
- Tests shall be written against the documented requirements, not merely against accidental behavior observed in the current implementation.
- If `issues.cgi` behavior and `requirements.md` disagree, the test author shall flag the mismatch rather than silently encoding the implementation behavior as correct.
- Each focused test module should map back to one or more sections of `requirements.md` so future maintainers can understand which requirement is being protected.
- When test expectations depend on phrases such as "according to application behavior" or "unless the implementation requirements explicitly permit it," the test author shall resolve the expectation by reading the current `requirements.md`.

## Recommended Requirement-to-Test Mapping

- `test_auth.py` should map to access and authentication requirements.
- `test_routing.py` should map to CGI routing, action dispatch, public authentication support actions, and error response requirements.
- `test_permissions.py` should map to issue visibility, role-specific UI controls, and backend authorization requirements.
- `test_issue_lifecycle.py` should map to create, update, assign, close, cancel, reopen, and issue-history requirements.
- `test_comments.py` should map to comment form, comment submission, comment ordering, and Markdown comment requirements.
- `test_attachments.py` should map to attachment upload, filename safety, download behavior, and attachment authorization requirements.
- `test_preferences.py` should map to per-user configuration loading, saving, validation, Static and Dynamic list filters, and administrator creator-filter behavior.
- `test_security.py` should map to escaping, Markdown safety, SQL-safety, attachment safety, and direct backend authorization requirements.
- `test_import_and_schema.py` should map to application import behavior, schema requirements, and optional site configuration file behavior.
- `test_notifications.py` should map to optional local notification email behavior and notification-history requirements.

# Test Suite Structure

The test suite should initially be implemented as multiple pytest files under a `tests/` directory.

## Recommended Initial Layout

```text
issues.cgi
requirements.md
tests/
  conftest.py
  test_auth.py
  test_routing.py
  test_permissions.py
  test_issue_lifecycle.py
  test_comments.py
  test_attachments.py
  test_preferences.py
  test_security.py
```

## Acceptable Minimal Initial Layout

A smaller initial implementation may use one test file plus shared fixtures:

```text
issues.cgi
requirements.md
tests/
  conftest.py
  test_issues.py
```

The single-file layout is acceptable only as a starting point. The tests should be split into focused files as the suite grows.

# Test Execution Command

The regression test suite and application under test shall be compatible with Python 3.9 through Python 3.12 unless the supported runtime is intentionally changed, and shall not be treated as Python 3.13-compatible until the application no longer depends on the removed standard-library `cgi` module.

The tests shall be runnable with the deployed Python 3 interpreter. For example, on a Python 3.9 deployment:

```bash
python3.9 -m pytest -q
```

On a Python 3.11 deployment, the tests may be run with:

```bash
python3.11 -m pytest -q
```

The application shall also pass Python syntax checking before or during regression testing:

```bash
python3 -m py_compile issues.cgi
```

If the deployed interpreter is Python 3.12, the corresponding commands may use `python3.12`.

# Test Dependencies

The required test dependency is:

- `pytest`

The optional runtime dependency for testing Markdown behavior is:

- `markdown`

The tests shall not require:

- Apache
- mod_ssl
- mod_wsgi
- Flask
- Django
- SQLAlchemy
- a live FreeIPA server
- production Unix users or groups
- the production SQLite database

# Application Import Behavior

## Single-File Application Import

If the application remains a single file named `issues.cgi`, the tests shall import it using `importlib.util.spec_from_file_location` or an equivalent import mechanism that supports importing a Python file with a non-`.py` extension.

The test suite shall not rename `issues.cgi` for test purposes.

## Refactored Application Import

If the application is later refactored, the preferred structure is:

```text
issues_app.py
issues.cgi
```

In that model:

- `issues_app.py` contains the application logic.
- `issues.cgi` remains the CGI entry point.
- `issues.cgi` imports and calls `main()` from `issues_app.py`.
- The tests import `issues_app.py` directly.

The refactor is optional. The regression suite must support the current single-file `issues.cgi` structure unless the application has actually been refactored.

# Test Isolation Requirements

- Tests shall not read from or write to `/var/lib/issues/issues.db`.
- Tests shall not read from or write to `/var/lib/issues/config`.
- Tests shall use a temporary SQLite database for each test or test group.
- Tests shall use a temporary per-user configuration directory.
- Tests shall not depend on real system users, real Unix groups, LDAP, SSSD, or FreeIPA.
- Tests shall monkeypatch application global variables such as `DB_FILE` and `PER_USER_CONFIG_DIR`.
- Tests shall monkeypatch user and group lookup functions to provide deterministic users and groups.

# Temporary Database Requirements

The regression tests shall create a fresh SQLite database using the schema expected by the application.

## Table: `issues`

The test database shall include:

```sql
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
    state_changed_at TEXT NOT NULL,
    completed_at TEXT
);
```

## Table: `comments`

The test database shall include:

```sql
CREATE TABLE comments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    issue_id INTEGER NOT NULL,
    commenter_username TEXT NOT NULL,
    comment_text TEXT NOT NULL,
    time_worked_minutes INTEGER,
    created_at TEXT NOT NULL
);
```

## Table: `attachments`

The test database shall include:

```sql
CREATE TABLE attachments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    issue_id INTEGER NOT NULL,
    filename TEXT NOT NULL,
    content BLOB NOT NULL,
    uploader_username TEXT NOT NULL,
    created_at TEXT NOT NULL
);
```

## Table: `issue_contributing_users`

The test database shall include:

```sql
CREATE TABLE issue_contributing_users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    issue_id INTEGER NOT NULL,
    contributing_username TEXT NOT NULL,
    contributed_by_username TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(issue_id, contributing_username)
);
```

## Table: `issue_history`

The test database shall include:

```sql
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
```

The test database should include an index or otherwise support efficient retrieval of history entries for a single issue ordered newest first.


# Mock User and Group Model

The regression tests shall use deterministic fake users and groups.

## Required Fake Users

The test suite shall include at least these fake users:

- `alice` - normal assignable user and common issue creator
- `bob` - normal assignable user and common assigned user
- `admin` - system administrator and assignable user
- `mallory` - valid system user who is not assignable and not an administrator
- `vwboot` - valid system user who belongs to the assignee group but is excluded

## Required Fake Groups

The test suite shall include at least these fake groups:

- `users`
- `wheel`

## Fake Group Membership

The test group model shall represent:

- `alice` belongs to `users`.
- `bob` belongs to `users`.
- `admin` belongs to `users`.
- `admin` belongs to `wheel`.
- `mallory` does not belong to `users`.
- `mallory` does not belong to `wheel`.
- `vwboot` belongs to `users` but is excluded by `ASSIGNEE_EXCLUDE`.

## Monkeypatched Lookup Behavior

The tests shall monkeypatch:

- `pwd.getpwnam`
- `pwd.getpwall`
- `grp.getgrnam`
- `os.getgrouplist`

The fake lookup behavior shall support both explicit group membership and supplemental group membership checks.

# Application Global Values During Tests

The tests shall monkeypatch application globals to deterministic values.

## Required Test Values

- `DB_FILE` - path to the temporary SQLite database
- `PER_USER_CONFIG_DIR` - path to a temporary configuration directory
- `ASSIGNEE_GROUP` - `users`
- `ASSIGNEE_EXCLUDE` - `vwboot`
- `ADMINS_GROUP` - `wheel`
- `ADMINS_GROUP_EXCLUDE` - empty string unless a specific exclusion test overrides it
- `MAX_UPLOAD_BYTES` - may use the application default unless a specific upload-size test overrides it
- `MAX_FILENAME_LEN` - may use the application default unless a specific filename-length test overrides it
- `SITE_CONFIG_FILE` - may use the application default unless a site-configuration test overrides it
- `BANNER_FILE` - empty string unless a configured-banner test overrides it
- `BANNER_DIMENSIONS` - empty string unless a configured-banner test overrides it
- `ISSUES_VERSION` - `1.0.0` unless a version-footer test overrides it

# Site Configuration File Tests

The tests shall verify:

- Missing `/etc/issues.conf` uses built-in default values.
- A present site configuration file overrides supported keys.
- Missing individual keys use built-in defaults.
- Unknown keys are ignored.
- Full-line `#` comments are ignored.
- Inline `#` comments are ignored.
- Invalid integer values are ignored.
- Invalid banner dimensions are ignored.
- Empty banner file and banner dimensions values are valid and disable the default banner image.
- The site configuration loader does not allow arbitrary globals to be overridden.
- Form-authentication variables are not changed by `/etc/issues.conf`.
- `LOGOUT_URL` is not changed by `/etc/issues.conf`.
- `ISSUES_PER_PAGE` is not changed by `/etc/issues.conf`.
- Auto-refresh options and auto-refresh interval mappings are not changed by `/etc/issues.conf`.
- Supported notification settings can be changed by `/etc/issues.conf`.
- Invalid notification boolean values are ignored.
- Invalid sendmail paths are ignored.
- Invalid notification body size limits are ignored.
- Triage notification recipients can be changed by `/etc/issues.conf`.
- Tests that exercise `/etc/issues.conf` behavior use temporary files and do not read or write the host system `/etc/issues.conf`.

# Expected Shared Fixture Names

The regression suite should use clear, stable pytest fixture and helper names so future maintainers can recreate, extend, or navigate the suite consistently.

Recommended fixture and helper names include:

- `app` - imported application module under test
- `temp_db` - path to a temporary SQLite database
- `temp_config_dir` - path to a temporary per-user configuration directory
- `fake_users` - deterministic fake user records
- `fake_groups` - deterministic fake group records and memberships
- `patched_environment` - monkeypatched application globals and CGI environment defaults
- `make_form` - helper that constructs CGI-compatible form objects
- `invoke_action` - helper that calls an action handler and captures CGI output
- `parse_headers` - helper that separates CGI headers from response body
- `seed_issue` - helper that inserts an issue row
- `seed_comment` - helper that inserts a comment row
- `seed_attachment` - helper that inserts an attachment row
- `fetch_issue` - helper that retrieves an issue row for assertions
- `fetch_comments` - helper that retrieves comment rows for assertions
- `fetch_attachments` - helper that retrieves attachment rows for assertions
- `fetch_history` - helper that retrieves issue history rows for assertions

Exact names may vary when there is a clear reason, but the suite should remain consistent and self-explanatory.

# Test Form Construction

The regression suite shall include helpers for constructing CGI form objects or equivalent request objects.

The helper shall support:

- GET-style query values
- POST-style form values
- blank values
- multiple field names when the application accepts alternatives
- file upload data for attachment tests

If the application uses `cgi.FieldStorage`, the helper shall produce objects that behave compatibly with `cgi.FieldStorage` for the tested code paths.

# Output Capture Requirements

The regression suite shall capture CGI output written to standard output.

Captured output shall be used to verify:

- HTTP status header
- `Content-Type` header
- `Location` header for redirects
- HTML page content
- plain text error content
- attachment download headers
- attachment download body when practical

# CGI Header Requirements Tested

The tests shall verify expected headers for representative actions.

## HTML Page Responses

HTML page responses shall include:

- `Content-Type: text/html`

## Plain Text Responses

Plain text error responses shall include:

- `Content-Type: text/plain`

## Redirect Responses

Successful form submissions shall commonly include:

- `Status: 303 See Other` or `Status: 302 Found`, depending on the implemented action
- `Location:` pointing back to the issue view or issue list as required

## Error Responses

Representative error cases shall verify appropriate status codes, including:

- `400 Bad Request`
- `403 Forbidden`
- `404 Not Found`
- `500 Internal Server Error` where applicable

# Direct Function Test Requirements

The regression suite shall include direct tests for pure or mostly pure helper functions.

## User and Group Tests

The tests shall verify:

- A known fake user exists.
- An unknown fake user does not exist.
- `admin` is recognized as a system administrator.
- `alice` is not recognized as a system administrator.
- `mallory` is not recognized as a system administrator.
- `ADMINS_GROUP_EXCLUDE` can exclude a group member from administrator recognition.
- `alice`, `bob`, and `admin` appear in the assignable user list.
- `vwboot` does not appear in the assignable user list.
- `mallory` does not appear in the assignable user list.
- Assignable-user dropdown list tests verify that users are not added solely because their primary group id matches `ASSIGNEE_GROUP`.
- A non-empty assignee must be both a valid system user and an allowed assignable user.
- An empty assignee is allowed when the application requirements allow an unassigned issue.

## Filename Tests

The tests shall verify:

- Safe filenames are preserved.
- Unsafe path separators are removed or normalized.
- Parent-directory references are removed or normalized.
- Empty filenames are rejected or replaced according to application behavior.
- Filenames longer than `MAX_FILENAME_LEN` are truncated or rejected according to application behavior.
- Filenames are escaped before display.

## Markdown Tests

The tests shall verify:

- Raw Markdown is preserved in database storage.
- Markdown is rendered only for display.
- HTML-special characters are escaped when required.
- Raw `<script>` input does not become executable output.
- GitLab-style strikethrough syntax using double tildes renders as strikethrough text.
- Unsafe HTML inside strikethrough content is escaped or otherwise prevented from executing.
- Supported unordered-list and ordered-list Markdown syntax renders as real list elements wherever the active renderer supports list syntax.
- The fallback Markdown renderer behaves safely when the `markdown` package is unavailable.
- The fallback Markdown renderer renders supported unordered-list and ordered-list block syntax as real list elements rather than paragraph text with line breaks.
- The fallback Markdown renderer renders supported GitLab-style strikethrough syntax safely.

## Date Validation Tests

The tests shall verify:

- Dates in `YYYY-MM-DD` format are accepted when valid and later than the current UTC date.
- Invalid date strings are rejected.
- Dates equal to the current UTC date are rejected for due-date updates.
- Dates earlier than the current UTC date are rejected.

## Date and Time Handling Tests

The tests shall verify:

- Timezone-aware date and timestamp values created by the application are stored in UTC.
- Timezone-aware date and timestamp values displayed by the application are displayed in the browser's local time zone.
- Created, updated, and completed timestamp displays do not silently convert UTC values to the server local timezone.
- Displayed timestamps include the browser-local time zone abbreviation when available.
- Tests that assert current-date or future-date behavior use UTC as the reference timezone.

# Handler-Level Test Requirements

The regression suite shall include tests that call action handlers directly and inspect output and database side effects.

# Authentication Tests

The tests shall verify:

- Public authentication support actions render without `REMOTE_USER`.
- `action=login` renders without `REMOTE_USER`.
- `action=login_failed` renders without `REMOTE_USER`.
- `action=logged_out` renders without `REMOTE_USER`.
- `action=auth_error` renders without `REMOTE_USER`.
- `action=favicon` returns the embedded favicon without `REMOTE_USER`.
- The login page renders as a complete HTML document.
- The login page includes the application header and includes a banner image only when `BANNER_FILE` is configured.
- The login form posts to the configured external form-authentication endpoint.
- The login form includes the configured username field.
- The login form includes the configured password field.
- The login form includes the configured destination or return-location field.
- The login form does not post to an application password-validation action.
- The application does not expose an action that validates passwords directly.
- The login page and authentication support pages do not disclose the authentication mechanism.
- The login page and authentication support pages do not mention Apache, PAM, web server authentication, server-side authentication, or similar implementation details in user-facing text.
- The login failed page renders as a complete HTML document.
- The logged out page renders as a complete HTML document.
- The authentication error page renders as a complete HTML document.
- Missing `REMOTE_USER` redirects protected actions to the public login action with a safe captured destination.
- Empty `REMOTE_USER` redirects protected actions to the public login action with a safe captured destination.
- Unknown `REMOTE_USER` is rejected for protected actions.
- Valid `REMOTE_USER` is accepted for protected actions.
- Anonymous access cannot directly reach protected issue-tracking pages or actions.

# Routing Tests

The tests shall verify:

- Missing `action` defaults to `login` when `REMOTE_USER` is missing or empty and defaults to `list` when `REMOTE_USER` is present.
- Known action values dispatch to the correct handler.
- Unknown action values return an error.
- Action names with unsafe characters are rejected or fail safely.
- The dispatcher checks for a global handler named `action_<action>` when present.
- The dispatcher can fall back to the internal action map when appropriate.
- GET and POST requests use the same CGI entry point.
- Public authentication support actions are recognized by the dispatcher.
- The public `favicon` action is recognized by the dispatcher.
- Public authentication support actions bypass the normal authenticated-user lookup.
- Non-public actions do not bypass authenticated-user lookup.

# Login and Authentication Support Page Tests

The tests shall verify:

- The login page renders with `Content-Type: text/html`.
- The login page renders as a complete HTML document.
- The login page includes a banner image only when `BANNER_FILE` is configured.
- The login page includes the favicon link.
- The login page includes a form with method `post`.
- The login form action matches `AUTH_FORM_ACTION`.
- The username input name matches `AUTH_FORM_USERNAME_FIELD`.
- The password input name matches `AUTH_FORM_PASSWORD_FIELD`.
- The destination input name matches `AUTH_FORM_LOCATION_FIELD`.
- The destination input value is safely escaped.
- The default destination input value is `/cgi-bin/issues.cgi`.
- A safe destination supplied in the login request through `AUTH_FORM_LOCATION_FIELD` or an accepted alias such as `next` or `return_to` is copied into the login form destination field.
- A safe destination supplied in the login request through split path and raw query-string parameters is reconstructed and copied into the login form destination field, including query-string values that are not URL encoded.
- Unauthenticated requests for protected application actions redirect to the public login action with the safe requested URL encoded into the login destination field.
- A safe originally requested application URL is captured as the destination when no explicit safe destination field is supplied.
- A safe originally requested application URL supplied through CGI/web-server internal redirect environment values such as `REDIRECT_URL` and `REDIRECT_QUERY_STRING` is captured as the destination.
- A safe originally requested application URL supplied through a same-origin `HTTP_REFERER` value is captured when direct request and internal redirect environment values do not identify the original protected URL.
- External, cross-origin, and public-authentication-page referer values fall back to `/cgi-bin/issues.cgi`.
- Unsafe destinations, including external URLs, scheme-relative URLs, URLs with schemes, and control-character values, fall back to `/cgi-bin/issues.cgi`.
- The login form does not use `/issues.cgi` or a relative `issues.cgi` path as its default destination.
- The login page includes concise user-facing sign-in text such as `Please sign in.`
- The login page does not display implementation details about the authentication mechanism.
- The login page does not mention Apache, PAM, web server authentication, server-side authentication, or similar implementation details.
- The login page does not echo a submitted password.
- The login failed page renders with `Content-Type: text/html`.
- The login failed page includes a retry or login link.
- The login failed page does not display implementation details about the authentication mechanism.
- The logged out page renders with `Content-Type: text/html`.
- The logged out page includes a login link.
- The authentication error page renders with `Content-Type: text/html`.
- The authentication error page does not expose raw environment values, system lookup internals, passwords, or authentication backend details.
- Protected actions remain inaccessible without valid `REMOTE_USER` even though public authentication support pages exist.

# Issue List Page Tests

The tests shall verify:

- The issue list page renders as a complete HTML document.
- The banner image is present only when `BANNER_FILE` is configured.
- The favicon link is present.
- The page title is present.
- The current user is displayed.
- User-facing username displays use the user's full name from the system account record when it is available.
- User-facing username displays fall back to the login name when the system full name is unavailable or empty.
- User-facing username displays fall back to the login name when the system full-name value contains a single word with no whitespace.
- Full-name display does not change submitted form values, authorization checks, stored database values, per-user configuration filenames, or notification recipients.
- Authenticated pages display the current user as bold text with a visually distinct adjacent `Logout` link in parentheses.
- The logout link points to `LOGOUT_URL`.
- The issue list uses an HTML table.
- Table headings are present, including the percent-complete heading.
- The issue list table headings are displayed in this order: ID, Title, Status, Due, Priority, Creator, Assignee, State, % Complete, Comments, Attachments, Updated.
- The issue list table includes the column heading `Assignee`, not `Assigned`.
- The issue view metadata table includes the row label `Assignee`, not `Assigned`.
- The issue view metadata table shows `Time in current state` only for open issues and places it immediately after `State`.
- The issue view metadata table appends `(wall clock)` to `Time in current state`.
- The issue view metadata table appends `(work time)` to `Total time worked`.
- Comment metadata appends `(work time)` to saved time-worked text.
- The parenthetical display text does not change the open-only behavior of `Time in current state`.
- Closed and canceled issue views still do not display `Time in current state`.
- Create and assignment forms use the label `Assignee`, not `Assigned user`.
- The issue list table includes the column heading `Due`, matching the Due filter label.
- Seeded issues with multiple ids are displayed in descending issue id order.
- Percent-complete values are displayed for each listed issue.
- The create-new-issue link is present.
- Status filter controls are present.
- Status filter controls support `any`, `open`, `closed`, and `canceled` values.
- The status filter options are displayed in this exact order: `any`, `open`, `closed`, `canceled`.
- Priority filter controls are present.
- The all-users filter checkbox is not present for system administrators.
- The all-users filter checkbox is not present for non-administrators.
- Non-administrators only see issues related to themselves.
- System administrators see all users' issues by default.
- Comment counts are displayed.
- Attachment counts are displayed.
- Percent-complete values, comment counts, and attachment counts are displayed together in the issue list.
- Stored per-user filter preferences are applied when no form values are provided.
- Changed filter values are saved to the per-user configuration file.
- Changed filter values are applied to the rendered issue list.
- Invalid stored filter preferences are ignored or reset to safe defaults.
- Pagination controls are present above the issue list.
- Pagination controls are present below the issue list.
- Pagination controls are structurally aligned to the right side of the issue-list area.
- The upper pagination controls are horizontally level with the create-new-issue link in a shared top issue-list control row.
- The create-new-issue link is structurally aligned to the left side of the shared top issue-list control row.
- Pagination controls are present even when there is only one page of issues.
- Pagination controls include Previous and Next controls.
- Pagination controls include a page dropdown between Previous and Next.
- The page dropdown displays the current page in `x of y` form.
- The page dropdown allows direct navigation to a selected page.
- Pagination controls submit a single effective `page` value so Previous, Next, and page-dropdown navigation are not browser-dependent.
- Previous and Next controls navigate to the intended adjacent page rather than remaining on the current page or returning to the first page.
- The page dropdown does not submit a competing `page` value that can override Previous or Next.
- The issue list renders no more than 25 issues on a page.
- Page navigation preserves active filters and user preference values.
- Missing, invalid, non-numeric, and out-of-range page values select a valid page safely.
- When filter changes reduce the number of available pages, the selected page is normalized to a valid page.
- The auto-refresh timer dropdown is present below the issue list.
- The auto-refresh timer dropdown is structurally aligned to the left side of the issue-list area.
- The auto-refresh label appears to the left of the dropdown and reads `Auto-refresh`.
- A last-refreshed indicator appears in parentheses immediately to the right of the auto-refresh dropdown box.
- The last-refreshed indicator text is slightly smaller than the Auto-refresh label text.
- The last-refreshed indicator uses the format `(Last refreshed: <relative time>)`.
- Immediately after the issue list page loads, the last-refreshed indicator displays `(Last refreshed: just now)`.
- After one minute, the last-refreshed indicator displays `(Last refreshed: 1 minute ago)`.
- After two or more minutes, the last-refreshed indicator displays `(Last refreshed: <n> minutes ago)`.
- The last-refreshed indicator updates automatically once per minute without reloading the page.
- The last-refreshed source timestamp is generated by the server in UTC.
- The relative-time display is calculated in the browser from the server-provided UTC refresh timestamp.
- The last-refreshed indicator does not display an absolute timestamp.
- The auto-refresh control is horizontally level with the lower pagination controls in a shared bottom issue-list control row.
- The lower pagination controls are structurally aligned to the right side of the shared bottom issue-list control row.
- The auto-refresh dropdown options are `never`, `5 minutes`, `10 minutes`, `20 minutes`, and `30 minutes`.
- The default auto-refresh selection is `never`.
- Selecting an auto-refresh value saves it to the per-user configuration file.
- Changing the auto-refresh dropdown saves the newly selected value rather than reverting to the previously selected value.
- The auto-refresh dropdown form submits a single effective `auto_refresh` value so saved preferences are not browser-dependent.
- The auto-refresh dropdown form does not include a hidden or duplicate `auto_refresh` value that can override the user's new selection.
- Stored auto-refresh preferences are reloaded when the issue list renders.
- Invalid stored auto-refresh values are ignored or replaced with `never`.
- A non-`never` auto-refresh value causes the rendered page to refresh automatically after the selected interval.

## Issue List Static and Dynamic Filter Tests

The tests shall verify:

- The Static filter group contains Status, Due, Has comments, Has attachments, and Search.
- The Dynamic filter group contains Priority, Creator, Assignee, and State.
- The Static filter group and Dynamic filter group are visually or structurally separated.
- The Search field appears on the same horizontal row as the other Static filter controls when screen width allows.
- The Status, Due, Has comments, and Has attachments controls appear on the left side of the Static filter row.
- The Search field appears on the right side of the Static filter row and is visually right-aligned.
- The Search field width responds to browser/window width with a usable minimum and reasonable maximum width.
- The Search field's responsive sizing is implemented with CSS and does not require JavaScript.
- The Search field has no separate Apply or Clear buttons.
- The Search field has no visible text label.
- A magnifying-glass control appears inside the left side of the Search field.
- The magnifying-glass control opens a drop-down-like search-history pane.
- The search-history pane contains previous non-empty search terms.
- Search-history terms are sorted newest first.
- Search-history terms are rendered as clickable text controls, not hyperlinks.
- Search-history term hover/focus styling changes the term background to a very light grey.
- Search-history term hover/focus styling spans the available row width minus the trash/delete control.
- Selecting a search-history term applies that term to the search.
- Selecting a search-history term moves that term to the top of search history.
- Each search-history term includes a right-justified trash/delete control.
- Trash/delete controls use a darker unobtrusive color, are not black, and remain large enough to read clearly.
- Activating a search-history term trash/delete control removes that term from search history.
- The bottom of the search-history pane includes a clear-history button.
- Priority appears to the left of Creator, Assignee, and State in the Dynamic filter group.
- The creator filter dropdown appears for system administrators.
- The creator filter dropdown does not appear for non-administrators.
- The creator filter defaults to `any` for system administrators.
- The creator filter option `any` allows system administrators to see all users' matching issues.
- Priority dropdown options are generated from issue rows matching the current Static filter group settings before Dynamic filter group filters are applied.
- The Priority dropdown includes an `any` option.
- Priority dropdown options other than `any` are generated from matching issue rows and use values from `PRIORITIES`.
- Selecting a specific priority limits the issue list to matching issues with that priority.
- Selecting a specific creator limits the issue list to matching issues created by that user.
- Creator dropdown options are generated from issue rows matching the current Static filter group settings before Dynamic filter group filters are applied.
- The assignee filter dropdown appears for system administrators.
- The assignee filter dropdown appears for non-administrators.
- Selecting a specific assignee limits the issue list to matching issues assigned to that user.
- The assignee filter respects the acting user's issue visibility scope.
- The assignee dropdown includes an `any` option.
- The assignee dropdown includes an `unassigned` option when matching issues include rows with no assigned user.
- Selecting `unassigned` limits the issue list to matching issues with no assigned user.
- Assignee dropdown options are generated from issue rows matching the current Static filter group settings before Dynamic filter group filters are applied.
- The state filter dropdown appears for system administrators.
- The state filter dropdown appears for non-administrators.
- Selecting a specific state limits the issue list to matching issues in that state.
- The state filter respects the acting user's issue visibility scope.
- The state dropdown includes an `any` option.
- State dropdown options are generated from issue rows matching the current Static filter group settings before Dynamic filter group filters are applied.
- The due-date filter dropdown appears when the status filter is `open`.
- The due-date filter dropdown appears when the status filter is `any`.
- The due-date filter dropdown does not appear when the status filter is `closed`.
- The due-date filter dropdown does not appear when the status filter is `canceled`.
- The Due filter label text is `Due`.
- The Due filter options are `any`, `no due date`, `today`, `within 5 days`, and `within 30 days`.
- The Due option `any` includes all due-date values and issues with no due date.
- The Due option `no due date` returns only issues without due dates.
- The Due option `today` returns only issues due on the current UTC date.
- The Due option `within 5 days` returns issues due within the next 5 UTC days.
- The Due option `within 30 days` returns issues due within the next 30 UTC days.
- Due-date filter tests freeze or monkeypatch the current UTC date so expectations are deterministic.
- The Has comments checkbox appears for all users.
- The Has comments checkbox label text is `Has comments`.
- The Has comments checkbox includes a click-based submit handler so the filter is applied immediately when clicked.
- Selecting the Has comments checkbox limits the issue list to issues with one or more comments.
- Unchecking the Has comments checkbox clears the saved `has_comments` preference.
- The Has attachments checkbox appears for all users.
- The Has attachments checkbox label text is `Has attachments`.
- The Has attachments checkbox includes a click-based submit handler so the filter is applied immediately when clicked.
- Selecting the Has attachments checkbox limits the issue list to issues with one or more attachments.
- Unchecking the Has attachments checkbox clears the saved `has_attachments` preference.
- The Search field is present in the Static filter group.
- Pressing Enter in the Search field is represented by normal list form submission and applies the search.
- Clearing the Search field and submitting the list form clears the saved search preference.
- Regression coverage must exercise real CGI GET parsing with `search=` to ensure blank submitted values are preserved and do not reload a stale saved search.
- Initial issue-list loads do not automatically reapply the last stored search term.
- Pagination and auto-refresh preserve the active submitted Search value.
- Submitted non-empty searches are saved to per-user search history.
- Per-user search history keeps a rolling window of the last 10 unique non-empty searches.
- Per-user search history displays newest first.
- Reusing a search term moves it to the top of search history.
- Search-history removal deletes only the selected search term.
- Search-history clearing removes all search-history terms.
- Search matches issue title.
- Search matches issue description.
- Search matches comment text.
- Search matches attachment filename.
- Search matches attachment uploader username.
- Search matches attachment creation timestamp metadata.
- Search does not match attachment file content.
- Search is limited to issues the acting user is authorized to see.
- Search combines correctly with Status, Due, Has comments, Has attachments, Priority, Creator, Assignee, and State filters.
- Dynamic dropdown options reflect the searched result set.
- Search does not create issue-history entries.
- Search does not send notification email.
- SQL-like search strings containing `%` or `_` are treated safely as literal search text.
- The Static filter group is applied before the Dynamic filter group.
- A combined filter case using multiple Static and Dynamic filter group filters returns only issues that match all selected filters.

# Issue History Tests

The tests shall verify:

- The test database includes the `issue_history` table.
- Creating an issue records one compact history entry.
- Changing priority records one compact history entry.
- Changing assignee records one compact history entry.
- Changing state records one compact history entry.
- Setting state to `complete` records history and still sets percent complete to `100`.
- Updating percent complete records one compact history entry.
- Updating due date records one compact history entry.
- Closing an issue records one compact history entry.
- Canceling an issue records one compact history entry.
- Reopening an issue records one compact history entry.
- Adding a comment records a compact history entry that references the new comment by `comment_id`.
- Comment history entries do not duplicate the full comment text in the `issue_history` table.
- Adding an attachment records a compact history entry that references the new attachment by `attachment_id`.
- Attachment history entries do not duplicate attachment content in the `issue_history` table.
- Attachment history display uses attachment metadata and does not select or display the attachment `content` BLOB.
- Issue history display does not include a separate Reference column.
- Comment excerpts and attachment metadata appear in the Summary column.
- Field-change history summaries display old and new values as quoted bold text.
- Updating title and description records a compact history entry.
- Title-change summaries include only truncated before-and-after title values when title values are included.
- Description-change summaries do not include full previous descriptions, full new descriptions, or full text diffs.
- Description-change summaries include only compact information such as character counts, line counts, or that description content changed.
- Issue history entries include issue id, acting username, action type, concise summary text, optional comment id, optional attachment id, and UTC creation timestamp in storage.
- Issue history display uses the acting user's display name.
- Issue history entries are append-only during normal application operation.
- Issue history entries are displayed newest first.
- Issue history display uses pagination controls consistent with the issue list page pagination controls.
- The issue history page displays no more than 25 history entries on a page.
- Issue history pagination controls are present above the history entry rows.
- Issue history pagination controls are present below the history entry rows.
- Issue history pagination controls are structurally aligned to the right side of the history page content area.
- Issue history pagination controls are present even when there is only one page of history entries.
- Issue history pagination controls include Previous and Next controls.
- Issue history pagination controls include a page dropdown between Previous and Next.
- The history page dropdown displays the current history page in `x of y` form.
- The history page dropdown allows direct navigation to a selected history page.
- Issue history pagination controls submit a single effective history page value so Previous, Next, and page-dropdown navigation are not browser-dependent.
- Previous and Next controls navigate to the intended adjacent history page rather than remaining on the current page or returning to the first page.
- The history page dropdown does not submit a competing page value that can override Previous or Next.
- History page navigation preserves the issue id.
- Missing, invalid, non-numeric, and out-of-range history page values select a valid page safely.
- Authorized issue creators can view issue history.
- Authorized assigned users can view issue history.
- System administrators can view issue history.
- Unrelated non-admin users cannot view issue history.
- Unauthorized users cannot view history by calling the history action directly.
- The issue list page does not display issue history.
- The issue list page does not query or load issue history.
- Ordinary page views are not recorded as issue history.
- Issue-list filtering, pagination, and auto-refresh are not recorded as issue history.
- Attachment downloads are not recorded as issue history.
- Successful notification email submissions are recorded as compact issue-history entries.
- Notification history entries include recipient names.
- Notification history entries do not include email body text, subject lines, full headers, SMTP transcripts, delivery status details, or attachment contents.

# Email Notification Tests

The tests shall verify:

- Notification email support is disabled by default.
- When notification email support is disabled, issue actions do not invoke the local mail command.
- When notification email support is enabled, supported issue actions submit plain-text notification email through the configured sendmail-compatible command.
- Notification email submission uses the configured `SENDMAIL_PATH`.
- Notification email submission does not connect directly to a remote SMTP server.
- Notification email submission does not require or store SMTP credentials.
- Notification email uses the configured `NOTIFICATION_FROM` sender.
- Notification email subject lines use the configured `NOTIFICATION_SUBJECT_PREFIX`.
- Notification email includes an issue link when `ISSUE_BASE_URL` is configured.
- Notification email omits the issue link when `ISSUE_BASE_URL` is empty.
- Notification email does not include attachment content.
- Issue creation without an assignee sends notification to configured triage recipients when notifications are enabled.
- Assignment or reassignment sends notification to the newly assigned user when notifications are enabled.
- Reassignment from one non-empty assignee to a different non-empty assignee also sends notification to the previously assigned user when notifications are enabled.
- Reassignment notification excludes the acting user, including when the acting user is the previously assigned user.
- Comment submission sends notification to the issue creator, assigned user, and contributing users when notifications are enabled, excluding the commenter.
- Comment notification email bodies include the submitted comment text capped by `NOTIFICATION_BODY_MAX_CHARS`.
- Attachment submission sends notification to the issue creator, assigned user, and contributing users when notifications are enabled, excluding the actor.
- Attachment notification email bodies include attachment metadata such as filename, uploader, timestamp, and file size.
- Attachment notification email bodies do not include attachment file content and do not attach the uploaded file.
- Title/description update sends notification to the issue creator, assigned user, and contributing users when notifications are enabled, excluding the actor.
- Title/description update notification email bodies include the updated title and updated description capped by `NOTIFICATION_BODY_MAX_CHARS`.
- Issue close sends notification to the issue creator, assigned user, and contributing users when notifications are enabled, excluding the actor.
- Issue close notification is sent as a single close notification and does not send a separate comment notification for the stored closing comment.
- Issue cancel sends notification to the issue creator, assigned user, and contributing users when notifications are enabled, excluding the actor.
- Issue cancel notification is sent as a single cancel notification and does not send a separate comment notification for the stored cancel comment.
- Issue reopen sends notification to the issue creator, assigned user, and contributing users when notifications are enabled, excluding the actor.
- Contributing-user add and remove actions send notification to affected contributing users when notifications are enabled, excluding the actor.
- Due-date changes send notification to the assigned user when notifications are enabled, excluding the actor.
- Notification-triggering actions on unassigned issues use `NOTIFICATION_TRIAGE_RECIPIENTS` when the ordinary recipient list is empty after actor exclusion.
- The default notification triage recipient is `root`.
- Triage recipient lists can include comma-separated local recipients and `@group` references.
- Triage `@group` references are expanded through system/NSS group lookup.
- Duplicate triage recipients are removed while preserving order.
- The acting user is excluded from triage recipients.
- If no triage recipients remain after actor exclusion, no email is sent and no `email_sent` history entry is recorded.
- Ordinary page views, issue list filtering, pagination, auto-refresh, history page views, and attachment downloads do not send notification email.
- Notification email is attempted only after the triggering issue action succeeds.
- A notification failure does not roll back the database change for the triggering issue action.
- A notification failure does not convert an otherwise successful issue action into a user-visible internal error.
- Successful notification submissions create compact `email_sent` issue-history entries.
- Email notification history entries include the recipient or recipients.
- Email notification history entries do not include the email body, subject line, attachments, full headers, SMTP transcript, or delivery status details.
- Tests monkeypatch the local mail command invocation and do not send real email.

# Issue View Page Tests

The tests shall verify:

- Existing issues render successfully for authorized users.
- Missing issues return a not-found error.
- The issue metadata table is present.
- The description section is present.
- The comments section is present.
- The attachments section is present.
- Total time worked displays between the Status and Due date metadata rows when total time worked is greater than 0 minutes and includes `(work time)`.
- Total time worked does not display when total time worked is 0 minutes.
- Total time worked is calculated from all saved comment time-worked entries for the issue.
- Total time worked uses labeled compact format and includes trailing zero-value units required by the selected display range.
- Comments display in reverse chronological order.
- Comment metadata displays saved time worked at the end of the metadata line using compact labeled format.
- Attachments display in chronological order.
- Completed-at information displays only when the issue is closed or canceled.
- A non-open issue with no due date displays a blank due-date value rather than the open-issue placeholder.
- The page includes a banner image only when `BANNER_FILE` is configured.
- The page title is present.
- The current user is displayed.
- Authenticated pages display the current user as bold text with a visually distinct adjacent `Logout` link in parentheses.
- The logout link points to `LOGOUT_URL`.

## Issue View Authorization Tests

The tests shall verify:

- The creator can view the issue.
- The assigned user can view the issue.
- A contributing user can view the issue.
- A system administrator can view the issue.
- An unrelated non-admin user who is not contributing cannot view the issue.

## Issue View UI-Control Tests

The tests shall verify:

- `Edit Title & Description` displays only when the issue is open and the acting user is the creator or a system administrator.
- `Close` displays only when the issue is open and the acting user is permitted by the application requirements.
- `Cancel` displays only when the issue is open and the acting user is the creator.
- `Re-open` displays only when the issue is not open and the acting user is a system administrator.
- Assignee editing displays only when the issue is open and the acting user is the creator or a system administrator.
- Priority editing displays only when the issue is open and the acting user is the creator or a system administrator.
- Percent-complete editing displays only when the issue is open and the acting user is the assigned user.
- State editing displays only when the issue is open and the acting user is the assigned user.
- Due-date editing displays only when the issue is open and the acting user is the creator or a system administrator.
- Assignee changes are saved when the user changes the assignee field value.
- Priority changes are saved when the user changes the priority field value.
- State changes are saved when the user changes the state field value.
- Percent-complete changes are saved when the user clicks the corresponding percent-complete button.
- Due-date changes are saved when the user clicks the corresponding due-date button.
- The percent-complete button is not clickable until the user changes the percent-complete field value.
- The due-date button is not clickable until the user changes the due-date field value.
- The add-comment link displays only for users allowed to comment.
- The add-attachment link displays only for users allowed to attach files.
- Contributing-user management controls display according to contributing-user management permissions.
- Issue-view action items use a consistent UI element style and do not mix links, buttons, and other control styles.

# Create Issue Tests

## Create Form Tests

The tests shall verify:

- The create form renders as a complete HTML document.
- The title field is present.
- The description field is present.
- The priority selector is present.
- The due-date field is present.
- The assignee selector is present.
- The contributing-users dual listbox is present.
- The contributing-users dual listbox available-users box contains candidate users selected by the same rules as candidate assignees.
- The contributing-users dual listbox does not contain users who are not valid candidate assignees.
- The contributing-users dual listbox excludes the issue creator and selected assignee.
- A username displayed in one contributing-users dual listbox box is not displayed in the other box.
- Contributing-user dual listbox entries are sorted by displayed user name.
- Contributing-user dual listbox entries continue to display user-facing names after users are moved between boxes.
- The empty assignee option is present.
- Assignable users appear in the assignee selector.
- Excluded users do not appear in the assignee selector.
- The Markdown help link is present.
- The Markdown help link opens in a new browser window or tab and includes a safe relationship attribute when required.
- The submit button is present.

## Create Submission Tests

The tests shall verify:

- A valid submission creates an issue.
- The acting user becomes `creator_username`.
- The supplied assignee becomes `assigned_username`.
- Empty assignee is stored safely according to application behavior.
- Missing title is rejected.
- Missing description is rejected.
- Invalid priority is rejected.
- Nonexistent assignee is rejected.
- Existing but non-assignable assignee is rejected.
- Excluded assignee is rejected.
- A valid creation submission can add multiple contributing users.
- Nonexistent contributing users are rejected.
- Existing users who are not valid candidate assignees are rejected as contributing users.
- The issue creator is rejected as a contributing user.
- The assigned user is rejected as a contributing user.
- Successful creation with contributing users records rows in `issue_contributing_users`.
- Successful creation with contributing users records a compact contributing-user history entry.
- Successful creation redirects to the issue view or issue list as implemented.
- Created issue defaults are correct for status, state, percent complete, timestamps, and completion state.

# Contributing User Tests

The tests shall verify:

- The test database schema includes `issue_contributing_users`.
- A contributing user sees contributing issues in the issue list.
- A contributing user can view a contributing issue.
- A contributing user has read-only access to issue metadata, description, comments, attachments, and history.
- A contributing user on an open issue can comment.
- A contributing user on an open issue can attach files.
- A contributing user can download attachments for an issue where they are listed as a contributor.
- A contributing user can remove themself from contributing users.
- A contributing user cannot add contributing users unless they are also creator, assignee, or system administrator.
- A contributing user cannot remove other contributing users unless they are also creator, assignee, or system administrator.
- Issue creators, assigned users, and system administrators can add contributing users.
- Issue creators, assigned users, and system administrators manage contributing users with a dual listbox.
- The dual listbox left box contains users who can contribute and are not current contributing users.
- The dual listbox right box contains users currently contributing on the issue.
- The issue creator and assigned user are excluded from both contributing-user dual listbox boxes.
- Moving users between contributing-user dual listbox boxes re-sorts the destination box alphabetically.
- Issue creators, assigned users, and system administrators can remove contributing users.
- Multiple contributing users can be added in one operation.
- Multiple contributing users can be removed in one operation.
- Contributing-user add and remove operations create compact issue-history entries.
- Contributing-user add and remove notifications are sent to the affected contributing users when notifications are enabled, excluding the actor.
- Contributing users receive the same issue-activity notification emails as issue creators.

# Assignment Tests

The tests shall verify:

- The issue creator can assign an open issue.
- A system administrator can assign an open issue.
- A non-creator assigned user cannot assign unless also otherwise authorized.
- An unrelated non-admin user cannot assign.
- Closed issues cannot be assigned.
- Canceled issues cannot be assigned.
- Nonexistent target users are rejected.
- Existing but non-assignable users are rejected.
- Excluded users are rejected.
- Successful assignment updates the database.
- Successful assignment redirects back to the issue view.

# Comment Tests

## Comment Form Tests

The tests shall verify:

- The comment form renders for appropriate issue ids.
- The comment text area is present.
- The optional time-worked input is present after or below the comment field.
- The optional time-worked input displays compact example placeholder text using minimal unit specifiers.
- The optional time-worked input is sized to fit the placeholder examples without being larger than necessary.
- The optional time-worked input clears its placeholder hint when the field receives focus.
- The Markdown help link is present.
- The Markdown help link opens in a new browser window or tab and includes a safe relationship attribute when required.
- The submit button is present.
- On open issues, the creator, assigned user, contributing user, and system administrator can render the comment form.
- On open issues, an unrelated non-admin user who is not contributing cannot render the comment form.
- On closed issues, only a system administrator can render the comment form.
- On canceled issues, only a system administrator can render the comment form.

## Comment Submission Tests

The tests shall verify:

- Empty comments are rejected.
- Whitespace-only comments are rejected.
- Valid time-worked values are normalized to integer minutes and stored with the comment.
- Empty time-worked values are accepted and stored without a time-worked value.
- Invalid time-worked values are rejected without saving the comment.
- Invalid time-worked submissions return the comment form with the entered comment text and time-worked value preserved.
- Time-worked parsing accepts supported minute, hour, and day units and defaults to hours when no unit is provided.
- Time-worked parsing rejects normalized durations that are not greater than `0` minutes, normalized durations that are not less than `24` hours, values with more than two decimal places, and unknown units.
- Raw comment text is stored in the database.
- Markdown comment text remains raw in storage.
- On open issues, the creator can comment.
- On open issues, the assigned user can comment.
- On open issues, a contributing user can comment.
- On open issues, a system administrator can comment.
- On open issues, an unrelated non-admin user who is not contributing cannot comment.
- On closed issues, only a system administrator can comment.
- On canceled issues, only a system administrator can comment.
- Successful comment submission redirects back to the issue view.

# Attachment Tests

## Attach Form Tests

The tests shall verify:

- The attachment form renders for appropriate issue ids.
- The file upload field is present.
- The maximum upload size label is present.
- The maximum upload size is displayed in MB.
- The submit button is present.

## Attach Submission Tests

The tests shall verify:

- Missing issue id is rejected.
- Missing file data is rejected.
- Empty file data is rejected or handled according to application behavior.
- Uploads larger than `MAX_UPLOAD_BYTES` are rejected.
- The creator can attach a file.
- The assigned user can attach a file.
- A contributing user can attach a file.
- A system administrator can attach a file.
- An unrelated non-admin user who is not contributing cannot attach a file.
- The stored filename is normalized.
- The stored filename is limited to `MAX_FILENAME_LEN`.
- The stored binary content matches the uploaded content.
- Successful attachment submission redirects back to the issue view.

## Download Attachment Tests

The tests shall verify:

- Missing attachment id is rejected.
- Unknown attachment id returns a not-found error.
- The issue creator can download the attachment.
- The assigned user can download the attachment.
- A contributing user can download the attachment.
- A system administrator can download the attachment.
- An unrelated non-admin user who is not contributing cannot download the attachment.
- Download responses include a safe `Content-Disposition` filename.
- Download responses include the stored file bytes.
- Filenames are normalized or escaped before being returned in headers.

# Update Issue Tests

## Update Form Tests

The tests shall verify:

- The update form renders for an existing issue.
- The form is populated with the current title.
- The form is populated with the current description.
- The Markdown help link is present.
- The Markdown help link opens in a new browser window or tab and includes a safe relationship attribute when required.
- The submit button is present.
- The issue creator and system administrator can render the update form for open issues.
- Unauthorized users cannot render the update form.
- Closed issues cannot render the update form.
- Canceled issues cannot render the update form.

## Update Submission Tests

The tests shall verify:

- The issue creator can update title and description on an open issue.
- A system administrator can update title and description on an open issue.
- The assigned user cannot update title and description unless also authorized.
- An unrelated non-admin user cannot update title and description.
- Closed issues cannot be updated.
- Canceled issues cannot be updated.
- Missing title is rejected.
- If description is omitted and the application supports title-only update, only the title changes.
- If description is supplied, both title and description change.
- Successful update redirects back to the issue view.

# Inline Update Tests

## Priority Tests

The tests shall verify:

- The issue creator can set priority.
- A system administrator can set priority.
- The assigned user cannot set priority unless also authorized.
- An unrelated non-admin user cannot set priority.
- Invalid priority values are rejected.
- Closed issues reject priority updates.
- Canceled issues reject priority updates.
- Successful priority update persists to the database.

## Due-Date Tests

The tests shall verify:

- The issue creator can set due date on an open issue.
- A system administrator can set due date on an open issue.
- The assigned user cannot set due date unless also authorized.
- An unrelated non-admin user cannot set due date.
- Closed issues reject due-date updates.
- Canceled issues reject due-date updates.
- Invalid date formats are rejected.
- Current-date due dates are rejected.
- Past due dates are rejected.
- Valid future due dates are accepted.
- Clicking the due-date button saves the due-date value.
- Successful due-date update persists to the database.

## Percent-Complete Tests

The tests shall verify:

- The assigned user can set percent complete.
- The creator cannot set percent complete unless also the assigned user.
- A system administrator cannot set percent complete unless also the assigned user, unless the implementation requirements explicitly permit it.
- An unrelated non-admin user cannot set percent complete.
- Non-integer values are rejected.
- Values below 0 are rejected.
- Values above 100 are rejected.
- Closed issues reject percent-complete updates.
- Canceled issues reject percent-complete updates.
- Boundary values 0 and 100 are accepted.
- Clicking the percent-complete button saves the percent-complete value.
- Successful percent-complete update persists to the database.

## State Tests

The tests shall verify:

- The assigned user can set state.
- The creator cannot set state unless also the assigned user.
- A system administrator cannot set state unless also the assigned user, unless the implementation requirements explicitly permit it.
- An unrelated non-admin user cannot set state.
- Invalid state values are rejected.
- All configured valid state values are accepted.
- Closed issues reject state updates.
- Canceled issues reject state updates.
- Setting state to `complete` also sets percent complete to `100`.
- Indirect updates that set state to `complete` also set percent complete to `100`.
- Successful state update persists to the database.

# Close Issue Tests

## Close Form Tests

The tests shall verify:

- Missing issue id is rejected.
- Missing issue record is rejected.
- Unauthorized users cannot render the close form.
- Authorized users can render the close form.
- The closing comment field is present.
- The Markdown help link is present.
- The Markdown help link opens in a new browser window or tab and includes a safe relationship attribute when required.
- The submit button is present.

## Close Submission Tests

The tests shall verify:

- The issue creator can close an open issue.
- The assigned user can close an open issue when permitted by the implemented requirements.
- A system administrator can close an open issue.
- An unrelated non-admin user cannot close an issue.
- Missing closing comment uses `DEFAULT_CLOSING_COMMENT`.
- Empty closing comment uses `DEFAULT_CLOSING_COMMENT`.
- Either accepted closing-comment field name is supported.
- The default value of `DEFAULT_CLOSING_COMMENT` is `no comment provided`.
- Successful close sets `status` to `closed`.
- Successful close sets `state` to `complete`.
- Successful close sets percent complete to `100`.
- Successful close sets `completed_at`.
- Successful close updates `updated_at`.
- Successful close stores a closing comment.
- Successful close records a compact issue-history entry that references the stored closing comment by `comment_id`.
- Successful close does not record a separate `comment_added` issue-history entry for the stored closing comment.
- Successful close redirects back to the issue view.

# Cancel Issue Tests

## Cancel Form Tests

The tests shall verify:

- Missing issue id is rejected.
- Missing issue record is rejected.
- Only the issue creator can render the cancel form for an open issue.
- Assigned users who are not the creator cannot render the cancel form.
- System administrators who are not the creator cannot render the cancel form unless the implementation requirements explicitly permit it.
- Closed issues cannot render the cancel form.
- Canceled issues cannot render the cancel form.
- The cancel comment field is present.
- The Markdown help link is present.
- The Markdown help link opens in a new browser window or tab and includes a safe relationship attribute when required.
- The submit button is present.

## Cancel Submission Tests

The tests shall verify:

- The issue creator can cancel an open issue.
- The assigned user cannot cancel unless also the creator.
- A system administrator cannot cancel unless also the creator, unless the implementation requirements explicitly permit it.
- An unrelated non-admin user cannot cancel.
- Missing cancel comment uses `DEFAULT_CLOSING_COMMENT`.
- Empty cancel comment uses `DEFAULT_CLOSING_COMMENT`.
- Either accepted cancel-comment field name is supported.
- The default value of `DEFAULT_CLOSING_COMMENT` is `no comment provided`.
- Successful cancel sets `status` to `canceled`.
- Successful cancel sets `completed_at`.
- Successful cancel updates `updated_at`.
- Successful cancel stores a cancel comment.
- Successful cancel records a compact issue-history entry that references the stored cancel comment by `comment_id`.
- Successful cancel does not record a separate `comment_added` issue-history entry for the stored cancel comment.
- Successful cancel redirects back to the issue view.

# Reopen Issue Tests

The tests shall verify:

- A system administrator can reopen a closed issue.
- A system administrator can reopen a canceled issue.
- A non-admin creator cannot reopen an issue.
- A non-admin assigned user cannot reopen an issue.
- An unrelated non-admin user cannot reopen an issue.
- Open issues are not changed by the reopen action.
- Reopening sets `status` to `open`.
- Reopening clears or resets completion data according to application behavior.
- Reopening updates `updated_at`.
- An optional reopen comment is stored when supplied.
- Empty supplied reopen comment uses `DEFAULT_CLOSING_COMMENT` when required by implementation behavior.
- Successful reopen redirects back to the issue view.

# Markdown Help Page Tests

The tests shall verify:

- The Markdown help page renders as a complete HTML document.
- The banner image is present only when `BANNER_FILE` is configured.
- The page title is present.
- Markdown examples are present.
- Numbered-list help examples in the rendered Markdown example block are rendered as numbered list items.
- Bulleted-list help examples in the rendered Markdown example block are rendered as bulleted list items.
- The rendered Markdown example block keeps the bulleted-list example and numbered-list example as separate lists, not as one nested or merged list.
- The help page does not contain duplicate hard-coded unordered-list or ordered-list sections outside the rendered Markdown example block.
- The Markdown help page includes a GitLab-style strikethrough example using double tildes.
- The strikethrough help example renders as strikethrough text.
- The informational note text is present.
- The help page is available through its documented action.

# Embedded Favicon Tests

The tests shall verify:

- Every representative HTML page includes a favicon link in the document head.
- The favicon link points to the CGI favicon action.
- The favicon action renders without `REMOTE_USER`.
- The favicon action returns `Content-Type: image/x-icon` or the configured favicon MIME type.
- The favicon response body is non-empty binary data.
- The favicon response body matches the embedded icon format expected by the application.
- The embedded favicon payload remains at the end of `issues.cgi` rather than being placed in the middle of application logic.

# Per-User Configuration Tests

The tests shall verify:

- Missing per-user configuration file uses `CONFIG_DEFAULTS`.
- Existing valid per-user configuration is loaded.
- Changed list filters are saved to the correct per-user JSON file.
- Changed list filters are applied to the issue list.
- The configuration path is based on the current username.
- Status, due-date, `has_comments`, `has_attachments`, priority, creator, assignee, state, and auto-refresh preferences are saved and read consistently.
- All Static and Dynamic filter group preferences are saved and read in the same manner as the status filter, except stored Search values are not automatically applied on initial issue-list loads.
- Search history is saved and read from the acting user's per-user configuration file.
- The auto-refresh preference is saved and read in the same manner as list filter preferences.
- Missing `has_comments` and `has_attachments` checkbox fields in a submitted list-filter request are saved as false, because unchecked HTML checkboxes are omitted from GET form submissions.
- Invalid stored status values are ignored or replaced with defaults.
- Invalid stored priority values are ignored or replaced with defaults.
- Invalid stored creator values are ignored or replaced with defaults.
- Invalid stored assignee values are ignored or replaced with defaults.
- Invalid stored state values are ignored or replaced with defaults.
- Invalid stored due-date filter values are ignored or replaced with defaults.
- Invalid stored `has_comments` values are ignored or replaced with defaults.
- Invalid stored `has_attachments` values are ignored or replaced with defaults.
- Invalid stored auto-refresh values are ignored or replaced with defaults.
- The all-users preference is not required and is ignored if present in a stored configuration file.
- Non-admin users cannot use stored creator preferences to view unauthorized users' issues.
- System administrators can persist and reload the creator filter, including the `any` default.

# Security Tests

The tests shall verify security-sensitive behavior.

## HTML Escaping Tests

The tests shall verify:

- Issue titles are escaped before display.
- Display names and fallback usernames are escaped before display.
- Filenames are escaped before display.
- Comment text is rendered safely.
- Description text is rendered safely.
- Raw `<script>` input does not appear as executable HTML.

## Authentication Support Page Safety Tests

The tests shall verify:

- Authentication support pages escape any displayed destination or message values.
- Authentication support pages do not display password values.
- Authentication support pages do not write submitted password values to the database.
- Authentication support pages do not write submitted password values to per-user preference files.
- Authentication support pages do not expose raw environment values.
- Authentication support pages do not display implementation details about the authentication mechanism.
- Public authentication support actions do not make protected issue-tracking actions publicly accessible.

## SQL Safety Tests

The tests shall verify:

- SQL injection-like issue titles do not alter query structure.
- SQL injection-like comments do not alter query structure.
- SQL injection-like assignee values are rejected or treated as plain values.
- Database writes use parameterized query behavior as observable through successful safe storage of dangerous-looking strings.

## Authorization Enforcement Tests

For each protected action, the tests shall verify that authorization is enforced by the backend action itself, not only by hiding UI controls.

Issue-list filter tests shall verify that non-admin users cannot use creator, assignee, state, due-date, Has comments, Has attachments, auto-refresh, or stored preference values to view issues they are not otherwise authorized to see.

Protected actions include:

- view issue
- assign issue
- attach file
- download attachment
- comment
- update title and description
- set priority
- set due date
- set percent complete
- set state
- close issue
- cancel issue
- reopen issue

## Attachment Safety Tests

The tests shall verify:

- Path traversal filenames are normalized or rejected.
- Absolute-path filenames are normalized or rejected.
- Filenames with unsafe shell characters are normalized or rejected.
- Download headers do not contain unsafe unescaped filename content.
- Oversized uploads are rejected before storage.

# UI Testing Requirements

The regression suite shall test the UI structurally, not pixel-perfect visually.

## Required UI Assertions

The tests shall inspect generated HTML and verify:

- Required page sections are present.
- Required forms are present.
- Required input fields are present.
- Required links are present.
- Required submit buttons are present where documented.
- Required non-submit action buttons are present where documented.
- Buttons documented as not clickable until a field value changes are initially not clickable.
- Checkbox filter controls documented as applying immediately when clicked include the required click-based submit handler.
- The Has comments and Has attachments checkbox labels are present where documented.
- Pagination controls are present above and below the issue list where documented.
- Pagination controls are structurally aligned to the right side of the issue-list area where documented.
- Pagination markup avoids duplicate submitted `page` controls that can cause browser-dependent Previous and Next behavior.
- The create-new-issue link and upper pagination controls are horizontally level in a shared top issue-list control row where documented.
- The auto-refresh dropdown is present below the issue list where documented.
- The auto-refresh dropdown is structurally aligned to the left side of the issue-list area where documented.
- The auto-refresh label text is `Auto-refresh`.
- The last-refreshed indicator is present immediately to the right of the auto-refresh dropdown where documented.
- The last-refreshed indicator is enclosed in parentheses where documented.
- The last-refreshed indicator has a structural style rule that makes it slightly smaller than the Auto-refresh label text.
- The last-refreshed indicator includes a server-generated UTC source timestamp in a data attribute.
- The last-refreshed indicator initially displays relative text such as `(Last refreshed: just now)`, not an absolute timestamp.
- Generated JavaScript updates the last-refreshed relative text once per minute without reloading the page.
- Auto-refresh markup avoids duplicate submitted `auto_refresh` controls that can cause the previous preference value to override the newly selected value.
- The auto-refresh control and lower pagination controls are horizontally level in a shared bottom issue-list control row where documented.
- Action items documented as using a consistent UI element style do not mix links, buttons, and other control styles.
- Page-level action rows, form submit rows, pagination rows, issue-list filters, issue-history controls, and issue-view inline edit forms use shared structural classes for spacing rather than page-specific ad hoc control spacing.
- Create, update, comment, attach, close, cancel, login, and contributing-user management forms use the shared form-action row structure for submit controls and cancel controls when present.
- The issue-list table retains the documented compact text size.
- The issue-view metadata table uses the same documented compact table text size as the issue-list table.
- Comment author, timestamp, and time-worked metadata uses the documented compact metadata class rather than raw heading markup.
- Shared typography rules are present for page headings, section headings, metadata text, form controls, notices, errors, and Markdown-rendered content.
- Required table headers are present.
- Percent-complete table headers and issue-list values are present where documented.
- Static and Dynamic filter controls are present or absent according to role and current status filter.
- Static and Dynamic filter groups are structurally separated.
- Role-specific controls appear for authorized users.
- Role-specific controls do not appear for unauthorized users.
- When configured, the banner image appears before the text page header.
- When no banner image is configured, the CSS fallback header appears before the text page header.
- The CSS fallback header structurally includes the `Issues` text, a 35-pixel height rule, a horizontal gradient rule, the `#E6E9EF` left-side color, and the `#BFC5D0` text color.
- The CSS fallback header structurally uses a half-page-margin buffer above, left, and right.
- HTML pages include a favicon link in the document head.
- The current user appears in the page header where the page requires an authenticated user.
- Authenticated page headers include a distinct `Logout` link adjacent to the current username.
- Authenticated page headers structurally place the page title and current-user/logout display on the same row with the current-user/logout display right-aligned.
- Authenticated page headers use the current-user label `Welcome,`.
- The username is rendered as bold text and the logout link is rendered separately in parentheses.
- Public authentication support pages do not display the authenticated page username/logout header.
- Public authentication support pages render without displaying a current-user value.
- When `ISSUES_VERSION` is non-empty, authenticated pages display a footer containing `Issues` followed by the version number.
- Unauthenticated public pages do not display the application version number even when `ISSUES_VERSION` is non-empty.
- Form pages that contain eligible text-entry controls include automatic focus on the top-left-most eligible control.
- Issue list and issue view pages do not include automatic form-focus behavior.

# Build Script Tests

The tests shall verify:
- The repository build script obtains the current local `HEAD` commit ID from Git.
- The repository build script updates the `ISSUES_VERSION` assignment in `issues.cgi`.
- In default development-build mode, the updated `ISSUES_VERSION` value uses the form `x.y.z-dev.N+GITID`.
- Development-build mode uses the number of commits after the matching release tag as `N`.
- Development-build mode uses `0` as `N` when no matching release tag exists.
- In explicit release-build mode, the updated `ISSUES_VERSION` value uses the form `x.y.z+GITID`.
- The `GITID` value in the updated `ISSUES_VERSION` is an abbreviated commit ID suitable for display in the application footer.
- The repository build script preserves the existing `x.y.z` base version.
- The repository build script replaces existing build metadata rather than appending a second metadata suffix.
- The repository build script fails if the target `issues.cgi` file does not contain exactly one `ISSUES_VERSION` assignment.

# Repository Workflow Tests

The tests shall not commit local repository changes directly on `main`.

Repository workflow checks shall treat the source-default `ISSUES_VERSION` value and build-script-stamped `ISSUES_VERSION` values as separate states:
- ordinary source commits are expected to leave `ISSUES_VERSION` at the source default documented in `requirements.md`;
- intentional build-output or release-stamping commits may contain a generated `x.y.z-dev.N+GITID` or `x.y.z+GITID` value.

## Not Required Initially

The regression suite is not required to test:

- exact CSS layout
- pixel positioning
- browser rendering screenshots
- font sizes
- table column widths
- cross-browser visual differences

Browser-based or screenshot-based tests may be added later, but they are not required for the initial regression suite.

# Subprocess CGI Smoke Tests

The regression suite shall include a small number of tests that execute the CGI script as a subprocess.

These tests shall set CGI environment variables such as:

- `REQUEST_METHOD`
- `QUERY_STRING`
- `REMOTE_USER`
- `CONTENT_TYPE`
- `CONTENT_LENGTH`
- `SERVER_NAME`
- `SERVER_PORT`
- `SERVER_PROTOCOL`
- `GATEWAY_INTERFACE`
- `SCRIPT_NAME`

Subprocess tests shall verify:

- The script can execute as a CGI program.
- The dispatcher handles a known action.
- The dispatcher rejects an unknown action.
- Missing action defaults to the list action when `REMOTE_USER` is present.
- Headers are emitted before body content.
- GET request parsing works.
- POST request parsing works for a representative form.
- A public authentication support action such as `action=login` can run without `REMOTE_USER`.
- A request with no `action` and no `REMOTE_USER` defaults to the public login page.
- A protected action without `REMOTE_USER` redirects to the public login action with a safe captured destination.

Subprocess tests should be limited in number because monkeypatching does not naturally cross process boundaries. Most behavior shall be tested through direct function and handler-level tests.

# Test Data Helper Requirements

The regression suite shall provide helper functions to seed test data.

Required helpers include:

- create temporary schema
- seed an issue
- seed a comment
- seed an attachment
- fetch an issue row
- fetch comments for an issue
- fetch attachments for an issue
- construct a form object
- invoke a handler and capture output
- parse CGI headers from captured output
- assert that output contains required fragments
- assert that output does not contain forbidden fragments

# Regression Guard Requirements

When a bug is fixed in `issues.cgi`, the test suite should add a regression test that fails without the fix and passes with the fix.

Bug-fix regression tests shall be named clearly and should describe the behavior being protected.

Examples:

- `test_freeipa_group_membership_uses_getgrouplist`
- `test_unrelated_user_cannot_call_close_directly`
- `test_raw_markdown_is_stored_but_rendered_safely`
- `test_attachment_download_rejects_unauthorized_user`

# Minimum First-Pass Scope

A first implementation of the regression suite may be smaller than the full target suite, but it shall establish the core architecture and protect the highest-risk behavior first.

The first pass should include at least:

- application import and `issues.cgi` syntax checking
- temporary SQLite database creation using the expected schema
- fake user and fake group monkeypatching
- login redirection for missing and empty `REMOTE_USER`, and authentication rejection for unknown `REMOTE_USER`
- assignable-user and administrator recognition tests
- one successful issue creation test
- one issue visibility authorization test for each major role category
- one unauthorized direct-call test for a protected backend action
- one structural issue-list or issue-view HTML test
- one role-specific UI-control visibility test
- one safe rendering or escaping test for user-supplied content
- one SQL-injection-like string test that verifies dangerous-looking input is handled as data
- one attachment upload or download authorization test
- one per-user preference loading or saving test
- one Static and Dynamic list filter rendering or behavior test
- one subprocess CGI smoke test

After this first pass exists and runs reliably, additional tests should be added incrementally until the full acceptance criteria are satisfied.

# License Notice Regression Requirements

- Release review and regression checks must verify that project-owned Python source files include `SPDX-License-Identifier: AGPL-3.0-only` near the top of the file.
- Release review and regression checks must verify that project-owned source-file license notices do not contain `AGPL-3.0-or-later`, `or later`, `any later version`, or equivalent wording unless the project owner explicitly changes the licensing policy.
- Release review must verify that the top-level `LICENSE` file contains the official, unmodified GNU Affero General Public License version 3 text.
- License-notice checks must not require editing the official GNU license text to remove its generic explanatory language about future versions; the project-owned source notices define this project as AGPLv3-only.

# Acceptance Criteria

The regression test suite is considered complete enough for initial use when:

- It can be run with `python3.11 -m pytest -q`.
- It creates and uses a temporary SQLite database.
- It uses fake users and fake groups rather than real system accounts.
- It verifies authentication behavior.
- It verifies group membership and assignable-user behavior.
- It verifies issue creation.
- It verifies issue visibility permissions.
- It verifies at least one successful and one unauthorized case for each protected action.
- It verifies role-specific UI controls on the issue view page.
- It verifies comment creation and ordering.
- It verifies attachment upload and download authorization.
- It verifies close, cancel, and reopen behavior.
- It verifies per-user preference loading and saving.
- It verifies Static and Dynamic issue-list filter rendering, persistence, and behavior.
- It verifies issue-list pagination rendering, navigation, and 25-issue page limits.
- It verifies auto-refresh control rendering, persistence, and generated refresh behavior.
- It verifies that non-admin users cannot broaden issue visibility through list filters or stored filter preferences.
- It verifies HTML escaping or safe rendering for user-supplied content.
- It verifies GitLab-style Markdown strikethrough rendering and safety.
- It verifies SQL-injection-like strings are handled as data.
- It includes at least one subprocess CGI smoke test.
- It passes syntax checking for `issues.cgi`.
- It verifies license notice requirements for AGPLv3-only project-owned source headers.

# Recommended Development Workflow

Before accepting application changes, run:

```bash
python3.11 -m py_compile issues.cgi
python3.11 -m pytest -q
```

For every future bug fix:

1. Add a nearby `BUGFIX:` or `REGRESSION GUARD:` comment in the application code when appropriate.
2. Add a pytest regression test that would fail without the bug fix.
3. Run the full regression suite.
4. Preserve the new test in future changes unless the protected behavior is intentionally changed.
