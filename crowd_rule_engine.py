"""Doha After Dark – Smart Crowd Prediction Rule Engine v1.0.

Scoring and confidence are transcribed from Mohamed's SmartPredWEEK5.xlsx.
The rule engine is deterministic; it does not query Qatar Calendar, fetch
opening hours, estimate real attendance, or train a machine-learning model.

Run `python crowd_rule_engine.py --help` for CLI instructions.
Python 3.9+; no third-party packages.
"""

from __future__ import annotations

import argparse
from datetime import date, datetime, time
import json
import re
import sys
from typing import Any, Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

# Source: SmartPredWEEK5.xlsx, Sheet1, B3:D15, B20:B22, H6:I11.
DAY_SCORES = {
    "sunday": 0, "monday": 0, "tuesday": 0, "wednesday": 0,
    "thursday": 1, "friday": 2, "saturday": 2,
}
EVENT_SCORES = {"none": 0, "small": 1, "large": 2}
BASELINE_SCORES = {"quiet": 0, "moderate": 1, "busy": 2}
CONFIDENCE_BY_INPUT_COUNT = {0: 0.0, 1: 0.5, 2: 0.6, 3: 0.8, 4: 0.9}


def _normalize(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("Input values must be text")
    value = value.strip().lower()
    return value or None


def parse_day(value: Optional[str]) -> Optional[str]:
    """Accept weekday names or ISO dates; missing day decreases confidence."""
    value = _normalize(value)
    if value is None:
        return None
    if value in DAY_SCORES:
        return value
    abbreviated = {
        "sun": "sunday", "mon": "monday", "tue": "tuesday",
        "tues": "tuesday", "wed": "wednesday", "thu": "thursday",
        "thur": "thursday", "thurs": "thursday", "fri": "friday", "sat": "saturday",
    }
    if value in abbreviated:
        return abbreviated[value]
    try:
        parsed_date = date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("day must be a weekday name or YYYY-MM-DD") from exc
    return parsed_date.strftime("%A").lower()


def parse_time(value: Optional[str]) -> Optional[time]:
    """Accept '20:00', '8PM', '8 PM', '5:30 PM', or '20:00:00'."""
    value = _normalize(value)
    if value is None:
        return None
    value = value.replace(" ", "")
    match = re.fullmatch(r"(\d{1,2})(?::(\d{2})(?::(\d{2}))?)?(am|pm)", value)
    if match:
        hour = int(match.group(1))
        minute = int(match.group(2) or 0)
        second = int(match.group(3) or 0)
        if not (1 <= hour <= 12 and 0 <= minute <= 59 and 0 <= second <= 59):
            raise ValueError("Invalid 12-hour time")
        hour = hour % 12 + (12 if match.group(4) == "pm" else 0)
        return time(hour, minute, second)
    for format_string in ("%H:%M", "%H:%M:%S"):
        try:
            return datetime.strptime(value, format_string).time()
        except ValueError:
            continue
    raise ValueError("time must look like '8PM', '5:30 PM' or '20:00'")


def score_time(value: Optional[str]) -> Optional[int]:
    parsed = parse_time(value)
    if parsed is None:
        return None
    minutes = parsed.hour * 60 + parsed.minute
    # Workbook time slots: 6AM–4PM=0; 4PM–7PM=1; 7PM–12AM=2.
    # Boundary policy: 4PM begins the second slot, 7PM the third.
    # Midnight itself belongs to the previous late-night slot.
    if minutes == 0:
        return 2
    if 6 * 60 <= minutes < 16 * 60:
        return 0
    if 16 * 60 <= minutes < 19 * 60:
        return 1
    if 19 * 60 <= minutes <= 23 * 60 + 59:
        return 2
    raise ValueError("No scoring rule covers 12:01 AM–5:59 AM in the workbook")


def score_event(value: Optional[str]) -> Optional[int]:
    value = _normalize(value)
    if value is None:
        return None
    normalized = {
        "none": "none", "no event": "none", "no events": "none",
        "small": "small", "small event": "small", "local": "small",
        "local event": "small", "small/local event": "small",
        "large": "large", "large event": "large",
    }.get(value)
    if normalized is None:
        raise ValueError("event must be 'none', 'small', or 'large'")
    return EVENT_SCORES[normalized]


def score_baseline(value: Optional[str]) -> Optional[int]:
    value = _normalize(value)
    if value is None:
        return None
    if value not in BASELINE_SCORES:
        raise ValueError("baseline must be 'quiet', 'moderate', or 'busy'")
    return BASELINE_SCORES[value]


def score_to_label(total_score: int) -> str:
    if not 0 <= total_score <= 8:
        raise ValueError("total_score must be between 0 and 8")
    if total_score <= 2:
        return "Quiet"
    if total_score <= 5:
        return "Moderate"
    return "Busy"


def calculate_prediction(
    *, location: str, day: Optional[str] = None,
    time_of_day: Optional[str] = None, event: Optional[str] = None,
    baseline: Optional[str] = None, event_name: Optional[str] = None,
    event_venue: Optional[str] = None, data_source: Optional[str] = None,
) -> dict[str, Any]:
    """Calculate deterministic rule scores; absent inputs lower confidence.

    Missing inputs contribute zero to the *observed score* but are explicitly
    flagged so the observed category is not confused with a confident result.
    """
    if not isinstance(location, str) or not location.strip():
        raise ValueError("location is required")
    parsed_day = parse_day(day)
    breakdown = {
        "time": score_time(time_of_day),
        "day": DAY_SCORES[parsed_day] if parsed_day else None,
        "event": score_event(event),
        "historical_baseline": score_baseline(baseline),
    }
    available_count = sum(value is not None for value in breakdown.values())
    total = sum(value for value in breakdown.values() if value is not None)
    missing = [name for name, score in breakdown.items() if score is None]
    high = total + 2 * len(missing)
    possible_categories = list(dict.fromkeys(score_to_label(s) for s in range(total, high + 1)))
    complete = available_count == 4
    result = {
        "location": location.strip(),
        "inputs": {
            "day": parsed_day,
            "time": time_of_day,
            "event": event,
            "historical_baseline": baseline,
            "event_name": event_name,
            "event_venue": event_venue,
            "data_source": data_source,
        },
        "score_breakdown": breakdown,
        "total_score": total,
        "prediction": score_to_label(total) if available_count else "Unknown",
        "confidence": CONFIDENCE_BY_INPUT_COUNT[available_count],
        "available_inputs": available_count,
        "missing_inputs": missing,
        "complete": complete,
        "possible_score_range": [total, high],
        "possible_categories": possible_categories if available_count else ["Quiet", "Moderate", "Busy"],
        "note": ("All four inputs supplied. Confidence is a rule-based workbook heuristic, "
                 "not a measured probability of correctness.") if complete else (
                     "Some inputs are missing: observed score and category are provisional; "
                     "unknown inputs could increase the score. Confidence is a workbook heuristic."
                 ),
    }
    return result


def submit_prediction(result: dict[str, Any], location_id: int,
                      source: str = "test",
                      api_url: str = "http://localhost:8000/api/crowd-predictions") -> dict[str, Any]:
    """Send the exact workbook 0-8 score, label, confidence and breakdown.

    Requires four inputs. Restricted to localhost for the project prototype.
    """
    if not isinstance(location_id, int) or isinstance(location_id, bool) or location_id < 1:
        raise ValueError("location_id must be a positive integer")
    if not result.get("complete"):
        raise ValueError("Supply all four inputs before sending a prediction")
    if source not in ("test", "algorithm"):
        raise ValueError("source must be 'test' or 'algorithm'")
    if api_url != "http://localhost:8000/api/crowd-predictions":
        raise ValueError("Submission restricted to the local Week 10 API")
    payload = {
        "location_id": location_id,
        "total_score": result["total_score"],
        "prediction": result["prediction"],
        "confidence": result["confidence"],
        "score_breakdown": result["score_breakdown"],
        "source": source,
    }
    request = Request(api_url, data=json.dumps(payload).encode("utf-8"),
                      headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urlopen(request, timeout=5) as response:
            stored = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        explanation = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"API returned HTTP {exc.code}: {explanation}") from exc
    except URLError as exc:
        raise RuntimeError(f"Could not reach local API: {exc.reason}") from exc
    return {"sent_payload": payload, "api_response": stored}


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Run Mohamed's Smart Crowd Prediction rules locally")
    parser.add_argument("--location", required=True, help='e.g. "Souq Waqif"')
    parser.add_argument("--location-id", type=int, help="existing SQLite location ID; required for --send-test")
    parser.add_argument("--day", help="Weekday or YYYY-MM-DD")
    parser.add_argument("--time", dest="time_of_day", help="e.g. 20:00, 5PM or 10PM")
    parser.add_argument("--event", help="none, small, or large")
    parser.add_argument("--baseline", help="quiet, moderate, or busy")
    parser.add_argument("--event-name", help="Optional event name (informational only)")
    parser.add_argument("--event-venue", help="Optional event venue (informational only)")
    parser.add_argument("--data-source", help="Optional manual source label")
    parser.add_argument("--send-test", action="store_true",
                        help="Send original 0–8 score to local API with source=test")
    parser.add_argument("--send", action="store_true",
                        help="Send original 0–8 score to local API with source=algorithm")
    args = parser.parse_args(argv)
    try:
        result = calculate_prediction(
            location=args.location, day=args.day, time_of_day=args.time_of_day,
            event=args.event, baseline=args.baseline,
            event_name=args.event_name, event_venue=args.event_venue,
            data_source=args.data_source,
        )
        print(json.dumps(result, indent=2, ensure_ascii=False))
        if args.send_test and args.send:
            raise ValueError("Use only one of --send or --send-test")
        if args.send_test or args.send:
            if args.location_id is None:
                raise ValueError("--location-id is required when sending")
            receipt = submit_prediction(result, args.location_id,
                                        source="algorithm" if args.send else "test")
            print("\nAPI SUBMISSION:\n" + json.dumps(receipt, indent=2))
        return 0
    except (ValueError, RuntimeError) as exc:
        print("Error:", exc, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
