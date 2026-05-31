# Application Overview

**Issues** is a CGI-based web application for tracking issues in an SQLite-backed issue database. It provides a web front end for creating, viewing, editing, assigning, commenting on, closing, canceling, reopening, and attaching files to issues, with access controls based on the acting user, issue ownership, assignment, and system administrator status.

# Implementation Language Requirement

- This application shall be written in Python.

# Python Runtime Compatibility

- The application shall run on Python 3.9 through Python 3.12 unless the supported runtime is intentionally changed.
- The application shall not be treated as Python 3.13-compatible until the dependency on the removed standard-library `cgi` module has been removed or replaced.
- Application code shall avoid Python language features and standard-library APIs introduced after Python 3.9 while Python 3.9 compatibility is required.
- Date/time code shall use Python 3.9-compatible UTC handling, such as `datetime.timezone.utc`, rather than APIs introduced in later Python versions such as `datetime.UTC`.

# Licensing Notice Requirements

- All project-owned Python source files, including `issues.cgi`, helper scripts, and tests, must include a short license header near the top of the file.
- The required SPDX identifier is `SPDX-License-Identifier: AGPL-3.0-only`.
- Project-owned source-file license notices must not use `AGPL-3.0-or-later`, `or later`, `any later version`, or equivalent wording unless the project owner explicitly changes the licensing policy.
- The top-level `LICENSE` file must contain the official, unmodified GNU Affero General Public License version 3 text.
- The official GNU license text itself must not be edited to remove generic explanatory language about later versions; project-owned source notices control whether this project permits later license versions.

# AI/LLM Maintenance Requirements

- AI/LLM assistants modifying this application must read the current `requirements.md` file before making non-trivial changes, unless the user explicitly directs them to proceed without it or to disregard this requirement.
- The requirements document is the authoritative functional specification for routing, schema expectations, access control, validation, form behavior, attachment handling, Markdown rendering, error handling, and redirect behavior.
- Existing behavior, features, access-control checks, validation rules, escaping behavior, filename handling, and database-query behavior must not be removed, simplified, or rewritten unless the requested change explicitly requires it.
- Bug fixes must be documented with nearby `BUGFIX:` or `REGRESSION GUARD:` comments explaining the regression or defect the code prevents.
- Existing bug-fix and regression-guard comments must not be removed unless the user explicitly directs their removal, or unless the associated code is replaced by an equivalent or better fix and the preservation comment is updated accordingly.
- Unless the user explicitly directs otherwise, AI/LLM assistants must produce valid unified diffs only when proposing modifications.
- Patch output must use standard unified diff format, include `---` and `+++` file headers, include `@@` hunk headers, include at least 3 lines of unchanged context around each change, and be directly usable with `git apply` or `patch -p1`.
- Patch output must not include Markdown fences, explanations, or abbreviated unchanged code such as `...`.

# Global Variables

DB_FILE - path to the SQLite database file used by the application  
DEFAULT_CLOSING_COMMENT - default text used when a closing or cancel comment is empty  
MAX_UPLOAD_BYTES - maximum allowed upload size for attachment submissions  
ASSIGNEE_GROUP - group name used to build the assignable user list  
ASSIGNEE_EXCLUDE - comma-separated list of usernames excluded from the assignable user list  
PER_USER_CONFIG_DIR - directory used for per-user preference files  
CONFIG_DEFAULTS - default per-user filter settings stored as a configuration object with named keys  
MAX_FILENAME_LEN - maximum safe length for stored attachment filenames  
STATUSES - comma-separated list of allowed issue status values  
PRIORITIES - comma-separated list of allowed issue priority values  
STATES - comma-separated list of allowed issue state values  
ADMINS_GROUP - name of system administrators group  
ADMINS_GROUP_EXCLUDE - comma-separated list of usernames excluded from the system administrators group  
BANNER_FILE - optional path to the banner image file; an empty value disables the banner image  
BANNER_DIMENSIONS - optional banner image width and height, stored as a width-by-height pair such as `750x54`; an empty value omits explicit banner dimensions  
FAVICON_MIME_TYPE - MIME type used when serving the embedded favicon  
EMBEDDED_FAVICON_BASE64 - Base64-encoded favicon image data embedded in the CGI script  
AUTH_FORM_ACTION - URL to which the login form posts for external form-based authentication  
AUTH_FORM_USERNAME_FIELD - username field name expected by the external form-authentication endpoint  
AUTH_FORM_PASSWORD_FIELD - password field name expected by the external form-authentication endpoint  
AUTH_FORM_LOCATION_FIELD - destination or return-location field name expected by the external form-authentication endpoint  
AUTH_FORM_DEFAULT_LOCATION - default post-login destination used by the login form  
LOGOUT_URL - URL used by the authenticated page logout link  
SITE_CONFIG_FILE - path to the optional site configuration file  
EMAIL_NOTIFICATIONS_ENABLED - boolean value controlling whether issue notification email is submitted to the local mail system  
SENDMAIL_PATH - path to the local sendmail-compatible command used for notification delivery  
NOTIFICATION_FROM - sender address used for notification email  
NOTIFICATION_SUBJECT_PREFIX - prefix used on notification email subject lines  
ISSUE_BASE_URL - optional base URL used to include issue links in notification email bodies  
NOTIFICATION_TRIAGE_RECIPIENTS - fallback notification recipients for unassigned issues  
NOTIFICATION_BODY_MAX_CHARS - maximum number of characters from comment and description text included in notification email bodies  

# Variable Initial Values

DB_FILE - `/var/lib/issues/issues.db`  
DEFAULT_CLOSING_COMMENT - `no closing comment provided`  
MAX_UPLOAD_BYTES - `10485760`  
ASSIGNEE_GROUP - `users`  
ASSIGNEE_EXCLUDE - empty string  
PER_USER_CONFIG_DIR - `/var/lib/issues/config`  
CONFIG_DEFAULTS - `{"status": "open", "priority": "any", "creator": "any", "assignee": "any", "state": "any", "due_date": "any", "has_comments": False, "has_attachments": False, "search": "", "auto_refresh": "never"}`  
MAX_FILENAME_LEN - `255`  
STATUSES - `("any", "open", "closed", "canceled")`  
PRIORITIES - `("any", "high", "normal", "low")`  
STATES - `("not started", "in progress", "deferred", "waiting", "complete")`  
ADMINS_GROUP - `wheel`  
ADMINS_GROUP_EXCLUDE - value user specified  
BANNER_FILE - empty string  
BANNER_DIMENSIONS - empty string
FAVICON_MIME_TYPE - `image/x-icon`
EMBEDDED_FAVICON_BASE64 - embedded icon data kept at the end of `issues.cgi`
AUTH_FORM_ACTION - `/login`
AUTH_FORM_USERNAME_FIELD - `httpd_username`
AUTH_FORM_PASSWORD_FIELD - `httpd_password`
AUTH_FORM_LOCATION_FIELD - `httpd_location`
AUTH_FORM_DEFAULT_LOCATION - `/cgi-bin/issues.cgi`
LOGOUT_URL - `/issues-logout`
SITE_CONFIG_FILE - `/etc/issues.conf`
EMAIL_NOTIFICATIONS_ENABLED - `False`
SENDMAIL_PATH - `/usr/sbin/sendmail`
NOTIFICATION_FROM - `issues@localhost`
NOTIFICATION_SUBJECT_PREFIX - `[Issues]`
ISSUE_BASE_URL - empty string
NOTIFICATION_TRIAGE_RECIPIENTS - `root`
NOTIFICATION_BODY_MAX_CHARS - `8192`

