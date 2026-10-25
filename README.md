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

## Configuration (.env)

Config is loaded from a `.env` file in the repo root (via `python-dotenv`).
Copy the example file and fill in your own values:

```powershell
Copy-Item .env.example .env
```

`.env` holds two variables:

- `DJ_KEY` - the shared secret that protects the `/dj` page. Must be at
  least 16 characters; if it's missing or too short, the app refuses to
  start and prints a clear error instead of booting insecurely.
- `PUBLIC_URL` - the public URL guests will use (e.g. your ngrok URL).
  Used by the `/qr` page and by `start.ps1` to print the DJ URL.

`.env` is excluded from git (see `.gitignore`); only `.env.example`, with
placeholder values, is committed.

## Running the app

### Quick local run

With `.env` filled in:

```powershell
.venv312\Scripts\python.exe -m uvicorn main:app --reload
```

- Guest request form: http://127.0.0.1:8000/
- DJ queue page: http://127.0.0.1:8000/dj?key=&lt;your DJ_KEY&gt;
- Printable QR page: http://127.0.0.1:8000/qr

### Gig mode (`start.ps1`)

For a live event, `start.ps1` loads `.env`, starts uvicorn on
`127.0.0.1:8000` in its own window, starts `ngrok http 8000 --url
$PUBLIC_URL` in another window (tunneling your `PUBLIC_URL` to the local
server), and prints the guest URL and the full DJ URL (with key) to
copy/paste:

```powershell
.\start.ps1
```

Requires `.env` to exist (see Configuration above) and `ngrok` to be
installed and on your `PATH`. If `.env` is missing, the script exits with
a clear error instead of starting anything.

Requests are stored in a local SQLite file (`song_requests.db` in the repo
root by default); it's created automatically on first run and is excluded
from git.

## The /qr page

`/qr` is a public, printable page with a large QR code (generated locally
with the `qrcode` library, rendered as inline SVG - no external services)
that encodes `PUBLIC_URL`, under the heading "Scan to request a song", with
the plain URL shown below as a fallback for anyone who can't scan. It needs
no `DJ_KEY`, so it's safe to print and post for guests. Open
http://127.0.0.1:8000/qr (or your `PUBLIC_URL` + `/qr`) and print it before
the gig.

## Running the tests

```powershell
.venv312\Scripts\python.exe -m pytest
```

Tests cover duplicate-request merging (`db.get_merged_pending_requests`),
the `/dj` key check (missing key, wrong key, no `DJ_KEY` set, and the
correct key), the `DJ_KEY` startup validation (missing/too-short/valid
keys, and `main.on_startup` itself), and the `/qr` route (missing/blank
`PUBLIC_URL`, and a successful render) - all using temporary SQLite files
so they never touch `song_requests.db`.
