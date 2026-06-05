#!/usr/bin/env python3
# Copyright (C) 2026 David Redmond
# SPDX-License-Identifier: AGPL-3.0-only
#
"""
Create a temporary demo database for the Issues CGI application.

This script does not touch /var/lib/issues/issues.db. By default it creates:

    /tmp/issues_demo.db

The demo data uses fake usernames instead of the account running the script.
The generated issue histories also include example notification-email activity rows:

    casey      - small business office manager / primary issue creator
    jordan     - operations manager / secondary issue creator
    morgan     - IT support technician / primary assignee
    jamie      - IT support technician / secondary assignee
    rileyadmin - IT administrator

For the live CGI app to display these issues normally, the authenticated
REMOTE_USER must be one of those users, or a real account recognized by the app
as an administrator. For screenshot-only use, you can either create matching
temporary local users/groups or adjust the fake names below to match accounts
available in your test environment.

Example:

    python3 create_demo_issues_db_fake_users.py --force

Or choose your own fake names:

    python3 create_demo_issues_db_fake_users.py --creator dana --creator2 robin --tech morgan --tech2 jamie --admin patadmin --force
"""

import argparse
import sqlite3
from pathlib import Path
from typing import Optional


def utc(day: int, hour: int, minute: int = 0) -> str:
    return f"2026-05-{day:02d}T{hour:02d}:{minute:02d}:00+00:00"


def create_schema(con: sqlite3.Connection) -> None:
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

        CREATE INDEX idx_comments_issue_id ON comments(issue_id);
        CREATE INDEX idx_attachments_issue_id ON attachments(issue_id);
        CREATE INDEX idx_issue_contributing_users_issue_user
        ON issue_contributing_users(issue_id, contributing_username);
        CREATE INDEX idx_issue_history_issue_id_created_at
        ON issue_history(issue_id, created_at DESC, id DESC);
        """
    )


def add_history(
    con: sqlite3.Connection,
    issue_id: int,
    actor: str,
    action: str,
    summary: str,
    created_at: str,
    comment_id: Optional[int] = None,
    attachment_id: Optional[int] = None,
) -> None:
    con.execute(
        """
        INSERT INTO issue_history
            (issue_id, actor_username, action, summary, comment_id, attachment_id, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (issue_id, actor, action, summary, comment_id, attachment_id, created_at),
    )


def add_email_history(
    con: sqlite3.Connection,
    issue_id: int,
    actor: str,
    recipients: str,
    created_at: str,
) -> None:
    # Demo notification history rows intentionally include only recipients.
    # They do not include email bodies, subject lines, headers, delivery status,
    # SMTP transcripts, or attachment contents.
    add_history(
        con,
        issue_id,
        actor,
        "email_sent",
        f"Notification email sent to {recipients}",
        created_at,
    )


