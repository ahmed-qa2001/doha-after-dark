# Doha After Dark
Doha After Dark is a UDST Practicum project about exploring Doha at night. It will combine an interactive map with stories, interviews, and multimedia content.

# Pilot Locations
Souq Waqif
Doha Corniche
Katara Cultural Village


# Planned Features
Interactive night map and location-based stories
Interviews and multimedia content
Smart Crowd Prediction and recommendations
Content Management System (CMS)
Consent and permission management


# IT Development
Our IT work includes front-end and back-end development, database design, REST APIs, system integration, testing, and deployment.

# Current Phase: Week 10 – Multimedia API and Smart Crowd Prediction Integration
The Leaflet map loads location names, descriptions, and coordinates from a SQLite database through the Python API.

In Week 7, I added a basic CMS page to add and edit locations. Saved changes appear on the map after refreshing. I tested adding a location, editing a description, keeping changes after restarting the server, and blocking invalid latitude values.

The background map now uses CARTO Voyager with English labels.

This local prototype now supports location management, multimedia metadata, and rule-based crowd predictions. Media uploads, user authentication, and live crowd data integration remain future work.

# How to Run

Install Python 3.
Open a terminal in the project folder.
Run python server.py and keep the terminal open.
Open http://localhost:8000/ to view the map.
Open http://localhost:8000/admin to add or edit locations.
Open http://localhost:8000/api/locations to view the JSON data.
The locations.db file is created automatically with the three pilot locations. Existing database changes are preserved.

CARTO map tiles require a valid Basemaps API key in the tile URL in script.js. Internet access is needed to load the map tiles and external map assets.


---

## Week 10 – Backend API Expansion

### 1. Multimedia Metadata

Expanded the SQLite database and Python API to support multimedia story information.

Implemented:
- Created a stories table linked to locations.
- Added story summaries, video URLs, and thumbnail paths.
- Added API endpoints to create, retrieve, and update stories.
- Tested input validation and database persistence.
- Kept the existing location CMS working.

API Endpoints:
- GET /api/stories
- GET /api/stories?location_id=1
- POST /api/stories
- PUT /api/stories/1

Note: The API currently stores multimedia metadata only. Actual video and image uploads are not implemented.

### 2. Smart Crowd Prediction

Integrated a Python rule-based crowd prediction engine using Mohamed's scoring rules.

The prediction uses four inputs:
- Time of day: 0–2 points
- Day of week: 0–2 points
- Event activity: 0–2 points
- Historical crowd baseline: 0–2 points

Crowd Classification:
- 0–2 = Quiet
- 3–5 = Moderate
- 6–8 = Busy

The engine calculates the total score, prediction category, and rule-based confidence.

### 3. Python API Integration

The crowd_rule_engine.py script calculates predictions and sends them to server.py.

The Python API validates the results and stores them in SQLite.

API Endpoints:
- GET /api/crowd-predictions
- POST /api/crowd-predictions

Each saved prediction includes:
- Location ID
- Location name
- Total score (0–8)
- Prediction category
- Confidence value
- Score breakdown
- Timestamp

### 4. How to Test

Step 1: Start the Python server.

    python server.py

Step 2: Open another PowerShell terminal.

Step 3: Run the rule engine for Souq Waqif.

    python crowd_rule_engine.py --location "Souq Waqif" --location-id 1 --day Sunday --time 10PM --event none --baseline busy --send-test

Step 4: Open the prediction API.

    http://localhost:8000/api/crowd-predictions

The API will display the saved prediction with its location name and scoring information.

### 5. Testing Results

Successfully tested the three pilot locations:

| Location | Score | Prediction |
|---|---|---|
| Souq Waqif | 4/8 | Moderate |
| Doha Corniche | 4/8 | Moderate |
| Katara Cultural Village | 6/8 | Busy |

Additional tests:
- Multimedia story creation and editing.
- Multimedia metadata retrieval.
- Invalid URL rejection.
- Crowd prediction score validation (0–8).
- SQLite persistence after server restart.
- Crowd rule engine and API integration.
- Existing CMS functionality.
- Dynamic location names in API responses.

All predictions currently use example inputs for testing, not live crowd measurements.

Confidence is rule-based and does not represent measured prediction accuracy.

### 6. Current Limitations

- Real-time crowd data is not connected.
- Qatar Calendar event integration is not implemented.
- Historical crowd data is currently supplied manually.
- Predictions are not yet displayed on the Leaflet map.
- Media uploads and video playback are not implemented.
- The local API does not include user authentication.

### 7. Updated Project Files

- server.py – Python backend, REST API, and SQLite integration.
- crowd_rule_engine.py – Crowd prediction scoring algorithm.
- locations.db – SQLite database.
- admin.html / admin.js – Location CMS.
- index.html / script.js – Interactive Leaflet map.

