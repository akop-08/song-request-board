"""Minimal song request web app: guest submission form + DJ queue page."""

import io
import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Form, Request
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import qrcode
import qrcode.image.svg

import db

# Load a .env file from the repo root into the process environment, if one
# exists. Called once at module level, before anything below reads an env
# var (DJ_KEY, PUBLIC_URL). If no .env file exists, this is a safe no-op.
load_dotenv()

BASE_DIR = Path(__file__).resolve().parent

MIN_DJ_KEY_LENGTH = 16

app = FastAPI()

templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

static_dir = BASE_DIR / "static"
if static_dir.is_dir():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


def _dj_key_startup_error(dj_key):
    """Return a startup error message for an unacceptable DJ_KEY, or None.

    Pure function: no env reads, no exceptions raised here - just the
    candidate key value (or None) in, and either an error message string
    describing what's wrong (missing vs. too short) or None if the key is
    acceptable. Kept pure and side-effect-free so it's trivial to unit test.
    """
    if not dj_key:
        return (
            "DJ_KEY is missing. Set DJ_KEY in your .env file (see "
            ".env.example) to a random string at least {} characters "
            "long.".format(MIN_DJ_KEY_LENGTH)
        )
    if len(dj_key) < MIN_DJ_KEY_LENGTH:
        return (
            "DJ_KEY is too short ({} characters); it must be at least {} "
            "characters long.".format(len(dj_key), MIN_DJ_KEY_LENGTH)
        )
    return None


def _validate_dj_key_or_raise():
    """Raise RuntimeError with a clear message if DJ_KEY is unacceptable."""
    error = _dj_key_startup_error(os.environ.get("DJ_KEY"))
    if error:
        raise RuntimeError(error)


@app.on_event("startup")
def on_startup():
    _validate_dj_key_or_raise()
    db.init_db(db.get_db_path())


def get_db():
    """FastAPI dependency: yield a fresh connection, close it after the request."""
    conn = db.get_connection(db.get_db_path())
    try:
        yield conn
    finally:
        conn.close()


def _dj_key_is_valid(key):
    dj_key = os.environ.get("DJ_KEY")
    if not dj_key:
        return False
    if not key:
        return False
    return key == dj_key


def _parse_request_ids(raw):
    ids = []
    for part in raw.split(","):
        part = part.strip()
        if part:
            ids.append(int(part))
    return ids


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    return templates.TemplateResponse(
        request,
        "index.html",
        {"confirmation": False},
    )


@app.post("/submit", response_class=HTMLResponse)
def submit(
    request: Request,
    title: str = Form(...),
    artist: str = Form(...),
    requester_name: str = Form(""),
    conn=Depends(get_db),
):
    clean_title = title.strip()
    clean_artist = artist.strip()
    clean_requester = requester_name.strip()

    if not clean_title or not clean_artist:
        return templates.TemplateResponse(
            request,
            "index.html",
            {
                "confirmation": False,
                "error": "Please fill in both song title and artist.",
                "title": title,
                "artist": artist,
                "requester_name": requester_name,
            },
            status_code=400,
        )

    db.add_request(conn, clean_title, clean_artist, clean_requester)

    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "confirmation": True,
            "title": clean_title,
            "artist": clean_artist,
        },
    )


@app.get("/dj", response_class=HTMLResponse)
def dj(request: Request, key: str = None, conn=Depends(get_db)):
    if not _dj_key_is_valid(key):
        return PlainTextResponse("Forbidden", status_code=403)

    requests_list = db.get_merged_pending_requests(conn)

    return templates.TemplateResponse(
        request,
        "dj.html",
        {"requests": requests_list, "key": key},
    )


@app.post("/dj/played")
def dj_played(key: str = None, request_ids: str = Form(...), conn=Depends(get_db)):
    if not _dj_key_is_valid(key):
        return PlainTextResponse("Forbidden", status_code=403)

    ids = _parse_request_ids(request_ids)
    db.set_status_for_ids(conn, ids, "played")

    return RedirectResponse(url="/dj?key={}".format(key), status_code=303)


@app.post("/dj/dismiss")
def dj_dismiss(key: str = None, request_ids: str = Form(...), conn=Depends(get_db)):
    if not _dj_key_is_valid(key):
        return PlainTextResponse("Forbidden", status_code=403)

    ids = _parse_request_ids(request_ids)
    db.set_status_for_ids(conn, ids, "dismissed")

    return RedirectResponse(url="/dj?key={}".format(key), status_code=303)


@app.get("/qr", response_class=HTMLResponse)
def qr(request: Request):
    """Public, printable "scan to request a song" page.

    No DJ_KEY required - this is meant to be printed and posted publicly
    for guests to scan. PUBLIC_URL is read fresh from the environment on
    every request (not cached at import time), the same way DJ_KEY is read
    elsewhere in this module.
    """
    public_url = os.environ.get("PUBLIC_URL")
    if not public_url or not public_url.strip():
        return PlainTextResponse("PUBLIC_URL is not configured", status_code=500)

    public_url = public_url.strip()

    qr_img = qrcode.make(public_url, image_factory=qrcode.image.svg.SvgPathImage)
    buffer = io.BytesIO()
    qr_img.save(buffer)
    qr_svg = buffer.getvalue().decode("utf-8")
    if qr_svg.startswith("<?xml"):
        # Drop the XML declaration so this is embeddable directly as inline
        # HTML markup (via Jinja2's `| safe`) rather than as a standalone
        # XML document.
        qr_svg = qr_svg.split("?>", 1)[1].lstrip()

    return templates.TemplateResponse(
        request,
        "qr.html",
        {"qr_svg": qr_svg, "public_url": public_url},
    )
