"""Minimal song request web app: guest submission form + DJ queue page."""

import os
from pathlib import Path

from fastapi import Depends, FastAPI, Form, Request
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

import db

BASE_DIR = Path(__file__).resolve().parent

app = FastAPI()

templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

static_dir = BASE_DIR / "static"
if static_dir.is_dir():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


@app.on_event("startup")
def on_startup():
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
