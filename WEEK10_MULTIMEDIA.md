# Week 10: Multimedia Story Metadata API

This update adds **story metadata only** to the existing Doha After Dark Python/SQLite project. Crowd rating and prediction work are explicitly out of scope.

## Database
New `stories` table linked to `locations.id` with fields:
`id`, `location_id`, `summary`, `video_url`, `thumbnail_path`, `created_at`.
Existing location rows and CMS routes are preserved by `initialize_database()`.

## API
- `GET /api/locations`: returns existing fields plus `stories` array per location.
- `GET /api/stories`: list stories.
- `GET /api/stories?location_id=1`: filter by location.
- `POST /api/stories`: create multimedia metadata.
- `PUT /api/stories/1`: edit metadata.

Example PowerShell:
```powershell
python server.py
$story = @{ location_id = 1; summary = "Souq Waqif after dark"; video_url = "https://example.com/video.mp4"; thumbnail_path = "media/souq.jpg" } | ConvertTo-Json
Invoke-RestMethod -Uri http://localhost:8000/api/stories -Method Post -ContentType application/json -Body $story
Invoke-RestMethod -Uri 'http://localhost:8000/api/stories?location_id=1'
```
The URL in the example is placeholder metadata, not a real project video. Thumbnail file uploads, video hosting, publication controls, and popup rendering are not implemented yet.

## Local verification
A standalone test package covering nine multimedia API tests is available separately. The tests run on a temporary SQLite database. Run the server locally and take screenshots of successful API results for the COMP4101 logbook.

**Security:** Local prototype only; write routes are unauthenticated and must not be exposed publicly.