from __future__ import annotations

import argparse
import json
from pathlib import Path

SCHEMA_VERSION = 1


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def completed_ids_oldest_first(history: dict) -> list[int]:
    # history.completedEvents is canonical newest-first.
    return [int(event["id"]) for event in reversed(history.get("completedEvents", []))]


def initial_state(history: dict, legacy_marker: Path | None = None) -> dict:
    published: list[int] = []
    migrated_from: int | None = None

    if legacy_marker and legacy_marker.exists():
        raw = legacy_marker.read_text(encoding="utf-8").strip()
        if raw:
            marker = int(raw)
            ordered = completed_ids_oldest_first(history)
            if marker not in ordered:
                raise RuntimeError(
                    f"Legacy published marker {marker} is not present in completed event history"
                )
            published = ordered[: ordered.index(marker) + 1]
            migrated_from = marker

    return {
        "schemaVersion": SCHEMA_VERSION,
        "publishedEventIds": published,
        "migratedFromLegacyMarker": migrated_from,
    }


def load_state(state_path: Path, history: dict, legacy_marker: Path | None = None) -> dict:
    if state_path.exists():
        state = load_json(state_path)
    else:
        state = initial_state(history, legacy_marker)

    if int(state.get("schemaVersion", 0)) != SCHEMA_VERSION:
        raise RuntimeError(f"Unsupported publish state schema: {state.get('schemaVersion')}")

    state["publishedEventIds"] = sorted(
        {int(value) for value in state.get("publishedEventIds", [])}
    )
    return state


def build_plan(history: dict, state: dict) -> dict:
    ordered = completed_ids_oldest_first(history)
    published = {int(value) for value in state.get("publishedEventIds", [])}
    missing = [event_id for event_id in ordered if event_id not in published]
    return {
        "schemaVersion": SCHEMA_VERSION,
        "completedEventIdsOldestFirst": ordered,
        "publishedEventIds": [event_id for event_id in ordered if event_id in published],
        "missingEventIdsOldestFirst": missing,
        "latestCompletedEventId": ordered[-1] if ordered else None,
        "queueLength": len(missing),
    }


def mark_published(state: dict, event_ids: list[int]) -> dict:
    published = {int(value) for value in state.get("publishedEventIds", [])}
    published.update(int(value) for value in event_ids)
    return {
        **state,
        "schemaVersion": SCHEMA_VERSION,
        "publishedEventIds": sorted(published),
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Plan and persist completed-event publication state without skipping failed events."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    plan = sub.add_parser("plan")
    plan.add_argument("history", type=Path)
    plan.add_argument("--state", type=Path, required=True)
    plan.add_argument("--legacy-marker", type=Path)
    plan.add_argument("--write-state", action="store_true")
    plan.add_argument("--output", type=Path)

    mark = sub.add_parser("mark")
    mark.add_argument("history", type=Path)
    mark.add_argument("--state", type=Path, required=True)
    mark.add_argument("--legacy-marker", type=Path)
    mark.add_argument("--event", type=int, action="append", required=True)

    args = parser.parse_args()
    history = load_json(args.history)
    state = load_state(args.state, history, args.legacy_marker)

    if args.command == "plan":
        if args.write_state and not args.state.exists():
            write_json(args.state, state)
        result = build_plan(history, state)
        if args.output:
            write_json(args.output, result)
        print(json.dumps(result))
        return

    state = mark_published(state, args.event)
    write_json(args.state, state)
    print(json.dumps(build_plan(history, state)))


if __name__ == "__main__":
    main()