# Site Configuration File

- The application supports an optional site configuration file at `/etc/issues.conf`.
- If `/etc/issues.conf` does not exist, the application uses built-in default values.
- If a supported value is not present in `/etc/issues.conf`, the application uses the built-in default for that value.
- The configuration file uses simple `KEY=value` lines.
- Empty lines are ignored.
- Lines beginning with `#` are ignored.
- Inline `#` comments are ignored.
- Unknown keys are ignored.
- Invalid values are ignored and do not replace built-in defaults.
- The configuration file is plain text and is not executed as code.
- Only documented site configuration keys are read from the file.
- The supported site configuration keys are `DB_FILE`, `DEFAULT_CLOSING_COMMENT`, `MAX_UPLOAD_BYTES`, `ASSIGNEE_GROUP`, `ASSIGNEE_EXCLUDE`, `PER_USER_CONFIG_DIR`, `MAX_FILENAME_LEN`, `ADMINS_GROUP`, `ADMINS_GROUP_EXCLUDE`, `BANNER_FILE`, `BANNER_DIMENSIONS`, `EMAIL_NOTIFICATIONS_ENABLED`, `SENDMAIL_PATH`, `NOTIFICATION_FROM`, `NOTIFICATION_SUBJECT_PREFIX`, `ISSUE_BASE_URL`, `NOTIFICATION_TRIAGE_RECIPIENTS`, and `NOTIFICATION_BODY_MAX_CHARS`.
- Form-authentication variables, logout URL, issue-list page size, and auto-refresh options are not read from `/etc/issues.conf`.
- `EMAIL_NOTIFICATIONS_ENABLED` values from `/etc/issues.conf` must be parsed as a boolean value using documented true/false forms.
- `SENDMAIL_PATH` values from `/etc/issues.conf` must be non-empty absolute paths.
- `NOTIFICATION_FROM` and `NOTIFICATION_SUBJECT_PREFIX` values from `/etc/issues.conf` must be non-empty strings when email notifications are enabled.
- `ISSUE_BASE_URL` values from `/etc/issues.conf` may be empty; when non-empty, the value is used as the base for issue links in notification email bodies.
- `NOTIFICATION_TRIAGE_RECIPIENTS` values from `/etc/issues.conf` may be a comma-separated list of local mail recipients and group references.
- Items in `NOTIFICATION_TRIAGE_RECIPIENTS` beginning with `@` are treated as system group names and expanded to group members using normal system/NSS group lookup.
- `NOTIFICATION_BODY_MAX_CHARS` values from `/etc/issues.conf` must be positive integers.
- `MAX_UPLOAD_BYTES` and `MAX_FILENAME_LEN` values from `/etc/issues.conf` must be positive integers.
- `BANNER_DIMENSIONS` values from `/etc/issues.conf` must be empty or width-by-height values using positive integers, such as `750x54`.

# Presentation Requirements

- A banner image is rendered at the top of every page only when `BANNER_FILE` is not empty.
- When rendered, the banner image uses `BANNER_FILE` as its source.
- When `BANNER_DIMENSIONS` is not empty and contains valid dimensions, the rendered banner image uses `BANNER_DIMENSIONS`.
- When `BANNER_FILE` is empty, no banner image is rendered.
- Every HTML page includes a favicon link in the document head.
- The favicon link points to the CGI favicon action and does not require an external favicon file.
- Markdown help links open in a new browser window or tab.
- Authenticated application pages display the current authenticated username in the page header.
- When an authenticated username is displayed, a logout link appears adjacent to it.
- The logout link is visually distinct from the username and must not appear to be part of the username.
- The logout link text is `Logout`.
- The username is displayed as plain bold text and the logout link is displayed as an underlined link in parentheses, for example: `Current user: redmondd (Logout)`.
- The logout link points to `LOGOUT_URL`.
- The logout link is not displayed on unauthenticated public pages such as the login page, login failed page, logged out page, or authentication error page.

# Data Sources Controlled by Constants or Globals

- SQLite database file: `DB_FILE`
- Optional site configuration file: `SITE_CONFIG_FILE`
- Per-user configuration files: `PER_USER_CONFIG_DIR/<username>.json`
- Assignable user list source: `ASSIGNEE_GROUP`
- Assignable user exclusions: `ASSIGNEE_EXCLUDE`
- Assignable-user dropdown lists are built from explicitly listed members of `ASSIGNEE_GROUP`; users are not added to dropdown lists solely because their primary group id matches `ASSIGNEE_GROUP`.
- System administrator group source: `ADMINS_GROUP`
- System administrator exclusions: `ADMINS_GROUP_EXCLUDE`
- Banner image file: `BANNER_FILE`
- Favicon image data: embedded in `issues.cgi`

# Access and Authentication Requirements

- Normal issue-tracking actions require an authenticated acting user supplied through `REMOTE_USER`.
- The application validates the acting user from `REMOTE_USER` against the configured system user lookup behavior before allowing access to normal issue-tracking actions.
- The application does not validate passwords and does not authenticate users directly.
- Password validation, login success handling, login failure handling, session handling, and logout handling are performed outside the CGI application by the configured HTTP authentication layer.
- The application provides public display-only authentication support pages for use with form-based authentication.
- Public authentication support actions do not require `REMOTE_USER`.
- Public authentication support actions are limited to `login`, `login_failed`, `logged_out`, and `auth_error`.
- The `favicon` action is public and does not require `REMOTE_USER`.
- When a request omits the `action` parameter and `REMOTE_USER` is missing or empty, the application uses `login` as the default action.
- When a request omits the `action` parameter and `REMOTE_USER` is present, the application uses `list` as the default action.
- The `login` action renders a login form that posts to `AUTH_FORM_ACTION`.
- The login form uses the field names defined by `AUTH_FORM_USERNAME_FIELD`, `AUTH_FORM_PASSWORD_FIELD`, and `AUTH_FORM_LOCATION_FIELD`.
- The login form includes a destination field using `AUTH_FORM_DEFAULT_LOCATION` unless a safe destination is supplied. The default destination is `/cgi-bin/issues.cgi`.
- The login form and authentication support pages must not state or imply what authentication mechanism, server module, or backend service is being used.
- The login form and authentication support pages must not mention Apache, PAM, web server authentication, server-side authentication, or similar implementation details in user-facing text.
- The application must not store, log, echo, or otherwise process submitted passwords.
- All normal issue-tracking actions continue to require a valid `REMOTE_USER`.
- If `REMOTE_USER` is missing, empty, or invalid for a protected action, the application returns an authentication or authorization error with an appropriate HTTP status code.

