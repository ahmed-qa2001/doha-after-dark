"""Doha After Dark: location CMS and Week 10 story multimedia metadata API.

Python 3.9+, standard library only. Binds to localhost for development;
write endpoints are NOT authenticated, and must not be publicly exposed.
"""

import json
from contextlib import contextmanager
import math
import re
import sqlite3
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

PROJECT_DIR = Path(__file__).resolve().parent
DATABASE = PROJECT_DIR / "locations.db"
SEED_LOCATIONS = [
    ("Souq Waqif", 25.2867, 51.5333,
     "Traditional market with restaurants, shops, and evening activities."),
    ("Doha Corniche", 25.3020, 51.5195,
     "A waterfront promenade with beautiful views of Doha at night."),
    ("Katara Cultural Village", 25.3608, 51.5253,
     "A cultural destination with restaurants, events, art, and entertainment."),
]
MAX_BODY_BYTES = 65_536


@contextmanager
def connect():
    connection = sqlite3.connect(DATABASE, timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    try:
        with connection:
            yield connection
    finally:
        connection.close()


def initialize_database():
    """Create new tables without deleting or rewriting previously saved locations."""
    with connect() as db:
        db.execute("""
            CREATE TABLE IF NOT EXISTS locations (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                latitude REAL NOT NULL,
                longitude REAL NOT NULL,
                description TEXT NOT NULL
            )
        """)
        # Week 10: one location may contain multiple stories.
        db.execute("""
            CREATE TABLE IF NOT EXISTS stories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                location_id INTEGER NOT NULL,
                summary TEXT NOT NULL,
                video_url TEXT,
                thumbnail_path TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (location_id) REFERENCES locations(id) ON DELETE CASCADE
            )
        """)
        db.execute("CREATE INDEX IF NOT EXISTS idx_stories_location ON stories(location_id)")
        if db.execute("SELECT COUNT(*) FROM locations").fetchone()[0] == 0:
            db.executemany(
                "INSERT INTO locations (name, latitude, longitude, description) VALUES (?, ?, ?, ?)",
                SEED_LOCATIONS,
            )


def required_text(data, key, limit):
    value = data.get(key)
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise ValueError(f"{key} must be nonempty text of at most {limit} characters")
    return value.strip()


def optional_text(data, key, limit=2048):
    value = data.get(key)
    if value is None or value == "":
        return None
    if not isinstance(value, str) or len(value) > limit:
        raise ValueError(f"{key} must be text of at most {limit} characters")
    return value.strip() or None


def positive_id(value, key="location_id"):
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{key} must be a positive integer")
    return value


def coordinates(data):
    def one(key, lower, upper):
        value = data.get(key)
        if isinstance(value, bool):
            raise ValueError(f"{key} must be a number")
        try:
            parsed = float(value)
        except (TypeError, ValueError, OverflowError):
            raise ValueError(f"{key} must be a number") from None
        if not math.isfinite(parsed) or not lower <= parsed <= upper:
            raise ValueError(f"{key} must be between {lower} and {upper}")
        return parsed
    return one("latitude", -90, 90), one("longitude", -180, 180)


def validate_story(data):
    from urllib.parse import urlsplit
    location_id = positive_id(data.get("location_id"))
    summary = required_text(data, "summary", 2000)
    video_url = optional_text(data, "video_url")
    thumbnail_path = optional_text(data, "thumbnail_path")
    if video_url:
        parts = urlsplit(video_url)
        if parts.scheme not in ("http", "https") or not parts.hostname or parts.username or parts.password:
            raise ValueError("video_url must be an http(s) URL")
    if thumbnail_path:
        # Store metadata only; file uploads and static media serving are future work.
        parts = urlsplit(thumbnail_path)
        if parts.scheme:
            if parts.scheme not in ("http", "https") or not parts.hostname or parts.username or parts.password:
                raise ValueError("thumbnail_path must be a relative path or http(s) URL")
        elif thumbnail_path.startswith("/") or ".." in Path(thumbnail_path).parts or "\\" in thumbnail_path:
            raise ValueError("thumbnail_path must not contain directory traversal")
    return (location_id, summary, video_url, thumbnail_path)


def location_exists(db, location_id):
    return db.execute("SELECT 1 FROM locations WHERE id = ?", (location_id,)).fetchone() is not None


def stories_for(db, location_id=None):
    sql = "SELECT id, location_id, summary, video_url, thumbnail_path, created_at FROM stories"
    params = []
    if location_id is not None:
        sql += " WHERE location_id = ?"
        params.append(location_id)
    sql += " ORDER BY id"
    return [dict(row) for row in db.execute(sql, params)]


class Handler(BaseHTTPRequestHandler):
    def send_json(self, status, value):
        payload = json.dumps(value, ensure_ascii=False, allow_nan=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(payload)

    def read_json(self):
        if self.headers.get("Content-Type", "").split(";", 1)[0].strip().lower() != "application/json":
            raise ValueError("Content-Type must be application/json")
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            raise ValueError("Invalid Content-Length") from None
        if length <= 0 or length > MAX_BODY_BYTES:
            raise ValueError("JSON body is missing or too large")
        try:
            result = json.loads(self.rfile.read(length))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("Invalid JSON") from exc
        if not isinstance(result, dict):
            raise ValueError("JSON body must be an object")
        return result

    def origin_allowed(self):
        # Same-origin check is suitable for this localhost prototype, not full authentication.
        origin = self.headers.get("Origin")
        return not origin or origin == "http://" + self.headers.get("Host", "")

    def do_GET(self):
        path = urlsplit(self.path).path
        query = parse_qs(urlsplit(self.path).query)
        if path == "/api/locations":
            with connect() as db:
                locations = [dict(row) for row in db.execute(
                    "SELECT id, name, latitude, longitude, description FROM locations ORDER BY id"
                )]
                all_stories = stories_for(db)
            grouped = {}
            for story in all_stories:
                grouped.setdefault(story["location_id"], []).append(story)
            for location in locations:
                location["stories"] = grouped.get(location["id"], [])
            return self.send_json(200, locations)
        if path == "/api/stories":
            try:
                location_id = self.filter_id(query)
            except ValueError as exc:
                return self.send_json(400, {"error": str(exc)})
            with connect() as db:
                return self.send_json(200, stories_for(db, location_id))
        static = {
            "/": ("index.html", "text/html"),
            "/index.html": ("index.html", "text/html"),
            "/admin": ("admin.html", "text/html"),
            "/admin.html": ("admin.html", "text/html"),
            "/script.js": ("script.js", "text/javascript"),
            "/style.css": ("style.css", "text/css"),
            "/admin.js": ("admin.js", "text/javascript"),
        }
        if path not in static:
            return self.send_json(404, {"error": "Not found"})
        filename, mime = static[path]
        file_path = PROJECT_DIR / filename
        if not file_path.is_file():
            return self.send_json(404, {"error": f"Missing project file: {filename}"})
        payload = file_path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", mime + "; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    @staticmethod
    def filter_id(query, required=False):
        values = query.get("location_id", [])
        if not values:
            if required:
                raise ValueError("location_id query parameter is required")
            return None
        if len(values) != 1 or not re.fullmatch(r"[1-9][0-9]*", values[0]):
            raise ValueError("location_id must be a positive integer")
        return int(values[0])

    def do_POST(self):
        path = urlsplit(self.path).path
        if path not in ("/api/locations", "/api/stories"):
            return self.send_json(404, {"error": "Not found"})
        if not self.origin_allowed():
            return self.send_json(403, {"error": "Origin not allowed"})
        try:
            data = self.read_json()
            if path == "/api/locations":
                name = required_text(data, "name", 120)
                latitude, longitude = coordinates(data)
                description = required_text(data, "description", 2000)
                with connect() as db:
                    cur = db.execute(
                        "INSERT INTO locations (name, latitude, longitude, description) VALUES (?, ?, ?, ?)",
                        (name, latitude, longitude, description),
                    )
                    result = {"id": cur.lastrowid, "name": name, "latitude": latitude,
                              "longitude": longitude, "description": description, "stories": []}
                return self.send_json(201, result)
            if path == "/api/stories":
                location_id, summary, video_url, thumbnail_path = validate_story(data)
                with connect() as db:
                    if not location_exists(db, location_id):
                        return self.send_json(404, {"error": "Location not found"})
                    cur = db.execute(
                        "INSERT INTO stories (location_id, summary, video_url, thumbnail_path) "
                        "VALUES (?, ?, ?, ?)",
                        (location_id, summary, video_url, thumbnail_path),
                    )
                    result = dict(db.execute(
                        "SELECT * FROM stories WHERE id = ?", (cur.lastrowid,)
                    ).fetchone())
                return self.send_json(201, result)
        except ValueError as exc:
            return self.send_json(400, {"error": str(exc)})

    def do_PUT(self):
        path = urlsplit(self.path).path
        location_match = re.fullmatch(r"/api/locations/([1-9][0-9]*)", path)
        story_match = re.fullmatch(r"/api/stories/([1-9][0-9]*)", path)
        if not (location_match or story_match):
            return self.send_json(404, {"error": "Not found"})
        if not self.origin_allowed():
            return self.send_json(403, {"error": "Origin not allowed"})
        try:
            data = self.read_json()
            if story_match:
                story_id = int(story_match.group(1))
                values = validate_story(data)
                with connect() as db:
                    if not location_exists(db, values[0]):
                        return self.send_json(404, {"error": "Location not found"})
                    cursor = db.execute(
                        "UPDATE stories SET location_id=?, summary=?, video_url=?, thumbnail_path=? WHERE id=?",
                        (*values, story_id),
                    )
                    if cursor.rowcount == 0:
                        return self.send_json(404, {"error": "Story not found"})
                    result = dict(db.execute("SELECT * FROM stories WHERE id=?", (story_id,)).fetchone())
                return self.send_json(200, result)
            location_id = int(location_match.group(1))
            name = required_text(data, "name", 120)
            latitude, longitude = coordinates(data)
            description = required_text(data, "description", 2000)
        except ValueError as exc:
            return self.send_json(400, {"error": str(exc)})
        with connect() as db:
            cur = db.execute(
                "UPDATE locations SET name = ?, latitude = ?, longitude = ?, description = ? WHERE id = ?",
                (name, latitude, longitude, description, location_id),
            )
            if cur.rowcount == 0:
                return self.send_json(404, {"error": "Location not found"})
        self.send_json(200, {"id": location_id, "name": name,
                             "latitude": latitude, "longitude": longitude,
                             "description": description})


def main():
    initialize_database()
    server = ThreadingHTTPServer(("127.0.0.1", 8000), Handler)
    print("Map: http://localhost:8000/\nCMS: http://localhost:8000/admin")
    print("API: /api/locations, /api/stories")
    print("Press Ctrl+C to stop")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
