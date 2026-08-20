from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import render_high_loft as renderer
import write_high_loft_recap  # noqa: F401 - applies High Loft prompt/validation overrides
import write_league_copy
import write_recap

ROOT = Path(__file__).resolve().parents[1]


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def normalize_analysis(analysis: dict) -> dict:
    players = {
        p.get("name"): p
        for p in analysis.get("players", [])
        if p.get("completed")
    }
    normalized = []
    for original in analysis.get("carnage", []):
        item = dict(original)
        raw_hole = item.get("hole")
        if not isinstance(raw_hole, dict):
            player = players.get(item.get("name")) or {}
            worst_hole = player.get("worstHole")
            if not isinstance(worst_hole, dict):
                raise RuntimeError(
                    f"Cannot normalize Carnage hole for {item.get('name')} in "
                    f"tournament {analysis.get('tournament', {}).get('id')}"
                )
            item["hole"] = worst_hole
        normalized.append(item)
    analysis = dict(analysis)
    analysis["carnage"] = normalized
    return analysis


def main() -> None:
    parser = argparse.ArgumentParser(description="One-time editorial backfill for all High Loft completed-event recaps.")
    parser.add_argument("--production-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path("site-high-loft-backfill"))
    parser.add_argument("--model", default=os.environ.get("OPENAI_MODEL", "gpt-5.6-luna"))
    args = parser.parse_args()

    if not os.environ.get("OPENAI_API_KEY"):
        raise RuntimeError("OPENAI_API_KEY is not set")

    production_root = args.production_root.resolve()
    output = args.output if args.output.is_absolute() else ROOT / args.output
    output.mkdir(parents=True, exist_ok=True)
    (output / "recaps").mkdir(parents=True, exist_ok=True)

    cfg = load(ROOT / "config.json")
    history = load(ROOT / "data" / "history.json")
    analyses = {
        int(p.stem): normalize_analysis(load(p))
        for p in (ROOT / "data" / "analysis").glob("*.json")
    }
    completed = history.get("completedEvents", [])
    excluded = {int(e["id"]) for e in history.get("excludedProfileEvents", [])}

    # Refresh landing-page scouting copy from the same current verified history.
    league_copy, league_facts = write_league_copy.write_all(history, args.model)
    (ROOT / "data" / "league-copy.json").write_text(
        json.dumps(league_copy, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    (ROOT / "data" / "league-facts.json").write_text(
        json.dumps(league_facts, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    copies: dict[int, dict] = {}
    for event in reversed(completed):
        event_id = int(event["id"])
        analysis = analyses.get(event_id)
        if not analysis:
            raise RuntimeError(f"Missing deterministic analysis for completed event {event_id}")
        print(f"Rewriting High Loft recap copy for SGT {event_id}...")
        copy, facts = write_recap.write_recap(analysis, cfg, history, args.model)
        copies[event_id] = copy
        (ROOT / "data" / "copy" / f"{event_id}.json").write_text(
            json.dumps(copy, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        facts_dir = ROOT / "data" / "facts"
        facts_dir.mkdir(parents=True, exist_ok=True)
        (facts_dir / f"{event_id}.json").write_text(
            json.dumps(facts, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )

        slug = renderer.recap_slug(event, cfg)
        page = renderer.recap_page(event, analysis, copy, cfg, event_id in excluded)
        (output / "recaps" / f"{slug}.html").write_text(page, encoding="utf-8")

    latest_event = completed[0]
    latest_id = int(latest_event["id"])
    landing = renderer.landing(history, league_copy, analyses, copies[latest_id], cfg, production_root)
    (output / "index.html").write_text(landing, encoding="utf-8")

    recap_files = sorted((output / "recaps").glob("*.html"))
    if len(recap_files) != len(completed):
        raise RuntimeError(f"Expected {len(completed)} recap pages, rendered {len(recap_files)}")

    for page in recap_files:
        text = page.read_text(encoding="utf-8")
        for required in (
            'assets/recap-v2.css', 'Tournament leaderboard', 'data-board="net"',
            'data-board="gross"', 'Carnage Board', 'Player by player', 'State of the league'
        ):
            if required.lower() not in text.lower():
                raise RuntimeError(f"{page.name} missing required recap element: {required}")

    print(f"Editorial backfill rendered {len(recap_files)} completed-event recaps.")
    print("Discord is intentionally not part of this backfill.")


if __name__ == "__main__":
    main()