def add_comment(
    con: sqlite3.Connection,
    issue_id: int,
    actor: str,
    text: str,
    created_at: str,
    time_worked_minutes: Optional[int] = None,
) -> int:
    cur = con.execute(
        """
        INSERT INTO comments (issue_id, commenter_username, comment_text, time_worked_minutes, created_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (issue_id, actor, text, time_worked_minutes, created_at),
    )
    comment_id = int(cur.lastrowid)
    add_history(con, issue_id, actor, "comment_added", "Added comment", created_at, comment_id=comment_id)
    return comment_id


def add_attachment(
    con: sqlite3.Connection,
    issue_id: int,
    actor: str,
    filename: str,
    created_at: str,
) -> int:
    # Intentional empty BLOB: enough for the app to display attachment metadata
    # and counts for screenshots, without creating real file content.
    cur = con.execute(
        """
        INSERT INTO attachments (issue_id, filename, content, uploader_username, created_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (issue_id, filename, b"", actor, created_at),
    )
    attachment_id = int(cur.lastrowid)
    add_history(
        con,
        issue_id,
        actor,
        "attachment_added",
        "Added attachment",
        created_at,
        attachment_id=attachment_id,
    )
    return attachment_id


def add_issue(
    con: sqlite3.Connection,
    *,
    title: str,
    description: str,
    creator: str,
    assignee: str,
    priority: str,
    state: str,
    status: str,
    pct_complete: int,
    due_date: Optional[str],
    created_at: str,
    updated_at: str,
    completed_at: Optional[str] = None,
) -> int:
    cur = con.execute(
        """
        INSERT INTO issues
            (title, description, creator_username, assigned_username, priority,
             pct_complete, state, status, due_date, created_at, updated_at, completed_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            title,
            description,
            creator,
            assignee,
            priority,
            pct_complete,
            state,
            status,
            due_date,
            created_at,
            updated_at,
            completed_at,
        ),
    )
    issue_id = int(cur.lastrowid)
    add_history(con, issue_id, creator, "created", "Created issue", created_at)
    return issue_id


def seed_demo(con: sqlite3.Connection, creator: str, creator2: str, tech: str, tech2: str, admin: str) -> None:
    # Issue 1: active work, comments, and attachment metadata.
    issue_id = add_issue(
        con,
        title="Front desk printer will not print invoices",
        description=(
            "The front desk printer is online but invoice print jobs stay in the queue. "
            "Staff can print to the back office printer as a workaround."
        ),
        creator=creator,
        assignee=tech,
        priority="high",
        state="in progress",
        status="open",
        pct_complete=60,
        due_date="2026-06-03",
        created_at=utc(20, 9, 5),
        updated_at=utc(20, 15, 45),
    )
    add_history(con, issue_id, creator, "assigned", f'Changed assignee from "unassigned" to "{tech}"', utc(20, 9, 8))
    add_email_history(con, issue_id, creator, tech, utc(20, 9, 9))
    add_history(con, issue_id, creator, "priority_changed", 'Changed priority from "normal" to "high"', utc(20, 9, 10))
    add_history(con, issue_id, creator, "due_date_changed", 'Changed due date from "blank" to "2026-06-03"', utc(20, 9, 12))
    add_email_history(con, issue_id, creator, tech, utc(20, 9, 13))
    add_history(con, issue_id, tech, "state_changed", 'Changed state from "not started" to "in progress"', utc(20, 10, 30))
    add_history(con, issue_id, tech, "percent_complete_changed", 'Changed percent complete from "0" to "60"', utc(20, 15, 45))
    add_comment(
        con,
        issue_id,
        tech,
        "Restarted the print spooler and cleared two stuck invoice jobs. Printer responds to ping but test pages still fail.",
        utc(20, 10, 35),
    )
    add_email_history(con, issue_id, tech, creator, utc(20, 10, 36))
    add_comment(
        con,
        issue_id,
        admin,
        "Vendor support suggested replacing the toner sensor before scheduling a service call.",
        utc(20, 14, 20),
    )
    add_email_history(con, issue_id, admin, f"{creator}, {tech}", utc(20, 14, 21))
    add_attachment(con, issue_id, tech, "printer-queue-screenshot.png", utc(20, 14, 25))

    # Issue 2: active work, waiting on equipment, comments, and attachment metadata.
    issue_id = add_issue(
        con,
        title="Conference room Wi-Fi drops during video calls",
        description=(
            "Video calls in the large conference room disconnect several times per hour. "
            "The problem is worse when the room is full."
        ),
        creator=creator2,
        assignee=tech2,
        priority="normal",
        state="waiting",
        status="open",
        pct_complete=35,
        due_date="2026-06-07",
        created_at=utc(21, 8, 20),
        updated_at=utc(22, 11, 50),
    )
    add_history(con, issue_id, creator2, "assigned", f'Changed assignee from "unassigned" to "{tech2}"', utc(21, 8, 25))
    add_email_history(con, issue_id, creator2, tech2, utc(21, 8, 26))
    add_history(con, issue_id, creator2, "due_date_changed", 'Changed due date from "blank" to "2026-06-07"', utc(21, 8, 30))
    add_email_history(con, issue_id, creator2, tech2, utc(21, 8, 31))
    add_history(con, issue_id, tech2, "state_changed", 'Changed state from "not started" to "in progress"', utc(21, 13, 15))
    add_history(con, issue_id, tech2, "percent_complete_changed", 'Changed percent complete from "0" to "35"', utc(22, 11, 50))
    add_history(con, issue_id, tech2, "state_changed", 'Changed state from "in progress" to "waiting"', utc(22, 11, 55))
    add_comment(
        con,
        issue_id,
        tech2,
        "Measured weak signal near the projector wall. Moving the access point higher may improve coverage.",
        utc(21, 13, 18),
    )
    add_comment(
        con,
        issue_id,
        tech2,
        "Ordered a replacement access point and a longer patch cable. Waiting for delivery.",
        utc(22, 11, 55),
    )
    add_email_history(con, issue_id, tech2, creator2, utc(22, 11, 56))
    add_attachment(con, issue_id, tech2, "conference-room-signal-map.pdf", utc(22, 11, 58))

    # Issue 3: closed issue with workflow history, comments, and attachment metadata.
    issue_id = add_issue(
        con,
        title="Payroll laptop cannot connect to VPN",
        description=(
            "The payroll laptop fails VPN login with a certificate warning. "
            "Payroll processing is due tomorrow morning."
        ),
        creator=creator,
        assignee=tech,
        priority="high",
        state="complete",
        status="closed",
        pct_complete=100,
        due_date="2026-05-24",
        created_at=utc(23, 7, 55),
        updated_at=utc(23, 16, 40),
        completed_at=utc(23, 16, 40),
    )
    add_history(con, issue_id, creator, "assigned", f'Changed assignee from "unassigned" to "{tech}"', utc(23, 8, 0))
    add_email_history(con, issue_id, creator, tech, utc(23, 8, 1))
    add_history(con, issue_id, creator, "priority_changed", 'Changed priority from "normal" to "high"', utc(23, 8, 2))
    add_history(con, issue_id, creator, "due_date_changed", 'Changed due date from "blank" to "2026-05-24"', utc(23, 8, 5))
    add_history(con, issue_id, tech, "state_changed", 'Changed state from "not started" to "in progress"', utc(23, 9, 10))
    add_comment(
        con,
        issue_id,
        tech,
        "Found an expired user certificate in the VPN client profile.",
        utc(23, 9, 15),
    )
    add_attachment(con, issue_id, tech, "vpn-certificate-warning.png", utc(23, 9, 16))
    add_comment(
        con,
        issue_id,
        admin,
        "Renewed the certificate and verified VPN login on wired and wireless networks.",
        utc(23, 16, 30),
    )
    add_email_history(con, issue_id, admin, f"{creator}, {tech}", utc(23, 16, 31))
    add_history(con, issue_id, tech, "state_changed", 'Changed state from "in progress" to "complete"', utc(23, 16, 35))
    add_history(con, issue_id, tech, "percent_complete_changed", 'Changed percent complete from "80" to "100"', utc(23, 16, 36))
    add_history(con, issue_id, admin, "closed", "Closed issue", utc(23, 16, 40))
    add_email_history(con, issue_id, admin, f"{creator}, {tech}", utc(23, 16, 41))

    # Issue 4: permissions issue, active work, comments, no attachment.
    issue_id = add_issue(
        con,
        title="Shared accounting folder permissions are wrong",
        description=(
            "The accounts payable team can open the accounting share but cannot save updated vendor documents."
        ),
        creator=creator2,
        assignee=tech,
        priority="normal",
        state="deferred",
        status="open",
        pct_complete=20,
        due_date="2026-06-10",
        created_at=utc(24, 10, 5),
        updated_at=utc(25, 9, 40),
    )
    add_history(con, issue_id, creator2, "assigned", f'Changed assignee from "unassigned" to "{tech}"', utc(24, 10, 10))
    add_email_history(con, issue_id, creator2, tech, utc(24, 10, 11))
    add_history(con, issue_id, creator2, "due_date_changed", 'Changed due date from "blank" to "2026-06-10"', utc(24, 10, 12))
    add_history(con, issue_id, tech, "state_changed", 'Changed state from "not started" to "in progress"', utc(24, 10, 25))
    add_history(con, issue_id, tech, "percent_complete_changed", 'Changed percent complete from "0" to "20"', utc(24, 10, 35))
    add_comment(
        con,
        issue_id,
        tech,
        "Confirmed the share is reachable. The problem appears limited to write permissions on the vendor documents folder.",
        utc(24, 10, 30),
    )
    add_history(con, issue_id, tech, "state_changed", 'Changed state from "in progress" to "deferred"', utc(25, 9, 40))
    add_comment(
        con,
        issue_id,
        admin,
        "Deferred until the accounting manager confirms the correct access group.",
        utc(25, 9, 42),
    )

    # Issue 5: simple open issue with minimal history for list screenshots.
    issue_id = add_issue(
        con,
        title="New hire workstation setup for Monday",
        description=(
            "Prepare a workstation for the new sales employee. Needs browser shortcuts, printer setup, "
            "email profile, and access to the shared sales folder."
        ),
        creator=creator,
        assignee="",
        priority="low",
        state="not started",
        status="open",
        pct_complete=0,
        due_date="2026-06-01",
        created_at=utc(26, 12, 0),
        updated_at=utc(26, 12, 0),
    )
    add_history(con, issue_id, creator, "due_date_changed", 'Changed due date from "blank" to "2026-06-01"', utc(26, 12, 5))


def main() -> None:
    parser = argparse.ArgumentParser(description="Create a temporary demo Issues CGI SQLite database.")
    parser.add_argument(
        "--db",
        default="/tmp/issues_demo.db",
        help="database path to create; default: /tmp/issues_demo.db",
    )
    parser.add_argument(
        "--creator",
        default="casey",
        help="fake primary issue creator username; default: casey",
    )
    parser.add_argument(
        "--creator2",
        default="jordan",
        help="fake secondary issue creator username; default: jordan",
    )
    parser.add_argument(
        "--tech",
        default="morgan",
        help="fake primary IT technician / assignee username; default: morgan",
    )
    parser.add_argument(
        "--tech2",
        default="jamie",
        help="fake secondary IT technician / assignee username; default: jamie",
    )
    parser.add_argument(
        "--admin",
        default="rileyadmin",
        help="fake administrator username used in comments/history; default: rileyadmin",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="overwrite the database if it already exists",
    )
    args = parser.parse_args()

    db_path = Path(args.db)

    if db_path == Path("/var/lib/issues/issues.db"):
        raise SystemExit("Refusing to overwrite /var/lib/issues/issues.db")

    if db_path.exists():
        if not args.force:
            raise SystemExit(f"{db_path} already exists. Re-run with --force to replace it.")
        db_path.unlink()

    if db_path.parent:
        db_path.parent.mkdir(parents=True, exist_ok=True)

    con = sqlite3.connect(db_path)
    try:
        create_schema(con)
        seed_demo(con, args.creator, args.creator2, args.tech, args.tech2, args.admin)
        con.commit()
    finally:
        con.close()

    print(f"Created demo database: {db_path}")
    print()
    print("Fake usernames in this demo:")
    print(f"    Primary creator: {args.creator}")
    print(f"    Secondary creator: {args.creator2}")
    print(f"    Primary technician/assignee: {args.tech}")
    print(f"    Secondary technician/assignee: {args.tech2}")
    print(f"    Administrator/commenter: {args.admin}")
    print()
    print("To point the CGI app at this database, add or temporarily set:")
    print()
    print("    DB_FILE=" + str(db_path))
    print("    PER_USER_CONFIG_DIR=/tmp/issues_demo_config")
    print()
    print("Then create the temporary preference directory if needed:")
    print()
    print("    mkdir -p /tmp/issues_demo_config")
    print()
    print("For normal CGI viewing, authenticate as one of the fake users or use")
    print("matching real test accounts/group membership in your demo environment.")


if __name__ == "__main__":
    main()
