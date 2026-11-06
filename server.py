"""Doha After Dark: local CMS, multimedia, and original 0-8 crowd score API.

The server connects the map, the CMS, and the crowd rule engine to SQLite.
Start with Handler below to see what happens when a request arrives.

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
MEDIA_TYPES = {
    ".svg": "image/svg+xml", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
    ".png": "image/png", ".webp": "image/webp", ".mp4": "video/mp4",
    ".webm": "video/webm", ".wav": "audio/wav", ".mp3": "audio/mpeg",
}


# 1. Set up SQLite and upgrade older copies of locations.db.

@contextmanager
def connect():
    # Rows can be read by column name, such as row["location_id"].
    connection = sqlite3.connect(DATABASE, timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    try:
        # Save changes on success, or undo the transaction if an error occurs.
        with connection:
            yield connection
    finally:
        connection.close()


def initialize_database():
    """Create new tables without deleting or rewriting previously saved locations."""
    with connect() as db:
        # Run the setup as one transaction so a failed upgrade can roll back.
        db.execute("BEGIN IMMEDIATE")
        db.execute("""
            CREATE TABLE IF NOT EXISTS locations (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                latitude REAL NOT NULL,
                longitude REAL NOT NULL,
                description TEXT NOT NULL
            )
        """)
        # One location may contain multiple stories.
        db.execute("""
            CREATE TABLE IF NOT EXISTS stories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                location_id INTEGER NOT NULL,
                summary TEXT NOT NULL,
                video_url TEXT,
                thumbnail_path TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                audio_url TEXT,
                author_credit TEXT,
                rich_description TEXT,
                FOREIGN KEY (location_id) REFERENCES locations(id) ON DELETE CASCADE
            )
        """)
        # Add Week 11 fields to existing databases without replacing saved stories.
        story_columns = {row["name"] for row in db.execute("PRAGMA table_info(stories)")}
        for column in ("audio_url", "author_credit", "rich_description"):
            if column not in story_columns:
                db.execute(f"ALTER TABLE stories ADD COLUMN {column} TEXT")
        db.execute("CREATE INDEX IF NOT EXISTS idx_stories_location ON stories(location_id)")
        # Change from the earlier 1-5 test API to Mohamed's 0-8 rule-engine score.
        # The old 1-5 data MUST NOT be silently relabeled as scores out of 8.
        # Keep those rows in a separate, clearly named legacy table.
        existing = db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='crowd_predictions'"
        ).fetchone()
        if existing:
            columns = {row[1] for row in db.execute("PRAGMA table_info(crowd_predictions)")}
            if "total_score" not in columns and "crowd_rating" in columns:
                old_backup = db.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' "
                    "AND name='crowd_predictions_legacy_1to5'"
                ).fetchone()
                if old_backup:
                    raise RuntimeError("Legacy table already exists; manually review migration")
                db.execute("ALTER TABLE crowd_predictions RENAME TO crowd_predictions_legacy_1to5")
            elif "total_score" not in columns:
                raise RuntimeError("Unrecognized crowd_predictions schema; no changes made")
        db.execute("""
            CREATE TABLE IF NOT EXISTS crowd_predictions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                location_id INTEGER NOT NULL,
                total_score INTEGER NOT NULL CHECK(total_score BETWEEN 0 AND 8),
                prediction TEXT NOT NULL CHECK(prediction IN ('Quiet', 'Moderate', 'Busy')),
                confidence REAL CHECK(confidence IS NULL OR confidence BETWEEN 0 AND 1),
                source TEXT NOT NULL DEFAULT 'test' CHECK(source IN ('test', 'algorithm')),
                score_breakdown_json TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (location_id) REFERENCES locations(id) ON DELETE CASCADE
            )
        """)
        db.execute("CREATE INDEX IF NOT EXISTS idx_crowd_predictions_score08_location "
                   "ON crowd_predictions(location_id)")
        # Add the three pilot venues only when the locations table is empty.
        if db.execute("SELECT COUNT(*) FROM locations").fetchone()[0] == 0:
            db.executemany(
                "INSERT INTO locations (name, latitude, longitude, description) VALUES (?, ?, ?, ?)",
                SEED_LOCATIONS,
            )


# 2. Check incoming data before writing it to SQLite.

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
    # Use the same number check for latitude and longitude, with different limits.
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


def media_filename(path):
    # Serve only flat, named media files from the project's media folder.
    if re.fullmatch(r"/media/[A-Za-z0-9_-]+\.[A-Za-z0-9]+", path):
        return Path(path).name
    return None


def valid_media_url(value, key, local_suffixes):
    if value is None:
        return
    parts = urlsplit(value)
    if (parts.scheme in ("http", "https") and parts.hostname
            and parts.username is None and parts.password is None):
        return
    if value.startswith("media/") and media_filename("/" + value):
        if Path(value).suffix.lower() in local_suffixes:
            return
    raise ValueError(f"{key} must be an http(s) URL or a supported media/ path")


def validate_story(data):
    # The story belongs to a location. Its media fields are optional.
    location_id = positive_id(data.get("location_id"))
    summary = required_text(data, "summary", 2000)
    video_url = optional_text(data, "video_url")
    thumbnail_path = optional_text(data, "thumbnail_path")
    audio_url = optional_text(data, "audio_url")
    author_credit = optional_text(data, "author_credit", 200)
    rich_description = optional_text(data, "rich_description", 6000)
    valid_media_url(video_url, "video_url", (".mp4", ".webm"))
    valid_media_url(audio_url, "audio_url", (".wav", ".mp3"))
    if thumbnail_path:
        parts = urlsplit(thumbnail_path)
        if parts.scheme:
            valid_media_url(thumbnail_path, "thumbnail_path", ())
        elif thumbnail_path.startswith("/") or ".." in Path(thumbnail_path).parts or "\\" in thumbnail_path:
            raise ValueError("thumbnail_path must not contain directory traversal")
    return {
        "location_id": location_id, "summary": summary, "video_url": video_url,
        "thumbnail_path": thumbnail_path, "audio_url": audio_url,
        "author_credit": author_credit, "rich_description": rich_description,
    }


def score_label(score):
    """Exact label boundaries from Mohamed's rule table."""
    if score <= 2:
        return "Quiet"
    if score <= 5:
        return "Moderate"
    return "Busy"


