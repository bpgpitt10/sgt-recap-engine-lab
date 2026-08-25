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


def process_tour(*, refresh_all: bool = False) -> dict:
    config = load_config()
    tour_id = int(config["tourId"])
    tour_name = config.get("tourName")
    ignored_event_ids = {int(x) for x in config.get("ignoreEventIds", [])}

    print(f"Discovering Tour {tour_id} ({tour_name})")
    discovery = parse_events(fetch_events_html(tour_id), tour_id, tour_name)

    # Some SGT entries are test/wonky/non-league events that should never enter the
    # publishing pipeline. Remove configured IDs before analysis, history, latest-event
    # selection, or Discord can see them. Keep a small audit trail in discovery output.
    discovered_completed = list(discovery.get("completed", []))
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
            print(f"REUSE {event_id}: existing deterministic analysis validated against SGT event card")
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
    if history["missingAnalysisEventIds"]:
        raise RuntimeError(
            f"Completed events still missing deterministic analysis: {history['missingAnalysisEventIds']}"
        )
    history["processing"] = {
        "newlyProcessedEventIds": processed,
        "reusedEventIds": reused,
        "ignoredEventIds": sorted(ignored_event_ids),
    }
    history_path = ROOT / "data" / "history.json"
    write_json(history_path, history)

    print(
        f"Tour complete: completed={len(discovery.get('completed', []))} "
        f"ignored={len(ignored_completed)} processed={processed} reused={reused}"
    )
    return history


def main() -> None:
    parser = argparse.ArgumentParser(description="Incrementally discover, export, analyze, and aggregate an SGT tour.")
    parser.add_argument("--refresh-all", action="store_true", help="Re-export and re-analyze every completed event.")
    args = parser.parse_args()
    process_tour(refresh_all=args.refresh_all)


if __name__ == "__main__":
    main()
