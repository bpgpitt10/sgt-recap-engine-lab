from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from validate_recap_copy import validate
from write_recap import load_json, write_recap

ROOT = Path(__file__).resolve().parents[1]


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Regenerate every completed tournament recap with as-of-event history.")
    parser.add_argument("--model", default=os.environ.get("OPENAI_MODEL", "gpt-5.6-luna"))
    args = parser.parse_args()

    config = load_json(ROOT / "config.json")
    history = load_json(ROOT / "data/history.json")
    completed = list(reversed(history["completedEvents"]))  # oldest first for readable logs

    for index, event in enumerate(completed, start=1):
        tournament_id = int(event["id"])
        analysis_path = ROOT / "data/analysis" / f"{tournament_id}.json"
        if not analysis_path.exists():
            raise RuntimeError(f"Missing deterministic analysis for completed tournament {tournament_id}")
        print(f"[{index}/{len(completed)}] Writing {tournament_id} · {event.get('tourName')}")
        analysis = load_json(analysis_path)
        copy, facts = write_recap(analysis, config, history, args.model)
        validate(copy, facts)
        write_json(ROOT / "data/copy" / f"{tournament_id}.json", copy)
        write_json(ROOT / "data/facts" / f"{tournament_id}.json", facts)
        print(f"  prior eligible events: {facts['historicalContext']['priorEligibleEventIds']}")

    print(f"Generated and validated {len(completed)} historical recaps using {args.model}")


if __name__ == "__main__":
    main()
