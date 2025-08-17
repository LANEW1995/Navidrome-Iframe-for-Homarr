#!/usr/bin/env python3
"""
Homarr Navidrome Web Player backend
- Serves index.html UI
- Proxies cover art with correct headers
- Proxies audio with HTTP Range support (so seeking works!)
- Random songs endpoint
- Search endpoint (Spotlight-style results)

Run:  python3 webplayer.py
Port: 5069 by default (set PORT env to override)
"""

import os
import hashlib
import secrets
from typing import Dict, Any, Iterable

import requests
from flask import Flask, request, send_from_directory, jsonify, Response, abort

# Optional CORS (kept permissive because you’re embedding in Homarr)
try:
    from flask_cors import CORS  # type: ignore

    _HAS_CORS = True
except Exception:
    _HAS_CORS = False

# ------------------ Config ------------------
PORT = int(os.environ.get("PORT", "5069"))

# Support both naming styles
NAVIDROME_URL = (
    os.environ.get("NAVIDROME_URL")
    or os.environ.get("NAVIDROME_BASE_URL")
    or "http://127.0.0.1:4533"
)

# Prefer SUBSONIC_* but fall back to your NAVIDROME_*
SUBSONIC_USER = os.environ.get("SUBSONIC_USER") or os.environ.get("NAVIDROME_USER", "")
SUBSONIC_PASSWORD = (
    os.environ.get("SUBSONIC_PASSWORD")
    or os.environ.get("NAVIDROME_PASS")
    or os.environ.get("NAVIDROME_PASSWORD", "")
)

SUBSONIC_VERSION = os.environ.get("SUBSONIC_VERSION", "1.16.1")
SUBSONIC_CLIENT = os.environ.get("SUBSONIC_CLIENT", "homarr-webplayer")
SUBSONIC_FORMAT = "json"


# ------------------ App ---------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
app = Flask(__name__, static_folder=None)

if _HAS_CORS:
    CORS(app, resources={r"/api/*": {"origins": "*"}, r"/": {"origins": "*"}})


def md5_hex(s: str) -> str:
    return hashlib.md5(s.encode("utf-8")).hexdigest()


def subsonic_auth() -> Dict[str, Any]:
    """
    Build Subsonic-compatible auth using token+salt (Navidrome supports this).
    """
    if not SUBSONIC_USER or not SUBSONIC_PASSWORD:
        # Better error than silent failure
        abort(500, "SUBSONIC_USER and SUBSONIC_PASSWORD env vars must be set")

    salt = secrets.token_hex(8)
    token = md5_hex(SUBSONIC_PASSWORD + salt)
    return {
        "u": SUBSONIC_USER,
        "t": token,
        "s": salt,
        "v": SUBSONIC_VERSION,
        "c": SUBSONIC_CLIENT,
        "f": SUBSONIC_FORMAT,
    }


# ------------------ Static / UI ------------------


@app.route("/")
def index():
    # Serve the single-page app
    return send_from_directory(BASE_DIR, "index.html")


@app.route("/index.html")
def index_html():
    return send_from_directory(BASE_DIR, "index.html")


@app.route("/ping")
def ping():
    return jsonify(ok=True)


# ------------------ API: Cover Art ------------------


@app.route("/api/cover/<cover_id>")
def api_cover(cover_id: str):
    """
    Proxy cover art so the UI can request /api/cover/<id>.
    """
    params = subsonic_auth() | {"id": cover_id}
    upstream = requests.get(
        f"{NAVIDROME_URL}/rest/getCoverArt", params=params, stream=True
    )

    # Build streaming response with key headers
    def gen() -> Iterable[bytes]:
        for chunk in upstream.iter_content(chunk_size=8192):
            if chunk:
                yield chunk

    resp = Response(gen(), status=upstream.status_code)
    for h in [
        "Content-Type",
        "Content-Length",
        "Cache-Control",
        "ETag",
        "Last-Modified",
        "Accept-Ranges",
    ]:
        v = upstream.headers.get(h)
        if v:
            resp.headers[h] = v

    # Default type if upstream was vague
    resp.headers.setdefault("Content-Type", "image/jpeg")
    return resp


