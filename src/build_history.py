from __future__ import annotations

import argparse
import json
from collections import defaultdict
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCOPES = ("all", "5", "10", "20")
SG_KEYS = ("tee", "approach", "shortGame", "putting", "teeToGreen", "total")


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def event_sort_key(event: dict) -> tuple:
    raw = event.get("date")
    try:
        parsed = date.fromisoformat(raw) if raw else date.min
    except ValueError:
        parsed = date.min
    return (parsed, int(event.get("id", 0)))


def mean(values: list[float | int]) -> float | None:
    if not values:
        return None
    return round(sum(values) / len(values), 2)


def history_config() -> dict:
    path = ROOT / "config.json"
    if not path.exists():
        return {"defaultScope": "10", "scopes": list(SCOPES), "excludeEventIds": []}
    return (load_json(path).get("history") or {})


def scope_events(completed: list[dict], scope: str) -> list[dict]:
    newest_first = sorted(completed, key=event_sort_key, reverse=True)
    if scope == "all":
        return newest_first
    return newest_first[: int(scope)]


def player_event_record(event: dict, player: dict) -> dict:
    lb = player.get("leaderboard", {})
    return {
        "tournamentId": event["id"],
        "name": event.get("name") or event.get("tourName"),
        "date": event.get("date"),
        "course": event.get("course"),
        "netPosition": lb.get("netPosition"),
        "grossPosition": lb.get("grossPosition"),
        "netTotal": lb.get("netTotal"),
        "grossTotal": lb.get("grossTotal"),
        "sg": player.get("sg", {}),
        "stats": player.get("stats", {}),
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
                },
            )
            if not entry.get("name") and player.get("name"):
                entry["name"] = player["name"]

            lb = player.get("leaderboard", {})
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

            entry["events"].append(player_event_record(event, player))

    players = []
    for entry in by_player.values():
        sg_avg = {key: mean(entry["sgValues"].get(key, [])) for key in SG_KEYS}
        players.append(
            {
                "id": entry["id"],
                "name": entry["name"],
                "starts": len(entry["events"]),
                "avgNet": mean(entry["netPositions"]),
                "avgGross": mean(entry["grossPositions"]),
                "netWins": entry["netWins"],
                "grossWins": entry["grossWins"],
                "sg": sg_avg,
                "events": entry["events"],
            }
        )

    players.sort(
        key=lambda p: (
            p["avgNet"] is None,
            p["avgNet"] if p["avgNet"] is not None else 9999,
            -p["starts"],
            p["name"] or "",
        )
    )

    return {
        "eventCount": len(events),
        "eventIds": [event["id"] for event in events],
        "players": players,
    }


def build_history(discovery: dict, analyses_dir: Path) -> dict:
    completed = discovery.get("completed", [])
    config = history_config()
    excluded_ids = {int(x) for x in config.get("excludeEventIds", [])}
    configured_scopes = tuple(str(x) for x in config.get("scopes", SCOPES))
    default_scope = str(config.get("defaultScope", "10"))

    analyses: dict[int, dict] = {}
    missing = []
    for event in completed:
        event_id = int(event["id"])
        path = analyses_dir / f"{event_id}.json"
        if not path.exists():
            missing.append(event_id)
            continue
        analyses[event_id] = load_json(path)

    eligible = [event for event in completed if int(event["id"]) not in excluded_ids]
    excluded = [
        {**event, "profileHistoryEligible": False, "exclusionReason": "configured_exclusion"}
        for event in completed
        if int(event["id"]) in excluded_ids
    ]

    scopes = {
        scope: aggregate_scope(scope_events(eligible, scope), analyses)
        for scope in configured_scopes
    }

    return {
        "schemaVersion": 2,
        "tour": {"id": discovery.get("tourId"), "name": discovery.get("tourName")},
        "scopeDefinition": "Rolling windows are based on the league's most recent completed profile-eligible tournaments, not each player's most recent starts. Excluded team/special events remain in the archive but do not affect player scouting history.",
        "defaultScope": default_scope,
        "availableScopes": list(configured_scopes),
        "completedEvents": sorted(completed, key=event_sort_key, reverse=True),
        "profileEligibleEvents": sorted(eligible, key=event_sort_key, reverse=True),
        "excludedProfileEvents": sorted(excluded, key=event_sort_key, reverse=True),
        "analyzedEventIds": sorted(analyses.keys()),
        "missingAnalysisEventIds": sorted(missing),
        "scopes": scopes,
    }


def validate(history: dict) -> None:
    analyzed = set(history["analyzedEventIds"])
    if not analyzed:
        raise RuntimeError("History contains no analyzed tournaments")

    all_scope = history["scopes"]["all"]
    if not all_scope["players"]:
        raise RuntimeError("History contains no completed players")

    eligible_ids = {int(event["id"]) for event in history.get("profileEligibleEvents", [])}
    for scope_name, scope in history["scopes"].items():
        if any(int(event_id) not in eligible_ids for event_id in scope.get("eventIds", [])):
            raise RuntimeError(f"Profile-ineligible event leaked into scope {scope_name}")
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
    parser = argparse.ArgumentParser(description="Build rolling league history from analyzed SGT tournaments.")
    parser.add_argument("discovery", type=Path)
    parser.add_argument("--analyses-dir", type=Path, default=Path("data/analysis"))
    parser.add_argument("--output", type=Path, default=Path("data/history.json"))
    args = parser.parse_args()

    discovery_path = args.discovery if args.discovery.is_absolute() else ROOT / args.discovery
    analyses_dir = args.analyses_dir if args.analyses_dir.is_absolute() else ROOT / args.analyses_dir
    output = args.output if args.output.is_absolute() else ROOT / args.output

    history = build_history(load_json(discovery_path), analyses_dir)
    validate(history)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(history, indent=2) + "\n", encoding="utf-8")

    print(f"Wrote {output.relative_to(ROOT)}")
    print(f"Analyzed events: {len(history['analyzedEventIds'])}")
    print(f"Missing analyses: {history['missingAnalysisEventIds']}")
    print(f"Profile-eligible events: {len(history['profileEligibleEvents'])}")
    print(f"Excluded profile events: {[e['id'] for e in history['excludedProfileEvents']]}")
    for scope, data in history["scopes"].items():
        leader = data["players"][0]["name"] if data["players"] else None
        print(f"Scope {scope}: events={data['eventCount']} players={len(data['players'])} avg-net leader={leader}")


if __name__ == "__main__":
    main()
