from __future__ import annotations

import argparse
import json
from pathlib import Path

from analyze_tournament import analyze
from build_history import build_history, validate as validate_history
from discover import fetch_events_html, load_config, parse_events
from export_tournament import export_tournament

ROOT = Path(__file__).resolve().parents[1]


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def validate_event_against_sgt(event: dict, analysis: dict) -> None:
    expected_net = event.get("netWinner")
    expected_gross = event.get("grossWinner")
    actual_net = ((analysis.get("winners") or {}).get("net") or {}).get("name")
    actual_gross = ((analysis.get("winners") or {}).get("gross") or {}).get("name")

    if expected_net and actual_net != expected_net:
        raise RuntimeError(
            f"Tournament {event['id']} net winner mismatch: SGT event card={expected_net!r}, analysis={actual_net!r}"
        )
    if expected_gross and actual_gross != expected_gross:
        raise RuntimeError(
            f"Tournament {event['id']} gross winner mismatch: SGT event card={expected_gross!r}, analysis={actual_gross!r}"
        )


def enrich_metadata(analysis: dict, event: dict) -> dict:
    tournament = analysis.setdefault("tournament", {})
    tournament["id"] = event["id"]
    tournament["course"] = event.get("course")
    tournament["date"] = event.get("date")
    tournament["displayDate"] = event.get("displayDate")
    tournament["url"] = event.get("url")
    return analysis


def load_valid_existing_history() -> dict | None:
    history_path = ROOT / "data" / "history.json"
    if not history_path.exists():
        return None
    try:
        history = json.loads(history_path.read_text(encoding="utf-8"))
        validate_history(history)
        if not history.get("completedEvents"):
            return None
        return history
    except Exception as exc:
        print(f"Existing history is not a usable fallback: {exc}")
        return None


def add_pinned_completed_events(discovery: dict, config: dict) -> list[int]:
    completed = list(discovery.get("completed", []))
    known_ids = {int(event["id"]) for event in completed}
    added: list[int] = []

    for pinned in config.get("pinnedCompletedEvents", []):
        event_id = int(pinned["id"])
        if event_id in known_ids:
            continue
        completed.append(dict(pinned))
        known_ids.add(event_id)
        added.append(event_id)

    discovery["completed"] = completed
    return added


def carry_forward_validated_completed_events(discovery: dict, previous: dict | None) -> list[int]:
    """Preserve durable completed history when SGT returns only part of the tour.

    SGT's tour-events endpoint is useful for discovering new events, but it is not a
    reliable historical database: older completed events can disappear from a valid
    HTTP 200 response. Once an event has passed our deterministic validation and is
    present in history.json, absence from a later discovery response must not delete it.

    Current SGT discovery wins for IDs it does return. We only append previously
    validated event cards whose IDs are missing entirely from the current response.
    """
    if previous is None:
        return []

    completed = list(discovery.get("completed", []))
    known_ids = {int(event["id"]) for event in completed}
    carried: list[int] = []

    for prior in previous.get("completedEvents", []):
        event_id = int(prior["id"])
        if event_id in known_ids:
            continue
        completed.append(dict(prior))
        known_ids.add(event_id)
        carried.append(event_id)

    discovery["completed"] = completed
    return carried


def validate_history_did_not_shrink(previous: dict | None, current: dict, ignored_event_ids: set[int]) -> None:
    if previous is None:
        return

    previous_ids = {int(event["id"]) for event in previous.get("completedEvents", [])}
    current_ids = {int(event["id"]) for event in current.get("completedEvents", [])}
    disappeared = previous_ids - current_ids - ignored_event_ids
    if disappeared:
        raise RuntimeError(
            "Completed tournament history regressed; previously validated event IDs disappeared: "
            + ", ".join(str(x) for x in sorted(disappeared))
        )

    previous_dates = {
        int(event["id"]): event.get("date") for event in previous.get("completedEvents", [])
    }
    current_dates = {
        int(event["id"]): event.get("date") for event in current.get("completedEvents", [])
    }
    shared = previous_ids & current_ids
    date_regressions = [
        event_id
        for event_id in shared
        if previous_dates.get(event_id) and current_dates.get(event_id)
        and previous_dates[event_id] != current_dates[event_id]
    ]
    if date_regressions:
        raise RuntimeError(
            "Completed tournament chronology changed for previously validated event IDs: "
            + ", ".join(str(x) for x in sorted(date_regressions))
        )


