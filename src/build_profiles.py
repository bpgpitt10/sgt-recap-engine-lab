from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SCOPES = ("all", "5", "10", "20")
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


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def event_sort_key(event: dict) -> tuple:
    raw = event.get("date")
    try:
        parsed = date.fromisoformat(raw) if raw else date.min
    except ValueError:
        parsed = date.min
    # Tournament ID is only a deterministic tie-breaker for equal dates.
    return (parsed, int(event.get("id", 0)))


def mean(values: list[float | int]) -> float | None:
    if not values:
        return None
    return round(sum(values) / len(values), 2)


def numeric_stat(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    match = re.search(r"[-+]?\d+(?:\.\d+)?", str(value).replace(",", ""))
    return float(match.group()) if match else None


def evidence_level(starts: int) -> str:
    if starts <= 1:
        return "round_only"
    if starts == 2:
        return "possible_change"
    if starts < 5:
        return "trend"
    return "strong_trend"


def history_settings(config: dict) -> tuple[list[str], str, set[int]]:
    raw = config.get("history") or {}
    scopes = [str(scope).lower() for scope in raw.get("scopes", DEFAULT_SCOPES)]
    if "all" not in scopes:
        scopes.insert(0, "all")
    for scope in scopes:
        if scope != "all" and (not scope.isdigit() or int(scope) <= 0):
            raise RuntimeError(f"Invalid rolling history scope: {scope!r}")
    default_scope = str(raw.get("defaultScope", "10")).lower()
    if default_scope not in scopes:
        raise RuntimeError(f"Default scope {default_scope!r} is not in configured scopes {scopes}")
    excluded = {int(value) for value in raw.get("excludeEventIds", [])}
    return scopes, default_scope, excluded


def eligible_events(completed: list[dict], excluded: set[int]) -> tuple[list[dict], list[dict]]:
    eligible = []
    excluded_events = []
    for event in completed:
        if int(event["id"]) in excluded:
            excluded_events.append({**event, "profileHistoryEligible": False, "exclusionReason": "configured_exclusion"})
        else:
            eligible.append({**event, "profileHistoryEligible": True})
    return eligible, excluded_events


def scope_events(eligible: list[dict], scope: str) -> list[dict]:
    newest_first = sorted(eligible, key=event_sort_key, reverse=True)
    if scope == "all":
        return newest_first
    return newest_first[: int(scope)]


def selected_stats(player: dict) -> dict:
    stats = player.get("stats") or {}
    return {key: stats.get(key) for key in PROFILE_STAT_KEYS if key in stats}


def player_event_record(event: dict, player: dict) -> dict:
    lb = player.get("leaderboard") or {}
    return {
        "tournamentId": event["id"],
        "name": event.get("tourName"),
        "date": event.get("date"),
        "course": event.get("course"),
        "netPosition": lb.get("netPosition"),
        "grossPosition": lb.get("grossPosition"),
        "netTotal": lb.get("netTotal"),
        "grossTotal": lb.get("grossTotal"),
        "netAdjustment": lb.get("netAdjustment"),
        "sg": player.get("sg") or {},
        "stats": selected_stats(player),
    }


def aggregate_scope(events: list[dict], analyses: dict[int, dict]) -> dict:
    by_player: dict[int, dict] = {}

    for event in events:
        analysis = analyses.get(int(event["id"]))
        if not analysis:
            continue
        for player in analysis.get("players", []):
            if not player.get("completed"):
                continue
            player_id = int(player["id"])
            entry = by_player.setdefault(
                player_id,
                {
                    "id": player_id,
                    "name": player.get("name"),
                    "events": [],
                    "netPositions": [],
                    "grossPositions": [],
                    "netWins": 0,
                    "grossWins": 0,
                    "sgValues": defaultdict(list),
                    "statValues": defaultdict(list),
                },
            )
            if not entry.get("name") and player.get("name"):
                entry["name"] = player["name"]

            lb = player.get("leaderboard") or {}
            net_pos = lb.get("netPosition")
            gross_pos = lb.get("grossPosition")
            if isinstance(net_pos, int):
                entry["netPositions"].append(net_pos)
                if net_pos == 1:
                    entry["netWins"] += 1
            if isinstance(gross_pos, int):
                entry["grossPositions"].append(gross_pos)
                if gross_pos == 1:
                    entry["grossWins"] += 1

            for key in SG_KEYS:
                value = (player.get("sg") or {}).get(key)
                if isinstance(value, (int, float)):
                    entry["sgValues"][key].append(float(value))

            stats = player.get("stats") or {}
            for key in PROFILE_STAT_KEYS:
                value = numeric_stat(stats.get(key))
                if value is not None:
                    entry["statValues"][key].append(value)

            entry["events"].append(player_event_record(event, player))

    players = []
    for entry in by_player.values():
        starts = len(entry["events"])
        players.append(
            {
                "id": entry["id"],
                "name": entry["name"],
                "starts": starts,
                "evidenceLevel": evidence_level(starts),
                "avgNet": mean(entry["netPositions"]),
                "avgGross": mean(entry["grossPositions"]),
                "netWins": entry["netWins"],
                "grossWins": entry["grossWins"],
                "sg": {key: mean(entry["sgValues"].get(key, [])) for key in SG_KEYS},
                "stats": {key: mean(entry["statValues"].get(key, [])) for key in PROFILE_STAT_KEYS},
                "events": entry["events"],
            }
        )

    players.sort(
        key=lambda player: (
            player["avgNet"] is None,
            player["avgNet"] if player["avgNet"] is not None else 9999,
            -player["starts"],
            player["name"] or "",
        )
    )

    return {
        "eventCount": len(events),
        "eventIds": [event["id"] for event in events],
        "players": players,
    }


def build_profiles(discovery: dict, analyses_dir: Path, config: dict) -> dict:
    completed = sorted(discovery.get("completed", []), key=event_sort_key, reverse=True)
    scopes, default_scope, excluded_ids = history_settings(config)
    profile_eligible, excluded_events = eligible_events(completed, excluded_ids)

    analyses: dict[int, dict] = {}
    missing = []
    for event in completed:
        event_id = int(event["id"])
        path = analyses_dir / f"{event_id}.json"
        if not path.exists():
            missing.append(event_id)
            continue
        analyses[event_id] = load_json(path)

    output_scopes = {
        scope: aggregate_scope(scope_events(profile_eligible, scope), analyses)
        for scope in scopes
    }

    return {
        "schemaVersion": 2,
        "tour": {"id": discovery.get("tourId"), "name": discovery.get("tourName")},
        "scopeDefinition": "Rolling windows use the league's most recent profile-eligible completed tournaments, not each player's most recent starts.",
        "defaultScope": default_scope,
        "availableScopes": scopes,
        "completedEvents": completed,
        "profileEligibleEvents": sorted(profile_eligible, key=event_sort_key, reverse=True),
        "excludedProfileEvents": sorted(excluded_events, key=event_sort_key, reverse=True),
        "analyzedEventIds": sorted(analyses.keys()),
        "missingAnalysisEventIds": sorted(missing),
        "scopes": output_scopes,
    }


def validate(history: dict) -> None:
    if not history["analyzedEventIds"]:
        raise RuntimeError("Profile history contains no analyzed tournaments")
    if history["missingAnalysisEventIds"]:
        raise RuntimeError(f"Completed events missing analysis: {history['missingAnalysisEventIds']}")
    if not history["scopes"]["all"]["players"]:
        raise RuntimeError("Profile history contains no completed players")

    eligible_ids = {event["id"] for event in history["profileEligibleEvents"]}
    excluded_ids = {event["id"] for event in history["excludedProfileEvents"]}
    if eligible_ids & excluded_ids:
        raise RuntimeError("An event cannot be both profile eligible and excluded")

    for scope_name, scope in history["scopes"].items():
        if not set(scope["eventIds"]).issubset(eligible_ids):
            raise RuntimeError(f"Scope {scope_name} contains excluded events")
        last_avg = None
        for player in scope["players"]:
            if player["starts"] <= 0:
                raise RuntimeError(f"Invalid starts for {player['name']} in scope {scope_name}")
            avg = player["avgNet"]
            if avg is not None and last_avg is not None and avg < last_avg:
                raise RuntimeError(f"AVG NET ordering failed in scope {scope_name}")
            if avg is not None:
                last_avg = avg


def main() -> None:
    parser = argparse.ArgumentParser(description="Build rolling player-profile history from analyzed SGT tournaments.")
    parser.add_argument("discovery", type=Path)
    parser.add_argument("--analyses-dir", type=Path, default=Path("data/analysis"))
    parser.add_argument("--config", type=Path, default=Path("config.json"))
    parser.add_argument("--output", type=Path, default=Path("data/history.json"))
    args = parser.parse_args()

    discovery_path = args.discovery if args.discovery.is_absolute() else ROOT / args.discovery
    analyses_dir = args.analyses_dir if args.analyses_dir.is_absolute() else ROOT / args.analyses_dir
    config_path = args.config if args.config.is_absolute() else ROOT / args.config
    output = args.output if args.output.is_absolute() else ROOT / args.output

    history = build_profiles(load_json(discovery_path), analyses_dir, load_json(config_path))
    validate(history)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(history, indent=2) + "\n", encoding="utf-8")

    print(f"Wrote {output.relative_to(ROOT)}")
    print(f"Completed events: {len(history['completedEvents'])}")
    print(f"Profile eligible: {len(history['profileEligibleEvents'])}")
    print(f"Excluded from profiles: {[event['id'] for event in history['excludedProfileEvents']]}")
    for scope, data in history["scopes"].items():
        leader = data["players"][0]["name"] if data["players"] else None
        print(f"Scope {scope}: events={data['eventCount']} players={len(data['players'])} avg-net leader={leader}")


if __name__ == "__main__":
    main()