# Error Response Requirements

- Error responses must include an HTTP status header appropriate to the failure.
- Malformed requests, missing required parameters, invalid field values, invalid date formats, invalid percent-complete values, invalid priority values, invalid state values, missing required form values, and invalid attachment submissions must return `400 Bad Request`.
- Authentication failures and authorization failures must return `403 Forbidden`.
- Requests for missing issues, missing comments when directly addressed, missing attachments, or other missing application records must return `404 Not Found`.
- Unexpected internal failures may return `500 Internal Server Error`; routine validation, authentication, authorization, and not-found cases must not be reported as `500 Internal Server Error`.
- Plain text error responses must include `Content-Type: text/plain`.
- HTML error responses, if used, must include `Content-Type: text/html`.
- Authentication support pages render as complete HTML pages with `Content-Type: text/html`.
- Authentication support pages must not expose passwords, environment values, authentication backend details, or server-module details.
- The favicon response uses `FAVICON_MIME_TYPE` as its `Content-Type` and returns non-empty binary image data.

# Database Schema

The application uses an existing SQLite database identified by `DB_FILE`.

## Table: `issues`

Stores the main issue records.

### Columns
- `id` - unique issue identifier
- `title` - issue title
- `description` - issue description text
- `creator_username` - username of the user who created the issue
- `assigned_username` - username of the user assigned to the issue
- `priority` - issue priority
- `pct_complete` - numeric percent complete
- `state` - issue workflow state
- `status` - issue status
- `due_date` - due date value
- `created_at` - creation timestamp
- `updated_at` - last update timestamp
- `completed_at` - completion timestamp when the issue is closed or canceled

### Schema behavior implied by the application
- `id` serves as the primary lookup key for issue views and updates.
- `creator_username` and `assigned_username` store usernames as text.
- `priority` uses values from `PRIORITIES`.
- `state` uses values from `STATES`.
- `status` uses values from `STATUSES`.
- `pct_complete` stores an integer percentage value.
- `due_date` stores a date value that the application formats as `YYYY-MM-DD`.
- `created_at`, `updated_at`, and `completed_at` store timestamp values.

---

## Table: `comments`

Stores issue comments, including Markdown-formatted text.

### Columns
- `id` - unique comment identifier
- `issue_id` - issue identifier that the comment belongs to
- `commenter_username` - username of the user who created the comment
- `comment_text` - raw comment text
- `created_at` - creation timestamp for ordering and display

### Schema behavior implied by the application
- `issue_id` links each comment to a row in `issues`.
- Comments are displayed in reverse chronological order by `created_at`.
- The `created_at` column is required and must be populated when comments are inserted.

---

## Table: `attachments`

Stores uploaded files associated with issues.

### Columns
- `id` - unique attachment identifier
- `issue_id` - issue identifier that the attachment belongs to
- `filename` - stored attachment filename
- `content` - binary file content
- `uploader_username` - username of the user who uploaded the attachment
- `created_at` - creation timestamp for ordering and display

### Schema behavior implied by the application
- `issue_id` links each attachment to a row in `issues`.
- `filename` is displayed in the issue view and used in the download response.
- `content` stores the uploaded file bytes.
- Attachments are displayed in chronological order by `created_at`.
- The `created_at` column is required and must be populated when attachments are inserted.

---

## Table: `issue_history`

Stores compact append-only history entries for material actions taken on issues.

### Columns
- `id` - unique history entry identifier
- `issue_id` - issue identifier that the history entry belongs to
- `actor_username` - username of the user who performed the action
- `action` - compact action type for the history entry
- `summary` - concise user-visible summary of the action
- `comment_id` - optional referenced comment identifier for comment-related history entries
- `attachment_id` - optional referenced attachment identifier for attachment-related history entries
- `created_at` - UTC timestamp when the history entry was recorded

### Schema behavior implied by the application
- `issue_id` links each history entry to a row in `issues`.
- `actor_username` stores the authenticated acting username that performed the action.
- `action` stores a compact machine-readable action name.
- `summary` stores a concise user-visible description of the action.
- `comment_id` is populated only when the history entry refers to a comment.
- `attachment_id` is populated only when the history entry refers to an attachment.
- History entries are append-only during normal application operation.
- History entries are displayed in reverse chronological order by `created_at` and `id`.
- History entries store concise summaries and optional row references rather than full issue snapshots, full comment text, attachment content, or large before-and-after text values.

---

## Relationships

- One issue can have many comments.
- One issue can have many attachments.
- One issue can have many history entries.
- Comments and attachments both belong to exactly one issue through `issue_id`.
- History entries belong to exactly one issue through `issue_id`.
- History entries can optionally reference a comment through `comment_id`.
- History entries can optionally reference an attachment through `attachment_id`.

---

## Required Supporting Data

The database must support:
- issue creation and update operations
- comment insertion and retrieval
- attachment insertion and retrieval
- filtering and listing by issue fields
- joining attachments to issues for download authorization checks
- counting comments and attachments per issue
- recording compact issue history entries
- retrieving issue history for a single issue without loading history for the issue list

---

## Rebuild Notes

To rebuild the application from scratch, the database must provide:
- a unique issue identifier for each issue row
- text fields for title, description, usernames, priority, state, and status
- date/timestamp fields for due, created, updated, and completed values
- comment storage linked to issues
- attachment storage linked to issues
- binary storage for attachment content
- compact append-only history storage linked to issues

# Pages and Forms

## Issue List Page

**Purpose:**
- Show issues in a tabular list.
- Sort issues by issue id in descending order.
- Support a Static filter group containing status, due date, comment presence, attachment presence, and search filters.
- Support a Dynamic filter group containing priority, creator, assignee, and state filters.
- Preserve per-user filter preferences.

**Static data on the page:**
- Table headings
- Percent complete table heading and values
- Static filter group labels
- Dynamic filter group labels
- Pagination navigation controls
- Auto-refresh label
- Last-refreshed indicator
- Link to create a new issue

**User-editable data:**
- Status filter
- Due filter when the status filter is `open` or `any`
- Has comments filter checkbox
- Has attachments filter checkbox
- Search text field
- Priority filter
- Creator filter for system administrators
- Assignee filter
- State filter
- Pagination page dropdown
- Auto-refresh timer dropdown

