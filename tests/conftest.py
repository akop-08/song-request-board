"""Shared pytest fixtures for the whole tests/ directory.

main.on_startup() now refuses to start the app (raises RuntimeError) if
DJ_KEY is missing or shorter than main.MIN_DJ_KEY_LENGTH characters - see
main._dj_key_startup_error / main._validate_dj_key_or_raise.

tests/test_app.py's `client_with_temp_db` fixture builds a fresh
`TestClient(main.app)` - which runs the FastAPI startup event - before the
test body gets a chance to set DJ_KEY via monkeypatch. Without a valid
DJ_KEY already present in the environment at that point, every test using
that fixture would fail at client construction, before the test itself
ever runs.

This autouse fixture seeds a valid default DJ_KEY for every test in this
directory, restoring whatever (if anything) was there before. Individual
tests are free to override or delete DJ_KEY afterwards with their own
monkeypatch calls, since monkeypatch's teardown restores this fixture's
default, not the other way around (pytest tears down fixtures in reverse
setup order).
"""

import os

import pytest

DEFAULT_TEST_DJ_KEY = "test-dj-key-1234567890"


@pytest.fixture(autouse=True)
def _default_dj_key():
    previous = os.environ.get("DJ_KEY")
    os.environ["DJ_KEY"] = DEFAULT_TEST_DJ_KEY
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop("DJ_KEY", None)
        else:
            os.environ["DJ_KEY"] = previous