def process_tour(*, refresh_all: bool = False) -> dict:
    config = load_config()
    tour_id = int(config["tourId"])
    tour_name = config.get("tourName")
    ignored_event_ids = {int(x) for x in config.get("ignoreEventIds", [])}
    existing_history = load_valid_existing_history()

    print(f"Discovering Tour {tour_id} ({tour_name})")
    discovery = parse_events(fetch_events_html(tour_id), tour_id, tour_name)

    pinned_added = add_pinned_completed_events(discovery, config)
    if pinned_added:
        print(
            "PINNED completed event IDs missing from SGT tour discovery: "
            + ", ".join(str(x) for x in pinned_added)
        )

    carried_forward = carry_forward_validated_completed_events(discovery, existing_history)
    if carried_forward:
        print(
            "CARRY FORWARD previously validated completed event IDs missing from SGT discovery: "
            + ", ".join(str(x) for x in carried_forward)
        )

    # SGT occasionally returns a normal HTTP 200 containing a login/error/HTML shell
    # instead of the events payload, or a partial payload that omits older completed
    # tournaments. Pinned events and previously validated completed history are merged
    # first, so a flaky discovery response cannot silently erase league history.
    discovered_completed = list(discovery.get("completed", []))
    if not discovered_completed:
        if existing_history is not None:
            print(
                "SGT discovery returned zero usable completed events. "
                "Preserving existing validated history and exiting cleanly with no publication changes."
            )
            return existing_history
        raise RuntimeError(
            "SGT discovery returned zero completed events and no valid existing history is available"
        )

    # Some SGT entries are test/wonky/non-league events that should never enter the
    # publishing pipeline. Remove configured IDs before analysis, history, latest-event
    # selection, or Discord can see them. Keep a small audit trail in discovery output.
    ignored_completed = [
        event for event in discovered_completed if int(event["id"]) in ignored_event_ids
    ]
    discovery["completed"] = [
        event for event in discovered_completed if int(event["id"]) not in ignored_event_ids
    ]
    discovery["ignoredCompleted"] = ignored_completed
    if ignored_completed:
        print(
            "IGNORED completed event IDs: "
            + ", ".join(str(event["id"]) for event in ignored_completed)
        )

    discovery_path = ROOT / "data" / "discovery" / f"{tour_id}.json"
    write_json(discovery_path, discovery)

    analyses_dir = ROOT / "data" / "analysis"
    raw_dir = ROOT / "data" / "work" / "tournaments"
    analyses_dir.mkdir(parents=True, exist_ok=True)
    raw_dir.mkdir(parents=True, exist_ok=True)

    processed = []
    reused = []
    for event in discovery.get("completed", []):
        event_id = int(event["id"])
        analysis_path = analyses_dir / f"{event_id}.json"

        if analysis_path.exists() and not refresh_all:
            analysis = json.loads(analysis_path.read_text(encoding="utf-8"))
            validate_event_against_sgt(event, analysis)
            reused.append(event_id)
            print(f"REUSE {event_id}: existing deterministic analysis validated against event metadata")
            continue

        print(f"PROCESS {event_id}: {event.get('course')} | {event.get('date')}")
        raw = export_tournament(event_id)
        raw_path = raw_dir / f"{event_id}.json"
        write_json(raw_path, raw)

        analysis = enrich_metadata(analyze(raw), event)
        validate_event_against_sgt(event, analysis)
        write_json(analysis_path, analysis)
        processed.append(event_id)

    history = build_history(discovery, analyses_dir)
    validate_history(history)
    validate_history_did_not_shrink(existing_history, history, ignored_event_ids)
    if history["missingAnalysisEventIds"]:
        raise RuntimeError(
            f"Completed events still missing deterministic analysis: {history['missingAnalysisEventIds']}"
        )
    history["processing"] = {
        "newlyProcessedEventIds": processed,
        "reusedEventIds": reused,
        "ignoredEventIds": sorted(ignored_event_ids),
        "pinnedEventIdsAddedToDiscovery": pinned_added,
        "carriedForwardValidatedEventIds": carried_forward,
    }
    history_path = ROOT / "data" / "history.json"
    write_json(history_path, history)

    print(
        f"Tour complete: completed={len(discovery.get('completed', []))} "
        f"ignored={len(ignored_completed)} pinned={pinned_added} carried={carried_forward} "
        f"processed={processed} reused={reused}"
    )
    return history


def main() -> None:
    parser = argparse.ArgumentParser(description="Incrementally discover, export, analyze, and aggregate an SGT tour.")
    parser.add_argument("--refresh-all", action="store_true", help="Re-export and re-analyze every completed event.")
    args = parser.parse_args()
    process_tour(refresh_all=args.refresh_all)


if __name__ == "__main__":
    main()