**Conditional UI elements:**
- The issue list displays percent complete for each listed issue.
- The issue list table displays the columns in this order: ID, Title, Status, Due, Priority, Creator, Assignee, State, % Complete, Comments, Attachments, Updated.
- The issue list table uses the column heading `Assignee`, not `Assigned`.
- The issue view metadata table uses the row label `Assignee`, not `Assigned`.
- Create and assignment form labels use `Assignee`, not `Assigned user`.
- The issue list table uses the column heading `Due`, matching the Due filter label.
- The “All Users Issues” checkbox is not displayed.
- The creator filter dropdown displays only when the acting user is a system administrator.
- For system administrators, the default creator filter is `any`, which shows all users' issues.
- The assignee filter dropdown displays for all users.
- The state filter dropdown displays for all users.
- The Due filter dropdown displays for all users only when the status filter is `open` or `any`.
- The Has comments filter checkbox displays for all users.
- The Has attachments filter checkbox displays for all users.
- The Has comments and Has attachments filter checkboxes submit the filter form immediately when clicked.
- The Has comments and Has attachments filter checkboxes use a click-based submit handler so browsers that defer checkbox change events until blur still apply the filters immediately.
- The Static filter group contains Status, Due, Has comments, Has attachments, and Search.
- The Dynamic filter group contains Priority, Creator, Assignee, and State.
- The Static filter group and Dynamic filter group are visually or structurally separated.
- The Search field is logically part of the Static filter group.
- The Search field appears on the same horizontal row as the other Static filter controls when screen width allows.
- The Status, Due, Has comments, and Has attachments controls appear on the left side of the Static filter row.
- The Search field appears on the right side of the Static filter row.
- The Search field is visually right-aligned within the Static filter row.
- When screen width is insufficient, the Static filter row may wrap, but the Search field remains visually distinct from the Dynamic filter group.
- The Search field width is responsive to browser/window width.
- The Search field has a reasonable minimum width so it remains usable on narrow windows.
- The Search field has a reasonable maximum width so it does not dominate wide pages.
- The Search field grows when additional horizontal space is available and shrinks when horizontal space is constrained.
- The responsive Search field sizing is implemented with CSS and does not require JavaScript.
- The Search field does not have separate Apply or Clear buttons.
- Pressing Enter while focus is in the Search field submits the list filter form and applies the search.
- Clearing the Search field and pressing Enter clears the active search and clears the saved search preference.
- Blank submitted form/query values must be preserved during CGI parsing so intentional clears, including `search=`, are distinguishable from omitted fields.
- In the Dynamic filter group, Priority appears to the left of Creator, Assignee, and State.
- Pagination controls appear above and below the issue list.
- Pagination controls are aligned to the right side of the screen.
- Pagination controls are always present, including when there is only one page of issues.
- The top issue-list control row places the “Create new issue” link and the upper pagination controls on the same horizontal line, with the create link on the left and the pagination controls on the right.
- The auto-refresh timer dropdown appears below the issue list.
- The auto-refresh timer dropdown is aligned to the left side of the screen.
- The auto-refresh label appears to the left of the dropdown and reads `Auto-refresh`.
- A last-refreshed indicator appears in parentheses immediately to the right of the auto-refresh dropdown box.
- The last-refreshed indicator text is slightly smaller than the Auto-refresh label text.
- The bottom issue-list control row places the auto-refresh control and the lower pagination controls on the same horizontal line, with auto-refresh on the left and pagination controls on the right.
- Filter selections default from the acting user’s per-user configuration when the form is not submitted.
- List filters are saved and applied when the user changes any filter value.
- The “Create new issue” link always displays.

**Filter behavior:**
- The Static filter group is applied before the Dynamic filter group.
- The Dynamic filter group is applied after the Static filter group.
- The status filter supports `any`, `open`, `closed`, and `canceled` values.
- The status filter displays the options in this order: `any`, `open`, `closed`, `canceled`.
- The Due filter label text is `Due`.
- The Due dropdown options are `any`, `no due date`, `today`, `within 5 days`, and `within 30 days`.
- The Due option `any` matches all due-date values and issues with no due date.
- The Due option `no due date` matches issues that do not have a due date.
- The Due option `today` matches issues due on the current UTC date.
- The Due option `within 5 days` matches issues due within the next 5 UTC days.
- The Due option `within 30 days` matches issues due within the next 30 UTC days.
- The Has comments checkbox limits the issue list to issues with one or more comments when selected.
- The Has attachments checkbox limits the issue list to issues with one or more attachments when selected.
- The Search field searches issue title, issue description, comment text, and attachment metadata.
- Attachment metadata search includes attachment filename, uploader username, and attachment creation timestamp.
- Attachment file content is not searched.
- Search uses parameterized SQL and does not concatenate user input into SQL.
- Search treats SQL LIKE wildcard characters in the search text as literal characters.
- Search is applied only within the acting user's authorized issue visibility scope.
- Static filters, including Search, are applied before Dynamic filter group options are generated.
- Dynamic filter options reflect the current Search value.
- Search is applied before pagination.
- Search text is saved and restored as a per-user list preference.
- Page navigation and auto-refresh preserve the active Search value.
- Search actions do not create issue-history entries.
- Search actions do not send notification email.
- When the Has comments checkbox is unchecked, the saved `has_comments` preference is cleared.
- When the Has attachments checkbox is unchecked, the saved `has_attachments` preference is cleared.
- Priority, Creator, Assignee, and State dropdown options are generated from issue rows that match the current Static filter group settings before Dynamic filter group filters are applied.
- The Priority dropdown includes an `any` option.
- Priority dropdown options other than `any` are generated from matching issue rows and use values from `PRIORITIES`.
- The Creator dropdown includes an `any` option for system administrators.
- The Assignee dropdown includes an `any` option.
- The Assignee dropdown includes an `unassigned` option when matching issues include rows with no assigned user.
- The State dropdown includes an `any` option.

**Pagination behavior:**
- Pagination is applied after all active issue-list filters are applied.
- The issue list displays a maximum of 25 issues per page.
- Pagination navigation includes a Previous control and a Next control.
- Pagination navigation includes a page dropdown between Previous and Next.
- The page dropdown displays the current page in `x of y` form, where `x` is the current page and `y` is the total number of pages.
- The page dropdown acts as both the current-page indicator and a direct navigation control for selecting a specific page.
- Previous, Next, and direct page navigation preserve active filters and user preference values.
- Missing, invalid, non-numeric, or out-of-range page values are handled safely by selecting a valid page.
- When active filters change and the current page is no longer valid, the selected page is normalized to a valid page.

**Auto-refresh behavior:**
- The auto-refresh dropdown options are `never`, `5 minutes`, `10 minutes`, `20 minutes`, and `30 minutes`.
- The default auto-refresh value is `never`.
- The selected auto-refresh value is saved to the acting user's preference file.
- The saved auto-refresh value is reloaded when the issue list is displayed.
- When the auto-refresh value is not `never`, the issue list page automatically refreshes after the selected period.
- Auto-refresh preserves active filters and current list state where applicable.
- The last-refreshed indicator uses the format `(Last refreshed: <relative time>)`.
- Immediately after the issue list page loads, the last-refreshed indicator displays `(Last refreshed: just now)`.
- After one minute, the last-refreshed indicator displays `(Last refreshed: 1 minute ago)`.
- After two or more minutes, the last-refreshed indicator displays `(Last refreshed: <n> minutes ago)`.
- The last-refreshed indicator updates automatically once per minute without reloading the page.
- The last-refreshed source timestamp is generated by the server in UTC.
- The relative-time display is calculated in the browser from the server-provided UTC refresh timestamp.
- The last-refreshed indicator does not display an absolute timestamp.

