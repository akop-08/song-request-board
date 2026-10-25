"""Tests for the gig-readiness additions: the DJ_KEY startup check and the
public /qr route.

Covers:
  1. main._dj_key_startup_error - pure function, no app/HTTP involved.
  2. main._validate_dj_key_or_raise - thin wrapper that reads os.environ
     and raises RuntimeError using that function's message.
  3. main.on_startup - called directly (not through a TestClient), so it
     is exercised exactly as a later step would call it: with a valid
     DJ_KEY it should succeed and initialize the DB; with an invalid one
     it should raise RuntimeError before touching the DB.
  4. GET /qr - the public QR code page, which requires no DJ_KEY.

Each test is self-contained: it uses monkeypatch for env vars and a
temporary SQLite file where the app/DB is touched, so nothing here reads
or writes the real song_requests.db.
"""

import os
import sys
import tempfile

import pytest
from fastapi.testclient import TestClient

# Make sure the repo root (parent of this tests/ dir) is importable
# regardless of where pytest is invoked from.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import main  # noqa: E402


# ---------------------------------------------------------------------------
# 1. main._dj_key_startup_error (pure function)
# ---------------------------------------------------------------------------


def test_startup_error_for_missing_key_mentions_missing_and_minimum():
    error = main._dj_key_startup_error(None)
    assert error is not None
    assert "missing" in error.lower()
    assert str(main.MIN_DJ_KEY_LENGTH) in error


def test_startup_error_for_empty_string_key_is_treated_as_missing():
    error = main._dj_key_startup_error("")
    assert error is not None
    assert "missing" in error.lower()


def test_startup_error_for_short_key_mentions_actual_and_minimum_length():
    short_key = "short-key-12"  # 12 characters, below the minimum of 16
    error = main._dj_key_startup_error(short_key)

    assert error is not None
    assert "too short" in error.lower()
    assert str(len(short_key)) in error
    assert str(main.MIN_DJ_KEY_LENGTH) in error


def test_startup_error_for_key_one_below_minimum_length_is_rejected():
    key = "a" * (main.MIN_DJ_KEY_LENGTH - 1)
    assert main._dj_key_startup_error(key) is not None


def test_startup_error_for_key_at_minimum_length_is_none():
    key = "a" * main.MIN_DJ_KEY_LENGTH
    assert main._dj_key_startup_error(key) is None


def test_startup_error_for_key_above_minimum_length_is_none():
    key = "a" * (main.MIN_DJ_KEY_LENGTH + 10)
    assert main._dj_key_startup_error(key) is None


# ---------------------------------------------------------------------------
# 2. main._validate_dj_key_or_raise
# ---------------------------------------------------------------------------


def test_validate_dj_key_or_raise_raises_when_unset(monkeypatch):
    monkeypatch.delenv("DJ_KEY", raising=False)
    with pytest.raises(RuntimeError):
        main._validate_dj_key_or_raise()


def test_validate_dj_key_or_raise_raises_when_too_short(monkeypatch):
    monkeypatch.setenv("DJ_KEY", "tooshort")
    with pytest.raises(RuntimeError):
        main._validate_dj_key_or_raise()


def test_validate_dj_key_or_raise_passes_when_valid(monkeypatch):
    monkeypatch.setenv("DJ_KEY", "a-valid-dj-key-1234")
    main._validate_dj_key_or_raise()  # must not raise


# ---------------------------------------------------------------------------
# 3. main.on_startup, called directly
# ---------------------------------------------------------------------------


@pytest.fixture
def temp_db_path(monkeypatch):
    """Point DB_PATH at a fresh temporary SQLite file for this test only."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.remove(path)  # on_startup/init_db should create it from scratch
    monkeypatch.setenv("DB_PATH", path)
    try:
        yield path
    finally:
        if os.path.exists(path):
            os.remove(path)


def test_on_startup_raises_and_skips_db_init_when_dj_key_invalid(
    monkeypatch, temp_db_path
):
    monkeypatch.delenv("DJ_KEY", raising=False)

    with pytest.raises(RuntimeError):
        main.on_startup()

    assert not os.path.exists(temp_db_path)


def test_on_startup_succeeds_and_initializes_db_when_dj_key_valid(
    monkeypatch, temp_db_path
):
    monkeypatch.setenv("DJ_KEY", "a-valid-dj-key-1234")

    main.on_startup()  # must not raise

    assert os.path.exists(temp_db_path)


# ---------------------------------------------------------------------------
# 4. GET /qr
# ---------------------------------------------------------------------------


@pytest.fixture
def client_with_temp_db(monkeypatch):
    """A TestClient wired to a fresh temporary SQLite file via DB_PATH.

    DJ_KEY is already set to a valid value by the autouse fixture in
    conftest.py, so the startup check passes here without extra setup.
    """
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    monkeypatch.setenv("DB_PATH", path)
    try:
        with TestClient(main.app) as client:
            yield client
    finally:
        if os.path.exists(path):
            os.remove(path)


def test_qr_returns_500_when_public_url_unset(client_with_temp_db, monkeypatch):
    monkeypatch.delenv("PUBLIC_URL", raising=False)

    response = client_with_temp_db.get("/qr")

    assert response.status_code == 500
    assert "PUBLIC_URL is not configured" in response.text


def test_qr_returns_500_when_public_url_blank(client_with_temp_db, monkeypatch):
    monkeypatch.setenv("PUBLIC_URL", "   ")

    response = client_with_temp_db.get("/qr")

    assert response.status_code == 500
    assert "PUBLIC_URL is not configured" in response.text


def test_qr_renders_svg_and_url_when_public_url_set(client_with_temp_db, monkeypatch):
    monkeypatch.setenv("PUBLIC_URL", "https://example.ngrok-free.app")

    response = client_with_temp_db.get("/qr")

    assert response.status_code == 200
    assert "Scan to request a song" in response.text
    assert "<svg" in response.text
    assert "https://example.ngrok-free.app" in response.text
    # The raw XML declaration should have been stripped before embedding.
    assert "<?xml" not in response.text


def test_qr_requires_no_dj_key(client_with_temp_db, monkeypatch):
    """The /qr page is public: no `key` query param should still work."""
    monkeypatch.setenv("PUBLIC_URL", "https://example.ngrok-free.app")

    response = client_with_temp_db.get("/qr")

    assert response.status_code == 200
