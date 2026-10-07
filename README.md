# Doha After Dark

Doha After Dark is a UDST Practicum project about exploring Doha at night. It will combine an interactive map with stories, interviews, and multimedia content.

## Pilot Locations

- Souq Waqif
- Doha Corniche
- Katara Cultural Village

## Planned Features

- Interactive night map and location-based stories
- Interviews and multimedia content
- Smart Crowd Prediction and recommendations
- Content Management System (CMS)
- Consent and permission management

## IT Development

Our IT work includes front-end and back-end development, database design, REST APIs, system integration, testing, and deployment.




##### Current Phase: Map and Basic CMS Prototype

The Leaflet map loads location names, descriptions, and coordinates from a SQLite database through the Python API.

In Week 7, I added a basic CMS page to add and edit locations. Saved changes appear on the map after refreshing. I tested adding a location, editing a description, keeping changes after restarting the server, and blocking invalid latitude values.

The background map now uses CARTO Voyager with English labels.

This is a local prototype. Login, story management, and the other planned features are still to be developed.

## How to Run

1. Install Python 3.
2. Open a terminal in the project folder.
3. Run `python server.py` and keep the terminal open.
4. Open http://localhost:8000/ to view the map.
5. Open http://localhost:8000/admin to add or edit locations.
6. Open http://localhost:8000/api/locations to view the JSON data.

The `locations.db` file is created automatically with the three pilot locations. Existing database changes are preserved.

CARTO map tiles require a valid Basemaps API key in the tile URL in `script.js`. Internet access is needed to load the map tiles and external map assets.
