"""Tests for the song request app.

Covers:
  1. Duplicate merging in db.get_merged_pending_requests, exercised against
     a temporary SQLite file created with Python's tempfile module.
  2. The DJ key check on GET /dj, exercised with FastAPI's TestClient
     against the real app in main.py.

Each test is self-contained: it creates (and cleans up) its own temporary
SQLite file and sets its own environment variables via monkeypatch, so
tests never touch the real song_requests.db and never depend on each
other's state.
"""

import os
import sys
import tempfile
import time

import pytest
from fastapi.testclient import TestClient

# Make sure the repo root (parent of this tests/ dir) is importable
# regardless of where pytest is invoked from.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import db  # noqa: E402  (import after sys.path tweak)
import main  # noqa: E402


# ---------------------------------------------------------------------------
# 1. Duplicate merging (db.py, no FastAPI involved)
# ---------------------------------------------------------------------------


@pytest.fixture
def temp_db_path():
    """A path to a fresh, empty temporary SQLite file, cleaned up after."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    try:
        yield path
    finally:
        if os.path.exists(path):
            os.remove(path)


def test_duplicate_requests_merge_into_one_group_with_correct_count(temp_db_path):
    db.init_db(temp_db_path)
    conn = db.get_connection(temp_db_path)
    try:
        # Three variants of the same song (case / whitespace differences).
        db.add_request(conn, "Bohemian Rhapsody", "Queen", "Alice")
        db.add_request(conn, " bohemian rhapsody ", "queen", "Bob")
        db.add_request(conn, "BOHEMIAN RHAPSODY", "QUEEN", "")

        # A genuinely different song.
        db.add_request(conn, "Don't Stop Believin'", "Journey", "Cleo")

        groups = db.get_merged_pending_requests(conn)

        assert len(groups) == 2

        by_key = {
            (g["title"].strip().lower(), g["artist"].strip().lower()): g
            for g in groups
        }

        rhapsody = by_key[("bohemian rhapsody", "queen")]
        assert rhapsody["count"] == 3
        # Blank requester_name on the third insert must not produce an
        # empty-string entry in requester_names.
        assert rhapsody["requester_names"] == ["Bob", "Alice"]
        assert len(rhapsody["request_ids"]) == 3

        journey = by_key[("don't stop believin'", "journey")]
        assert journey["count"] == 1
        assert journey["requester_names"] == ["Cleo"]
    finally:
        conn.close()


def test_groups_are_sorted_newest_first(temp_db_path):
    db.init_db(temp_db_path)
    conn = db.get_connection(temp_db_path)
    try:
        # Insert in a deliberately mixed order; add_request always stamps
        # "now" as created_at, so insertion order == chronological order.
        # A tiny sleep between inserts guarantees distinct timestamps even
        # on filesystems/clocks with coarse resolution.
        db.add_request(conn, "Song A", "Artist A", "")
        time.sleep(0.01)
        db.add_request(conn, "Song B", "Artist B", "")
        time.sleep(0.01)
        db.add_request(conn, "song a", "artist a", "")  # bumps Song A's group
        time.sleep(0.01)
        db.add_request(conn, "Song C", "Artist C", "")

        groups = db.get_merged_pending_requests(conn)
        ordered_titles = [g["title"].strip().lower() for g in groups]

        # Newest group first: "song c" was added last, then the
        # "song a" duplicate (which refreshed that group's latest
        # timestamp), then the original "song b".
        assert ordered_titles[0] == "song c"
        assert ordered_titles[1] == "song a"
        assert ordered_titles[2] == "song b"

        # Sanity check: latest_created_at is non-increasing down the list.
        timestamps = [g["latest_created_at"] for g in groups]
        assert timestamps == sorted(timestamps, reverse=True)
    finally:
        conn.close()


def test_non_pending_requests_are_excluded_from_merge(temp_db_path):
    db.init_db(temp_db_path)
    conn = db.get_connection(temp_db_path)
    try:
        db.add_request(conn, "Song X", "Artist X", "")
        db.add_request(conn, "Song Y", "Artist Y", "")

        groups = db.get_merged_pending_requests(conn)
        y_group = next(g for g in groups if g["title"] == "Song Y")
        db.set_status_for_ids(conn, y_group["request_ids"], "played")

        remaining = db.get_merged_pending_requests(conn)
        assert len(remaining) == 1
        assert remaining[0]["title"] == "Song X"
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# 2. DJ key check (main.py, via FastAPI's TestClient)
# ---------------------------------------------------------------------------


@pytest.fixture
def client_with_temp_db(monkeypatch):
    """A TestClient wired to a fresh temporary SQLite file via DB_PATH.

    Using monkeypatch keeps this change scoped to the single test that
    requests this fixture, and the temp file is removed afterward.
    """
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    monkeypatch.setenv("DB_PATH", path)
    db.init_db(db.get_db_path())
    try:
        with TestClient(main.app) as client:
            yield client
    finally:
        if os.path.exists(path):
            os.remove(path)


def test_dj_rejects_missing_key(client_with_temp_db, monkeypatch):
    monkeypatch.setenv("DJ_KEY", "secret123")

    response = client_with_temp_db.get("/dj")

    assert response.status_code == 403


def test_dj_rejects_wrong_key(client_with_temp_db, monkeypatch):
    monkeypatch.setenv("DJ_KEY", "secret123")

    response = client_with_temp_db.get("/dj", params={"key": "not-the-right-key"})

    assert response.status_code == 403


def test_dj_rejects_any_key_when_dj_key_env_var_unset(client_with_temp_db, monkeypatch):
    monkeypatch.delenv("DJ_KEY", raising=False)

    response = client_with_temp_db.get("/dj", params={"key": "whatever"})

    assert response.status_code == 403


def test_dj_accepts_correct_key(client_with_temp_db, monkeypatch):
    monkeypatch.setenv("DJ_KEY", "secret123")

    response = client_with_temp_db.get("/dj", params={"key": "secret123"})

    assert response.status_code == 200


def test_dj_key_helper_function_directly(monkeypatch):
    """Unit-level check of main._dj_key_is_valid, independent of HTTP."""
    monkeypatch.setenv("DJ_KEY", "abc")
    assert main._dj_key_is_valid("abc") is True
    assert main._dj_key_is_valid("wrong") is False
    assert main._dj_key_is_valid(None) is False
    assert main._dj_key_is_valid("") is False

    monkeypatch.delenv("DJ_KEY", raising=False)
    assert main._dj_key_is_valid("abc") is False
