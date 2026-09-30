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

## Current Phase: Map Prototype

The map now gets its three pilot locations from a SQLite database. The Python server sends the location data to the map through `/api/locations`. The CMS and other planned features have not been built yet.

To run the map, open a terminal in the project folder and type `python server.py`. Keep the terminal open, then visit http://localhost:8000/. To view the location data, visit http://localhost:8000/api/locations. The database file, `locations.db`, is created automatically.