def validate_prediction(data):
    """Accept the original 0-8 total, not the retired 1-5 demo rating."""
    location_id = positive_id(data.get("location_id"))
    if "crowd_rating" in data:
        raise ValueError("Use total_score (0 to 8), not legacy crowd_rating (1 to 5)")
    total_score = data.get("total_score")
    if (isinstance(total_score, bool) or not isinstance(total_score, int)
            or not 0 <= total_score <= 8):
        raise ValueError("total_score must be an integer from 0 to 8")
    prediction = score_label(total_score)
    if "prediction" in data and data["prediction"] != prediction:
        raise ValueError("prediction does not match total_score")
    confidence = data.get("confidence")
    if confidence is not None:
        if (isinstance(confidence, bool) or not isinstance(confidence, (int, float))
                or not math.isfinite(confidence) or not 0 <= confidence <= 1):
            raise ValueError("confidence must be a number from 0 to 1")
        confidence = float(confidence)
    source = data.get("source", "test")
    if source not in ("test", "algorithm"):
        raise ValueError("source must be 'test' or 'algorithm'")
    breakdown = data.get("score_breakdown")
    if breakdown is not None:
        # If the engine sends the four individual scores, check they add up.
        expected_keys = {"time", "day", "event", "historical_baseline"}
        if not isinstance(breakdown, dict) or set(breakdown) != expected_keys:
            raise ValueError("score_breakdown must contain time, day, event, historical_baseline")
        if any(isinstance(x, bool) or not isinstance(x, int) or not 0 <= x <= 2
               for x in breakdown.values()):
            raise ValueError("Each score_breakdown value must be an integer from 0 to 2")
        if sum(breakdown.values()) != total_score:
            raise ValueError("score_breakdown sum must match total_score")
    return location_id, total_score, prediction, confidence, source, (
        json.dumps(breakdown, ensure_ascii=False) if breakdown is not None else None
    )


# 3. Read saved data and prepare it for JSON responses.

