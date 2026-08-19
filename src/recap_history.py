from __future__ import annotations

import re
from datetime import date

SG_KEYS = ("tee", "approach", "shortGame", "putting", "teeToGreen", "total")
PROFILE_STAT_KEYS = (
    "LONGEST DRIVE",
    "AVG DRIVE DISTANCE (FIR)",
    "FAIRWAYS HIT",
    "GREENS IN REGULATION",
    "GIR PROXIMITY",
    "SAND SAVES",
    "SAND SAVES ATTEMPTS",
    "TOTAL PUTTS",
    "TOTAL 3-PUTTS",
    "EAGLES",
    "BIRDIES",
    "BOGEYS",
    "DBL BOGEYS",
    "ACES",
    "TOTAL FEET OF PUTTS MADE",
)


def parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def sequence_number(name: str | None) -> int | None:
    if not name:
        return None
    match = re.search(r"\b(?:week|event|round)\s*(\d+)\b", name, re.IGNORECASE)
    return int(match.group(1)) if match else None


def confidently_before(candidate: dict, target: dict) -> bool:
    candidate_date = parse_date(candidate.get("date"))
    target_date = parse_date(target.get("date"))
    if not candidate_date or not target_date:
        return False
    if candidate_date < target_date:
        return True
    if candidate_date > target_date:
        return False

    candidate_seq = sequence_number(candidate.get("tourName") or candidate.get("name"))
    target_seq = sequence_number(target.get("name") or target.get("tourName"))
    if candidate_seq is not None and target_seq is not None:
        return candidate_seq < target_seq

    # Same-day events with no clear sequence are intentionally treated as ambiguous.
    return False


def mean(values: list[float]) -> float | None:
    return round(sum(values) / len(values), 2) if values else None


def evidence_level(starts: int) -> str:
    if starts <= 1:
        return "round_only"
    if starts == 2:
        return "possible_change"
    if starts < 5:
        return "trend"
    return "strong_trend"


def numeric(value: object) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    if value is None:
        return None
    match = re.search(r"[-+]?\d+(?:\.\d+)?", str(value).replace(",", ""))
    return float(match.group()) if match else None


def aggregate_prior_events(events: list[dict]) -> dict:
    net_positions = [event.get("netPosition") for event in events if isinstance(event.get("netPosition"), int)]
    gross_positions = [event.get("grossPosition") for event in events if isinstance(event.get("grossPosition"), int)]
    sg_values = {key: [] for key in SG_KEYS}
    stat_values = {key: [] for key in PROFILE_STAT_KEYS}

    for event in events:
        for key in SG_KEYS:
            value = (event.get("sg") or {}).get(key)
            if isinstance(value, (int, float)):
                sg_values[key].append(float(value))
        for key in PROFILE_STAT_KEYS:
            value = numeric((event.get("stats") or {}).get(key))
            if value is not None:
                stat_values[key].append(value)

    starts = len(events)
    return {
        "starts": starts,
        "evidenceLevel": evidence_level(starts),
        "avgNet": mean([float(value) for value in net_positions]),
        "avgGross": mean([float(value) for value in gross_positions]),
        "netWins": sum(1 for value in net_positions if value == 1),
        "grossWins": sum(1 for value in gross_positions if value == 1),
        "sg": {key: mean(values) for key, values in sg_values.items()},
        "stats": {key: mean(values) for key, values in stat_values.items()},
        "recentEvents": events[:5],
    }


def build_as_of_history(history: dict, target_tournament: dict, current_player_names: list[str]) -> dict:
    eligible_events = history.get("profileEligibleEvents", [])
    prior_event_ids = {
        int(event["id"])
        for event in eligible_events
        if confidently_before(event, target_tournament)
    }

    all_players = history.get("scopes", {}).get("all", {}).get("players", [])
    player_by_name = {player.get("name"): player for player in all_players if player.get("name")}
    players = {}
    for name in current_player_names:
        player = player_by_name.get(name)
        if not player:
            players[name] = aggregate_prior_events([])
            continue
        prior_events = [
            event
            for event in player.get("events", [])
            if int(event.get("tournamentId", -1)) in prior_event_ids
        ]
        players[name] = aggregate_prior_events(prior_events)

    return {
        "definition": "Only profile-eligible completed events confidently before this tournament are included. Future events and same-day ambiguous events are excluded.",
        "priorEligibleEventIds": sorted(prior_event_ids),
        "players": players,
    }