**Access control:**
- Non-administrators do not receive the creator filter.
- Non-administrators can use the due-date, Has comments, Has attachments, priority, assignee, and state filters only within issues they are otherwise authorized to see.
- System administrators see all users' issues by default and can use the creator filter to limit the list to a specific creator.

**Persistent preferences:**
- Filter defaults are stored per user in files under `PER_USER_CONFIG_DIR`.
- Updated filter values are saved when the user changes any list filter value.
- All Static and Dynamic filter group preferences, including Search, are saved and read in the same manner as the status filter.
- The auto-refresh preference is saved and read in the same manner as list filter preferences.

---

## Issue View Page

**Purpose:**
- Show a single issue with metadata, description, comments, and attachments.
- Provide action links and inline edit controls based on role and issue status.

**Static data on the page:**
- Issue title label and section labels
- Action labels
- Comments and attachments section labels
- Issue history link or action label

**User-editable data:**
- Assignee, if editable
- Priority, if editable
- Percent complete, if editable
- State, if editable
- Due date, if editable
- Comment and attachment actions through linked forms

**Conditional UI elements:**
- The issue page displays only when the issue exists.
- The acting user requires access to the issue: the acting user is the issue owner, the assigned user, or a system administrator.
- **Edit Title & Description** displays only when the issue is open and the acting user is the issue owner or a system administrator.
- **Close** displays only when the issue is open and the acting user is the issue owner, the assigned user, or a system administrator.
- **Cancel** displays only when the issue is open and the acting user is the issue owner.
- **Re-open** displays only when the issue is not open and the acting user is a system administrator.
- Assignee editing displays only when the issue is open and the acting user is the issue owner or a system administrator.
- Priority editing displays only when the issue is open and the acting user is the issue owner or a system administrator.
- Percent complete editing displays only when the issue is open and the acting user is the assigned user.
- State editing displays only when the issue is open and the acting user is the assigned user.
- Due date editing displays only when the issue is open and the acting user is the issue owner or a system administrator.
- When the issue is not open and the due date value is empty, the due date is displayed as a blank value.
- Assignee, Priority, and State field changes are saved when the user changes the corresponding field value.
- Percent complete and Due date values are saved when the user clicks the corresponding button.
- The Percent complete button and Due date button are not clickable until the user changes the value of the corresponding field.
- Issue view action items use a consistent UI element form; action items must not mix links, buttons, and other control styles.
- The **Add** comment link displays only when the acting user is the issue owner, the assigned user, or a system administrator.
- The **Add** attachment link displays only when the acting user is the issue owner, the assigned user, or a system administrator.
- Completed-at information displays only when the issue status is closed or canceled.
- A history link or action displays for users who are authorized to view the issue.

**Access control:**
- Viewing requires that the acting user is the issue owner, assigned user, or a system administrator.
- Editing links and inline editors are role- and state-restricted as listed above.

---

## Login Page

**Purpose:**
- Render a public login form for form-based authentication.

**Static data on the page:**
- Page title
- Banner image
- Username label
- Password label
- Login button

**User-editable data:**
- Username
- Password

**Conditional UI elements:**
- The page displays a concise sign-in prompt such as `Please sign in.`
- The page does not display implementation details about the authentication mechanism.
- The page does not mention Apache, PAM, web server authentication, server-side authentication, or similar implementation details.

**Conditional behavior:**
- The login page is available without `REMOTE_USER`.
- The login form uses method `post`.
- The login form posts to `AUTH_FORM_ACTION`.
- The login form includes a username input named by `AUTH_FORM_USERNAME_FIELD`.
- The login form includes a password input named by `AUTH_FORM_PASSWORD_FIELD`.
- The login form includes a destination or return-location input named by `AUTH_FORM_LOCATION_FIELD`.
- The destination value is safely escaped before rendering.
- The application does not validate the submitted password.
- The application does not echo submitted password values.

**Access control:**
- No authenticated user is required to render this page.

---

## Login Failed Page

**Purpose:**
- Render a public page explaining that login failed.

**Static data on the page:**
- Page title
- Banner image
- Failure message
- Link or control returning to the login page

**Conditional behavior:**
- The page is available without `REMOTE_USER`.
- The page provides a way to return to the login page.
- The page does not display implementation details about the authentication mechanism.
- The page does not mention Apache, PAM, web server authentication, server-side authentication, or similar implementation details.
- The page must not display passwords or sensitive authentication details.

**Access control:**
- No authenticated user is required to render this page.

---

## Logged Out Page

**Purpose:**
- Render a public page explaining that the user has logged out.

**Static data on the page:**
- Page title
- Banner image
- Logout message
- Link or control returning to the login page

**Conditional behavior:**
- The page is available without `REMOTE_USER`.
- The page provides a way to return to the login page.
- The page does not display implementation details about the authentication mechanism.

**Access control:**
- No authenticated user is required to render this page.

---

## Authentication Error Page

**Purpose:**
- Render a page explaining that the user could not be accepted by the application.

**Static data on the page:**
- Page title
- Banner image
- Generic authentication or authorization problem message
- Link or control returning to the login page or issue list as appropriate

**Conditional behavior:**
- The page is available without requiring a valid application user.
- The page does not display implementation details about the authentication mechanism.
- The page does not mention Apache, PAM, web server authentication, server-side authentication, or similar implementation details.
- The page must not display passwords, raw environment values, system lookup internals, or sensitive authentication details.

**Access control:**
- No valid application user is required to render this page.

---

## Issue History Page

**Purpose:**
- Show compact history entries for actions taken on a single issue.
- Avoid loading or displaying history on the issue list page or ordinary issue view unless the user explicitly opens the issue history page or explicitly requests history.

**Static data on the page:**
- Issue identifier or issue title context
- History section label
- History entry rows
- Pagination controls above and below the history entry rows

**User-editable data:**
- None

**Conditional UI elements:**
- The issue history page displays only when the issue exists.
- History entries are displayed newest first.
- Issue history display uses pagination controls consistent with the issue list page pagination controls.
- The issue history page displays a maximum of 25 history entries per page.
- Pagination controls appear above and below the history entry rows.
- Pagination controls are aligned to the right side of the history page content area.
- Pagination controls are always present, including when there is only one page of history entries.
- Pagination navigation includes a Previous control and a Next control.
- Pagination navigation includes a page dropdown between Previous and Next.
- The page dropdown displays the current history page in `x of y` form, where `x` is the current history page and `y` is the total number of history pages.
- The page dropdown acts as both the current-page indicator and a direct navigation control for selecting a specific history page.
- Previous, Next, and direct page navigation preserve the issue id.
- Missing, invalid, non-numeric, or out-of-range history page values are handled safely by selecting a valid page.
- Each history entry displays the action timestamp, acting username, action type, and a concise self-contained summary.
- Field-change history summaries visually distinguish old and new values.
- Old and new values in field-change history summaries are displayed as quoted bold text.
- Underlining is not used for old and new values because underlined text can be confused with links.
- The issue history page does not display a separate Reference column.
- Comment-related history summaries include a short excerpt made from the first few words of the referenced comment.
- Comment-related history entries do not duplicate the full comment text in the history table.
- Attachment-related history summaries include referenced attachment metadata, such as the filename.
- Attachment-related history entries do not duplicate attachment file content in the history table.
- Attachment-related history display selects attachment metadata only and must not select the attachment `content` BLOB.
- Title changes may display truncated before-and-after title values.
- Long title values in history summaries are truncated before storage or display.
- Description changes are summarized without storing the full previous description, full new description, or a full text diff in the history entry.
- Description summaries may include compact metadata such as line counts, character counts, or that description content changed.
- If both title and description are changed in the same action, the history entry may summarize both changes in one concise entry.
- Ordinary page views, issue-list filtering, pagination, auto-refresh, and attachment downloads are not recorded as issue history.

