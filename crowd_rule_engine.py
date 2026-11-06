"""Doha After Dark: Mohamed's crowd rules + Ahmed's local API (0–8 scores)."""

import argparse
import json
import re
from datetime import date
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

# PART 1: Mohamed's score tables. Each input contributes 0, 1, or 2 points.
DAY_SCORES = {
    "Sunday": 0, "Monday": 0, "Tuesday": 0, "Wednesday": 0,
    "Thursday": 1, "Friday": 2, "Saturday": 2,
}
TIME_SCORES = {"6AM-4PM": 0, "4PM-7PM": 1, "7PM-12AM": 2}
EVENT_SCORES = {"None": 0, "Small": 1, "Large": 2}
BASELINE_SCORES = {"Quiet": 0, "Moderate": 1, "Busy": 2}
CONFIDENCE_SCORES = {0: 0, 1: 50, 2: 60, 3: 80, 4: 90}
API_URL = "http://127.0.0.1:8000"  # Local computer only, not a public service.


# PART 2: Mohamed's 3 functions: calculate score, classify it, estimate confidence.
def calculate_score(day, time_slot, event, baseline):
    return (DAY_SCORES.get(day, 0) + TIME_SCORES.get(time_slot, 0)
            + EVENT_SCORES.get(event, 0) + BASELINE_SCORES.get(baseline, 0))


def predict_crowd(score):
    if score <= 2:
        return "Quiet"
    if score <= 5:
        return "Moderate"
    return "Busy"


def calculate_confidence(day, time_slot, event, baseline):
    # Count supplied inputs. 90% is a rule-based label, NOT measured accuracy.
    available = sum(value is not None for value in (day, time_slot, event, baseline))
    return CONFIDENCE_SCORES[available]


# PART 3: Turn a time like 10PM into the correct Excel scoring time slot.
def to_time_slot(value):
    if not value:
        return None
    text = value.upper().replace(" ", "").replace("–", "-")
    if text in TIME_SCORES:
        return text
    match = re.fullmatch(r"(1[0-2]|0?[1-9])(?::([0-5][0-9]))?(AM|PM)", text)
    if not match:
        raise ValueError("Use a time such as 10PM, 5:30PM, or 7PM-12AM")
    hour = int(match.group(1)) % 12
    minute = int(match.group(2) or 0)
    if match.group(3) == "PM":
        hour += 12
    minutes = 60 * hour + minute
    if 360 <= minutes < 960:     # 6 AM to just before 4 PM
        return "6AM-4PM"
    if 960 <= minutes < 1140:    # 4 PM to just before 7 PM
        return "4PM-7PM"
    if minutes >= 1140 or minutes == 0:  # 7 PM to midnight
        return "7PM-12AM"
    raise ValueError("The Excel rules do not cover 12:01AM–5:59AM")


# PART 4: Check the inputs before applying the scoring rules.
def check_choice(value, table, label):
    if value is None or not value.strip():
        return None  # Missing input is allowed for calculation, but not submission.
    name = value.strip().title()
    if name not in table:
        raise ValueError(f"Invalid {label}: choose {', '.join(table)}")
    return name


def make_prediction(location, day, time, event, baseline):
    if not location.strip():
        raise ValueError("Location name is required")
    if day and day.strip() and re.fullmatch(r"\d{4}-\d{2}-\d{2}", day.strip()):
        day = date.fromisoformat(day.strip()).strftime("%A")
    day = check_choice(day, DAY_SCORES, "day")
    time_slot = to_time_slot(time)
    event = check_choice(event, EVENT_SCORES, "event")
    baseline = check_choice(baseline, BASELINE_SCORES, "baseline")

    # The breakdown shows exactly where the 0–8 score comes from.
    breakdown = {
        "time": TIME_SCORES.get(time_slot, 0),
        "day": DAY_SCORES.get(day, 0),
        "event": EVENT_SCORES.get(event, 0),
        "historical_baseline": BASELINE_SCORES.get(baseline, 0),
    }
    score = calculate_score(day, time_slot, event, baseline)
    confidence = calculate_confidence(day, time_slot, event, baseline)
    return {
        "location": location.strip(), "total_score": score,
        "prediction": predict_crowd(score), "confidence_percent": confidence,
        "score_breakdown": breakdown,
        "complete": all(item is not None for item in (day, time_slot, event, baseline)),
    }


# PART 5: Send one TEST result to Ahmed's Python API, which saves it in SQLite.
def send_to_api(result, location_id, api_url=API_URL):
    if location_id is None or location_id <= 0:
        raise ValueError("Use a positive --location-id with --send-test")
    if not result["complete"]:
        raise ValueError("Supply all four inputs before --send-test")

    # Check that the ID really belongs to the selected location.
    with urlopen(api_url + "/api/locations", timeout=5) as response:
        locations = json.load(response)
    match = next((row for row in locations if row["id"] == location_id), None)
    if not match:
        raise ValueError(f"Location ID {location_id} does not exist")
    actual = match["name"].strip().casefold()
    typed = result["location"].casefold()
    if actual != typed and not (typed == "katara" and actual == "katara cultural village"):
        raise ValueError(f"Location ID {location_id} belongs to {match['name']}")

    # API expects confidence between 0 and 1: 90% becomes 0.9.
    payload = {
        "location_id": location_id,
        "total_score": result["total_score"],
        "prediction": result["prediction"],
        "confidence": result["confidence_percent"] / 100,
        "score_breakdown": result["score_breakdown"],
        "source": "test",  # No live crowd measurements are used.
    }
    request = Request(api_url + "/api/crowd-predictions",
                      data=json.dumps(payload).encode("utf-8"),
                      headers={"Content-Type": "application/json"}, method="POST")
    with urlopen(request, timeout=5) as response:
        return json.load(response)["id"]  # The saved SQLite record number.


# PART 6: PowerShell arguments, simple result display, optional API submission.
def main():
    parser = argparse.ArgumentParser(description="Doha After Dark crowd scoring (0–8)")
    parser.add_argument("--location", required=True)
    parser.add_argument("--location-id", type=int)
    parser.add_argument("--day")
    parser.add_argument("--time")
    parser.add_argument("--event")
    parser.add_argument("--baseline")
    parser.add_argument("--send-test", action="store_true", help="Save a new test record in SQLite")
    args = parser.parse_args()

    try:
        result = make_prediction(args.location, args.day, args.time, args.event, args.baseline)
        print(f"Location: {result['location']}")
        print(f"Crowd score: {result['total_score']}/8")
        print(f"Prediction: {result['prediction']}")
        print(f"Confidence: {result['confidence_percent']}% (rule-based)")
        if not result["complete"]:
            print("Note: Some inputs are missing; the result is provisional.")
        if args.send_test:
            record_id = send_to_api(result, args.location_id)
            print(f"API: Saved successfully (record ID: {record_id})")
    except (ValueError, HTTPError, URLError, OSError) as error:
        print(f"Error: {error}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
