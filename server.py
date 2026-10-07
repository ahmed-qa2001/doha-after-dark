"""Small local API and web server for the Doha After Dark map."""

import json
import math
import re
import sqlite3
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit


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


def initialize_database():
    with sqlite3.connect(DATABASE) as connection:
        connection.execute("""
            CREATE TABLE IF NOT EXISTS locations (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                latitude REAL NOT NULL,
                longitude REAL NOT NULL,
                description TEXT NOT NULL
            )
        """)
        if connection.execute("SELECT COUNT(*) FROM locations").fetchone()[0] == 0:
            connection.executemany(
                "INSERT INTO locations (name, latitude, longitude, description) "
                "VALUES (?, ?, ?, ?)",
                SEED_LOCATIONS,
            )


class Handler(BaseHTTPRequestHandler):
    def send_json(self, status, data):
        payload = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def save_location(self, location_id=None):
        # This prototype is served locally. Reject writes from other websites.
        origin = self.headers.get("Origin")
        if origin and origin != "http://" + self.headers.get("Host", ""):
            self.send_json(403, {"error": "Origin not allowed."})
            return
        try:
            if self.headers.get("Content-Type", "").split(";")[0].strip() != "application/json":
                raise ValueError("Send location data as JSON.")
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 16384:
                raise ValueError("Invalid request size.")
            data = json.loads(self.rfile.read(length))
            if not isinstance(data, dict):
                raise ValueError("A location object is required.")
            name, description = data.get("name"), data.get("description")
            if not isinstance(name, str) or not name.strip() or len(name.strip()) > 120:
                raise ValueError("Enter a name of 1 to 120 characters.")
            if not isinstance(description, str) or not description.strip() or len(description.strip()) > 2000:
                raise ValueError("Enter a description of 1 to 2000 characters.")
            coordinates = []
            for field, limit in [("latitude", 90), ("longitude", 180)]:
                value = data.get(field)
                if isinstance(value, bool) or value is None or value == "":
                    raise ValueError("Enter valid coordinates.")
                value = float(value)
                if not math.isfinite(value) or not -limit <= value <= limit:
                    raise ValueError(f"{field.capitalize()} must be between {-limit} and {limit}.")
                coordinates.append(value)
            values = (name.strip(), *coordinates, description.strip())
        except (ValueError, TypeError, UnicodeDecodeError):
            self.send_json(400, {"error": "Check the name, description and coordinates. Latitude: -90 to 90; longitude: -180 to 180."})
            return
        with sqlite3.connect(DATABASE) as connection:
            if location_id is None:
                cursor = connection.execute(
                    "INSERT INTO locations (name, latitude, longitude, description) VALUES (?, ?, ?, ?)", values)
                location_id = cursor.lastrowid
                status = 201
            else:
                cursor = connection.execute(
                    "UPDATE locations SET name=?, latitude=?, longitude=?, description=? WHERE id=?", (*values, location_id))
                if cursor.rowcount == 0:
                    self.send_json(404, {"error": "Location not found."})
                    return
                status = 200
        self.send_json(status, {"id": location_id, "name": values[0], "latitude": values[1],
                                "longitude": values[2], "description": values[3]})

    def do_POST(self):
        if urlsplit(self.path).path != "/api/locations":
            self.send_json(404, {"error": "Not found."})
            return
        self.save_location()

    def do_PUT(self):
        match = re.fullmatch(r"/api/locations/([0-9]+)", urlsplit(self.path).path)
        if not match:
            self.send_json(404, {"error": "Not found."})
            return
        self.save_location(int(match.group(1)))

    def do_GET(self):
        path = urlsplit(self.path).path
        if path == "/api/locations":
            with sqlite3.connect(DATABASE) as connection:
                connection.row_factory = sqlite3.Row
                rows = connection.execute(
                    "SELECT id, name, latitude, longitude, description "
                    "FROM locations ORDER BY id"
                ).fetchall()
            payload = json.dumps([dict(row) for row in rows]).encode("utf-8")
            content_type = "application/json; charset=utf-8"
        else:
            filename = {"/": "index.html", "/index.html": "index.html",
                        "/script.js": "script.js", "/style.css": "style.css",
                        "/admin": "admin.html", "/admin.html": "admin.html",
                        "/admin.js": "admin.js"}.get(path)
            if filename is None:
                self.send_error(404, "Not found")
                return
            payload = (PROJECT_DIR / filename).read_bytes()
            content_type = {"index.html": "text/html", "script.js": "text/javascript",
                            "style.css": "text/css", "admin.html": "text/html", "admin.js": "text/javascript"}[filename] + "; charset=utf-8"

        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


if __name__ == "__main__":
    initialize_database()
    print("Open http://localhost:8000/ in your browser")
    ThreadingHTTPServer(("127.0.0.1", 8000), Handler).serve_forever()