def location_exists(db, location_id):
    return db.execute("SELECT 1 FROM locations WHERE id = ?", (location_id,)).fetchone() is not None


def stories_for(db, location_id=None):
    sql = "SELECT * FROM stories"
    params = []
    if location_id is not None:
        sql += " WHERE location_id = ?"
        params.append(location_id)
    sql += " ORDER BY id"
    return [dict(row) for row in db.execute(sql, params)]


# Both the history endpoint and the save response use the location's current name.
PREDICTION_SELECT = """
    SELECT cp.id, cp.location_id, l.name AS location_name,
           cp.total_score, cp.prediction, cp.confidence, cp.source,
           cp.score_breakdown_json, cp.created_at
    FROM crowd_predictions AS cp
    JOIN locations AS l ON l.id = cp.location_id
"""


def prediction_row(row):
    result = dict(row)
    # SQLite stores the breakdown as text. Convert it back into a JSON object.
    breakdown = result.pop("score_breakdown_json")
    result["score_breakdown"] = json.loads(breakdown) if breakdown else None
    return result


def predictions_for(db, location_id=None):
    sql = PREDICTION_SELECT
    params = []
    if location_id is not None:
        sql += " WHERE cp.location_id = ?"
        params.append(location_id)
    sql += " ORDER BY cp.id DESC"
    return [prediction_row(row) for row in db.execute(sql, params)]


def latest_crowd_by_location(db):
    # A location can have many predictions. Its newest saved row has the highest ID.
    rows = db.execute("""
        SELECT cp.location_id, cp.total_score, cp.prediction, cp.source, cp.created_at
        FROM locations AS l
        JOIN crowd_predictions AS cp ON cp.id = (
            SELECT MAX(id) FROM crowd_predictions WHERE location_id = l.id
        )
    """)
    return {row["location_id"]: dict(row) for row in rows}


# 4. Answer requests from the map, the CMS, and the crowd rule engine.