**Access control:**
- Viewing issue history requires the same authorization as viewing the issue: the acting user is the issue owner, the assigned user, or a system administrator.
- Unauthorized users must not be able to view issue history by calling the history action directly.

---

## Create Issue Form

**Purpose:**
- Present the form for creating a new issue.

**Static data on the page:**
- Form labels
- Markdown help link text
- Markdown help link opens in a new browser window or tab
- Priority option labels
- Due date format hint text
- Submit button label

**User-editable data:**
- Title
- Description
- Priority
- Due date
- Assignee

**Conditional UI elements:**
- The assignee dropdown includes usernames from the assignable user list.
- The empty assignee option always displays.

**Access control:**
- No explicit role restriction for rendering the form.

---

## Create Issue Submission

**Purpose:**
- Create a new issue from submitted form data.

**User-editable inputs:**
- Title
- Description
- Priority
- Due date
- Assignee

**Conditions required:**
- Title is required.
- Description is required.
- If an assignee is supplied, the assignee must exist on the system.
- If an assignee is supplied, the assignee must be allowed by the assignable-user rules derived from `ASSIGNEE_GROUP` and `ASSIGNEE_EXCLUDE`.
- Existing system users who are not in the assignable-user list must be rejected as assignees.
- Users excluded by `ASSIGNEE_EXCLUDE` must be rejected as assignees even if they belong to `ASSIGNEE_GROUP`.

**Access control:**
- The acting user becomes the creator of the new issue.
- No special role restriction for submitting the creation request.

---

## Assign Form and Assignment Action

**Purpose:**
- Update the assigned user for an open issue.

**User-editable inputs:**
- Assignee username

**Conditions required:**
- The issue exists.
- The target username exists on the system.
- The target username is allowed by the assignable-user rules derived from `ASSIGNEE_GROUP` and `ASSIGNEE_EXCLUDE`.
- Existing system users who are not in the assignable-user list must be rejected as assignment targets.
- Users excluded by `ASSIGNEE_EXCLUDE` must be rejected as assignment targets even if they belong to `ASSIGNEE_GROUP`.
- The issue is open.

**Access control:**
- Only the issue creator or a system administrator can assign the issue.

**Conditional UI behavior:**
- The assignment control on the issue view displays only for open issues when the acting user is the issue owner or a system administrator.
- The assignee value is saved when the user changes the assignee field value on the issue view page.

---

## Attach File Form

**Purpose:**
- Present the file upload form for an issue attachment.

**Static data on the page:**
- File upload label
- Maximum upload size label
- Submit button label

**User-editable data:**
- File selection

**Conditional UI elements:**
- The page displays the maximum upload size derived from `MAX_UPLOAD_BYTES`.
- The maximum upload size is displayed in MB.

**Conditions required:**
- The issue exists.

**Access control:**
- Only the issue owner, assigned user, or a system administrator can render the attachment form.
- Unauthorized users must not be able to render the attachment form by calling the form action directly.

---

## Attach File Submission

**Purpose:**
- Store an uploaded file as an attachment for an issue.

**User-editable inputs:**
- Uploaded file

**Conditions required:**
- The issue exists.
- A file is supplied.
- The uploaded file size does not exceed `MAX_UPLOAD_BYTES`.
- The stored filename is normalized and limited to `MAX_FILENAME_LEN`.

**Access control:**
- Only the issue owner, assigned user, or a system administrator can attach a file.

**Conditional behavior:**
- Uploads that exceed the maximum size are rejected.
- Missing file data is rejected.

---

## Download Attachment Action

**Purpose:**
- Deliver an attachment as a downloadable file.

**Conditions required:**
- The attachment exists.

**Access control:**
- Only the issue owner, assigned user, or a system administrator can download the attachment.

**Conditional behavior:**
- A missing attachment id returns an error.
- A missing attachment record returns an error.
- Unauthorized access returns an error.

---

## Comment Form

**Purpose:**
- Present the comment entry form for an issue.

**Static data on the page:**
- Comment label
- Markdown help link text
- Markdown help link opens in a new browser window or tab
- Submit button label

**User-editable data:**
- Comment text

**Conditions required:**
- The issue exists.

**Access control:**
- If the issue is open, only the issue owner, assigned user, or a system administrator can render the comment form.
- If the issue is not open, only a system administrator can render the comment form.
- Unauthorized users must not be able to render the comment form by calling the form action directly.

---

## Comment Submission

**Purpose:**
- Add a comment to an issue.

**User-editable inputs:**
- Comment text

**Conditions required:**
- The issue exists.
- Comment text is not empty after trimming.

**Access control:**
- If the issue is open, only the issue owner, assigned user, or a system administrator can comment.
- If the issue is not open, only a system administrator can comment.

**Conditional behavior:**
- Empty comments are rejected.
- Permission checks vary by issue status.

---

## Update Issue Form

**Purpose:**
- Present a form for editing the issue title and description.

**Static data on the page:**
- Title label
- Description label
- Markdown help link text
- Markdown help link opens in a new browser window or tab
- Submit button label

**User-editable data:**
- Title
- Description

**Conditions required:**
- The issue exists.
- The issue is open.

**Access control:**
- Only the issue owner or a system administrator can render the update form.
- Unauthorized users must not be able to render the update form by calling the form action directly.

**Conditional behavior:**
- The form is populated from the current issue data when the issue exists.

---

## Update Issue Submission

**Purpose:**
- Update issue title and optionally description.

**User-editable inputs:**
- Title
- Description

**Conditions required:**
- The issue exists.
- The issue is open.

**Access control:**
- Only the issue owner or a system administrator can update the issue.

**Conditional behavior:**
- If description is omitted, only the title updates.
- If description is supplied, both title and description update.

---

## Set Priority Inline Action

**Purpose:**
- Update issue priority.

**User-editable inputs:**
- Priority

**Conditions required:**
- The issue exists.
- The issue status is open.
- Priority is one of the allowed priority values.

**Access control:**
- Only the issue owner or a system administrator can set priority.

**Conditional UI elements:**
- The priority selector displays on the issue view only when the issue is open and the acting user is the issue owner or a system administrator.
- The priority value is saved when the user changes the priority field value.

---

## Set Due Date Inline Action

**Purpose:**
- Update issue due date.

**User-editable inputs:**
- Due date

