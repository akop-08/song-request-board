"""Single source of truth for all SQLite access used by main.py and tests.

All paths are handled with pathlib so this works the same on Windows,
macOS, and Linux.
"""

import os
import sqlite3
from datetime import datetime
from pathlib import Path

# Directory this file lives in == the repo root.
REPO_ROOT = Path(__file__).resolve().parent

DEFAULT_DB_FILENAME = "song_requests.db"

VALID_STATUSES = ("pending", "played", "dismissed")


def get_db_path():
    """Resolve the SQLite file path from the DB_PATH env var.

    Read at call time (never cached) so callers/tests can point this at a
    different file by setting the env var before calling. A relative path
    is resolved relative to the repo root; an absolute path is used as-is.
    Returns a string path.
    """
    raw = os.environ.get("DB_PATH", DEFAULT_DB_FILENAME)
    path = Path(raw)
    if not path.is_absolute():
        path = REPO_ROOT / path
    return str(path)


def init_db(db_path):
    """Create the `requests` table if it does not already exist."""
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                artist TEXT NOT NULL,
                requester_name TEXT,
                status TEXT NOT NULL DEFAULT 'pending',
                created_at TEXT NOT NULL
            )
            """
        )
        conn.commit()
    finally:
        conn.close()


def get_connection(db_path):
    """Open a new SQLite connection with row access by column name."""
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def add_request(conn, title, artist, requester_name):
    """Insert a new pending request row and commit."""
    created_at = datetime.utcnow().isoformat()
    conn.execute(
        """
        INSERT INTO requests (title, artist, requester_name, status, created_at)
        VALUES (?, ?, ?, 'pending', ?)
        """,
        (title, artist, requester_name, created_at),
    )
    conn.commit()


def get_merged_pending_requests(conn):
    """Return pending requests grouped by case-insensitive, trimmed title+artist.

    Depends only on the rows passed in via `conn` (no module-level state),
    so it is easy to exercise against a temporary database in tests.

    Each group is a dict:
        {
            "title": <title as typed, from the newest row in the group>,
            "artist": <artist as typed, from the newest row in the group>,
            "count": <number of rows in the group>,
            "requester_names": [non-empty requester_name values, newest first, as typed],
            "latest_created_at": <max created_at string in the group>,
            "request_ids": [all row ids in the group],
        }

    The returned list is sorted by latest_created_at descending (newest
    group first).
    """
    rows = conn.execute(
        """
        SELECT id, title, artist, requester_name, created_at
        FROM requests
        WHERE status = 'pending'
        ORDER BY created_at DESC, id DESC
        """
    ).fetchall()

    groups = {}  # key -> group dict, built in newest-row-first order
    order = []  # preserves first-seen (i.e. newest) order of keys

    for row in rows:
        title = row["title"]
        artist = row["artist"]
        key = (title.strip().lower(), artist.strip().lower())

        if key not in groups:
            groups[key] = {
                "title": title,
                "artist": artist,
                "count": 0,
                "requester_names": [],
                "latest_created_at": row["created_at"],
                "request_ids": [],
            }
            order.append(key)

        group = groups[key]
        group["count"] += 1
        group["request_ids"].append(row["id"])
        if row["created_at"] > group["latest_created_at"]:
            group["latest_created_at"] = row["created_at"]

        requester_name = row["requester_name"]
        if requester_name and requester_name.strip():
            group["requester_names"].append(requester_name)

    result = [groups[key] for key in order]
    result.sort(key=lambda g: g["latest_created_at"], reverse=True)
    return result


def set_status_for_ids(conn, request_ids, status):
    """Update all rows whose id is in request_ids to the given status."""
    if status not in VALID_STATUSES:
        raise ValueError("invalid status: {!r}".format(status))
    if not request_ids:
        return
    placeholders = ",".join("?" for _ in request_ids)
    conn.execute(
        "UPDATE requests SET status = ? WHERE id IN ({})".format(placeholders),
        (status, *request_ids),
    )
    conn.commit()