class Handler(BaseHTTPRequestHandler):
    # A response includes a status code, headers, and the JSON body.
    def send_json(self, status, value):
        payload = json.dumps(value, ensure_ascii=False, allow_nan=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(payload)

    def read_json(self):
        # Check the format and size before reading a request body.
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
        # GET reads data or serves a file. Split the URL into its path and filters.
        url = urlsplit(self.path)
        path = url.path
        query = parse_qs(url.query)
        if path == "/api/locations":
            with connect() as db:
                # Read locations, stories, and predictions from the same database snapshot.
                db.execute("BEGIN")
                locations = [dict(row) for row in db.execute(
                    "SELECT id, name, latitude, longitude, description FROM locations ORDER BY id"
                )]
                all_stories = stories_for(db)
                latest_crowd = latest_crowd_by_location(db)
            # Group stories by venue so each map marker gets its own stories.
            grouped = {}
            for story in all_stories:
                grouped.setdefault(story["location_id"], []).append(story)
            for location in locations:
                location_id = location["id"]
                location["stories"] = grouped.get(location_id, [])
                location["crowd_status"] = latest_crowd.get(location_id)
            return self.send_json(200, locations)
        # Both list endpoints accept the same optional ?location_id= filter.
        if path in ("/api/stories", "/api/crowd-predictions"):
            try:
                location_id = self.filter_id(query)
            except ValueError as exc:
                return self.send_json(400, {"error": str(exc)})
            with connect() as db:
                if path == "/api/stories":
                    return self.send_json(200, stories_for(db, location_id))
                return self.send_json(200, predictions_for(db, location_id))

        # The browser can request the listed site files and supported demo media.
        static = {
            "/": ("index.html", "text/html"),
            "/index.html": ("index.html", "text/html"),
            "/admin": ("admin.html", "text/html"),
            "/admin.html": ("admin.html", "text/html"),
            "/script.js": ("script.js", "text/javascript"),
            "/style.css": ("style.css", "text/css"),
            "/admin.js": ("admin.js", "text/javascript"),
        }
        if path in static:
            filename, mime = static[path]
            file_path = PROJECT_DIR / filename
            mime += "; charset=utf-8"
        else:
            filename = media_filename(path)
            mime = MEDIA_TYPES.get(Path(filename).suffix.lower()) if filename else None
            if not mime:
                return self.send_json(404, {"error": "Not found"})
            file_path = PROJECT_DIR / "media" / filename
            if file_path.resolve().parent != PROJECT_DIR / "media":
                return self.send_json(404, {"error": "Not found"})
        if not file_path.is_file():
            return self.send_json(404, {"error": f"Missing project file: {filename}"})
        payload = file_path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    @staticmethod
    def filter_id(query):
        values = query.get("location_id", [])
        if not values:
            return None
        if len(values) != 1 or not re.fullmatch(r"[1-9][0-9]*", values[0]):
            raise ValueError("location_id must be a positive integer")
        return int(values[0])

    def do_POST(self):
        # POST creates a new location, story, or crowd prediction.
        path = urlsplit(self.path).path
        if path not in ("/api/locations", "/api/stories", "/api/crowd-predictions"):
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
                story = validate_story(data)
                with connect() as db:
                    if not location_exists(db, story["location_id"]):
                        return self.send_json(404, {"error": "Location not found"})
                    cur = db.execute(
                        "INSERT INTO stories (location_id, summary, video_url, thumbnail_path, "
                        "audio_url, author_credit, rich_description) VALUES "
                        "(:location_id, :summary, :video_url, :thumbnail_path, "
                        ":audio_url, :author_credit, :rich_description)",
                        story,
                    )
                    result = dict(db.execute(
                        "SELECT * FROM stories WHERE id = ?", (cur.lastrowid,)
                    ).fetchone())
                return self.send_json(201, result)
            if path == "/api/crowd-predictions":
                (location_id, total_score, prediction, confidence, source, breakdown_json) = validate_prediction(data)
                with connect() as db:
                    if not location_exists(db, location_id):
                        return self.send_json(404, {"error": "Location not found"})
                    cursor = db.execute(
                        "INSERT INTO crowd_predictions "
                        "(location_id, total_score, prediction, confidence, source, score_breakdown_json) "
                        "VALUES (?, ?, ?, ?, ?, ?)",
                        (location_id, total_score, prediction, confidence, source, breakdown_json),
                    )
                    row = db.execute(
                        PREDICTION_SELECT + " WHERE cp.id = ?",
                        (cursor.lastrowid,),
                    ).fetchone()
                    result = prediction_row(row)
                return self.send_json(201, result)
        except ValueError as exc:
            return self.send_json(400, {"error": str(exc)})

    def do_PUT(self):
        # PUT edits an existing record. The last part of the URL is its ID.
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
                story = validate_story(data)
                story["id"] = story_id
                with connect() as db:
                    # Read and update together so another request cannot edit between them.
                    db.execute("BEGIN IMMEDIATE")
                    previous = db.execute("SELECT * FROM stories WHERE id=?", (story_id,)).fetchone()
                    if previous is None:
                        return self.send_json(404, {"error": "Story not found"})
                    if not location_exists(db, story["location_id"]):
                        return self.send_json(404, {"error": "Location not found"})
                    # Older callers can omit Week 11 fields when editing a story.
                    for field in ("audio_url", "author_credit", "rich_description"):
                        if field not in data:
                            story[field] = previous[field]
                    db.execute(
                        "UPDATE stories SET location_id=:location_id, summary=:summary, "
                        "video_url=:video_url, thumbnail_path=:thumbnail_path, audio_url=:audio_url, "
                        "author_credit=:author_credit, rich_description=:rich_description WHERE id=:id",
                        story,
                    )
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


# 5. Start the local server after the database is ready.

def main():
    initialize_database()
    server = ThreadingHTTPServer(("127.0.0.1", 8000), Handler)
    print("Map: http://localhost:8000/\nCMS: http://localhost:8000/admin")
    print("API: http://localhost:8000/api/locations, http://localhost:8000/api/stories, http://localhost:8000/api/crowd-predictions")
    print("Video:     http://localhost:8000/media/souq-demo.mp4")
    print("Thumbnail: http://localhost:8000/media/souq-demo.svg")
    print("Audio:     http://localhost:8000/media/souq-demo.wav")
    print("Press Ctrl+C to stop")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