**Conditions required:**
- The issue exists.
- The issue status is open.
- The due date matches the required date format.
- The due date is later than the current UTC date.

**Access control:**
- Only the issue owner or a system administrator can set the due date.

**Conditional UI elements:**
- The due date editor displays on the issue view only when the issue is open and the acting user is the issue owner or a system administrator.
- The due date button is not clickable until the user changes the due date field value.
- When no due date exists on an open issue, the input shows a placeholder string in the field.
- When the issue is not open and no due date exists, the due date value is displayed as blank.

---

## Set Percent Complete Inline Action

**Purpose:**
- Update percent complete for an issue.

**User-editable inputs:**
- Percent complete

**Conditions required:**
- The issue exists.
- The issue status is open.
- The value is an integer between 0 and 100.

**Access control:**
- Only the assigned user can set percent complete.

**Conditional UI elements:**
- The percent complete editor displays on the issue view only when the issue is open and the acting user is the assigned user.
- The percent complete value is saved when the user clicks the percent complete button.
- The percent complete button is not clickable until the user changes the percent complete field value.

---

## Set State Inline Action

**Purpose:**
- Update issue state.

**User-editable inputs:**
- State

**Conditions required:**
- The issue exists.
- The issue status is open.
- The state is one of the allowed state values.

**Access control:**
- Only the assigned user can set state.

**Conditional UI elements:**
- The state selector displays on the issue view only when the issue is open and the acting user is the assigned user.
- The state value is saved when the user changes the state field value.

**Conditional behavior:**
- Setting the issue state to `complete` also sets percent complete to `100`.
- The percent-complete update occurs whenever state becomes `complete`, including indirect state updates performed by other actions.

---

## Close Issue Form

**Purpose:**
- Present a form for closing an issue with an optional closing comment.

**Static data on the page:**
- Closing comment label
- Markdown help link text
- Markdown help link opens in a new browser window or tab
- Submit button label

**User-editable data:**
- Closing comment

**Conditions required:**
- The issue id is present.
- The acting user is permitted to close the issue.

**Access control:**
- The acting user can close the issue only when the acting user is the issue owner, the assigned user, or a system administrator.

**Conditional behavior:**
- The form renders only after the permission check succeeds.

---

## Close Issue Submission

**Purpose:**
- Close an issue, store a closing comment, and mark completion data.

**User-editable inputs:**
- Optional closing comment

**Conditions required:**
- The issue exists.
- The acting user is permitted to close the issue.
- If the comment is empty or missing, the default closing comment is used.

**Access control:**
- The acting user can close the issue only when the acting user is the issue owner, the assigned user, or a system administrator.

**Conditional behavior:**
- The comment input accepts either of two field names.
- The issue becomes closed and completed when the action succeeds.
- Closing an issue sets the issue state to `complete`.
- Closing an issue also sets percent complete to `100` because the issue state becomes `complete`.

---

## Re-open Issue Action

**Purpose:**
- Re-open a closed or canceled issue and optionally store a comment.

**User-editable inputs:**
- Optional comment

**Conditions required:**
- The issue exists.
- The acting user is a system administrator.
- The current status is closed or canceled.

**Access control:**
- Only a system administrator can re-open an issue.

**Conditional behavior:**
- If the issue status is not closed or canceled, the action does not change the issue.
- The comment input accepts either of two field names.
- If a comment is supplied and empty, the default closing comment is used.

---

## Cancel Issue Form

**Purpose:**
- Present a form for canceling an issue with an optional comment.

**Static data on the page:**
- Cancel comment label
- Markdown help link text
- Markdown help link opens in a new browser window or tab
- Submit button label

**User-editable data:**
- Cancel comment

**Conditions required:**
- The issue exists.
- The acting user is the issue owner.
- The issue status is open.

**Access control:**
- Only the issue owner can cancel the issue.

**Conditional behavior:**
- The form renders only when the permission and status checks succeed.

---

## Cancel Issue Submission

**Purpose:**
- Cancel an issue, store a cancel comment, and mark completion data.

**User-editable inputs:**
- Optional cancel comment

**Conditions required:**
- The issue exists.
- The acting user is the issue owner.
- The issue status is open.
- If the comment is empty or missing, the default closing comment is used.

**Access control:**
- Only the issue owner can cancel the issue.

**Conditional behavior:**
- The comment input accepts either of two field names.
- The issue becomes canceled and completed when the action succeeds.

---

## Markdown Help Page

**Purpose:**
- Display Markdown syntax help for issue, comment, and closing-comment entry.

**Static data on the page:**
- Help text content
- Markdown examples
- Page title
- Informational note text

**User-editable data:**
- None

**Conditional UI elements:**
- The page includes the same help content for users who open it.
- Numbered-list help items in the rendered Markdown examples are displayed as numbered list items.
- Bulleted-list help items in the rendered Markdown examples are displayed as bulleted list items.
- The rendered Markdown examples keep bulleted-list and numbered-list examples as separate lists, not as a single nested or merged list.
- The Markdown help page does not include a second duplicate hard-coded unordered-list or ordered-list section outside the rendered Markdown example.
- The Markdown help page includes a GitLab-style strikethrough example using double tildes, such as `~~struck text~~`.
- Strikethrough examples display as strikethrough text.
- The help is linked from forms that accept Markdown content.
- Markdown help links from forms open this page in a new browser window or tab.

**Access control:**
- No explicit role restriction.

# Additional Functional Requirements

## Issue History
- The application records a compact history entry when an issue is created or materially changed.
- History entries are stored in the `issue_history` table, separate from the main issue record.
- History entries are append-only during normal application operation.
- History entries include issue id, acting username, action type, concise summary text, optional comment id, optional attachment id, and UTC creation timestamp.
- History entries store concise summaries and optional row references rather than full issue snapshots.
- History entries do not store attachment content.
- History entries do not store full comment text.
- History entries do not store full previous descriptions, full new descriptions, or full text diffs for description changes.
- When notification email is successfully submitted to the local mail system, the application records a compact issue-history entry.
- Email notification history entries include the notification recipient or recipients.
- Email notification history entries do not store the email body, subject line, attachments, full headers, SMTP transcript, or delivery status details.
- Email notification history entries are created only after the issue action succeeds and the notification is accepted by the local mail command.
- Comment history entries reference the related comment by `comment_id`.
- Attachment history entries reference the related attachment by `attachment_id`.
- Attachment history display uses attachment metadata and does not read or return the attachment content BLOB.
- Comment and attachment display details are included in the concise Summary column rather than in a separate Reference column.
- Field-change history summaries visually distinguish old and new values using quoted bold text.
- Title-change summaries may include truncated before-and-after title values.
- Description-change summaries use compact metadata such as character counts, line counts, or that description content changed.
- History is not loaded, queried, or displayed on the issue list page.
- History is displayed only when the user explicitly opens the issue history page or explicitly requests history for an issue.
- The issue history page is accessible only to users who are authorized to view the issue.
- History entries are displayed newest first.
- Issue history display uses pagination controls consistent with the issue list page pagination controls.
- The issue history page displays a maximum of 25 history entries per page.
- Issue history pagination includes Previous, page-dropdown, and Next controls in the same order and style as issue list pagination.
- Issue history pagination preserves the issue id during page navigation.
- Missing, invalid, non-numeric, or out-of-range issue history page values are handled safely by selecting a valid page.
- Attachment downloads and ordinary page views are not recorded as issue history.

