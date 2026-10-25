# Song Request Board

A minimal song request web app for live events: guests submit song requests
from their phones on a simple mobile-first form, and the DJ works a
separate, key-protected queue page that merges duplicate requests (same
title and artist, ignoring case and extra whitespace) into one row with a
request count, and lets the DJ mark each row "Played" or "Dismiss". Built
with Python 3.12, FastAPI, Jinja2 templates, and SQLite, with no JavaScript
framework and no external APIs.

## Setup (Windows / PowerShell)

These commands assume a Python 3.12 virtual environment at `.venv312` in
the repo root (create one with `py -3.12 -m venv .venv312` if it doesn't
exist yet).

```powershell
.venv312\Scripts\python.exe -m pip install -r requirements.txt
```

## Running the app

Set the `DJ_KEY` environment variable (this is the shared secret that
protects the `/dj` page) and start the server:

```powershell
$env:DJ_KEY = "choose-a-secret-key"
.venv312\Scripts\python.exe -m uvicorn main:app --reload
```

- Guest request form: http://127.0.0.1:8000/
- DJ queue page: http://127.0.0.1:8000/dj?key=choose-a-secret-key

(use the same value you set for `$env:DJ_KEY` in the `key` query parameter).

`$env:DJ_KEY` only applies to the current PowerShell session/process, so
set it again in any new terminal before starting the server.

Requests are stored in a local SQLite file (`song_requests.db` in the repo
root by default); it's created automatically on first run and is excluded
from git.

## Running the tests

```powershell
.venv312\Scripts\python.exe -m pytest
```

Tests cover duplicate-request merging (`db.get_merged_pending_requests`)
and the `/dj` key check (missing key, wrong key, no `DJ_KEY` set, and the
correct key), using temporary SQLite files so they never touch
`song_requests.db`.
