"""Small local API and web server for the Doha After Dark map."""

import json
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
                        "/script.js": "script.js", "/style.css": "style.css"}.get(path)
            if filename is None:
                self.send_error(404, "Not found")
                return
            payload = (PROJECT_DIR / filename).read_bytes()
            content_type = {"index.html": "text/html", "script.js": "text/javascript",
                            "style.css": "text/css"}[filename] + "; charset=utf-8"

        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


if __name__ == "__main__":
    initialize_database()
    print("Open http://localhost:8000/ in your browser")
    ThreadingHTTPServer(("127.0.0.1", 8000), Handler).serve_forever()