## Email Notifications
- The application supports optional notification email submitted through a local sendmail-compatible command.
- Notification email support is disabled by default.
- When notification email support is enabled, the application uses `SENDMAIL_PATH` to submit plain-text email to the local mail system.
- The application does not connect directly to a remote SMTP server and does not store SMTP credentials.
- Local mail delivery, local mailbox routing, aliases, forwarding, and relay-host behavior are handled by the host's local mail system outside the CGI application.
- Notification recipients are derived from issue usernames, such as creator and assignee usernames, and are submitted to the local mail system as local recipient names unless the implementation requirements are intentionally changed.
- Notification email may include a direct issue link only when `ISSUE_BASE_URL` is non-empty.
- Notification email never includes attachment content.
- Notification email is sent only after the triggering issue action succeeds.
- Failure to send notification email does not roll back or prevent the issue action that triggered the notification.
- Notification email failures may be written to server-side error output or logs, but they do not produce a user-visible failure for an otherwise successful issue action.
- Notification email is not sent for ordinary page views, issue list filtering, pagination, auto-refresh, history page views, or attachment downloads.
- Initial notification triggers include issue creation, assignment or reassignment, comment submission, attachment submission, title/description update, issue close, issue reopen, and due-date changes.
- Assignment notification email is sent to the newly assigned user when the issue is assigned or reassigned and the newly assigned user is not the acting user.
- When an issue is reassigned from one non-empty assignee to a different non-empty assignee, notification email is also sent to the previously assigned user unless the previously assigned user is the acting user.
- The acting user who performed the triggering action is not sent a notification for that same action unless the implementation requirements are intentionally changed.
- When a notification-triggering action on an unassigned issue would otherwise have no non-actor recipient, notification email is sent to the triage recipients configured by `NOTIFICATION_TRIAGE_RECIPIENTS`.
- The default `NOTIFICATION_TRIAGE_RECIPIENTS` value is `root`.
- `NOTIFICATION_TRIAGE_RECIPIENTS` may contain a comma-separated mixture of local mail recipient names and `@group` references.
- Group references in `NOTIFICATION_TRIAGE_RECIPIENTS` are expanded through normal system/NSS group lookup, not by manually reading `/etc/group`.
- Triage recipients are local mail recipients and are not required to be assignable issue users.
- Duplicate triage recipients are removed while preserving order.
- The acting user is excluded from triage recipients in the same way the acting user is excluded from ordinary notification recipients.
- If no recipient remains after actor exclusion, no notification email is sent and no `email_sent` history entry is recorded.
- Comment notification email bodies include the submitted comment text, capped by `NOTIFICATION_BODY_MAX_CHARS`.
- Attachment notification email bodies include attachment metadata such as filename, uploader, creation timestamp, and file size.
- Attachment notification email bodies do not include attachment file content and do not attach the uploaded file.
- Title/description update notification email bodies include the updated title and updated description, with each text field capped by `NOTIFICATION_BODY_MAX_CHARS`.
- Notification email bodies may include the issue id, issue title, action, acting user, current status, current priority, current due date, and issue link when `ISSUE_BASE_URL` is configured.
- When notification body content is truncated, the email body indicates that content was truncated.

## Per-User Configuration
- The application stores and reads user preferences from disk-based JSON files under `PER_USER_CONFIG_DIR`.
- The configuration file path uses the current user name.
- The application applies only allowed status, priority, creator, assignee, state, due-date, `has_comments`, `has_attachments`, and `auto_refresh` values from the stored configuration.
- The application no longer stores or applies an all-users list filter preference.
- All Static and Dynamic filter group preferences, including Search, are saved and read in the same manner as the status filter.
- The auto-refresh preference is saved and read in the same manner as list filter preferences.

## Issue, Comment, Attachment, and History Storage
- The application stores issues, comments, attachments, and issue history in the SQLite database identified by `DB_FILE`.
- The issue list displays percent complete, comment counts, and attachment counts.
- The issue list sorts issues by issue id in descending order.
- The issue list supports filtering by status, priority, creator, assignee, state, due-date range, comment presence, and attachment presence.
- The issue list supports pagination after filters are applied.
- The issue view shows comments in reverse chronological order.
- The issue view shows attachments in chronological order.
- The issue history page shows issue history entries in reverse chronological order.

## Embedded Favicon
- The application provides a favicon without requiring an external favicon file.
- The favicon image data is embedded in the CGI script as Base64 data.
- The embedded favicon payload is kept at the end of `issues.cgi` so normal code review does not require scrolling past the icon data.
- The favicon is served through the public `favicon` CGI action.
- The favicon action does not require `REMOTE_USER`.
- Every HTML page includes a favicon link in the document head.
- The favicon response uses the correct image content type and returns binary image data.

## Date and Time Handling
- Timezone-aware date and timestamp values are stored in UTC.
- Timezone-aware date and timestamp values are displayed in the browser's local time zone.
- Displayed timestamps include the browser-local time zone abbreviation when available.
- Issue-list due-date filters that compare against the current date use the current UTC date.

## Attachment Handling
- Attachment filenames are normalized before storage and before download.
- Upload size is limited by `MAX_UPLOAD_BYTES`.
- Stored filenames are limited by `MAX_FILENAME_LEN`.

## Markdown Rendering
- Issue descriptions, comments, closing comments, and cancel comments can contain Markdown.
- Supported Markdown list syntax is rendered as real unordered or ordered HTML lists wherever the active renderer supports that syntax.
- GitLab-style strikethrough syntax using double tildes, such as `~~struck text~~`, renders as strikethrough text.
- Strikethrough rendering is safe and does not allow unsafe HTML or script content to execute.
- When the optional Markdown package is unavailable, the fallback renderer safely escapes input and still renders supported unordered-list and ordered-list block syntax as real list elements instead of paragraph text with line breaks.
- When the optional Markdown package is unavailable, the fallback renderer safely renders supported GitLab-style strikethrough syntax.
- The application provides a help page describing supported Markdown syntax.

## Routing Behavior
- Public authentication support actions are dispatched through the same `issues.cgi?action=...` routing model as other actions.
- If `action` is missing and `REMOTE_USER` is missing or empty, the dispatcher uses `login` as the default action.
- If `action` is missing and `REMOTE_USER` is present, the dispatcher uses `list` as the default action.
- Public authentication support actions bypass the normal `REMOTE_USER` requirement.
- The `favicon` action bypasses the normal `REMOTE_USER` requirement.
- All non-public actions other than `favicon` require valid `REMOTE_USER`.

## Redirect Behavior
- Create, assign, comment, update, priority update, due date update, percent update, state update, close, reopen, and cancel actions redirect back to the issue view or list after success.