# ------------------ API: Audio Stream (Range aware) ------------------


@app.route("/api/stream/<song_id>")
def api_stream(song_id: str):
    """
    Proxy audio with HTTP Range support so <audio> can seek.
    We use /rest/download to guarantee byte-range support.
    """
    params = subsonic_auth() | {"id": song_id}

    headers = {}
    # Forward Range if present (critical for seeking)
    rng = request.headers.get("Range")
    if rng:
        headers["Range"] = rng

    # Using /download ensures a static file-like response with ranges.
    upstream = requests.get(
        f"{NAVIDROME_URL}/rest/download",
        params=params,
        headers=headers,
        stream=True,
    )

    def gen() -> Iterable[bytes]:
        for chunk in upstream.iter_content(chunk_size=8192):
            if chunk:
                yield chunk

    resp = Response(gen(), status=upstream.status_code)
    passthrough = [
        "Content-Type",
        "Content-Length",
        "Accept-Ranges",
        "Content-Range",
        "Cache-Control",
        "ETag",
        "Last-Modified",
        "Content-Disposition",
    ]
    for h in passthrough:
        v = upstream.headers.get(h)
        if v:
            resp.headers[h] = v

    # Reasonable default
    resp.headers.setdefault("Accept-Ranges", "bytes")
    resp.headers.setdefault("Content-Type", "audio/mpeg")
    return resp


# ------------------ API: Random list ------------------


@app.route("/api/random/list")
def api_random_list():
    """
    Return a list of random songs (mapped to the UI’s shape).
    GET /api/random/list?size=25
    """
    try:
        size = int(request.args.get("size", 30))
    except Exception:
        size = 30

    params = subsonic_auth() | {"size": size}
    r = requests.get(f"{NAVIDROME_URL}/rest/getRandomSongs", params=params)
    try:
        js = r.json().get("subsonic-response", {})
    except Exception:
        return jsonify(success=False, error="Upstream invalid JSON"), 502

    songs = js.get("randomSongs", {}).get("song", []) or []
    # Ensure we always return a list
    if isinstance(songs, dict):
        songs = [songs]

    payload = []
    for s in songs:
        if not s:
            continue
        payload.append(
            {
                "id": s.get("id"),
                "title": s.get("title", "Unknown"),
                "artist": s.get("artist", "Unknown"),
                "coverArt": s.get("coverArt") or s.get("id"),
            }
        )

    return jsonify(success=True, songs=payload)


# ------------------ API: Search ------------------


@app.route("/api/search")
def api_search():
    """
    Simple song search (returns up to songCount results).
    GET /api/search?query=...
    """
    q = (request.args.get("query") or "").strip()
    if not q:
        return jsonify(success=False, error="No query"), 400

    params = subsonic_auth() | {
        "query": q,
        "songCount": int(request.args.get("songCount", 25)),
        "albumCount": 0,
        "artistCount": 0,
    }
    r = requests.get(f"{NAVIDROME_URL}/rest/search3", params=params)
    try:
        js = r.json().get("subsonic-response", {})
    except Exception:
        return jsonify(success=False, error="Upstream invalid JSON"), 502

    res = js.get("searchResult3", {}) or {}
    songs = res.get("song", []) or []
    if isinstance(songs, dict):
        songs = [songs]

    results = []
    for s in songs:
        if not s:
            continue
        results.append(
            {
                "id": s.get("id"),
                "title": s.get("title", "Unknown"),
                "artist": s.get("artist", "Unknown"),
                "coverArt": s.get("coverArt") or s.get("id"),
            }
        )

    return jsonify(success=True, results=results)


# ------------------ Main ------------------

if __name__ == "__main__":
    # Make sure index.html exists relative to this file
    idx_path = os.path.join(BASE_DIR, "index.html")
    if not os.path.isfile(idx_path):
        print("WARNING: index.html not found next to webplayer.py")

    app.run(host="0.0.0.0", port=PORT, debug=True)
